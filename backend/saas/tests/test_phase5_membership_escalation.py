"""Phase 5 security regression: POST /api/saas/tenants/members/ tenant takeover.

Before the fix any authenticated user (even one without a membership) could
POST {"tenant": <any id>, "user": <self>, "role": "owner"}, switch to that
tenant and read its data. Confirmed by probe on 2026-10-11.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from audit.models import AuditEvent
from saas.models import Tenant, TenantMembership

User = get_user_model()
URL = "/api/saas/tenants/members/"


@override_settings(ROOT_URLCONF="backend.urls")
class MembershipEscalationTests(TestCase):
    def setUp(self):
        self.owner_a = User.objects.create_user(username="owner_a", password="x-pass-123")
        self.owner_b = User.objects.create_user(username="owner_b", password="x-pass-123")
        self.tenant_a = Tenant.objects.create(name="A", slug="esc-a", owner=self.owner_a)
        self.tenant_b = Tenant.objects.create(name="B", slug="esc-b", owner=self.owner_b)
        TenantMembership.objects.create(tenant=self.tenant_a, user=self.owner_a, role="owner", is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.tenant_b, user=self.owner_b, role="owner", is_active_in_tenant=True)
        self.cashier_b = User.objects.create_user(username="cashier_b", password="x-pass-123")
        TenantMembership.objects.create(tenant=self.tenant_b, user=self.cashier_b, role="staff", is_active_in_tenant=True)
        self.newcomer = User.objects.create_user(username="newcomer", password="x-pass-123")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_staff_cannot_grant_themselves_ownership_of_another_tenant(self):
        api = self.client_for(self.cashier_b)
        response = api.post(URL, {"tenant": self.tenant_a.id, "user": self.cashier_b.id, "role": "owner",
                                  "is_active_in_tenant": False}, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(TenantMembership.objects.filter(tenant=self.tenant_a, user=self.cashier_b).exists())
        # The follow-up switch must therefore fail as well.
        switched = api.post("/api/saas/tenants/switch/", {"tenant_id": self.tenant_a.id}, format="json")
        self.assertEqual(switched.status_code, 403, switched.data)

    def test_user_without_any_membership_cannot_join_a_tenant(self):
        response = self.client_for(self.newcomer).post(
            URL, {"tenant": self.tenant_a.id, "user": self.newcomer.id, "role": "owner"}, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(TenantMembership.objects.filter(user=self.newcomer).exists())

    def test_staff_cannot_add_members_to_their_own_tenant(self):
        response = self.client_for(self.cashier_b).post(
            URL, {"user": self.newcomer.id, "role": "staff"}, format="json")
        self.assertEqual(response.status_code, 403, response.data)

    def test_owner_cannot_add_members_to_a_different_tenant(self):
        response = self.client_for(self.owner_b).post(
            URL, {"tenant": self.tenant_a.id, "user": self.newcomer.id, "role": "staff"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(TenantMembership.objects.filter(tenant=self.tenant_a, user=self.newcomer).exists())

    def test_owner_cannot_grant_the_owner_role(self):
        response = self.client_for(self.owner_b).post(
            URL, {"user": self.newcomer.id, "role": "owner"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(TenantMembership.objects.filter(user=self.newcomer).exists())

    def test_owner_adds_staff_to_the_active_tenant_only_and_it_is_audited(self):
        response = self.client_for(self.owner_b).post(
            URL, {"user": self.newcomer.id, "role": "staff", "is_active_in_tenant": True}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        membership = TenantMembership.objects.get(user=self.newcomer)
        self.assertEqual(membership.tenant_id, self.tenant_b.id)
        self.assertEqual(membership.role, "staff")
        # The endpoint never selects the active tenant on another user's behalf.
        self.assertFalse(membership.is_active_in_tenant)
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant_b, action="saas.membership.created").exists())

    def test_duplicate_membership_is_a_validation_error(self):
        response = self.client_for(self.owner_b).post(
            URL, {"user": self.cashier_b.id, "role": "admin"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(TenantMembership.objects.get(tenant=self.tenant_b, user=self.cashier_b).role, "staff")

    def test_switching_to_a_tenant_without_membership_is_403_not_500(self):
        response = self.client_for(self.owner_b).post(
            "/api/saas/tenants/switch/", {"tenant_id": self.tenant_a.id}, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        missing = self.client_for(self.owner_b).post(
            "/api/saas/tenants/switch/", {"tenant_id": 999999}, format="json")
        self.assertEqual(missing.status_code, 403, missing.data)
        self.assertTrue(TenantMembership.objects.get(user=self.owner_b).is_active_in_tenant)

    def test_members_list_stays_scoped_to_the_active_tenant(self):
        response = self.client_for(self.cashier_b).get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["tenant"] for row in response.data}, {self.tenant_b.id})
