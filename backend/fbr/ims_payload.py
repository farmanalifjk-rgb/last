"""Builds the Tier-1 IMS fiscal invoice JSON for the FBR Software Fiscal Component.

Field names, types and limits follow the FBR "Technical Specification for Data
Sharing through Software Fiscal Component from TIER 1 Retailer with FBR"
(Invoice Model Details / Invoice Data 1 / Invoice Item 1 tables; .Net and JSON
samples; cloud PostData sample).

Arithmetic of the canonical envelope
------------------------------------
``SaleValue``   — actual sale price on which tax is calculated, exclusive of
                  tax (net of the allocated discount), per line.
``TaxCharged``  — SaleValue x TaxRate / 100 (TaxRate is a plain float, e.g.
                  ``17`` — NOT the DI ``"17%"`` string).
``TotalAmount`` — SaleValue + TaxCharged + FurtherTax (what the buyer pays for
                  the line; the discount is already netted inside SaleValue and
                  reported separately in ``Discount``).
Header totals sum the lines:
``TotalSaleValue = sum(SaleValue)``, ``TotalTaxCharged = sum(TaxCharged)``,
``Discount = sum(line Discount)``, ``TotalQuantity = sum(Quantity)``,
``TotalBillAmount = sum(TotalAmount) = TotalSaleValue + TotalTaxCharged``.
This matches the spec's worked header example (1298 + 221 = 1519) and the
canonical integrations' example (100 + 17 = 117); the spec's own .Net item
sample is internally inconsistent and is not reproduced.
"""
from decimal import Decimal

from django.utils import timezone
from zoneinfo import ZoneInfo

from .constants import (
    IMS_BUYER_CNIC_LENGTH,
    IMS_BUYER_NTN_MAX_LENGTH,
    IMS_BUYER_PHONE_MAX_LENGTH,
    IMS_INVOICE_TYPE_FROM_DI,
    IMS_INVOICE_TYPE_NEW,
    IMS_ITEM_CODE_MAX_LENGTH,
    IMS_ITEM_NAME_MAX_LENGTH,
    IMS_ITEM_TYPE_CREDIT,
    IMS_ITEM_TYPE_NEW,
    IMS_ITEM_TYPE_THIRD_SCHEDULE_CREDIT,
    IMS_ITEM_TYPE_THIRD_SCHEDULE_NEW,
    IMS_PAYMENT_MODE_CASH,
    IMS_PAYMENT_MODE_MAP,
    IMS_PAYMENT_MODE_MIXED,
    IMS_PCT_CODE_MAX_LENGTH,
    IMS_REFUSIN_MAX_LENGTH,
    IMS_USIN_MAX_LENGTH,
    INVOICE_TYPE_CREDIT_NOTE,
    INVOICE_TYPE_DEBIT_NOTE,
)
from .payload import _money, _number, _number_qty, check_fiscal_lines_match_charge

# Invoice DateTime is reported in Pakistan business time (the spec's samples
# are naive local timestamps and sales are reconciled in branch hours).
# Pakistan has no DST and is fixed at UTC+05:00.
IMS_BUSINESS_TIMEZONE = ZoneInfo("Asia/Karachi")


def resolve_usin(invoice):
    """Client-side unique sale id (USIN varchar(50), compulsory).

    The fiscal invoice ``uuid`` is issued when the invoice is issued and is
    globally unique, so the same sale can never be fiscalized under two USINs.
    """
    usin = (invoice.uuid or invoice.invoice_number or str(invoice.pk)).strip()
    return usin[:IMS_USIN_MAX_LENGTH]


def resolve_payment_mode(order):
    """Map tendered payments onto the IMS PaymentMode enum.

    Tender sources, in order of authority:
    1. ``order.tenders`` — canonical ``payments.TenderedPayment`` rows posted
       by ``settle_order`` at checkout (the real money movement);
    2. ``order.payments`` — legacy ``pos.Payment`` rows;
    3. ``order.payment_method`` — the checkout header method (single tender).

    Mixed (5) is used whenever more than one distinct payment method was
    tendered, exactly as the spec requires ("Use Mixed payment mode in case of
    more than 1 payment method like cash + card").
    """
    methods = []
    if order is not None:
        tenders = getattr(order, "tenders", None)
        if tenders is not None:
            methods = [t.tender_type for t in tenders.all()]
        if not methods:
            payments = getattr(order, "payments", None)
            if payments is not None:
                methods = [p.payment_method for p in payments.all()]
        if not methods and getattr(order, "payment_method", ""):
            methods = [order.payment_method]
    distinct = set(methods)
    if len(distinct) > 1:
        return IMS_PAYMENT_MODE_MIXED
    if distinct:
        return IMS_PAYMENT_MODE_MAP.get(next(iter(distinct)), IMS_PAYMENT_MODE_CASH)
    return IMS_PAYMENT_MODE_CASH


