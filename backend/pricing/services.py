from decimal import Decimal
from django.utils import timezone

from .models import (
    PriceList, PriceListItem, CustomerGroupPrice, VolumeTier,
    TimeBasedPrice, BuyXGetY,
)


def _now():
    return timezone.now()


def resolve_price(*, product, customer=None, variant=None, quantity=Decimal("1"), price_list=None, at=None):
    """Apply rules in priority order; first match wins.
    Priority: time-based > buyXgetY(unit effect handled elsewhere) > volume tier >
    customer group > price list item > product sales_price.
    """
    now = at or _now()

    # 1. Time-based
    t = TimeBasedPrice.objects.filter(product=product, is_active=True).first()
    if t and _time_matches(t, now):
        return t.price

    # 2. Volume tier
    for tier in VolumeTier.objects.filter(product=product, min_quantity__lte=quantity).order_by("-min_quantity"):
        return tier.unit_price

    # 3. Customer group
    if customer and getattr(customer, "group_id", None):
        gp = CustomerGroupPrice.objects.filter(customer_group_id=customer.group_id, product=product).first()
        if gp:
            return gp.price

    # 4. Price list item
    if price_list:
        item = PriceListItem.objects.filter(price_list=price_list, product=product, variant=variant,
                                             min_quantity__lte=quantity).order_by("-min_quantity").first()
        if item:
            return item.price

    # 5. Base
    return getattr(variant, "price", None) or product.sales_price


def _time_matches(t, now):
    if t.valid_from and now < t.valid_from:
        return False
    if t.valid_to and now > t.valid_to:
        return False
    if t.weekdays:
        wd = str(now.weekday())
        if wd not in t.weekdays.split(","):
            return False
    if t.start_time and t.end_time:
        if not (t.start_time <= now.time() <= t.end_time):
            return False
    return True


def apply_buyx_gety(*, product, quantity):
    """Return list of (free_product, qty) granted for a given cart quantity."""
    out = []
    for rule in BuyXGetY.objects.filter(product=product, is_active=True):
        if rule.valid_from and _now() < rule.valid_from:
            continue
        if rule.valid_to and _now() > rule.valid_to:
            continue
        sets = quantity // (rule.buy_quantity + rule.get_quantity)
        if sets > 0:
            free = (rule.get_product or product)
            out.append((free, int(sets * rule.get_quantity)))
    return out