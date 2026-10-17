"""Authoritative sell-price resolution for POS transactions."""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone


def resolve_unit_price(*, product, customer=None, quantity=Decimal("1")) -> Decimal:
    """Resolve a sell price with deterministic precedence.

    Precedence is customer-group price, active default price-list item, active
    time-based price, volume tier, then the product's base sales price.
    """
    quantity = Decimal(str(quantity))
    now = timezone.now()
    price = Decimal(product.sales_price)

    # Tenant-scoped: all pricing lookups are per-tenant (product.tenant determines scope)
    tenant_id = getattr(product, "tenant_id", None)
    if customer and customer.group_id:
        from pricing.models import CustomerGroupPrice

        group_price = (
            CustomerGroupPrice.objects.filter(
                tenant_id=tenant_id,
                customer_group_id=customer.group_id,
                product_id=product.id,
            )
            .order_by("id")
            .first()
        )
        if group_price:
            return Decimal(group_price.price)

    from pricing.models import PriceList, PriceListItem

    price_list = (
        PriceList.objects.filter(
            tenant_id=tenant_id,
            is_active=True,
            is_default=True,
        )
        .filter(valid_from__isnull=True) | PriceList.objects.filter(
            tenant_id=tenant_id,
            is_active=True,
            is_default=True,
            valid_from__lte=now,
        )
    )
    price_list = price_list.filter(valid_to__isnull=True) | price_list.filter(valid_to__gte=now)
    price_item = (
        PriceListItem.objects.filter(
            tenant_id=tenant_id,
            price_list__in=price_list,
            product_id=product.id,
            variant__isnull=True,
            min_quantity__lte=quantity,
        )
        .order_by("-min_quantity", "id")
        .first()
    )
    if price_item:
        price = Decimal(price_item.price)

    from pricing.models import TimeBasedPrice, VolumeTier

    today = now.date()
    current_time = now.time()
    time_price = (
        TimeBasedPrice.objects.filter(
            tenant_id=tenant_id,
            product_id=product.id,
            is_active=True,
        )
        .filter(valid_from__isnull=True) | TimeBasedPrice.objects.filter(
            tenant_id=tenant_id,
            product_id=product.id,
            is_active=True,
            valid_from__lte=today,
        )
    )
    time_price = time_price.filter(valid_to__isnull=True) | time_price.filter(valid_to__gte=today)
    time_price = time_price.filter(start_time__isnull=True) | time_price.filter(start_time__lte=current_time)
    time_price = time_price.filter(end_time__isnull=True) | time_price.filter(end_time__gte=current_time)
    time_price = time_price.order_by("id").first()
    if time_price:
        weekdays = [item.strip() for item in (time_price.weekdays or "").split(",") if item.strip()]
        if not weekdays or str(today.weekday()) in weekdays:
            price = Decimal(time_price.price)

    volume_tier = (
        VolumeTier.objects.filter(tenant_id=tenant_id, product_id=product.id, min_quantity__lte=quantity)
        .order_by("-min_quantity", "id")
        .first()
    )
    if volume_tier:
        price = Decimal(volume_tier.unit_price)

    return price.quantize(Decimal("0.01"))
