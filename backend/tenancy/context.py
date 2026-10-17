from .models import UserTenantMembership


def active_tenant(user):
    if not user or not user.is_authenticated:
        return None
    m = UserTenantMembership.objects.filter(user=user, is_active=True).select_related("tenant").first()
    return m.tenant if m else None


def active_branch(user):
    if not user or not user.is_authenticated:
        return None
    m = UserTenantMembership.objects.filter(user=user, is_active=True).select_related("branch").first()
    return m.branch if m else None


def scoped_queryset(model_cls, user, tenant_field="tenant", branch_field="branch"):
    """Filter a queryset by the user's tenant (and branch if the model has the field)."""
    qs = model_cls.objects.all()
    tenant = active_tenant(user)
    if tenant is None:
        return qs.none()
    if tenant_field and hasattr(model_cls, tenant_field):
        qs = qs.filter(**{tenant_field: tenant})
    branch = active_branch(user)
    if branch and branch_field and hasattr(model_cls, branch_field):
        qs = qs.filter(**{branch_field: branch})
    return qs