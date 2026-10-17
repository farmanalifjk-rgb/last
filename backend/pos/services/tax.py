"""Authoritative tax calculation for POS transactions."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def calculate_order_tax(*, subtotal: Decimal, discount: Decimal, tenant=None) -> Decimal:
    """Calculate tax from TaxSettings and its configured default tax (tenant-scoped)."""
    from system.models import TaxSettings

    settings = TaxSettings.load(tenant=tenant)
    if not settings.enable_taxes:
        return Decimal("0.00")

    tax = settings.default_tax
    # Ensure the default tax actually belongs to this tenant before using it
    if tax is not None and tenant is not None and getattr(tax, "tenant_id", None) != getattr(tenant, "id", None):
        tax = None
    if tax is None:
        from pos.models import Tax

        qs = Tax.objects.filter(is_active=True, is_default=True)
        if tenant is not None:
            qs = qs.filter(tenant=tenant)
        tax = qs.first()
    if tax is None:
        return Decimal("0.00")

    taxable = max(Decimal("0.00"), subtotal - discount)
    if tax.tax_type == "fixed":
        value = Decimal(tax.rate)
    else:
        value = taxable * Decimal(tax.rate) / Decimal("100")

    precision = max(int(settings.tax_precision or 2), 0)
    quantum = Decimal("1").scaleb(-precision)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)
