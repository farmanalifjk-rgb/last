from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from enterprise.models import Warehouse, WarehouseStock
from pos.models import Product, StockMovement

from .models import BinReplenishmentTask, PutAwayRule, PutAwayTask, StockTransfer, StockTransferItem


def _decimal(value): return Decimal(str(value))


def _next_number(tenant):
    prefix = f"TR-{tenant.id}-"
    last = StockTransfer.objects.select_for_update().filter(
        tenant=tenant,
        transfer_number__startswith=prefix,
    ).order_by("-transfer_number").first()
    try:
        suffix = int(last.transfer_number.rsplit("-", 1)[-1]) + 1 if last else 1
    except ValueError:
        suffix = 1
    return f"{prefix}{suffix:06d}"


def _warehouse_stock(tenant, warehouse, product):
    return WarehouseStock.objects.select_for_update().get_or_create(
        tenant=tenant, warehouse=warehouse, product=product, defaults={"quantity": Decimal("0")}
    )[0]


@transaction.atomic
def create_transfer(*, tenant, source, destination, lines, note="", user=None):
    # A tenant-row lock serializes reference allocation without blocking transfers
    # belonging to another workspace.
    from saas.models import Tenant

    Tenant.objects.select_for_update().get(pk=tenant.id)
    if source.tenant_id != tenant.id or destination.tenant_id != tenant.id:
        raise ValueError("Transfer warehouses must belong to the active tenant.")
    if source.id == destination.id:
        raise ValueError("Source and destination warehouses must differ.")
    if not lines:
        raise ValueError("A transfer needs at least one item.")
    transfer = StockTransfer.objects.create(tenant=tenant, transfer_number=_next_number(tenant), source_warehouse=source, destination_warehouse=destination, note=note, created_by=user)
    for line in lines:
        product = Product.objects.select_for_update().get(tenant=tenant, pk=line["product_id"])
        quantity = _decimal(line["quantity"])
        if quantity <= 0:
            raise ValueError("Transfer quantities must be positive.")
        source_stock = _warehouse_stock(tenant, source, product)
        if source_stock.quantity < quantity:
            raise ValueError(f"Insufficient source stock for {product.name}.")
        source_stock.quantity -= quantity
        source_stock.save(update_fields=["quantity", "updated_at"])
        # A warehouse transfer relocates existing aggregate inventory; it must
        # not reduce tenant-wide product stock while goods are in transit.
        previous = _decimal(product.stock_quantity)
        StockTransferItem.objects.create(tenant=tenant, transfer=transfer, product=product, quantity=quantity)
        StockMovement.objects.create(tenant=tenant, product=product, warehouse=source, quantity=-quantity, movement_type="transfer_out", reference=transfer.transfer_number, previous_stock=previous, new_stock=previous, note=f"Transfer to warehouse {destination.code}")
    transfer.status = StockTransfer.STATUS_IN_TRANSIT
    transfer.shipped_at = timezone.now()
    transfer.save(update_fields=["status", "shipped_at"])
    return transfer


@transaction.atomic
def receive_transfer(*, tenant, transfer_id, received_lines=None, user=None):
    transfer = StockTransfer.objects.select_for_update().prefetch_related("items__product").get(tenant=tenant, pk=transfer_id)
    if transfer.status != StockTransfer.STATUS_IN_TRANSIT:
        raise ValueError("Only in-transit transfers can be received.")
    requested = {int(row["item_id"]): _decimal(row["received_quantity"]) for row in (received_lines or []) if row.get("item_id") is not None and row.get("received_quantity") is not None}
    all_received = True
    for item in transfer.items.select_for_update().all():
        remaining = _decimal(item.quantity) - _decimal(item.received_quantity)
        received = requested.get(item.id, remaining)
        if received < 0 or received > remaining:
            raise ValueError("Received quantity must be between zero and the remaining transfer quantity.")
        if received != remaining: all_received = False
        if received:
            destination_stock = _warehouse_stock(tenant, transfer.destination_warehouse, item.product)
            destination_stock.quantity += received
            destination_stock.save(update_fields=["quantity", "updated_at"])
            product = Product.objects.select_for_update().get(pk=item.product_id, tenant=tenant)
            previous = _decimal(product.stock_quantity)
            StockMovement.objects.create(tenant=tenant, product=product, warehouse=transfer.destination_warehouse, quantity=received, movement_type="transfer_in", reference=transfer.transfer_number, previous_stock=previous, new_stock=previous, note=f"Transfer from warehouse {transfer.source_warehouse.code}")
        item.received_quantity += received
        item.save(update_fields=["received_quantity"])
    if all_received:
        transfer.status = StockTransfer.STATUS_RECEIVED
        transfer.received_at = timezone.now()
        transfer.received_by = user
        transfer.save(update_fields=["status", "received_at", "received_by"])
    return transfer


@transaction.atomic
def suggest_putaway(*, tenant, warehouse, product, quantity, reference=""):
    rule = PutAwayRule.objects.filter(tenant=tenant, warehouse=warehouse, is_active=True, category=product.category).first() if product.category_id else None
    if rule is None:
        rule = PutAwayRule.objects.filter(tenant=tenant, warehouse=warehouse, is_active=True, strategy=PutAwayRule.STRATEGY_FIXED).first()
    return PutAwayTask.objects.create(tenant=tenant, warehouse=warehouse, product=product, quantity=quantity, suggested_bin=rule.target_bin if rule else None, reference=reference)


@transaction.atomic
def generate_replenishment_tasks(*, tenant, warehouse, low_threshold=Decimal("5")):
    from inventory.models import BinLocation
    tasks = []
    for bin_location in BinLocation.objects.filter(tenant=tenant, warehouse=warehouse, is_active=True):
        for stock in WarehouseStock.objects.filter(tenant=tenant, warehouse=warehouse, quantity__lte=low_threshold).select_related("product"):
            task, created = BinReplenishmentTask.objects.get_or_create(tenant=tenant, warehouse=warehouse, product=stock.product, to_bin=bin_location, status=BinReplenishmentTask.STATUS_OPEN, defaults={"quantity": max(stock.product.min_stock - stock.quantity, Decimal("0"))})
            if created: tasks.append(task)
    return tasks