def _pct_code(profile, errors):
    """PCTCode varchar(8) — compulsory and never guessed (audit H7).

    An HS heading is not a Pakistan Custom Tariff code, so the platform
    requires the explicit PCT code on the product's FBR profile instead of
    deriving one from the HS code.
    """
    pct = (profile.pct_code or "").strip()
    if not pct:
        errors.append(
            f"Product '{profile.product.name}' requires an explicit PCT code — set pct_code on its "
            f"FBR product profile (up to {IMS_PCT_CODE_MAX_LENGTH} digits, e.g. 11001010)."
        )
        return ""
    if not pct.isdigit() or len(pct) > IMS_PCT_CODE_MAX_LENGTH:
        errors.append(
            f"Product '{profile.product.name}' has an invalid PCT code '{pct}' "
            f"(must be up to {IMS_PCT_CODE_MAX_LENGTH} digits, e.g. 11001010)."
        )
    return pct


def _buyer_fields(invoice):
    """Buyer fields are all Optional in the IMS model — best effort, no errors."""
    customer = invoice.customer or (invoice.order.customer if invoice.order else None)
    if customer is None:
        return "", "", "", ""
    profile = getattr(customer, "fbr_profile", None)
    name = (profile.registered_name if profile and profile.registered_name else customer.name) or ""
    ntn = cnic = ""
    raw = (profile.ntn_cnic if profile and profile.is_active else "") or ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == IMS_BUYER_CNIC_LENGTH:
        cnic = digits
    elif digits:
        ntn = digits[:IMS_BUYER_NTN_MAX_LENGTH]
    phone = "".join(ch for ch in (customer.phone or "") if ch.isdigit())[:IMS_BUYER_PHONE_MAX_LENGTH]
    return name[:150], ntn, cnic, phone


def _ims_item_type(di_invoice_type, third_schedule):
    """Item-level InvoiceType: 1 New / 3 Credit, 11/12 for 3rd Schedule goods."""
    if di_invoice_type == INVOICE_TYPE_CREDIT_NOTE:
        return IMS_ITEM_TYPE_THIRD_SCHEDULE_CREDIT if third_schedule else IMS_ITEM_TYPE_CREDIT
    return IMS_ITEM_TYPE_THIRD_SCHEDULE_NEW if third_schedule else IMS_ITEM_TYPE_NEW


def _invoice_datetime(invoice):
    """Spec-format local business timestamp (audit H6)."""
    issued_at = invoice.created_at or timezone.now()
    if timezone.is_naive(issued_at):
        issued_at = timezone.make_aware(issued_at, timezone.utc)
    local_dt = issued_at.astimezone(IMS_BUSINESS_TIMEZONE)
    if invoice.issue_date:
        local_dt = local_dt.replace(
            year=invoice.issue_date.year, month=invoice.issue_date.month, day=invoice.issue_date.day
        )
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")


