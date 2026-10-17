"""REST surface of the FBR integration — DI API v1.12."""
from django.test import override_settings

from fbr.models import FBRConfiguration

from .base import FBRTestBase


@override_settings(ROOT_URLCONF="backend.urls")
class ConfigurationAPITests(FBRTestBase):
    def test_security_token_is_never_returned(self):
        client = self.api_client(self.user_a)
        response = client.get("/api/fbr/configurations/")
        self.assertEqual(response.status_code, 200)
        rows = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn("security_token", row)
            self.assertTrue(row["has_security_token"])

    def test_configuration_is_created_for_the_active_tenant_only(self):
        client = self.api_client(self.user_b)
        response = client.post("/api/fbr/configurations/", {
            "environment": "sandbox", "security_token": "token-b",
            "seller_ntn_cnic": "7654321", "seller_business_name": "Buyer Co",
            "seller_address": "Plot 9, Lahore",
            "seller_province": self.province_punjab.id,
            "scenario_id": "SN001",
            "tenant": self.tenant_a.id,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        config = FBRConfiguration.objects.get(pk=response.data["id"])
        self.assertEqual(config.tenant_id, self.tenant_b.id)
        self.assertEqual(config.security_token, "token-b")
        self.assertEqual(config.seller_province_id, self.province_punjab.id)

    def test_production_configuration_requires_credentials(self):
        client = self.api_client(self.user_b)
        response = client.post("/api/fbr/configurations/", {
            "environment": "production", "seller_ntn_cnic": "", "security_token": "",
            "seller_province": self.province_sindh.id,
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_cannot_read_another_tenants_configuration(self):
        client = self.api_client(self.user_b)
        response = client.get(f"/api/fbr/configurations/{self.config_a.id}/")
        self.assertIn(response.status_code, [400, 403, 404])


@override_settings(ROOT_URLCONF="backend.urls")
class ProfileAPITests(FBRTestBase):
    def test_cannot_attach_a_profile_to_another_tenants_product(self):
        from pos.models import Product

        product_a = Product.objects.get(sku="SKU-A")
        client = self.api_client(self.user_b)
        response = client.post("/api/fbr/product-profiles/", {
            "product": product_a.id, "hs_code": self.hs_code.id, "uom": self.uom.id,
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_reference_lookups_include_provinces(self):
        client = self.api_client(self.user_a)
        for path in ["provinces", "transaction-types", "sro-schedules", "uom", "hs-codes"]:
            response = client.get(f"/api/fbr/reference/{path}/")
            self.assertEqual(response.status_code, 200, path)


@override_settings(ROOT_URLCONF="backend.urls")
class InvoiceAPITests(FBRTestBase):
    def test_preview_returns_the_v112_document(self):
        client = self.api_client(self.user_a)
        response = client.get(f"/api/fbr/invoices/{self.invoice_a.id}/preview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sellerNTNCNIC"], "1234567")
        self.assertEqual(response.data["sellerProvince"], "Sindh")
        self.assertEqual(response.data["invoiceType"], "Sale Invoice")
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["hsCode"], "8471.3010")

    def test_preview_with_string_invoice_type(self):
        client = self.api_client(self.user_a)
        response = client.get(f"/api/fbr/invoices/{self.invoice_a.id}/preview/?invoice_type=Sale Invoice")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["invoiceType"], "Sale Invoice")

    def test_preview_reports_validation_errors(self):
        self.config_a.security_token = ""
        self.config_a.save(update_fields=["security_token"])
        client = self.api_client(self.user_a)
        response = client.get(f"/api/fbr/invoices/{self.invoice_a.id}/preview/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.data["errors"])

    def test_cannot_preview_another_tenants_invoice(self):
        client = self.api_client(self.user_b)
        response = client.get(f"/api/fbr/invoices/{self.invoice_a.id}/preview/")
        self.assertIn(response.status_code, [400, 403, 404])

    def test_cannot_submit_another_tenants_invoice(self):
        client = self.api_client(self.user_b)
        response = client.post(f"/api/fbr/invoices/{self.invoice_a.id}/submit/")
        self.assertIn(response.status_code, [400, 403, 404])

    def test_submission_payloads_never_echo_credential_shaped_keys(self):
        # The security token travels only as an HTTP header and is never stored;
        # stored upstream payloads are arbitrary remote content, so the API
        # redacts credential-shaped keys before echoing them back.
        client = self.api_client(self.user_a)
        response = client.post(f"/api/fbr/invoices/{self.invoice_a.id}/submit/")
        self.assertIn(response.status_code, [200, 201, 400, 422, 502])
        for key in ("request_payload", "response_payload", "validation_response"):
            self.assertNotIn("Authorization", str(response.data.get(key, {})))
            self.assertNotIn("security_token", str(response.data.get(key, {})))

    def test_qr_requires_an_accepted_invoice(self):
        client = self.api_client(self.user_a)
        response = client.get(f"/api/fbr/invoices/{self.invoice_a.id}/qr.png")
        self.assertEqual(response.status_code, 400)

    def test_qr_is_rendered_once_fbr_accepted_the_invoice(self):
        self.invoice_a.fbr_invoice_number = "3310227771151DI1700000000123"
        self.invoice_a.save(update_fields=["fbr_invoice_number"])
        client = self.api_client(self.user_a)
        response = client.get(f"/api/fbr/invoices/{self.invoice_a.id}/qr.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
