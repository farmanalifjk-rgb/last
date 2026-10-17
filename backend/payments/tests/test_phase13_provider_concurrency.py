import threading
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from payments.models import (
    PaymentSettlement,
    ProviderPaymentOperation,
    ProviderRefundOperation,
    ProviderWebhookEvent,
    RefundSettlement,
)
from payments.provider_services import (
    process_provider_webhook,
    start_provider_payment,
    start_provider_refund,
    verify_provider_payment,
)
from payments.providers.base import (
    PaymentSnapshot,
    ProviderVerificationError,
    RefundSnapshot,
)
from pos.models import CashSession, Category, Product, Refund
from pos.services.canonical_pos import process_refund
from inventory.models import StockReservation
from saas.models import Tenant, TenantMembership


User = get_user_model()


class ConcurrentMockProvider:
    """Thread-safe provider-neutral test double used only for PostgreSQL lock tests."""

    code = "concurrency_mock"
    display_name = "Concurrency mock gateway"
    client_integration = ""
    webhook_signature_header = "X-Concurrency-Signature"

    def __init__(self):
        self.payment_status = "requires_payment_method"
        self.refund_status = "succeeded"
        self.payment_id = "pay_phase13_concurrency"
        self.refund_id = "ref_phase13_concurrency"
        self.amount_minor = 0
        self.refund_amount_minor = 0
        self.currency = "USD"
        self.metadata = {}
        self.refund_create_calls = 0
        self._lock = threading.Lock()

    def ensure_configured(self):
        return True

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
            client_secret="concurrency_client_token",
        )

    def cancel_payment_intent(self, provider_payment_id):
        self.payment_status = "cancelled"
        return self.retrieve_payment_intent(provider_payment_id)

    def create_refund(self, *, provider_payment_id, amount_minor, idempotency_key):
        with self._lock:
            self.refund_create_calls += 1
        self.refund_amount_minor = amount_minor
        return RefundSnapshot(self.refund_id, self.refund_status, amount_minor, self.currency)

    def retrieve_refund(self, provider_refund_id):
        return RefundSnapshot(provider_refund_id, self.refund_status, self.refund_amount_minor, self.currency)

    def verify_webhook(self, *, raw_body, signature):
        if signature != "valid-concurrency-signature":
            raise ProviderVerificationError("Provider webhook signature verification failed.")
        return {
            "id": "evt_phase13_concurrency_replay",
            "type": "payment.succeeded",
            "data": {"object": {"id": self.payment_id}},
        }


