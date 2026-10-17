from decimal import Decimal
from django.conf import settings
from django.db import models


class StockTransfer(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_DRAFT = "draft"
    STATUS_IN_TRANSIT = "in_transit"
    STATUS_RECEIVED = "received"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_IN_TRANSIT, "In transit"),
                      (STATUS_RECEIVED, "Received"), (STATUS_CANCELLED, "Cancelled")]
    transfer_number = models.CharField(max_length=30)
    source_warehouse = models.ForeignKey('enterprise.Warehouse', on_delete=models.PROTECT, related_name="transfers_out")
    destination_warehouse = models.ForeignKey('enterprise.Warehouse', on_delete=models.PROTECT, related_name="transfers_in")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    shipped_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="received_inventory_transfers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "transfer_number"], name="unique_tenant_stock_transfer_number")]


class StockTransferItem(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("pos.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    received_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))


class PutAwayRule(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Rules to auto-assign received goods to bins (by category, supplier, ABC class)."""
    STRATEGY_ABC = "abc"
    STRATEGY_CATEGORY = "category"
    STRATEGY_FIXED = "fixed"
    STRATEGY_CHOICES = [(STRATEGY_ABC, "By ABC class"), (STRATEGY_CATEGORY, "By category"), (STRATEGY_FIXED, "Fixed bin")]
    warehouse = models.ForeignKey('enterprise.Warehouse', on_delete=models.CASCADE, related_name="putaway_rules")
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES, default=STRATEGY_FIXED)
    category = models.ForeignKey("pos.Category", null=True, blank=True, on_delete=models.SET_NULL)
    abc_class = models.CharField(max_length=1, blank=True)  # A/B/C
    target_bin = models.ForeignKey('inventory.BinLocation', null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PutAwayTask(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_PENDING = "pending"
    STATUS_DONE = "done"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_DONE, "Done"), (STATUS_SKIPPED, "Skipped")]
    warehouse = models.ForeignKey('enterprise.Warehouse', on_delete=models.CASCADE, related_name="putaway_tasks")
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    suggested_bin = models.ForeignKey('inventory.BinLocation', null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reference = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class BinReplenishmentTask(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Move stock from bulk/reserve bins to pick-face bins when they run low."""
    STATUS_OPEN = "open"
    STATUS_DONE = "done"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_DONE, "Done")]
    warehouse = models.ForeignKey('enterprise.Warehouse', on_delete=models.CASCADE, related_name="replenishment_tasks")
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE)
    from_bin = models.ForeignKey('inventory.BinLocation', related_name="replenish_out", null=True, blank=True, on_delete=models.SET_NULL)
    to_bin = models.ForeignKey('inventory.BinLocation', related_name="replenish_in", null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
