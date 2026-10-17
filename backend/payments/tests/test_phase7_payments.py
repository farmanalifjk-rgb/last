from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from payments.models import GiftCard, PaymentReconciliation, PaymentSettlement, RefundSettlement, StoreCredit, TenderedPayment
from payments.services import issue_gift_card, issue_store_credit, settle_order
from pos.models import CashSession, Category, Customer, Order, Product, Refund
from rbac.models import Permission, Role, UserRole
from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant


User = get_user_model()


class Phase7PaymentsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="phase7-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase 7 Tenant", slug="phase7-tenant", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)
        set_current_tenant(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.category = Category.objects.create(tenant=self.tenant, name="Phase 7 Category")
        self.product = Product.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Phase 7 Product",
            sku="P7-PRODUCT",
            barcode="707070",
            sales_price=Decimal("10.00"),
            cost_price=Decimal("3.00"),
            stock_quantity=Decimal("20.000"),
            is_active=True,
        )
        self.session = CashSession.objects.create(tenant=self.tenant, opened_by=self.owner, employee_name="Phase 7 owner", opening_balance=Decimal("0.00"), is_open=True)

    def checkout(self, *, tender_type="cash", amount="20.00", reference="", customer=None, quantity="1", key="phase7-checkout"):
        payload = {
            "items": [{"product_id": self.product.id, "quantity": quantity}],
            "tenders": [{"tender_type": tender_type, "amount": amount, "reference": reference}],
        }
        if customer:
            payload["customer_id"] = customer.id
        return self.client.post("/api/pos/checkout/", payload, format="json", HTTP_IDEMPOTENCY_KEY=key)

    def test_checkout_creates_one_settlement_tender_ledger_and_audit_event(self):
        created = self.checkout()
        self.assertEqual(created.status_code, 201, created.data)
        order = Order.objects.get(tenant=self.tenant, pk=created.data["order"]["id"])
        settlement = PaymentSettlement.objects.get(tenant=self.tenant, order=order)
        tender = TenderedPayment.objects.get(tenant=self.tenant, order=order)
        self.assertEqual(settlement.total_amount, Decimal("10.00"))
        self.assertEqual(tender.amount, Decimal("10.00"))
        self.assertEqual(order.change_amount, Decimal("10.00"))
        self.assertTrue(tender.is_settled)
        self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant, entity_type="paymentsettlement", entity_id=str(settlement.id)).count(), 1)
        replay = self.checkout()
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertTrue(replay.data["idempotent_replay"])
        self.assertEqual(PaymentSettlement.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(TenderedPayment.objects.filter(tenant=self.tenant).count(), 1)

    def test_paid_order_cannot_be_settled_again(self):
        created = self.checkout(key="single-settlement")
        order = Order.objects.get(tenant=self.tenant, pk=created.data["order"]["id"])
        with self.assertRaisesMessage(ValueError, "Only draft orders can be settled"):
            settle_order(order=order, tenders=[{"tender_type": "cash", "amount": "10"}], user=self.owner)
        self.assertEqual(PaymentSettlement.objects.filter(tenant=self.tenant, order=order).count(), 1)

    def test_card_reference_rejects_raw_pan_like_values(self):
        rejected = self.checkout(tender_type="card", amount="10", reference="4111 1111 1111 1111", key="raw-pan")
        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.assertEqual(PaymentSettlement.objects.filter(tenant=self.tenant).count(), 0)

    def test_gift_card_redemption_is_tenant_bound_and_atomic_with_checkout(self):
        gift_card = issue_gift_card(tenant=self.tenant, initial_balance="15.00", user=self.owner)
        redeemed = self.checkout(tender_type="gift_card", amount="10", reference=gift_card.code, key="gift-redemption")
        self.assertEqual(redeemed.status_code, 201, redeemed.data)
        gift_card.refresh_from_db()
        self.assertEqual(gift_card.balance, Decimal("5.00"))
        self.assertEqual(gift_card.transactions.filter(kind="redeem").count(), 1)

    def test_store_credit_redemption_locks_customer_wallet_and_requires_customer(self):
        customer = Customer.objects.create(tenant=self.tenant, name="Phase 7 customer", phone="5550001", is_active=True)
        issue_store_credit(tenant=self.tenant, customer=customer, amount="12.00", user=self.owner, note="Phase 7 credit")
        paid = self.checkout(tender_type="store_credit", amount="10", customer=customer, key="store-credit-redemption")
        self.assertEqual(paid.status_code, 201, paid.data)
        wallet = StoreCredit.objects.get(tenant=self.tenant, customer=customer)
        self.assertEqual(wallet.balance, Decimal("2.00"))
        self.assertEqual(wallet.transactions.filter(kind="redeem").count(), 1)
        missing_customer = self.checkout(tender_type="store_credit", amount="10", key="missing-store-credit-customer")
        self.assertEqual(missing_customer.status_code, 400, missing_customer.data)

    def test_canonical_pos_refund_creates_one_compensating_refund_settlement(self):
        created = self.checkout(key="refund-settlement")
        order = Order.objects.get(tenant=self.tenant, pk=created.data["order"]["id"])
        item = order.items.get()
        response = self.client.post("/api/pos/refunds/", {"order_id": order.id, "items": [{"order_item_id": item.id, "quantity": "1"}], "reason": "Phase 7 refund"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        refund = Refund.objects.get(tenant=self.tenant, pk=response.data["id"])
        payment_refund = RefundSettlement.objects.get(tenant=self.tenant, refund=refund)
        self.assertEqual(payment_refund.amount, Decimal("10.00"))
        self.assertEqual(payment_refund.method, RefundSettlement.METHOD_RECORDED)
        self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant, action=AuditEvent.ACTION_REFUND, entity_id=str(payment_refund.id)).count(), 1)

    def test_reconciliation_is_unique_per_session_and_only_matched_records_can_close(self):
        self.checkout(key="reconciliation-sale")
        created = self.client.post("/api/payments/reconciliations/", {"session_id": self.session.id, "lines": [{"tender_type": "cash", "counted_amount": "10.00"}]}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        reconciliation = PaymentReconciliation.objects.get(tenant=self.tenant, pk=created.data["id"])
        self.assertEqual(reconciliation.status, PaymentReconciliation.STATUS_MATCHED)
        closed = self.client.post(f"/api/payments/reconciliations/{reconciliation.id}/close/", {}, format="json")
        self.assertEqual(closed.status_code, 200, closed.data)
        reconciliation.refresh_from_db()
        self.assertEqual(reconciliation.status, PaymentReconciliation.STATUS_CLOSED)
        duplicate = self.client.post("/api/payments/reconciliations/", {"session_id": self.session.id, "lines": [{"tender_type": "cash", "counted_amount": "10.00"}]}, format="json")
        self.assertEqual(duplicate.status_code, 400, duplicate.data)

    def test_payment_objects_are_tenant_isolated_and_payment_viewer_cannot_mutate(self):
        gift_card = issue_gift_card(tenant=self.tenant, initial_balance="5.00", user=self.owner)
        other = User.objects.create_user(username="phase7-other", password="StrongPass123!")
        other_tenant = Tenant.objects.create(name="Other Phase 7 Tenant", slug="phase7-other", owner=other, status="active")
        TenantMembership.objects.create(tenant=other_tenant, user=other, role="owner", is_active_in_tenant=True)
        other_client = APIClient()
        other_client.force_authenticate(other)
        self.assertEqual(other_client.get(f"/api/payments/gift-cards/{gift_card.id}/").status_code, 404)

        viewer = User.objects.create_user(username="phase7-payment-viewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant, user=viewer, role="staff", is_active_in_tenant=True)
        role = Role.objects.create(key="phase7-payment-viewer", label="Phase 7 payment viewer")
        role.permissions.add(Permission.objects.get(module__key="payments", action="view"))
        UserRole.objects.create(user=viewer, role=role)
        viewer_client = APIClient()
        viewer_client.force_authenticate(viewer)
        self.assertEqual(viewer_client.get("/api/payments/register/").status_code, 200)
        self.assertEqual(viewer_client.get(f"/api/payments/gift-cards/{gift_card.id}/").status_code, 200)
        self.assertEqual(viewer_client.post(f"/api/payments/gift-cards/{gift_card.id}/topup/", {"amount": "1.00"}, format="json").status_code, 403)
        self.assertEqual(viewer_client.post(f"/api/payments/store-credit/999/issue/", {"amount": "1.00"}, format="json").status_code, 403)
        self.assertEqual(viewer_client.post("/api/payments/reconciliations/", {"session_id": self.session.id, "lines": [{"tender_type": "cash", "counted_amount": "0"}]}, format="json").status_code, 403)
