from datetime import timedelta
from decimal import Decimal

from django.db import models, transaction
from django.db.models import F, Sum
from django.utils import timezone

from enterprise.models import Warehouse, WarehouseStock
from pos.models import OrderItem, Product, StockAdjustment, StockAdjustmentItem, StockMovement

from .models import ABCAnalysis, CycleCount, CycleCountLine, InventoryAgingSnapshot, ReorderRule, StockReservation


def _decimal(value):
    return Decimal(str(value))


def _tenant_product(tenant, product_id):
    return Product.objects.select_for_update().get(tenant=tenant, pk=product_id)


def _tenant_warehouse(tenant, warehouse_id):
    return Warehouse.objects.get(tenant=tenant, pk=warehouse_id, is_active=True)


def _stock_row(tenant, warehouse, product):
    row, _ = WarehouseStock.objects.select_for_update().get_or_create(
        tenant=tenant, warehouse=warehouse, product=product,
        defaults={"quantity": Decimal("0")},
    )
    return row


def available_stock(tenant, product, warehouse=None):
    """Return on-hand minus active, unexpired reservations in the same tenant/location."""
    on_hand = _decimal(product.stock_quantity or 0)
    if warehouse is not None:
        row = WarehouseStock.objects.filter(tenant=tenant, warehouse=warehouse, product=product).first()
        on_hand = _decimal(row.quantity if row else 0)
    reservations = StockReservation.objects.filter(tenant=tenant, product=product, status=StockReservation.STATUS_ACTIVE).filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=timezone.now())
    )
    if warehouse is not None:
        reservations = reservations.filter(warehouse=warehouse)
    reserved = reservations.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    return on_hand - _decimal(reserved)


@transaction.atomic
def apply_adjustment(
    *,
    tenant,
    product_id,
    warehouse_id=None,
    quantity,
    reason,
    note="",
    user=None,
    movement_type="adjustment",
    reference="",
    reservation_id=None,
):
    """Apply one authoritative stock delta under row locks and record immutable movement history.

    Negative adjustments cannot consume stock already committed to active
    reservations unless the exact reservation is explicitly supplied.
    """
    delta = _decimal(quantity)

    if delta == 0:
        raise ValueError("An inventory adjustment quantity cannot be zero.")

    product = _tenant_product(tenant, product_id)
    warehouse = _tenant_warehouse(tenant, warehouse_id) if warehouse_id else None

    previous = _decimal(product.stock_quantity or 0)
    new_total = previous + delta

    from system.models import POSSettings

    pos_settings = POSSettings.load(tenant=tenant)

    if new_total < 0 and not pos_settings.allow_negative_stock:
        raise ValueError(f"Stock cannot become negative for {product.name}.")

    row = None
    previous_warehouse_quantity = None
    new_warehouse_quantity = None

    if warehouse is not None:
        row = _stock_row(tenant, warehouse, product)
        previous_warehouse_quantity = _decimal(row.quantity)
        new_warehouse_quantity = previous_warehouse_quantity + delta

        if (
            new_warehouse_quantity < 0
            and not pos_settings.allow_negative_stock
        ):
            raise ValueError(
                f"Warehouse stock cannot become negative for {product.name}."
            )

    # Negative stock movements must not consume stock committed to
    # active reservations unless the exact reservation is being fulfilled.
    if delta < 0:
        reservations = (
            StockReservation.objects
            .select_for_update()
            .filter(
                tenant=tenant,
                product=product,
                status=StockReservation.STATUS_ACTIVE,
            )
            .filter(
                models.Q(expires_at__isnull=True)
                | models.Q(expires_at__gte=timezone.now())
            )
        )

        if warehouse is not None:
            reservations = reservations.filter(warehouse=warehouse)

        if reservation_id is not None:
            reservation = (
                reservations
                .filter(pk=reservation_id)
                .first()
            )

            if reservation is None:
                raise ValueError(
                    "The specified stock reservation is not active "
                    "or does not belong to this product and warehouse."
                )

            reservations = reservations.exclude(pk=reservation.pk)

        reserved_quantity = (
            reservations.aggregate(total=Sum("quantity"))["total"]
            or Decimal("0")
        )
        reserved_quantity = _decimal(reserved_quantity)

        if warehouse is not None:
            available_after_reservation = (
                new_warehouse_quantity - reserved_quantity
            )
        else:
            available_after_reservation = (
                new_total - reserved_quantity
            )

        if available_after_reservation < 0:
            raise ValueError(
                f"Stock adjustment would consume stock reserved for "
                f"{product.name}."
            )

    if warehouse is not None:
        row.quantity = new_warehouse_quantity
        row.save(update_fields=["quantity", "updated_at"])

    product.stock_quantity = new_total
    product.save(update_fields=["stock_quantity"])

    movement = StockMovement.objects.create(
        tenant=tenant,
        product=product,
        warehouse=warehouse,
        quantity=delta,
        movement_type=movement_type,
        reference=reference,
        previous_stock=previous,
        new_stock=new_total,
        note=note or reason,
    )

    return product, warehouse, movement


