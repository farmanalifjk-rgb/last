from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from pricing.models import CustomerGroupPrice, PriceList, PriceListItem, VolumeTier
from pos.models import Category, Customer, Order, Product, StockMovement, Tax
from inventory.services import apply_adjustment
from pos.services.pricing import resolve_unit_price
from pos.services.tax import calculate_order_tax
from reports.services import sales_summary
from rbac.models import Module, Permission, Role, UserRole
from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant
from system.models import CustomerGroup, POSSettings, TaxSettings


User = get_user_model()


class PricingAndTaxCertificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pricing-user", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Pricing Tenant", slug="pricing-tenant", owner=self.user, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role="owner", is_active_in_tenant=True)
        set_current_tenant(self.tenant)
        self.category = Category.objects.create(name="Certification")
        self.product = Product.objects.create(
            name="Certification Product",
            sku="CERT-001",
            category=self.category,
            sales_price=Decimal("10.00"),
            cost_price=Decimal("4.00"),
            stock_quantity=Decimal("100.000"),
            is_active=True,
        )
        self.customer_group = CustomerGroup.objects.create(name="Wholesale")
        self.customer = Customer.objects.create(name="Wholesale Customer", group=self.customer_group)
        self.tax = Tax.objects.create(
            name="Certification VAT",
            rate=Decimal("10.00"),
            tax_type="percentage",
            is_active=True,
            is_default=True,
        )
        tax_settings = TaxSettings.load()
        tax_settings.enable_taxes = True
        tax_settings.default_tax = self.tax
        tax_settings.tax_precision = 2
        tax_settings.save()

    def test_customer_group_price_has_authoritative_precedence(self):
        CustomerGroupPrice.objects.create(
            customer_group=self.customer_group,
            product=self.product,
            price=Decimal("7.50"),
        )
        PriceListItem.objects.create(
            price_list=PriceList.objects.create(name="Default", is_default=True),
            product=self.product,
            price=Decimal("8.00"),
            min_quantity=Decimal("1"),
        )
        self.assertEqual(resolve_unit_price(product=self.product, customer=self.customer), Decimal("7.50"))

    def test_volume_tier_overrides_base_price_when_quantity_qualifies(self):
        VolumeTier.objects.create(product=self.product, min_quantity=Decimal("5"), unit_price=Decimal("8.25"))
        self.assertEqual(resolve_unit_price(product=self.product, quantity=Decimal("5")), Decimal("8.25"))

    def test_tax_can_be_disabled_and_supports_percentage_and_fixed_modes(self):
        settings = TaxSettings.load()
        self.assertEqual(calculate_order_tax(subtotal=Decimal("100.00"), discount=Decimal("10.00")), Decimal("9.00"))
        settings.enable_taxes = False
        settings.save()
        self.assertEqual(calculate_order_tax(subtotal=Decimal("100.00"), discount=Decimal("0.00")), Decimal("0.00"))
        settings.enable_taxes = True
        self.tax.tax_type = "fixed"
        self.tax.rate = Decimal("3.25")
        self.tax.save(update_fields=["tax_type", "rate"])
        settings.default_tax = self.tax
        settings.save()
        self.assertEqual(calculate_order_tax(subtotal=Decimal("100.00"), discount=Decimal("50.00")), Decimal("3.25"))


