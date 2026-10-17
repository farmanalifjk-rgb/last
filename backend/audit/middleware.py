from .recorder import record
from .models import AuditEvent
from saas.services import get_active_tenant_for_user


def _audit_tenant(request, actor):
    """Resolve the canonical active tenant after DRF token auth has populated request.user."""
    tenant = getattr(request, "tenant", None)
    if tenant is not None:
        return tenant
    if actor is not None and getattr(actor, "is_authenticated", False):
        return get_active_tenant_for_user(actor)
    return None


class AuditMiddleware:
    """Logs login/logout + attaches request to a thread-local for recorder use."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # record auth events by path
        path = request.path.rstrip("/")
        if path.endswith("/login") and request.method == "POST" and getattr(request.user, "id", None):
            tenant = _audit_tenant(request, request.user)
            if tenant is not None:
                record(actor=request.user, action=AuditEvent.ACTION_LOGIN, entity_type="User",
                       entity_id=str(request.user.id), entity_label=str(request.user),
                       request=request, summary=f"{request.user} logged in", icon="log-in", tenant=tenant)
        elif path.endswith("/logout") and request.method in ("POST", "GET"):
            actor = getattr(request, "_pre_logout_user", None)
        
            if actor is not None and getattr(actor, "is_authenticated", False):
                tenant = _audit_tenant(request, actor)
        
                if tenant is not None:
                    record(
                        actor=actor,
                        action=AuditEvent.ACTION_LOGOUT,
                        entity_type="User",
                        # Logout is an actor event, not a mutation of the User entity.
                        # Keep entity_id blank to preserve the audit event contract.
                        entity_id="",
                        entity_label=str(actor),
                        request=request,
                        summary="User logged out",
                        icon="log-out",
                        tenant=tenant
                    )
        return response
