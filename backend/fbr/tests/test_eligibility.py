"""Fiscalization-track eligibility gate (audit H8): integration mode is a
platform-verified registration fact, not a free tenant choice."""
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from fbr.models import FBRTenantEligibility, FBRConfiguration

from .base import FBRTestBase


@override_settings(ROOT_URLCONF="backend.urls")
class EligibilityTests(FBRTestBase):
    def test_tenants_default_to_the_di_track(self):
        from fbr.models import tenant_allowed_modes

        self.assertEqual(tenant_allowed_modes(self.tenant_a), {"di"})
        self.assertEqual(self.config_a.integration_mode, "di")

    def test_tenant_cannot_self_select_ims_without_eligibility(self):
        client = self.api_client(self.user_a)
        payload = {
            "environment": "sandbox", "integration_mode": "ims",
            "pos_registration_number": 110099,
            "seller_ntn_cnic": "1234567", "seller_business_name": "S", "seller_address": "A",
        }
        # tenant_a's sandbox config already exists; PATCH it into IMS — blocked.
        response = client.patch(
            f"/api/fbr/configurations/{self.config_a.id}/",
            {"integration_mode": "ims"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("eligib", str(response.content).lower())
        self.config_a.refresh_from_db()
        self.assertEqual(self.config_a.integration_mode, "di")
        # And tenant_b cannot CREATE an IMS config either.
        client_b = self.api_client(self.user_b)
        response = client_b.post("/api/fbr/configurations/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            FBRConfiguration.objects.filter(tenant=self.tenant_b, integration_mode="ims").exists()
        )

    def test_operator_command_grants_ims_and_then_config_is_accepted(self):
        call_command(
            "set_fbr_eligibility", self.tenant_b.slug,
            "--modes", "di,ims", "--reference", "eFBR Tier-1 registration verified",
        )
        self.assertTrue(FBRTenantEligibility.objects.filter(tenant=self.tenant_b, is_active=True).exists())
        client = self.api_client(self.user_b)
        payload = {
            "environment": "sandbox", "integration_mode": "ims",
            "pos_registration_number": 110099,
            "seller_ntn_cnic": "1234567", "seller_business_name": "S", "seller_address": "A",
        }
        response = client.post("/api/fbr/configurations/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["integration_mode"], "ims")

    def test_command_rejects_unknown_modes_and_slugs(self):
        with self.assertRaises(CommandError):
            call_command("set_fbr_eligibility", self.tenant_b.slug, "--modes", "graphql")
        with self.assertRaises(CommandError):
            call_command("set_fbr_eligibility", "no-such-tenant")

    def test_eligibility_api_reports_modes_without_leaking(self):
        client = self.api_client(self.user_a)
        response = client.get("/api/fbr/eligibility/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"allowed_modes": ["di"], "verified": False, "reference": ""})

        call_command("set_fbr_eligibility", self.tenant_a.slug, "--modes", "di,ims", "--reference", "REF-1")
        response = client.get("/api/fbr/eligibility/")
        self.assertEqual(response.json(), {"allowed_modes": ["di", "ims"], "verified": True, "reference": "REF-1"})

    def test_di_mode_remains_selectable_without_any_eligibility_record(self):
        client = self.api_client(self.user_b)
        response = client.post("/api/fbr/configurations/", {
            "environment": "sandbox", "integration_mode": "di",
            "security_token": "tok", "seller_ntn_cnic": "7654321",
            "seller_business_name": "DI Co", "seller_address": "Lahore",
            "seller_province": self.province_punjab.id, "scenario_id": "SN001",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
