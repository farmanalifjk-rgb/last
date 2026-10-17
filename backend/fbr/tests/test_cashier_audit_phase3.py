"""Cashier audit phase 3: S.R.O. 1006(I)/2021 receipt content (G2, G4, G5, G10, G11).

docs/pos-cashier-terminal-audit-2026-10-13.md. The receipt payload carries the
seller NTN and PoS registration number, the cashier, readable payment modes and
the item lines exactly as fiscalized (rate, GST, value excl. tax). STRN and tax
office are deliberately not part of this phase. Every print is audited and
copies after the first are reprints. All FBR transport is faked.
"""
import base64
import io
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from PIL import Image

from audit.models import AuditEvent
from fbr.qr import QUIET_ZONE_MODULES, render_qr_png
from pos.models import CashSession, Order
from rbac.models import Permission, Role, UserRole
from saas.models import TenantMembership

from .test_phase4_checkout_fiscalization import CheckoutFixture

User = get_user_model()


def _receipt(api, order_id):
    return api.get(f"/api/pos/orders/{order_id}/receipt/")


def _printed(api, order_id):
    return api.post(f"/api/pos/orders/{order_id}/receipt/printed/", {}, format="json")


class ReceiptPayloadTests(CheckoutFixture):
    def setUp(self):
        super().setUp()
        self.sale = self.checkout(amount="106.20", key="p3-sale", discount="10.00").json()
        self.order_id = self.sale["order"]["id"]

    def test_header_carries_ntn_and_pos_registration_number(self):
        business = _receipt(self.owner_api, self.order_id).json()["business"]
        self.assertEqual(business["ntn"], "1234567")
        self.assertEqual(business["pos_registration_number"], "110014")
        self.assertTrue(business["fbr_integrated"])
        self.assertNotIn("strn", business, "STRN is out of scope for this phase")

    def test_no_credentials_leak_into_the_receipt(self):
        self.config.security_token = "test-token"
        self.config.save()
        raw = json.dumps(_receipt(self.owner_api, self.order_id).json())
        self.assertNotIn("test-token", raw)
        self.assertNotIn("security_token", raw)

    def test_cashier_tender_label_and_invoice_number(self):
        data = _receipt(self.owner_api, self.order_id).json()
        self.assertEqual(data["order"]["cashier"], "B")  # CashSession.employee_name
        self.assertEqual(data["tenders"][0]["tender_type"], "cash")
        self.assertEqual(data["tenders"][0]["label"], "Cash")
        self.assertTrue(data["fiscal"]["invoice_number"].startswith("P4"))

    def test_cashier_falls_back_to_the_session_user(self):
        CashSession.objects.filter(tenant=self.tenant_b).update(employee_name="")
        self.user_b.first_name, self.user_b.last_name = "Bilal", "Ahmed"
        self.user_b.save()
        self.assertEqual(_receipt(self.owner_api, self.order_id).json()["order"]["cashier"], "Bilal Ahmed")

    def test_item_lines_match_the_fiscal_invoice(self):
        data = _receipt(self.owner_api, self.order_id).json()
        self.assertEqual(len(data["fiscal_lines"]), 1)
        line = data["fiscal_lines"][0]
        self.assertEqual(line["line_number"], 1)
        self.assertEqual(line["description"], "Item P4-1")
        self.assertEqual(Decimal(line["quantity"]), Decimal("1"))
        self.assertEqual(Decimal(line["unit_price"]), Decimal("100.00"))   # exclusive of tax
        self.assertEqual(line["tax_rate"], "18.00")
        self.assertEqual(Decimal(line["discount"]), Decimal("10.00"))
        self.assertEqual(Decimal(line["value_excl_tax"]), Decimal("90.00"))
        self.assertEqual(Decimal(line["tax"]), Decimal("16.20"))
        self.assertEqual(Decimal(line["total"]), Decimal("106.20"))
        # The lines add up to what the customer paid.
        self.assertEqual(sum(Decimal(row["total"]) for row in data["fiscal_lines"]), Decimal(data["totals"]["total"]))

    def test_quantities_print_in_plain_notation(self):
        from fiscal.models import FiscalInvoiceLine
        FiscalInvoiceLine.objects.filter(invoice__order_id=self.order_id).update(quantity=Decimal("10.0000"))
        self.assertEqual(_receipt(self.owner_api, self.order_id).json()["fiscal_lines"][0]["quantity"], "10")
        FiscalInvoiceLine.objects.filter(invoice__order_id=self.order_id).update(quantity=Decimal("2.5000"))
        self.assertEqual(_receipt(self.owner_api, self.order_id).json()["fiscal_lines"][0]["quantity"], "2.5")

    def test_accepted_receipt_qr_is_the_bare_symbol(self):
        fiscal = _receipt(self.owner_api, self.order_id).json()["fiscal"]
        self.assertEqual(fiscal["status"], "accepted")
        image = Image.open(io.BytesIO(base64.b64decode(fiscal["qr_png_base64"])))
        # No quiet zone: the corner module of a finder pattern is black.
        self.assertEqual(image.getpixel((0, 0)), 0)

    def test_other_tenant_cannot_read_the_receipt(self):
        self.assertEqual(_receipt(self.api_client(self.user_a), self.order_id).status_code, 404)