@transaction.atomic
def create_adjustment(*, tenant, product_id, warehouse_id=None, new_quantity=None, adjustment_quantity=None, reason, note="", user=None):
    product = _tenant_product(tenant, product_id)
    warehouse = _tenant_warehouse(tenant, warehouse_id) if warehouse_id else None
    current = _decimal(product.stock_quantity or 0)
    if warehouse is not None:
        current = _decimal(_stock_row(tenant, warehouse, product).quantity)
    if new_quantity is None and adjustment_quantity is None:
        raise ValueError("Provide either a new quantity or an adjustment quantity.")
    delta = _decimal(adjustment_quantity) if adjustment_quantity is not None else _decimal(new_quantity) - current
    product, warehouse, movement = apply_adjustment(
        tenant=tenant, product_id=product.id, warehouse_id=warehouse.id if warehouse else None,
        quantity=delta, reason=reason, note=note, user=user, movement_type="adjustment", reference="MANUAL",
    )
    adjustment = StockAdjustment.objects.create(
        tenant=tenant,
        adjustment_type="increase" if delta > 0 else "decrease",
        reason=reason,
        note=note,
        created_by=user,
    )
    StockAdjustmentItem.objects.create(
        tenant=tenant, adjustment=adjustment, product=product,
        adjustment_type=adjustment.adjustment_type, quantity=abs(delta),
        previous_stock=movement.previous_stock, new_stock=movement.new_stock, note=note,
    )
    return adjustment, movement


@transaction.atomic
def reserve_stock(*,tenant,product_id,warehouse_id=None,quantity,order=None,reference="",reserved_by=None,expires_in_hours=24,):
    requested = _decimal(quantity)
    if requested <= 0:
        raise ValueError("Reservation quantity must be positive.")
    product = _tenant_product(tenant, product_id)
    warehouse = _tenant_warehouse(tenant, warehouse_id) if warehouse_id else None
    if warehouse is not None:
        _stock_row(tenant, warehouse, product)
    if available_stock(tenant, product, warehouse) < requested:
        raise ValueError(f"Insufficient available stock for {product.name}.")
    expires_at = timezone.now() + timedelta(hours=expires_in_hours) if expires_in_hours else None
    reservation = StockReservation.objects.create(tenant=tenant,product=product,warehouse=warehouse,order=order,quantity=requested,reference=reference,reserved_by=reserved_by,expires_at=expires_at,)
    StockMovement.objects.create(tenant=tenant, product=product, warehouse=warehouse, quantity=Decimal("0"), movement_type="reservation", reference=reference, previous_stock=product.stock_quantity, new_stock=product.stock_quantity, note=f"Reservation {reservation.id}")
    return reservation


@transaction.atomic
def release_reservation(*, tenant, reservation_id, user=None):
    reservation = StockReservation.objects.select_for_update(of=("self",)).select_related("product", "warehouse").get(tenant=tenant, pk=reservation_id)
    if reservation.status != StockReservation.STATUS_ACTIVE:
        raise ValueError("Only active reservations may be released.")
    reservation.status = StockReservation.STATUS_RELEASED
    reservation.save(update_fields=["status"])
    StockMovement.objects.create(tenant=tenant, product=reservation.product, warehouse=reservation.warehouse, quantity=Decimal("0"), movement_type="reservation_release", reference=reservation.reference, previous_stock=reservation.product.stock_quantity, new_stock=reservation.product.stock_quantity, note=f"Reservation {reservation.id} released")
    return reservation


