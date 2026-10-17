"""Builds the FBR DI API v1.12 JSON document for a fiscal invoice.

Field names and cardinality follow §§4.1/4.1.2 of the PRAL
Technical Documentation for DI API v1.12 (2025-07-24).
Monetary values are rounded as FBR documents:
 - totals/valueSalesExcludingST/salesTaxApplicable etc. → 2 dp
 - quantity → 4 dp (spec p11 quantity 1.0000)
Rate is emitted as string "18%" (ratE_DESC from 5.8).
UoM and saleType are emitted as description strings (5.6, 5.5).
HS code is dotted 0101.2100 (itemdesccode 5.3).
"""

from decimal import Decimal, ROUND_HALF_UP

from .constants import (
    ENVIRONMENT_SANDBOX,
    INVOICE_TYPE_CHOICES,
    INVOICE_TYPE_SALE,
    INVOICE_TYPE_STRINGS,
    BUYER_REGISTRATION_REGISTERED,
)

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


class FBRValidationError(Exception):
    """Raised when an invoice cannot be expressed as a valid FBR document."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _money(value):
    return Decimal(value or 0).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _quantity(value):
    return Decimal(value or 0).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def check_fiscal_lines_match_charge(invoice, errors):
    """The fiscal document must report exactly what the customer was charged.

    Fiscal lines are recomputed from FBR product profiles while the order was
    charged by the POS tax engine; they diverge when the rates differ, when a
    tax is price-inclusive, or when tax was charged on the pre-discount
    amount. Such an invoice is never sent: reporting a sale value or bill
    amount other than the one collected would misstate the sale to FBR.
    Invoices without a source order carry no charged amount to compare.
    """
    if not getattr(invoice, "order_id", None):
        return
    lines = list(invoice.lines.all())
    if not lines:
        return
    fiscal_sale_value = sum((_money(line.taxable_amount) for line in lines), Decimal("0"))
    fiscal_bill = sum((_money(line.total_amount) for line in lines), Decimal("0"))
    charged_sale_value = _money(invoice.subtotal) - _money(invoice.discount)
    charged_total = _money(invoice.total)
    if fiscal_sale_value != charged_sale_value or fiscal_bill != charged_total:
        errors.append(
            f"The fiscal lines (sale value {fiscal_sale_value}, bill {fiscal_bill}) do not match what the "
            f"customer was charged (sale value {charged_sale_value}, total {charged_total}). Align the "
            "product's FBR profile tax rate with the POS tax rate (and its inclusive/exclusive mode and "
            "discount treatment) before fiscalizing; nothing was sent to FBR."
        )


def _number(value):
    """JSON-serialisable 2-dp representation."""
    return float(_money(value))


def _number_qty(value):
    """Quantity as float with 4 dp."""
    return float(_quantity(value))


def _rate_str(rate: Decimal) -> str:
    """Format Decimal rate as PRAL expects: 18% , 5% , 0% etc."""
    # rate is Decimal e.g. 18.000 -> "18%"
    # Keep up to 3 dp but strip trailing zeros
    if rate is None:
        return "0%"
    d = Decimal(rate).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP).normalize()
    # normalize may use exponent, format as plain
    s = format(d, "f")
    return f"{s}%"



def _line_items(invoice, config, errors):
    """
    Serialize immutable FiscalInvoiceLine snapshots into the
    FBR DI API v1.12 item structure.

    IMPORTANT:
    No financial calculation belongs here.
    """

    lines = list(
        invoice.lines
        .select_related(
            "source_order_item",
            "source_product",
        )
        .order_by("line_number")
    )

    if not lines:
        errors.append(
            "The fiscal invoice has no fiscal lines."
        )
        return []

    items = []

    for line in lines:

        snapshot = line.fbr_snapshot or {}

        hs_code = snapshot.get("hs_code", "")
        uom_str = snapshot.get("uom", "")
        sale_type_str = snapshot.get("sale_type", "")
        sro_no = snapshot.get("sro_schedule_no", "")
        sale_type_id = snapshot.get(
            "transaction_type_code"
        )

        if not hs_code:
            errors.append(
                f"Fiscal line {line.line_number} has no "
                "historical HS code."
            )

        if not uom_str:
            errors.append(
                f"Fiscal line {line.line_number} has no "
                "historical UoM."
            )

        if not sale_type_str:
            errors.append(
                f"Fiscal line {line.line_number} has no "
                "historical sale type."
            )

        items.append({
            "hsCode": hs_code,

            "productDescription": (
                line.product_name
            ),

            "rate": _rate_str(
                Decimal(
                    snapshot.get(
                        "sales_tax_rate",
                        "0",
                    )
                )
            ),

            "uoM": uom_str,

            "quantity": _number_qty(
                line.quantity
            ),

            "totalValues": _number(
                line.total_amount
            ),

            "valueSalesExcludingST": _number(
                line.taxable_amount
            ),

            "fixedNotifiedValueOrRetailPrice": _number(
                line.fixed_notified_value_or_retail_price
            ),

            "salesTaxApplicable": _number(
                line.sales_tax
            ),

            "salesTaxWithheldAtSource": _number(
                line.sales_tax_withheld
            ),

            "extraTax": _number(
                line.extra_tax
            ),

            "furtherTax": _number(
                line.further_tax
            ),

            "sroScheduleNo": sro_no,

            "fedPayable": _number(
                line.fed_payable
            ),

            "discount": _number(
                line.discount
            ),

            "saleType": sale_type_str,

            "sroItemSerialNo": snapshot.get(
                "sro_item_serial_no",
                "",
            ),

            "_saleTypeId": sale_type_id,
        })

    return items


def _buyer_details(invoice, errors):
    customer = invoice.customer or (invoice.order.customer if invoice.order else None)
    if customer is None:
        errors.append("The invoice has no customer; FBR requires the buyer NTN/CNIC, name and address.")
        return "", "", "", "", ""
    profile = getattr(customer, "fbr_profile", None)
    # v1.12: buyerRegistrationType drives whether NTN may be blank
    reg_type = getattr(profile, "buyer_registration_type", BUYER_REGISTRATION_REGISTERED) if profile and profile.is_active else BUYER_REGISTRATION_REGISTERED
    ntn_cnic = profile.ntn_cnic if profile and profile.is_active else ""
    name = (profile.registered_name if profile and profile.registered_name else customer.name) or ""
    address = (profile.destination_address if profile and profile.destination_address else customer.address) or ""
    # province
    buyer_province = ""
    if profile and getattr(profile, "buyer_province", None):
        buyer_province = profile.buyer_province.code if hasattr(profile.buyer_province, "code") else str(profile.buyer_province)
    elif profile and getattr(profile, "buyer_province_text", ""):
        buyer_province = profile.buyer_province_text
    # If no profile province, try to infer from customer? keep blank to trigger error
    if not reg_type:
        reg_type = BUYER_REGISTRATION_REGISTERED
    # Validation per v1.12 table p10: buyerNTNCNIC Required (Optional in case of Unregistered), buyerBusinessName Required, buyerProvince Required, buyerAddress Required, buyerRegistrationType Required
    if reg_type == BUYER_REGISTRATION_REGISTERED and not ntn_cnic:
        errors.append(f"Customer '{customer.name}' has no FBR buyer profile with an NTN/CNIC (required for Registered).")
    if not name:
        errors.append("The buyer name is mandatory.")
    if not address:
        errors.append("The destination address is mandatory.")
    if not buyer_province:
        errors.append(f"Customer '{customer.name}' has no buyer province (v1.12 5.1 required).")
    if not reg_type:
        errors.append("The buyerRegistrationType is mandatory (Registered/Unregistered).")
    return ntn_cnic, name, address, buyer_province, reg_type


def _seller_details(config, errors):
    if not config.seller_ntn_cnic:
        errors.append("The FBR configuration has no seller NTN/CNIC.")
    if not config.seller_business_name:
        errors.append("The FBR configuration has no seller business name.")
    # seller province required p10
    seller_province = config.resolved_seller_province if hasattr(config, "resolved_seller_province") else ""
    if not seller_province:
        # fallback to province FK description
        if getattr(config, "seller_province", None):
            seller_province = config.seller_province.code
        # else error
        if not seller_province:
            errors.append("The FBR configuration has no seller province (v1.12 5.1 required).")
            seller_province = ""
    if not config.seller_address:
        errors.append("The FBR configuration has no seller address.")
    if not config.security_token:
        errors.append("The FBR configuration has no security token.")
    return seller_province


def build_invoice_payload(invoice, *, config, invoice_type=INVOICE_TYPE_SALE, invoice_ref_no="", scenario_id=None):
    """Return the v1.12 JSON document for *invoice*, or raise ``FBRValidationError``.

    invoice_type may be int 1-4 or string "Sale Invoice" etc. — int is mapped
    to the string PRAL expects via INVOICE_TYPE_STRINGS.
    invoice_ref_no is required only for debit/credit notes (p11).
    scenario_id is required for sandbox (p11) — defaults to config.scenario_id if not passed.
    """
    # Normalize invoice_type to string
    if isinstance(invoice_type, int):
        valid_ints = {value for value, _ in INVOICE_TYPE_CHOICES}
        if invoice_type not in valid_ints:
            raise FBRValidationError([f"Invoice type must be one of {sorted(valid_ints)} (int 1-4) or string Sale Invoice etc."])
        invoice_type_str = INVOICE_TYPE_STRINGS.get(invoice_type, "Sale Invoice")
        invoice_type_int = invoice_type
    elif isinstance(invoice_type, str):
        # Allow string directly — validate against reverse map values
        allowed_strs = set(INVOICE_TYPE_STRINGS.values())
        if invoice_type not in allowed_strs:
            raise FBRValidationError([f"Invoice type string must be one of {sorted(allowed_strs)}"])
        invoice_type_str = invoice_type
        # try to find int for debit check
        invoice_type_int = next((k for k, v in INVOICE_TYPE_STRINGS.items() if v == invoice_type_str), INVOICE_TYPE_SALE)
    else:
        raise FBRValidationError(["Invoice type must be int 1-4 or string 'Sale Invoice'"])

    errors = []
    seller_province = _seller_details(config, errors)
    ntn_cnic, buyer_name, destination_address, buyer_province, buyer_reg_type = _buyer_details(invoice, errors)
    items = _line_items(invoice, config, errors)

    # invoiceRefNo required only for debit note (p11: Required only in case of debit note)
    # We treat debit/credit both requiring ref. Check spec: p11 says debit note 22/28 digits, but we accept for both 3,4.
    from .constants import INVOICE_TYPE_DEBIT_NOTE, INVOICE_TYPE_CREDIT_NOTE
    is_debit_or_credit = invoice_type_int in (INVOICE_TYPE_DEBIT_NOTE, INVOICE_TYPE_CREDIT_NOTE)
    if is_debit_or_credit and not invoice_ref_no:
        # Try to pull from invoice.fbr_invoice_number or invoice_ref_no field if exists
        # Fallback to invoice.invoice_number as ref if debit? But spec says must be FBR DI number.
        errors.append("invoiceRefNo is required for debit/credit notes (v1.12 p11, 22/28-digit DI number).")

    check_fiscal_lines_match_charge(invoice, errors)
    if errors:
        raise FBRValidationError(errors)

    # Every line of one invoice is posted under a single sale type; FBR keys the
    # header on it, so a mixed basket has to be split into separate invoices.
    sale_types = {item.pop("_saleTypeId") for item in items}
    if len(sale_types) > 1:
        raise FBRValidationError([
            "All items of an invoice must share one sale type; this invoice mixes "
            f"{sorted(sale_types)}."
        ])

    # ScenarioId handling — Required for Sandbox only (p11)
    resolved_scenario = scenario_id if scenario_id is not None else getattr(config, "scenario_id", "") or ""
    if config.environment == ENVIRONMENT_SANDBOX and not resolved_scenario:
        raise FBRValidationError(["scenarioId is required for sandbox (v1.12 p11 §9). Set FBRConfiguration.scenario_id (e.g. SN001)."])

    payload = {
        "invoiceType": invoice_type_str,
        "invoiceDate": (invoice.issue_date or invoice.created_at.date()).isoformat(),
        "sellerNTNCNIC": config.seller_ntn_cnic,
        "sellerBusinessName": config.seller_business_name,
        "sellerProvince": seller_province,
        "sellerAddress": config.seller_address,
        "buyerNTNCNIC": ntn_cnic,
        "buyerBusinessName": buyer_name,
        "buyerProvince": buyer_province,
        "buyerAddress": destination_address,
        "buyerRegistrationType": buyer_reg_type,
        "invoiceRefNo": invoice_ref_no or "",
        "items": items,
    }
    # Only include scenarioId for sandbox per spec (prod sample omits it)
    if config.environment == ENVIRONMENT_SANDBOX:
        payload["scenarioId"] = resolved_scenario
    return payload


# Backwards compatibility: legacy v1.0 builder (used by old tests if needed)
def build_invoice_payload_legacy(invoice, *, config, invoice_type=INVOICE_TYPE_SALE):
    """Legacy v1.0 payload (bposId/total* etc.) — kept for reference/migration."""
    # This is the pre-v1.12 shape; not used for new posts but kept for audit.
    # To avoid duplication, we simply call the v1.12 builder and then map? For now
    # we reimplement minimally via the old logic stored in git history — here we
    # just raise to signal deprecation.
    raise NotImplementedError("Legacy v1.0 payload is deprecated; use build_invoice_payload for v1.12")
