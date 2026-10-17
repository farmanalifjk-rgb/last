from functools import wraps

from django.http import JsonResponse

from .models import Permission, PermissionOverride, RoleTemplate, UserRole


# Every retained backend/frontend capability uses one module key from this
# catalog.  Adding a route must add its module/action here and in the
# corresponding migration seed; silently allowing unknown module keys is not
# permitted.
TENANT_PERMISSION_CATALOG = {
    "dashboard": ["view"],
    "pos": ["view", "create", "update", "refund", "void", "discount"],
    "payments": ["view", "create", "update", "refund", "void", "manage"],
    "inventory": ["view", "create", "update", "delete", "manage"],
    "transfers": ["view", "create", "update", "approve", "receive"],
    "products": ["view", "create", "update", "delete"],
    "catalog": ["view", "create", "update", "manage"],
    "pricing": ["view", "create", "update", "manage"],
    "customers": ["view", "create", "update", "delete"],
    "loyalty": ["view", "create", "update", "manage"],
    "suppliers": ["view", "create", "update"],
    "purchasing": ["view", "create", "update", "approve", "receive", "return"],
    "accounting": ["view", "create", "update", "post", "manage"],
    "reports": ["view", "report", "export"],
    "tax": ["view", "manage", "report"],
    "hr": ["view", "create", "update", "manage"],
    "fiscal": ["view", "create", "manage"],
    "audit": ["view"],
    "operations": ["view", "manage", "approve"],
    "notifications": ["view", "manage"],
    "integrations": ["view", "manage"],
    "ai": ["view", "create", "update", "manage"],
    "hardware": ["view", "manage"],
    "settings": ["view", "manage"],
    "billing": ["view", "manage", "request"],
    "rbac": ["view", "manage"],
}

PLATFORM_PERMISSION_CATALOG = {
    "settings": ["view", "manage"],
    "billing": ["verify"],
    "rbac": ["view", "manage"],
    "system": ["manage"],
}


def user_permissions(user, *, tenant=None, scope=None, branch=None):
    """Resolve effective permissions for one explicit platform or tenant scope.

    When *branch* is provided, only role assignments that either have no branch
    (global within the tenant) or match the given branch are included.
    """
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return {"*.*"}
    if scope is None:
        scope = Permission.SCOPE_TENANT if tenant is not None else Permission.SCOPE_PLATFORM

    assignments = UserRole.objects.filter(
        user=user,
        is_active=True,
        role__is_active=True,
        role__scope=scope,
    ).select_related("role")
    if scope == Permission.SCOPE_TENANT:
        if tenant is None:
            return set()
        assignments = assignments.filter(tenant=tenant)
        # Branch scoping: include global (branch=null) and branch-specific assignments.
        if branch is not None:
            from django.db.models import Q
            assignments = assignments.filter(Q(branch__isnull=True) | Q(branch=branch))
    else:
        assignments = assignments.filter(tenant__isnull=True)

    keys = set()
    for assignment in assignments:
        for permission in assignment.role.permissions.filter(scope=scope).select_related("module"):
            keys.add(f"{permission.module.key}.{permission.action}")

    overrides = PermissionOverride.objects.filter(user=user, permission__scope=scope).select_related("permission__module")
    if scope == Permission.SCOPE_TENANT:
        overrides = overrides.filter(tenant=tenant)
    else:
        overrides = overrides.filter(tenant__isnull=True)
    for override in overrides:
        key = f"{override.permission.module.key}.{override.permission.action}"
        if override.decision == "allow":
            keys.add(key)
        else:
            keys.discard(key)
    return keys


def has_permission(user, module_key, action, *, tenant=None, scope=None):
    keys = user_permissions(user, tenant=tenant, scope=scope)
    return "*.*" in keys or f"{module_key}.{action}" in keys


def require_permission(module_key, action):
    """Decorator for DRF / Django views: ``@require_permission('pos', 'refund')``."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            tenant = getattr(request, "tenant", None)
            if not has_permission(request.user, module_key, action, tenant=tenant):
                return JsonResponse({"detail": f"Permission denied: {module_key}.{action}"}, status=403)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def apply_template_to_role(role, template):
    """Materialize a role template into permissions of the role's explicit scope.

    ``*.*`` is a template convenience only.  It is expanded into atomic scoped
    permissions, so later deny overrides and permission audits remain reliable.
    """
    requested = set(template.permission_keys or [])
    permissions = Permission.objects.filter(scope=role.scope).select_related("module")
    if "*.*" in requested:
        selected = list(permissions)
    else:
        selected = []
        for key in requested:
            if "." not in key:
                continue
            module_key, action = key.split(".", 1)
            permission = permissions.filter(module__key=module_key, action=action).first()
            if permission:
                selected.append(permission)
    role.permissions.add(*selected)
    return [f"{permission.module.key}.{permission.action}" for permission in selected]


def _permission_metadata(module_key, action, scope):
    sensitive = (module_key, action) in {
        ("billing", "verify"), ("payments", "refund"), ("payments", "manage"),
        ("accounting", "post"), ("accounting", "manage"), ("fiscal", "manage"),
        ("hr", "manage"), ("operations", "approve"), ("settings", "manage"),
        ("system", "manage"), ("rbac", "manage"), ("integrations", "manage"),
    }
    if action in {"manage", "verify"}:
        access_kind = Permission.ACCESS_ADMIN
    elif action in {"approve", "post", "refund"}:
        access_kind = Permission.ACCESS_APPROVE
    elif action in {"create", "update", "delete", "void", "discount", "receive", "return", "request"}:
        access_kind = Permission.ACCESS_MUTATE
    else:
        access_kind = Permission.ACCESS_READ
    risk = Permission.RISK_CRITICAL if sensitive else Permission.RISK_HIGH if access_kind in {"admin", "approve"} else Permission.RISK_MEDIUM if access_kind == "mutate" else Permission.RISK_LOW
    return {"scope": scope, "access_kind": access_kind, "risk_level": risk, "is_sensitive": sensitive}


def seed_modules_and_permissions():
    """Idempotently seed the complete scoped permission catalog and templates."""
    from .models import Module

    for scope, catalog in (
        (Permission.SCOPE_TENANT, TENANT_PERMISSION_CATALOG),
        (Permission.SCOPE_PLATFORM, PLATFORM_PERMISSION_CATALOG),
    ):
        for module_key, actions in catalog.items():
            module, _ = Module.objects.get_or_create(key=module_key, defaults={"label": module_key.replace("_", " ").title()})
            for action in actions:
                Permission.objects.update_or_create(
                    module=module,
                    action=action,
                    scope=scope,
                    defaults=_permission_metadata(module_key, action, scope),
                )

    templates = {
        "cashier": ["pos.view", "pos.create", "customers.view", "customers.create", "products.view"],
        "supervisor": ["pos.view", "pos.create", "pos.update", "pos.refund", "pos.void", "pos.discount", "customers.view", "customers.create", "customers.update", "inventory.view", "reports.view", "hr.view"],
        "manager": ["*.*"],
        "accountant": ["reports.view", "reports.report", "tax.view", "tax.report", "fiscal.view", "audit.view", "accounting.view", "accounting.create", "accounting.update", "accounting.post"],
    }
    for key, permission_keys in templates.items():
        RoleTemplate.objects.update_or_create(
            key=key,
            defaults={"label": key.title(), "permission_keys": permission_keys},
        )
