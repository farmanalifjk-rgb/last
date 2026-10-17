"""
views/auth_secure.py
The real authentication flow that enforces everything configured in the
Security settings tab:

  • Lockout tracking     — every attempt is logged; N failures within the
                            configured window locks the account for the
                            configured duration (HTTP 423).
  • Password policy       — enforced server-side on every password set/change,
                            using the exact same rule the frontend can preview
                            via /security/password-policy-check/.
  • Password expiry       — login is blocked (403, password_expired) once a
                            password is older than the configured max age.
  • Two-factor auth       — if enabled, login pauses on a 6-digit OTP
                            (delivered by email/SMS per the configured method)
                            before a session token is issued.
  • Trusted devices       — if device authorization is required, a brand-new
                            device must be verified with an OTP before it can
                            receive a session token; admins can also revoke a
                            device at any time to instantly kill its sessions.

None of this is wired in as a global requirement — it's opt-in per view via
`authentication_classes = [ExpiringTokenAuthentication]`, so it won't break
any existing unauthenticated endpoint until you choose to protect it.
"""
from datetime import timedelta
import logging

from django.conf import settings as dj_settings
from .throttles import UsernameBruteForceThrottle
from django.contrib.auth import authenticate, get_user_model
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from pos.authentication import ExpiringTokenAuthentication
from pos.models import UserProfile
from auth_app.models import AuthToken, OneTimePasscode
from system.models import SecuritySettings, TrustedDevice, LoginAttempt
from system.views import _client_ip, validate_password_against_policy, write_audit_log

User = get_user_model()
logger = logging.getLogger(__name__)


class OTPDeliveryUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Verification delivery is temporarily unavailable. Please try again later."
    default_code = "otp_delivery_unavailable"


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════
def _user_agent(request):
    return request.META.get("HTTP_USER_AGENT", "")[:300]


def _recent_failed_attempts(username, security):
    window_start = timezone.now() - timedelta(minutes=security.lockout_duration_minutes)
    return LoginAttempt.objects.filter(
        username__iexact=username, was_successful=False, created_at__gte=window_start
    ).count()


def _deliver_otp(user, code, purpose, method):
    """Deliver an OTP without logging the code or silently issuing an unusable challenge."""
    subject = "Your POS verification code" if purpose == "login_2fa" else "Authorize this device"
    message = f"Your verification code is {code}. It expires in 10 minutes. If you didn't request this, ignore it."
    if method == "sms":
        logger.error("OTP SMS delivery requested but no SMS provider adapter is configured.")
        return False
    if not user.email:
        logger.warning("OTP email delivery requested for an account without an email address.")
        return False
    try:
        delivered = send_mail(
            subject,
            message,
            getattr(dj_settings, "DEFAULT_FROM_EMAIL", None),
            [user.email],
            fail_silently=False,
        )
        return delivered == 1
    except Exception:
        logger.exception("OTP email delivery failed.")
        return False


def _issue_otp(user, purpose, device=None, digits=6, ttl_minutes=10):
    import secrets
    code = f"{secrets.randbelow(10 ** digits):0{digits}d}"
    otp = OneTimePasscode(user=user, device=device, purpose=purpose,
                           expires_at=timezone.now() + timedelta(minutes=ttl_minutes))
    otp.set_code(code)
    otp.save()
    security = SecuritySettings.load()
    if not _deliver_otp(user, code, purpose, security.two_factor_method):
        otp.delete()
        raise OTPDeliveryUnavailable()
    return code


def _issue_token(user, device=None):
    return AuthToken.objects.create(user=user, device=device)


def _tenant_summary(tenant):
    if tenant is None:
        return None
    from pos.models import Company

    currency = (
        Company.objects.filter(tenant=tenant).order_by("id").values_list("currency", flat=True).first()
    )
    currency = str(currency).strip() if currency else ""
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "currency": currency or None}


