"""Canonical manual/offline SaaS subscription billing orchestration.

This module deliberately does not call POS payments, external providers, or
accounting posting services. It updates the existing SaaS subscription and
invoice records only after a platform-authorized manual verification.
"""
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from audit.recorder import record, snapshot
from operations.models import InAppNotification
from operations.services import create_notification
from rbac.checker import has_permission

from .models import (
    Invoice,
    ManualPaymentMethod,
    ManualSubscriptionPayment,
    Subscription,
    SubscriptionPlan,
    SubscriptionRequest,
    Tenant,
)


class BillingStateConflict(ValidationError):
    status_code = 409

    def __init__(self, detail):
        super().__init__({"detail": detail})


def _as_decimal(value, field_name):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field_name: "Enter a valid monetary amount."})
    if amount <= Decimal("0.00"):
        raise ValidationError({field_name: "Amount must be greater than zero."})
    return amount.quantize(Decimal("0.01"))


def _normalized_currency(value):
    currency = str(value or "").strip().upper()
    if not currency or len(currency) > 10:
        raise ValidationError({"paid_currency": "Enter a valid currency code."})
    return currency


def _period_end(start, interval):
    if interval == SubscriptionPlan.INTERVAL_YEARLY:
        try:
            return start.replace(year=start.year + 1)
        except ValueError:
            return start.replace(year=start.year + 1, day=28)
    month = start.month + 1
    year = start.year + (1 if month == 13 else 0)
    month = 1 if month == 13 else month
    return start.replace(year=year, month=month, day=min(start.day, monthrange(year, month)[1]))


def _safe_payment_snapshot(payment):
    return snapshot(
        payment,
        fields=[
            "status", "paid_amount", "paid_currency", "payment_method",
            "payment_date", "submitted_by", "submitted_at", "verified_by",
            "verified_at", "rejection_reason",
        ],
    )


def _is_platform_verifier(actor):
    if not actor or not actor.is_authenticated:
        return False
    if actor.is_superuser:
        return True
    # Check platform-scope permission first (no tenant).
    if has_permission(actor, "billing", "verify"):
        return True
    # The enforce_tenant_ownership signal may silently bind a platform UserRole
    # to a tenant when the user has a single membership.  Fall back to checking
    # tenant-scoped permissions via every tenant the user belongs to.
    from saas.models import TenantMembership
    for tm in TenantMembership.objects.filter(user=actor, is_active_in_tenant=True).select_related("tenant"):
        if has_permission(actor, "billing", "verify", tenant=tm.tenant):
            return True
    return False


def _require_platform_verifier(actor):
    if not _is_platform_verifier(actor):
        raise PermissionDenied("A platform billing verification permission is required for this action.")


@transaction.atomic
def create_subscription_request(*, tenant, plan_id, actor, request=None):
    plan = SubscriptionPlan.objects.filter(pk=plan_id, is_active=True, is_public=True).first()
    if plan is None:
        raise ValidationError({"plan_id": "The selected plan is unavailable."})
    existing = SubscriptionRequest.objects.select_for_update().filter(
        tenant=tenant,
        status__in=[SubscriptionRequest.STATUS_AWAITING_PAYMENT, SubscriptionRequest.STATUS_PAYMENT_SUBMITTED],
    ).first()
    if existing is not None:
        raise BillingStateConflict("This tenant already has a subscription request awaiting payment or review.")
    subscription = Subscription.objects.select_for_update().select_related("plan").filter(tenant=tenant).first()
    if subscription is None:
        raise ValidationError({"detail": "The tenant has no canonical subscription to amend."})
    now = timezone.now()
    period_start = now
    if subscription.plan_id == plan.id and subscription.current_period_end and subscription.current_period_end > now:
        period_start = subscription.current_period_end
    period_end = _period_end(period_start, plan.interval)
    try:
        billing_request = SubscriptionRequest.objects.create(
            tenant=tenant,
            subscription=subscription,
            plan=plan,
            expected_amount=plan.price,
            expected_currency=plan.currency.upper(),
            period_start=period_start,
            period_end=period_end,
            requested_by=actor,
        )
    except IntegrityError:
        raise BillingStateConflict("This tenant already has a subscription request awaiting payment or review.")
    invoice = Invoice.objects.create(
        tenant=tenant,
        subscription=subscription,
        subscription_request=billing_request,
        number=f"SAAS-{tenant.id}-{billing_request.id:08d}",
        status=Invoice.STATUS_OPEN,
        amount_due=plan.price,
        amount_paid=Decimal("0.00"),
        currency=plan.currency.upper(),
        issued_at=now,
        due_at=None,
        period_start=period_start,
        period_end=period_end,
    )
    record(
        tenant=tenant,
        actor=actor,
        action="create",
        instance=billing_request,
        request=request,
        summary=f"Requested {plan.name} subscription plan",
        icon="file-plus-2",
        after=snapshot(billing_request, fields=["plan", "expected_amount", "expected_currency", "period_start", "period_end", "status"]),
    )
    return billing_request, invoice


