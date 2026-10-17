from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q

from pos.models import Order, OrderItem, Product
from .models import ProductTaxAssignment, TaxRate, TaxExemption, TaxBreakdown


class TaxConfigurationError(ValueError):
    """A tenant's active tax rules cannot be resolved unambiguously."""


def _compound_is_explicit(rates):
    """Multiple selected rates are allowed only as an explicitly cascading set."""
    return len(rates) <= 1 or all(rate.compound_style == TaxRate.COMPOUND_COMPOUND for rate in rates)


def _select_rate_set(rates, *, description, allow_flat=False):
    rates = list(rates)
    if len(rates) > 1 and any(rate.rate == 0 for rate in rates):
        codes = ", ".join(sorted(rate.code for rate in rates))
        raise TaxConfigurationError(
            f"Ambiguous tax configuration for {description}: zero-rated/exempt treatments "
            f"cannot be combined with other rates ({codes}). Select one treatment."
        )
    styles = {rate.compound_style for rate in rates}
    if len(rates) > 1 and not _compound_is_explicit(rates) and not (allow_flat and styles == {TaxRate.COMPOUND_FLAT}):
        codes = ", ".join(sorted(rate.code for rate in rates))
        raise TaxConfigurationError(
            f"Ambiguous tax configuration for {description}: {codes} are mutually exclusive. "
            "Assign exactly one treatment, configure explicit flat product assignments, or mark every rate compound."
        )
    if len(rates) > 1 and len({rate.mode for rate in rates}) > 1:
        raise TaxConfigurationError(
            f"Ambiguous tax configuration for {description}: combined rates must all use the same inclusive/exclusive mode."
        )
    if len(rates) > 1 and rates[0].mode == TaxRate.MODE_INCLUSIVE:
        raise TaxConfigurationError(
            f"Ambiguous tax configuration for {description}: multiple inclusive rates cannot be combined; select one inclusive treatment."
        )
    return rates


