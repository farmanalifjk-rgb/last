"""Concurrent duplicate checkouts (double-submit / network retry) must yield one sale.

Runs on PostgreSQL with real threads; each thread uses its own DB connection.
"""
import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from pos.models import CashSession, Category, Order, Product
from pos.services.canonical_pos import checkout
from saas.models import Tenant, TenantMembership

User = get_user_model()


class CheckoutIdempotencyRaceTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest(f"requires PostgreSQL, got {connection.vendor}")
        self.owner = User.objects.create_user(username="race-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Race Tenant", slug="race-tenant", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)
        category = Category.objects.create(tenant=self.tenant, name="Race Category")
        self.product = Product.objects.create(
            tenant=self.tenant, category=category, name="Race Product", sku="RACE-1",
            sales_price=Decimal("10.00"), cost_price=Decimal("4.00"), stock_quantity=Decimal("10.000"), is_active=True,
        )
        CashSession.objects.create(tenant=self.tenant, opened_by=self.owner, employee_name="Owner",
                                   opening_balance=Decimal("0.00"), is_open=True)

    def test_concurrent_duplicate_checkouts_create_exactly_one_sale(self):
        threads_count = 4
        barrier = threading.Barrier(threads_count)
        results, errors = [], []
        lock = threading.Lock()

        def worker():
            try:
                barrier.wait(timeout=20)
                order, replayed = checkout(
                    tenant=self.tenant,
                    user=self.owner,
                    items=[{"product_id": self.product.id, "quantity": "1"}],
                    tenders=[{"tender_type": "cash", "amount": "10.00"}],
                    customer_id=None,
                    discount=Decimal("0"),
                    idempotency_key="race-same-key",
                )
                with lock:
                    results.append((order.id, replayed))
            except Exception as exc:  # collected and asserted below
                with lock:
                    errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(threads_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [], "a retried checkout must replay, not fail")
        self.assertEqual(len(results), threads_count)
        self.assertEqual(len({order_id for order_id, _ in results}), 1)
        self.assertEqual(sum(1 for _, replayed in results if not replayed), 1)
        self.assertEqual(Order.objects.filter(tenant=self.tenant, idempotency_key="race-same-key").count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("9.000"))
