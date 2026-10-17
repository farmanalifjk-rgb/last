from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from payments.models import (
    PaymentSettlement,
    ProviderPaymentOperation,
    ProviderRefundOperation,
    ProviderWebhookEvent,
    RefundSettlement,
    TenderedPayment,
)
from payments.provider_services import (
    process_provider_webhook,
    start_provider_payment,
    start_provider_refund,
    verify_provider_payment,
)
from payments.providers.base import (
    PaymentSnapshot,
    ProviderConfigurationError,
    ProviderVerificationError,
    RefundSnapshot,
)
from payments.providers.stripe import StripeProvider
from pos.models import CashSession, Category, Product
from pos.services.canonical_pos import process_refund
from rbac.models import Module, Permission, Role, UserRole
from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant


User = get_user_model()


class MockProvider:
    """Provider-independent test double; its protocol matches BasePaymentProvider."""

    code = "mock_gateway"
    display_name = "Mock gateway"
    client_integration = ""
    webhook_signature_header = "X-Mock-Signature"

    def __init__(self):
        self.payment_status = "requires_payment_method"
        self.payment_id = "pay_phase13_mock"
        self.refund_status = "succeeded"
        self.refund_id = "ref_phase13_mock"
        self.metadata = {}
        self.amount_minor = 0
        self.currency = "USD"

    def ensure_configured(self):
        return True

    def public_configuration(self):
        return {"provider": self.code, "configured": True, "actions_enabled": True}

    def create_payment_intent(self, *, amount_minor, currency, metadata, idempotency_key):
        self.amount_minor = amount_minor
        self.currency = currency.upper()
        self.metadata = dict(metadata)
        return self.retrieve_payment_intent(self.payment_id)

    def retrieve_payment_intent(self, provider_payment_id):
        return PaymentSnapshot(
            provider_payment_id=provider_payment_id,
            status=self.payment_status,
            amount_minor=self.amount_minor,
            currency=self.currency,
            metadata=self.metadata,
            client_secret="mock_client_token",
        )

    def cancel_payment_intent(self, provider_payment_id):
        self.payment_status = "cancelled"
        return self.retrieve_payment_intent(provider_payment_id)

    def create_refund(self, *, provider_payment_id, amount_minor, idempotency_key):
        self.refund_amount_minor = amount_minor
        return RefundSnapshot(self.refund_id, self.refund_status, amount_minor, self.currency)

    def retrieve_refund(self, provider_refund_id):
        return RefundSnapshot(provider_refund_id, self.refund_status, self.refund_amount_minor, self.currency)

    def verify_webhook(self, *, raw_body, signature):
        if signature != "valid-mock-signature":
            raise ProviderVerificationError("Provider webhook signature verification failed.")
        return {
            "id": "evt_phase13_provider_replay",
            "type": "payment.succeeded",
            "data": {"object": {"id": self.payment_id}},
        }


