from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from pos.models import OrderItem, Product
from .models import AIQuery, ReorderSuggestion


class AIServiceUnavailable(Exception):
    """Raised when no reviewed AI provider is enabled for this environment."""

    code = "ai_unavailable"
    detail = "AI assistance is currently unavailable. No response was generated."


def _require_enabled_provider():
    """Fail closed until a reviewed provider integration is explicitly enabled.

    Phase 19 intentionally does not add or claim a production AI provider.
    Returning a hard unavailable state prevents a provider exception from being
    presented to users as if it were a generated business answer.
    """
    if not getattr(settings, "AI_FEATURE_ENABLED", False):
        raise AIServiceUnavailable()


def _avg_daily_sales(*, tenant, product, days=30):
    since = timezone.now() - timedelta(days=days)
    qs = OrderItem.objects.filter(
        tenant=tenant,
        product=product,
        order__created_at__gte=since,
        order__status__in=["paid", "partially_refunded"],
    )
    total = qs.aggregate(t=Sum("quantity"))["t"] or Decimal("0")
    return Decimal(total) / Decimal(days)


def generate_reorder_suggestions(*, tenant):
    """Create deterministic, tenant-scoped reorder suggestions.

    This calculation is not an LLM response and is retained because it is a
    deterministic analysis over products and sales belonging to ``tenant``.
    """
    suggestions = []
    for product in Product.objects.filter(tenant=tenant, is_active=True):
        avg_daily = _avg_daily_sales(tenant=tenant, product=product)
        if avg_daily <= 0:
            continue
        days_of_stock = Decimal(product.stock_quantity) / avg_daily
        lead_time = 7
        reorder_point = max((avg_daily * lead_time * Decimal("1.5")), Decimal(product.min_stock or 1))
        if Decimal(product.stock_quantity) > reorder_point and days_of_stock > 14:
            continue
        suggested_qty = max(int((avg_daily * 30) - product.stock_quantity), int(reorder_point))
        confidence = Decimal("0.85") if avg_daily > 2 else Decimal("0.60")
        rationale = (
            f"Avg {avg_daily:.1f}/day, {days_of_stock:.0f} days of stock left, "
            f"reorder point {reorder_point:.0f}, lead time {lead_time}d."
        )
        suggestion = ReorderSuggestion.objects.create(
            tenant=tenant,
            product=product,
            suggested_qty=suggested_qty,
            current_stock=product.stock_quantity,
            avg_daily_sales=avg_daily,
            days_of_stock=days_of_stock,
            lead_time_days=lead_time,
            confidence=confidence,
            rationale=rationale,
        )
        suggestions.append(suggestion.id)
    return {"generated": len(suggestions), "ids": suggestions}


def _build_context(*, tenant, question):
    """Gather only data owned by the supplied canonical tenant."""
    context = {"question": question}
    question_lower = question.lower()
    if any(word in question_lower for word in ["sale", "revenue", "profit", "margin", "today", "week", "month"]):
        context["reporting_note"] = "Tenant-scoped reporting data is available through the authenticated reporting workspace."
    if any(word in question_lower for word in ["product", "stock", "inventory", "reorder", "low"]):
        context["low_stock_products"] = list(
            Product.objects.filter(tenant=tenant, is_active=True, stock_quantity__lte=5)
            .values("name", "sku", "stock_quantity")[:20]
        )
    return context


def ask(*, tenant, question, user=None, model="automatic"):
    """Return an LLM answer only when an approved provider is enabled.

    A provider failure is intentionally surfaced as an unavailable state and is
    not persisted as a fabricated user-visible answer.
    """
    _require_enabled_provider()
    context = _build_context(tenant=tenant, question=question)
    prompt = (
        "You are a POS business analyst. Answer the user's question using ONLY the provided data. "
        "Be concise and specific. Include numbers.\n\n"
        f"Question: {question}\n\nData context: {context}"
    )
    try:
        from base44.integrations import Core
        result = Core.InvokeLLM(prompt=prompt, model=model)
    except Exception as exc:
        raise AIServiceUnavailable() from exc

    answer = result if isinstance(result, str) else str(result)
    query = AIQuery.objects.create(
        tenant=tenant,
        user=user,
        question=question,
        answer=answer,
        data=context,
        model=model,
        tokens_used=0,
    )
    return {"id": query.id, "answer": answer, "status": "completed"}


def daily_summary(*, tenant, user=None, model="automatic"):
    """Generate an audited tenant-scoped daily summary when a provider is enabled."""
    _require_enabled_provider()
    data = {"reporting_note": "Tenant-scoped end-of-day reporting is available through the authenticated reporting workspace."}
    prompt = f"Write a concise end-of-day business summary for a retail POS. Data: {data}"
    try:
        from base44.integrations import Core
        result = Core.InvokeLLM(prompt=prompt, model=model)
    except Exception as exc:
        raise AIServiceUnavailable() from exc

    answer = result if isinstance(result, str) else str(result)
    query = AIQuery.objects.create(
        tenant=tenant,
        user=user,
        question="End-of-day summary",
        answer=answer,
        data=data,
        model=model,
    )
    return {"id": query.id, "summary": answer, "data": data, "status": "completed"}
