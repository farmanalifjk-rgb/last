from django.conf import settings
from django.db import models


class Tenant(models.Model):
    """An organisation/business that owns branches, users, and data."""
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30, unique=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    logo_url = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]


class Branch(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("tenant", "code")]
        ordering = ["name"]


class UserTenantMembership(models.Model):
    """Links a user to a tenant + their active branch scope."""
    ROLE_TENANT_ADMIN = "tenant_admin"
    ROLE_BRANCH_MANAGER = "branch_manager"
    ROLE_STAFF = "staff"
    ROLE_CHOICES = [(ROLE_TENANT_ADMIN, "Tenant admin"), (ROLE_BRANCH_MANAGER, "Branch manager"), (ROLE_STAFF, "Staff")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tenant_memberships_legacy')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.CASCADE, help_text="Active branch; null = all branches")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STAFF)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "tenant", "branch")]


class TenantSetting(models.Model):
    """Per-tenant key/value config (currency, tax mode, receipt header...)."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="settings")
    key = models.CharField(max_length=80)
    value = models.TextField(blank=True)
    is_json = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("tenant", "key")]


class BranchSetting(models.Model):
    """Per-branch overrides (terminal count, receipt printer name...)."""
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="settings")
    key = models.CharField(max_length=80)
    value = models.TextField(blank=True)
    is_json = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("branch", "key")]