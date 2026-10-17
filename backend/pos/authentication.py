"""
authentication.py
Custom DRF authentication backend: `Authorization: Token <key>` header.

Every successful authentication:
  1. Rejects revoked tokens.
  2. Rejects tokens whose device has had its trust revoked.
  3. Enforces a SLIDING session timeout from SecuritySettings.session_timeout_minutes
     — if the gap since the token's last use exceeds the configured timeout,
     the token is auto-revoked and the request is rejected.
  4. On success, "touches" the token (slides the expiry window forward) so
     an active user is never logged out mid-session.

Opt in per-view with `authentication_classes = [ExpiringTokenAuthentication]`
— nothing here is wired in globally, so existing endpoints keep working
exactly as they do today until you choose to protect them.
"""
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from auth_app.models import AuthToken
from system.models import SecuritySettings


class ExpiringTokenAuthentication(BaseAuthentication):
    keyword = "Token"

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None
        key = parts[1]

        # Reuse token resolved by TenantMiddleware to avoid a second DB hit per request
        cached = getattr(request, "_cached_auth_token", None)
        if cached is not None and getattr(cached, "key", None) == key:
            token = cached
        else:
            try:
                token = AuthToken.objects.select_related("user", "device").get(key=key)
            except AuthToken.DoesNotExist:
                raise AuthenticationFailed("Invalid authentication token.")

        if token.is_revoked:
            raise AuthenticationFailed("This session has been revoked. Please log in again.")

        if not token.user.is_active:
            raise AuthenticationFailed("This account has been deactivated.")

        security = SecuritySettings.load()
        if token.is_expired(security.session_timeout_minutes):
            token.is_revoked = True
            token.save(update_fields=["is_revoked"])
            raise AuthenticationFailed("Session expired due to inactivity. Please log in again.")

        if token.device is not None and not token.device.is_authorized:
            raise AuthenticationFailed("This device's access has been revoked. Contact an administrator.")

        token.touch()
        return (token.user, token)

    def authenticate_header(self, request):
        return self.keyword
