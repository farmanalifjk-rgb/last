from decimal import Decimal
from django.conf import settings
from django.db import models


class CustomerAddress(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    KIND_BILLING = "billing"
    KIND_SHIPPING = "shipping"
    KIND_CHOICES = [(KIND_BILLING, "Billing"), (KIND_SHIPPING, "Shipping")]
    customer = models.ForeignKey("pos.Customer", on_delete=models.CASCADE, related_name="addresses")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_SHIPPING)
    label = models.CharField(max_length=60, blank=True)   # "Home", "Office"
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "kind"],
                condition=models.Q(is_default=True),
                name="unique_default_customer_address_per_kind",
            )
        ]


class CustomerCreditLimit(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    customer = models.OneToOneField("pos.Customer", on_delete=models.CASCADE, related_name="credit_limit")
    limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    used = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    terms_days = models.PositiveIntegerField(default=0)  # net 30 etc.
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)


class CustomerDocument(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    customer = models.ForeignKey("pos.Customer", on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=60, blank=True)  # "ID", "Contract", "Tax cert"
    file = models.FileField(upload_to="customers/docs/")
    name = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class LoyaltyEvent(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Timeline of loyalty point earn/burn events."""
    KIND_EARN = "earn"
    KIND_BURN = "burn"
    KIND_ADJUST = "adjust"
    KIND_EXPIRE = "expire"
    KIND_CHOICES = [(KIND_EARN, "Earn"), (KIND_BURN, "Burn"), (KIND_ADJUST, "Adjust"), (KIND_EXPIRE, "Expire")]
    customer = models.ForeignKey("pos.Customer", on_delete=models.CASCADE, related_name="loyalty_events")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    points = models.IntegerField()
    order = models.ForeignKey("pos.Order", null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class CustomerNote(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    customer = models.ForeignKey("pos.Customer", on_delete=models.CASCADE, related_name="notes")
    body = models.TextField()
    pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class CustomerPortalToken(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Self-service portal access token for a customer."""
    customer = models.OneToOneField("pos.Customer", on_delete=models.CASCADE, related_name="portal_token")
    token = models.CharField(max_length=64, unique=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