@transaction.atomic
def submit_manual_payment(*, tenant, subscription_request_id, actor, payment_method_id, paid_amount, paid_currency, payment_date, payment_reference="", proof_reference="", notes="", request=None):
    billing_request = SubscriptionRequest.objects.select_for_update().select_related("plan", "subscription").filter(
        tenant=tenant, pk=subscription_request_id,
    ).first()
    if billing_request is None:
        raise PermissionDenied("The requested subscription record is not available in the active tenant.")
    if billing_request.requested_by_id != actor.id and not actor.is_superuser:
        raise PermissionDenied("Only the subscription requester may submit its manual payment details.")
    if billing_request.status != SubscriptionRequest.STATUS_AWAITING_PAYMENT:
        raise BillingStateConflict("This subscription request is not awaiting a manual payment.")
    method = ManualPaymentMethod.objects.filter(pk=payment_method_id, is_active=True).first()
    if method is None:
        raise ValidationError({"payment_method_id": "Choose an active configured manual payment method."})
    normalized_reference = str(payment_reference or "").strip()
    if method.reference_required and not normalized_reference:
        raise ValidationError({"payment_reference": "A payment reference is required for the selected method."})
    amount = _as_decimal(paid_amount, "paid_amount")
    currency = _normalized_currency(paid_currency)
    if not payment_date:
        raise ValidationError({"payment_date": "A payment date is required."})
    try:
        payment = ManualSubscriptionPayment.objects.create(
            tenant=tenant,
            subscription_request=billing_request,
            plan=billing_request.plan,
            payment_method=method,
            paid_amount=amount,
            paid_currency=currency,
            payment_reference=normalized_reference,
            payment_date=payment_date,
            proof_reference=str(proof_reference or "").strip(),
            notes=str(notes or "").strip(),
            submitted_by=actor,
        )
    except IntegrityError:
        raise BillingStateConflict("This payment reference has already been submitted for the selected method.")
    billing_request.status = SubscriptionRequest.STATUS_PAYMENT_SUBMITTED
    billing_request.save(update_fields=["status", "updated_at"])
    record(
        tenant=tenant,
        actor=actor,
        action="create",
        instance=payment,
        request=request,
        summary="Submitted manual subscription payment for review",
        icon="receipt-text",
        after=_safe_payment_snapshot(payment),
    )
    create_notification(
        tenant=tenant,
        user=actor,
        event_key=f"billing-payment:{payment.pk}:submitted:{actor.pk}",
        notification_type=InAppNotification.TYPE_WARNING,
        title="Manual payment submitted",
        message="Your subscription payment is awaiting platform verification.",
        link="/billing?tab=payments",
    )
    return payment


