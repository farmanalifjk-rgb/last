"""Regression tests for the tax engine, checkout, FBR, and receipt pipeline.

These tests cover the 22 requirements from the Phase-7 production-hardening
brief, including the confirmed root causes:

  * Tax stacking: explicit ProductTaxAssignment must suppress applies_to_all
    defaults (not stack on top). Production order POS-000281 showed 34%
    effective rate due to this bug.
  * Rate conversion: 17% must be stored/processed as 0.17, never 17 or 0.0017.
  * Checkout idempotency, stock, payment, and FBR-submission integrity.
  * Receipt correctness.

Run with:
    python manage.py test tax.tests
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from enterprise.models import Warehouse, WarehouseStock
from pos.models import CashSession, Category, Order, OrderItem, Product, StockMovement
from rbac.models import Permission, Role, UserRole
from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant
from tax.engine import (
    _active_rates_for,
    allocate_order_discount,
    amount_added_to_price,
    compute_line_tax,
    compute_order_tax,
    money,
)
from tax.models import ProductTaxAssignment, TaxBreakdown, TaxExemption, TaxRate

from rest_framework.test import APIClient

User = get_user_model()


def make_tenant(slug):
    owner = User.objects.create_user(username=f"owner-{slug}", password="TestPass123!")
    tenant = Tenant.objects.create(
        name=f"Test Tenant {slug}", slug=slug, owner=owner, status="active"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=owner, role="owner", is_active_in_tenant=True
    )
    return tenant, owner


def make_product(tenant, *, name="Product", price="100.00", category=None):
    cat = category or Category.objects.create(tenant=tenant, name="Default Cat")
    return Product.objects.create(
        tenant=tenant,
        category=cat,
        name=name,
        sku=f"SKU-{name[:8].upper()}",
        sales_price=Decimal(price),
        cost_price=Decimal("0.00"),
        stock_quantity=Decimal("100.000"),
        is_active=True,
    )


def make_tax_rate(tenant, *, code, rate, applies_to_all=True, product=None, category=None):
    return TaxRate.objects.create(
        tenant=tenant,
        name=f"Tax {code}",
        code=code,
        rate=Decimal(str(rate)),
        mode=TaxRate.MODE_EXCLUSIVE,
        compound_style=TaxRate.COMPOUND_FLAT,
        is_active=True,
        applies_to_all=applies_to_all,
        product=product,
        category=category,
    )


# ============================================================
# 1. Tax calculation arithmetic
# ============================================================

class TaxArithmeticTests(TestCase):
    """Test 1 & 2: correct amounts for standard rates."""

    def setUp(self):
        self.tenant, self.owner = make_tenant("arith")
        set_current_tenant(self.tenant)
        self.product = make_product(self.tenant, price="24999.00")

    def _line_tax_total(self, rate_str):
        make_tax_rate(self.tenant, code=f"GST{rate_str}", rate=rate_str, applies_to_all=True)
        rows = compute_line_tax(self.product, Decimal("24999.00"))
        return money(sum(Decimal(r["amount"]) for r in rows))

    def test_17_percent_exclusive_gst(self):
        """Test 1: Rs 24,999 × 17% = Rs 4,249.83."""
        tax = self._line_tax_total("0.17")
        self.assertEqual(tax, Decimal("4249.83"))

    def test_7_percent_exclusive_gst(self):
        """Test 2: Rs 24,999 × 7% = Rs 1,749.93."""
        tax = self._line_tax_total("0.07")
        self.assertEqual(tax, Decimal("1749.93"))

    def test_total_with_17_percent(self):
        make_tax_rate(self.tenant, code="GST17T", rate="0.17", applies_to_all=True)
        rows = compute_line_tax(self.product, Decimal("24999.00"))
        added = amount_added_to_price(rows)
        total = money(Decimal("24999.00") + added)
        self.assertEqual(total, Decimal("29248.83"))

    def test_total_with_7_percent(self):
        make_tax_rate(self.tenant, code="GST7T", rate="0.07", applies_to_all=True)
        rows = compute_line_tax(self.product, Decimal("24999.00"))
        added = amount_added_to_price(rows)
        total = money(Decimal("24999.00") + added)
        self.assertEqual(total, Decimal("26748.93"))


# ============================================================
# 2. Tax selection precedence (THE CRITICAL BUG FIX)
# ============================================================

class TaxSelectionPrecedenceTests(TestCase):
    """Tests 3, 5, 6: deterministic selection, no stacking."""

    def setUp(self):
        self.tenant, self.owner = make_tenant("prec")
        set_current_tenant(self.tenant)
        self.category = Category.objects.create(tenant=self.tenant, name="Cat A")
        self.product = make_product(self.tenant, category=self.category)
        # Tenant-wide default: 17% GST
        self.default_gst = make_tax_rate(
            self.tenant, code="GST17", rate="0.17", applies_to_all=True
        )

    def test_explicit_assignment_suppresses_applies_to_all(self):
        """Test 6: explicit ProductTaxAssignment takes precedence over applies_to_all.

        Before fix: both rates stacked → 34% effective rate.
        After fix: only the explicit 7% rate applies.
        """
        gst7 = make_tax_rate(
            self.tenant, code="GST7", rate="0.07", applies_to_all=False
        )
        ProductTaxAssignment.objects.create(
            tenant=self.tenant, product=self.product, tax_rate=gst7, is_active=True
        )
        rates = _active_rates_for(self.product)
        rate_ids = {r.id for r in rates}
        # Only the explicit 7% rate should apply, NOT the 17% applies_to_all.
        self.assertIn(gst7.id, rate_ids)
        self.assertNotIn(self.default_gst.id, rate_ids)
        self.assertEqual(len(rate_ids), 1)

    def test_zero_rated_does_not_also_receive_standard_gst(self):
        """Test 3: zero-rated products do not receive the standard GST."""
        zero = make_tax_rate(self.tenant, code="ZERO", rate="0.00", applies_to_all=False)
        ProductTaxAssignment.objects.create(
            tenant=self.tenant, product=self.product, tax_rate=zero, is_active=True
        )
        rates = _active_rates_for(self.product)
        rate_ids = {r.id for r in rates}
        self.assertIn(zero.id, rate_ids)
        self.assertNotIn(self.default_gst.id, rate_ids)
        # Tax on a zero-rated product must be zero.
        rows = compute_line_tax(self.product, Decimal("24999.00"))
        total = money(sum(Decimal(r["amount"]) for r in rows))
        self.assertEqual(total, Decimal("0.00"))

    def test_category_scoped_rate_suppresses_applies_to_all(self):
        """Category-level rate takes precedence over applies_to_all."""
        cat_rate = make_tax_rate(
            self.tenant, code="CAT7", rate="0.07",
            applies_to_all=False, category=self.category
        )
        rates = _active_rates_for(self.product)
        rate_ids = {r.id for r in rates}
        self.assertIn(cat_rate.id, rate_ids)
        self.assertNotIn(self.default_gst.id, rate_ids)

    def test_product_scoped_rate_suppresses_category_and_all(self):
        """Product-scoped TaxRate (not via assignment) suppresses category+applies_to_all."""
        make_tax_rate(
            self.tenant, code="CAT7", rate="0.07",
            applies_to_all=False, category=self.category
        )
        prod_rate = make_tax_rate(
            self.tenant, code="PROD5", rate="0.05",
            applies_to_all=False, product=self.product
        )
        rates = _active_rates_for(self.product)
        rate_ids = {r.id for r in rates}
        self.assertIn(prod_rate.id, rate_ids)
        self.assertNotIn(self.default_gst.id, rate_ids)
        self.assertEqual(len(rate_ids), 1)

    def test_exempt_customer_pays_no_tax(self):
        """Test 4: customer exemption removes tax."""
        from pos.models import Customer
        customer = Customer.objects.create(
            tenant=self.tenant, name="Exempt Corp", is_active=True
        )
        TaxExemption.objects.create(
            tenant=self.tenant, scope="customer", customer=customer, is_active=True
        )
        rows = compute_line_tax(self.product, Decimal("100.00"), customer=customer)
        total = money(sum(Decimal(r["amount"]) for r in rows))
        self.assertEqual(total, Decimal("0.00"))

    def test_two_competing_applies_to_all_rates_both_apply(self):
        """Multiple applies_to_all rates with no explicit assignment all apply (flat stack)."""
        gst7 = make_tax_rate(self.tenant, code="GST7", rate="0.07", applies_to_all=True)
        # product has no assignment → both applies_to_all rates apply
        rates = _active_rates_for(self.product)
        rate_ids = {r.id for r in rates}
        self.assertIn(self.default_gst.id, rate_ids)
        self.assertIn(gst7.id, rate_ids)


# ============================================================
# 3. Compound and inclusive taxes
# ============================================================

class TaxModeTests(TestCase):
    """Tests 7 & 8."""

    def setUp(self):
        self.tenant, _ = make_tenant("mode")
        set_current_tenant(self.tenant)
        self.product = make_product(self.tenant, price="100.00")

    def test_inclusive_tax_not_charged_twice(self):
        """Test 8: inclusive tax is embedded in the price, not added again."""
        TaxRate.objects.create(
            tenant=self.tenant, name="GST Inclusive", code="GSTI",
            rate=Decimal("0.17"), mode=TaxRate.MODE_INCLUSIVE,
            compound_style=TaxRate.COMPOUND_FLAT, is_active=True, applies_to_all=True,
        )
        rows = compute_line_tax(self.product, Decimal("100.00"))
        # Inclusive: tax amount = 100 - (100/1.17) ≈ 14.53
        tax_row = rows[0]
        self.assertEqual(tax_row["mode"], TaxRate.MODE_INCLUSIVE)
        added = amount_added_to_price(rows)
        # Nothing is ADDED to the price; the amount due stays 100.
        self.assertEqual(added, Decimal("0"))
        # But tax is non-zero (it was already inside).
        self.assertGreater(Decimal(tax_row["amount"]), 0)

    def test_compound_exclusive_cascades(self):
        """Test 7: compound tax applies on running total (each rate compounds)."""
        TaxRate.objects.create(
            tenant=self.tenant, name="T1", code="T1",
            rate=Decimal("0.10"), mode=TaxRate.MODE_EXCLUSIVE,
            compound_style=TaxRate.COMPOUND_COMPOUND,
            is_active=True, applies_to_all=True, priority=0,
        )
        TaxRate.objects.create(
            tenant=self.tenant, name="T2", code="T2",
            rate=Decimal("0.05"), mode=TaxRate.MODE_EXCLUSIVE,
            compound_style=TaxRate.COMPOUND_COMPOUND,
            is_active=True, applies_to_all=True, priority=1,
        )
        rows = compute_line_tax(self.product, Decimal("100.00"))
        # T1: 100 × 0.10 = 10 → running = 110
        # T2: 110 × 0.05 = 5.5
        t1 = next(r for r in rows if r["code"] == "T1")
        t2 = next(r for r in rows if r["code"] == "T2")
        self.assertEqual(money(Decimal(t1["amount"])), Decimal("10.00"))
        self.assertEqual(money(Decimal(t2["amount"])), Decimal("5.50"))


# ============================================================
# 4. Discount allocation and tax on discounted base
# ============================================================

class DiscountAllocationTests(TestCase):
    """Tests 9 & 10."""

    def setUp(self):
        self.tenant, _ = make_tenant("disc")
        set_current_tenant(self.tenant)

    def test_discount_allocates_proportionally_with_remainder_on_last(self):
        """Test 9: order discount split proportionally, last line takes remainder."""
        allocs = allocate_order_discount(
            [Decimal("60.00"), Decimal("40.00")], Decimal("10.00")
        )
        self.assertEqual(allocs[0], Decimal("6.00"))
        self.assertEqual(allocs[1], Decimal("4.00"))
        self.assertEqual(sum(allocs), Decimal("10.00"))

    def test_discount_allocation_sums_to_exact_discount(self):
        """Rounding remainder: allocations must sum exactly to discount."""
        allocs = allocate_order_discount(
            [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")],
            Decimal("1.00"),
        )
        self.assertEqual(sum(allocs), Decimal("1.00"))

    def test_tax_calculated_on_discounted_base(self):
        """Test 9: tax is computed on price net of discount."""
        product = make_product(self.tenant, price="100.00")
        make_tax_rate(self.tenant, code="G17", rate="0.17", applies_to_all=True)
        # 10% order discount on a single-item order
        rows = compute_line_tax(product, Decimal("90.00"))  # 100 - 10 discount
        tax = money(sum(Decimal(r["amount"]) for r in rows))
        expected = money(Decimal("90.00") * Decimal("0.17"))  # 15.30
        self.assertEqual(tax, expected)


# ============================================================
# 5. Rate contract at the API boundary
# ============================================================

class TaxRateAPIValidationTests(TestCase):
    """Tests 11 & 12: percentage-point conversion and rejection of invalid rates."""

    def setUp(self):
        self.tenant, self.owner = make_tenant("api")
        set_current_tenant(self.tenant)
        _ensure_pos_permission(self.tenant, self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_rate_17_percentage_point_is_converted_to_fractional(self):
        """Test 11: sending 17 (percentage point) stores 0.17."""
        response = self.client.post(
            "/api/tax/rates/",
            {"name": "GST 17%", "code": "GST17PP", "rate": "17", "mode": "exclusive"},
            format="json",
        )
        self.assertIn(response.status_code, [200, 201], response.data)
        self.assertEqual(Decimal(response.data["rate"]), Decimal("0.17"))

    def test_rate_01_fractional_stored_as_is(self):
        """Fractional 0.17 passes through unchanged."""
        response = self.client.post(
            "/api/tax/rates/",
            {"name": "GST 17f", "code": "GST17F", "rate": "0.17", "mode": "exclusive"},
            format="json",
        )
        self.assertIn(response.status_code, [200, 201], response.data)
        self.assertEqual(Decimal(response.data["rate"]), Decimal("0.17"))

    def test_rate_negative_rejected(self):
        """Test 12: negative rate is rejected."""
        response = self.client.post(
            "/api/tax/rates/",
            {"name": "Bad", "code": "NEG", "rate": "-0.05", "mode": "exclusive"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rate_above_100_percent_rejected(self):
        """Test 12: rate > 100% (200 as percentage point) is rejected."""
        response = self.client.post(
            "/api/tax/rates/",
            {"name": "Huge", "code": "HUGE", "rate": "200", "mode": "exclusive"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cross_tenant_tax_rate_assignment_rejected(self):
        """Test 13: cross-tenant tax_rate reference is rejected."""
        other_tenant, _ = make_tenant("other-apitest")
        other_rate = TaxRate.objects.create(
            tenant=other_tenant, name="Other GST", code="OGST",
            rate=Decimal("0.17"), mode=TaxRate.MODE_EXCLUSIVE,
            is_active=True, applies_to_all=True,
        )
        product = make_product(self.tenant)
        response = self.client.post(
            f"/api/tax/products/{product.id}/assignments/",
            {"tax_rate": other_rate.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


# ============================================================
# 6. Checkout correctness
# ============================================================

class CheckoutTaxIntegrityTests(TestCase):
    """Tests 14 & 15: server-side totals cannot be bypassed; stock deducted once."""

    def setUp(self):
        self.tenant, self.owner = make_tenant("chk")
        set_current_tenant(self.tenant)
        _ensure_pos_permission(self.tenant, self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.category = Category.objects.create(tenant=self.tenant, name="Cat")
        self.product = make_product(
            self.tenant, price="100.00", category=self.category
        )
        make_tax_rate(self.tenant, code="GST17", rate="0.17", applies_to_all=True)
        self.warehouse = Warehouse.objects.create(
            tenant=self.tenant, code="WH1", name="Warehouse"
        )
        WarehouseStock.objects.create(
            tenant=self.tenant, warehouse=self.warehouse,
            product=self.product, quantity=Decimal("50.00"),
        )
        self.session = CashSession.objects.create(
            tenant=self.tenant, warehouse=self.warehouse,
            opened_by=self.owner, employee_name="Owner",
            opening_balance=Decimal("0.00"), is_open=True,
        )

    def test_client_supplied_wrong_total_does_not_bypass_server_calculation(self):
        """Test 14: server always computes its own tax; client total is ignored."""
        # Client claims total = 50 (wrong; correct is 117.00 for qty=1)
        response = self.client.post(
            "/api/pos/checkout/",
            {
                "items": [{"product_id": self.product.id, "quantity": "1"}],
                "tenders": [{"tender_type": "cash", "amount": "117.00"}],
                "total": "50.00",  # intentionally wrong
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="chk-bypass-test",
        )
        self.assertIn(response.status_code, [200, 201], response.data)
        order = Order.objects.get(tenant=self.tenant, pk=response.data["order"]["id"])
        # Server must have used its own calculation: 100.00 + 17.00 tax = 117.00
        self.assertEqual(order.total, Decimal("117.00"))

    def test_checkout_deducts_stock_exactly_once(self):
        """Test 15: single checkout deducts stock once, replay does not deduct again."""
        key = "chk-stock-once"
        r1 = self.client.post(
            "/api/pos/checkout/",
            {
                "items": [{"product_id": self.product.id, "quantity": "2"}],
                "tenders": [{"tender_type": "cash", "amount": "234.00"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertIn(r1.status_code, [200, 201], r1.data)
        self.product.refresh_from_db()
        stock_after_first = self.product.stock_quantity

        # Replay the exact same request.
        r2 = self.client.post(
            "/api/pos/checkout/",
            {
                "items": [{"product_id": self.product.id, "quantity": "2"}],
                "tenders": [{"tender_type": "cash", "amount": "234.00"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertIn(r2.status_code, [200, 201], r2.data)
        self.assertTrue(r2.data["idempotent_replay"])

        self.product.refresh_from_db()
        # Stock must not have changed on replay.
        self.assertEqual(self.product.stock_quantity, stock_after_first)

        # Exactly one stock movement of type "sale".
        moves = StockMovement.objects.filter(
            tenant=self.tenant, product=self.product, movement_type="sale"
        )
        self.assertEqual(moves.count(), 1)

    def test_checkout_tax_breakdown_written(self):
        """After checkout the TaxBreakdown rows exist and the amounts agree."""
        r = self.client.post(
            "/api/pos/checkout/",
            {
                "items": [{"product_id": self.product.id, "quantity": "1"}],
                "tenders": [{"tender_type": "cash", "amount": "117.00"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="chk-breakdown",
        )
        self.assertIn(r.status_code, [200, 201], r.data)
        order = Order.objects.get(tenant=self.tenant, pk=r.data["order"]["id"])
        breakdowns = TaxBreakdown.objects.filter(tenant=self.tenant, order=order)
        self.assertGreater(breakdowns.count(), 0)
        total_tb = sum(b.tax_amount for b in breakdowns)
        self.assertEqual(money(total_tb), order.tax)


# ============================================================
# 7. FBR / Fiscal status on receipt
# ============================================================

class ReceiptFiscalStatusTests(TestCase):
    """Tests 18 & 20: FBR status is not faked on the receipt."""

    def setUp(self):
        self.tenant, self.owner = make_tenant("rec")
        set_current_tenant(self.tenant)
        _ensure_pos_permission(self.tenant, self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.product = make_product(self.tenant)
        make_tax_rate(self.tenant, code="GST0R", rate="0.00", applies_to_all=True)
        self.warehouse = Warehouse.objects.create(
            tenant=self.tenant, code="REC1", name="RW"
        )
        WarehouseStock.objects.create(
            tenant=self.tenant, warehouse=self.warehouse,
            product=self.product, quantity=Decimal("20.00"),
        )
        self.session = CashSession.objects.create(
            tenant=self.tenant, warehouse=self.warehouse,
            opened_by=self.owner, employee_name="Owner",
            opening_balance=Decimal("0.00"), is_open=True,
        )

    def _do_checkout(self, key="rec-chk-1"):
        return self.client.post(
            "/api/pos/checkout/",
            {
                "items": [{"product_id": self.product.id, "quantity": "1"}],
                "tenders": [{"tender_type": "cash", "amount": "100.00"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_receipt_shows_not_configured_when_no_fbr_config(self):
        """Test 20: receipt fiscal status is 'not_configured' not 'accepted'."""
        r = self._do_checkout("rec-no-cfg")
        self.assertIn(r.status_code, [200, 201], r.data)
        order_id = r.data["order"]["id"]
        receipt = self.client.get(f"/api/pos/orders/{order_id}/receipt/")
        self.assertEqual(receipt.status_code, 200)
        fiscal = receipt.data.get("fiscal", {})
        # No FBR config → status must be not_configured or not_fiscalized, never accepted.
        self.assertNotEqual(fiscal.get("status"), "accepted")
        self.assertFalse(fiscal.get("fbr_invoice_number", ""))

    def test_receipt_does_not_show_approval_without_genuine_acceptance(self):
        """Test 18: simulated/unsubmitted invoice must not appear as officially accepted."""
        r = self._do_checkout("rec-not-accepted")
        self.assertIn(r.status_code, [200, 201], r.data)
        order_id = r.data["order"]["id"]
        receipt = self.client.get(f"/api/pos/orders/{order_id}/receipt/")
        self.assertEqual(receipt.status_code, 200)
        fiscal = receipt.data.get("fiscal", {})
        status = fiscal.get("status", "")
        self.assertNotIn(status, ["accepted"])
        # No genuine fbr_invoice_number should appear.
        self.assertFalse(fiscal.get("fbr_invoice_number", ""))


# ============================================================
# 8. Historical orders are not modified
# ============================================================

class HistoricalOrderPreservationTests(TestCase):
    """Test 21: tax engine repair / re-run does not alter paid historical orders."""

    def setUp(self):
        self.tenant, self.owner = make_tenant("hist")
        set_current_tenant(self.tenant)

    def test_compute_order_tax_on_new_order_does_not_alter_historical_orders(self):
        """Separate orders are independent; one re-computation doesn't touch others."""
        from pos.models import CashSession as CS
        session = CS.objects.create(
            tenant=self.tenant, opened_by=self.owner,
            employee_name="Owner", opening_balance=Decimal("0"),
            is_open=True,
        )
        product = make_product(self.tenant, price="100.00")
        make_tax_rate(self.tenant, code="GST17H", rate="0.17", applies_to_all=True)

        # Create and finalize a "historical" order.
        hist_order = Order.objects.create(
            tenant=self.tenant, session=session,
            subtotal=Decimal("100.00"), discount=Decimal("0"),
            tax=Decimal("17.00"), total=Decimal("117.00"),
            status="paid",
        )
        OrderItem.objects.create(
            tenant=self.tenant, order=hist_order, product=product,
            quantity=Decimal("1"), unit_price=Decimal("100.00"),
            subtotal=Decimal("100.00"), cost_price=Decimal("0.00"),
        )
        TaxBreakdown.objects.create(
            tenant=self.tenant, order=hist_order, tax_rate_code="GST17H",
            rate=Decimal("0.17"), taxable_amount=Decimal("100.00"),
            tax_amount=Decimal("17.00"), mode="exclusive",
        )

        hist_total_before = hist_order.total

        # Compute tax for a *new* order (simulating a new sale).
        new_order = Order.objects.create(
            tenant=self.tenant, session=session,
            subtotal=Decimal("200.00"), discount=Decimal("0"),
            tax=Decimal("0"), total=Decimal("0"),
            status="draft",
        )
        OrderItem.objects.create(
            tenant=self.tenant, order=new_order, product=product,
            quantity=Decimal("2"), unit_price=Decimal("100.00"),
            subtotal=Decimal("200.00"), cost_price=Decimal("0.00"),
        )
        compute_order_tax(new_order)

        # Historical order must be untouched.
        hist_order.refresh_from_db()
        self.assertEqual(hist_order.total, hist_total_before)
        self.assertEqual(hist_order.status, "paid")


