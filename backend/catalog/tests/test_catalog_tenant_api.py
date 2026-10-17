from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from pos.models import Brand, Product
from saas.models import Tenant, TenantMembership


class CatalogTenantApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="catalog-owner", password="test-password")
        self.other_user = user_model.objects.create_user(username="catalog-other", password="test-password")
        self.outsider = user_model.objects.create_user(username="catalog-outsider", password="test-password")

        self.tenant = Tenant.objects.create(name="Catalog Tenant", slug="catalog-tenant", owner=self.user, is_active=True)
        self.other_tenant = Tenant.objects.create(name="Other Catalog Tenant", slug="other-catalog-tenant", owner=self.other_user, is_active=True)
        TenantMembership.objects.create(user=self.user, tenant=self.tenant, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(user=self.other_user, tenant=self.other_tenant, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)

        self.product = Product.objects.create(tenant=self.tenant, name="Visible Product", sku="VISIBLE-SKU", sales_price=Decimal("12.00"), cost_price=Decimal("5.00"))
        Product.objects.create(tenant=self.other_tenant, name="Foreign Product", sku="FOREIGN-SKU", sales_price=Decimal("12.00"), cost_price=Decimal("5.00"))
        Brand.objects.create(tenant=self.tenant, name="Visible Brand")
        Brand.objects.create(tenant=self.other_tenant, name="Foreign Brand")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_product_router_returns_only_the_active_tenant_catalog(self):
        response = self.client.get("/api/products/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.product.id)

    def test_catalog_brand_endpoints_scope_reads_and_stamp_writes_to_active_tenant(self):
        response = self.client.get("/api/catalog/brands/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Visible Brand")

        create_response = self.client.post("/api/catalog/brands/", {"name": "Created In Tenant"}, format="json")

        self.assertEqual(create_response.status_code, 201)
        self.assertTrue(Brand.objects.filter(tenant=self.tenant, name="Created In Tenant").exists())
        self.assertFalse(Brand.objects.filter(tenant=self.other_tenant, name="Created In Tenant").exists())

    def test_unaffiliated_user_cannot_access_catalog_records(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.get("/api/catalog/brands/")

        self.assertEqual(response.status_code, 403)


class CatalogProductExportTests(TestCase):
    """Phase 5: the Products screen exports through this endpoint."""

    def setUp(self):
        CatalogTenantApiTests.setUp(self)
        Product.objects.create(tenant=self.tenant, name='=HYPERLINK("http://evil","x")', sku="@SKU",
                               sales_price=Decimal("1.00"), cost_price=Decimal("1.00"))

    def test_export_is_tenant_scoped_and_neutralises_formulas(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/catalog/products/export/csv/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Visible Product", body)
        self.assertNotIn("Foreign Product", body)
        self.assertIn("'=HYPERLINK", body)
        self.assertIn("'@SKU", body)
        self.assertNotIn(',=HYPERLINK', body.replace('"', ""))

    def test_member_without_catalog_manage_is_refused(self):
        staff = get_user_model().objects.create_user(username="catalog-staff", password="test-password")
        TenantMembership.objects.create(user=staff, tenant=self.tenant, role=TenantMembership.ROLE_STAFF, is_active_in_tenant=True)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/catalog/products/export/csv/").status_code, 403)
