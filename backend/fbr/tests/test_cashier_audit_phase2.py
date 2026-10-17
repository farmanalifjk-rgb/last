"""Cashier terminal audit 2026-10-13, Phase 2 (backend validation).

* C1: the preview applies the same discount permission as checkout, so a
  cashier never sees a discounted total that checkout then refuses. A zero
  discount written as "0.000" is not a discount request.
* D3: S.R.O. 1006(I)/2021 B(iv) - an FBR-integrated sale above the threshold
  (default Rs.100,000) must record the buyer's name. Only tenants whose till
  is FBR-integrated (active IMS configuration) are affected.

The IMS transport is faked by CheckoutFixture: no network.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings


from pos.models import CashSession, Customer, Order
from pos.services.canonical_pos import (
    BUYER_IDENTIFICATION_THRESHOLD_DEFAULT,
    buyer_identification_required,
    discount_requested,
    parse_discount,
)
from rbac.models import Permission, Role, UserRole
from saas.models import TenantMembership

from .test_phase4_checkout_fiscalization import CheckoutFixture

User = get_user_model()


class DiscountParsingTests(CheckoutFixture):
    def test_parse_and_request_detection(self):
        self.assertEqual(parse_discount(""), Decimal("0.00"))
        self.assertEqual(parse_discount(None), Decimal("0.00"))
        self.assertEqual(parse_discount(" 12.345 "), Decimal("12.35"))
        for zero in ("0", "0.0", "0.000", "00", ""):
            self.assertFalse(discount_requested(zero), zero)
        self.assertTrue(discount_requested("0.01"))
        for bad in ("abc", "NaN", "Infinity", "1,000"):
            with self.assertRaisesMessage(ValueError, "Discount must be a valid amount."):
                parse_discount(bad)
            self.assertFalse(discount_requested(bad), bad)


class PreviewDiscountPermissionTests(CheckoutFixture):
    def _cashier(self):
        user = User.objects.create_user(username="p2_cashier", password="x-pass-123")
        TenantMembership.objects.create(tenant=self.tenant_b, user=user, role=TenantMembership.ROLE_STAFF,
                                        is_active_in_tenant=True)
        CashSession.objects.create(tenant=self.tenant_b, opened_by=user, employee_name="c",
                                   opening_balance=Decimal("0.00"), is_open=True)
        role = Role.objects.create(key="p2-cashier", label="Cashier", tenant=self.tenant_b)
        role.permissions.add(*Permission.objects.filter(module__key="pos", action__in=["view", "create"], scope="tenant"))
        UserRole.objects.create(user=user, role=role, tenant=self.tenant_b)
        return self.api_client(user)

    def preview(self, api, discount, expected):
        response = api.post("/api/pos/preview/", {"items": [{"product_id": self.product.id, "quantity": "1"}],
                                                  "discount": discount}, format="json")
        self.assertEqual(response.status_code, expected, response.content)
        return response

    def test_cashier_without_permission_is_refused_at_preview(self):
        api = self._cashier()
        self.preview(api, "10.00", 403)
        self.assertEqual(self.preview(api, "0.00", 200).json()["total"], "118.00")

    def test_zero_written_with_extra_decimals_is_not_a_discount(self):
        api = self._cashier()
        self.preview(api, "0.000", 200)
        # Previously checkout compared strings and refused "0.000" with 403.
        self.checkout(api, amount="118.00", key="p2-zero", discount="0.000")

    def test_owner_preview_applies_the_discount(self):
        data = self.preview(self.owner_api, "10.00", 200).json()
        self.assertEqual((data["discount"], data["tax"], data["total"]), ("10.00", "16.20", "106.20"))

    def test_malformed_discount_is_a_readable_400_at_preview_and_checkout(self):
        for bad in ("abc", "NaN"):
            response = self.preview(self.owner_api, bad, 400)
            self.assertIn("Discount must be a valid amount.", response.content.decode())
            response = self.checkout(amount="118.00", key=f"p2-bad-{bad}", discount=bad, expected=400)
            self.assertIn("Discount must be a valid amount.", response.content.decode())
        self.assertFalse(Order.objects.filter(tenant=self.tenant_b).exists())


@override_settings(POS_BUYER_IDENTIFICATION_THRESHOLD="100")
class BuyerIdentificationTests(CheckoutFixture):
    """Threshold lowered to 100 so the fixture's 118.00 sale is "above" it."""

    def preview(self, customer_id=None):
        body = {"items": [{"product_id": self.product.id, "quantity": "1"}]}
        if customer_id:
            body["customer_id"] = customer_id
        response = self.owner_api.post("/api/pos/preview/", body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_preview_tells_the_till_a_buyer_is_needed(self):
        data = self.preview()
        self.assertIs(data["buyer_identification_required"], True)
        self.assertEqual(data["buyer_identification_threshold"], "100")

    def test_walk_in_sale_above_the_threshold_is_refused_and_nothing_is_recorded(self):
        response = self.checkout(amount="118.00", key="p2-buyer-1", expected=400)
        self.assertIn("must record the buyer's name", response.content.decode())
        self.assertFalse(Order.objects.filter(tenant=self.tenant_b).exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("50.000"))
        self.assertEqual(len(self.ims_session.calls), 0, "nothing is fiscalized")

    def test_sale_with_a_named_customer_goes_through_and_fiscalizes(self):
        customer = Customer.objects.create(tenant=self.tenant_b, name="Buyer B", phone="0300")
        body = {"items": [{"product_id": self.product.id, "quantity": "1"}],
                "tenders": [{"tender_type": "cash", "amount": "118.00"}], "customer_id": customer.id}
        response = self.owner_api.post("/api/pos/checkout/", body, format="json", HTTP_IDEMPOTENCY_KEY="p2-buyer-2")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["fiscal"]["status"], "accepted")

    def test_customer_without_a_name_does_not_satisfy_the_rule(self):
        customer = Customer.objects.create(tenant=self.tenant_b, name=" ", phone="0301")
        body = {"items": [{"product_id": self.product.id, "quantity": "1"}],
                "tenders": [{"tender_type": "cash", "amount": "118.00"}], "customer_id": customer.id}
        response = self.owner_api.post("/api/pos/checkout/", body, format="json", HTTP_IDEMPOTENCY_KEY="p2-buyer-3")
        self.assertEqual(response.status_code, 400, response.content)

    @override_settings(POS_BUYER_IDENTIFICATION_THRESHOLD="118.00")
    def test_a_total_equal_to_the_threshold_is_not_above_it(self):
        self.assertIs(self.preview()["buyer_identification_required"], False)
        self.checkout(amount="118.00", key="p2-buyer-eq")

    @override_settings(POS_BUYER_IDENTIFICATION_THRESHOLD=0)
    def test_zero_disables_the_rule(self):
        self.assertIs(self.preview()["buyer_identification_required"], False)
        self.checkout(amount="118.00", key="p2-buyer-off")

    def test_tenant_without_an_active_fbr_configuration_is_unchanged(self):
        self.config.is_active = False
        self.config.save(update_fields=["is_active"])
        self.assertIs(self.preview()["buyer_identification_required"], False)
        data = self.checkout(amount="118.00", key="p2-buyer-nofbr").json()
        self.assertEqual(data["fiscal"]["status"], "not_configured")

    def test_rule_is_evaluated_for_the_requesting_tenant_only(self):
        # tenant_a's configuration is Digital Invoicing, not the IMS till track.
        self.assertFalse(buyer_identification_required(tenant=self.tenant_a, total=Decimal("1000000")))
        self.assertTrue(buyer_identification_required(tenant=self.tenant_b, total=Decimal("1000000")))


class BuyerIdentificationDefaultTests(CheckoutFixture):
    def test_default_threshold_is_rs_100000_and_ordinary_sales_are_unaffected(self):
        self.assertEqual(BUYER_IDENTIFICATION_THRESHOLD_DEFAULT, Decimal("100000"))
        self.assertFalse(buyer_identification_required(tenant=self.tenant_b, total=Decimal("100000.00")))
        self.assertTrue(buyer_identification_required(tenant=self.tenant_b, total=Decimal("100000.01")))
        self.checkout(amount="118.00", key="p2-default")