class ReceiptWithoutFBRTests(CheckoutFixture):
    def test_no_fbr_configuration_means_no_ntn_pos_id_or_fiscal_lines(self):
        data = self.checkout(amount="118.00", key="p3-nofbr").json()
        self.config.is_active = False
        self.config.save()
        receipt = _receipt(self.owner_api, data["order"]["id"]).json()
        self.assertEqual(receipt["business"]["pos_registration_number"], "")
        self.assertEqual(receipt["business"]["ntn"], "")
        self.assertFalse(receipt["business"]["fbr_integrated"])

    def test_sale_without_a_fiscal_invoice_has_no_fiscal_lines(self):
        data = self.checkout(amount="118.00", key="p3-noinv").json()
        from fiscal.models import FiscalInvoice
        FiscalInvoice.objects.filter(tenant=self.tenant_b, order_id=data["order"]["id"]).update(status=FiscalInvoice.STATUS_VOID)
        receipt = _receipt(self.owner_api, data["order"]["id"]).json()
        self.assertEqual(receipt["fiscal_lines"], [])
        self.assertEqual(len(receipt["items"]), 1)


class QRRenderTests(CheckoutFixture):
    def test_quiet_zone_is_optional_and_defaults_to_four_modules(self):
        bare = Image.open(io.BytesIO(render_qr_png("110014-131026143000-0001", module_size=1, quiet_zone=0)))
        framed = Image.open(io.BytesIO(render_qr_png("110014-131026143000-0001", module_size=1)))
        self.assertEqual(framed.size[0], bare.size[0] + 2 * QUIET_ZONE_MODULES)
        self.assertEqual(framed.getpixel((0, 0)), 255)
        self.assertEqual(bare.getpixel((0, 0)), 0)


class ReceiptPrintAuditTests(CheckoutFixture):
    def setUp(self):
        super().setUp()
        self.order_id = self.checkout(amount="118.00", key="p3-print").json()["order"]["id"]

    def _events(self):
        return AuditEvent.objects.filter(tenant=self.tenant_b, action=AuditEvent.ACTION_PRINT,
                                         entity_type="pos_receipt", entity_id=str(self.order_id))

    def test_first_print_is_the_original_and_later_prints_are_reprints(self):
        first = _printed(self.owner_api, self.order_id)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), {"order_id": self.order_id, "copy": 1, "reprint": False})
        second = _printed(self.owner_api, self.order_id).json()
        self.assertEqual((second["copy"], second["reprint"]), (2, True))
        events = list(self._events().order_by("id"))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].actor, self.user_b)
        self.assertEqual(events[1].after, {"copy": 2, "reprint": True})

    def test_other_tenant_cannot_record_or_count_prints(self):
        response = _printed(self.api_client(self.user_a), self.order_id)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self._events().exists())
        self.assertFalse(AuditEvent.objects.filter(tenant=self.tenant_a, entity_type="pos_receipt").exists())

    def test_prints_in_another_tenant_do_not_change_the_copy_number(self):
        AuditEvent.objects.create(tenant=self.tenant_a, action=AuditEvent.ACTION_PRINT,
                                  entity_type="pos_receipt", entity_id=str(self.order_id))
        self.assertEqual(_printed(self.owner_api, self.order_id).json()["copy"], 1)

    def test_requires_pos_view_permission(self):
        user = User.objects.create_user(username="noperm_b", password="x-pass-123")
        TenantMembership.objects.create(tenant=self.tenant_b, user=user, role=TenantMembership.ROLE_STAFF,
                                        is_active_in_tenant=True)
        self.assertEqual(_printed(self.api_client(user), self.order_id).status_code, 403)
        role = Role.objects.create(key="p3-viewer", label="Viewer", tenant=self.tenant_b)
        role.permissions.add(*Permission.objects.filter(module__key="pos", action="view", scope="tenant"))
        UserRole.objects.create(user=user, role=role, tenant=self.tenant_b)
        self.assertEqual(_printed(self.api_client(user), self.order_id).status_code, 200)

    def test_unauthenticated_and_draft_orders_are_refused(self):
        from rest_framework.test import APIClient
        self.assertIn(_printed(APIClient(), self.order_id).status_code, (401, 403))
        Order.objects.filter(pk=self.order_id).update(status="draft")
        self.assertEqual(_printed(self.owner_api, self.order_id).status_code, 400)
        self.assertFalse(self._events().exists())
