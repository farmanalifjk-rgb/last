from .context import active_tenant, active_branch


class TenantScopeMiddleware:
    """Attach `request.tenant` and `request.branch` for downstream use."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = active_tenant(getattr(request, "user", None))
        request.branch = active_branch(getattr(request, "user", None))
        return self.get_response(request)