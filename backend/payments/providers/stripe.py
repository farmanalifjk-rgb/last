from django.conf import settings

from .base import (
    BasePaymentProvider,
    PaymentSnapshot,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderVerificationError,
    RefundSnapshot,
)


class StripeProvider(BasePaymentProvider):
    """Thin Stripe SDK adapter. It never creates Ledgerline orders, settlements, journals, or refunds."""

    code = "stripe"
    display_name = "Stripe sandbox"
    client_integration = "stripe_payment_element"
    webhook_signature_header = "Stripe-Signature"

    def ensure_configured(self):
        self._require_test_configuration()
        return True

    def public_configuration(self):
        secret = getattr(settings, "STRIPE_SECRET_KEY", "")
        publishable = getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")
        webhook = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        configured = secret.startswith("sk_test_") and webhook.startswith("whsec_")
        return {
            "provider": self.code,
            "display_name": self.display_name,
            "environment": "test",
            "configured": configured,
            "actions_enabled": configured,
            "client_integration": self.client_integration if configured and publishable.startswith("pk_test_") else "",
            "publishable_key": publishable if publishable.startswith("pk_test_") else "",
            "webhook_configured": bool(webhook.startswith("whsec_")),
            "message": "Stripe sandbox configuration is required." if not configured else "Stripe sandbox configuration is available.",
        }

    def _require_test_configuration(self):
        secret = getattr(settings, "STRIPE_SECRET_KEY", "")
        if not secret.startswith("sk_test_"):
            raise ProviderConfigurationError("Stripe sandbox configuration is required before provider actions are available.")
        return secret

    @staticmethod
    def _payment_snapshot(intent):
        last_error = intent.get("last_payment_error") or {}
        return PaymentSnapshot(
            provider_payment_id=str(intent.get("id", "")),
            status=str(intent.get("status", "")),
            amount_minor=int(intent.get("amount", 0)),
            currency=str(intent.get("currency", "")).upper(),
            metadata=dict(intent.get("metadata") or {}),
            client_secret=str(intent.get("client_secret", "")),
            failure_code=str(last_error.get("code", "")),
            failure_reason=str(last_error.get("message", ""))[:255],
        )

    @staticmethod
    def _refund_snapshot(refund):
        failure_reason = refund.get("failure_reason") or ""
        return RefundSnapshot(
            provider_refund_id=str(refund.get("id", "")),
            status=str(refund.get("status", "")),
            amount_minor=int(refund.get("amount", 0)),
            currency=str(refund.get("currency", "")).upper(),
            failure_code=str(refund.get("failure_reason", ""))[:80] if refund.get("failure_reason") else "",
            failure_reason=str(failure_reason)[:255],
        )

    def create_payment_intent(self, *, amount_minor, currency, metadata, idempotency_key):
        try:
            import stripe

            intent = stripe.PaymentIntent.create(
                amount=amount_minor,
                currency=currency.lower(),
                automatic_payment_methods={"enabled": True},
                metadata=metadata,
                api_key=self._require_test_configuration(),
                idempotency_key=idempotency_key,
            )
            return self._payment_snapshot(intent)
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            raise ProviderRequestError("Stripe could not create the payment operation. Its status must be verified before retrying.") from exc

    def retrieve_payment_intent(self, provider_payment_id):
        try:
            import stripe

            intent = stripe.PaymentIntent.retrieve(provider_payment_id, api_key=self._require_test_configuration())
            return self._payment_snapshot(intent)
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            raise ProviderRequestError("Stripe payment status could not be retrieved.") from exc

    def cancel_payment_intent(self, provider_payment_id):
        try:
            import stripe

            intent = stripe.PaymentIntent.cancel(provider_payment_id, api_key=self._require_test_configuration())
            return self._payment_snapshot(intent)
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            raise ProviderRequestError("Stripe payment cancellation could not be verified.") from exc

    def create_refund(self, *, provider_payment_id, amount_minor, idempotency_key):
        try:
            import stripe

            refund = stripe.Refund.create(
                payment_intent=provider_payment_id,
                amount=amount_minor,
                api_key=self._require_test_configuration(),
                idempotency_key=idempotency_key,
            )
            return self._refund_snapshot(refund)
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            raise ProviderRequestError("Stripe refund status could not be established.") from exc

    def retrieve_refund(self, provider_refund_id):
        try:
            import stripe

            refund = stripe.Refund.retrieve(provider_refund_id, api_key=self._require_test_configuration())
            return self._refund_snapshot(refund)
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            raise ProviderRequestError("Stripe refund status could not be retrieved.") from exc

    def verify_webhook(self, *, raw_body, signature):
        secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        if not secret.startswith("whsec_"):
            raise ProviderConfigurationError("Stripe webhook signing configuration is required.")
        if not signature:
            raise ProviderVerificationError("Stripe signature is required.")
        try:
            import stripe

            return stripe.Webhook.construct_event(raw_body, signature, secret)
        except Exception as exc:
            raise ProviderVerificationError("Stripe webhook signature verification failed.") from exc
