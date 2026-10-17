from decimal import Decimal

from django.conf import settings
from django.db import models


class SupplierContact(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    supplier = models.ForeignKey("pos.Supplier", on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier"],
                condition=models.Q(is_primary=True),
                name="one_primary_contact_per_supplier",
            ),
        ]


class GoodsReceipt(models.Model):
    """An immutable, completed receipt of goods against a purchase order."""

    STATUS_RECEIVED = "received"
    STATUS_CHOICES = [(STATUS_RECEIVED, "Received")]

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    purchase_order = models.ForeignKey("pos.PurchaseOrder", on_delete=models.PROTECT, related_name="receipts")
    receipt_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    supplier_invoice_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RECEIVED)
    received_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_at", "-id"]


class GoodsReceiptLine(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    purchase_order_item = models.ForeignKey("pos.PurchaseOrderItem", on_delete=models.PROTECT, related_name="receipt_lines")
    batch = models.ForeignKey("catalog.Batch", null=True, blank=True, on_delete=models.SET_NULL, related_name="receipt_lines")
    quantity_ordered = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    quantity_received = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    quantity_accepted = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    quantity_rejected = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    rejection_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity_received__gt=0), name="receipt_line_received_positive"),
            models.CheckConstraint(condition=models.Q(quantity_accepted__gte=0), name="receipt_line_accepted_nonnegative"),
            models.CheckConstraint(condition=models.Q(quantity_rejected__gte=0), name="receipt_line_rejected_nonnegative"),
        ]


class PurchaseReturn(models.Model):
    """Supplier return workflow; stock is changed only when a draft is processed."""

    STATUS_DRAFT = "draft"
    STATUS_RETURNED = "returned"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_RETURNED, "Returned"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    purchase_order = models.ForeignKey("pos.PurchaseOrder", on_delete=models.PROTECT, related_name="supplier_returns")
    return_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    supplier_credit_note = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="processed_supplier_returns")

    class Meta:
        ordering = ["-created_at", "-id"]


class PurchaseReturnLine(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name="lines")
    purchase_order_item = models.ForeignKey("pos.PurchaseOrderItem", on_delete=models.PROTECT, related_name="return_lines")
    receipt_line = models.ForeignKey(GoodsReceiptLine, null=True, blank=True, on_delete=models.PROTECT, related_name="return_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="purchase_return_line_quantity_positive")]


class SupplierPortalToken(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    supplier = models.OneToOneField("pos.Supplier", on_delete=models.CASCADE, related_name="portal_token")
    token = models.CharField(max_length=64, unique=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
