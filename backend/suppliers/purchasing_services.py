import secrets
from decimal import Decimal


from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Batch, BatchMovement, SerialNumber
from enterprise.models import Warehouse
from inventory.services import apply_adjustment
from pos.models import Product, PurchaseOrder, PurchaseOrderItem, Supplier

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseReturn, PurchaseReturnLine, SupplierContact, SupplierPortalToken


def _decimal(value):
    return Decimal(str(value))


def _supplier(tenant, supplier_id):
    return Supplier.objects.get(tenant=tenant, pk=supplier_id)


def _warehouse(tenant, warehouse_id):
    return Warehouse.objects.get(tenant=tenant, pk=warehouse_id, is_active=True)


def _order_totals(order):
    order.subtotal = sum((line.subtotal for line in order.items.all()), Decimal("0"))
    order.tax = Decimal("0")
    order.total = order.subtotal
    order.save(update_fields=["subtotal", "tax", "total", "updated_at"])
    return order


def _replace_draft_lines(tenant, order, items):
    ids = [line["product_id"] for line in items]
    products = {row.id: row for row in Product.objects.filter(tenant=tenant, is_active=True, pk__in=ids)}
    if len(products) != len(set(ids)):
        raise ValidationError({"items": "Every purchase-order product must be active and belong to the active tenant."})
    PurchaseOrderItem.objects.filter(tenant=tenant, purchase_order=order).delete()
    PurchaseOrderItem.objects.bulk_create([
        PurchaseOrderItem(
            tenant=tenant,
            purchase_order=order,
            product=products[line["product_id"]],
            quantity=_decimal(line["quantity"]),
            unit_cost=_decimal(line["unit_cost"]),
            subtotal=_decimal(line["quantity"]) * _decimal(line["unit_cost"]),
        )
        for line in items
    ])
    return _order_totals(order)


@transaction.atomic
def create_purchase_order(*, tenant, payload):
    supplier = _supplier(tenant, payload["supplier_id"])
    if not supplier.is_active:
        raise ValidationError({"supplier_id": "Archived suppliers cannot receive new purchase orders."})
    order = PurchaseOrder.objects.create(
        tenant=tenant,
        supplier=supplier,
        warehouse=_warehouse(tenant, payload["warehouse_id"]),
        order_number=None,
        expected_date=payload.get("expected_date"),
        supplier_invoice_number=payload.get("supplier_invoice_number", ""),
        note=payload.get("note", ""),
    )
    order.order_number = f"PO-{tenant.id}-{order.id:06d}"
    order.save(update_fields=["order_number", "updated_at"])
    return _replace_draft_lines(tenant, order, payload["items"])


@transaction.atomic
def update_draft_purchase_order(*, tenant, order, payload):
    order = PurchaseOrder.objects.select_for_update().get(tenant=tenant, pk=order.pk)
    if order.status != "draft":
        raise ValidationError({"detail": "Only draft purchase orders may be edited."})
    supplier = _supplier(tenant, payload["supplier_id"])
    if not supplier.is_active:
        raise ValidationError({"supplier_id": "Archived suppliers cannot receive new purchase orders."})
    order.supplier = supplier
    order.warehouse = _warehouse(tenant, payload["warehouse_id"])
    order.expected_date = payload.get("expected_date")
    order.supplier_invoice_number = payload.get("supplier_invoice_number", "")
    order.note = payload.get("note", "")
    order.save(update_fields=["supplier", "warehouse", "expected_date", "supplier_invoice_number", "note", "updated_at"])
    return _replace_draft_lines(tenant, order, payload["items"])


