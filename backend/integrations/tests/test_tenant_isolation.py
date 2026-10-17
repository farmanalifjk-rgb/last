from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from integrations.models import Integration, SyncLog
from saas.models import Tenant, TenantMembership


class IntegrationTenantIsolationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_superuser(
            username="integration-a", email="integration-a@example.test", password="test-password"
        )
        self.user_b = User.objects.create_user(username="integration-b", password="test-password")
        self.tenant_a = Tenant.objects.create(name="Integration Tenant A", slug="integration-tenant-a", owner=self.user_a)
        self.tenant_b = Tenant.objects.create(name="Integration Tenant B", slug="integration-tenant-b", owner=self.user_b)
        TenantMembership.objects.create(
            tenant=self.tenant_a, user=self.user_a,
            role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True,
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b, user=self.user_b,
            role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True,
        )
        self.integration_a = Integration.objects.create(
            tenant=self.tenant_a, kind=Integration.KIND_SHOPIFY, name="Primary", is_active=False,
        )
        self.integration_b = Integration.objects.create(
            tenant=self.tenant_b, kind=Integration.KIND_SHOPIFY, name="Primary", is_active=False,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user_a)

    def test_same_provider_name_is_allowed_in_different_tenants(self):
        self.assertNotEqual(self.integration_a.pk, self.integration_b.pk)
        self.assertEqual(Integration.objects.filter(kind=Integration.KIND_SHOPIFY, name="Primary").count(), 2)

    def test_sync_log_rejects_cross_tenant_integration_reference(self):
        log = SyncLog(
            tenant=self.tenant_a,
            integration=self.integration_b,
            direction=SyncLog.DIRECTION_INBOUND,
            entity_type="product",
        )
        with self.assertRaises(ValidationError):
            log.full_clean()

    def test_quickbooks_is_reported_as_not_implemented(self):
        response = self.client.post(
            "/api/integrations/",
            {"kind": Integration.KIND_QUICKBOOKS, "name": "QB", "is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not implemented", str(response.data).lower())

    def test_inactive_integration_sync_returns_controlled_unavailable_state(self):
        response = self.client.post(
            f"/api/integrations/{self.integration_a.id}/sync/",
            {"direction": "inbound", "entity_type": "product"},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "integration_unavailable")