def build_ims_invoice_payload(
    invoice,
    *,
    config,
    di_invoice_type=2,
    ref_usin="",
):
    """Return the IMS JSON document for *invoice*.

    Fiscal monetary values are read exclusively from FiscalInvoiceLine
    snapshots created by the fiscal service.

    This function must not recalculate discounts, taxes, or totals.
    """
    errors = []

    ims_invoice_type = IMS_INVOICE_TYPE_FROM_DI.get(
        int(di_invoice_type) if di_invoice_type else 2,
        IMS_INVOICE_TYPE_NEW,
    )

    order = invoice.order

    pos_id = getattr(
        config,
        "pos_registration_number",
        None,
    )

    if not pos_id:
        errors.append(
            "The FBR configuration has no POS registration number (POSID) "
            "— register the POS on eFBR (Registration > POS Client "
            "Registration) and store the issued number."
        )

    usin = resolve_usin(invoice)

    ref_usin = (
        (ref_usin or "").strip()
        [:IMS_REFUSIN_MAX_LENGTH]
    )

    if ims_invoice_type in (2, 3) and not ref_usin:
        errors.append(
            "A debit/credit note needs the RefUSIN of the original sale "
            "— pass invoice_ref_no (RefUSIN) with the submit request."
        )

    lines = list(
        invoice.lines.all().order_by("line_number")
    )

    if not lines:
        errors.append(
            "The fiscal invoice has no fiscal lines."
        )

    items = []

    for line in lines:
        snapshot = line.fbr_snapshot or {}

        pct = (
            snapshot.get("pct_code") or ""
        ).strip()

        if not pct:
            errors.append(
                f"Product '{line.product_name}' requires an explicit "
                "PCT code — the fiscal snapshot does not contain one."
            )
            continue

        if (
            not pct.isdigit()
            or len(pct) > IMS_PCT_CODE_MAX_LENGTH
        ):
            errors.append(
                f"Product '{line.product_name}' has an invalid PCT code "
                f"'{pct}' (must be up to "
                f"{IMS_PCT_CODE_MAX_LENGTH} digits, e.g. 11001010)."
            )

        product_code = (
            snapshot.get("product_code")
            or line.product_sku
            or str(line.source_product_id or "")
        )

        tax_rate = Decimal(
            snapshot.get(
                "sales_tax_rate",
                "0",
            ) or "0"
        )

        items.append(
            {
                "ItemCode": (
                    product_code
                    or ""
                )[:IMS_ITEM_CODE_MAX_LENGTH],

                "ItemName": (
                    line.product_name
                    or ""
                )[:IMS_ITEM_NAME_MAX_LENGTH],

                "PCTCode": pct,

                "Quantity": _number_qty(
                    Decimal(line.quantity or 0)
                ),

                "TaxRate": float(tax_rate),

                "SaleValue": _number(
                    _money(line.taxable_amount)
                ),

                "Discount": _number(
                    _money(line.discount)
                ),

                "FurtherTax": _number(
                    _money(line.further_tax)
                ),

                "TaxCharged": _number(
                    _money(line.sales_tax)
                ),

                "TotalAmount": _number(
                    _money(line.total_amount)
                ),

                "InvoiceType": _ims_item_type(
                    int(di_invoice_type or 2),
                    bool(
                        snapshot.get(
                            "third_schedule",
                            False,
                        )
                    ),
                ),

                "RefUSIN": ref_usin or None,
            }
        )

    total_sale_value = _money(
        sum(
            (
                _money(line.taxable_amount)
                for line in lines
            ),
            Decimal("0"),
        )
    )

    total_tax_charged = _money(
        sum(
            (
                _money(line.sales_tax)
                for line in lines
            ),
            Decimal("0"),
        )
    )

    total_further_tax = _money(
        sum(
            (
                _money(line.further_tax)
                for line in lines
            ),
            Decimal("0"),
        )
    )

    total_discount = _money(
        sum(
            (
                _money(line.discount)
                for line in lines
            ),
            Decimal("0"),
        )
    )

    total_quantity = sum(
        (
            Decimal(line.quantity or 0)
            for line in lines
        ),
        Decimal("0"),
    )

    total_bill_amount = _money(
        sum(
            (
                _money(line.total_amount)
                for line in lines
            ),
            Decimal("0"),
        )
    )

    buyer_name, buyer_ntn, buyer_cnic, buyer_phone = (
        _buyer_fields(invoice)
    )

    payload = {
        "InvoiceNumber": "",
        "POSID": int(pos_id) if pos_id else None,
        "USIN": usin,
        "RefUSIN": ref_usin or None,
        "DateTime": _invoice_datetime(invoice),
        "BuyerName": buyer_name,
        "BuyerNTN": buyer_ntn,
        "BuyerCNIC": buyer_cnic,
        "BuyerPhoneNumber": buyer_phone,

        "TotalSaleValue": _number(
            total_sale_value
        ),

        "TotalTaxCharged": _number(
            total_tax_charged
        ),

        "TotalQuantity": _number_qty(
            total_quantity
        ),

        "Discount": _number(
            total_discount
        ),

        "FurtherTax": _number(
            total_further_tax
        ),

        "TotalBillAmount": _number(
            total_bill_amount
        ),

        "PaymentMode": resolve_payment_mode(
            order
        ),

        "InvoiceType": ims_invoice_type,

        "Items": items,
    }

    check_fiscal_lines_match_charge(invoice, errors)
    if errors:
        from .payload import FBRValidationError

        raise FBRValidationError(errors)

    return payload


__all__ = ["build_ims_invoice_payload", "resolve_payment_mode", "resolve_usin"]
