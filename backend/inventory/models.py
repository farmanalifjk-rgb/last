from decimal import Decimal
from django.conf import settings
from django.db import models


class BinLocation(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Physical bin/shelf within a warehouse (zone > aisle > bin)."""
    warehouse = models.ForeignKey('enterprise.Warehouse', on_delete=models.CASCADE, related_name="bins")
    zone = models.CharField(max_length=60, blank=True)     # zone / area
    aisle = models.CharField(max_length=60, blank=True)
    rack = models.CharField(max_length=60, blank=True)
    bin = models.CharField(max_length=60, blank=True)
    code = models.CharField(max_length=100)               # full bin code e.g. A-12-3
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["warehouse", "code"], name="unique_bin_code")]
        ordering = ["code"]


class StockReservation(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Reserve stock for an order/park/layaway without deducting it."""
    STATUS_ACTIVE = "active"
    STATUS_RELEASED = "released"
    STATUS_FULFILLED = "fulfilled"
    STATUS_CHOICES = [(STATUS_ACTIVE, "Active"), (STATUS_RELEASED, "Released"), (STATUS_FULFILLED, "Fulfilled")]

    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="reservations")
    order = models.ForeignKey("pos.Order",null=True,blank=True,on_delete=models.CASCADE,related_name="stock_reservations",)    
    warehouse = models.ForeignKey('enterprise.Warehouse', null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations")
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    reserved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reference = models.CharField(max_length=100, blank=True)  # order / park id
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="inventory_reservation_quantity_positive")]


class CycleCount(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_DRAFT = "draft"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RECONCILED = "reconciled"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_IN_PROGRESS, "In progress"), (STATUS_RECONCILED, "Reconciled")]

    warehouse = models.ForeignKey('enterprise.Warehouse', null=True, blank=True, on_delete=models.SET_NULL, related_name="cycle_counts")
    reference = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class CycleCountLine(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    count = models.ForeignKey(CycleCount, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("pos.Product", on_delete=models.PROTECT)
    expected_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    counted_quantity = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    note = models.CharField(max_length=255, blank=True)


class ReorderRule(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Automatic reorder point + target stock per product/warehouse."""
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="reorder_rules")
    warehouse = models.ForeignKey('enterprise.Warehouse', null=True, blank=True, on_delete=models.CASCADE, related_name="reorder_rules")
    reorder_point = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    target_stock = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    supplier = models.ForeignKey("pos.Supplier", null=True, blank=True, on_delete=models.SET_NULL)
    auto_generate_po = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(reorder_point__gte=0) & models.Q(target_stock__gte=0), name="inventory_reorder_quantities_nonnegative"),
            models.CheckConstraint(condition=models.Q(target_stock__gte=models.F("reorder_point")), name="inventory_reorder_target_not_below_point"),
        ]


class ABCAnalysis(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Snapshot of ABC classification (Pareto) per product."""
    CLASS_A = "A"
    CLASS_B = "B"
    CLASS_C = "C"
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="abc_records")
    annual_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    cumulative_share = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0"))
    abc_class = models.CharField(max_length=1, choices=[(CLASS_A, "A"), (CLASS_B, "B"), (CLASS_C, "C")])
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-annual_value"]


class InventoryAgingSnapshot(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """How long stock has been sitting (aging buckets)."""
    product = models.ForeignKey("pos.Product", null=True, blank=True, on_delete=models.CASCADE, related_name="aging_snapshots")
    bucket = models.CharField(max_length=20)  # 0-30, 31-60, 61-90, 90+
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    captured_at = models.DateTimeField(auto_now_add=True)
