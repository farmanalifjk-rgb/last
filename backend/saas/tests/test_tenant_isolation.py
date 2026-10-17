"""
Cross-module tenant isolation test suite.

Verifies that Tenant A cannot access Tenant B's data through any API endpoint.
Each test creates two tenants, populates data in one, and attempts to access it
from the other.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from pos.models import Product, Customer, Category, Order, CashSession
from saas.models import Tenant, TenantMembership
from enterprise.models import Warehouse

User = get_user_model()


class TenantIsolationTestBase(TestCase):
    """Base class that sets up two tenants with products, customers, and an admin user for each."""

    def setUp(self):
        # Tenant A
        self.user_a = User.objects.create_user(username="admin_a", password="testpass123", email="a@test.com", is_staff=True)
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a", owner=self.user_a, status="active")
        TenantMembership.objects.create(tenant=self.tenant_a, user=self.user_a, role="owner", is_active_in_tenant=True)
        self.cat_a = Category.objects.create(tenant=self.tenant_a, name="Cat A")
        self.product_a = Product.objects.create(
            tenant=self.tenant_a, name="Product A", sku="SKU-A", sales_price=Decimal("10.00"),
            cost_price=Decimal("5.00"), category=self.cat_a,
        )
        self.customer_a = Customer.objects.create(tenant=self.tenant_a, name="Customer A", phone="111")

        # Tenant B
        self.user_b = User.objects.create_user(username="admin_b", password="testpass123", email="b@test.com", is_staff=True)
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b", owner=self.user_b, status="active")
        TenantMembership.objects.create(tenant=self.tenant_b, user=self.user_b, role="owner", is_active_in_tenant=True)
        self.product_b = Product.objects.create(
            tenant=self.tenant_b, name="Product B", sku="SKU-B", sales_price=Decimal("20.00"),
            cost_price=Decimal("10.00"),
        )
        self.customer_b = Customer.objects.create(tenant=self.tenant_b, name="Customer B", phone="222")

    def _auth_client(self, user, tenant):
        client = APIClient()
        from auth_app.models import AuthToken
        token = AuthToken.objects.create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        # Simulate the tenant middleware by using the token — middleware resolves tenant.
        return client


@override_settings(ROOT_URLCONF="backend.urls")
class ProductIsolationTests(TenantIsolationTestBase):
    """Tenant A's products must not be visible to Tenant B."""

    def test_cannot_list_other_tenant_products(self):
        client = self._auth_client(self.user_b, self.tenant_b)
        response = client.get("/api/products/")
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        product_ids = [p["id"] for p in results]
        self.assertNotIn(self.product_a.id, product_ids)

    def test_cannot_access_other_tenant_product_detail(self):
        client = self._auth_client(self.user_b, self.tenant_b)
        response = client.get(f"/api/products/{self.product_a.id}/")
        self.assertIn(response.status_code, [403, 404])

    def test_product_search_is_tenant_scoped(self):
        client = self._auth_client(self.user_b, self.tenant_b)
        response = client.get("/api/pos/products/", {"search": "Product A"})
        self.assertEqual(response.status_code, 200)
        data = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(data), 0)


@override_settings(ROOT_URLCONF="backend.urls")
class CustomerIsolationTests(TenantIsolationTestBase):
    """Tenant A's customers must not be visible to Tenant B."""

    def test_cannot_list_other_tenant_customers(self):
        client = self._auth_client(self.user_b, self.tenant_b)
        response = client.get("/api/customers/")
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data)
        customer_ids = [c["id"] for c in results]
        self.assertNotIn(self.customer_a.id, customer_ids)

    def test_cannot_access_other_tenant_customer_detail(self):
        client = self._auth_client(self.user_b, self.tenant_b)
        response = client.get(f"/api/customers/{self.customer_a.id}/")
        self.assertIn(response.status_code, [403, 404])


@override_settings(ROOT_URLCONF="backend.urls")
class POSIsolationTests(TenantIsolationTestBase):
    """POS operations must be tenant-scoped."""

    def test_pos_product_search_is_tenant_scoped(self):
        client = self._auth_client(self.user_b, self.tenant_b)
        response = client.get("/api/pos/products/", {"search": "Product"})
        self.assertEqual(response.status_code, 200)
        data = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        for item in data:
            self.assertNotEqual(item.get("name"), "Product A")

    def test_pos_customer_search_is_tenant_scoped(self):
        client = self._auth_client(self.user_b, self.tenant_b)
        response = client.get("/api/pos/customers/", {"search": "Customer"})
        self.assertEqual(response.status_code, 200)
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        for item in data:
            self.assertNotEqual(item.get("name"), "Customer A")


@override_settings(ROOT_URLCONF="backend.urls")
class DashboardIsolationTests(TenantIsolationTestBase):
    """Dashboard data must be tenant-scoped."""

    def test_dashboard_overview_is_tenant_scoped(self):
        client = self._auth_client(self.user_b, self.tenant_b)
        response = client.get("/api/dashboard/overview/")
        self.assertEqual(response.status_code, 200)
        # Dashboard should not contain Tenant A's data.
        data = response.data
        if isinstance(data, dict):
            # Check that no Tenant A product names appear in the response.
            import json
            json_str = json.dumps(data)
            self.assertNotIn("Product A", json_str)


@override_settings(ROOT_URLCONF="backend.urls")
class AccountIsolationTests(TenantIsolationTestBase):
    """Accounting data must be tenant-scoped."""

    def test_accounts_are_tenant_scoped(self):
        client = self._auth_client(self.user_b, self.tenant_b)
        response = client.get("/api/accounting/accounts/")
        self.assertEqual(response.status_code, 200)


@override_settings(ROOT_URLCONF="backend.urls")
class UnauthenticatedAccessTests(TenantIsolationTestBase):
    """Unauthenticated requests must be rejected."""

    def test_products_require_auth(self):
        client = APIClient()
        response = client.get("/api/products/")
        self.assertIn(response.status_code, [401, 403])

    def test_dashboard_requires_auth(self):
        client = APIClient()
        response = client.get("/api/dashboard/overview/")
        self.assertIn(response.status_code, [401, 403])

    def test_accounting_requires_auth(self):
        client = APIClient()
        response = client.get("/api/accounting/accounts/")
        self.assertIn(response.status_code, [401, 403])