@skipUnless(connection.vendor == "postgresql", "Provider locking tests require PostgreSQL.")
class PostgreSQLProviderConcurrencyTests(TransactionTestCase):
    """Exercise the provider-neutral financial bridge with real PostgreSQL row locks."""

    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user(username="phase13-pg-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase 13 PostgreSQL Tenant", slug="phase13-pg-tenant", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)
        self.category = Category.objects.create(tenant=self.tenant, name="Phase 13 PostgreSQL Category")
        self.product = Product.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Phase 13 PostgreSQL Product",
            sku="P13-PG",
            barcode="1313001",
            sales_price=Decimal("10.00"),
            cost_price=Decimal("3.00"),
            stock_quantity=Decimal("30.000"),
            is_active=True,
        )
        self.session = CashSession.objects.create(
            tenant=self.tenant,
            opened_by=self.owner,
            employee_name="Phase 13 PostgreSQL Owner",
            opening_balance=Decimal("0.00"),
            is_open=True,
        )

    def _run_parallel(self, callback):
        barrier = threading.Barrier(2)
        results = []
        result_lock = threading.Lock()

        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                callback(index)
                result = "ok"
            except Exception as exc:  # Each expected losing path is asserted by the caller.
                result = f"{type(exc).__name__}: {exc}"
            finally:
                connections.close_all()
            with result_lock:
                results.append(result)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=25)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "A provider-locking worker did not complete.")
        self.assertEqual(len(results), 2)
        return results

    def _provider_operation(self):
        provider = ConcurrentMockProvider()
        operation, _token, replayed = start_provider_payment(
            tenant=self.tenant,
            user=self.owner,
            items=[{"product_id": self.product.id, "quantity": "1"}],
            idempotency_key="phase13-pg-provider-payment",
            provider=provider,
        )
        self.assertFalse(replayed)
        provider.payment_status = "succeeded"
        return operation, provider

    def _settled_provider_operation(self):
        operation, provider = self._provider_operation()
        verify_provider_payment(tenant=self.tenant, operation_id=operation.id, user=self.owner, provider=provider)
        operation.refresh_from_db()
        self.assertEqual(operation.status, ProviderPaymentOperation.STATUS_SUCCEEDED)
        return operation, provider

    def test_successful_provider_payment_replay_does_not_reserve_or_settle_again(self):
        operation, provider = self._settled_provider_operation()

        self.product.refresh_from_db()
        stock_after_first_success = self.product.stock_quantity

        self.assertEqual(
            StockReservation.objects.filter(
                tenant=self.tenant,
                order_id=operation.order_id,
                status=StockReservation.STATUS_ACTIVE,
            ).count(),
            0,
        )
        self.assertEqual(
            StockReservation.objects.filter(
                tenant=self.tenant,
                order_id=operation.order_id,
                status=StockReservation.STATUS_FULFILLED,
            ).count(),
            1,
        )
        self.assertEqual(
            PaymentSettlement.objects.filter(
                tenant=self.tenant,
                order_id=operation.order_id,
            ).count(),
            1,
        )

        replay_operation, _token, replayed = start_provider_payment(
            tenant=self.tenant,
            user=self.owner,
            items=[{"product_id": self.product.id, "quantity": "1"}],
            idempotency_key="phase13-pg-provider-payment",
            provider=provider,
        )

        self.assertTrue(replayed)
        self.assertEqual(replay_operation.id, operation.id)

        self.product.refresh_from_db()
        self.assertEqual(
            self.product.stock_quantity,
            stock_after_first_success,
        )

        self.assertEqual(
            StockReservation.objects.filter(
                tenant=self.tenant,
                order_id=operation.order_id,
                status=StockReservation.STATUS_ACTIVE,
            ).count(),
            0,
        )
        self.assertEqual(
            StockReservation.objects.filter(
                tenant=self.tenant,
                order_id=operation.order_id,
            ).count(),
            1,
        )
        self.assertEqual(
            PaymentSettlement.objects.filter(
                tenant=self.tenant,
                order_id=operation.order_id,
            ).count(),
            1,
        )

    def test_expired_provider_reservation_cannot_be_fulfilled(self):
        operation, provider = self._provider_operation()

        reservation = StockReservation.objects.get(
            tenant=self.tenant,
            order_id=operation.order_id,
            product_id=self.product.id,
            status=StockReservation.STATUS_ACTIVE,
        )

        reservation.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        reservation.save(update_fields=["expires_at"])

        provider.payment_status = "succeeded"

        with self.assertRaises(ValueError) as context:
            verify_provider_payment(
                tenant=self.tenant,
                operation_id=operation.id,
                user=self.owner,
                provider=provider,
            )

        self.assertIn("has expired", str(context.exception))

        reservation.refresh_from_db()
        self.assertEqual(
            reservation.status,
            StockReservation.STATUS_ACTIVE,
        )

        self.product.refresh_from_db()
        self.assertEqual(
            self.product.stock_quantity,
            Decimal("30.000"),
        )

        self.assertFalse(
            PaymentSettlement.objects.filter(
                tenant=self.tenant,
                order_id=operation.order_id,
            ).exists()
        )

        operation.refresh_from_db()
        self.assertNotEqual(
            operation.status,
            ProviderPaymentOperation.STATUS_SUCCEEDED,
        )    

    def test_two_concurrent_provider_finalizations_create_only_one_canonical_settlement(self):
        operation, provider = self._provider_operation()

        results = self._run_parallel(
            lambda _index: verify_provider_payment(
                tenant=self.tenant,
                operation_id=operation.id,
                user=self.owner,
                provider=provider,
            )
        )

        self.assertEqual(results.count("ok"), 2, results)
        self.assertEqual(PaymentSettlement.objects.filter(tenant=self.tenant, order_id=operation.order_id).count(), 1)

    def test_two_concurrent_webhook_deliveries_persist_one_event_and_one_settlement(self):
        operation, provider = self._provider_operation()

        results = self._run_parallel(
            lambda _index: process_provider_webhook(
                provider_code=provider.code,
                raw_body=b"{}",
                signature="valid-concurrency-signature",
                provider=provider,
            )
        )

        self.assertEqual(results.count("ok"), 2, results)
        self.assertEqual(ProviderWebhookEvent.objects.filter(provider=provider.code).count(), 1)
        self.assertEqual(PaymentSettlement.objects.filter(tenant=self.tenant, order_id=operation.order_id).count(), 1)

    def test_concurrent_provider_refunds_cannot_create_duplicate_provider_execution_or_settlement(self):
        operation, provider = self._settled_provider_operation()
        item = operation.order.items.get()
        refund = process_refund(
            tenant=self.tenant,
            user=self.owner,
            order_id=operation.order_id,
            rows=[{"order_item_id": item.id, "quantity": "1"}],
            reason="Phase 13 PostgreSQL duplicate provider refund",
        )

        results = self._run_parallel(
            lambda _index: start_provider_refund(
                tenant=self.tenant,
                refund=Refund.objects.get(pk=refund.pk),
                user=self.owner,
                provider=provider,
            )
        )

        self.assertEqual(results.count("ok"), 1, results)
        self.assertTrue(
            any(result.startswith(("ProviderVerificationError:", "ValueError:")) for result in results),
            results,
        )
        self.assertEqual(provider.refund_create_calls, 1)
        self.assertEqual(ProviderRefundOperation.objects.filter(tenant=self.tenant, refund=refund).count(), 1)
        self.assertEqual(RefundSettlement.objects.filter(tenant=self.tenant, refund=refund).count(), 1)

    def test_concurrent_reconciliation_keeps_one_verified_provider_operation_and_settlement(self):
        operation, provider = self._provider_operation()

        results = self._run_parallel(
            lambda _index: verify_provider_payment(
                tenant=self.tenant,
                operation_id=operation.id,
                user=self.owner,
                provider=provider,
            )
        )

        operation.refresh_from_db()
        self.assertEqual(results.count("ok"), 2, results)
        self.assertEqual(operation.status, ProviderPaymentOperation.STATUS_SUCCEEDED)
        self.assertIsNotNone(operation.verified_at)
        self.assertEqual(PaymentSettlement.objects.filter(tenant=self.tenant, order_id=operation.order_id).count(), 1)
