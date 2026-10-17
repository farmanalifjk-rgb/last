from decimal import Decimal
from django.conf import settings
from django.db import models


class ParkedOrder(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """A held/parked cart that can be resumed later."""
    STATUS_PARKED = "parked"
    STATUS_RESUMED = "resumed"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [(STATUS_PARKED, "Parked"), (STATUS_RESUMED, "Resumed"), (STATUS_EXPIRED, "Expired")]

    session = models.ForeignKey("pos.CashSession", on_delete=models.CASCADE, related_name="parked_orders")
    label = models.CharField(max_length=60, blank=True)   # "Table 5", customer name
    customer = models.ForeignKey("pos.Customer", null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict)              # full cart snapshot
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PARKED)
    parked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    parked_at = models.DateTimeField(auto_now_add=True)
    resumed_at = models.DateTimeField(null=True, blank=True)


class Layaway(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Partial-payment hold: customer pays deposit, balance due later."""
    STATUS_OPEN = "open"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_COMPLETED, "Completed"), (STATUS_CANCELLED, "Cancelled")]

    order = models.ForeignKey("pos.Order", on_delete=models.CASCADE, related_name="layaways")
    customer = models.ForeignKey("pos.Customer", null=True, blank=True, on_delete=models.SET_NULL)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LayawayPayment(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    layaway = models.ForeignKey(Layaway, on_delete=models.CASCADE, related_name="installments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20)
    paid_at = models.DateTimeField(auto_now_add=True)


class SplitBill(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Split an order into N shares (even or custom)."""
    order = models.ForeignKey("pos.Order", on_delete=models.CASCADE, related_name="splits")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    share_count = models.PositiveIntegerField(default=2)
    created_at = models.DateTimeField(auto_now_add=True)


class SplitBillShare(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    split = models.ForeignKey(SplitBill, on_delete=models.CASCADE, related_name="shares")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=20, blank=True)


class ExchangeOrder(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Customer exchanges item(s) for other item(s), with a net difference."""
    original_order = models.ForeignKey("pos.Order", on_delete=models.CASCADE, related_name="exchanges")
    returned_items = models.JSONField(default=list)   # [{product_id, quantity, ...}]
    replacement_items = models.JSONField(default=list)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    created_at = models.DateTimeField(auto_now_add=True)


class OfflineSyncQueue(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Pending offline POS transactions waiting to sync when back online."""
    STATUS_PENDING = "pending"
    STATUS_SYNCED = "synced"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_SYNCED, "Synced"), (STATUS_FAILED, "Failed")]

    device_id = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ReceiptTemplate(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Customizable receipt layout (store-level)."""
    name = models.CharField(max_length=120)
    is_default = models.BooleanField(default=False)
    header = models.TextField(blank=True)
    footer = models.TextField(blank=True)
    show_logo = models.BooleanField(default=True)
    show_qr = models.BooleanField(default=True)
    show_tax_breakdown = models.BooleanField(default=True)
    show_cashier = models.BooleanField(default=True)
    show_customer = models.BooleanField(default=True)
    accent_color = models.CharField(max_length=20, default="#111827")
    columns = models.JSONField(default=list)  # [{key,label,width}]
    paper = models.CharField(max_length=10, default="80mm")
    created_at = models.DateTimeField(auto_now_add=True)


class CashDrawerEvent(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    KIND_OPEN = "open"
    KIND_CLOSE = "close"
    KIND_NO_SALE = "no_sale"
    KIND_PAYOUT = "payout"
    KIND_DROP = "drop"
    KIND_CHOICES = [(KIND_OPEN, "Open"), (KIND_CLOSE, "Close"), (KIND_NO_SALE, "No sale"),
                    (KIND_PAYOUT, "Payout"), (KIND_DROP, "Drop")]
    session = models.ForeignKey("pos.CashSession", on_delete=models.CASCADE, related_name="drawer_events")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)