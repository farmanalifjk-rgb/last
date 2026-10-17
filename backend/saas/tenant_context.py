from contextvars import ContextVar


_current_tenant = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant):
    return _current_tenant.set(tenant)


def reset_current_tenant(token):
    _current_tenant.reset(token)


def get_current_tenant():
    return _current_tenant.get()


def require_current_tenant():
    tenant = get_current_tenant()
    if tenant is None:
        raise RuntimeError("No active tenant is bound to this request or operation.")
    return tenant


def scoped_queryset(queryset, tenant=None):
    tenant = tenant or get_current_tenant()
    if tenant is None:
        return queryset.none()
    return queryset.filter(tenant=tenant)
