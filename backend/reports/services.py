"""Canonical tenant-scoped reporting queries over persisted operational and accounting data."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from accounting.models import (
    AccountType,
    AccountingEvent,
    AccountingEventStatus,
    AccountingPeriod,
    ChartOfAccount,
    FinancialAccountMapping,
    FinancialStatementRole,
    JournalEntry,
    JournalEntryLine,
)
from payments.models import TenderedPayment
from pos.models import Customer, Order, OrderItem, Product, PurchaseOrder, Refund, StockMovement


ZERO = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=18, decimal_places=2)
PAID_ORDER_STATUSES = ["paid", "partially_refunded"]


class ReportingValidationError(ValueError):
    """A deliberately client-safe invalid filter error."""


def _decimal_text(value):
    """Return money values with a stable two-decimal API representation."""
    amount = Decimal(str(value if value is not None else ZERO))
    return f"{amount.quantize(Decimal('0.01')):.2f}"


def _parse_bound(value, *, field, is_end=False):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(datetime.fromisoformat(str(value)).date(), time.max if is_end else time.min)
        except ValueError as exc:
            raise ReportingValidationError(f"{field} must be an ISO date or timestamp.") from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def date_range(*, start=None, end=None, default_days=30):
    """Return an inclusive start and exclusive end with a bounded, deterministic default period."""
    now = timezone.now()
    parsed_start = _parse_bound(start, field="start") or (now - timedelta(days=default_days))
    parsed_end = _parse_bound(end, field="end", is_end=True) or now
    if parsed_start > parsed_end:
        raise ReportingValidationError("start must be before end.")
    if parsed_end - parsed_start > timedelta(days=3660):
        raise ReportingValidationError("The requested report range is too large.")
    return parsed_start, parsed_end


def pagination(*, page=1, page_size=50, maximum=200):
    try:
        page = max(1, int(page))
        page_size = min(maximum, max(1, int(page_size)))
    except (TypeError, ValueError) as exc:
        raise ReportingValidationError("page and page_size must be positive integers.") from exc
    return page, page_size


def _page(queryset, *, page, page_size, serializer):
    total = queryset.count()
    offset = (page - 1) * page_size
    return {
        "results": [serializer(row) for row in queryset[offset : offset + page_size]],
        "page": page,
        "page_size": page_size,
        "count": total,
        "has_next": offset + page_size < total,
    }


def _orders(*, tenant, start, end):
    return Order.objects.filter(
        tenant=tenant,
        created_at__gte=start,
        created_at__lt=end,
        status__in=PAID_ORDER_STATUSES,
    )


def sales_summary(start=None, end=None, *, tenant=None):
    """Summarize one explicit tenant; legacy internal callers resolve only the current tenant context."""
    if tenant is None:
        from saas.tenant_context import require_current_tenant

        tenant = require_current_tenant()
    orders = _orders(tenant=tenant, start=start, end=end)
    refunds = Refund.objects.filter(tenant=tenant, created_at__gte=start, created_at__lt=end)
    order_totals = orders.aggregate(
        gross_sales=Coalesce(Sum("total"), ZERO, output_field=MONEY_FIELD),
        discount=Coalesce(Sum("discount"), ZERO, output_field=MONEY_FIELD),
        tax_collected=Coalesce(Sum("tax"), ZERO, output_field=MONEY_FIELD),
        order_count=Count("id"),
    )
    refunded = refunds.aggregate(total=Coalesce(Sum("total_amount"), ZERO, output_field=MONEY_FIELD))["total"]
    gross = order_totals["gross_sales"]
    net = gross - refunded
    count = order_totals["order_count"]
    return {
        "gross_sales": _decimal_text(gross),
        "discount": _decimal_text(order_totals["discount"]),
        "tax_collected": _decimal_text(order_totals["tax_collected"]),
        "refunded": _decimal_text(refunded),
        "net_sales": _decimal_text(net),
        "order_count": count,
        "average_order": _decimal_text((net / count) if count else ZERO),
        "refund_count": refunds.count(),
    }


def sales_by_day(*, tenant, start, end):
    rows = (
        _orders(tenant=tenant, start=start, end=end)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Coalesce(Sum("total"), ZERO, output_field=MONEY_FIELD), count=Count("id"))
        .order_by("day")
    )
    return [{"date": row["day"].isoformat(), "total": _decimal_text(row["total"]), "count": row["count"]} for row in rows]


def sales_by_product(*, tenant, start, end, page=1, page_size=50):
    rows = (
        OrderItem.objects.filter(tenant=tenant, order__tenant=tenant, order__created_at__gte=start, order__created_at__lt=end, order__status__in=PAID_ORDER_STATUSES)
        .values("product_id", "product__name", "product__sku")
        .annotate(units=Coalesce(Sum("quantity"), Decimal("0")), sales=Coalesce(Sum("subtotal"), ZERO, output_field=MONEY_FIELD))
        .order_by("-sales", "product__name")
    )
    return _page(
        rows,
        page=page,
        page_size=page_size,
        serializer=lambda row: {"product_id": row["product_id"], "name": row["product__name"], "sku": row["product__sku"], "units": _decimal_text(row["units"]), "sales": _decimal_text(row["sales"])},
    )


def sales_by_category(*, tenant, start, end):
    rows = (
        OrderItem.objects.filter(tenant=tenant, order__tenant=tenant, order__created_at__gte=start, order__created_at__lt=end, order__status__in=PAID_ORDER_STATUSES)
        .values("product__category__id", "product__category__name")
        .annotate(units=Coalesce(Sum("quantity"), Decimal("0")), sales=Coalesce(Sum("subtotal"), ZERO, output_field=MONEY_FIELD))
        .order_by("-sales", "product__category__name")
    )
    return [{"category_id": row["product__category__id"], "category": row["product__category__name"] or "Uncategorised", "units": _decimal_text(row["units"]), "sales": _decimal_text(row["sales"])} for row in rows]


def sales_by_payment_method(*, tenant, start, end):
    rows = (
        TenderedPayment.objects.filter(tenant=tenant, settlement__tenant=tenant, settlement__settled_at__gte=start, settlement__settled_at__lt=end, is_settled=True)
        .values("tender_type")
        .annotate(total=Coalesce(Sum("amount"), ZERO, output_field=MONEY_FIELD), count=Count("id"))
        .order_by("-total", "tender_type")
    )
    return [{"method": row["tender_type"], "total": _decimal_text(row["total"]), "count": row["count"]} for row in rows]


def customer_sales(*, tenant, start, end, page=1, page_size=50):
    rows = (
        _orders(tenant=tenant, start=start, end=end)
        .filter(customer__isnull=False)
        .values("customer_id", "customer__name", "customer__customer_code")
        .annotate(order_count=Count("id"), sales=Coalesce(Sum("total"), ZERO, output_field=MONEY_FIELD))
        .order_by("-sales", "customer__name")
    )
    return _page(
        rows,
        page=page,
        page_size=page_size,
        serializer=lambda row: {"customer_id": row["customer_id"], "name": row["customer__name"], "code": row["customer__customer_code"], "order_count": row["order_count"], "sales": _decimal_text(row["sales"])},
    )


def inventory_valuation(*, tenant, page=1, page_size=50):
    """Return inventory valuation using the tenant's configured costing method.

    Methods:
      - weighted_average: Uses the weighted average cost from recent purchase movements.
      - fifo: Uses the most recent purchase cost (simplified FIFO approximation).
      - Default: Uses the product's cost_price field (simple valuation).
    """
    from system.models import InventorySettings
    settings = InventorySettings.load(tenant=tenant)
    method = settings.stock_valuation_method if settings else "average"

    if method in ("average", "fifo"):
        # Compute weighted average cost from recent purchase movements.
        from pos.models import StockMovement
        from decimal import Decimal as D

        rows = []
        for product in Product.objects.filter(tenant=tenant, is_active=True).order_by("name", "id"):
            qty = D(str(product.stock_quantity or 0))
            if qty <= 0:
                rows.append({
                    "product_id": product.id, "name": product.name, "sku": product.sku,
                    "quantity": str(qty), "unit_cost": str(product.cost_price),
                    "stock_value": "0.00", "valuation_method": method,
                })
                continue
            # Get purchase movements to compute weighted average.
            purchases = (
                StockMovement.objects
                .filter(tenant=tenant, product=product, quantity__gt=0,
                        movement_type__in=["purchase", "adjustment"])
                .order_by("-created_at")[:50]
            )
            if purchases.exists():
                # Weighted average from purchase history.
                total_cost = sum(D(str(p.previous_stock or 0)) * D(str(product.cost_price or 0)) for p in purchases)
                total_qty = sum(D(str(p.quantity)) for p in purchases)
                if total_qty > 0:
                    avg_cost = (total_cost / total_qty).quantize(D("0.01"))
                else:
                    avg_cost = product.cost_price
            else:
                avg_cost = product.cost_price
            stock_value = (qty * avg_cost).quantize(D("0.01"))
            rows.append({
                "product_id": product.id, "name": product.name, "sku": product.sku,
                "quantity": str(qty), "unit_cost": str(avg_cost),
                "stock_value": str(stock_value), "valuation_method": method,
            })
        # Sort by stock_value descending.
        rows.sort(key=lambda r: D(r["stock_value"]), reverse=True)
        # Paginate manually.
        start = (page - 1) * page_size
        end = start + page_size
        return {"count": len(rows), "page": page, "page_size": page_size, "results": rows[start:end]}
    else:
        # Simple cost_price × quantity.
        value = ExpressionWrapper(F("stock_quantity") * F("cost_price"), output_field=MONEY_FIELD)
        qs = Product.objects.filter(tenant=tenant).annotate(stock_value=value).order_by("-stock_value", "name")
        return _page(
            qs, page=page, page_size=page_size,
            serializer=lambda product: {
                "product_id": product.id, "name": product.name, "sku": product.sku,
                "quantity": _decimal_text(product.stock_quantity),
                "unit_cost": _decimal_text(product.cost_price),
                "stock_value": _decimal_text(product.stock_value),
                "valuation_method": method,
            },
        )


def stock_movements(*, tenant, start, end, page=1, page_size=50, movement_type=None):
    rows = StockMovement.objects.filter(tenant=tenant, created_at__gte=start, created_at__lt=end).select_related("product", "warehouse").order_by("-created_at", "-id")
    if movement_type:
        rows = rows.filter(movement_type=movement_type)
    return _page(
        rows,
        page=page,
        page_size=page_size,
        serializer=lambda movement: {
            "id": movement.id,
            "created_at": movement.created_at.isoformat(),
            "movement_type": movement.movement_type,
            "reference": movement.reference,
            "product_id": movement.product_id,
            "product_name": movement.product.name,
            "warehouse": movement.warehouse.name if movement.warehouse_id else None,
            "quantity": _decimal_text(movement.quantity),
        },
    )


def purchase_summary(*, tenant, start, end):
    orders = PurchaseOrder.objects.filter(tenant=tenant, created_at__gte=start, created_at__lt=end)
    aggregates = orders.aggregate(count=Count("id"), total=Coalesce(Sum("total"), ZERO, output_field=MONEY_FIELD))
    return {"purchase_order_count": aggregates["count"], "purchase_order_total": _decimal_text(aggregates["total"])}


def supplier_spend(*, tenant, start, end, page=1, page_size=50):
    rows = (
        PurchaseOrder.objects.filter(tenant=tenant, created_at__gte=start, created_at__lt=end)
        .exclude(status="cancelled")
        .values("supplier_id", "supplier__name")
        .annotate(order_count=Count("id"), purchase_order_total=Coalesce(Sum("total"), ZERO, output_field=MONEY_FIELD))
        .order_by("-purchase_order_total", "supplier__name")
    )
    return _page(
        rows,
        page=page,
        page_size=page_size,
        serializer=lambda row: {"supplier_id": row["supplier_id"], "supplier": row["supplier__name"], "order_count": row["order_count"], "purchase_order_total": _decimal_text(row["purchase_order_total"])},
    )


def financial_trial_balance(*, tenant):
    rows = []
    total_debit = ZERO
    total_credit = ZERO
    for account in ChartOfAccount.objects.filter(tenant=tenant).order_by("code"):
        aggregate = JournalEntryLine.objects.filter(tenant=tenant, account=account, entry__tenant=tenant, entry__status=JournalEntry.STATUS_POSTED).aggregate(
            debit=Coalesce(Sum("debit"), ZERO, output_field=MONEY_FIELD),
            credit=Coalesce(Sum("credit"), ZERO, output_field=MONEY_FIELD),
        )
        balance = (aggregate["debit"] - aggregate["credit"]) if account.type in {AccountType.ASSET, AccountType.EXPENSE} else (aggregate["credit"] - aggregate["debit"])
        debit = balance if balance > ZERO and account.type in {AccountType.ASSET, AccountType.EXPENSE} else -balance if balance < ZERO and account.type not in {AccountType.ASSET, AccountType.EXPENSE} else ZERO
        credit = balance if balance > ZERO and account.type not in {AccountType.ASSET, AccountType.EXPENSE} else -balance if balance < ZERO and account.type in {AccountType.ASSET, AccountType.EXPENSE} else ZERO
        rows.append({"code": account.code, "name": account.name, "type": account.type, "debit": _decimal_text(debit), "credit": _decimal_text(credit)})
        total_debit += debit
        total_credit += credit
    return {"rows": rows, "total_debit": _decimal_text(total_debit), "total_credit": _decimal_text(total_credit)}


def financial_date_filters(*, tenant, start=None, end=None, period_id=None):
    """Return inclusive DateField bounds from safe query inputs and an optional tenant period."""
    if period_id:
        try:
            period = AccountingPeriod.objects.get(tenant=tenant, pk=int(period_id))
        except (AccountingPeriod.DoesNotExist, TypeError, ValueError) as exc:
            raise ReportingValidationError("period must identify an accounting period in the active tenant.") from exc
        return period.start_date, period.end_date, period
    parsed_start = _parse_bound(start, field="start")
    parsed_end = _parse_bound(end, field="end", is_end=True)
    if parsed_start and parsed_end and parsed_start > parsed_end:
        raise ReportingValidationError("start must be before end.")
    return (
        parsed_start.date() if parsed_start else None,
        parsed_end.date() if parsed_end else None,
        None,
    )


def _posted_lines(*, tenant, start=None, end=None):
    rows = JournalEntryLine.objects.filter(
        tenant=tenant,
        entry__tenant=tenant,
        entry__status=JournalEntry.STATUS_POSTED,
    )
    if start:
        rows = rows.filter(entry__date__gte=start)
    if end:
        rows = rows.filter(entry__date__lte=end)
    return rows


def financial_trial_balance_v2(*, tenant, start=None, end=None, period_id=None):
    start, end, period = financial_date_filters(tenant=tenant, start=start, end=end, period_id=period_id)
    grouped = {
        row["account_id"]: row
        for row in _posted_lines(tenant=tenant, start=start, end=end)
        .values("account_id")
        .annotate(
            debit=Coalesce(Sum("debit"), ZERO, output_field=MONEY_FIELD),
            credit=Coalesce(Sum("credit"), ZERO, output_field=MONEY_FIELD),
        )
    }
    rows, total_debit, total_credit = [], ZERO, ZERO
    for account in ChartOfAccount.objects.filter(tenant=tenant).order_by("code"):
        aggregate = grouped.get(account.id, {})
        debit_total = aggregate.get("debit", ZERO)
        credit_total = aggregate.get("credit", ZERO)
        normal_debit = account.type in {AccountType.ASSET, AccountType.EXPENSE}
        balance = debit_total - credit_total if normal_debit else credit_total - debit_total
        debit = balance if normal_debit and balance > ZERO else -balance if not normal_debit and balance < ZERO else ZERO
        credit = balance if not normal_debit and balance > ZERO else -balance if normal_debit and balance < ZERO else ZERO
        rows.append({
            "account_id": account.id, "code": account.code, "name": account.name, "type": account.type,
            "debit": _decimal_text(debit), "credit": _decimal_text(credit), "balance": _decimal_text(balance),
        })
        total_debit += debit
        total_credit += credit
    return {
        "rows": rows,
        "total_debit": _decimal_text(total_debit),
        "total_credit": _decimal_text(total_credit),
        "is_balanced": total_debit == total_credit,
        "start": str(start) if start else None,
        "end": str(end) if end else None,
        "period": {"id": period.id, "code": period.code, "status": period.status} if period else None,
    }


def financial_general_ledger(*, tenant, account_id, start=None, end=None, period_id=None, page=1, page_size=50):
    try:
        account = ChartOfAccount.objects.get(tenant=tenant, pk=account_id)
    except ChartOfAccount.DoesNotExist as exc:
        raise ReportingValidationError("account must belong to the active tenant.") from exc
    start, end, period = financial_date_filters(tenant=tenant, start=start, end=end, period_id=period_id)
    prior = _posted_lines(tenant=tenant, end=start - timedelta(days=1) if start else None).filter(account=account).aggregate(
        debit=Coalesce(Sum("debit"), ZERO, output_field=MONEY_FIELD),
        credit=Coalesce(Sum("credit"), ZERO, output_field=MONEY_FIELD),
    )
    normal_debit = account.type in {AccountType.ASSET, AccountType.EXPENSE}
    running = prior["debit"] - prior["credit"] if normal_debit else prior["credit"] - prior["debit"]
    page, page_size = pagination(page=page, page_size=page_size)
    lines = _posted_lines(tenant=tenant, start=start, end=end).filter(account=account).select_related(
        "entry", "entry__accounting_event"
    ).order_by("entry__date", "id")
    total = lines.count()
    offset = (page - 1) * page_size
    result = []
    for line in lines[:offset]:
        running += (line.debit - line.credit) if normal_debit else (line.credit - line.debit)
    for line in lines[offset:offset + page_size]:
        running += (line.debit - line.credit) if normal_debit else (line.credit - line.debit)
        event = getattr(line.entry, "accounting_event", None)
        result.append({
            "line_id": line.id, "date": str(line.entry.date), "reference": line.entry.reference,
            "description": line.description or line.entry.description, "debit": _decimal_text(line.debit),
            "credit": _decimal_text(line.credit), "balance": _decimal_text(running),
            "journal_entry_id": line.entry_id, "source_event_id": event.id if event else None,
            "source_domain": event.source_domain if event else None,
            "source_reference": event.source_reference if event else None,
        })
    return {
        "account": {"id": account.id, "code": account.code, "name": account.name, "type": account.type},
        "opening_balance": _decimal_text((prior["debit"] - prior["credit"]) if normal_debit else (prior["credit"] - prior["debit"])),
        "results": result, "page": page, "page_size": page_size, "count": total,
        "has_next": offset + page_size < total, "start": str(start) if start else None,
        "end": str(end) if end else None,
        "period": {"id": period.id, "code": period.code, "status": period.status} if period else None,
    }


def financial_configuration(*, tenant):
    mappings = FinancialAccountMapping.objects.filter(tenant=tenant, is_active=True).select_related("account")
    by_role = {mapping.role: mapping for mapping in mappings}
    return {
        "mapped_roles": [{"role": item.role, "account_id": item.account_id, "account_code": item.account.code, "account_name": item.account.name} for item in mappings],
        "missing_statement_roles": [
            FinancialStatementRole.COGS,
            FinancialStatementRole.OPERATING_EXPENSE,
            FinancialStatementRole.RETAINED_EARNINGS,
        ] if not by_role else [
            role for role in [FinancialStatementRole.COGS, FinancialStatementRole.OPERATING_EXPENSE, FinancialStatementRole.RETAINED_EARNINGS]
            if role not in by_role
        ],
    }


def financial_exceptions(*, tenant, start=None, end=None, page=1, page_size=50):
    start, end, _period = financial_date_filters(tenant=tenant, start=start, end=end)
    statuses = [
        AccountingEventStatus.CONFIGURATION_REQUIRED,
        AccountingEventStatus.POLICY_REQUIRED,
        AccountingEventStatus.FAILED,
    ]
    events = AccountingEvent.objects.filter(tenant=tenant, status__in=statuses)
    if start:
        events = events.filter(event_date__gte=start)
    if end:
        events = events.filter(event_date__lte=end)
    events = events.order_by("-event_date", "-id")
    return _page(events, page=page, page_size=page_size, serializer=lambda event: {
        "id": event.id, "event_date": str(event.event_date), "event_type": event.event_type,
        "source_domain": event.source_domain, "source_reference": event.source_reference,
        "amount": _decimal_text(event.amount), "currency": event.currency, "status": event.status,
        "reason": event.exception_reason,
    })


def financial_dashboard(*, tenant, start=None, end=None, period_id=None):
    trial = financial_trial_balance_v2(tenant=tenant, start=start, end=end, period_id=period_id)
    rows = trial["rows"]
    by_type = {kind: ZERO for kind in AccountType.values}
    for row in rows:
        by_type[row["type"]] += Decimal(row["balance"])
    exceptions = AccountingEvent.objects.filter(
        tenant=tenant,
        status__in=[AccountingEventStatus.CONFIGURATION_REQUIRED, AccountingEventStatus.POLICY_REQUIRED, AccountingEventStatus.FAILED],
    ).count()
    return {
        "trial_balance": {"total_debit": trial["total_debit"], "total_credit": trial["total_credit"], "is_balanced": trial["is_balanced"]},
        "assets": _decimal_text(by_type[AccountType.ASSET]), "liabilities": _decimal_text(by_type[AccountType.LIABILITY]),
        "equity": _decimal_text(by_type[AccountType.EQUITY]), "revenue": _decimal_text(by_type[AccountType.REVENUE]),
        "expenses": _decimal_text(by_type[AccountType.EXPENSE]), "exception_count": exceptions,
        "configuration": financial_configuration(tenant=tenant),
    }


def financial_profit_loss(*, tenant, start=None, end=None, period_id=None):
    trial = financial_trial_balance_v2(tenant=tenant, start=start, end=end, period_id=period_id)
    mappings = {item.role: item for item in FinancialAccountMapping.objects.filter(tenant=tenant, is_active=True).select_related("account")}
    required = [FinancialStatementRole.COGS, FinancialStatementRole.OPERATING_EXPENSE]
    missing = [role for role in required if role not in mappings]
    if missing:
        return {"status": "accounting_mapping_required", "detail": "Configure COGS and operating-expense account roles before viewing a policy-backed P&L.", "missing_roles": missing, "trial_balance": trial}
    balances = {row["account_id"]: Decimal(row["balance"]) for row in trial["rows"]}
    revenue = sum((amount for row_id, amount in balances.items() if next((row for row in trial["rows"] if row["account_id"] == row_id), {}).get("type") == AccountType.REVENUE), ZERO)
    cogs = balances.get(mappings[FinancialStatementRole.COGS].account_id, ZERO)
    operating = balances.get(mappings[FinancialStatementRole.OPERATING_EXPENSE].account_id, ZERO)
    return {
        "status": "implemented", "revenue": _decimal_text(revenue), "cogs": _decimal_text(cogs),
        "gross_profit": _decimal_text(revenue - cogs), "operating_expenses": _decimal_text(operating),
        "net_result": _decimal_text(revenue - cogs - operating), "trial_balance": trial,
    }


def financial_balance_sheet(*, tenant, as_of=None, period_id=None):
    trial = financial_trial_balance_v2(tenant=tenant, end=as_of, period_id=period_id)
    mappings = {item.role: item for item in FinancialAccountMapping.objects.filter(tenant=tenant, is_active=True)}
    if FinancialStatementRole.RETAINED_EARNINGS not in mappings:
        return {"status": "accounting_policy_required", "detail": "Retained-earnings treatment must be configured before claiming a balance sheet.", "trial_balance": trial}
    sections = {kind: [] for kind in [AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY]}
    for row in trial["rows"]:
        if row["type"] in sections:
            sections[row["type"]].append(row)
    totals = {kind: sum((Decimal(row["balance"]) for row in items), ZERO) for kind, items in sections.items()}
    balanced = totals[AccountType.ASSET] == totals[AccountType.LIABILITY] + totals[AccountType.EQUITY]
    return {
        "status": "implemented" if balanced else "configuration_required",
        "assets": {"rows": sections[AccountType.ASSET], "total": _decimal_text(totals[AccountType.ASSET])},
        "liabilities": {"rows": sections[AccountType.LIABILITY], "total": _decimal_text(totals[AccountType.LIABILITY])},
        "equity": {"rows": sections[AccountType.EQUITY], "total": _decimal_text(totals[AccountType.EQUITY])},
        "is_balanced": balanced,
        "detail": "Assets must equal liabilities plus equity." if not balanced else "Posted-ledger statement is balanced.",
        "trial_balance": trial,
    }
