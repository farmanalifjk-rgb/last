"""Canonical orchestration for optional external payment providers.

An adapter speaks to its own provider. This module owns tenant-bound provider operation state,
server-side verification, and the narrow bridge to Ledgerline's existing POS
settlement and refund services. It never trusts a browser payment outcome.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from audit.models import AuditEvent
from audit.recorder import record
from inventory.models import StockReservation
from inventory.services import (
    apply_adjustment,
    release_reservation,
    reserve_stock,
)
from pos.models import Order, OrderItem, Refund
from pos.services.canonical_pos import (
    _quote,
    _tenant_customer,
    active_session_for_user,
)
from tax.engine import compute_order_tax

from .models import (
    PaymentSettlement,
    ProviderPaymentOperation,
    ProviderRefundOperation,
    ProviderWebhookEvent,
    RefundSettlement,
)
from .providers import get_provider
from .providers.base import (
    ProviderConfigurationError,
    ProviderError,
    ProviderRequestError,
    ProviderVerificationError,
    from_minor_units,
    to_minor_units,
)
from .services import _money, _tenant_currency, record_refund_settlement, settle_order


PAYMENT_STATUS_MAP = {
    "requires_payment_method": ProviderPaymentOperation.STATUS_PENDING,
    "requires_confirmation": ProviderPaymentOperation.STATUS_PENDING,
    "requires_action": ProviderPaymentOperation.STATUS_REQUIRES_ACTION,
    "processing": ProviderPaymentOperation.STATUS_PROCESSING,
    "succeeded": ProviderPaymentOperation.STATUS_SUCCEEDED,
    "canceled": ProviderPaymentOperation.STATUS_CANCELLED,
    "cancelled": ProviderPaymentOperation.STATUS_CANCELLED,
}
REFUND_STATUS_MAP = {
    "pending": ProviderRefundOperation.STATUS_PENDING,
    "succeeded": ProviderRefundOperation.STATUS_SUCCEEDED,
    "failed": ProviderRefundOperation.STATUS_FAILED,
    "canceled": ProviderRefundOperation.STATUS_CANCELLED,
    "cancelled": ProviderRefundOperation.STATUS_CANCELLED,
}


def _audit(*, tenant, actor, action, instance, summary, after):
    record(
        tenant=tenant,
        actor=actor,
        action=action,
        instance=instance,
        summary=summary,
        icon="credit-card",
        after=after,
    )


def _operation_status(provider_status):
    return PAYMENT_STATUS_MAP.get(provider_status, ProviderPaymentOperation.STATUS_VERIFICATION_REQUIRED)


def _refund_status(provider_status):
    return REFUND_STATUS_MAP.get(provider_status, ProviderRefundOperation.STATUS_VERIFICATION_REQUIRED)


def _metadata_for(operation):
    return {
        "ledgerline_tenant_id": str(operation.tenant_id),
        "ledgerline_order_id": str(operation.order_id),
        "ledgerline_operation_id": str(operation.id),
    }


def _resolve_provider(*, provider=None, provider_code=""):
    resolved = provider or get_provider(provider_code)
    if not getattr(resolved, "code", ""):
        raise ProviderConfigurationError("A registered payment provider must be explicitly selected.")
    return resolved


def _assert_payment_snapshot(operation, snapshot):
    if not snapshot.provider_payment_id:
        raise ProviderVerificationError("Provider payment reference is missing.")
    if from_minor_units(snapshot.amount_minor) != _money(operation.amount, allow_zero=True):
        raise ProviderVerificationError("Provider payment amount does not match the canonical order total.")
    if snapshot.currency.upper() != operation.currency.upper():
        raise ProviderVerificationError("Provider payment currency does not match the canonical order currency.")
    metadata = snapshot.metadata or {}
    expected = _metadata_for(operation)
    if any(str(metadata.get(key, "")) != value for key, value in expected.items()):
        raise ProviderVerificationError("Provider payment is not mapped to this tenant-owned operation.")


def _assert_refund_snapshot(refund_operation, snapshot):
    if not snapshot.provider_refund_id:
        raise ProviderVerificationError("Provider refund reference is missing.")
    if from_minor_units(snapshot.amount_minor) != _money(refund_operation.amount, allow_zero=True):
        raise ProviderVerificationError("Provider refund amount does not match the canonical refund total.")
    if snapshot.currency.upper() != refund_operation.currency.upper():
        raise ProviderVerificationError("Provider refund currency does not match the canonical refund currency.")


@transaction.atomic
def prepare_provider_order(*, tenant, user, items, customer_id=None, discount=Decimal("0"), idempotency_key=""):
    """Create a tenant-owned, unreserved draft order for provider processing.

    Cash checkout retains its existing eager inventory adjustment. Provider orders
    reserve no stock and acquire no financial effect until remote success has been
    server-verified and the canonical settlement bridge runs.
    """
    key = (idempotency_key or "").strip()
    if not key:
        raise ValueError("An Idempotency-Key is required to start provider payment safely.")
    existing = Order.objects.select_for_update().filter(tenant=tenant, idempotency_key=key).first()
    if existing:
        if existing.payment_method != "card":
            raise ValueError("This idempotency key belongs to another checkout method.")
        return existing, True
    customer = _tenant_customer(tenant, customer_id)
    session = active_session_for_user(tenant=tenant, user=user, lock=True)
    if session is None:
        raise LookupError("Open a cash session before starting provider payment.")
    lines, subtotal, applied_discount, _preview_tax, _preview_total = _quote(
        tenant=tenant, customer=customer, items=items, discount=discount
    )
    try:
        order = Order.objects.create(
            tenant=tenant,
            warehouse=session.warehouse,
            customer=customer,
            session=session,
            payment_method="card",
            subtotal=subtotal,
            discount=applied_discount,
            tax=Decimal("0"),
            total=Decimal("0"),
            status="draft",
            idempotency_key=key,
        )
    except IntegrityError:
        return Order.objects.get(tenant=tenant, idempotency_key=key), True
    for line in lines:
        OrderItem.objects.create(
            tenant=tenant,
            order=order,
            product=line["product"],
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            subtotal=line["subtotal"],
            cost_price=line["product"].cost_price,
        )
    compute_order_tax(order, customer)
    order.refresh_from_db()
    return order, False


@transaction.atomic
def _reserve_provider_order_stock(*, order, user=None):
    from inventory.models import StockReservation

    order = (
        Order.objects
        .select_for_update()
        .get(
            tenant=order.tenant,
            pk=order.pk,
        )
    )

    lines = (
        OrderItem.objects
        .select_for_update()
        .select_related("product")
        .filter(
            tenant=order.tenant,
            order=order,
        )
        .order_by("id")
    )

    reservations = []

    for line in lines:
        existing = (
            StockReservation.objects
            .select_for_update()
            .filter(
                tenant=order.tenant,
                order=order,
                product_id=line.product_id,
                status=StockReservation.STATUS_ACTIVE,
            )
            .first()
        )

        if existing is not None:
            if existing.quantity != line.quantity:
                raise ValueError(
                    f"Stock reservation quantity mismatch for provider order "
                    f"{order.order_number}, product {line.product_id}."
                )

            reservations.append(existing)
            continue

        reservation = reserve_stock(
            tenant=order.tenant,
            product_id=line.product_id,
            warehouse_id=order.warehouse_id,
            quantity=line.quantity,
            order=order,
            reference=order.order_number,
            reserved_by=user,
        )

        reservations.append(reservation)

    return reservations


def _release_provider_order_stock(*, order, user=None):
    from inventory.models import StockReservation

    reservations = (
        StockReservation.objects
        .filter(
            tenant=order.tenant,
            order=order,
            status=StockReservation.STATUS_ACTIVE,
        )
        .values_list("id", flat=True)
    )

    for reservation_id in reservations:
        release_reservation(
            tenant=order.tenant,
            reservation_id=reservation_id,
            user=user,
        )


def _fulfill_provider_order_reservations(*, order, user=None):
    from inventory.models import StockReservation

    reservations = list(
        StockReservation.objects
        .select_for_update()
        .filter(
            tenant=operation.tenant,
            order=order,
            status=StockReservation.STATUS_ACTIVE,
        )
        .order_by("id")
    )

    for reservation in reservations:
        reservation.status = StockReservation.STATUS_FULFILLED
        reservation.save(update_fields=["status"])

    return reservations


@transaction.atomic
def finalize_verified_provider_order(*, operation, user=None):
    """Apply reserved stock and settle exactly once after verified provider success."""
    from inventory.models import StockReservation

    operation = (
        ProviderPaymentOperation.objects
        .select_for_update()
        .select_related("order")
        .get(pk=operation.pk)
    )

    order = (
        Order.objects
        .select_for_update()
        .get(
            tenant=operation.tenant,
            pk=operation.order_id,
        )
    )

    if PaymentSettlement.objects.filter(
        tenant=operation.tenant,
        order=order,
    ).exists():
        return order

    if order.status != "draft":
        raise ValueError("Only a draft provider order can be finalized.")

    lines = list(
        OrderItem.objects
        .select_for_update()
        .select_related("product")
        .filter(
            tenant=operation.tenant,
            order=order,
        )
    )

    reservations = list(
        StockReservation.objects
        .select_for_update()
        .filter(
            tenant=operation.tenant,
            order=order,
            status=StockReservation.STATUS_ACTIVE,
        )
        .order_by("id")
    )
    
    now = timezone.now()
    
    for reservation in reservations:
        if reservation.expires_at is not None and reservation.expires_at < now:
            raise ValueError(
                f"Stock reservation {reservation.id} for provider order "
                f"{order.order_number} has expired."
            )
    reservation_by_product = {
        reservation.product_id: reservation
        for reservation in reservations
    }

    for line in lines:
        reservation = reservation_by_product.get(line.product_id)

        if reservation is None:
            raise ValueError(
                f"Missing stock reservation for provider order "
                f"{order.order_number}, product {line.product_id}."
            )

        if reservation.quantity != line.quantity:
            raise ValueError(
                f"Stock reservation quantity mismatch for provider order "
                f"{order.order_number}, product {line.product_id}."
            )

        apply_adjustment(
            tenant=operation.tenant,
            product_id=line.product_id,
            warehouse_id=order.warehouse_id,
            quantity=-line.quantity,
            reason="POS provider sale",
            note=f"Provider sale {order.order_number}",
            user=user,
            movement_type="sale",
            reference=order.order_number,
            reservation_id=reservation.id,
        )

        reservation.status = StockReservation.STATUS_FULFILLED
        reservation.save(update_fields=["status"])

    return settle_order(
        order=order,
        tenders=[{
            "tender_type": "card",
            "amount": str(operation.amount),
            "reference": operation.provider_payment_id,
        }],
        user=user,
    )


@transaction.atomic
def _mark_payment_snapshot(*, operation, snapshot, user=None, settle_on_success=True):
    operation = ProviderPaymentOperation.objects.select_for_update().get(pk=operation.pk)
    _assert_payment_snapshot(operation, snapshot)
    operation.provider_payment_id = snapshot.provider_payment_id
    operation.provider_status = snapshot.status[:64]
    operation.status = _operation_status(snapshot.status)
    operation.failure_code = snapshot.failure_code[:80]
    operation.failure_reason = snapshot.failure_reason[:255]
    operation.verified_at = timezone.now()
    operation.save(update_fields=[
        "provider_payment_id", "provider_status", "status", "failure_code",
        "failure_reason", "verified_at", "updated_at",
    ])
    if operation.status == ProviderPaymentOperation.STATUS_SUCCEEDED and settle_on_success:
        finalize_verified_provider_order(operation=operation, user=user)
        _audit(
            tenant=operation.tenant,
            actor=user,
            action="payments.provider.succeeded",
            instance=operation,
            summary="Verified provider payment and finalized canonical settlement.",
            after={"provider": operation.provider, "provider_payment_id": operation.provider_payment_id[-12:], "order_id": operation.order_id, "amount": str(operation.amount), "currency": operation.currency},
        )
    elif operation.status in {ProviderPaymentOperation.STATUS_FAILED,ProviderPaymentOperation.STATUS_CANCELLED,}:
        order = (
            Order.objects
            .select_for_update()
            .get(
                tenant=operation.tenant,
                pk=operation.order_id,
            )
        )
    
        _release_provider_order_stock(
            order=order,
            user=user,
        )
    
        if (
            operation.status == ProviderPaymentOperation.STATUS_CANCELLED
            and order.status == "draft"
        ):
            order.status = "cancelled"
            order.save(update_fields=["status"])
    
        _audit(
            tenant=operation.tenant,
            actor=user,
            action="payments.provider.failed",
            instance=operation,
            summary="Provider payment did not complete; active stock reservations were released.",
            after={
                "provider": operation.provider,
                "provider_payment_id": operation.provider_payment_id[-12:],
                "status": operation.status,
                "order_id": operation.order_id,
            },
        )
    return operation


def start_provider_payment(
    *,
    tenant,
    user,
    items,
    customer_id=None,
    discount=Decimal("0"),
    idempotency_key="",
    provider=None,
    provider_code="",
):
    provider = _resolve_provider(
        provider=provider,
        provider_code=provider_code,
    )
    provider.ensure_configured()

    with transaction.atomic():
        order, _replayed = prepare_provider_order(
            tenant=tenant,
            user=user,
            items=items,
            customer_id=customer_id,
            discount=discount,
            idempotency_key=idempotency_key,
        )

        operation, created = (
            ProviderPaymentOperation.objects
            .select_for_update()
            .get_or_create(
                order=order,
                defaults={
                    "tenant": tenant,
                    "provider": provider.code,
                    "amount": _money(
                        order.total,
                        field="order total",
                        allow_zero=True,
                    ),
                    "currency": _tenant_currency(tenant),
                    "idempotency_key": f"{provider.code}:{order.id}",
                    "initiated_by": user,
                },
            )
        )

        if operation.tenant_id != tenant.id:
            raise ProviderVerificationError(
                "Provider operation does not belong to the active tenant."
            )

        # Stock is reserved only for a brand-new provider operation.
        #
        # An existing operation represents a replay/reconciliation path.
        # Reserving here again could create a second active reservation after
        # the original reservation has already been fulfilled.
        if created:
            _reserve_provider_order_stock(
                order=order,
                user=user,
            )

    if not created:
        if not operation.provider_payment_id:
            raise ProviderVerificationError(
                "Existing provider payment status is being verified; "
                "do not create a duplicate operation."
            )

        snapshot = provider.retrieve_payment_intent(
            operation.provider_payment_id
        )

        operation = _mark_payment_snapshot(
            operation=operation,
            snapshot=snapshot,
            user=user,
        )

        return operation, snapshot.client_secret, True

    try:
        snapshot = provider.create_payment_intent(
            amount_minor=to_minor_units(operation.amount),
            currency=operation.currency,
            metadata=_metadata_for(operation),
            idempotency_key=operation.idempotency_key,
        )

        operation = _mark_payment_snapshot(
            operation=operation,
            snapshot=snapshot,
            user=user,
        )

        _audit(
            tenant=tenant,
            actor=user,
            action="payments.provider.initiated",
            instance=operation,
            summary="Created a tenant-scoped provider payment operation.",
            after={
                "provider": operation.provider,
                "order_id": order.id,
                "amount": str(operation.amount),
                "currency": operation.currency,
            },
        )

        return operation, snapshot.client_secret, False

    except ProviderError:
        operation.status = (
            ProviderPaymentOperation.STATUS_VERIFICATION_REQUIRED
        )
        operation.failure_reason = (
            "Provider operation creation outcome requires verification."
        )
        operation.save(
            update_fields=[
                "status",
                "failure_reason",
                "updated_at",
            ]
        )
        raise


def verify_provider_payment(*, tenant, operation_id, user=None, provider=None):
    operation = ProviderPaymentOperation.objects.get(tenant=tenant, pk=operation_id)
    if not operation.provider_payment_id:
        raise ProviderVerificationError("Provider payment reference is unavailable for verification.")
    provider = _resolve_provider(provider=provider, provider_code=operation.provider)
    if provider.code != operation.provider:
        raise ProviderVerificationError("Provider adapter does not match the tenant-owned operation.")
    snapshot = provider.retrieve_payment_intent(operation.provider_payment_id)
    try:
        operation = _mark_payment_snapshot(operation=operation, snapshot=snapshot, user=user)
    except ProviderVerificationError as exc:
        operation.status = ProviderPaymentOperation.STATUS_EXCEPTION
        operation.failure_reason = str(exc)[:255]
        operation.save(update_fields=["status", "failure_reason", "updated_at"])
        _audit(tenant=tenant, actor=user, action="payments.provider.exception", instance=operation, summary="Provider payment verification exception.", after={"operation_id": operation.id, "provider": operation.provider})
        raise
    _audit(tenant=tenant, actor=user, action="payments.provider.reconciled", instance=operation, summary="Reconciled local provider operation against verified provider state.", after={"operation_id": operation.id, "status": operation.status, "provider_status": operation.provider_status})
    return operation


def cancel_provider_payment(*, tenant, operation_id, user=None, provider=None):
    operation = ProviderPaymentOperation.objects.get(tenant=tenant, pk=operation_id)
    if operation.status in {ProviderPaymentOperation.STATUS_SUCCEEDED, ProviderPaymentOperation.STATUS_CANCELLED}:
        return operation
    if not operation.provider_payment_id:
        raise ProviderVerificationError("Provider payment reference is unavailable for cancellation.")
    provider = _resolve_provider(provider=provider, provider_code=operation.provider)
    if provider.code != operation.provider:
        raise ProviderVerificationError("Provider adapter does not match the tenant-owned operation.")
    snapshot = provider.cancel_payment_intent(operation.provider_payment_id)
    operation = _mark_payment_snapshot(operation=operation, snapshot=snapshot, user=user, settle_on_success=False)
    return operation


def process_provider_webhook(*, provider_code, raw_body, signature, provider=None):
    provider = _resolve_provider(provider=provider, provider_code=provider_code)
    event = provider.verify_webhook(raw_body=raw_body, signature=signature)
    event_id = str(event.get("id", ""))
    event_type = str(event.get("type", ""))
    object_data = ((event.get("data") or {}).get("object") or {})
    payment_id = str(object_data.get("id", ""))
    if not event_id or not event_type:
        raise ProviderVerificationError("Provider webhook event is malformed.")
    operation = ProviderPaymentOperation.objects.filter(
        provider=provider.code,
        provider_payment_id=payment_id,
    ).first()
    try:
        with transaction.atomic():
            webhook_event, created = ProviderWebhookEvent.objects.get_or_create(
                provider=provider.code,
                provider_event_id=event_id,
                defaults={
                    "event_type": event_type,
                    "tenant": operation.tenant if operation else None,
                    "operation": operation,
                },
            )
    except IntegrityError:
        # A concurrently committed delivery won the provider-event uniqueness
        # race. Treat this request as the same acknowledged replay rather than
        # risking a second settlement or refund effect.
        webhook_event = ProviderWebhookEvent.objects.get(
            provider=provider.code,
            provider_event_id=event_id,
        )
        return webhook_event, True
    if not created:
        return webhook_event, True
    if operation is None:
        webhook_event.processing_state = ProviderWebhookEvent.STATE_IGNORED
        webhook_event.error_reason = "No tenant-owned provider operation matched the event."
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["processing_state", "error_reason", "processed_at"])
        return webhook_event, False
    try:
        # A signed event identifies a provider object, but the current provider
        # object is retrieved before any local financial effect is allowed.
        verify_provider_payment(tenant=operation.tenant, operation_id=operation.id, provider=provider)
        webhook_event.processing_state = ProviderWebhookEvent.STATE_PROCESSED
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["processing_state", "processed_at"])
        _audit(tenant=operation.tenant, actor=None, action="payments.provider.webhook", instance=webhook_event, summary="Processed verified provider webhook.", after={"event_type": event_type, "operation_id": operation.id})
    except ProviderError as exc:
        webhook_event.processing_state = ProviderWebhookEvent.STATE_FAILED
        webhook_event.error_reason = str(exc)[:255]
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["processing_state", "error_reason", "processed_at"])
        raise
    return webhook_event, False


def start_provider_refund(*, tenant, refund, user=None, provider=None):
    with transaction.atomic():
        refund = Refund.objects.select_for_update().select_related("order").get(tenant=tenant, pk=refund.pk)
        if RefundSettlement.objects.filter(tenant=tenant, refund=refund).exists():
            raise ValueError("This refund already has a recorded local payment settlement.")
        payment_operation = ProviderPaymentOperation.objects.select_for_update().get(
            tenant=tenant,
            order=refund.order,
            status=ProviderPaymentOperation.STATUS_SUCCEEDED,
        )
        provider = _resolve_provider(provider=provider, provider_code=payment_operation.provider)
        if provider.code != payment_operation.provider:
            raise ProviderVerificationError("Provider adapter does not match the tenant-owned operation.")
        provider.ensure_configured()
        existing = ProviderRefundOperation.objects.select_for_update().filter(tenant=tenant, refund=refund).first()
        if existing:
            if not existing.provider_refund_id:
                raise ProviderVerificationError("Existing provider refund status is being verified; do not create a duplicate refund.")
            existing_id = existing.id
        else:
            previous = ProviderRefundOperation.objects.filter(
                tenant=tenant,
                payment_operation=payment_operation,
                status__in=[ProviderRefundOperation.STATUS_PENDING, ProviderRefundOperation.STATUS_SUCCEEDED, ProviderRefundOperation.STATUS_VERIFICATION_REQUIRED],
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            amount = _money(refund.total_amount, allow_zero=True)
            if Decimal(previous) + amount > Decimal(payment_operation.amount):
                raise ValueError("Provider refund exceeds the verified original payment amount.")
            refund_operation = ProviderRefundOperation.objects.create(
                tenant=tenant,
                refund=refund,
                payment_operation=payment_operation,
                provider=payment_operation.provider,
                amount=amount,
                currency=payment_operation.currency,
                idempotency_key=f"{provider.code}-refund:{refund.id}",
                initiated_by=user,
            )
            existing_id = None
    if existing_id is not None:
        return verify_provider_refund(tenant=tenant, refund_operation_id=existing_id, user=user, provider=provider)
    try:
        snapshot = provider.create_refund(
            provider_payment_id=payment_operation.provider_payment_id,
            amount_minor=to_minor_units(amount),
            idempotency_key=refund_operation.idempotency_key,
        )
        return _mark_refund_snapshot(refund_operation=refund_operation, snapshot=snapshot, user=user)
    except ProviderError:
        refund_operation.status = ProviderRefundOperation.STATUS_VERIFICATION_REQUIRED
        refund_operation.failure_reason = "Provider refund creation outcome requires verification."
        refund_operation.save(update_fields=["status", "failure_reason", "updated_at"])
        raise


@transaction.atomic
def _mark_refund_snapshot(*, refund_operation, snapshot, user=None):
    # Keep the lock order consistent with start_provider_refund() and the
    # canonical refund-settlement service: refund first, then its provider
    # operation. This prevents a completion/retry deadlock on PostgreSQL.
    refund_operation = ProviderRefundOperation.objects.select_related("refund").get(pk=refund_operation.pk)
    Refund.objects.select_for_update().get(
        tenant=refund_operation.tenant,
        pk=refund_operation.refund_id,
    )
    refund_operation = ProviderRefundOperation.objects.select_for_update().get(pk=refund_operation.pk)
    _assert_refund_snapshot(refund_operation, snapshot)
    refund_operation.provider_refund_id = snapshot.provider_refund_id
    refund_operation.provider_status = snapshot.status[:64]
    refund_operation.status = _refund_status(snapshot.status)
    refund_operation.failure_code = snapshot.failure_code[:80]
    refund_operation.failure_reason = snapshot.failure_reason[:255]
    refund_operation.verified_at = timezone.now()
    refund_operation.save(update_fields=[
        "provider_refund_id", "provider_status", "status", "failure_code",
        "failure_reason", "verified_at", "updated_at",
    ])
    if refund_operation.status == ProviderRefundOperation.STATUS_SUCCEEDED:
        settlement = record_refund_settlement(
            refund=refund_operation.refund,
            user=user,
            method=RefundSettlement.METHOD_PROVIDER,
        )
        _audit(tenant=refund_operation.tenant, actor=user, action="payments.provider.refund", instance=refund_operation, summary="Verified provider refund and recorded canonical refund settlement.", after={"refund_id": refund_operation.refund_id, "provider_refund_id": refund_operation.provider_refund_id[-12:], "settlement_id": settlement.id})
    return refund_operation


def verify_provider_refund(*, tenant, refund_operation_id, user=None, provider=None):
    refund_operation = ProviderRefundOperation.objects.get(tenant=tenant, pk=refund_operation_id)
    if not refund_operation.provider_refund_id:
        raise ProviderVerificationError("Provider refund reference is unavailable for verification.")
    provider = _resolve_provider(provider=provider, provider_code=refund_operation.provider)
    if provider.code != refund_operation.provider:
        raise ProviderVerificationError("Provider adapter does not match the tenant-owned refund operation.")
    snapshot = provider.retrieve_refund(refund_operation.provider_refund_id)
    return _mark_refund_snapshot(refund_operation=refund_operation, snapshot=snapshot, user=user)