def _active_rates_for(product, customer=None):
    """Resolve one statutory treatment, or an explicitly cascading tax set.

    Precedence is deterministic: explicit product assignments, then a
    product-scoped rate, then a category-scoped rate, then unscoped defaults
    (``applies_to_all=True``). A more specific tier completely overrides less
    specific tiers. Multiple assigned product rates are an explicit combination:
    all-flat assignments add independently on the base; all-compound assignments
    cascade. Unassigned scope/default tiers require every selected rate to be
    explicitly compound. Zero/exempt rates never combine with another rate.
    """
    tenant_id = product.tenant_id
    active_rates = list(
        TaxRate.objects.filter(tenant_id=tenant_id, is_active=True)
        .select_related("product", "category")
        .order_by("priority", "id")
    )
    assignments = list(
        ProductTaxAssignment.objects.filter(product_id=product.id, is_active=True)
        .select_related("tax_rate", "product")
        .order_by("id")
    )
    for assignment in assignments:
        if assignment.tenant_id != tenant_id or assignment.product.tenant_id != tenant_id or assignment.tax_rate.tenant_id != tenant_id:
            raise TaxConfigurationError("A product tax assignment crosses tenant boundaries; correct the assignment before checkout.")
    assigned_ids = {assignment.tax_rate_id for assignment in assignments}
    rates_by_id = {rate.id: rate for rate in active_rates}

    if assignments:
        inactive_assigned = [assignment.tax_rate.code for assignment in assignments if assignment.tax_rate_id not in rates_by_id]
        if inactive_assigned:
            raise TaxConfigurationError(
                "An active product tax assignment references an inactive tax rate: "
                + ", ".join(sorted(inactive_assigned))
                + ". Activate or deactivate the assignment before checkout."
            )
        candidates = [rate for rate in active_rates if rate.id in assigned_ids]
        description = f"product {product.id} assignments"
        selected = _select_rate_set(candidates, description=description, allow_flat=True)
    else:
        product_rates = [rate for rate in active_rates if rate.product_id == product.id]
        category_rates = [rate for rate in active_rates if rate.product_id is None and rate.category_id == product.category_id and product.category_id is not None]
        for rate in product_rates:
            if rate.product.tenant_id != tenant_id:
                raise TaxConfigurationError(f"Tax rate {rate.code} references a product in another tenant.")
        for rate in category_rates:
            if rate.category.tenant_id != tenant_id:
                raise TaxConfigurationError(f"Tax rate {rate.code} references a category in another tenant.")
        default_rates = [rate for rate in active_rates if rate.product_id is None and rate.category_id is None and rate.applies_to_all]
        if product_rates:
            selected = _select_rate_set(product_rates, description=f"product {product.id}")
        elif category_rates:
            selected = _select_rate_set(category_rates, description=f"category {product.category_id}")
        else:
            selected = _select_rate_set(default_rates, description=f"tenant {tenant_id} default rates")

    invalid_rates = [rate for rate in selected if not Decimal("0") <= rate.rate <= Decimal("1")]
    if invalid_rates:
        details = ", ".join(f"{rate.code}={rate.rate}" for rate in invalid_rates)
        raise TaxConfigurationError(
            f"Invalid tax-rate fraction for {details}; active rates must be between 0 and 1. "
            "Review and repair the configuration before checkout."
        )

    selected_ids = {rate.id for rate in selected}
    exempt_ids = set()
    exemptions = TaxExemption.objects.filter(tenant_id=tenant_id, is_active=True)
    product_or_category_exemptions = Q(scope=TaxExemption.SCOPE_PRODUCT, product_id=product.id)
    if product.category_id is not None:
        product_or_category_exemptions |= Q(scope=TaxExemption.SCOPE_CATEGORY, category_id=product.category_id)
    if customer is not None and customer.tenant_id == tenant_id:
        exemptions = exemptions.filter(
            Q(scope=TaxExemption.SCOPE_CUSTOMER, customer_id=customer.id) | product_or_category_exemptions
        )
    else:
        exemptions = exemptions.filter(product_or_category_exemptions)
    for exemption in exemptions:
        if exemption.tax_rate_id is None:
            exempt_ids.update(selected_ids)
        elif exemption.tax_rate_id in selected_ids:
            exempt_ids.add(exemption.tax_rate_id)
    selected = [rate for rate in selected if rate.id not in exempt_ids]
    return selected


def compute_line_tax(product, line_subtotal, customer=None):
    """Return line tax rows using decimal-fraction rates (17% is ``0.1700``).

    Amounts and taxable bases are rounded to currency precision per rate. This
    keeps quote, persisted breakdown, order totals, payment, and receipt in
    agreement, including inclusive and cascading taxes.
    """
    rates = _active_rates_for(product, customer)
    base = money(line_subtotal)
    out = []
    running = base
    flat_amounts = None
    if len(rates) > 1 and all(rate.compound_style == TaxRate.COMPOUND_FLAT for rate in rates):
        exact_amounts = [base * rate.rate for rate in rates]
        if all(amount >= 0 for amount in exact_amounts):
            flat_amounts = _round_flat_components(exact_amounts)
    for index, rate in enumerate(rates):
        if rate.mode == TaxRate.MODE_INCLUSIVE:
            taxable = base / (Decimal("1") + rate.rate)
            amount = base - taxable
        else:
            taxable = running if rate.compound_style == TaxRate.COMPOUND_COMPOUND else base
            amount = flat_amounts[index] if flat_amounts is not None else taxable * rate.rate
        taxable = money(taxable)
        amount = money(amount)
        out.append({"rate_id": rate.id, "code": rate.code, "rate": str(rate.rate), "mode": rate.mode,
                    "taxable": str(taxable), "amount": str(amount)})
        if rate.compound_style == TaxRate.COMPOUND_COMPOUND:
            running = running + amount
    return out


MONEY = Decimal("0.01")


def money(value):
    return Decimal(value or 0).quantize(MONEY, rounding=ROUND_HALF_UP)


