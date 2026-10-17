from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import BundleComponent, ProductBundle, ProductMedia, ProductVariant
from pos.models import Category, Product
from pricing.models import PriceList
from saas.models import Tenant, TenantMembership
from tax.models import ProductTaxAssignment, TaxRate


class CatalogCompletionApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="completion-owner", password="test-password")
        self.other_owner = user_model.objects.create_user(username="completion-other", password="test-password")
        self.tenant = Tenant.objects.create(name="Completion Tenant", slug="completion-tenant", owner=self.owner, is_active=True)
        self.other_tenant = Tenant.objects.create(name="Completion Other", slug="completion-other", owner=self.other_owner, is_active=True)
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(user=self.other_owner, tenant=self.other_tenant, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        self.category = Category.objects.create(tenant=self.tenant, name="Parent")
        self.child = Category.objects.create(tenant=self.tenant, name="Child", parent=self.category)
        self.product = Product.objects.create(tenant=self.tenant, name="Visible Product", sku="COMPLETE-1", category=self.category, sales_price=Decimal("12.00"), cost_price=Decimal("5.00"))
        self.other_product = Product.objects.create(tenant=self.other_tenant, name="Foreign Product", sku="COMPLETE-2", sales_price=Decimal("12.00"), cost_price=Decimal("5.00"))
        self.rate = TaxRate.objects.create(tenant=self.tenant, name="VAT", code="VAT", rate=Decimal("0.13"))
        self.other_rate = TaxRate.objects.create(tenant=self.other_tenant, name="Foreign VAT", code="VAT", rate=Decimal("0.05"))
        self.price_list = PriceList.objects.create(tenant=self.tenant, name="Retail", currency="USD")
        PriceList.objects.create(tenant=self.other_tenant, name="Foreign Retail", currency="USD")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_category_tree_is_tenant_scoped_and_rejects_cycle(self):
        response = self.client.get("/api/categories/tree/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["id"], self.category.id)
        self.assertEqual(response.data[0]["children"][0]["id"], self.child.id)

        cycle_response = self.client.patch(f"/api/categories/{self.category.id}/", {"parent": self.child.id}, format="json")
        self.assertEqual(cycle_response.status_code, 400)
        self.assertIn("parent", cycle_response.data["error"]["fields"])

    def test_tax_assignments_and_rate_list_are_isolated_to_active_tenant(self):
        response = self.client.get("/api/tax/rates/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([entry["id"] for entry in response.data], [self.rate.id])

        create_response = self.client.post(f"/api/tax/products/{self.product.id}/assignments/", {"tax_rate": self.rate.id, "is_active": True}, format="json")
        self.assertEqual(create_response.status_code, 201)
        self.assertTrue(ProductTaxAssignment.objects.filter(tenant=self.tenant, product=self.product, tax_rate=self.rate).exists())

        foreign_response = self.client.post(f"/api/tax/products/{self.product.id}/assignments/", {"tax_rate": self.other_rate.id, "is_active": True}, format="json")
        self.assertEqual(foreign_response.status_code, 400)

    def test_pricing_lists_and_price_resolution_do_not_cross_tenants(self):
        response = self.client.get("/api/pricing/price-lists/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.price_list.id)

        foreign_response = self.client.get(f"/api/pricing/resolve/?product={self.other_product.id}&quantity=1")
        self.assertEqual(foreign_response.status_code, 404)

    def test_buy_x_get_y_list_filters_to_active_tenant_product(self):
        from pricing.models import BuyXGetY
        BuyXGetY.objects.create(tenant=self.tenant, product=self.product, buy_quantity=2, get_quantity=1)
        BuyXGetY.objects.create(tenant=self.other_tenant, product=self.other_product, buy_quantity=3, get_quantity=1)

        response = self.client.get(f"/api/pricing/buyx-gety/?product_id={self.product.id}&page_size=100")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["product"], self.product.id)

    def test_product_media_stamps_tenant_and_allows_one_primary_media(self):
        first = SimpleUploadedFile("first.png", b"not-a-real-png", content_type="image/png")
        first_response = self.client.post(f"/api/catalog/products/{self.product.id}/media/", {"file": first, "kind": "image"}, format="multipart")
        self.assertEqual(first_response.status_code, 201)
        self.assertTrue(first_response.data["is_primary"])

        second = SimpleUploadedFile("second.png", b"not-a-real-png", content_type="image/png")
        second_response = self.client.post(f"/api/catalog/products/{self.product.id}/media/", {"file": second, "kind": "image", "is_primary": True}, format="multipart")
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(ProductMedia.objects.filter(tenant=self.tenant, product=self.product, is_primary=True).count(), 1)

    def test_bundle_component_can_reference_exactly_one_concrete_variant(self):
        variant = ProductVariant.objects.create(tenant=self.tenant, product=self.product, sku="COMPLETE-1-RED", stock_quantity=Decimal("4"))

        response = self.client.post("/api/catalog/bundles/", {
            "name": "Variant bundle",
            "price_strategy": "sum",
            "components": [{"product": None, "variant": variant.id, "quantity": "2", "override_price": None}],
        }, format="json")

        self.assertEqual(response.status_code, 201)
        component = BundleComponent.objects.get(bundle_id=response.data["id"])
        self.assertIsNone(component.product)
        self.assertEqual(component.variant_id, variant.id)