class AuthorizationAndReportsCertificationTests(TestCase):
    def setUp(self):
        self.cashier = User.objects.create_user(username="cert-cashier", password="StrongPass123!")
        self.admin = User.objects.create_user(username="cert-admin", password="StrongPass123!", is_staff=True)
        self.tenant = Tenant.objects.create(name="Authorization Tenant", slug="authorization-tenant", owner=self.admin, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.cashier, role="staff", is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.tenant, user=self.admin, role="owner", is_active_in_tenant=True)
        self.client = APIClient()

    def test_non_admin_cannot_modify_company_settings(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.patch("/api/settings/company/", {"name": "Unauthorized"}, format="json")
        self.assertEqual(response.status_code, 403, response.data)

    def test_admin_can_read_company_settings(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/settings/company/")
        self.assertEqual(response.status_code, 200, response.data)

    def test_non_admin_cannot_read_all_settings_bundle(self):
        self.client.force_authenticate(self.cashier)
        response = self.client.get("/api/settings/all/")
        self.assertEqual(response.status_code, 403, response.data)

    def test_reports_require_authentication_and_authenticated_summary_is_available(self):
        anonymous = self.client.get("/api/reports/sales-summary/")
        self.assertEqual(anonymous.status_code, 401)
        report_role = Role.objects.create(key="cert-report-viewer", label="Certified report viewer")
        report_role.permissions.add(Permission.objects.get(module__key="reports", action="view"))
        UserRole.objects.create(user=self.cashier, role=report_role)
        self.client.force_authenticate(self.cashier)
        response = self.client.get("/api/reports/sales-summary/")
        self.assertEqual(response.status_code, 200, response.data)


class TenantIsolationCertificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tenant-user", password="StrongPass123!")
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a", owner=self.user)
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b", owner=self.user)
        TenantMembership.objects.create(tenant=self.tenant_a, user=self.user, role="owner", is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.tenant_b, user=self.user, role="staff", is_active_in_tenant=False)
        module, _ = Module.objects.get_or_create(key="products", defaults={"label": "Products"})
        permission, _ = Permission.objects.get_or_create(module=module, action="view")
        self.catalog_viewer_role = Role.objects.create(key="catalog-viewer", label="Catalog Viewer")
        self.catalog_viewer_role.permissions.add(permission)
        UserRole.objects.create(user=self.user, role=self.catalog_viewer_role, tenant=self.tenant_b)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_active_tenant_members_endpoint_excludes_other_tenant_memberships(self):
        response = self.client.get("/api/saas/tenants/members/")
        self.assertEqual(response.status_code, 200, response.data)
        returned_tenant_ids = {row["tenant"] for row in response.data}
        self.assertEqual(returned_tenant_ids, {self.tenant_a.id})

    def test_switching_tenant_changes_the_scoped_membership_set(self):
        switched = self.client.post("/api/saas/tenants/switch/", {"tenant_id": self.tenant_b.id}, format="json")
        self.assertEqual(switched.status_code, 200, switched.data)
        response = self.client.get("/api/saas/tenants/members/")
        self.assertEqual(response.status_code, 200, response.data)
        returned_tenant_ids = {row["tenant"] for row in response.data}
        self.assertEqual(returned_tenant_ids, {self.tenant_b.id})

    def test_product_api_isolation_follows_the_active_tenant(self):
        set_current_tenant(self.tenant_a)
        category_a = Category.objects.create(name="A Catalog")
        product_a = Product.objects.create(name="A Product", sku="A-001", category=category_a, sales_price=Decimal("5.00"), cost_price=Decimal("2.00"), stock_quantity=Decimal("1.000"))
        set_current_tenant(self.tenant_b)
        category_b = Category.objects.create(name="B Catalog")
        product_b = Product.objects.create(name="B Product", sku="B-001", category=category_b, sales_price=Decimal("6.00"), cost_price=Decimal("3.00"), stock_quantity=Decimal("1.000"))
        set_current_tenant(self.tenant_a)

        response_a = self.client.get("/api/products/")
        self.assertEqual(response_a.status_code, 200, response_a.data)
        rows_a = response_a.data.get("results", response_a.data) if isinstance(response_a.data, dict) else response_a.data
        self.assertEqual({row["id"] for row in rows_a}, {product_a.id})

        switched = self.client.post("/api/saas/tenants/switch/", {"tenant_id": self.tenant_b.id}, format="json")
        self.assertEqual(switched.status_code, 200, switched.data)
        response_b = self.client.get("/api/products/")
        self.assertEqual(response_b.status_code, 200, response_b.data)
        rows_b = response_b.data.get("results", response_b.data) if isinstance(response_b.data, dict) else response_b.data
        self.assertEqual({row["id"] for row in rows_b}, {product_b.id})

        switched_back = self.client.post("/api/saas/tenants/switch/", {"tenant_id": self.tenant_a.id}, format="json")
        self.assertEqual(switched_back.status_code, 200, switched_back.data)
        self.assertEqual(self.client.get(f"/api/products/{product_b.id}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/products/{product_b.id}/", {"name": "Tampered"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/products/{product_b.id}/").status_code, 404)
        self.assertTrue(Product.objects.filter(pk=product_b.id, tenant=self.tenant_b).exists())

        viewer = User.objects.create_user(username="catalog-viewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant_a, user=viewer, role="staff", is_active_in_tenant=True)
        UserRole.objects.create(user=viewer, role=self.catalog_viewer_role)
        viewer_client = APIClient()
        viewer_client.force_authenticate(viewer)
        self.assertEqual(viewer_client.get("/api/products/").status_code, 200)
        self.assertEqual(viewer_client.patch(f"/api/products/{product_a.id}/", {"name": "Denied"}, format="json").status_code, 403)

    def test_sales_reports_are_isolated_by_active_tenant(self):
        now = timezone.now()
        set_current_tenant(self.tenant_a)
        Order.objects.create(tenant=self.tenant_a, payment_method="cash", status="paid", subtotal=Decimal("100.00"), total=Decimal("100.00"))
        set_current_tenant(self.tenant_b)
        Order.objects.create(tenant=self.tenant_b, payment_method="cash", status="paid", subtotal=Decimal("200.00"), total=Decimal("200.00"))

        set_current_tenant(self.tenant_a)
        report_a = sales_summary(now - timedelta(days=1), now + timedelta(days=1))
        set_current_tenant(self.tenant_b)
        report_b = sales_summary(now - timedelta(days=1), now + timedelta(days=1))
        self.assertEqual(Decimal(report_a["gross_sales"]), Decimal("100.00"))
        self.assertEqual(Decimal(report_b["gross_sales"]), Decimal("200.00"))
        self.assertNotEqual(Decimal(report_a["gross_sales"]), Decimal(report_b["gross_sales"]))


class InventorySafetyCertificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="inventory-user", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Inventory Tenant", slug="inventory-tenant", owner=self.user, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role="owner", is_active_in_tenant=True)
        set_current_tenant(self.tenant)
        self.category = Category.objects.create(name="Inventory Certification")
        self.product = Product.objects.create(
            name="Limited Stock Product",
            sku="CERT-STOCK-001",
            category=self.category,
            sales_price=Decimal("10.00"),
            cost_price=Decimal("4.00"),
            stock_quantity=Decimal("1.000"),
            is_active=True,
        )
        POSSettings.load().save()

    def test_negative_stock_is_rejected_without_mutating_product_or_movement_log(self):
        with self.assertRaises(ValueError):
            apply_adjustment(
                tenant=self.tenant,
                product_id=self.product.id,
                quantity=Decimal("-2.000"),
                reason="Certification",
                reference="certification",
                movement_type="sale",
            )

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.stock_quantity,
            Decimal("1.000"),
        )

        self.assertFalse(
            StockMovement.objects.filter(
                tenant=self.tenant,
                product=self.product,
            ).exists()
        )


class ConcurrentInventoryCertificationTests(TransactionTestCase):
    reset_sequences = True

    @skipUnless(connection.vendor == "postgresql", "SQLite certification database cannot prove row-lock concurrency semantics")
    def test_concurrent_debits_cannot_oversell_stock(self):
        user = User.objects.create_user(username="concurrency-user", password="StrongPass123!")
        tenant = Tenant.objects.create(name="Concurrency Tenant", slug="concurrency-tenant", owner=user, status="active")
        TenantMembership.objects.create(tenant=tenant, user=user, role="owner", is_active_in_tenant=True)
        set_current_tenant(tenant)
        category = Category.objects.create(name="Concurrency Certification")
        product = Product.objects.create(
            tenant=tenant,
            name="Concurrent Product",
            sku="CERT-CONCURRENT-001",
            category=category,
            sales_price=Decimal("10.00"),
            cost_price=Decimal("4.00"),
            stock_quantity=Decimal("1.000"),
            is_active=True,
        )
        POSSettings.load().save()
        barrier = Barrier(2)
        product_id = product.id

        def debit_once():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                apply_adjustment(
                    tenant=tenant,
                    product_id=product_id,
                    quantity=Decimal("-1.000"),
                    reason="Certification concurrent debit",
                    movement_type="sale",
                )
                return "ok"
            except (ValueError, OperationalError):
                return "failed"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: debit_once(), range(2)))

        product.refresh_from_db()
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(product.stock_quantity, Decimal("0.000"))
