"""FEFO allocation + bundle price + serial validation."""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from .models import Batch, BatchMovement, ProductBundle, SerialNumber


@transaction.atomic
def allocate_batch_fefo(*, product, quantity, kind=BatchMovement.KIND_SALE, order=None, reference="", user=None):
    """Pick batches in First-Expire-First-Out order, decrement remaining qty."""
    remaining = Decimal(quantity)
    allocations = []
    for batch in (
    Batch.objects
        .select_for_update()
        .filter(
            product=product,
            remaining_quantity__gt=0,
            is_recalled=False,
        )
        .order_by("expiry_date", "created_at")):
        if remaining <= 0:
            break
        take = min(batch.remaining_quantity, remaining)
        batch.remaining_quantity -= take
        batch.save(update_fields=["remaining_quantity"])
        BatchMovement.objects.create(tenant=batch.tenant, batch=batch, kind=kind, quantity=take, order=order, reference=reference, created_by=user)
        allocations.append((batch, take))
        remaining -= take
    if remaining > 0:
        raise ValueError("Not enough batch stock to allocate")
    return allocations


def recall_batch(batch, reason=""):
    batch.is_recalled = True
    batch.notes = (batch.notes + "\n" + reason).strip()
    batch.save(update_fields=["is_recalled", "notes"])


def validate_serial(product, serial_number):
    s = SerialNumber.objects.filter(product=product, serial_number=serial_number).first()
    if not s:
        raise ValueError("Serial number not found")
    if s.status != SerialNumber.STATUS_IN_STOCK:
        raise ValueError(f"Serial not in stock (currently {s.status})")
    return s


@transaction.atomic
def mark_serial_sold(serial, order):
    serial = (
        SerialNumber.objects
        .select_for_update()
        .get(pk=serial.pk)
    )

    if serial.status != SerialNumber.STATUS_IN_STOCK:
        raise ValueError(
            f"Serial not in stock (currently {serial.status})"
        )

    serial.status = SerialNumber.STATUS_SOLD
    serial.sold_at = timezone.now()
    serial.sold_in_order = order
    serial.save(update_fields=["status", "sold_at", "sold_in_order"])

    return serial


def bundle_price(bundle_id):
    b = ProductBundle.objects.prefetch_related("components__product").get(pk=bundle_id)
    return b.computed_price()