def _round_flat_components(exact_amounts):
    """Round an additive flat set once, then apportion cents to its breakdown rows."""
    target = money(sum(exact_amounts, Decimal("0")))
    rows = [amount.quantize(MONEY, rounding=ROUND_DOWN) for amount in exact_amounts]
    cents_left = int((target - sum(rows, Decimal("0"))) / MONEY)
    ranking = sorted(
        range(len(rows)),
        key=lambda index: exact_amounts[index] - rows[index],
        reverse=True,
    )
    for index in ranking[:cents_left]:
        rows[index] += MONEY
    return rows


def allocate_order_discount(line_values, discount):
    """Split order discount proportionally; last line absorbs rounding remainder."""
    line_values = [money(value) for value in line_values]
    total = sum(line_values, Decimal("0"))
    discount = money(discount)
    if not line_values:
        return []
    if discount <= 0 or total <= 0:
        return [Decimal("0.00")] * len(line_values)
    allocations = []
    allocated = Decimal("0.00")
    for value in line_values[:-1]:
        share = money(discount * value / total)
        allocations.append(share)
        allocated += share
    allocations.append(money(discount - allocated))
    return allocations


def amount_added_to_price(tax_rows):
    """Tax charged on top of the entered price; inclusive tax is already paid."""
    return sum(
        (Decimal(row["amount"]) for row in tax_rows if row.get("mode") != TaxRate.MODE_INCLUSIVE),
        Decimal("0"),
    )


@transaction.atomic
def compute_order_tax(order, customer=None):
    """Compute and persist draft-order tax; never recalculate a historical sale."""
    original_order = order
    order = Order.objects.select_for_update().get(pk=order.pk, tenant_id=order.tenant_id)
    if order.status != "draft":
        raise ValueError("Tax can only be recomputed for a draft order; paid order tax is immutable.")
    TaxBreakdown.objects.filter(order=order).delete()
    total_tax = Decimal("0.00")
    added_tax = Decimal("0.00")
    items = list(order.items.all().order_by("id"))
    allocations = allocate_order_discount([item.subtotal for item in items], order.discount)
    for item, line_discount in zip(items, allocations):
        rows = compute_line_tax(item.product, money(item.subtotal) - line_discount, customer)
        line_tax = sum((Decimal(row["amount"]) for row in rows), Decimal("0.00"))
        total_tax += line_tax
        added_tax += amount_added_to_price(rows)
        for row in rows:
            TaxBreakdown.objects.create(
                tenant=order.tenant, order=order, order_item=item, tax_rate_id=row["rate_id"],
                tax_rate_code=row["code"], rate=Decimal(row["rate"]),
                taxable_amount=Decimal(row["taxable"]), tax_amount=Decimal(row["amount"]), mode=row["mode"],
            )
    order.tax = money(total_tax)
    order.total = money(Decimal(order.subtotal) - Decimal(order.discount) + added_tax)
    order.save(update_fields=["tax", "total"])
    original_order.tax = order.tax
    original_order.total = order.total
    return order.tax


def tax_report(period_start, period_end, tenant):
    """Aggregate collected tax by rate code over a date range."""
    qs = TaxBreakdown.objects.filter(tenant=tenant, order__created_at__date__gte=period_start,
                                     order__created_at__date__lte=period_end,
                                     order__status__in=["paid", "partially_refunded"])
    by_code = {}
    total_taxable = Decimal("0")
    total_tax = Decimal("0")
    for row in qs:
        key = row.tax_rate_code or "UNKNOWN"
        by_code.setdefault(key, {"taxable": Decimal("0"), "tax": Decimal("0"), "rate": str(row.rate)})
        by_code[key]["taxable"] += row.taxable_amount
        by_code[key]["tax"] += row.tax_amount
        total_taxable += row.taxable_amount
        total_tax += row.tax_amount
    return {
        "period_start": str(period_start),
        "period_end": str(period_end),
        "total_taxable": str(total_taxable),
        "total_tax_collected": str(total_tax),
        "by_rate": [{"code": code, "rate": value["rate"], "taxable": str(value["taxable"]),
                     "tax": str(value["tax"])} for code, value in by_code.items()],
    }
