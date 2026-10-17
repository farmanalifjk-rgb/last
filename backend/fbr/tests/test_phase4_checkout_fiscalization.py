"""Phase 4 regressions: tax after discount, owner discounts, checkout fiscalization.

Decisions recorded in docs/fbr-production-readiness-2026-10-11.md:
* tax is levied on the discounted price (Sales Tax Act 1990 s.2(46)(b));
* tenant owners/admins may discount (same rule as TenantRBACPermission);
* a completed POS sale is fiscalized synchronously through the local IMS
  component; the sale is never rolled back and the receipt shows the honest
  FBR state. The IMS transport is always faked here: no network.
"""
import base64
from decimal import Decimal
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import override_settings

from fbr.ims_client import IMSFiscalClient
from fbr.ims_payload import build_ims_invoice_payload
from fbr.models import FBRHSCode, FBRProductProfile, FBRSubmission, FBRUnitOfMeasure
from fiscal.models import FiscalInvoice, InvoiceSequence
from fiscal.services import FiscalServiceError, issue_invoice
from fbr import services as fbr_services
from payments.models import TenderedPayment
from pos.models import CashSession, Category, Company, Order, Product
from pricing.models import PriceList, PriceListItem
from rbac.models import Permission, Role, UserRole
from saas.models import TenantMembership
from tax.engine import allocate_order_discount
from tax.models import TaxBreakdown, TaxRate

from .base import FakeResponse, FakeSession, FBRTestBase

User = get_user_model()
LOCAL_OK = {"InvoiceNumber": "TEST-IMS-000123", "Code": "100", "Response": "Fiscal Invoice Number generated successfully.", "Errors": None}
LOCAL_REJECTED = {"InvoiceNumber": "", "Code": "401", "Response": "Invalid POS ID.", "Errors": "Invalid POS ID."}


def _no_sleep(*_args):
    return None


class AllocationTests(FBRTestBase):
    def test_discount_shares_sum_exactly_and_follow_line_values(self):
        shares = allocate_order_discount([Decimal("100.00"), Decimal("99.99")], Decimal("10.00"))
        self.assertEqual(sum(shares), Decimal("10.00"))
        self.assertEqual(allocate_order_discount([Decimal("33.33")] * 3, Decimal("0.10")),
                         [Decimal("0.03"), Decimal("0.03"), Decimal("0.04")])
        self.assertEqual(allocate_order_discount([Decimal("50.00")], Decimal("0")), [Decimal("0.00")])


