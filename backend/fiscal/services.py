"""
fiscal/services.py - Fiscal invoice business logic.

All functions accept an explicit tenant parameter and validate object
ownership before operating.  No function trusts client-supplied IDs without
confirming the object belongs to the active tenant.
"""
import base64
import json
import uuid as uuid_lib
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from xml.sax.saxutils import escape as xml_escape

from tax.models import TaxBreakdown

from .models import (
    InvoiceSequence,
    FiscalInvoice,
    FiscalInvoiceLine,
    FiscalDevice,
    FiscalSubmission,
)

from django.db import transaction
from django.utils import timezone

from pos.models import Order, Customer


class FiscalServiceError(Exception):
    pass


def _get_tenant_object(model, *, tenant, pk, label=None):
    try:
        return model.objects.get(tenant=tenant, pk=pk)
    except model.DoesNotExist:
        raise FiscalServiceError(
            f"{label or model.__name__} not found for the active tenant."
        )


def _get_tenant_sequence(tenant, sequence_id):
    return _get_tenant_object(InvoiceSequence, tenant=tenant, pk=sequence_id, label="Invoice sequence")


def _get_tenant_order(tenant, order_id):
    return _get_tenant_object(Order, tenant=tenant, pk=order_id, label="Order")


def _get_tenant_customer(tenant, customer_id):
    return _get_tenant_object(Customer, tenant=tenant, pk=customer_id, label="Customer")


def _get_tenant_invoice(tenant, invoice_id):
    return _get_tenant_object(FiscalInvoice, tenant=tenant, pk=invoice_id, label="Fiscal invoice")


def _get_tenant_device(tenant, device_id):
    return _get_tenant_object(FiscalDevice, tenant=tenant, pk=device_id, label="Fiscal device")


@transaction.atomic
def next_invoice_number(sequence):
    seq = InvoiceSequence.objects.select_for_update().get(pk=sequence.id)
    number = f"{seq.prefix}-{seq.next_number:0{seq.padding}d}"
    seq.next_number += 1
    seq.save(update_fields=["next_number"])
    return number


def build_qr_payload(invoice):
    parts = [
        f"S:{invoice.sequence.name}",
        f"N:{invoice.invoice_number}",
        f"D:{invoice.issue_date or date.today().isoformat()}",
        f"T:{invoice.total}",
        f"X:{invoice.tax}",
        f"U:{invoice.uuid}",
    ]
    if invoice.fbr_invoice_number:
        parts.append(f"F:{invoice.fbr_invoice_number}")
    raw = "|".join(parts)
    return base64.b64encode(raw.encode()).decode()


