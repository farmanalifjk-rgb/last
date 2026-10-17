import secrets
from decimal import Decimal

from django.db import transaction

from .models import CustomerCreditLimit, CustomerPortalToken


def _amount(value):
    amount = Decimal(str(value))
    if amount < 0:
        raise ValueError("Amounts cannot be negative.")
    return amount


@transaction.atomic
def set_credit_limit(*, tenant, customer, amount, terms_days=0):
    if customer.tenant_id != tenant.id:
        raise ValueError("The customer does not belong to the active tenant.")
    limit, _ = CustomerCreditLimit.objects.select_for_update().get_or_create(
        tenant=tenant, customer=customer,
        defaults={"limit": _amount(amount), "terms_days": max(int(terms_days or 0), 0)},
    )
    next_limit = _amount(amount)
    if limit.used > next_limit:
        raise ValueError("Credit limit cannot be set below the currently used credit.")
    limit.limit = next_limit
    limit.terms_days = max(int(terms_days or 0), 0)
    limit.is_active = True
    limit.save(update_fields=["limit", "terms_days", "is_active", "updated_at"])
    return limit


@transaction.atomic
def consume_credit(*, tenant, customer, amount):
    if customer.tenant_id != tenant.id:
        raise ValueError("The customer does not belong to the active tenant.")
    limit = CustomerCreditLimit.objects.select_for_update().filter(tenant=tenant, customer=customer, is_active=True).first()
    if limit is None:
        raise ValueError("No active credit limit is configured.")
    amount = _amount(amount)
    if limit.used + amount > limit.limit:
        raise ValueError("The transaction exceeds available customer credit.")
    limit.used += amount
    limit.save(update_fields=["used", "updated_at"])
    return limit


@transaction.atomic
def release_credit(*, tenant, customer, amount):
    if customer.tenant_id != tenant.id:
        raise ValueError("The customer does not belong to the active tenant.")
    limit = CustomerCreditLimit.objects.select_for_update().get(tenant=tenant, customer=customer)
    limit.used = max(Decimal("0"), limit.used - _amount(amount))
    limit.save(update_fields=["used", "updated_at"])
    return limit


@transaction.atomic
def issue_portal_token(*, tenant, customer):
    if customer.tenant_id != tenant.id:
        raise ValueError("The customer does not belong to the active tenant.")
    token, _ = CustomerPortalToken.objects.update_or_create(
        tenant=tenant, customer=customer,
        defaults={"token": secrets.token_urlsafe(32), "email": customer.email, "is_active": True},
    )
    return token
