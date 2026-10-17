from django.db.models import Max
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice, PlanEntitlement, Subscription, SubscriptionPlan, TenantUsage
from .permissions import HasActiveTenant, TenantRBACPermission
from .services import get_active_tenant_for_user


def _money(value):
    return str(value) if value is not None else None


def _plan_data(plan):
    if not plan:
        return None
    entitlements = []
    for item in PlanEntitlement.objects.filter(plan=plan, enabled=True):
        entitlements.append({"code": item.code, "label": item.label, "limit": item.limit_value, "metadata": item.metadata or {}})
    return {
        "id": plan.id,
        "slug": getattr(plan, "slug", ""),
        "name": getattr(plan, "name", ""),
        "description": getattr(plan, "description", ""),
        "interval": getattr(plan, "interval", None),
        "price": _money(getattr(plan, "price", None)),
        "currency": getattr(plan, "currency", "USD"),
        "monthly_price": _money(getattr(plan, "monthly_price", None)),
        "yearly_price": _money(getattr(plan, "yearly_price", None)),
        "max_users": getattr(plan, "max_users", None),
        "max_stores": getattr(plan, "max_stores", None),
        "max_warehouses": getattr(plan, "max_warehouses", None),
        "max_products": getattr(plan, "max_products", None),
        "storage_mb": getattr(plan, "storage_mb", None),
        "trial_days": getattr(plan, "trial_days", None),
        "is_active": getattr(plan, "is_active", True),
        "features": entitlements,
    }


def _subscription_data(subscription):
    if not subscription:
        return None
    return {
        "id": subscription.id,
        "status": subscription.status,
        "plan": _plan_data(getattr(subscription, "plan", None)),
        "current_period_start": getattr(subscription, "current_period_start", None),
        "current_period_end": getattr(subscription, "current_period_end", None),
        "cancel_at_period_end": getattr(subscription, "cancel_at_period_end", False),
        "provider_customer_configured": bool(getattr(subscription, "stripe_customer_id", "")),
        "provider_subscription_configured": bool(getattr(subscription, "stripe_subscription_id", "")),
    }


def _invoice_data(invoice):
    return {
        "id": invoice.id,
        "number": getattr(invoice, "number", ""),
        "status": invoice.status,
        "amount": _money(getattr(invoice, "amount_due", None)),
        "subtotal": _money(getattr(invoice, "subtotal", None)),
        "tax": _money(getattr(invoice, "tax", None)),
        "currency": getattr(invoice, "currency", ""),
        "period_start": getattr(invoice, "period_start", None),
        "period_end": getattr(invoice, "period_end", None),
        "issue_date": getattr(invoice, "issued_at", None),
        "due_date": getattr(invoice, "due_at", None),
        "paid_at": getattr(invoice, "paid_at", None),
        "payment_reference": bool(getattr(invoice, "stripe_invoice_id", "")),
        "download_url": getattr(invoice, "pdf_url", "") or None,
    }


def _usage_data(tenant, plan):
    latest = {}
    for row in TenantUsage.objects.filter(tenant=tenant).order_by("metric", "-captured_at"):
        latest.setdefault(row.metric, row)
    limits = {
        "users": getattr(plan, "max_users", None) if plan else None,
        "stores": getattr(plan, "max_stores", None) if plan else None,
        "warehouses": getattr(plan, "max_warehouses", None) if plan else None,
        "products": getattr(plan, "max_products", None) if plan else None,
        "storage_mb": getattr(plan, "storage_mb", None) if plan else None,
    }
    result = []
    for metric, row in latest.items():
        limit = limits.get(metric)
        used = row.value
        result.append({"metric": metric, "used": used, "limit": limit, "remaining": max(limit - used, 0) if limit is not None else None, "percentage": round((used / limit) * 100, 2) if limit else None, "captured_at": row.captured_at})
    return result


class BillingPermissionView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "billing"
    rbac_action = "view"

    def get_tenant(self, request):
        return get_active_tenant_for_user(request.user)


class BillingOverviewView(BillingPermissionView):
    def get(self, request):
        tenant = self.get_tenant(request)
        subscription = getattr(tenant, "subscription", None)
        plan = getattr(subscription, "plan", None) if subscription else None
        return Response({"tenant": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "status": tenant.status}, "plan": _plan_data(plan), "subscription": _subscription_data(subscription), "usage": _usage_data(tenant, plan), "invoices": [_invoice_data(item) for item in Invoice.objects.filter(tenant=tenant).order_by("-created_at")[:5]], "provider": _provider_status()})


class BillingPlansView(BillingPermissionView):
    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by("id")
        return Response({"results": [_plan_data(item) for item in plans]})


class BillingSubscriptionView(BillingPermissionView):
    def get(self, request):
        tenant = self.get_tenant(request)
        return Response({"subscription": _subscription_data(getattr(tenant, "subscription", None))})


class BillingUsageView(BillingPermissionView):
    def get(self, request):
        tenant = self.get_tenant(request)
        subscription = getattr(tenant, "subscription", None)
        plan = getattr(subscription, "plan", None) if subscription else None
        return Response({"results": _usage_data(tenant, plan)})


class BillingInvoicesView(BillingPermissionView):
    def get(self, request):
        tenant = self.get_tenant(request)
        qs = Invoice.objects.filter(tenant=tenant).order_by("-created_at")
        return Response({"results": [_invoice_data(item) for item in qs]})


def _provider_status():
    return {
        "provider": None,
        "configured": False,
        "actions_enabled": False,
        "status": "manual_offline_billing",
        "message": "SaaS subscriptions use manual/offline payment verification in this release. External subscription checkout is not enabled.",
    }


class BillingProviderStatusView(BillingPermissionView):
    def get(self, request):
        return Response(_provider_status())