@transaction.atomic
def run_cycle_count(*, tenant, count_id, counted_lines, user=None):
    count = CycleCount.objects.select_for_update(of=("self",)).select_related("warehouse").get(tenant=tenant, pk=count_id)
    if count.status == CycleCount.STATUS_RECONCILED:
        raise ValueError("A reconciled cycle count cannot be applied twice.")
    movements = []
    for payload in counted_lines:
        product = _tenant_product(tenant, payload["product_id"])
        warehouse = count.warehouse
        expected = _decimal(product.stock_quantity or 0) if warehouse is None else _decimal(_stock_row(tenant, warehouse, product).quantity)
        counted = _decimal(payload["counted_quantity"])
        line, _ = CycleCountLine.objects.update_or_create(
            tenant=tenant, count=count, product=product,
            defaults={"expected_quantity": expected, "counted_quantity": counted, "variance": counted - expected, "note": payload.get("note", "")},
        )
        if line.variance:
            _, movement = create_adjustment(
                tenant=tenant, product_id=product.id, warehouse_id=warehouse.id if warehouse else None,
                new_quantity=counted, reason=f"Cycle count {count.reference or count.id}", note=line.note, user=user,
            )
            movements.append(movement)
    count.status = CycleCount.STATUS_RECONCILED
    count.completed_at = timezone.now()
    count.save(update_fields=["status", "completed_at"])
    return count, movements


@transaction.atomic
def compute_abc(tenant, window_days=365):
    since = timezone.now() - timedelta(days=window_days)
    items = OrderItem.objects.filter(tenant=tenant, order__created_at__gte=since).values("product").annotate(value=Sum("subtotal")).order_by("-value")
    total = sum((_decimal(item["value"] or 0) for item in items), Decimal("0")) or Decimal("1")
    ABCAnalysis.objects.filter(tenant=tenant).delete()
    cumulative = Decimal("0")
    records = []
    for item in items:
        cumulative += _decimal(item["value"] or 0)
        share = cumulative / total
        classification = ABCAnalysis.CLASS_A if share <= Decimal("0.80") else ABCAnalysis.CLASS_B if share <= Decimal("0.95") else ABCAnalysis.CLASS_C
        records.append(ABCAnalysis(tenant=tenant, product_id=item["product"], annual_value=item["value"] or 0, cumulative_share=share, abc_class=classification))
    ABCAnalysis.objects.bulk_create(records)
    return records


@transaction.atomic
def compute_aging(tenant):
    InventoryAgingSnapshot.objects.filter(tenant=tenant).delete()
    snapshots = []
    for product in Product.objects.filter(tenant=tenant, is_active=True):
        last_in = StockMovement.objects.filter(tenant=tenant, product=product, quantity__gt=0).order_by("-created_at").first()
        days = (timezone.now() - last_in.created_at).days if last_in else 999
        bucket = "0-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        snapshots.append(InventoryAgingSnapshot(tenant=tenant, product=product, bucket=bucket, quantity=product.stock_quantity))
    InventoryAgingSnapshot.objects.bulk_create(snapshots)
    return snapshots


def products_below_reorder(tenant):
    results = []
    for rule in ReorderRule.objects.filter(tenant=tenant, is_active=True).select_related("product", "warehouse", "supplier"):
        available = available_stock(tenant, rule.product, rule.warehouse)
        if available <= rule.reorder_point:
            results.append({"rule_id": rule.id, "product_id": rule.product_id, "product_name": rule.product.name, "sku": rule.product.sku, "warehouse_id": rule.warehouse_id, "available": available, "reorder_point": rule.reorder_point, "target_stock": rule.target_stock, "suggested_quantity": max(rule.target_stock - available, Decimal("0")), "supplier_id": rule.supplier_id})
    return results
