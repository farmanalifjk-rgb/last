import logging

from django.http import JsonResponse

from .services import get_active_tenant_for_user
from .tenant_context import reset_current_tenant, set_current_tenant

logger = logging.getLogger(__name__)

# Paths that do not require an active, non-suspended tenant context.
_TENANT_FREE_PATHS = frozenset({
    "/api/auth/login/",
    "/api/auth/verify-otp/",
    "/api/auth/resend-otp/",
    "/api/health/",
    "/admin/",
})


class TenantMiddleware:
    """Bind the authenticated user's canonical SaaS workspace to the request.

    Workspace authority is derived only from ``saas.TenantMembership``.  The
    browser may request a tenant switch through the dedicated API, but an
    arbitrary header can never select a tenant, including for superusers.
    Platform operations use explicit platform permissions rather than tenant
    impersonation through request metadata.

    Tenant status enforcement:
      - ``suspended`` tenants are blocked from all API access except auth.
      - ``trial`` tenants whose ``trial_ends_at`` has passed are blocked.
      - ``inactive`` tenants are blocked.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None

        # Middleware runs before DRF authentication.  Resolve the same token
        # principal used by the API permission layer when a token is present.
        # Uses identical checks as ExpiringTokenAuthentication so revoked/expired/device-revoked
        # tokens never leak tenant context.  The resolved token is cached on the request
        # to avoid a second DB hit in DRF authentication.
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            parts = auth_header.split()
            if len(parts) == 2 and parts[0] in {"Token", "Bearer"}:
                from auth_app.models import AuthToken

                try:
                    token_obj = AuthToken.objects.select_related("user", "device").get(key=parts[1])
                except AuthToken.DoesNotExist:
                    token_obj = None
                if token_obj is not None:
                    # Mirror ExpiringTokenAuthentication checks so tenant is not bound from a bad token
                    if token_obj.is_revoked or not token_obj.user.is_active:
                        token_obj = None
                    else:
                        from django.utils import timezone as _tz
                        from system.models import SecuritySettings as _Sec
                        try:
                            security = _Sec.load(tenant=None)
                            timeout = security.session_timeout_minutes
                        except Exception:
                            timeout = 30
                        if token_obj.is_expired(timeout):
                            try:
                                token_obj.is_revoked = True
                                token_obj.save(update_fields=["is_revoked"])
                            except Exception:
                                pass
                            token_obj = None
                        elif token_obj.device is not None and not token_obj.device.is_authorized:
                            token_obj = None
                if token_obj is not None and token_obj.user.is_active:
                    request.user = token_obj.user
                    # Cache for DRF authentication to reuse without a second DB hit
                    request._cached_auth_token = token_obj  # type: ignore[attr-defined]

        # Tenant-free endpoints must remain reachable even when an already
        # authenticated principal belongs to a suspended/expired workspace.
        # They are intentionally not granted a tenant context here.
        if request.path in _TENANT_FREE_PATHS:
            token = set_current_tenant(None)
            try:
                return self.get_response(request)
            finally:
                reset_current_tenant(token)

        if getattr(request, "user", None) and request.user.is_authenticated:
            request.tenant = get_active_tenant_for_user(request.user)

            # ── Tenant status enforcement ──────────────────────────────────
            if request.tenant is not None:
                from django.utils import timezone

                tenant = request.tenant
                reason = None
                if tenant.status == "suspended":
                    reason = f"Tenant '{tenant.name}' has been suspended."
                elif not tenant.is_active:
                    reason = f"Tenant '{tenant.name}' is inactive."
                elif (
                    tenant.status == "trial"
                    and tenant.trial_ends_at is not None
                    and tenant.trial_ends_at < timezone.now()
                ):
                    reason = f"Tenant '{tenant.name}' trial period has expired."
                if reason is not None:
                    logger.warning("Tenant access blocked: %s (user=%s)", reason, request.user)
                    request.tenant = None
                    token = set_current_tenant(None)
                    try:
                        return JsonResponse(
                            {"detail": reason, "code": "tenant_unavailable"},
                            status=403,
                        )
                    finally:
                        reset_current_tenant(token)

        token = set_current_tenant(request.tenant)
        try:
            return self.get_response(request)
        finally:
            reset_current_tenant(token)
