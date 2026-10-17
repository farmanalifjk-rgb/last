from decimal import Decimal
from django.conf import settings
from django.db import models


# ───────────────────────── Variant detail ─────────────────────────
class ProductVariant(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """A concrete sellable variant of a Product (combination of attribute values)."""
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="variants_detail")
    sku = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  # override
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    image = models.ImageField(upload_to="products/variants/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "sku"], name="unique_variant_sku", condition=~models.Q(sku="")),
            models.UniqueConstraint(fields=["product", "barcode"], name="unique_variant_barcode", condition=~models.Q(barcode="")),
        ]


class ProductVariantAttribute(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=100)   # e.g. "Color"
    value = models.CharField(max_length=100)  # e.g. "Red"

    class Meta:
        constraints = [models.UniqueConstraint(fields=["variant", "name"], name="unique_variant_attr_name")]


# ───────────────────────── Bundles ─────────────────────────
class ProductBundle(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STRATEGY_FIXED = "fixed"
    STRATEGY_SUM = "sum"
    STRATEGY_DISCOUNT = "discount"
    STRATEGY_CHOICES = [
        (STRATEGY_FIXED, "Fixed price"),
        (STRATEGY_SUM, "Sum of components"),
        (STRATEGY_DISCOUNT, "Discount off sum"),
    ]

    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="bundles/", blank=True, null=True)
    price_strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES, default=STRATEGY_SUM)
    fixed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def computed_price(self):
        total = Decimal("0")
        for c in self.components.all():
            source_price = c.variant.price if c.variant and c.variant.price is not None else (c.variant.product.sales_price if c.variant else c.product.sales_price)
            total += (c.override_price or Decimal("0")) * c.quantity if c.override_price is not None else (source_price * c.quantity)
        if self.price_strategy == self.STRATEGY_FIXED:
            return self.fixed_price or total
        if self.price_strategy == self.STRATEGY_DISCOUNT:
            return total * (Decimal("1") - self.discount_percent / Decimal("100"))
        return total


class BundleComponent(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    bundle = models.ForeignKey(ProductBundle, on_delete=models.CASCADE, related_name="components")
    product = models.ForeignKey("pos.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="bundle_components")
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1"))
    override_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(product__isnull=False, variant__isnull=True) | models.Q(product__isnull=True, variant__isnull=False)),
                name="bundle_component_requires_one_catalog_source",
            ),
        ]


# ───────────────────────── Serial / IMEI tracking ─────────────────────────
class SerialNumber(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_IN_STOCK = "in_stock"
    STATUS_SOLD = "sold"
    STATUS_RETURNED = "returned"
    STATUS_REPLACED = "replaced"
    STATUS_IN_REPAIR = "in_repair"
    STATUS_CHOICES = [
        (STATUS_IN_STOCK, "In stock"), (STATUS_SOLD, "Sold"),
        (STATUS_RETURNED, "Returned"), (STATUS_REPLACED, "Replaced"),
        (STATUS_IN_REPAIR, "In repair"),
    ]

    product = models.ForeignKey("pos.Product", on_delete=models.PROTECT, related_name="serials")
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT)
    batch = models.ForeignKey("catalog.Batch", null=True, blank=True, on_delete=models.SET_NULL, related_name="serials")
    serial_number = models.CharField(max_length=100)  # IMEI / serial
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IN_STOCK)
    purchased_at = models.DateTimeField(null=True, blank=True)   # when received
    sold_at = models.DateTimeField(null=True, blank=True)
    sold_in_order = models.ForeignKey("pos.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="serials_sold")
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    warranty_months = models.PositiveIntegerField(default=0)
    warranty_expires = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "serial_number"], name="unique_product_serial")]
        ordering = ["-created_at"]


# ───────────────────────── Batch / Lot tracking ─────────────────────────
class Batch(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Lot/batch of a product with manufacturing & expiry dates (FEFO)."""
    product = models.ForeignKey("pos.Product", on_delete=models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=100)
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    remaining_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    manufacturing_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    supplier = models.ForeignKey("pos.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="batches")
    is_recalled = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "batch_number"], name="unique_product_batch")]
        ordering = ["expiry_date", "-created_at"]  # FEFO-friendly default

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.expiry_date is not None and self.expiry_date < timezone.now().date()


class BatchMovement(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Allocation of a batch to an order/purchase/transfer."""
    KIND_SALE = "sale"
    KIND_PURCHASE = "purchase"
    KIND_TRANSFER = "transfer"
    KIND_RETURN = "return"
    KIND_ADJUSTMENT = "adjustment"
    KIND_CHOICES = [(KIND_SALE, "Sale"), (KIND_PURCHASE, "Purchase"),
                    (KIND_TRANSFER, "Transfer"), (KIND_RETURN, "Return"),
                    (KIND_ADJUSTMENT, "Adjustment")]
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="movements")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    order = models.ForeignKey("pos.Order", null=True, blank=True, on_delete=models.SET_NULL)
    reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


# ───────────────────────── Product media ─────────────────────────
class ProductMedia(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    KIND_IMAGE = "image"
    KIND_VIDEO = "video"
    KIND_360 = "360"
    KIND_CHOICES = [(KIND_IMAGE, "Image"), (KIND_VIDEO, "Video"), (KIND_360, "360")]

    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="media")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_IMAGE)
    file = models.FileField(upload_to="products/media/")
    caption = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="one_primary_product_media",
            ),
        ]
