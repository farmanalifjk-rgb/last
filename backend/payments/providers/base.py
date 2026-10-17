from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from abc import ABC, abstractmethod


class ProviderError(Exception):
    """Safe base error for provider failures; never include credentials or raw payloads."""


class ProviderConfigurationError(ProviderError):
    pass


class ProviderVerificationError(ProviderError):
    pass


class ProviderRequestError(ProviderError):
    pass


class BasePaymentProvider(ABC):
    """Provider-neutral contract; adapters must not create Ledgerline financial effects."""

    code = ""
    display_name = ""
    client_integration = ""
    webhook_signature_header = "X-Provider-Signature"

    def public_configuration(self):
        """Return only browser-safe capability metadata; never credentials or signing secrets."""
        configured = False
        try:
            self.ensure_configured()
            configured = True
        except ProviderConfigurationError:
            pass
        return {
            "provider": self.code,
            "display_name": self.display_name or self.code,
            "environment": "sandbox",
            "configured": configured,
            "actions_enabled": configured,
            "client_integration": self.client_integration if configured else "",
            "publishable_key": "",
            "webhook_configured": configured,
            "message": "Provider sandbox configuration is required." if not configured else "Provider sandbox configuration is available.",
        }

    @abstractmethod
    def ensure_configured(self):
        """Raise ProviderConfigurationError unless this optional adapter is safely configured."""

    @abstractmethod
    def create_payment_intent(self, *, amount_minor, currency, metadata, idempotency_key):
        pass

    @abstractmethod
    def retrieve_payment_intent(self, provider_payment_id):
        pass

    @abstractmethod
    def cancel_payment_intent(self, provider_payment_id):
        pass

    @abstractmethod
    def create_refund(self, *, provider_payment_id, amount_minor, idempotency_key):
        pass

    @abstractmethod
    def retrieve_refund(self, provider_refund_id):
        pass

    @abstractmethod
    def verify_webhook(self, *, raw_body, signature):
        pass


@dataclass(frozen=True)
class PaymentSnapshot:
    provider_payment_id: str
    status: str
    amount_minor: int
    currency: str
    metadata: dict
    client_secret: str = ""
    failure_code: str = ""
    failure_reason: str = ""


@dataclass(frozen=True)
class RefundSnapshot:
    provider_refund_id: str
    status: str
    amount_minor: int
    currency: str
    failure_code: str = ""
    failure_reason: str = ""


def to_minor_units(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor_units(amount_minor: int) -> Decimal:
    return (Decimal(int(amount_minor)) / Decimal("100")).quantize(Decimal("0.01"))
