from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from saas.models import Tenant, TenantMembership
from saas.services import get_active_tenant_for_user


class TenantSelectorApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tenant-selector", password="test-password")
        self.other_user = get_user_model().objects.create_user(username="other-user", password="test-password")
        self.visible = Tenant.objects.create(name="Visible Tenant", slug="visible-tenant", owner=self.user, is_active=True)
        self.inactive_membership = Tenant.objects.create(name="Inactive Membership", slug="inactive-membership", owner=self.user, is_active=True)
        self.inactive_tenant = Tenant.objects.create(name="Inactive Tenant", slug="inactive-tenant", owner=self.user, is_active=False)
        self.foreign = Tenant.objects.create(name="Foreign Tenant", slug="foreign-tenant", owner=self.other_user, is_active=True)
        TenantMembership.objects.create(user=self.user, tenant=self.visible, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(user=self.user, tenant=self.inactive_membership, role=TenantMembership.ROLE_STAFF, is_active_in_tenant=False)
        TenantMembership.objects.create(user=self.user, tenant=self.inactive_tenant, role=TenantMembership.ROLE_STAFF, is_active_in_tenant=False)
        TenantMembership.objects.create(user=self.other_user, tenant=self.foreign, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_lists_only_authenticated_users_active_tenants_with_context_metadata(self):
        response = self.client.get("/api/saas/tenants/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [self.inactive_membership.id, self.visible.id])
        self.assertEqual([item["name"] for item in response.data], ["Inactive Membership", "Visible Tenant"])
        self.assertFalse(response.data[0]["is_active_in_tenant"])
        self.assertTrue(response.data[1]["is_active_in_tenant"])

    def test_tenant_header_cannot_override_canonical_membership_context(self):
        response = self.client.get("/api/saas/tenant/", HTTP_X_TENANT_ID=str(self.foreign.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tenant"]["id"], self.visible.id)

    def test_database_allows_only_one_active_workspace_per_user(self):
        with self.assertRaises(IntegrityError):
            TenantMembership.objects.create(
                user=self.user,
                tenant=self.inactive_membership,
                role=TenantMembership.ROLE_STAFF,
                is_active_in_tenant=True,
            )

    def test_superuser_membership_resolves_the_canonical_active_tenant(self):
        superuser = get_user_model().objects.create_superuser(
            username="tenant-admin", email="tenant-admin@example.test", password="test-password"
        )
        tenant = Tenant.objects.create(name="Admin Tenant", slug="admin-tenant", owner=superuser, is_active=True)
        TenantMembership.objects.create(
            user=superuser,
            tenant=tenant,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )

        self.assertEqual(get_active_tenant_for_user(superuser), tenant)
