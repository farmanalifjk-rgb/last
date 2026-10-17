"""Provisioning, usage counting, limit enforcement and Stripe billing."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    Tenant, TenantMembership, SubscriptionPlan, Subscription,
    Invoice, InvoiceItem, TenantUsage,
)


# ───────────────────────── Provisioning ─────────────────────────
@transaction.atomic
def provision_tenant(*, name, slug, owner, plan_slug="starter"):
    plan = SubscriptionPlan.objects.get(slug=plan_slug, is_active=True)
    tenant = Tenant.objects.create(name=name, slug=slug, owner=owner, status=Tenant.STATUS_TRIAL,
                                   trial_ends_at=timezone.now() + timedelta(days=plan.trial_days))
    TenantMembership.objects.create(tenant=tenant, user=owner,
                                    role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
    Subscription.objects.create(
        tenant=tenant, plan=plan, status=Subscription.STATUS_TRIALING,
        current_period_start=timezone.now(),
        current_period_end=timezone.now() + timedelta(days=plan.trial_days),
    )
    return tenant


def get_active_tenant_for_user(user):
    """Return the single active canonical workspace for an authenticated user.

    Tenant selection is owned by ``saas.TenantMembership``.  Callers must never
    infer authority from a browser-supplied tenant identifier; switching is an
    explicit, membership-checked command in ``switch_active_tenant``.
    """
    membership = (
        TenantMembership.objects
        .select_related("tenant")
        .filter(
            user=user,
            is_active_in_tenant=True,
            tenant__is_active=True,
        )
        .order_by("-joined_at", "-id")
        .first()
    )
    return membership.tenant if membership else None


def get_active_membership_for_user(user):
    """Return the authoritative active membership for permission-aware callers."""
    return (
        TenantMembership.objects
        .select_related("tenant")
        .filter(
            user=user,
            is_active_in_tenant=True,
            tenant__is_active=True,
        )
        .order_by("-joined_at", "-id")
        .first()
    )


@transaction.atomic
def switch_active_tenant(user, tenant_id):
    m = TenantMembership.objects.select_for_update().filter(
        user=user, tenant_id=tenant_id, tenant__is_active=True
    ).first()
    if m is None:
        raise TenantMembership.DoesNotExist("User is not a member of the requested active tenant.")
    TenantMembership.objects.filter(user=user).update(is_active_in_tenant=False)
    m.is_active_in_tenant = True
    m.save(update_fields=["is_active_in_tenant"])
    return m.tenant


# ───────────────────────── Usage & limits ─────────────────────────
def _count(model, tenant, **extra):
    qs = model.objects.filter(tenant=tenant) if hasattr(model, "_meta") and "tenant" in {f.name for f in model._meta.get_fields()} else model.objects.none()
    return qs.count()


def capture_usage(tenant):
    """Recompute current usage and store a snapshot for each metric."""
    # These counts rely on the optional tenant FK added by the migration in
    # section 5. Until you backfill, models without a tenant FK return 0.
    from pos.models import Product
    from system.models import Store
    from enterprise.models import Warehouse

    values = {
        TenantUsage.METRIC_PRODUCTS: Product.objects.filter(tenant=tenant).count(),
        TenantUsage.METRIC_STORES: Store.objects.filter(tenant=tenant).count(),
        TenantUsage.METRIC_WAREHOUSES: Warehouse.objects.filter(tenant=tenant).count(),
        TenantUsage.METRIC_USERS: TenantMembership.objects.filter(tenant=tenant).count(),
        TenantUsage.METRIC_STORAGE_MB: 0,
    }
    now = timezone.now()
    for metric, value in values.items():
        TenantUsage.objects.update_or_create(
            tenant=tenant, metric=metric, captured_at__date=now.date(),
            defaults={"value": value},
        )
    return values


def plan_limits(plan):
    return {
        TenantUsage.METRIC_USERS: plan.max_users,
        TenantUsage.METRIC_STORES: plan.max_stores,
        TenantUsage.METRIC_WAREHOUSES: plan.max_warehouses,
        TenantUsage.METRIC_PRODUCTS: plan.max_products,
        TenantUsage.METRIC_STORAGE_MB: plan.storage_mb,
    }


class LimitExceeded(Exception):
    def __init__(self, metric, limit, current):
        self.metric, self.limit, self.current = metric, limit, current
        super().__init__(f"Plan limit exceeded for {metric}: {current}/{limit}")


def enforce_limit(tenant, metric):
    """Raise LimitExceeded if adding one more unit of `metric` would breach plan."""
    sub = getattr(tenant, "subscription", None)
    if not sub:
        return
    limits = plan_limits(sub.plan)
    limit = limits.get(metric)
    if limit is None:
        return  # unlimited
    current = capture_usage(tenant).get(metric, 0)
    if current + 1 > limit:
        raise LimitExceeded(metric, limit, current)


# ───────────────────────── Stripe billing ─────────────────────────
def _stripe():
    import stripe 
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def create_checkout_session(tenant, plan, success_url, cancel_url):
    """Create a Stripe Checkout session to subscribe the tenant to `plan`."""
    if not plan.stripe_price_id:
        raise ValueError("Plan is not linked to a Stripe price.")
    stripe = _stripe()
    sub = tenant.subscription
    if not sub.stripe_customer_id:
        customer = stripe.Customer.create(email=tenant.owner.email, name=tenant.name)
        sub.stripe_customer_id = customer.id
        sub.save(update_fields=["stripe_customer_id"])
    session = stripe.checkout.Session.create(
        customer=sub.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"tenant_id": tenant.id, "plan_slug": plan.slug},
    )
    return session.url


def sync_subscription_from_stripe(sub):
    """Pull current status/period from Stripe into the local Subscription."""
    if not sub.stripe_subscription_id:
        return
    stripe = _stripe()
    s = stripe.Subscription.retrieve(sub.stripe_subscription_id)
    sub.status = s.get("status", sub.status)
    sub.current_period_start = timezone.datetime.fromtimestamp(s.current_period_start, tz=timezone.utc)
    sub.current_period_end = timezone.datetime.fromtimestamp(s.current_period_end, tz=timezone.utc)
    sub.cancel_at_period_end = s.cancel_at_period_end
    sub.save()


def handle_stripe_webhook(event):
    """Minimal webhook handler — extend with more event types as needed."""
    ttype = event.get("type")
    data = event.get("data", {}).get("object", {})
    if ttype == "checkout.session.completed":
        sub_id = data.get("subscription")
        cust = data.get("customer")
        tenant_id = data.get("metadata", {}).get("tenant_id")
        if tenant_id:
            sub = Tenant.objects.get(pk=tenant_id).subscription
            sub.stripe_subscription_id = sub_id or sub.stripe_subscription_id
            sub.stripe_customer_id = cust or sub.stripe_customer_id
            sub.status = Subscription.STATUS_ACTIVE
            sub.save()
    elif ttype == "invoice.payment_succeeded":
        _record_invoice(data)
    return {"received": True, "type": ttype}


def _record_invoice(inv_data):
    tenant_id = inv_data.get("metadata", {}).get("tenant_id")
    if not tenant_id:
        return
    tenant = Tenant.objects.get(pk=tenant_id)
    inv, _ = Invoice.objects.update_or_create(
        stripe_invoice_id=inv_data.get("id"),
        defaults={
            "tenant": tenant,
            "number": inv_data.get("number") or inv_data.get("id"),
            "status": Invoice.STATUS_PAID,
            "amount_due": Decimal(inv_data.get("amount_due", 0)) / Decimal(100),
            "amount_paid": Decimal(inv_data.get("amount_paid", 0)) / Decimal(100),
            "currency": (inv_data.get("currency") or "usd").upper(),
            "paid_at": timezone.now(),
            "pdf_url": inv_data.get("invoice_pdf") or "",
        },
    )
    return inv