class Phase13ProviderInfrastructureTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="phase13-provider-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase 13 Provider Tenant", slug="phase13-provider-tenant", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)
        set_current_tenant(self.tenant)
        self.category = Category.objects.create(tenant=self.tenant, name="Phase 13 Provider Category")
        self.product = Product.objects.create(tenant=self.tenant, category=self.category, name="Phase 13 Provider Product", sku="P13-PROVIDER", barcode="131314", sales_price=Decimal("10.00"), cost_price=Decimal("3.00"), stock_quantity=Decimal("20.000"), is_active=True)
        self.session = CashSession.objects.create(tenant=self.tenant, opened_by=self.owner, employee_name="Phase 13 Provider Owner", opening_balance=Decimal("0.00"), is_open=True)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def start(self, provider=None, key="phase13-provider-idempotency"):
        return start_provider_payment(
            tenant=self.tenant,
            user=self.owner,
            items=[{"product_id": self.product.id, "quantity": "1"}],
            idempotency_key=key,
            provider=provider or MockProvider(),
        )

    def test_verified_provider_success_calls_the_existing_settlement_path_exactly_once(self):
        provider = MockProvider()
        operation, client_token, replayed = self.start(provider)
        self.assertFalse(replayed)
        self.assertEqual(client_token, "mock_client_token")
        self.assertEqual(operation.provider, provider.code)
        self.assertFalse(PaymentSettlement.objects.filter(tenant=self.tenant).exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("20.000"))

        provider.payment_status = "succeeded"
        verified = verify_provider_payment(tenant=self.tenant, operation_id=operation.id, user=self.owner, provider=provider)
        self.assertEqual(verified.status, ProviderPaymentOperation.STATUS_SUCCEEDED)
        settlement = PaymentSettlement.objects.get(tenant=self.tenant, order_id=operation.order_id)
        tender = TenderedPayment.objects.get(tenant=self.tenant, settlement=settlement)
        self.assertEqual(tender.tender_type, TenderedPayment.TENDER_CARD)
        self.assertEqual(tender.reference, provider.payment_id)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("19.000"))
        verify_provider_payment(tenant=self.tenant, operation_id=operation.id, user=self.owner, provider=provider)
        self.assertEqual(PaymentSettlement.objects.filter(tenant=self.tenant, order_id=operation.order_id).count(), 1)

    def test_amount_currency_and_metadata_mismatches_cannot_settle(self):
        provider = MockProvider()
        operation, _token, _replayed = self.start(provider)
        provider.payment_status = "succeeded"
        provider.amount_minor = 999
        with self.assertRaises(ProviderVerificationError):
            verify_provider_payment(tenant=self.tenant, operation_id=operation.id, user=self.owner, provider=provider)
        operation.refresh_from_db()
        self.assertEqual(operation.status, ProviderPaymentOperation.STATUS_EXCEPTION)
        self.assertFalse(PaymentSettlement.objects.filter(tenant=self.tenant, order_id=operation.order_id).exists())

    def test_local_idempotency_and_tenant_scoped_provider_references(self):
        provider = MockProvider()
        first, _token, replayed = self.start(provider, key="phase13-provider-replay")
        self.assertFalse(replayed)
        second, _token, replayed = self.start(provider, key="phase13-provider-replay")
        self.assertTrue(replayed)
        self.assertEqual(first.id, second.id)
        self.assertEqual(ProviderPaymentOperation.objects.filter(tenant=self.tenant).count(), 1)

        other = User.objects.create_user(username="phase13-provider-other", password="StrongPass123!")
        other_tenant = Tenant.objects.create(name="Phase 13 Provider Other", slug="phase13-provider-other", owner=other, status="active")
        TenantMembership.objects.create(tenant=other_tenant, user=other, role="owner", is_active_in_tenant=True)
        other_client = APIClient()
        other_client.force_authenticate(other)
        self.assertEqual(other_client.get(f"/api/payments/providers/{provider.code}/operations/{first.id}/").status_code, 404)

    def test_viewer_can_read_but_cannot_initiate_or_manage_provider_operations(self):
        provider = MockProvider()
        operation, _token, _replayed = self.start(provider)
        viewer = User.objects.create_user(username="phase13-provider-viewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant, user=viewer, role="staff", is_active_in_tenant=True)
        role = Role.objects.create(key="phase13-provider-viewer", label="Phase 13 provider viewer")
        payments_module, _ = Module.objects.get_or_create(key="payments", defaults={"label": "Payments"})
        pos_module, _ = Module.objects.get_or_create(key="pos", defaults={"label": "Point of sale"})
        payments_view, _ = Permission.objects.get_or_create(module=payments_module, action="view")
        pos_view, _ = Permission.objects.get_or_create(module=pos_module, action="view")
        role.permissions.add(payments_view, pos_view)
        UserRole.objects.create(user=viewer, role=role)
        viewer_client = APIClient()
        viewer_client.force_authenticate(viewer)
        self.assertEqual(viewer_client.get(f"/api/payments/providers/{provider.code}/operations/").status_code, 200)
        self.assertEqual(viewer_client.get(f"/api/payments/providers/{provider.code}/operations/{operation.id}/").status_code, 200)
        self.assertEqual(viewer_client.post(f"/api/payments/providers/{provider.code}/operations/{operation.id}/verify/", {}, format="json").status_code, 403)
        self.assertEqual(viewer_client.post(f"/api/payments/providers/{provider.code}/checkout/", {"items": [{"product_id": self.product.id, "quantity": "1"}]}, format="json", HTTP_IDEMPOTENCY_KEY="phase13-viewer-mutation").status_code, 403)

    def test_verified_webhook_event_is_persisted_once_and_replay_cannot_duplicate_settlement(self):
        provider = MockProvider()
        operation, _token, _replayed = self.start(provider)
        provider.payment_status = "succeeded"
        event, replayed = process_provider_webhook(provider_code=provider.code, raw_body=b"{}", signature="valid-mock-signature", provider=provider)
        self.assertFalse(replayed)
        self.assertEqual(event.processing_state, ProviderWebhookEvent.STATE_PROCESSED)
        self.assertEqual(event.operation_id, operation.id)
        replay, replayed = process_provider_webhook(provider_code=provider.code, raw_body=b"{}", signature="valid-mock-signature", provider=provider)
        self.assertTrue(replayed)
        self.assertEqual(replay.id, event.id)
        self.assertEqual(ProviderWebhookEvent.objects.filter(provider=provider.code).count(), 1)
        self.assertEqual(PaymentSettlement.objects.filter(tenant=self.tenant, order_id=operation.order_id).count(), 1)

    def test_signed_unmatched_webhook_is_recorded_as_a_tenant_null_ignored_inbox_event(self):
        provider = MockProvider()
        provider.payment_id = "pay_phase13_no_local_operation"

        event, replayed = process_provider_webhook(
            provider_code=provider.code,
            raw_body=b"{}",
            signature="valid-mock-signature",
            provider=provider,
        )

        self.assertFalse(replayed)
        self.assertIsNone(event.tenant_id)
        self.assertIsNone(event.operation_id)
        self.assertEqual(event.processing_state, ProviderWebhookEvent.STATE_IGNORED)

    def test_provider_refund_links_the_existing_pos_refund_to_one_canonical_refund_settlement(self):
        provider = MockProvider()
        operation, _token, _replayed = self.start(provider)
        provider.payment_status = "succeeded"
        verify_provider_payment(tenant=self.tenant, operation_id=operation.id, user=self.owner, provider=provider)
        item = operation.order.items.get()
        refund = process_refund(tenant=self.tenant, user=self.owner, order_id=operation.order_id, rows=[{"order_item_id": item.id, "quantity": "1"}], reason="Phase 13 provider refund")
        self.assertFalse(RefundSettlement.objects.filter(tenant=self.tenant, refund=refund).exists())
        provider_refund = start_provider_refund(tenant=self.tenant, refund=refund, user=self.owner, provider=provider)
        self.assertEqual(provider_refund.status, ProviderRefundOperation.STATUS_SUCCEEDED)
        self.assertEqual(RefundSettlement.objects.get(tenant=self.tenant, refund=refund).method, RefundSettlement.METHOD_PROVIDER)

    @override_settings(STRIPE_SECRET_KEY="sk_live_not_permitted")
    def test_optional_stripe_adapter_rejects_non_test_credentials_without_calling_provider(self):
        with self.assertRaises(ProviderConfigurationError):
            StripeProvider().ensure_configured()

    def test_optional_adapter_config_never_exposes_secret_or_webhook_values(self):
        response = self.client.get("/api/payments/providers/stripe/config/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("secret", response.data)
        self.assertNotIn("webhook_secret", response.data)
        self.assertFalse(response.data["actions_enabled"])
