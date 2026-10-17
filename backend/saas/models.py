from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q


class Tenant(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_TRIAL = "trial"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_TRIAL, "Trial"),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_tenants"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TRIAL)
    is_active = models.BooleanField(default=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    suspended_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class TenantMembership(models.Model):
    ROLE_OWNER = "owner"
    ROLE_ADMIN = "admin"
    ROLE_MANAGER = "manager"
    ROLE_STAFF = "staff"
    ROLE_CHOICES = [
        (ROLE_OWNER, "Owner"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_STAFF, "Staff"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tenant_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STAFF)
    is_active_in_tenant = models.BooleanField(default=True)  # the tenant the user is "logged into"
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="unique_tenant_user"),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_active_in_tenant=True),
                name="saas_one_active_tenant_per_user",
            ),
        ]

        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user} @ {self.tenant} ({self.role})"


class SubscriptionPlan(models.Model):
    INTERVAL_MONTHLY = "monthly"
    INTERVAL_YEARLY = "yearly"
    INTERVAL_CHOICES = [(INTERVAL_MONTHLY, "Monthly"), (INTERVAL_YEARLY, "Yearly")]

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=10, default="USD")
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default=INTERVAL_MONTHLY)
    trial_days = models.PositiveIntegerField(default=14)

    # Usage limits — None means unlimited
    max_users = models.PositiveIntegerField(null=True, blank=True)
    max_stores = models.PositiveIntegerField(null=True, blank=True)
    max_warehouses = models.PositiveIntegerField(null=True, blank=True)
    max_products = models.PositiveIntegerField(null=True, blank=True)
    storage_mb = models.PositiveIntegerField(null=True, blank=True)

    features = models.JSONField(default=dict, blank=True)
    is_public = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    stripe_price_id = models.CharField(max_length=120, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price"]

    def __str__(self):
        return f"{self.name} ({self.interval})"


class Subscription(models.Model):
    STATUS_TRIALING = "trialing"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELED = "canceled"
    STATUS_EXPIRED = "expired"
    STATUS_INCOMPLETE = "incomplete"
    STATUS_CHOICES = [
        (STATUS_TRIALING, "Trialing"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAST_DUE, "Past due"),
        (STATUS_CANCELED, "Canceled"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_INCOMPLETE, "Incomplete"),
    ]

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TRIALING)
    stripe_customer_id = models.CharField(max_length=120, blank=True)
    stripe_subscription_id = models.CharField(max_length=120, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.tenant} — {self.plan} ({self.status})"


class ManualPaymentMethod(models.Model):
    """Globally configured offline payment methods for SaaS subscriptions only."""

    code = models.SlugField(max_length=40, unique=True)
    label = models.CharField(max_length=100)
    reference_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "label"]

    def __str__(self):
        return self.label


class SubscriptionRequest(models.Model):
    """A tenant request for a plan that remains non-entitling until verified."""

    STATUS_AWAITING_PAYMENT = "awaiting_payment"
    STATUS_PAYMENT_SUBMITTED = "payment_submitted"
    STATUS_ACTIVATED = "activated"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_AWAITING_PAYMENT, "Awaiting payment"),
        (STATUS_PAYMENT_SUBMITTED, "Payment submitted"),
        (STATUS_ACTIVATED, "Activated"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="subscription_requests")
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="requests")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscription_requests")
    expected_amount = models.DecimalField(max_digits=12, decimal_places=2)
    expected_currency = models.CharField(max_length=10)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_AWAITING_PAYMENT)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subscription_requests")
    requested_at = models.DateTimeField(auto_now_add=True)
    activated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="activated_subscription_requests")
    activated_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=Q(status__in=["awaiting_payment", "payment_submitted"]),
                name="saas_one_open_subscription_request_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.tenant} requested {self.plan} ({self.status})"


class ManualSubscriptionPayment(models.Model):
    """One immutable-on-verification offline payment submission per request."""

    STATUS_SUBMITTED = "submitted"
    STATUS_VERIFIED = "verified"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="manual_subscription_payments")
    subscription_request = models.OneToOneField(SubscriptionRequest, on_delete=models.PROTECT, related_name="manual_payment")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="manual_subscription_payments")
    payment_method = models.ForeignKey(ManualPaymentMethod, on_delete=models.PROTECT, related_name="manual_subscription_payments")
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_currency = models.CharField(max_length=10)
    payment_reference = models.CharField(max_length=160, blank=True)
    payment_date = models.DateField()
    proof_reference = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submitted_manual_subscription_payments")
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_manual_subscription_payments")
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment_method", "payment_reference"],
                condition=~Q(payment_reference=""),
                name="saas_unique_manual_payment_reference_by_method",
            ),
        ]

    def __str__(self):
        return f"Manual subscription payment #{self.pk} ({self.status})"


class Invoice(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_OPEN = "open"
    STATUS_PAID = "paid"
    STATUS_VOID = "void"
    STATUS_UNCOLLECTIBLE = "uncollectible"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"), (STATUS_OPEN, "Open"), (STATUS_PAID, "Paid"),
        (STATUS_VOID, "Void"), (STATUS_UNCOLLECTIBLE, "Uncollectible"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="invoices")
    subscription = models.ForeignKey(Subscription, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    subscription_request = models.OneToOneField("SubscriptionRequest", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoice")
    manual_payment = models.OneToOneField("ManualSubscriptionPayment", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoice")
    number = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=10, default="USD")
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    stripe_invoice_id = models.CharField(max_length=120, blank=True)
    pdf_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1"))
    unit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))


class TenantUsage(models.Model):
    """Point-in-time usage snapshot per metric for a tenant."""
    METRIC_USERS = "users"
    METRIC_STORES = "stores"
    METRIC_WAREHOUSES = "warehouses"
    METRIC_PRODUCTS = "products"
    METRIC_STORAGE_MB = "storage_mb"
    METRIC_CHOICES = [
        (METRIC_USERS, "Users"), (METRIC_STORES, "Stores"),
        (METRIC_WAREHOUSES, "Warehouses"), (METRIC_PRODUCTS, "Products"),
        (METRIC_STORAGE_MB, "Storage (MB)"),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="usage_snapshots")
    metric = models.CharField(max_length=20, choices=METRIC_CHOICES)
    value = models.PositiveIntegerField(default=0)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-captured_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "metric", "captured_at"], name="unique_usage_snapshot")
        ]


class TenantAwareModel(models.Model):
    """Abstract base for any record that must be isolated per tenant."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+", null=True, blank=True)

    class Meta:
        abstract = True
class PlanEntitlement(models.Model):
    """Tenant-plan entitlement metadata; RBAC remains a separate concern."""
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name="entitlements")
    code = models.CharField(max_length=120)
    label = models.CharField(max_length=200)
    enabled = models.BooleanField(default=True)
    limit_value = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "code"], name="saas_plan_entitlement_code"),
        ]
