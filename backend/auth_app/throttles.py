from rest_framework.throttling import SimpleRateThrottle


class UsernameBruteForceThrottle(SimpleRateThrottle):
    """Throttle login attempts per username.

    Prevents distributed brute-force attacks where an attacker rotates IPs
    but always targets the same username.  Falls back to client IP when no
    username is supplied in the request body.
    """

    scope = "login_username"

    def get_cache_key(self, request, view):
        username = str(request.data.get("username", "")).strip().lower()
        ident = username if username else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
