from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from saas.models import Tenant, TenantMembership
from pos.models import Company
from system.models import Store


class SystemScopeIsolationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.platform_user = User.objects.create_superuser(
            username="platform-admin", email="platform@example.test", password="test-password"
        )
        self.staff_user = User.objects.create_user(
            username="tenant-staff", password="test-password", is_staff=True
        )
        self.other_user = User.objects.create_user(username="other-tenant-user", password="test-password")
        self.tenant_a = Tenant.objects.create(name="System Tenant A", slug="system-tenant-a", owner=self.platform_user)
        self.tenant_b = Tenant.objects.create(name="System Tenant B", slug="system-tenant-b", owner=self.other_user)
        TenantMembership.objects.create(
            tenant=self.tenant_a, user=self.platform_user,
            role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True,
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a, user=self.staff_user,
            role=TenantMembership.ROLE_STAFF, is_active_in_tenant=True,
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b, user=self.other_user,
            role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True,
        )
        self.company_a = Company.objects.create(tenant=self.tenant_a, name="Company A")
        self.company_b = Company.objects.create(tenant=self.tenant_b, name="Company B")
        self.store_a = Store.objects.create(tenant=self.tenant_a, name="A Store", code="MAIN")
        self.store_b = Store.objects.create(tenant=self.tenant_b, name="B Store", code="MAIN")
        self.client = APIClient()

    def test_is_staff_is_not_platform_authority_for_global_singletons(self):
        self.client.force_authenticate(self.staff_user)

        response = self.client.get("/api/settings/pos/")

        self.assertEqual(response.status_code, 403)

    def test_company_settings_are_scoped_to_active_tenant(self):
        self.client.force_authenticate(self.platform_user)

        response = self.client.get("/api/settings/company/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.company_a.id)
        self.assertNotEqual(response.data["id"], self.company_b.id)

    def test_tenant_scoped_store_detail_denies_cross_tenant_identifier(self):
        self.client.force_authenticate(self.platform_user)

        response = self.client.get(f"/api/stores/{self.store_b.id}/")

        self.assertEqual(response.status_code, 404)

    def test_store_code_can_repeat_in_different_tenants(self):
        self.assertEqual(Store.objects.filter(code="MAIN").count(), 2)