def _login_success_payload(user, token, device):
    from rbac.checker import user_permissions
    from saas.models import TenantMembership
    from saas.services import get_active_tenant_for_user

    tenant = get_active_tenant_for_user(user)
    membership = TenantMembership.objects.filter(
        tenant=tenant, user=user, is_active_in_tenant=True,
    ).first() if tenant else None
    if user.is_superuser or membership and membership.role in {
        TenantMembership.ROLE_OWNER,
        TenantMembership.ROLE_ADMIN,
    }:
        effective_permissions = {"*.*"}
    else:
        effective_permissions = user_permissions(user, tenant=tenant)
    return {
        "token": token.key,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_staff": user.is_staff,
            "role": membership.role if membership else None,
            "permissions": sorted(effective_permissions),
        },
        # Active business, for the header badge and money formatting. Read
        # only: the company profile is never created here (currency is null
        # when the tenant has no profile yet and the UI falls back to "Rs").
        "tenant": _tenant_summary(tenant),
        "device_id": device.device_id if device else None,
        "device_authorized": device.is_authorized if device else None,
        "session_timeout_minutes": SecuritySettings.load().session_timeout_minutes,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Login
# ═══════════════════════════════════════════════════════════════════════════
class LoginView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [UsernameBruteForceThrottle]

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        device_id = str(request.data.get("device_id", "")).strip()
        device_name = str(request.data.get("device_name", "")).strip()

        if not username or not password:
            return Response({"error": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        security = SecuritySettings.load()

        # ── 1. Lockout check ────────────────────────────────────────────────
        if security.max_login_attempts:
            failures = _recent_failed_attempts(username, security)
            if failures >= security.max_login_attempts:
                LoginAttempt.objects.create(
                    username=username, was_successful=False, reason="locked_out",
                    ip_address=_client_ip(request), user_agent=_user_agent(request),
                )
                return Response({
                    "error": f"Too many failed attempts. Try again in {security.lockout_duration_minutes} minute(s).",
                    "locked_out": True,
                    "lockout_duration_minutes": security.lockout_duration_minutes,
                }, status=status.HTTP_423_LOCKED)

        # ── 2. Authenticate ──────────────────────────────────────────────────
        # Username remains the canonical credential.  A unique, case-insensitive
        # email match is also accepted so a user cannot be rejected simply because
        # they entered the email shown in their account profile.  Ambiguous emails
        # are deliberately not resolved to avoid account-selection surprises.
        user = authenticate(request, username=username, password=password)
        if user is None and "@" in username:
            email_matches = User.objects.filter(email__iexact=username, is_active=True)
            if email_matches.count() == 1:
                user = authenticate(request, username=email_matches.first().get_username(), password=password)
        if user is None or not user.is_active:
            LoginAttempt.objects.create(
                username=username, was_successful=False,
                reason="inactive_user" if user is not None else "invalid_credentials",
                ip_address=_client_ip(request), user_agent=_user_agent(request),
            )
            failures = _recent_failed_attempts(username, security)
            remaining = max(security.max_login_attempts - failures, 0) if security.max_login_attempts else None
            return Response({
                "error": "Invalid username or password.",
                "attempts_remaining": remaining,
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Credentials good — log success and continue.
        LoginAttempt.objects.create(
            username=username, was_successful=True,
            ip_address=_client_ip(request), user_agent=_user_agent(request),
        )

        # ── 3. Password expiry ──────────────────────────────────────────────
        profile, _created = UserProfile.objects.get_or_create(user=user)
        if security.password_expiry_days and profile.password_changed_at:
            age_days = (timezone.now() - profile.password_changed_at).days
            if age_days >= security.password_expiry_days:
                return Response({
                    "error": "Your password has expired and must be changed before continuing.",
                    "password_expired": True,
                    "username": user.username,
                }, status=status.HTTP_403_FORBIDDEN)

        # ── 4. Device trust / authorization ─────────────────────────────────
        device = None
        if device_id:
            device, was_created = TrustedDevice.objects.get_or_create(
                user=user, device_id=device_id,
                defaults={
                    "device_name": device_name,
                    "ip_address": _client_ip(request),
                    "user_agent": _user_agent(request),
                    "is_authorized": not security.require_device_authorization,
                },
            )
            if not was_created:
                device.last_seen = timezone.now()
                device.ip_address = _client_ip(request)
                if device_name:
                    device.device_name = device_name
                device.save()

            if security.require_device_authorization and not device.is_authorized:
                code = _issue_otp(user, "device_auth", device=device)
                write_audit_log(user, "other", entity="TrustedDevice", entity_id=device.id,
                                 description="New device pending authorization", request=request)
                return Response({
                    "requires_device_authorization": True,
                    "message": f"New device detected. Enter the verification code sent via "
                               f"{security.two_factor_method} to authorize it.",
                    "device_id": device.device_id,
                    "username": user.username,
                }, status=status.HTTP_200_OK)

        # ── 5. Two-factor authentication ────────────────────────────────────
        if security.two_factor_enabled:
            code = _issue_otp(user, "login_2fa", device=device)
            return Response({
                "requires_2fa": True,
                "method": security.two_factor_method,
                "message": f"Verification code sent via {security.two_factor_method}.",
                "username": user.username,
                "device_id": device.device_id if device else None,
            }, status=status.HTTP_200_OK)

        # ── 6. All clear — issue a session token ────────────────────────────
        token = _issue_token(user, device)
        write_audit_log(user, "login", entity="User", entity_id=user.id, request=request)
        return Response(_login_success_payload(user, token, device))


class VerifyOTPView(APIView):
    """Completes login for accounts with 2FA and/or device authorization enabled."""
    authentication_classes = []
    permission_classes = []
    throttle_classes = [UsernameBruteForceThrottle]

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        code = str(request.data.get("code", "")).strip()
        # purpose is NOT trusted from client — server derives it from the actual pending OTP
        device_id = str(request.data.get("device_id", "")).strip()

        user = User.objects.filter(username__iexact=username).first()
        if not user:
            return Response({"error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

        # Server-derived purpose: most recent unexpired OTP, fallback to any pending for accurate error
        otp = OneTimePasscode.objects.filter(user=user, is_used=False, expires_at__gt=timezone.now()).order_by("-created_at").first()
        if otp is None:
            otp = OneTimePasscode.objects.filter(user=user, is_used=False).order_by("-created_at").first()
        purpose = otp.purpose if otp else "login_2fa"
        if purpose == "password_reset":
            return Response(
                {"error": "Invalid verification request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

# If device is pending authorization, force device_auth regardless of pending
        # If the client supplied purpose differs from server purpose, we still validate against server OTP's code
        # (prevents cross-purpose OTP replay)
        if not otp:
            return Response({"error": "No pending verification code. Please log in again."},
                             status=status.HTTP_400_BAD_REQUEST)
        if otp.is_expired():
            return Response({"error": "Verification code expired. Please request a new one."},
                             status=status.HTTP_400_BAD_REQUEST)
        if otp.attempts >= 5:
            return Response({"error": "Too many incorrect attempts. Please request a new code."},
                             status=status.HTTP_429_TOO_MANY_REQUESTS)

        if not otp.check_code(code):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            return Response({"error": "Invalid verification code."}, status=status.HTTP_400_BAD_REQUEST)

        device = TrustedDevice.objects.filter(user=user, device_id=device_id).first() if device_id else None

        if otp.device_id is not None:
            if device is None or device.id != otp.device_id:
                return Response({"error": "Verification code is bound to a different device."},
                                 status=status.HTTP_400_BAD_REQUEST)

        otp.is_used = True
        otp.save(update_fields=["is_used"])

        if purpose == "device_auth":
            if device:
                device.is_authorized = True
                device.save(update_fields=["is_authorized"])
                write_audit_log(user, "update", entity="TrustedDevice", entity_id=device.id,
                                 description="Device authorized via OTP", request=request)

            security = SecuritySettings.load()
            if security.two_factor_enabled:
                new_code = _issue_otp(user, "login_2fa", device=device)
                return Response({
                    "requires_2fa": True,
                    "method": security.two_factor_method,
                    "message": "Device authorized. Enter the login verification code.",
                    "username": user.username,
                    "device_id": device.device_id if device else None,
                })

        token = _issue_token(user, device)
        write_audit_log(user, "login", entity="User", entity_id=user.id, request=request)
        return Response(_login_success_payload(user, token, device))


class ResendOTPView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [UsernameBruteForceThrottle]

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        # purpose is NOT trusted from client — derive from most recent pending OTP or device state
        device_id = str(request.data.get("device_id", "")).strip()

        user = User.objects.filter(username__iexact=username).first()
        if not user:
            return Response({"error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

        pending = OneTimePasscode.objects.filter(user=user, is_used=False, expires_at__gt=timezone.now()).order_by("-created_at").first()
        if pending is None:
            pending = OneTimePasscode.objects.filter(user=user, is_used=False).order_by("-created_at").first()
        purpose = pending.purpose if pending else "login_2fa"

        if purpose == "password_reset":
            return Response(
                {"error": "Invalid verification request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # If device is pending authorization, force device_auth regardless of pending
        if device_id:
            dev = TrustedDevice.objects.filter(user=user, device_id=device_id).first()
            if dev and not dev.is_authorized:
                purpose = "device_auth"

        device = TrustedDevice.objects.filter(user=user, device_id=device_id).first() if device_id else None
        code = _issue_otp(user, purpose, device=device)
        security = SecuritySettings.load()
        return Response({
            "message": f"A new code has been sent via {security.two_factor_method}.",
        })


# ═══════════════════════════════════════════════════════════════════════════
# Authenticated session management
# ═══════════════════════════════════════════════════════════════════════════
class LogoutView(APIView):
    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Preserve the authenticated actor for AuditMiddleware, which runs
        # after this view and may otherwise lose the pre-logout identity.
        raw_request = getattr(request, "_request", request)
        raw_request._pre_logout_user = request.user

        token = request.auth
        if isinstance(token, AuthToken):
            token.is_revoked = True
            token.save(update_fields=["is_revoked"])
        write_audit_log(request.user, "logout", entity="User", entity_id=request.user.id, request=request)
        return Response({"message": "Logged out successfully."})


class MeView(APIView):
    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_login_success_payload(request.user, request.auth,
                                                 request.auth.device if request.auth else None))


class MySessionsView(APIView):
    """List every active (non-revoked) session/device for the logged-in user."""
    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tokens = AuthToken.objects.filter(user=request.user, is_revoked=False).select_related("device")
        data = [{
            "id": t.id,
            "device_name": t.device.device_name if t.device else "Unknown device",
            "device_id": t.device.device_id if t.device else None,
            "created_at": t.created_at,
            "last_used_at": t.last_used_at,
            "is_current": request.auth is not None and t.id == request.auth.id,
        } for t in tokens]
        return Response(data)


class RevokeSessionView(APIView):
    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        token = get_object_or_404(AuthToken, pk=pk, user=request.user)
        token.is_revoked = True
        token.save(update_fields=["is_revoked"])
        return Response({"message": "Session revoked."})


# ═══════════════════════════════════════════════════════════════════════════
# Password management (policy-enforced)
# ═══════════════════════════════════════════════════════════════════════════
class ChangePasswordView(APIView):
    """For an already-logged-in user changing their password voluntarily."""
    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = str(request.data.get("old_password", ""))
        new_password = str(request.data.get("new_password", ""))

        if not request.user.check_password(old_password):
            return Response({"error": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, errors = validate_password_against_policy(new_password)
        if not is_valid:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save()

        profile, _created = UserProfile.objects.get_or_create(user=request.user)
        profile.password_changed_at = timezone.now()
        profile.save()

        # Changing your password logs out every other session — standard security hygiene.
        current_token_id = request.auth.id if request.auth else None
        AuthToken.objects.filter(user=request.user).exclude(pk=current_token_id).update(is_revoked=True)

        write_audit_log(request.user, "update", entity="User", entity_id=request.user.id,
                         description="Password changed", request=request)
        return Response({"message": "Password changed successfully. Other active sessions were logged out."})


class ExpiredPasswordChangeView(APIView):
    """
    For the flow where LoginView returned `password_expired: true` — the
    user isn't logged in yet, so this re-verifies the OLD password directly
    rather than requiring a token.
    """
    authentication_classes = []
    permission_classes = []
    # Re-verifies real credentials, so it must be throttled exactly like the
    # login endpoint — otherwise it becomes a lockout-free brute-force window.
    throttle_classes = [UsernameBruteForceThrottle]

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        old_password = str(request.data.get("old_password", ""))
        new_password = str(request.data.get("new_password", ""))

        user = authenticate(request, username=username, password=old_password)
        if not user:
            return Response({"error": "Invalid current credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        is_valid, errors = validate_password_against_policy(new_password)
        if not is_valid:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        profile, _created = UserProfile.objects.get_or_create(user=user)
        profile.password_changed_at = timezone.now()
        profile.save()

        write_audit_log(user, "update", entity="User", entity_id=user.id,
                         description="Password changed (expired-password flow)", request=request)
        return Response({"message": "Password updated. Please log in with your new password."})


# ═══════════════════════════════════════════════════════════════════════════
# Admin utilities
# ═══════════════════════════════════════════════════════════════════════════
class AdminUnlockAccountView(APIView):
    """Clears an account's recent failed-attempt history so it can log in immediately."""
    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        if not username:
            return Response({"error": "username is required."}, status=status.HTTP_400_BAD_REQUEST)

        security = SecuritySettings.load()
        window_start = timezone.now() - timedelta(minutes=security.lockout_duration_minutes)
        deleted, _ = LoginAttempt.objects.filter(
            username__iexact=username, was_successful=False, created_at__gte=window_start
        ).delete()

        write_audit_log(request.user, "update", entity="User", entity_id=username,
                         description="Account unlocked by admin", request=request)
        return Response({"message": f"{username} has been unlocked.", "cleared_attempts": deleted})


class AdminRevokeUserSessionsView(APIView):
    """Force-logout every active session for a given user (e.g. after a role change or a suspected compromise)."""
    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        updated = AuthToken.objects.filter(user=target, is_revoked=False).update(is_revoked=True)
        write_audit_log(request.user, "update", entity="User", entity_id=target.id,
                         description="All sessions revoked by admin", request=request)
        return Response({"message": f"Revoked {updated} active session(s) for {target.username}."})


# ═══════════════════════════════════════════════════════════════════════════
# Password Reset
# ═══════════════════════════════════════════════════════════════════════════
class RequestPasswordResetView(APIView):
    """Send a one-time code to the user's email for password reset.

    Always returns 200 OK to prevent email enumeration.
    """
    authentication_classes = []
    permission_classes = []
    throttle_classes = [UsernameBruteForceThrottle]

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is not None:
            try:
                _issue_otp(user, "password_reset", digits=6, ttl_minutes=15)
                write_audit_log(user, "other", entity="User", entity_id=user.id,
                                 description="Password reset requested", request=request)
            except Exception:
                logger.exception("Failed to send password reset code to %s", email)
        # Always return success to prevent email enumeration.
        return Response({"message": "If an account with that email exists, a reset code has been sent."})


class ConfirmPasswordResetView(APIView):
    """Verify the reset code and set a new password."""
    authentication_classes = []
    permission_classes = []
    throttle_classes = [UsernameBruteForceThrottle]

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        code = str(request.data.get("code", "")).strip()
        new_password = str(request.data.get("new_password", ""))

        if not email or not code or not new_password:
            return Response({"error": "Email, code, and new_password are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            return Response({"error": "Invalid reset request."}, status=status.HTTP_400_BAD_REQUEST)

        otp = OneTimePasscode.objects.filter(
            user=user, purpose="password_reset", is_used=False
        ).order_by("-created_at").first()
        if not otp:
            return Response({"error": "No pending reset code. Please request a new one."},
                            status=status.HTTP_400_BAD_REQUEST)
        if otp.is_expired():
            return Response({"error": "Reset code expired. Please request a new one."},
                            status=status.HTTP_400_BAD_REQUEST)
        if otp.attempts >= 5:
            return Response({"error": "Too many incorrect attempts. Please request a new code."},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        if not otp.check_code(code):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            return Response({"error": "Invalid reset code."}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, errors = validate_password_against_policy(new_password)
        if not is_valid:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        otp.is_used = True
        otp.save(update_fields=["is_used"])

        user.set_password(new_password)
        user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.password_changed_at = timezone.now()
        profile.save()

        # Invalidate all other sessions for security.
        AuthToken.objects.filter(user=user).update(is_revoked=True)
        write_audit_log(user, "update", entity="User", entity_id=user.id,
                         description="Password reset via email code", request=request)
        return Response({"message": "Password reset successfully. Please log in with your new password."})
