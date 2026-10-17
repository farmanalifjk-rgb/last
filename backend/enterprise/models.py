"""Enterprise location and stock movement models.

These models intentionally keep stock by warehouse separate from Product's
legacy aggregate stock field. Existing installations keep working while the
application transitions screens and reports to location-aware inventory.
"""

from django.conf import settings
from django.db import models


class Warehouse(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    # Reuse the Store model already provided by models_settings.py rather than
    # defining a second conflicting Store model in this Django app.
    store = models.ForeignKey('system.Store', on_delete=models.CASCADE, related_name="warehouses", null=True, blank=True)
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="unique_tenant_warehouse_code")]

    def __str__(self):
        return f"{self.code} — {self.name}"


class WarehouseStock(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="stock_levels")
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="warehouse_stock")
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reorder_point = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bin_location = models.CharField(max_length=60, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["warehouse", "product"], name="unique_warehouse_product_stock")]


class WarehouseTransfer(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_DRAFT = "draft"
    STATUS_IN_TRANSIT = "in_transit"
    STATUS_RECEIVED = "received"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_IN_TRANSIT, "In transit"),
        (STATUS_RECEIVED, "Received"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    transfer_number = models.CharField(max_length=30)
    source_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="outgoing_transfers")
    destination_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="incoming_transfers")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    note = models.TextField(blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="requested_stock_transfers")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="received_stock_transfers")
    created_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["tenant", "transfer_number"], name="unique_tenant_enterprise_transfer_number")]


class WarehouseTransferItem(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    transfer = models.ForeignKey(WarehouseTransfer, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("pos.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    received_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["transfer", "product"], name="unique_transfer_product")]