def build_xml(invoice, order=None, customer=None):
    items_xml = []
    if order:
        for it in order.items.all():
            items_xml.append(
                f"<Line><Product>{xml_escape(str(it.product.name))}</Product>"
                f"<Qty>{it.quantity}</Qty><UnitPrice>{it.unit_price}</UnitPrice>"
                f"<Subtotal>{it.subtotal}</Subtotal></Line>"
            )
    customer_name = xml_escape(str(customer.name)) if customer else "Walk-in customer"
    lines_str = ''.join(items_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
  <InvoiceNumber>{xml_escape(invoice.invoice_number)}</InvoiceNumber>
  <UUID>{xml_escape(invoice.uuid)}</UUID>
  <IssueDate>{invoice.issue_date or date.today().isoformat()}</IssueDate>
  <Customer>{customer_name}</Customer>
  <Subtotal>{invoice.subtotal}</Subtotal>
  <Tax>{invoice.tax}</Tax>
  <Discount>{invoice.discount}</Discount>
  <Total>{invoice.total}</Total>
  <Lines>{lines_str}</Lines>
  <QR>{xml_escape(invoice.qr_payload)}</QR>
</Invoice>"""


@transaction.atomic
def issue_invoice(*, tenant, order_id=None, sequence_id, customer_id=None,
                  user=None, document_type=None):
    seq = _get_tenant_sequence(tenant, sequence_id)
    if document_type and seq.document_type != document_type:
        raise FiscalServiceError("Sequence document_type mismatch")
    order = _get_tenant_order(tenant, order_id) if order_id else None
    if order is not None and seq.document_type == InvoiceSequence.TYPE_INVOICE:
        # One sale = one fiscal invoice. A second live invoice for the same
        # order would report the sale to FBR twice (checkout fiscalizes
        # automatically). The order row lock serializes concurrent issuers.
        Order.objects.select_for_update().filter(pk=order.pk, tenant=tenant).first()
        existing = (
            FiscalInvoice.objects.filter(tenant=tenant, order=order, sequence__document_type=InvoiceSequence.TYPE_INVOICE)
            .exclude(status__in=[FiscalInvoice.STATUS_CANCELLED, FiscalInvoice.STATUS_VOID])
            .first()
        )
        if existing is not None:
            raise FiscalServiceError(f"Order already has fiscal invoice {existing.invoice_number}.")
    customer = _get_tenant_customer(tenant, customer_id) if customer_id else (
        _get_tenant_customer(tenant, order.customer_id) if order and order.customer_id else None
    )
    # Use a UUID-based placeholder to avoid unique constraint collisions
    # between concurrent transactions. The real sequential number replaces
    # this before the atomic block commits.
    placeholder = f"PENDING-{uuid_lib.uuid4().hex[:12]}"
    invoice = FiscalInvoice.objects.create(tenant=tenant, sequence=seq, invoice_number=placeholder,
                                             order=order, customer=customer,
                                             created_by=user, uuid=uuid_lib.uuid4().hex,
                                             status=FiscalInvoice.STATUS_DRAFT)
    invoice.invoice_number = next_invoice_number(seq)
    if order:
        invoice.subtotal = order.subtotal
        invoice.tax = order.tax
        invoice.discount = order.discount
        invoice.total = order.total
    invoice.issue_date = date.today()
    
    _create_fiscal_line_snapshots(
        tenant=tenant,
        invoice=invoice,
        order=order,
    )
    invoice.qr_payload = build_qr_payload(invoice)
    invoice.xml_content = build_xml(invoice, order, customer)
    invoice.status = FiscalInvoice.STATUS_ISSUED
    invoice.save()
    return invoice


@transaction.atomic
def cancel_invoice(*, tenant, invoice_id, user=None):
    inv = _get_tenant_invoice(tenant, invoice_id)
    if inv.status != FiscalInvoice.STATUS_ISSUED:
        raise FiscalServiceError(f"Cannot cancel invoice in '{inv.status}' status.")
    inv.status = FiscalInvoice.STATUS_CANCELLED
    inv.save(update_fields=["status"])
    return inv


def submit_to_device(*, tenant, invoice_id, device_id, user=None):
    inv = _get_tenant_invoice(tenant, invoice_id)
    device = _get_tenant_device(tenant, device_id)
    if inv.status not in (FiscalInvoice.STATUS_ISSUED,):
        raise FiscalServiceError(f"Cannot submit invoice in '{inv.status}' status.")
    if device.provider == FiscalDevice.PROVIDER_FBR:
        return _submit_to_fbr(tenant=tenant, invoice=inv, device=device, user=user)
    return _submit_to_stub(tenant=tenant, invoice=inv, device=device)


def _submit_to_fbr(*, tenant, invoice, device, user=None):
    """Post to the FBR Digital Invoicing API and mirror the outcome locally."""
    from fbr.payload import FBRValidationError
    from fbr.services import FBRServiceError, submit_invoice

    try:
        fbr_submission = submit_invoice(tenant=tenant, invoice_id=invoice.id, user=user)
    except (FBRServiceError, FBRValidationError) as exc:
        raise FiscalServiceError(str(exc))

    # Only a genuine FBR/component acceptance is mirrored as accepted, and only
    # a genuine rejection as rejected. A simulated acceptance, an unknown
    # outcome (timeout: may have been fiscalized) or a transport failure is not
    # an authority decision and needs operator review.
    simulated = getattr(fbr_submission, "is_simulated", False)
    accepted = fbr_submission.status == fbr_submission.STATUS_ACCEPTED and not simulated
    if fbr_submission.status == fbr_submission.STATUS_REJECTED and not simulated:
        mirrored_status = FiscalSubmission.STATUS_REJECTED
    elif accepted:
        mirrored_status = FiscalSubmission.STATUS_ACCEPTED
    else:
        mirrored_status = FiscalSubmission.STATUS_REQUIRES_REVIEW
    if accepted:
        mirrored = FiscalSubmission.objects.filter(
            invoice=invoice, status=FiscalSubmission.STATUS_ACCEPTED,
            reference=fbr_submission.fbr_invoice_number,
        ).first()
        if mirrored is not None:
            return mirrored
    sub = FiscalSubmission.objects.create(
        tenant=tenant, invoice=invoice, device=device,
        status=mirrored_status,
        reference=fbr_submission.fbr_invoice_number,
        response_payload=json.dumps(fbr_submission.response_payload or {"error": fbr_submission.error_message}),
        responded_at=timezone.now(),
    )
    device.last_used_at = timezone.now()
    device.save(update_fields=["last_used_at"])
    return sub


@transaction.atomic
def _submit_to_stub(*, tenant, invoice, device):
    inv = invoice
    if FiscalSubmission.objects.select_for_update().filter(
        invoice=inv, status=FiscalSubmission.STATUS_PENDING
    ).exists():
        raise FiscalServiceError("This invoice already has a pending submission.")
    sub = FiscalSubmission.objects.create(
        tenant=tenant, invoice=inv, device=device,
        status=FiscalSubmission.STATUS_PENDING)
    sub.reference = f"STUB-{inv.invoice_number}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
    sub.status = FiscalSubmission.STATUS_PENDING
    sub.response_payload = json.dumps({
        "stub": True,
        "message": "Stub submission. Wire in the real provider before production.",
        "invoice_number": inv.invoice_number,
    })
    sub.responded_at = timezone.now()
    sub.save()
    device.last_used_at = timezone.now()
    device.save(update_fields=["last_used_at"])
    return sub


def _snapshot_fbr_profile(product):
    profile = getattr(product, "fbr_profile", None)

    if profile is None:
        return {}

    transaction_type = profile.transaction_type
    sro_schedule = profile.sro_schedule

    return {
        "profile_id": profile.pk,

        "hs_code": (
            profile.hs_code.dotted_code
            if hasattr(profile.hs_code, "dotted_code")
            else profile.hs_code.code
        ),

        "uom": (
            profile.uom.description
            or profile.uom.code
        ),

        "transaction_type_code": (
            transaction_type.numeric_code
            if transaction_type
            else None
        ),

        "sale_type": (
            transaction_type.description
            or transaction_type.code
        ) if transaction_type else "",

        "sro_schedule_no": (
            sro_schedule.code
            if sro_schedule
            else ""
        ),

        "sro_item_serial_no": profile.sro_item_serial_no or "",

        "pct_code": profile.pct_code or "",

        "third_schedule": bool(profile.third_schedule),

        "product_code": (
            profile.product_code
            or product.sku
        ),

        "sales_tax_rate": str(profile.sales_tax_rate),
        "retail_price": str(profile.retail_price),
        "extra_tax_rate": str(profile.extra_tax_rate),
        "further_tax_rate": str(profile.further_tax_rate),
        "fed_payable_rate": str(profile.fed_payable_rate),
        "cvt_rate": str(profile.cvt_rate),
        "st_withheld_rate": str(profile.st_withheld_rate),

        "withholding_income_tax_rate": str(
            profile.withholding_income_tax_rate
        ),

        "withholding_income_tax_rate_2": str(
            profile.withholding_income_tax_rate_2
        ),

        "withholding_section_1": (
            profile.withholding_section_1 or ""
        ),

        "withholding_section_2": (
            profile.withholding_section_2 or ""
        ),
    }


def _create_fiscal_line_snapshots(*, tenant, invoice, order):
    """
    Freeze the OrderItem, tax-engine output and FBR metadata
    at fiscal invoice creation time.
    """

    if order is None:
        return

    items = list(
        order.items
        .select_related(
            "product",
            "product__fbr_profile",
            "product__fbr_profile__hs_code",
            "product__fbr_profile__uom",
            "product__fbr_profile__transaction_type",
            "product__fbr_profile__sro_schedule",
        )
        .order_by("id")
    )

    breakdowns = TaxBreakdown.objects.filter(
        tenant=tenant,
        order=order,
        order_item__isnull=False,
    ).order_by(
        "order_item_id",
        "id",
    )

    breakdown_by_item = {}

    for row in breakdowns:
        breakdown_by_item.setdefault(
            row.order_item_id,
            [],
        ).append(
            {
                "tax_rate_id": row.tax_rate_id,
                "code": row.tax_rate_code,
                "rate": str(row.rate),
                "taxable_amount": str(row.taxable_amount),
                "tax_amount": str(row.tax_amount),
                "mode": row.mode,
            }
        )

    line_values = [
        _money(item.subtotal)
        for item in items
    ]

    discounts = _allocate_order_discount(
        line_values,
        invoice.discount,
    )

    for line_number, (item, discount) in enumerate(
        zip(items, discounts),
        start=1,
    ):
        tax_rows = breakdown_by_item.get(
            item.id,
            [],
        )

        tax_amount = sum(
            (
                Decimal(row["tax_amount"])
                for row in tax_rows
            ),
            Decimal("0.00"),
        )

        fbr_values = _calculate_fbr_line(
            item=item,
            discount=discount,
        )

        FiscalInvoiceLine.objects.create(
            tenant=tenant,
            invoice=invoice,

            source_order_item=item,
            source_product=item.product,

            line_number=line_number,

            product_name=item.product.name,
            product_sku=item.product.sku,
            product_description=item.product.description or "",

            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item.subtotal,

            discount=fbr_values["discount"],

            taxable_amount=fbr_values["taxable_amount"],

            # Preserve the tax-engine snapshot for this line.
            tax_amount=tax_amount,

            total_amount=fbr_values["total_amount"],

            sales_tax=fbr_values["sales_tax"],
            sales_tax_withheld=fbr_values["sales_tax_withheld"],
            extra_tax=fbr_values["extra_tax"],
            further_tax=fbr_values["further_tax"],
            fed_payable=fbr_values["fed_payable"],
            cvt=fbr_values["cvt"],
            withholding_income_tax=fbr_values[
                "withholding_income_tax"
            ],
            withholding_income_tax_2=fbr_values[
                "withholding_income_tax_2"
            ],
            fixed_notified_value_or_retail_price=(
                fbr_values[
                    "fixed_notified_value_or_retail_price"
                ]
            ),

            tax_breakdown=tax_rows,

            fbr_snapshot=_snapshot_fbr_profile(
                item.product
            ),
        )


def _money(value):
    # Half-up, like the POS (tax.engine.money) and the FBR payload builders;
    # the default banker's rounding made x.xx5 differ by one paisa.
    return Decimal(value or 0).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )


def _allocate_order_discount(line_values, discount):
    """
    Allocate an order-level discount across invoice lines.

    This preserves the existing FBR allocation behaviour, but places
    the financial rule in the fiscal layer rather than the FBR adapter.
    """

    # Single allocation shared with checkout (tax.engine), so the discount
    # split - and therefore the tax - matches what the customer was charged.
    from tax.engine import allocate_order_discount

    return allocate_order_discount(line_values, discount)


def _calculate_fbr_line(
    *,
    item,
    discount,
):
    """
    Calculate the complete FBR monetary snapshot for one invoice line.

    This is the ONLY place where FBR monetary values are calculated.

    fbr/payload.py must never recalculate these values.
    """

    product = item.product
    profile = getattr(product, "fbr_profile", None)

    if profile is None or not profile.is_active:
        raise FiscalServiceError(
            f"Product '{product.name}' has no active FBR profile."
        )

    quantity = Decimal(item.quantity or 0)

    subtotal = _money(item.subtotal)
    discount = _money(discount)

    taxable_amount = _money(
        subtotal - discount
    )

    sales_tax = _money(
        taxable_amount
        * profile.sales_tax_rate
        / Decimal("100")
    )

    extra_tax = _money(
        taxable_amount
        * profile.extra_tax_rate
        / Decimal("100")
    )

    further_tax = _money(
        taxable_amount
        * profile.further_tax_rate
        / Decimal("100")
    )

    fed_payable = _money(
        taxable_amount
        * profile.fed_payable_rate
        / Decimal("100")
    )

    sales_tax_withheld = _money(
        sales_tax
        * profile.st_withheld_rate
        / Decimal("100")
    )

    cvt = _money(
        taxable_amount
        * profile.cvt_rate
        / Decimal("100")
    )

    withholding_income_tax = _money(
        taxable_amount
        * profile.withholding_income_tax_rate
        / Decimal("100")
    )

    withholding_income_tax_2 = _money(
        taxable_amount
        * profile.withholding_income_tax_rate_2
        / Decimal("100")
    )

    fixed_retail = Decimal("0.00")

    if profile.retail_price:
        fixed_retail = _money(
            profile.retail_price * quantity
        )

    total_amount = _money(
        taxable_amount
        + sales_tax
        + extra_tax
        + further_tax
        + fed_payable
    )

    return {
        "discount": discount,
        "taxable_amount": taxable_amount,
        "sales_tax": sales_tax,
        "sales_tax_withheld": sales_tax_withheld,
        "extra_tax": extra_tax,
        "further_tax": further_tax,
        "fed_payable": fed_payable,
        "cvt": cvt,
        "withholding_income_tax": withholding_income_tax,
        "withholding_income_tax_2": withholding_income_tax_2,
        "fixed_notified_value_or_retail_price": fixed_retail,
        "total_amount": total_amount,
    }