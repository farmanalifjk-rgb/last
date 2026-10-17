import threading
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import TransactionTestCase

from payments.models import GiftCard, PaymentSettlement, StoreCredit
from payments.services import issue_gift_card, issue_store_credit, redeem_gift_card, redeem_store_credit, settle_order
from pos.models import CashSession, Category, Customer, Order, OrderItem, Product
from pos.services.canonical_pos import process_refund
from saas.models import Tenant, TenantMembership


User = get_user_model()


@skipUnless(connection.vendor == "postgresql", "Financial locking tests require PostgreSQL.")
class PostgreSQLFinancialConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user(username="phase7-pg-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase 7 PostgreSQL Tenant", slug="phase7-pg-tenant", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)
        self.category = Category.objects.create(tenant=self.tenant, name="Phase 7 PostgreSQL Category")
        self.product = Product.objects.create(tenant=self.tenant, category=self.category, name="Phase 7 PostgreSQL Product", sku="P7-PG", sales_price=Decimal("10.00"), cost_price=Decimal("3.00"), stock_quantity=Decimal("50.000"), is_active=True)
        self.session = CashSession.objects.create(tenant=self.tenant, opened_by=self.owner, employee_name="Phase 7 PostgreSQL", opening_balance=Decimal("0.00"), is_open=True)

    def _draft_order(self, suffix):
        order = Order.objects.create(tenant=self.tenant, session=self.session, payment_method="cash", subtotal=Decimal("10.00"), tax=Decimal("0.00"), discount=Decimal("0.00"), total=Decimal("10.00"), status="draft", idempotency_key=f"pg-{suffix}")
        OrderItem.objects.create(tenant=self.tenant, order=order, product=self.product, quantity=Decimal("1"), unit_price=Decimal("10.00"), subtotal=Decimal("10.00"))
        return order

    def _run_parallel(self, callback):
        barrier = threading.Barrier(2)
        results = []
        lock = threading.Lock()

        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                callback(index)
                result = "ok"
            except Exception as exc:
                result = type(exc).__name__
            finally:
                connections.close_all()
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertEqual(len(results), 2)
        return results

    def test_two_workers_cannot_settle_one_order_twice(self):
        order = self._draft_order("settlement")

        def settle(_index):
            current_order = Order.objects.get(pk=order.pk)
            settle_order(order=current_order, tenders=[{"tender_type": "cash", "amount": "10.00"}], user=self.owner)

        results = self._run_parallel(settle)
        self.assertEqual(results.count("ok"), 1, results)
        self.assertEqual(PaymentSettlement.objects.filter(tenant=self.tenant, order_id=order.id).count(), 1)

    def test_two_workers_cannot_redeem_one_gift_card_balance_twice(self):
        gift_card = issue_gift_card(tenant=self.tenant, initial_balance="10.00", user=self.owner)
        orders = [self._draft_order(f"gift-{index}") for index in range(2)]

        def redeem(index):
            redeem_gift_card(tenant=self.tenant, code=gift_card.code, amount="8.00", order=Order.objects.get(pk=orders[index].pk), user=self.owner)

        results = self._run_parallel(redeem)
        self.assertEqual(results.count("ok"), 1, results)
        gift_card.refresh_from_db()
        self.assertEqual(gift_card.balance, Decimal("2.00"))

    def test_two_workers_cannot_redeem_one_store_credit_balance_twice(self):
        customer = Customer.objects.create(tenant=self.tenant, name="Phase 7 PostgreSQL customer", phone="5557000", is_active=True)
        issue_store_credit(tenant=self.tenant, customer=customer, amount="10.00", user=self.owner)
        orders = [self._draft_order(f"credit-{index}") for index in range(2)]
        for order in orders:
            order.customer = customer
            order.save(update_fields=["customer"])

        def redeem(index):
            redeem_store_credit(tenant=self.tenant, customer=Customer.objects.get(pk=customer.pk), amount="8.00", order=Order.objects.get(pk=orders[index].pk), user=self.owner)

        results = self._run_parallel(redeem)
        self.assertEqual(results.count("ok"), 1, results)
        wallet = StoreCredit.objects.get(tenant=self.tenant, customer=customer)
        self.assertEqual(wallet.balance, Decimal("2.00"))

    def test_two_workers_cannot_refund_the_same_remaining_quantity_twice(self):
        order = self._draft_order("refund")
        settle_order(order=order, tenders=[{"tender_type": "cash", "amount": "10.00"}], user=self.owner)
        item = OrderItem.objects.get(order=order)

        def refund(_index):
            process_refund(tenant=self.tenant, user=self.owner, order_id=order.id, rows=[{"order_item_id": item.id, "quantity": "1"}], reason="PostgreSQL concurrency")

        results = self._run_parallel(refund)
        self.assertEqual(results.count("ok"), 1, results)
        order.refresh_from_db()
        self.assertEqual(order.status, "refunded")
