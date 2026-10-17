from decimal import Decimal
from django.db import models


class TaxRate(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    MODE_EXCLUSIVE = "exclusive"   # added on top of the price
    MODE_INCLUSIVE = "inclusive"   # already included in the price
    MODE_CHOICES = [(MODE_EXCLUSIVE, "Exclusive"), (MODE_INCLUSIVE, "Inclusive")]
    COMPOUND_FLAT = "flat"         # all rates sum then apply once
    COMPOUND_COMPOUND = "compound" # each rate applies on running total
    COMPOUND_CHOICES = [(COMPOUND_FLAT, "Flat (additive)"), (COMPOUND_COMPOUND, "Compound (cascading)")]
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20)
    rate = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0"))  # 0.13 = 13%
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_EXCLUSIVE)
    compound_style = models.CharField(max_length=10, choices=COMPOUND_CHOICES, default=COMPOUND_FLAT)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=0)  # lower applies first when compounding
    applies_to_all = models.BooleanField(default=True)
    # optional scope
    category = models.ForeignKey("pos.Category", null=True, blank=True, on_delete=models.SET_NULL)
    product = models.ForeignKey("pos.Product", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="unique_tax_code_per_tenant")]


class TaxExemption(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Customer or product-level exemption from a tax rate."""
    SCOPE_CUSTOMER = "customer"
    SCOPE_PRODUCT = "product"
    SCOPE_CATEGORY = "category"
    SCOPE_CHOICES = [(SCOPE_CUSTOMER, "Customer"), (SCOPE_PRODUCT, "Product"), (SCOPE_CATEGORY, "Category")]
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES)
    customer = models.ForeignKey("pos.Customer", null=True, blank=True, on_delete=models.CASCADE)
    product = models.ForeignKey("pos.Product", null=True, blank=True, on_delete=models.CASCADE)
    category = models.ForeignKey("pos.Category", null=True, blank=True, on_delete=models.CASCADE)
    tax_rate = models.ForeignKey(TaxRate, null=True, blank=True, on_delete=models.CASCADE,
                                 help_text="If blank, exempts from all tax rates")
    reason = models.CharField(max_length=255, blank=True)
    certificate_number = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TaxBreakdown(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Snapshot of computed tax for an order/line, for reporting + audits."""
    order = models.ForeignKey("pos.Order", on_delete=models.CASCADE, related_name="tax_breakdowns")
    order_item = models.ForeignKey("pos.OrderItem",null=True,blank=True,on_delete=models.CASCADE,related_name="tax_breakdowns",)
    tax_rate = models.ForeignKey(TaxRate, on_delete=models.SET_NULL, null=True, blank=True)
    tax_rate_code = models.CharField(max_length=20, blank=True)
    rate = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0"))
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    mode = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    


class TaxReport(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Aggregated tax collected over a period — for filing."""
    period_start = models.DateField()
    period_end = models.DateField()
    total_taxable = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_tax_collected = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    breakdown_json = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ProductTaxAssignment(models.Model):
    """Canonical association between a tenant product and an existing tax rule."""
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="tax_assignments")
    tax_rate = models.ForeignKey(TaxRate, on_delete=models.PROTECT, related_name="product_assignments")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "tax_rate"], name="unique_product_tax_assignment")]
