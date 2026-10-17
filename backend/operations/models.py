"""
Workflow approval and canonical in-app-notification models.

Operational domains retain ownership of their records. ApprovalRequest stores
only a tenant-scoped reference to a source action; it never duplicates it.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q


class ApprovalRule(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    MODULE_CHOICES = [
        ("purchase_order", "Purchase Order"),
        ("refund", "Refund"),
        ("stock_adjustment", "Stock Adjustment"),
        ("payroll", "Payroll"),
        ("expense", "Expense"),
        ("warehouse_transfer", "Warehouse Transfer"),
    ]

    module = models.CharField(max_length=50, choices=MODULE_CHOICES)
    action = models.CharField(max_length=80, help_text='e.g. "confirm" or "post"')
    min_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True,
                                     help_text="Only trigger if amount meets this threshold; null means every amount.")
    requires_approval = models.BooleanField(default=True)
    approver_role = models.CharField(max_length=100, blank=True,
                                     help_text="Optional existing tenant role key required to decide the request.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["module", "action"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "module", "action"],
                name="operations_unique_approval_rule_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.tenant_id}:{self.module}.{self.action} → requires={self.requires_approval}"


class ApprovalRequest(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    module = models.CharField(max_length=50)
    action = models.CharField(max_length=80)
    reference_id = models.PositiveIntegerField(help_text="Primary key of the authoritative source object")
    reference_str = models.CharField(max_length=100, blank=True, help_text="Human-readable source reference")
    amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="approval_requests")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="approvals_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "module", "action", "reference_id"],
                name="operations_unique_approval_request_source",
            ),
        ]

    def __str__(self):
        return f"{self.tenant_id}:{self.module}/{self.action} #{self.reference_id} [{self.status}]"


class InAppNotification(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    TYPE_INFO = "info"
    TYPE_SUCCESS = "success"
    TYPE_WARNING = "warning"
    TYPE_ERROR = "error"
    TYPE_CHOICES = [
        (TYPE_INFO, "Info"),
        (TYPE_SUCCESS, "Success"),
        (TYPE_WARNING, "Warning"),
        (TYPE_ERROR, "Error"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inapp_notifications")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_INFO)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=300, blank=True, help_text="Frontend path to the authoritative source")
    event_key = models.CharField(max_length=160, blank=True,
                                 help_text="Optional durable source-event identity preventing duplicate inbox entries.")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "In-App Notification"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "event_key"],
                condition=~Q(event_key=""),
                name="operations_unique_notification_event_per_user",
            ),
        ]

    def __str__(self):
        return f"[{self.type}] {self.title} → {self.user}"


class EmailQueue(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_SENT, "Sent"), (STATUS_FAILED, "Failed")]

    to = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class SMSQueue(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_SENT, "Sent"), (STATUS_FAILED, "Failed")]

    to = models.CharField(max_length=20)
    message = models.TextField(max_length=320)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
