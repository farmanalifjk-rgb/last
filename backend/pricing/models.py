from decimal import Decimal
from django.db import models
from django.utils import timezone


class PriceList(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """A named price list (regional, currency, B2B, etc.)."""
    name = models.CharField(max_length=120)
    currency = models.CharField(max_length=10, default="USD")
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PriceListItem(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="price_list_items")
    variant = models.ForeignKey("catalog.ProductVariant", null=True, blank=True, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    min_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["price_list", "product", "variant", "min_quantity"], name="unique_pricelist_item")
        ]


class CustomerGroupPrice(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    customer_group = models.ForeignKey('system.CustomerGroup', on_delete=models.CASCADE, related_name="prices")
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="group_prices")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["customer_group", "product"], name="unique_group_price")]


class VolumeTier(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Buy X units, pay Y per unit (volume/tier pricing)."""
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="volume_tiers")
    min_quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["min_quantity"]


class TimeBasedPrice(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Happy hour / seasonal / day-part pricing."""
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="time_prices")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    weekdays = models.CharField(max_length=30, blank=True, help_text="Comma-separated 0-6 (Mon=0)")
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class BuyXGetY(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Buy X get Y (BOGO) promotion at the product level."""
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="buyx_gety")
    buy_quantity = models.PositiveIntegerField(default=1)
    get_quantity = models.PositiveIntegerField(default=1)
    get_product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="+", null=True, blank=True)
    get_percent_off = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100"))  # 100 = free
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
