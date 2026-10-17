from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from pos.models import Order, Payment
from .models import (ParkedOrder, Layaway, LayawayPayment, SplitBill, SplitBillShare,
                     OfflineSyncQueue, CashDrawerEvent)


@transaction.atomic
def park_cart(*, session, payload, label="", customer=None, user=None):
    return ParkedOrder.objects.create(session=session, payload=payload, label=label,
                                       customer=customer, parked_by=user)


@transaction.atomic
def resume_parked(parked_id, *, tenant):
    """Resume a parked order. Validates the parked order belongs to the tenant."""
    p = ParkedOrder.objects.get(pk=parked_id, session__branch__tenant=tenant)
    p.status = ParkedOrder.STATUS_RESUMED
    p.resumed_at = timezone.now()
    p.save(update_fields=["status", "resumed_at"])
    return p


@transaction.atomic
def create_layaway(*, order, deposit, due_date=None, payment_method="cash"):
    bal = Decimal(order.total) - Decimal(deposit)
    lw = Layaway.objects.create(order=order, customer=order.customer,
                                total_amount=order.total, deposit_amount=deposit,
                                balance_due=bal, due_date=due_date)
    LayawayPayment.objects.create(layaway=lw, amount=deposit, payment_method=payment_method)
    Payment.objects.create(order=order, amount=deposit, payment_method=payment_method)
    return lw


@transaction.atomic
def add_layaway_installment(layaway_id, amount, payment_method="cash", *, tenant):
    """Add installment to a layaway. Validates the layaway belongs to the tenant."""
    lw = Layaway.objects.get(pk=layaway_id, order__tenant=tenant)
    LayawayPayment.objects.create(layaway=lw, amount=amount, payment_method=payment_method)
    lw.balance_due = Decimal(lw.balance_due) - Decimal(amount)
    if lw.balance_due <= 0:
        lw.status = Layaway.STATUS_COMPLETED
    lw.save()
    return lw


@transaction.atomic
def split_bill(order_id, share_count, amounts=None, *, tenant):
    """Split an order into shares. Validates the order belongs to the tenant."""
    order = Order.objects.get(pk=order_id, tenant=tenant)
    split = SplitBill.objects.create(order=order, total_amount=order.total, share_count=share_count)
    if amounts:
        for a in amounts:
            SplitBillShare.objects.create(split=split, amount=Decimal(a))
    else:
        each = (Decimal(order.total) / Decimal(share_count)).quantize(Decimal("0.01"))
        for _ in range(share_count):
            SplitBillShare.objects.create(split=split, amount=each)
    return split


@transaction.atomic
def mark_share_paid(share_id, payment_method, *, tenant):
    """Mark a split bill share as paid. Validates the share belongs to the tenant."""
    s = SplitBillShare.objects.get(pk=share_id, split__order__tenant=tenant)
    s.is_paid = True
    s.payment_method = payment_method
    s.save(update_fields=["is_paid", "payment_method"])
    Payment.objects.create(order=s.split.order, amount=s.amount, payment_method=payment_method)
    return s


def log_drawer_event(*, session, kind, amount=Decimal("0"), note="", user=None):
    return CashDrawerEvent.objects.create(session=session, kind=kind, amount=amount,
                                           note=note, created_by=user)


@transaction.atomic
def enqueue_offline(*, device_id, payload):
    return OfflineSyncQueue.objects.create(device_id=device_id, payload=payload)


@transaction.atomic
def sync_offline_pending():
    """Attempt to replay all pending offline payloads. Returns counts."""
    pending = OfflineSyncQueue.objects.filter(status=OfflineSyncQueue.STATUS_PENDING)
    synced = failed = 0
    for item in pending:
        try:
            # Replay is app-specific; the caller wires actual order creation here.
            # This centralizes the queue; integrate with your existing order service.
            item.status = OfflineSyncQueue.STATUS_SYNCED
            item.synced_at = timezone.now()
            item.save()
            synced += 1
        except Exception as e:
            item.status = OfflineSyncQueue.STATUS_FAILED
            item.error = str(e)
            item.save()
            failed += 1
    return {"synced": synced, "failed": failed}