class CheckoutFixture(FBRTestBase):
    """tenant_b: one taxed product, an open till, IMS config and a sequence."""

    price = Decimal("100.00")

    def setUp(self):
        super().setUp()
        tenant = self.tenant_b
        self.category = Category.objects.create(tenant=tenant, name="Phase4")
        self.price_list = PriceList.objects.create(tenant=tenant, name="POS default", is_default=True, is_active=True)
        self.product = self._product("P4-1", self.price)
        CashSession.objects.create(tenant=tenant, opened_by=self.user_b, employee_name="B",
                                   opening_balance=Decimal("0.00"), is_open=True)
        Company.objects.create(tenant=tenant, name="Phase4", address="Karachi", currency="PKR")
        TaxRate.objects.create(tenant=tenant, name="GST", code="GST18", rate=Decimal("0.1800"),
                               is_active=True, applies_to_all=True)
        self.config = self.make_ims_config(tenant)
        self.sequence = InvoiceSequence.objects.create(tenant=tenant, name="S", prefix="P4", document_type="invoice")
        self.ims_session = FakeSession([FakeResponse(LOCAL_OK, 200)])
        patcher = patch(
            "fbr.services._ims_client_for_configuration",
            side_effect=lambda cfg: IMSFiscalClient(cfg, session=self.ims_session, sleep=_no_sleep),
        )
        self._real_client_factory = fbr_services._ims_client_for_configuration
        self.client_factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.owner_api = self.api_client(self.user_b)

    def _product(self, sku, price):
        product = Product.objects.create(
            tenant=self.tenant_b, category=self.category, name=f"Item {sku}", sku=sku,
            sales_price=price, cost_price=Decimal("1.00"), stock_quantity=Decimal("50.000"), is_active=True,
        )
        PriceListItem.objects.create(tenant=self.tenant_b, price_list=self.price_list, product=product,
                                     price=price, min_quantity=Decimal("1"))
        FBRProductProfile.objects.create(
            tenant=self.tenant_b, product=product,
            hs_code=FBRHSCode.objects.get_or_create(code="84713010", defaults={"description": "x"})[0],
            uom=FBRUnitOfMeasure.objects.get_or_create(code="U1000012", defaults={"description": "u"})[0],
            pct_code="84713010", sales_tax_rate=Decimal("18.000"),
        )
        return product

    def checkout(self, api=None, *, amount, key, discount=None, product=None, expected=201):
        body = {"items": [{"product_id": (product or self.product).id, "quantity": "1"}],
                "tenders": [{"tender_type": "cash", "amount": amount}]}
        if discount is not None:
            body["discount"] = discount
        response = (api or self.owner_api).post("/api/pos/checkout/", body, format="json", HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(response.status_code, expected, response.content)
        return response


class TaxAfterDiscountTests(CheckoutFixture):
    def test_discounted_sale_is_taxed_on_the_discounted_price_and_fiscalizes(self):
        data = self.checkout(amount="106.20", key="disc-1", discount="10.00").json()
        order = Order.objects.get(tenant=self.tenant_b, pk=data["order"]["id"])
        self.assertEqual((order.subtotal, order.discount, order.tax, order.total),
                         (Decimal("100.00"), Decimal("10.00"), Decimal("16.20"), Decimal("106.20")))
        self.assertEqual(Decimal(TaxBreakdown.objects.get(order=order).taxable_amount), Decimal("90.00"))
        # The D-4 consistency guard passes: FBR receives exactly what was charged.
        invoice = FiscalInvoice.objects.get(tenant=self.tenant_b, order=order)
        payload = build_ims_invoice_payload(invoice, config=self.config)
        self.assertEqual(Decimal(str(payload["TotalBillAmount"])), order.total)
        self.assertEqual(Decimal(str(payload["TotalTaxCharged"])), order.tax)
        self.assertEqual(data["fiscal"]["status"], "accepted")

    def test_half_paisa_tax_rounds_the_same_at_checkout_and_on_the_fiscal_invoice(self):
        product = self._product("P4-HALF", Decimal("10.25"))  # 18% = 1.845
        data = self.checkout(amount="12.10", key="half-1", product=product).json()
        order = Order.objects.get(tenant=self.tenant_b, pk=data["order"]["id"])
        self.assertEqual(order.tax, Decimal("1.85"))
        payload = build_ims_invoice_payload(FiscalInvoice.objects.get(order=order), config=self.config)
        self.assertEqual(Decimal(str(payload["TotalTaxCharged"])), Decimal("1.85"))
        self.assertEqual(data["fiscal"]["status"], "accepted")


class DiscountPermissionTests(CheckoutFixture):
    def _member(self, username, role):
        user = User.objects.create_user(username=username, password="x-pass-123")
        TenantMembership.objects.create(tenant=self.tenant_b, user=user, role=role, is_active_in_tenant=True)
        CashSession.objects.create(tenant=self.tenant_b, opened_by=user, employee_name=username,
                                   opening_balance=Decimal("0.00"), is_open=True)
        return user

    def _cashier(self):
        user = self._member("cashier_b", TenantMembership.ROLE_STAFF)
        role = Role.objects.create(key="p4-cashier", label="Cashier", tenant=self.tenant_b)
        role.permissions.add(*Permission.objects.filter(module__key="pos", action__in=["view", "create"], scope="tenant"))
        UserRole.objects.create(user=user, role=role, tenant=self.tenant_b)
        return user

    def test_owner_without_a_user_role_may_discount(self):
        self.assertFalse(UserRole.objects.filter(user=self.user_b).exists())
        self.checkout(amount="106.20", key="own-1", discount="10.00")

    def test_admin_without_a_user_role_may_discount(self):
        admin = self._member("admin2_b", TenantMembership.ROLE_ADMIN)
        self.checkout(self.api_client(admin), amount="106.20", key="adm-1", discount="10.00")

    def test_cashier_without_discount_permission_is_refused_but_can_sell(self):
        cashier_api = self.api_client(self._cashier())
        self.checkout(cashier_api, amount="106.20", key="cash-1", discount="10.00", expected=403)
        self.assertFalse(Order.objects.filter(tenant=self.tenant_b).exists())
        # Plain sale: fiscalized although the cashier holds no FBR permission.
        data = self.checkout(cashier_api, amount="118.00", key="cash-2").json()
        self.assertEqual(data["fiscal"]["status"], "accepted")


class CheckoutFiscalizationTests(CheckoutFixture):
    def _order(self, data):
        return Order.objects.get(tenant=self.tenant_b, pk=data["order"]["id"])

    def assertSaleCommitted(self, order):
        order.refresh_from_db()
        self.assertEqual(order.status, "paid")
        self.assertEqual(TenderedPayment.objects.filter(tenant=self.tenant_b, order=order).count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("49.000"))

    def test_accepted_sale_returns_and_prints_the_fbr_number_and_qr(self):
        data = self.checkout(amount="118.00", key="ok-1").json()
        fiscal = data["fiscal"]
        self.assertEqual(fiscal["status"], "accepted")
        self.assertEqual(fiscal["fbr_invoice_number"], "TEST-IMS-000123")
        self.assertTrue(base64.b64decode(fiscal["qr_png_base64"]).startswith(b"\x89PNG"))
        self.assertEqual(data["receipt"]["fiscal"]["fbr_invoice_number"], "TEST-IMS-000123")
        order = self._order(data)
        receipt = self.owner_api.get(f"/api/pos/orders/{order.id}/receipt/").json()
        self.assertEqual(receipt["fiscal"]["status"], "accepted")
        self.assertEqual(receipt["fiscal"]["fbr_invoice_number"], "TEST-IMS-000123")
        self.assertEqual(len(self.ims_session.calls), 1)
        self.assertSaleCommitted(order)

    def test_component_down_keeps_the_sale_and_reports_failed(self):
        self.ims_session.responses = [requests.exceptions.ConnectionError("refused")] * 3
        data = self.checkout(amount="118.00", key="down-1").json()
        self.assertEqual(data["fiscal"]["status"], "failed")
        self.assertEqual(data["fiscal"]["fbr_invoice_number"], "")
        self.assertEqual(data["fiscal"]["qr_png_base64"], "")
        self.assertSaleCommitted(self._order(data))

    def test_timeout_is_unknown_and_never_reposted(self):
        self.ims_session.responses = [requests.exceptions.ReadTimeout("slow"), FakeResponse(LOCAL_OK, 200)]
        data = self.checkout(amount="118.00", key="slow-1").json()
        self.assertEqual(data["fiscal"]["status"], "unknown")
        self.assertEqual(len(self.ims_session.calls), 1)
        self.assertSaleCommitted(self._order(data))

    def test_rejection_is_shown_as_rejected(self):
        self.ims_session.responses = [FakeResponse(LOCAL_REJECTED, 200)]
        data = self.checkout(amount="118.00", key="rej-1").json()
        self.assertEqual(data["fiscal"]["status"], "rejected")
        self.assertEqual(data["fiscal"]["fbr_invoice_number"], "")
        self.assertSaleCommitted(self._order(data))

    def test_replayed_checkout_never_submits_twice(self):
        first = self.checkout(amount="118.00", key="replay-1").json()
        replay = self.checkout(amount="118.00", key="replay-1", expected=200).json()
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["fiscal"]["fbr_invoice_number"], first["fiscal"]["fbr_invoice_number"])
        order = self._order(first)
        self.assertEqual(FiscalInvoice.objects.filter(order=order).count(), 1)
        self.assertEqual(FBRSubmission.objects.filter(invoice__order=order).count(), 1)
        self.assertEqual(len(self.ims_session.calls), 1)

    def test_replay_after_failure_reports_without_resending(self):
        self.ims_session.responses = [requests.exceptions.ConnectionError("refused")] * 3
        self.checkout(amount="118.00", key="replay-2")
        calls = len(self.ims_session.calls)
        replay = self.checkout(amount="118.00", key="replay-2", expected=200).json()
        self.assertEqual(replay["fiscal"]["status"], "failed")
        self.assertEqual(len(self.ims_session.calls), calls, "retries are explicit, never automatic on replay")

    def test_order_can_never_get_a_second_fiscal_invoice(self):
        order = self._order(self.checkout(amount="118.00", key="dup-1").json())
        with self.assertRaises(FiscalServiceError):
            issue_invoice(tenant=self.tenant_b, order_id=order.id, sequence_id=self.sequence.id, user=self.user_b)
        self.assertEqual(FiscalInvoice.objects.filter(order=order).count(), 1)

    def test_tenant_without_fbr_is_not_configured_and_nothing_is_issued(self):
        self.config.delete()
        data = self.checkout(amount="118.00", key="nocfg-1").json()
        self.assertEqual(data["fiscal"]["status"], "not_configured")
        self.assertFalse(FiscalInvoice.objects.filter(tenant=self.tenant_b).exists())
        self.assertEqual(self.ims_session.calls, [])

    def test_missing_invoice_sequence_is_reported_honestly(self):
        self.sequence.delete()
        data = self.checkout(amount="118.00", key="noseq-1").json()
        self.assertEqual(data["fiscal"]["status"], "not_fiscalized")
        self.assertIn("invoice sequence", data["fiscal"]["message"])
        self.assertSaleCommitted(self._order(data))

    def test_digital_invoicing_tenant_is_not_submitted_from_the_till(self):
        self.config.integration_mode = "di"
        self.config.save()
        with patch("fbr.services.FBRClient") as di_client:
            data = self.checkout(amount="118.00", key="di-1").json()
        di_client.assert_not_called()
        self.assertEqual(data["fiscal"]["status"], "not_fiscalized")
        self.assertEqual(self.ims_session.calls, [])

    def test_unexpected_error_never_breaks_the_completed_sale(self):
        with patch("fbr.services.submit_invoice", side_effect=RuntimeError("bug")):
            data = self.checkout(amount="118.00", key="bug-1").json()
        self.assertEqual(data["fiscal"]["status"], "not_submitted")
        self.assertNotIn("bug", data["fiscal"]["message"])
        self.assertSaleCommitted(self._order(data))

    def test_validation_failure_is_not_submitted_and_explained(self):
        FBRProductProfile.objects.filter(product=self.product).update(sales_tax_rate=Decimal("17.000"))
        data = self.checkout(amount="118.00", key="val-1").json()
        self.assertEqual(data["fiscal"]["status"], "not_submitted")
        self.assertTrue(data["fiscal"]["message"].startswith("Not sent to FBR"))
        self.assertEqual(self.ims_session.calls, [])

    @override_settings(FBR_SIMULATOR_ENABLED=True, FBR_SIMULATOR_MODE="sandbox")
    def test_simulated_acceptance_receipt_shows_test_number_and_working_qr(self):
        # Real routing: opted-in configuration -> isolated simulator.
        self.client_factory.side_effect = self._real_client_factory
        self.config.use_simulator = True
        self.config.save()
        data = self.checkout(amount="118.00", key="sim-1").json()
        fiscal = data["fiscal"]
        self.assertEqual(fiscal["status"], "simulated")
        self.assertTrue(fiscal["is_simulated"])
        self.assertEqual(fiscal["fbr_invoice_number"], "")
        simulated_number = fiscal["simulated_invoice_number"]
        self.assertTrue(simulated_number.startswith("SIM-SBX-"))
        self.assertEqual(fiscal["receipt_label"], "TEST / SIMULATED — NOT AN FBR INVOICE")
        qr_png = base64.b64decode(fiscal["qr_png_base64"])
        self.assertTrue(qr_png.startswith(b"\x89PNG"))
        from fbr.qr import render_qr_png
        self.assertEqual(qr_png, render_qr_png(simulated_number, quiet_zone=0))
        receipt = self.owner_api.get(f"/api/pos/orders/{data['order']['id']}/receipt/").json()
        self.assertEqual(receipt["fiscal"]["status"], "simulated")
        self.assertEqual(receipt["fiscal"]["fbr_invoice_number"], "")
        self.assertEqual(receipt["fiscal"]["simulated_invoice_number"], simulated_number)
        self.assertEqual(receipt["fiscal"]["qr_png_base64"], fiscal["qr_png_base64"])

    def test_other_tenant_cannot_read_the_fiscal_receipt(self):
        order = self._order(self.checkout(amount="118.00", key="iso-1").json())
        response = self.api_client(self.user_a).get(f"/api/pos/orders/{order.id}/receipt/")
        self.assertEqual(response.status_code, 404)
