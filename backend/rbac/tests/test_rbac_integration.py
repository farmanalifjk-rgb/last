"""
RBAC integration test suite.

Verifies that the RBAC system correctly:
- Assigns and resolves permissions per tenant
- Enforces module/action access control
- Supports wildcard permissions
- Prevents unauthorized access
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from pos.models import Product
from rbac.models import Module, Permission, Role, UserRole
from saas.models import Tenant, TenantMembership

User = get_user_model()


class RBACIntegrationTestBase(TestCase):
    """Set up a tenant with RBAC roles and users."""

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="testpass123", is_staff=True)
        self.tenant = Tenant.objects.create(name="Test Tenant", slug="rbac-test", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)

        # Create modules and permissions
        self.pos_module = Module.objects.create(key="pos", label="POS")
        self.pos_view = Permission.objects.create(module=self.pos_module, action="view")
        self.pos_create = Permission.objects.create(module=self.pos_module, action="create")
        self.pos_refund = Permission.objects.create(module=self.pos_module, action="refund")

        self.catalog_module = Module.objects.create(key="catalog", label="Catalog")
        self.catalog_view = Permission.objects.create(module=self.catalog_module, action="view")

        # Create roles
        self.cashier_role = Role.objects.create(key="cashier", label="Cashier", scope="tenant", tenant=self.tenant)
        self.cashier_role.permissions.add(self.pos_view, self.pos_create)

        self.viewer_role = Role.objects.create(key="viewer", label="Viewer", scope="tenant", tenant=self.tenant)
        self.viewer_role.permissions.add(self.pos_view)

        # Create users
        self.cashier = User.objects.create_user(username="cashier", password="testpass123")
        TenantMembership.objects.create(tenant=self.tenant, user=self.cashier, role="staff", is_active_in_tenant=True)
        UserRole.objects.create(user=self.cashier, role=self.cashier_role, tenant=self.tenant)

        self.viewer = User.objects.create_user(username="viewer", password="testpass123")
        TenantMembership.objects.create(tenant=self.tenant, user=self.viewer, role="staff", is_active_in_tenant=True)
        UserRole.objects.create(user=self.viewer, role=self.viewer_role, tenant=self.tenant)

        self.no_role_user = User.objects.create_user(username="norole", password="testpass123")
        TenantMembership.objects.create(tenant=self.tenant, user=self.no_role_user, role="staff", is_active_in_tenant=True)

    def _auth_client(self, user):
        client = APIClient()
        from auth_app.models import AuthToken
        token = AuthToken.objects.create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client


@override_settings(ROOT_URLCONF="backend.urls")
class PermissionResolutionTests(RBACIntegrationTestBase):
    """Test that permission resolution works correctly."""

    def test_owner_has_wildcard_permissions(self):
        from rbac.checker import user_permissions
        perms = user_permissions(self.owner, tenant=self.tenant)
        self.assertIn("*.*", perms)

    def test_cashier_has_pos_view_and_create(self):
        from rbac.checker import user_permissions
        perms = user_permissions(self.cashier, tenant=self.tenant)
        self.assertIn("pos.view", perms)
        self.assertIn("pos.create", perms)

    def test_cashier_does_not_have_refund(self):
        from rbac.checker import user_permissions
        perms = user_permissions(self.cashier, tenant=self.tenant)
        self.assertNotIn("pos.refund", perms)

    def test_viewer_has_only_view(self):
        from rbac.checker import user_permissions
        perms = user_permissions(self.viewer, tenant=self.tenant)
        self.assertIn("pos.view", perms)
        self.assertNotIn("pos.create", perms)

    def test_no_role_user_has_no_permissions(self):
        from rbac.checker import user_permissions
        perms = user_permissions(self.no_role_user, tenant=self.tenant)
        self.assertEqual(len(perms), 0)

    def test_permission_check_function(self):
        from rbac.checker import has_permission
        self.assertTrue(has_permission(self.cashier, "pos", "view", tenant=self.tenant))
        self.assertTrue(has_permission(self.cashier, "pos", "create", tenant=self.tenant))
        self.assertFalse(has_permission(self.cashier, "pos", "refund", tenant=self.tenant))


@override_settings(ROOT_URLCONF="backend.urls")
class APIPermissionEnforcementTests(RBACIntegrationTestBase):
    """Test that API endpoints enforce RBAC permissions."""

    def test_viewer_can_list_products(self):
        client = self._auth_client(self.viewer)
        response = client.get("/api/products/")
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_create_product(self):
        client = self._auth_client(self.viewer)
        response = client.post("/api/products/", {"name": "Test", "sku": "T1", "sales_price": "10", "cost_price": "5"})
        self.assertIn(response.status_code, [403, 400])

    def test_no_role_user_gets_forbidden_on_rbac_management(self):
        client = self._auth_client(self.no_role_user)
        response = client.get("/api/rbac/roles/")
        self.assertIn(response.status_code, [403, 400])


@override_settings(ROOT_URLCONF="backend.urls")
class TenantScopeTests(RBACIntegrationTestBase):
    """Test that permissions are scoped to the correct tenant."""

    def test_permissions_do_not_leak_across_tenants(self):
        from rbac.checker import user_permissions
        other_tenant = Tenant.objects.create(name="Other", slug="other", owner=self.owner, status="active")
        # Cashier has no assignments in other_tenant.
        perms = user_permissions(self.cashier, tenant=other_tenant)
        self.assertEqual(len(perms), 0)
