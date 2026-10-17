"""
models_auth.py
Backing models for the real authentication layer that enforces the Security
settings tab: expiring session tokens (sliding window = SecuritySettings
.session_timeout_minutes) tied to a trusted device, and one-time passcodes
used for both 2FA and new-device authorization.

Kept in its own module (rather than models_settings.py) since it's
behavioural/auth machinery rather than a "settings group" — imported into
models.py the same way.
"""
import secrets
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.db import models
from django.utils import timezone

from system.models import TrustedDevice


def generate_token_key():
    return secrets.token_hex(32)


class AuthToken(models.Model):
    """
    A lightweight bearer token, one per logged-in device/session. Session
    timeout is enforced as a sliding window: every authenticated request
    pushes `last_used_at` forward (see pos/authentication.py); once the gap
    between requests exceeds SecuritySettings.session_timeout_minutes the
    token is auto-revoked on next use.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_tokens")
    device = models.ForeignKey(TrustedDevice, on_delete=models.SET_NULL, null=True, blank=True, related_name="tokens")
    key = models.CharField(max_length=64, unique=True, default=generate_token_key, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(default=timezone.now)
    is_revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Token({self.user}, {'revoked' if self.is_revoked else 'active'})"

    def is_expired(self, timeout_minutes):
        if not timeout_minutes:
            return False
        return timezone.now() > self.last_used_at + timezone.timedelta(minutes=timeout_minutes)

    def touch(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])


class OneTimePasscode(models.Model):
    PURPOSE_CHOICES = [
        ("login_2fa", "Login 2FA"),
        ("device_auth", "Device Authorization"),
        ("password_reset", "Password Reset"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps")
    device = models.ForeignKey(TrustedDevice, on_delete=models.CASCADE, null=True, blank=True, related_name="otps")
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    code_hash = models.CharField(max_length=200)
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP({self.user}, {self.purpose})"

    def set_code(self, raw_code):
        self.code_hash = make_password(raw_code)

    def check_code(self, raw_code):
        return check_password(raw_code, self.code_hash)

    def is_expired(self):
        return timezone.now() > self.expires_at