@transaction.atomic
def confirm_purchase_order(*, tenant, order):
    order = PurchaseOrder.objects.select_for_update().get(tenant=tenant, pk=order.pk)
    if order.status != "draft":
        raise ValidationError({"detail": "Only draft purchase orders may be confirmed."})
    if not order.items.exists():
        raise ValidationError({"detail": "A purchase order must contain at least one line before confirmation."})
    order.status = "ordered"
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def cancel_purchase_order(*, tenant, order):
    order = PurchaseOrder.objects.select_for_update().get(tenant=tenant, pk=order.pk)
    if order.status in {"received", "cancelled"} or order.items.filter(received_quantity__gt=0).exists():
        raise ValidationError({"detail": "This purchase order cannot be cancelled in its current state."})
    order.status = "cancelled"
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def create_receipt(*, tenant, purchase_order, payload, user):
    order = PurchaseOrder.objects.select_for_update().select_related("warehouse", "supplier").get(tenant=tenant, pk=purchase_order.pk)
    if order.status != "ordered":
        raise ValidationError({"detail": "Only confirmed purchase orders may receive stock."})
    receipt = GoodsReceipt.objects.create(
        tenant=tenant,
        purchase_order=order,
        receipt_number=None,
        supplier_invoice_number=payload.get("supplier_invoice_number", ""),
        note=payload.get("note", ""),
        received_by=user,
    )
    receipt.receipt_number = f"GR-{tenant.id}-{receipt.id:06d}"
    receipt.save(update_fields=["receipt_number"])
    for line_data in payload["lines"]:
        item = PurchaseOrderItem.objects.select_for_update().select_related("product").filter(
            tenant=tenant, purchase_order=order, pk=line_data["purchase_order_item_id"]
        ).first()
        if item is None:
            raise ValidationError({"lines": "Receipt lines must belong to this purchase order and the active tenant."})
        quantity = _decimal(line_data["quantity"])
        remaining = item.quantity - item.received_quantity
        if quantity > remaining:
            raise ValidationError({"lines": f"Only {remaining} units remain for {item.product.name}."})
        serial_numbers = line_data.get("serial_numbers", [])
        if serial_numbers:
            if quantity != quantity.to_integral_value() or len(serial_numbers) != int(quantity):
                raise ValidationError({"lines": f"Provide one serial number for every whole received unit of {item.product.name}."})
            if SerialNumber.objects.filter(tenant=tenant, product=item.product, serial_number__in=serial_numbers).exists():
                raise ValidationError({"lines": f"A serial number already exists for {item.product.name}."})
        batch = None
        batch_number = line_data.get("batch_number", "").strip()
        if batch_number:
            batch, created = Batch.objects.select_for_update().get_or_create(
                tenant=tenant,
                product=item.product,
                batch_number=batch_number,
                defaults={"quantity": Decimal("0"), "remaining_quantity": Decimal("0"), "expiry_date": line_data.get("expiry_date"), "received_at": timezone.now(), "supplier": order.supplier},
            )
            if not created and line_data.get("expiry_date") and batch.expiry_date not in {None, line_data["expiry_date"]}:
                raise ValidationError({"lines": f"Batch {batch_number} already has a different expiry date."})
            batch.quantity += quantity
            batch.remaining_quantity += quantity
            if batch.expiry_date is None and line_data.get("expiry_date"):
                batch.expiry_date = line_data["expiry_date"]
            batch.save(update_fields=["quantity", "remaining_quantity", "expiry_date"])
            BatchMovement.objects.create(tenant=tenant, batch=batch, kind=BatchMovement.KIND_PURCHASE, quantity=quantity, reference=receipt.receipt_number, created_by=user)
        receipt_line = GoodsReceiptLine.objects.create(
            tenant=tenant, receipt=receipt, purchase_order_item=item, batch=batch,
            quantity_ordered=item.quantity, quantity_received=quantity, quantity_accepted=quantity, quantity_rejected=Decimal("0"),
        )
        for serial in serial_numbers:
            try:
                with transaction.atomic():
                    SerialNumber.objects.create(
                        tenant=tenant,
                        product=item.product,
                        batch=batch,
                        serial_number=serial,
                        status=SerialNumber.STATUS_IN_STOCK,
                        purchased_at=timezone.now(),
                        cost_price=item.unit_cost,
                    )
            except IntegrityError as exc:
                raise ValidationError(
                    {"lines": f"Serial number {serial} already exists for {item.product.name}."}
                ) from exc
        apply_adjustment(
            tenant=tenant, product_id=item.product_id, warehouse_id=order.warehouse_id, quantity=quantity,
            reason=f"Purchase receipt {receipt.receipt_number}", note=payload.get("note", ""), user=user,
            movement_type="purchase", reference=receipt.receipt_number,
        )
        item.received_quantity += quantity
        item.save(update_fields=["received_quantity"])
    if all(line.received_quantity >= line.quantity for line in PurchaseOrderItem.objects.filter(tenant=tenant, purchase_order=order)):
        order.status = "received"
        order.save(update_fields=["status", "updated_at"])
    from accounting.services import emit_accounting_event

    receipt_total = sum(
        (line.quantity_accepted * line.purchase_order_item.unit_cost for line in receipt.lines.select_related("purchase_order_item")),
        Decimal("0.00"),
    )
    if receipt_total > 0:
        emit_accounting_event(
            tenant=tenant,
            source_domain="purchasing",
            event_type="goods_receipt",
            source_id=str(receipt.id),
            event_date=timezone.localdate(),
            amount=receipt_total,
            source_reference=receipt.receipt_number,
            payload={"receipt_id": receipt.id, "purchase_order_id": order.id, "supplier_id": order.supplier_id},
            user=user,
        )
    return receipt


