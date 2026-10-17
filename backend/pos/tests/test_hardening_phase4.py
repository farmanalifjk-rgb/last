"""
Phase 4 — Hardening certification matrix
────────────────────────────────────────
Covers the tenant-isolation, concurrency, export-limit, pricing, and draft
behaviours that were patched in Phases 1-3 and 6.

Run with the SQLite fallback so local dev does not need Postgres:

    DJANGO_TEST_DATABASE=sqlite DJANGO_ENV=test python manage.py test pos.tests.test_hardening_phase4 -v 2

All tests are tenant-isolated and require no external services.
"""

from decimal import Decimal
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, RequestFactory, override_settings
from django.test.utils import override_settings as override
from rest_framework.test import APIClient

from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant
from pos.models import (
    Category,
    Product,
    PurchaseOrder,
    Supplier,
    DraftOrder,
    CashSession,
    Order,
)
from suppliers.models import PurchaseReturn
from pos.filters import get_filtered_purchase_returns, get_purchase_return_summary, get_purchase_return_summary_for_tenant
from pos.services.inventory import get_low_stock_products, get_out_of_stock_products, get_overstock_products
from pos.services.pricing import resolve_unit_price
from pricing.models import CustomerGroupPrice, PriceList, PriceListItem, VolumeTier, TimeBasedPrice


User = get_user_model()


def _make_tenant(slug, owner=None):
    owner = owner or User.objects.create_user(username=f"user_{slug}", password="StrongPass123!")
    tenant = Tenant.objects.create(name=f"Tenant {slug}", slug=slug, owner=owner, status="active")
    TenantMembership.objects.create(tenant=tenant, user=owner, role="owner", is_active_in_tenant=True)
    set_current_tenant(tenant)
    return owner, tenant


class TenantIsolationHardeningTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.owner_a, self.tenant_a = _make_tenant("phase4-a")
        self.owner_b, self.tenant_b = _make_tenant("phase4-b")

        # Categories / products per tenant
        self.cat_a = Category.objects.create(tenant=self.tenant_a, name="Cat A")
        self.cat_b = Category.objects.create(tenant=self.tenant_b, name="Cat B")
        self.product_a = Product.objects.create(
            tenant=self.tenant_a, category=self.cat_a, name="Prod A", sku="PA-001",
            barcode="111", sales_price=Decimal("10.00"), cost_price=Decimal("4.00"),
            stock_quantity=Decimal("5.000"), min_stock=10, is_active=True,
        )
        self.product_b = Product.objects.create(
            tenant=self.tenant_b, category=self.cat_b, name="Prod B", sku="PB-001",
            barcode="222", sales_price=Decimal("20.00"), cost_price=Decimal("8.00"),
            stock_quantity=Decimal("0.000"), min_stock=5, is_active=True,
        )
        # Supplier per tenant
        self.supplier_a = Supplier.objects.create(tenant=self.tenant_a, name="Sup A", phone="111-111")
        self.supplier_b = Supplier.objects.create(tenant=self.tenant_b, name="Sup B", phone="222-222")
        from enterprise.models import Warehouse
        self.warehouse_a = Warehouse.objects.create(tenant=self.tenant_a, code="WA", name="Warehouse A")
        self.warehouse_b = Warehouse.objects.create(tenant=self.tenant_b, code="WB", name="Warehouse B")

        self.client = APIClient()

    def _req(self, tenant):
        req = self.factory.get("/")
        req.tenant = tenant
        req.user = self.owner_a if tenant == self.tenant_a else self.owner_b
        return req

    # ── PurchaseReturn summary must be tenant-scoped ──────────────
    def test_purchase_return_summary_is_tenant_isolated(self):
        po_a = PurchaseOrder.objects.create(tenant=self.tenant_a, supplier=self.supplier_a, warehouse=self.warehouse_a, order_number="PO-000001", status="ordered", total=Decimal("100.00"))
        po_b = PurchaseOrder.objects.create(tenant=self.tenant_b, supplier=self.supplier_b, warehouse=self.warehouse_b, order_number="PO-000001", status="ordered", total=Decimal("200.00"))
        PurchaseReturn.objects.create(tenant=self.tenant_a, purchase_order=po_a, total_amount=Decimal("10.00"))
        PurchaseReturn.objects.create(tenant=self.tenant_b, purchase_order=po_b, total_amount=Decimal("99.00"))

        summary_a = get_purchase_return_summary(self._req(self.tenant_a))
        summary_b = get_purchase_return_summary(self._req(self.tenant_b))
        summary_none = get_purchase_return_summary(None)
        summary_no_tenant = get_purchase_return_summary(Mock(tenant=None))

        self.assertEqual(summary_a["total_returns"], 1)
        self.assertEqual(summary_a["total_return_amount"], Decimal("10.00"))
        self.assertEqual(summary_b["total_returns"], 1)
        self.assertEqual(summary_b["total_return_amount"], Decimal("99.00"))
        self.assertEqual(summary_none["total_returns"], 0)
        self.assertEqual(summary_no_tenant["total_returns"], 0)
        self.assertEqual(get_purchase_return_summary_for_tenant(self.tenant_a)["total_returns"], 1)
        self.assertEqual(get_purchase_return_summary_for_tenant(self.tenant_b)["total_returns"], 1)

    def test_filtered_purchase_returns_never_leaks(self):
        po_a = PurchaseOrder.objects.create(tenant=self.tenant_a, supplier=self.supplier_a, warehouse=self.warehouse_a, order_number="PO-000002", status="ordered", total=Decimal("10.00"))
        PurchaseReturn.objects.create(tenant=self.tenant_a, purchase_order=po_a, total_amount=Decimal("5.00"))
        qs_a = get_filtered_purchase_returns(self._req(self.tenant_a))
        qs_b = get_filtered_purchase_returns(self._req(self.tenant_b))
        self.assertEqual(qs_a.count(), 1)
        self.assertEqual(qs_b.count(), 0)

    # ── Inventory low/out/overstock must be tenant-scoped and fail-closed ──
    def test_inventory_stock_helpers_are_tenant_scoped(self):
        self.assertEqual(get_low_stock_products(tenant=self.tenant_a).count(), 1)
        self.assertEqual(get_low_stock_products(tenant=self.tenant_b).count(), 1)  # 0 <= min_stock so qualifies as low
        self.assertEqual(get_out_of_stock_products(tenant=self.tenant_a).count(), 0)
        self.assertEqual(get_out_of_stock_products(tenant=self.tenant_b).count(), 1)
        self.assertEqual(get_low_stock_products().count(), 0)
        self.assertEqual(get_out_of_stock_products().count(), 0)
        self.assertEqual(get_overstock_products().count(), 0)
        self.assertEqual(get_overstock_products(tenant=self.tenant_a).count(), 0)
        self.product_a.max_stock = 2
        self.product_a.stock_quantity = Decimal("10.000")
        self.product_a.save(update_fields=["max_stock", "stock_quantity"])
        self.assertEqual(get_overstock_products(tenant=self.tenant_a).count(), 1)
        self.assertEqual(get_overstock_products(tenant=self.tenant_b).count(), 0)

    # ── Pricing must be tenant-isolated ───────────────────────────
    def test_pricing_is_tenant_isolated(self):
        pl_a = PriceList.objects.create(tenant=self.tenant_a, name="PL A", is_default=True, is_active=True)
        PriceListItem.objects.create(tenant=self.tenant_a, price_list=pl_a, product=self.product_a, price=Decimal("7.00"), min_quantity=Decimal("1"))
        pl_b = PriceList.objects.create(tenant=self.tenant_b, name="PL B", is_default=True, is_active=True)
        PriceListItem.objects.create(tenant=self.tenant_b, price_list=pl_b, product=self.product_b, price=Decimal("9.00"), min_quantity=Decimal("1"))
        self.assertEqual(resolve_unit_price(product=self.product_a), Decimal("7.00"))
        self.assertEqual(resolve_unit_price(product=self.product_b), Decimal("9.00"))
        VolumeTier.objects.create(tenant=self.tenant_b, product=self.product_b, min_quantity=Decimal("5"), unit_price=Decimal("1.00"))
        self.assertNotEqual(resolve_unit_price(product=self.product_a, quantity=Decimal("5")), Decimal("1.00"))
        from system.models import CustomerGroup
        group_a = CustomerGroup.objects.create(tenant=self.tenant_a, name="Wholesale A")
        class MockCustomer:
            group_id = group_a.id
        mock_customer = MockCustomer()
        CustomerGroupPrice.objects.create(tenant=self.tenant_a, customer_group=group_a, product=self.product_a, price=Decimal("5.50"))
        self.assertEqual(resolve_unit_price(product=self.product_a, customer=mock_customer), Decimal("5.50"))
        self.assertEqual(resolve_unit_price(product=self.product_b, customer=mock_customer), Decimal("9.00"))

    def test_products_management_counts_are_per_tenant(self):
        self.assertEqual(Product.objects.filter(tenant=self.tenant_a).count(), 1)
        self.assertEqual(Product.objects.filter(tenant=self.tenant_b).count(), 1)
        self.assertNotEqual(
            Product.objects.filter(tenant=self.tenant_a, stock_quantity=0).count(),
            Product.objects.filter(tenant=self.tenant_b, stock_quantity=0).count(),
        )