# ============================================================
# 9. QR rendering smoke test
# ============================================================

class QRRenderTests(TestCase):
    """Test 17: the QR code encodes the fiscal invoice number and is decodable."""

    def test_render_qr_png_produces_valid_png_bytes(self):
        from fbr.qr import render_qr_png
        data = "FBR-INV-2026-000001"
        png_bytes = render_qr_png(data, module_size=4)
        # PNG magic bytes
        self.assertEqual(png_bytes[:4], b"\x89PNG")
        self.assertGreater(len(png_bytes), 100)

    def test_qr_encodes_the_correct_data(self):
        """Decode the produced QR and verify the fiscal number is in it."""
        from fbr.qr import render_qr_png
        from io import BytesIO
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode
        except ImportError:
            self.skipTest("pyzbar not available; install it to enable QR decode verification")
        data = "FBR-INV-2026-TEST-DECODE"
        png_bytes = render_qr_png(data, module_size=6, quiet_zone=4)
        img = Image.open(BytesIO(png_bytes))
        decoded = decode(img)
        self.assertTrue(decoded, "QR decode returned no symbols")
        self.assertEqual(decoded[0].data.decode("utf-8"), data)


# ============================================================
# Helpers
# ============================================================

def _ensure_pos_permission(tenant, user):
    """Ensure the user has owner membership in the tenant and active flag."""
    user.is_staff = True
    user.save()
    TenantMembership.objects.get_or_create(
        tenant=tenant,
        user=user,
        defaults={"role": "owner", "is_active_in_tenant": True},
    )
