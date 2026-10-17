"""
Regression tests for loyalty module security fixes:
1. RBAC enforcement — all viewsets require TenantRBACPermission
2. Tenant injection prevention — tenant field is read-only on all serializers
3. Tenant auto-assignment — perform_create injects request.tenant
4. Coupon validation scoped to tenant
5. Cross-tenant isolation — one tenant cannot see/use another's coupons, tiers, etc.
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from saas.models import Tenant, TenantMembership
from loyalty.models import LoyaltyProgram, MembershipTier, LoyaltyTransaction, Coupon, Promotion
from auth_app.models import AuthToken
from rbac.models import Module, Role, Permission, UserRole

User = get_user_model()


class LoyaltyTestBase(TestCase):
    """Shared setUp for loyalty tests — creates two tenants with RBAC roles."""

    def setUp(self):
        # ── Tenant A ──
        self.user_a = User.objects.create_user(
            username="loyalty-admin-a", password="testpass123", email="loyalty-a@test.com"
        )
        self.tenant_a = Tenant.objects.create(
            name="Loyalty Tenant A", slug="loyalty-ten-a", owner=self.user_a, status="active"
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a, user=self.user_a, role="owner", is_active_in_tenant=True
        )

        # Create the loyalty module + permissions
        self.loyalty_module, _ = Module.objects.get_or_create(
            key="loyalty", defaults={"label": "Loyalty"}
        )
        self.perm_view, _ = Permission.objects.get_or_create(
            module=self.loyalty_module, action="view", scope="tenant",
            defaults={"description": "View loyalty"}
        )
        self.perm_manage, _ = Permission.objects.get_or_create(
            module=self.loyalty_module, action="manage", scope="tenant",
            defaults={"description": "Manage loyalty"}
        )

        # Create an RBAC role for tenant A with loyalty permissions
        self.role_a, _ = Role.objects.get_or_create(
            key="loyalty-admin-a",
            defaults={"label": "Loyalty Admin A", "description": "loyalty admin", "scope": "tenant"}
        )
        self.role_a.permissions.add(self.perm_view, self.perm_manage)
        UserRole.objects.get_or_create(user=self.user_a, role=self.role_a, tenant=self.tenant_a)

        # ── Tenant B ──
        self.user_b = User.objects.create_user(
            username="loyalty-admin-b", password="testpass123", email="loyalty-b@test.com"
        )
        self.tenant_b = Tenant.objects.create(
            name="Loyalty Tenant B", slug="loyalty-ten-b", owner=self.user_b, status="active"
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b, user=self.user_b, role="owner", is_active_in_tenant=True
        )

        self.role_b, _ = Role.objects.get_or_create(
            key="loyalty-admin-b",
            defaults={"label": "Loyalty Admin B", "description": "loyalty admin", "scope": "tenant"}
        )
        self.role_b.permissions.add(self.perm_view, self.perm_manage)
        UserRole.objects.get_or_create(user=self.user_b, role=self.role_b, tenant=self.tenant_b)

        # ── Shared test data ──
        self.tier_a = MembershipTier.objects.create(
            tenant=self.tenant_a, name="Gold A", min_points=100, bonus_percent=Decimal("5.00")
        )
        self.tier_b = MembershipTier.objects.create(
            tenant=self.tenant_b, name="Gold B", min_points=200, bonus_percent=Decimal("10.00")
        )
        self.coupon_a = Coupon.objects.create(
            tenant=self.tenant_a, code="SAVE10A", discount_type="percent",
            discount_value=Decimal("10.00"), min_order=Decimal("50.00"),
            uses_total=100, uses_left=99, is_active=True,
        )
        self.coupon_b = Coupon.objects.create(
            tenant=self.tenant_b, code="SAVE10B", discount_type="fixed",
            discount_value=Decimal("25.00"), min_order=Decimal("100.00"),
            uses_total=50, uses_left=49, is_active=True,
        )
        self.promo_a = Promotion.objects.create(
            tenant=self.tenant_a, name="Summer Sale A", type="percent_off",
            start_date="2025-01-01", end_date="2025-12-31", is_active=True,
        )

    def _client(self, user):
        client = APIClient()
        token = AuthToken.objects.create(user=user)
        client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        return client


@override_settings(ROOT_URLCONF="backend.urls")
class LoyaltyRBACTests(LoyaltyTestBase):
    """Verify RBAC enforcement — unauthenticated / non-member requests are rejected."""

    def test_tier_list_requires_auth(self):
        client = APIClient()  # no credentials
        response = client.get("/api/loyalty/tiers/")
        self.assertIn(response.status_code, [401, 403])

    def test_coupon_list_requires_rbac(self):
        # user_c has no RBAC role for loyalty
        user_c = User.objects.create_user(username="no-role-user", password="testpass123")
        tenant_c = Tenant.objects.create(name="No Role Tenant", slug="no-role-ten", owner=user_c, status="active")
        TenantMembership.objects.create(tenant=tenant_c, user=user_c, role="manager", is_active_in_tenant=True)
        client = self._client(user_c)
        response = client.get("/api/loyalty/coupons/")
        # Should be 403 because user has no loyalty RBAC permission
        self.assertIn(response.status_code, [403, 404])


@override_settings(ROOT_URLCONF="backend.urls")
class LoyaltyTenantInjectionTests(LoyaltyTestBase):
    """Verify tenant field is read-only and auto-assigned by perform_create."""

    def test_cannot_inject_tier_tenant(self):
        client = self._client(self.user_a)
        response = client.post("/api/loyalty/tiers/", {
            "name": "Hacked Tier",
            "tenant": self.tenant_b.id,
            "min_points": 0,
            "bonus_percent": 0,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["tenant"], self.tenant_a.id)

    def test_cannot_inject_coupon_tenant(self):
        client = self._client(self.user_a)
        response = client.post("/api/loyalty/coupons/", {
            "code": "INJECT1",
            "tenant": self.tenant_b.id,
            "discount_type": "fixed",
            "discount_value": "5.00",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["tenant"], self.tenant_a.id)

    def test_cannot_inject_promotion_tenant(self):
        client = self._client(self.user_a)
        response = client.post("/api/loyalty/promotions/", {
            "name": "Hacked Promo",
            "tenant": self.tenant_b.id,
            "type": "percent_off",
            "start_date": "2025-01-01",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["tenant"], self.tenant_a.id)


@override_settings(ROOT_URLCONF="backend.urls")
class LoyaltyCouponValidationTests(LoyaltyTestBase):
    """Verify coupon validation is scoped to the requesting tenant."""

    def test_validate_own_coupon(self):
        client = self._client(self.user_a)
        response = client.post("/api/loyalty/coupons/validate/", {
            "code": "SAVE10A", "order_total": "100.00",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["valid"])
        self.assertIn("discount_amount", response.data)

    def test_validate_cross_tenant_coupon_fails(self):
        """Tenant A trying to validate Tenant B's coupon should get 404."""
        client = self._client(self.user_a)
        response = client.post("/api/loyalty/coupons/validate/", {
            "code": "SAVE10B", "order_total": "100.00",
        }, format="json")
        self.assertEqual(response.status_code, 404)

    def test_validate_inactive_coupon(self):
        self.coupon_a.is_active = False
        self.coupon_a.save()
        client = self._client(self.user_a)
        response = client.post("/api/loyalty/coupons/validate/", {
            "code": "SAVE10A", "order_total": "100.00",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["valid"])

    def test_validate_below_minimum_order(self):
        client = self._client(self.user_a)
        response = client.post("/api/loyalty/coupons/validate/", {
            "code": "SAVE10A", "order_total": "10.00",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["valid"])


@override_settings(ROOT_URLCONF="backend.urls")
class LoyaltyCrossTenantIsolationTests(LoyaltyTestBase):
    """Verify one tenant cannot see or mutate another tenant's loyalty data."""

    def test_tier_list_excludes_other_tenant(self):
        client = self._client(self.user_a)
        response = client.get("/api/loyalty/tiers/")
        self.assertEqual(response.status_code, 200)
        ids = [t["id"] for t in (response.data.get("results", response.data)
                                  if isinstance(response.data, dict) else response.data)]
        self.assertIn(self.tier_a.id, ids)
        self.assertNotIn(self.tier_b.id, ids)

    def test_coupon_list_excludes_other_tenant(self):
        client = self._client(self.user_a)
        response = client.get("/api/loyalty/coupons/")
        self.assertEqual(response.status_code, 200)
        ids = [c["id"] for c in (response.data.get("results", response.data)
                                  if isinstance(response.data, dict) else response.data)]
        self.assertIn(self.coupon_a.id, ids)
        self.assertNotIn(self.coupon_b.id, ids)

    def test_promotion_list_excludes_other_tenant(self):
        client = self._client(self.user_a)
        response = client.get("/api/loyalty/promotions/")
        self.assertEqual(response.status_code, 200)
        ids = [p["id"] for p in (response.data.get("results", response.data)
                                  if isinstance(response.data, dict) else response.data)]
        self.assertIn(self.promo_a.id, ids)

    def test_program_singleton_is_tenant_scoped(self):
        """Each tenant gets its own LoyaltyProgram via get_or_create."""
        client_a = self._client(self.user_a)
        client_b = self._client(self.user_b)
        resp_a = client_a.get("/api/loyalty/program/")
        resp_b = client_b.get("/api/loyalty/program/")
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_b.status_code, 200)
        self.assertNotEqual(resp_a.data["id"], resp_b.data["id"])
        self.assertEqual(resp_a.data["tenant"], self.tenant_a.id)
        self.assertEqual(resp_b.data["tenant"], self.tenant_b.id)