@transaction.atomic
def create_purchase_return(*, tenant, purchase_order, payload, user):
    order = PurchaseOrder.objects.select_for_update().select_related("warehouse").get(tenant=tenant, pk=purchase_order.pk)
    if order.status not in {"ordered", "received"}:
        raise ValidationError({"detail": "Only confirmed or received purchase orders may have supplier returns."})
    purchase_return = PurchaseReturn.objects.create(
        tenant=tenant, purchase_order=order, return_number=None, reason=payload.get("reason", ""),
        supplier_credit_note=payload.get("supplier_credit_note", ""), created_by=user,
    )
    purchase_return.return_number = f"PR-{tenant.id}-{purchase_return.id:06d}"
    purchase_return.save(update_fields=["return_number"])
    total = Decimal("0")
    for line_data in payload["lines"]:
        item = PurchaseOrderItem.objects.filter(tenant=tenant, purchase_order=order, pk=line_data["purchase_order_item_id"]).first()
        if item is None:
            raise ValidationError({"lines": "Return lines must belong to this purchase order and the active tenant."})
        receipt_line = None
        if line_data.get("receipt_line_id"):
            receipt_line = GoodsReceiptLine.objects.filter(tenant=tenant, receipt__purchase_order=order, purchase_order_item=item, pk=line_data["receipt_line_id"]).first()
            if receipt_line is None:
                raise ValidationError({"lines": "The receipt line does not belong to this purchase-order line."})
        quantity = _decimal(line_data["quantity"])
        total += quantity * item.unit_cost
        PurchaseReturnLine.objects.create(
            tenant=tenant, purchase_return=purchase_return, purchase_order_item=item, receipt_line=receipt_line,
            quantity=quantity, unit_cost=item.unit_cost, reason=line_data.get("reason", ""),
        )
    purchase_return.total_amount = total
    purchase_return.save(update_fields=["total_amount"])
    return purchase_return


