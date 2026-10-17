from django.conf import settings


class ProductionSecurityHeadersMiddleware:
    """Add browser hardening headers without coupling policy to development tooling."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.DEBUG:
            return response

        response.setdefault(
            "Content-Security-Policy",
            "; ".join(
                [
                    "default-src 'self'",
                    "base-uri 'self'",
                    "object-src 'none'",
                    "frame-ancestors 'none'",
                    "form-action 'self'",
                    "script-src 'self'",
                    "style-src 'self' https://fonts.googleapis.com",
                    "font-src 'self' https://fonts.gstatic.com data:",
                    "img-src 'self' data: https:",
                    "connect-src 'self'",
                ]
            ),
        )
        response.setdefault(
            "Permissions-Policy",
            "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
        )
        return response


# Credential-at-rest encryption -------------------------------------------------
#
# FBR/ESD credentials are reversible secrets because the application must send
# them to the external fiscal authority/device.  They therefore must not be
# hashed.  Fernet provides authenticated symmetric encryption; the dedicated
# production key is supplied through the environment and is never stored in
# the database.
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured
from django.db import models


_ENCRYPTED_PREFIX = "enc:v1:"


def _credential_fernet():
    key = os.environ.get("FBR_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    if not key:
        # Development/test fallback: derive a stable key from the existing
        # Django secret so local setup remains simple. Production explicitly
        # requires the dedicated key below.
        if os.environ.get("DJANGO_ENV", "development").strip().lower() == "production":
            raise ImproperlyConfigured(
                "FBR_CREDENTIAL_ENCRYPTION_KEY must be set in production."
            )
        key = base64.urlsafe_b64encode(
            hashlib.sha256(str(settings.SECRET_KEY).encode("utf-8")).digest()
        ).decode("ascii")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            "FBR_CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


class EncryptedCredentialField(models.CharField):
    """CharField that encrypts reversible credentials before database storage.

    Values returned to application code are plaintext because callers need to
    transmit the credential to the external provider.  The database value is
    an authenticated Fernet ciphertext prefixed with ``enc:v1:``.

    Plaintext legacy rows remain readable so deployments can migrate without a
    flag day. Any subsequent save rewrites them as encrypted values.
    """

    description = "Encrypted reversible credential"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        if isinstance(value, str) and value.startswith(_ENCRYPTED_PREFIX):
            return value
        token = _credential_fernet().encrypt(value.encode("utf-8")).decode("ascii")
        return f"{_ENCRYPTED_PREFIX}{token}"

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        if not isinstance(value, str) or not value.startswith(_ENCRYPTED_PREFIX):
            # Backward compatibility for pre-hardening rows. A migration
            # rewrites existing rows, so this is only a safety net.
            return value
        token = value[len(_ENCRYPTED_PREFIX):]
        try:
            return _credential_fernet().decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError, TypeError) as exc:
            raise ImproperlyConfigured(
                "Stored credential cannot be decrypted. Check FBR_CREDENTIAL_ENCRYPTION_KEY."
            ) from exc