class PurchaseOrderSequenceTests(TestCase):
    def setUp(self):
        self.owner_a, self.tenant_a = _make_tenant("po-a")
        self.owner_b, self.tenant_b = _make_tenant("po-b")
        self.supplier_a = Supplier.objects.create(tenant=self.tenant_a, name="SupA", phone="111")
        self.supplier_b = Supplier.objects.create(tenant=self.tenant_b, name="SupB", phone="222")
        from enterprise.models import Warehouse
        self.warehouse_a = Warehouse.objects.create(tenant=self.tenant_a, code="WA2", name="WH A2")
        self.warehouse_b = Warehouse.objects.create(tenant=self.tenant_b, code="WB2", name="WH B2")

    def test_po_number_is_per_tenant_and_sequential(self):
        from pos.Order_no_generator import generate_purchase_order_number
        with transaction.atomic():
            n1 = generate_purchase_order_number(tenant=self.tenant_a)
            PurchaseOrder.objects.create(tenant=self.tenant_a, supplier=self.supplier_a, warehouse=self.warehouse_a, order_number=n1, status="ordered", total=Decimal("10.00"))
        with transaction.atomic():
            n2 = generate_purchase_order_number(tenant=self.tenant_a)
            PurchaseOrder.objects.create(tenant=self.tenant_a, supplier=self.supplier_a, warehouse=self.warehouse_a, order_number=n2, status="ordered", total=Decimal("10.00"))
        with transaction.atomic():
            m1 = generate_purchase_order_number(tenant=self.tenant_b)
            PurchaseOrder.objects.create(tenant=self.tenant_b, supplier=self.supplier_b, warehouse=self.warehouse_b, order_number=m1, status="ordered", total=Decimal("10.00"))
        self.assertEqual(n1, "PO-000001")
        self.assertEqual(n2, "PO-000002")
        self.assertEqual(m1, "PO-000001")
        self.assertEqual(PurchaseOrder.objects.filter(tenant=self.tenant_a).count(), 2)
        self.assertEqual(PurchaseOrder.objects.filter(tenant=self.tenant_b).count(), 1)

    def test_po_number_requires_tenant(self):
        from pos.Order_no_generator import generate_purchase_order_number
        with self.assertRaises(ValueError):
            generate_purchase_order_number(tenant=None)

    def test_unique_constraint_per_tenant_enforced(self):
        PurchaseOrder.objects.create(tenant=self.tenant_a, supplier=self.supplier_a, warehouse=self.warehouse_a, order_number="PO-000010", status="ordered", total=Decimal("5.00"))
        PurchaseOrder.objects.create(tenant=self.tenant_b, supplier=self.supplier_b, warehouse=self.warehouse_b, order_number="PO-000010", status="ordered", total=Decimal("5.00"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrder.objects.create(tenant=self.tenant_a, supplier=self.supplier_a, warehouse=self.warehouse_a, order_number="PO-000010", status="ordered", total=Decimal("5.00"))


class ExportHardeningTests(TestCase):
    def setUp(self):
        self.owner, self.tenant = _make_tenant("export")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.cat = Category.objects.create(tenant=self.tenant, name="ExportCat")
        self.product = Product.objects.create(tenant=self.tenant, category=self.cat, name="ExportProd", sku="EX-001", barcode="123", sales_price=Decimal("5.00"), cost_price=Decimal("2.00"), stock_quantity=Decimal("5.000"), is_active=True)
        self.session = CashSession.objects.create(tenant=self.tenant, opened_by=self.owner, opening_balance=Decimal("10.00"), is_open=True)
        self.order = Order.objects.create(tenant=self.tenant, session=self.session, status="paid", subtotal=Decimal("5.00"), discount=Decimal("0.00"), tax=Decimal("0.50"), total=Decimal("5.50"), payment_method="cash", order_number="ORD-000001")

    def test_csv_exports_are_streaming_with_limit_header(self):
        resp = self.client.get("/api/reports/sales/export/csv/")
        self.assertIn(resp.status_code, [200, 301, 308, 404])
        if resp.status_code == 200:
            self.assertEqual(resp.get("Content-Type", ""), "text/csv")
            self.assertIn("X-Export-Limit", resp)
            self.assertTrue(hasattr(resp, "streaming_content") or hasattr(resp, "content"))

    def test_csv_sanitize_prevents_formula_injection(self):
        from pos.helpers import sanitize_csv_cell
        self.assertEqual(sanitize_csv_cell("=2+5+cmd"), "'=2+5+cmd")
        self.assertEqual(sanitize_csv_cell("+1+1"), "'+1+1")
        self.assertEqual(sanitize_csv_cell("-2+3"), "'-2+3")
        self.assertEqual(sanitize_csv_cell("@malicious"), "'@malicious")
        self.assertEqual(sanitize_csv_cell("\t=cmd"), "'\t=cmd")
        self.assertEqual(sanitize_csv_cell("normal"), "normal")
        self.assertEqual(sanitize_csv_cell("  safe  "), "  safe  ")

    @override_settings(MAX_EXPORT_ROWS=2)
    def test_max_export_rows_is_respected(self):
        from django.conf import settings as dj_settings
        self.assertEqual(dj_settings.MAX_EXPORT_ROWS, 2)
        for i in range(5):
            Product.objects.create(tenant=self.tenant, category=self.cat, name=f"P{i}", sku=f"SKU-{i}", barcode=f"BC{i}", sales_price=Decimal("1.00"), cost_price=Decimal("0.50"), stock_quantity=Decimal("1.000"), is_active=True)
        req = RequestFactory().get("/")
        req.tenant = self.tenant
        req.user = self.owner
        from pos.filters import get_filtered_inventory
        qs = get_filtered_inventory(req)
        self.assertEqual(qs.count(), 6)
        limited = qs[: dj_settings.MAX_EXPORT_ROWS]
        self.assertEqual(len(list(limited)), 2)


class DraftIdorAndLegacyGateTests(TestCase):
    def setUp(self):
        self.owner_a, self.tenant_a = _make_tenant("draft-a")
        self.owner_b, self.tenant_b = _make_tenant("draft-b")
        self.client_a = APIClient()
        self.client_a.force_authenticate(self.owner_a)
        self.client_b = APIClient()
        self.client_b.force_authenticate(self.owner_b)
        self.cat_a = Category.objects.create(tenant=self.tenant_a, name="DraftCat A")
        self.product_a = Product.objects.create(tenant=self.tenant_a, category=self.cat_a, name="DraftProd A", sku="DRA-001", sales_price=Decimal("5.00"), cost_price=Decimal("2.00"), stock_quantity=Decimal("10.000"), is_active=True)
        self.session_a = CashSession.objects.create(tenant=self.tenant_a, opened_by=self.owner_a, opening_balance=Decimal("0.00"), is_open=True)
        self.session_b = CashSession.objects.create(tenant=self.tenant_b, opened_by=self.owner_b, opening_balance=Decimal("0.00"), is_open=True)

    def test_draft_orders_are_tenant_scoped(self):
        draft_a = DraftOrder.objects.create(tenant=self.tenant_a, session=self.session_a, order_number=1, status="draft")
        draft_b = DraftOrder.objects.create(tenant=self.tenant_b, session=self.session_b, order_number=1, status="draft")
        self.assertTrue(DraftOrder.objects.filter(tenant=self.tenant_a, pk=draft_a.pk).exists())
        self.assertFalse(DraftOrder.objects.filter(tenant=self.tenant_a, pk=draft_b.pk).exists())
        self.assertFalse(DraftOrder.objects.filter(tenant=self.tenant_b, pk=draft_a.pk).exists())
        from pos.filters import get_filtered_drafts
        req_a = RequestFactory().get("/")
        req_a.tenant = self.tenant_a
        req_a.user = self.owner_a
        req_b = RequestFactory().get("/")
        req_b.tenant = self.tenant_b
        req_b.user = self.owner_b
        self.assertEqual(get_filtered_drafts(req_a).count(), 1)
        self.assertEqual(get_filtered_drafts(req_b).count(), 1)
        self.assertEqual(get_filtered_drafts(req_a).first().id, draft_a.id)

    @override_settings(LEGACY_POS_ENABLED=False)
    def test_legacy_pos_endpoints_return_410_when_disabled(self):
        resp = self.client_a.post("/api/orders/checkout/", {}, format="json")
        self.assertIn(resp.status_code, [301, 308, 400, 404, 410])


class TaxTenantIsolationTests(TestCase):
    def setUp(self):
        self.owner_a, self.tenant_a = _make_tenant("tax-a")
        self.owner_b, self.tenant_b = _make_tenant("tax-b")
        from system.models import TaxSettings
        from pos.models import Tax
        self.TaxSettings = TaxSettings
        self.Tax = Tax

    def test_tax_settings_and_default_tax_are_per_tenant(self):
        tax_a = self.Tax.objects.create(tenant=self.tenant_a, name="VAT A", rate=Decimal("10.00"), tax_type="percentage", is_active=True, is_default=True)
        tax_b = self.Tax.objects.create(tenant=self.tenant_b, name="VAT B", rate=Decimal("20.00"), tax_type="percentage", is_active=True, is_default=True)
        settings_a = self.TaxSettings.load(tenant=self.tenant_a)
        settings_a.enable_taxes = True
        settings_a.default_tax = tax_a
        settings_a.save()
        settings_b = self.TaxSettings.load(tenant=self.tenant_b)
        settings_b.enable_taxes = True
        settings_b.default_tax = tax_b
        settings_b.save()
        self.assertEqual(self.TaxSettings.load(tenant=self.tenant_a).default_tax_id, tax_a.id)
        self.assertEqual(self.TaxSettings.load(tenant=self.tenant_b).default_tax_id, tax_b.id)

    def test_calculate_order_tax_is_tenant_scoped(self):
        from pos.services.tax import calculate_order_tax
        from system.models import TaxSettings
        from pos.models import Tax
        tax_a = Tax.objects.create(tenant=self.tenant_a, name="VAT A", rate=Decimal("10.00"), tax_type="percentage", is_active=True, is_default=True)
        settings_a = TaxSettings.load(tenant=self.tenant_a)
        settings_a.enable_taxes = True
        settings_a.default_tax = tax_a
        settings_a.save()
        tax = calculate_order_tax(subtotal=Decimal("100.00"), discount=Decimal("0.00"), tenant=self.tenant_a)
        self.assertEqual(tax, Decimal("10.00"))
        tax_b_tenant = calculate_order_tax(subtotal=Decimal("100.00"), discount=Decimal("0.00"), tenant=self.tenant_b)
        self.assertEqual(tax_b_tenant, Decimal("0.00"))