@transaction.atomic
def verify_manual_payment(*, payment_id, actor, review_note="", request=None):
    _require_platform_verifier(actor)
    payment = ManualSubscriptionPayment.objects.select_for_update().select_related(
        "subscription_request__plan", "subscription_request__subscription", "tenant", "submitted_by",
    ).filter(pk=payment_id).first()
    if payment is None:
        raise ValidationError({"detail": "Manual payment not found."})
    if payment.submitted_by_id == actor.id:
        raise PermissionDenied("A submitter cannot verify their own manual subscription payment.")
    billing_request = SubscriptionRequest.objects.select_for_update().get(pk=payment.subscription_request_id)
    subscription = Subscription.objects.select_for_update().get(pk=billing_request.subscription_id, tenant=payment.tenant)
    invoice = Invoice.objects.select_for_update().get(subscription_request=billing_request, tenant=payment.tenant)
    if payment.status != ManualSubscriptionPayment.STATUS_SUBMITTED or billing_request.status != SubscriptionRequest.STATUS_PAYMENT_SUBMITTED:
        raise BillingStateConflict("This manual payment has already been decided or its request is no longer reviewable.")
    if payment.paid_amount != billing_request.expected_amount:
        raise ValidationError({"detail": "Submitted amount does not match the authoritative plan amount and cannot be verified."})
    if payment.paid_currency != billing_request.expected_currency:
        raise ValidationError({"detail": "Submitted currency does not match the authoritative plan currency and cannot be verified."})
    if invoice.status != Invoice.STATUS_OPEN or invoice.amount_due != billing_request.expected_amount or invoice.currency != billing_request.expected_currency:
        raise BillingStateConflict("The linked SaaS invoice no longer matches the subscription request.")
    before_payment = _safe_payment_snapshot(payment)
    before_subscription = snapshot(subscription, fields=["plan", "status", "current_period_start", "current_period_end", "cancel_at_period_end"])
    now = timezone.now()
    payment.status = ManualSubscriptionPayment.STATUS_VERIFIED
    payment.verified_by = actor
    payment.verified_at = now
    payment.review_note = str(review_note or "").strip()
    payment.rejection_reason = ""
    payment.save(update_fields=["status", "verified_by", "verified_at", "review_note", "rejection_reason", "updated_at"])
    billing_request.status = SubscriptionRequest.STATUS_ACTIVATED
    billing_request.activated_by = actor
    billing_request.activated_at = now
    billing_request.save(update_fields=["status", "activated_by", "activated_at", "updated_at"])
    subscription.plan = billing_request.plan
    subscription.status = Subscription.STATUS_ACTIVE
    subscription.current_period_start = billing_request.period_start
    subscription.current_period_end = billing_request.period_end
    subscription.cancel_at_period_end = False
    subscription.started_at = subscription.started_at or now
    subscription.ended_at = None
    subscription.save(update_fields=["plan", "status", "current_period_start", "current_period_end", "cancel_at_period_end", "started_at", "ended_at", "updated_at"])
    Tenant.objects.filter(pk=payment.tenant_id).update(status=Tenant.STATUS_ACTIVE, is_active=True, updated_at=now)
    invoice.status = Invoice.STATUS_PAID
    invoice.amount_paid = payment.paid_amount
    invoice.paid_at = now
    invoice.finalized_at = now
    invoice.manual_payment = payment
    invoice.save(update_fields=["status", "amount_paid", "paid_at", "finalized_at", "manual_payment"])
    record(
        tenant=payment.tenant,
        actor=actor,
        action="update",
        instance=payment,
        request=request,
        summary="Verified manual subscription payment",
        icon="badge-check",
        before=before_payment,
        after=_safe_payment_snapshot(payment),
    )
    record(
        tenant=payment.tenant,
        actor=actor,
        action="update",
        instance=subscription,
        request=request,
        summary=f"Activated subscription on {billing_request.plan.name}",
        icon="sparkles",
        before=before_subscription,
        after=snapshot(subscription, fields=["plan", "status", "current_period_start", "current_period_end", "cancel_at_period_end"]),
    )
    create_notification(
        tenant=payment.tenant,
        user=payment.submitted_by,
        event_key=f"billing-payment:{payment.pk}:verified:{payment.submitted_by_id}",
        notification_type=InAppNotification.TYPE_SUCCESS,
        title="Subscription payment verified",
        message="Your subscription is active and the billing record has been finalized.",
        link="/billing?tab=overview",
    )
    return payment


@transaction.atomic
def reject_manual_payment(*, payment_id, actor, rejection_reason, review_note="", request=None):
    _require_platform_verifier(actor)
    reason = str(rejection_reason or "").strip()
    if not reason:
        raise ValidationError({"rejection_reason": "A rejection reason is required."})
    payment = ManualSubscriptionPayment.objects.select_for_update().select_related("subscription_request", "tenant", "submitted_by").filter(pk=payment_id).first()
    if payment is None:
        raise ValidationError({"detail": "Manual payment not found."})
    if payment.submitted_by_id == actor.id:
        raise PermissionDenied("A submitter cannot reject their own manual subscription payment.")
    billing_request = SubscriptionRequest.objects.select_for_update().get(pk=payment.subscription_request_id)
    if payment.status != ManualSubscriptionPayment.STATUS_SUBMITTED or billing_request.status != SubscriptionRequest.STATUS_PAYMENT_SUBMITTED:
        raise BillingStateConflict("This manual payment has already been decided or its request is no longer reviewable.")
    before = _safe_payment_snapshot(payment)
    now = timezone.now()
    payment.status = ManualSubscriptionPayment.STATUS_REJECTED
    payment.verified_by = actor
    payment.verified_at = now
    payment.rejection_reason = reason
    payment.review_note = str(review_note or "").strip()
    payment.save(update_fields=["status", "verified_by", "verified_at", "rejection_reason", "review_note", "updated_at"])
    billing_request.status = SubscriptionRequest.STATUS_REJECTED
    billing_request.save(update_fields=["status", "updated_at"])
    record(
        tenant=payment.tenant,
        actor=actor,
        action="update",
        instance=payment,
        request=request,
        summary="Rejected manual subscription payment",
        icon="circle-x",
        before=before,
        after=_safe_payment_snapshot(payment),
    )
    create_notification(
        tenant=payment.tenant,
        user=payment.submitted_by,
        event_key=f"billing-payment:{payment.pk}:rejected:{payment.submitted_by_id}",
        notification_type=InAppNotification.TYPE_ERROR,
        title="Subscription payment rejected",
        message="Your manual payment could not be verified. Review the rejection reason in billing history.",
        link="/billing?tab=payments",
    )
    return payment
