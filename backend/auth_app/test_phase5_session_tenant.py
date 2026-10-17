"""Phase 5: the session payload names the active business and its currency.

The frontend shows the active business in the sidebar and formats money with
the company currency. Cashiers cannot read /api/company/ (403), so the
currency travels with /api/auth/me/ and the login response.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from pos.models import Company
from saas.models import Tenant, TenantMembership

PASSWORD = "correct-horse-battery-staple"


class SessionTenantPayloadTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="biz-owner", password=PASSWORD)
        self.cashier = User.objects.create_user(username="biz-cashier", password=PASSWORD)
        self.tenant = Tenant.objects.create(name="Karachi Mart", slug="karachi-mart", owner=self.owner)
        self.other = Tenant.objects.create(name="Other Mart", slug="other-mart", owner=self.owner)
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.tenant, user=self.cashier, role="staff", is_active_in_tenant=True)
        Company.objects.create(tenant=self.tenant, name="Karachi Mart", address="", currency="PKR")
        Company.objects.create(tenant=self.other, name="Other Mart", address="", currency="AED")

    def login(self, user):
        response = self.client.post("/api/auth/login/", {
            "username": user.username, "password": PASSWORD, "device_id": f"dev-{user.username}",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def test_login_and_me_name_the_active_business_and_currency(self):
        login = self.login(self.cashier)
        expected = {"id": self.tenant.id, "name": "Karachi Mart", "slug": "karachi-mart", "currency": "PKR"}
        self.assertEqual(login.data["tenant"], expected)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login.data['token']}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["tenant"], expected)
        # A cashier gets the currency here although /api/company/ refuses them.
        self.assertEqual(me.data["user"]["role"], "staff")

    def test_currency_is_null_without_a_company_profile_and_none_is_created(self):
        Company.objects.filter(tenant=self.tenant).delete()
        login = self.login(self.cashier)
        self.assertIsNone(login.data["tenant"]["currency"])
        self.assertFalse(Company.objects.filter(tenant=self.tenant).exists())

    def test_user_without_a_business_gets_a_null_tenant(self):
        loner = get_user_model().objects.create_user(username="loner", password=PASSWORD)
        self.assertIsNone(self.login(loner).data["tenant"])

    def test_tenant_follows_the_active_membership_after_switching(self):
        TenantMembership.objects.create(tenant=self.other, user=self.cashier, role="staff", is_active_in_tenant=False)
        token = self.login(self.cashier).data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        switched = self.client.post("/api/saas/tenants/switch/", {"tenant_id": self.other.id}, format="json")
        self.assertEqual(switched.status_code, 200, switched.data)
        me = self.client.get("/api/auth/me/").data
        self.assertEqual((me["tenant"]["id"], me["tenant"]["currency"]), (self.other.id, "AED"))
        # The switcher lists only the user's own memberships.
        listed = self.client.get("/api/saas/tenants/").data
        self.assertEqual({row["id"] for row in listed}, {self.tenant.id, self.other.id})
        self.assertEqual([row["id"] for row in listed if row["is_active_in_tenant"]], [self.other.id])
