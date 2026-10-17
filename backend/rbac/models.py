from django.conf import settings
from django.db import models
from django.db.models import Q


class Module(models.Model):
    """A logical module/area the app exposes (pos, inventory, reports, hr, tax...)."""
    key = models.CharField(max_length=60, unique=True)
    label = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]


class PermissionManager(models.Manager):
    """Backward-compatible permission lookup for callers predating scopes.

    Phase 15 permits the same module/action to exist once per scope. Older
    callers commonly omit ``scope`` and expect the tenant permission. When
    both tenant and platform variants exist, resolve the legacy lookup to the
    tenant variant instead of raising ``MultipleObjectsReturned``.
    """

    def get_or_create(self, defaults=None, **kwargs):
        if "scope" not in kwargs and "module" in kwargs and "action" in kwargs:
            tenant_permission = self.filter(
                module=kwargs["module"],
                action=kwargs["action"],
                scope="tenant",
            ).order_by("id").first()
            if tenant_permission is not None:
                return tenant_permission, False
        return super().get_or_create(defaults=defaults, **kwargs)


class Permission(models.Model):
    """Atomic action on a module: pos.view, pos.refund, inventory.adjust..."""
    ACTION_VIEW = "view"
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_REFUND = "refund"
    ACTION_VOID = "void"
    ACTION_DISCOUNT = "discount"
    ACTION_REPORT = "report"
    ACTION_MANAGE = "manage"
    ACTION_REQUEST = "request"
    ACTION_VERIFY = "verify"
    ACTION_APPROVE = "approve"
    ACTION_RECEIVE = "receive"
    ACTION_RETURN = "return"
    ACTION_POST = "post"
    ACTION_EXPORT = "export"
    ACTION_CHOICES = [(ACTION_VIEW, "View"), (ACTION_CREATE, "Create"), (ACTION_UPDATE, "Update"),
                      (ACTION_DELETE, "Delete"), (ACTION_REFUND, "Refund"), (ACTION_VOID, "Void"),
                      (ACTION_DISCOUNT, "Discount"), (ACTION_REPORT, "Report"), (ACTION_MANAGE, "Manage"),
                      (ACTION_REQUEST, "Request"), (ACTION_VERIFY, "Verify"),
                      (ACTION_APPROVE, "Approve"), (ACTION_RECEIVE, "Receive"), (ACTION_RETURN, "Return"),
                      (ACTION_POST, "Post"), (ACTION_EXPORT, "Export")]
    SCOPE_TENANT = "tenant"
    SCOPE_PLATFORM = "platform"
    SCOPE_CHOICES = [(SCOPE_TENANT, "Tenant"), (SCOPE_PLATFORM, "Platform")]
    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CRITICAL = "critical"
    RISK_CHOICES = [(RISK_LOW, "Low"), (RISK_MEDIUM, "Medium"), (RISK_HIGH, "High"), (RISK_CRITICAL, "Critical")]
    ACCESS_READ = "read"
    ACCESS_MUTATE = "mutate"
    ACCESS_APPROVE = "approve"
    ACCESS_ADMIN = "admin"
    ACCESS_CHOICES = [(ACCESS_READ, "Read"), (ACCESS_MUTATE, "Mutate"), (ACCESS_APPROVE, "Approve"), (ACCESS_ADMIN, "Admin")]
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="permissions")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.CharField(max_length=255, blank=True)
    scope = models.CharField(max_length=12, choices=SCOPE_CHOICES, default=SCOPE_TENANT)
    risk_level = models.CharField(max_length=12, choices=RISK_CHOICES, default=RISK_LOW)
    access_kind = models.CharField(max_length=12, choices=ACCESS_CHOICES, default=ACCESS_READ)
    is_sensitive = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PermissionManager()

    class Meta:
        unique_together = [("module", "action", "scope")]
        ordering = ["module__label", "action"]


class Role(models.Model):
    """Named role (Cashier, Supervisor, Manager, Accountant) with a permission set."""
    SYSTEM_ADMIN = "admin"
    SCOPE_TENANT = Permission.SCOPE_TENANT
    SCOPE_PLATFORM = Permission.SCOPE_PLATFORM
    SCOPE_CHOICES = Permission.SCOPE_CHOICES
    key = models.CharField(max_length=60, unique=True)
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    scope = models.CharField(max_length=12, choices=SCOPE_CHOICES, default=SCOPE_TENANT)
    tenant = models.ForeignKey("saas.Tenant", null=True, blank=True, on_delete=models.CASCADE,
                               related_name="rbac_roles")
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]


class UserRole(models.Model):
    """Assignment of a role to a user (a user can hold multiple roles)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="assignments")
    tenant = models.ForeignKey("saas.Tenant", null=True, blank=True, on_delete=models.CASCADE,
                               related_name="rbac_role_assignments")
    branch = models.ForeignKey('tenancy.Branch', null=True, blank=True, on_delete=models.CASCADE,
                               help_text="Scope the role to a branch; blank = all branches")
    is_active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="role_assignments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "tenant"],
                condition=Q(branch__isnull=True),
                name="rbac_unique_user_role_tenant_unbranched",
            ),
            models.UniqueConstraint(
                fields=["user", "role", "tenant", "branch"],
                condition=Q(branch__isnull=False),
                name="rbac_unique_user_role_tenant_branch",
            ),
        ]
        ordering = ["-created_at"]


class RoleTemplate(models.Model):
    """Pre-baked permission bundles that can be cloned into a Role."""
    key = models.CharField(max_length=60, unique=True)
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    permission_keys = models.JSONField(default=list, help_text='List of "module.action" strings')
    created_at = models.DateTimeField(auto_now_add=True)


class PermissionOverride(models.Model):
    """Per-user allow/deny override on a single permission (wins over roles)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="permission_overrides")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    tenant = models.ForeignKey("saas.Tenant", null=True, blank=True, on_delete=models.CASCADE,
                               related_name="rbac_permission_overrides")
    decision = models.CharField(max_length=10, choices=[("allow", "Allow"), ("deny", "Deny")])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "permission", "tenant"], name="rbac_unique_user_permission_scope"),
        ]