@transaction.atomic
def process_purchase_return(*, tenant, purchase_return, user):
    purchase_return = PurchaseReturn.objects.select_for_update().select_related("purchase_order", "purchase_order__warehouse").get(tenant=tenant, pk=purchase_return.pk)
    if purchase_return.status != PurchaseReturn.STATUS_DRAFT:
        raise ValidationError({"detail": "Only draft supplier returns may be processed."})
    for line in PurchaseReturnLine.objects.select_related("purchase_order_item", "receipt_line", "receipt_line__batch").filter(tenant=tenant, purchase_return=purchase_return):
        item = PurchaseOrderItem.objects.select_for_update().select_related("product").get(tenant=tenant, pk=line.purchase_order_item_id)
        available = item.received_quantity - item.returned_quantity
        if line.quantity > available:
            raise ValidationError({"lines": f"Only {available} received units are available to return for {item.product.name}."})
        if line.receipt_line_id:
            prior = PurchaseReturnLine.objects.filter(tenant=tenant, receipt_line_id=line.receipt_line_id, purchase_return__status=PurchaseReturn.STATUS_RETURNED).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            if line.quantity + prior > line.receipt_line.quantity_accepted:
                raise ValidationError({"lines": "Return quantity exceeds accepted quantity on the selected receipt line."})
            if line.receipt_line.batch_id:
                batch = Batch.objects.select_for_update().get(tenant=tenant, pk=line.receipt_line.batch_id)
                if line.quantity > batch.remaining_quantity:
                    raise ValidationError({"lines": f"Batch {batch.batch_number} does not have enough remaining stock."})
                batch.remaining_quantity -= line.quantity
                batch.save(update_fields=["remaining_quantity"])
                BatchMovement.objects.create(tenant=tenant, batch=batch, kind=BatchMovement.KIND_RETURN, quantity=-line.quantity, reference=purchase_return.return_number, created_by=user)
        try:
            apply_adjustment(
                tenant=tenant,
                product_id=item.product_id,
                warehouse_id=purchase_return.purchase_order.warehouse_id,
                quantity=-line.quantity,
                reason=f"Supplier return {purchase_return.return_number}",
                note=line.reason or purchase_return.reason,
                user=user,
                movement_type="purchase_return",
                reference=purchase_return.return_number,
            )
        except ValueError as exc:
            raise ValidationError({"lines": str(exc)}) from exc
        item.returned_quantity += line.quantity
        item.save(update_fields=["returned_quantity"])
    purchase_return.status = PurchaseReturn.STATUS_RETURNED
    purchase_return.processed_at = timezone.now()
    purchase_return.processed_by = user
    purchase_return.save(update_fields=["status", "processed_at", "processed_by"])
    from accounting.models import AccountingEvent
    from accounting.services import emit_accounting_event

    original_receipt_event = AccountingEvent.objects.filter(
        tenant=tenant,
        source_domain="purchasing",
        event_type="goods_receipt",
        payload__purchase_order_id=purchase_return.purchase_order_id,
    ).order_by("id").first()
    if purchase_return.total_amount > 0:
        emit_accounting_event(
            tenant=tenant,
            source_domain="purchasing",
            event_type="purchase_return",
            source_id=str(purchase_return.id),
            event_date=purchase_return.processed_at.date(),
            amount=purchase_return.total_amount,
            source_reference=purchase_return.return_number,
            payload={"purchase_return_id": purchase_return.id, "purchase_order_id": purchase_return.purchase_order_id},
            reversal_of=original_receipt_event,
            user=user,
        )
    return purchase_return


@transaction.atomic
def cancel_purchase_return(*, tenant, purchase_return):
    purchase_return = PurchaseReturn.objects.select_for_update().get(tenant=tenant, pk=purchase_return.pk)
    if purchase_return.status != PurchaseReturn.STATUS_DRAFT:
        raise ValidationError({"detail": "Only draft supplier returns may be cancelled."})
    purchase_return.status = PurchaseReturn.STATUS_CANCELLED
    purchase_return.save(update_fields=["status"])
    return purchase_return


@transaction.atomic
def save_supplier_contact(*, tenant, supplier, serializer):
    if serializer.validated_data.get("is_primary"):
        SupplierContact.objects.filter(tenant=tenant, supplier=supplier, is_primary=True).update(is_primary=False)
    return serializer.save(tenant=tenant, supplier=supplier)


def issue_supplier_portal_token(*, tenant, supplier):
    token, _ = SupplierPortalToken.objects.update_or_create(
        tenant=tenant, supplier=supplier,
        defaults={"token": secrets.token_urlsafe(32), "contact_email": supplier.email, "is_active": True},
    )
    return token
