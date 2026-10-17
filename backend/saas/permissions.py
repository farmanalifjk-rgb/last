from rest_framework.permissions import BasePermission


class HasActiveTenant(BasePermission):
    message = "An active tenant is required for this operation."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        # DRF authentication is authoritative.  Re-resolve the canonical active
        # membership here so a stale Django session cannot leak tenant context.
        from .services import get_active_tenant_for_user
        request.tenant = get_active_tenant_for_user(request.user)
        if request.tenant is not None:
            from .tenant_context import set_current_tenant
            set_current_tenant(request.tenant)
        return bool(request.tenant)


class TenantRBACPermission(BasePermission):
    """Use SaaS tenant membership plus the existing RBAC permission graph."""

    message = "The active tenant role does not permit this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        # Retained endpoints occasionally declare this permission without
        # ``HasActiveTenant``.  Resolve the same canonical context defensively
        # rather than depending on permission ordering or middleware state.
        from .services import get_active_tenant_for_user
        tenant = get_active_tenant_for_user(request.user)
        request.tenant = tenant
        if tenant is None:
            return False
        if request.user.is_superuser:
            return True
        from .models import TenantMembership
        membership = TenantMembership.objects.filter(
            tenant=tenant, user=request.user, is_active_in_tenant=True
        ).first()
        if membership is None:
            return False
        if membership.role in {TenantMembership.ROLE_OWNER, TenantMembership.ROLE_ADMIN}:
            return True
        module = getattr(view, "rbac_module", None)
        if not module:
            return True
        action = getattr(view, "rbac_action", None) or getattr(view, "action", None)
        if action in {"list", "retrieve"}:
            action = "view"
        elif action in {"partial_update", "archive"}:
            action = "update"
        elif action is None:
            action = {"GET": "view", "POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(request.method)
        if not action:
            return False
        from rbac.checker import has_permission
        return has_permission(request.user, module, action, tenant=tenant)


def tenant_member_has_permission(user, tenant, module, action):
    """Single-action check using exactly the TenantRBACPermission rule.

    Superusers and active tenant owners/admins hold every tenant action; other
    members need the RBAC permission. View-level checks for extra actions
    (e.g. ``pos.discount``) must use this instead of ``rbac.checker.has_permission``
    alone, which ignores the membership role and so denied owners.
    """
    if not (user and user.is_authenticated) or tenant is None:
        return False
    if user.is_superuser:
        return True
    from .models import TenantMembership
    membership = TenantMembership.objects.filter(tenant=tenant, user=user, is_active_in_tenant=True).first()
    if membership is None:
        return False
    if membership.role in {TenantMembership.ROLE_OWNER, TenantMembership.ROLE_ADMIN}:
        return True
    from rbac.checker import has_permission
    return has_permission(user, module, action, tenant=tenant)


class PlatformBillingPermission(BasePermission):
    """Global verifier permission that intentionally does not inherit tenant-owner access."""

    message = "A platform billing verification permission is required for this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        from rbac.checker import has_permission
        return has_permission(request.user, "billing", "verify", scope="platform")


class PlatformRBACPermission(BasePermission):
    """Explicit platform permission; it never inherits tenant membership authority."""

    message = "A platform-level permission is required for this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        module = getattr(view, "rbac_module", None)
        action = getattr(view, "rbac_action", None)
        if not module or not action:
            return False
        from rbac.checker import has_permission
        return has_permission(request.user, module, action, scope="platform")


class TenantScopedViewSetMixin:
    """Limit a model viewset to request.tenant and stamp the tenant on create."""

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant = getattr(self.request, "tenant", None)
        return queryset.filter(tenant=tenant) if tenant is not None else queryset.none()

    def perform_create(self, serializer):
        tenant = getattr(self.request, "tenant", None)
        if tenant is None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(HasActiveTenant.message)
        serializer.save(tenant=tenant)

    def perform_update(self, serializer):
        self.perform_create(serializer)


class PlanEntitlementEnforcement(BasePermission):
    """Check plan limits before allowing resource creation.

    Attach to a ViewSet to enforce the active tenant's subscription plan
    limits (max_users, max_products, max_warehouses, max_stores) on POST.
    Views that do not create limited resources should not use this class.
    """
    message = "Your current plan limit has been reached for this resource."

    # Map (viewset model label → TenantUsage metric) so each view declares
    # which limit to enforce.  Subclass or extend as new resource types appear.
    METRIC_MAP = {}

    def has_permission(self, request, view):
        if request.method not in {"POST", "PUT", "PATCH"}:
            return True
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return True  # HasActiveTenant handles the missing-tenant case
        metric = self.METRIC_MAP.get(getattr(view, "entitlement_metric", None))
        if metric is None:
            return True
        from .services import enforce_limit, LimitExceeded
        try:
            enforce_limit(tenant, metric)
        except LimitExceeded:
            return False
        return True
