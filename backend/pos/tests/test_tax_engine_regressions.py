from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase
from rest_framework import serializers

from pos.models import Category, Customer, Order, Product
from saas.models import Tenant
from tax.engine import TaxConfigurationError, _active_rates_for, allocate_order_discount, compute_line_tax, compute_order_tax
from tax.models import ProductTaxAssignment, TaxBreakdown, TaxExemption, TaxRate
from tax.serializers import TaxRateSerializer


User = get_user_model()


class TaxEngineRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tax-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Tax Tenant", slug="tax-tenant", owner=self.user, status="active")
        self.other_user = User.objects.create_user(username="tax-other", password="StrongPass123!")
        self.other_tenant = Tenant.objects.create(name="Other Tax Tenant", slug="other-tax-tenant", owner=self.other_user, status="active")
        self.category = Category.objects.create(tenant=self.tenant, name="Taxable")
        self.product = Product.objects.create(
            tenant=self.tenant, category=self.category, name="Item", sku="TAX-1",
            sales_price=Decimal("24999.00"), cost_price=Decimal("1.00"), stock_quantity=Decimal("10"),
        )

    def rate(self, code, value, **kwargs):
        kwargs.setdefault("applies_to_all", True)
        return TaxRate.objects.create(
            tenant=self.tenant, name=code, code=code, rate=Decimal(value), is_active=True, **kwargs,
        )

    def test_17_percent_exclusive_fraction_rate(self):
        self.rate("GST17", "0.1700")
        row = compute_line_tax(self.product, Decimal("24999.00"))[0]
        self.assertEqual(row["amount"], "4249.83")
        self.assertEqual(row["rate"], "0.1700")

    def test_7_percent_exclusive_fraction_rate(self):
        self.rate("GST7", "0.0700")
        row = compute_line_tax(self.product, Decimal("24999.00"))[0]
        self.assertEqual(row["amount"], "1749.93")

    def test_existing_percent_point_rate_is_rejected_at_checkout_selection(self):
        malformed = self.rate("GST17", "17.0000")
        ProductTaxAssignment.objects.create(tenant=self.tenant, product=self.product, tax_rate=malformed)
        with self.assertRaisesRegex(TaxConfigurationError, "must be between 0 and 1"):
            compute_line_tax(self.product, Decimal("100.00"))

    def test_zero_rate_and_standard_rate_are_ambiguous_not_stacked(self):
        self.rate("GST17", "0.1700", compound_style=TaxRate.COMPOUND_COMPOUND)
        self.rate("GST7", "0.0700", compound_style=TaxRate.COMPOUND_COMPOUND)
        self.rate("ZERO", "0.0000", compound_style=TaxRate.COMPOUND_COMPOUND)
        self.rate("EXEMPT", "0.0000", compound_style=TaxRate.COMPOUND_COMPOUND)
        with self.assertRaisesRegex(TaxConfigurationError, "zero-rated/exempt treatments"):
            compute_line_tax(self.product, Decimal("100.00"))

    def test_explicit_assignment_overrides_default_and_selects_only_assigned_rate(self):
        self.rate("DEFAULT", "0.0500")
        assigned = self.rate("PRODUCT17", "0.1700", applies_to_all=False)
        ProductTaxAssignment.objects.create(tenant=self.tenant, product=self.product, tax_rate=assigned)
        self.assertEqual([rate.code for rate in _active_rates_for(self.product)], ["PRODUCT17"])
        self.assertEqual(compute_line_tax(self.product, Decimal("100.00"))[0]["amount"], "17.00")

    def test_product_scope_overrides_category_scope_and_category_is_tenant_scoped(self):
        category_rate = self.rate("CAT10", "0.1000", applies_to_all=False, category=self.category)
        self.assertEqual([r.code for r in _active_rates_for(self.product)], [category_rate.code])
        product_rate = self.rate("PROD7", "0.0700", applies_to_all=False, product=self.product)
        self.assertEqual([r.code for r in _active_rates_for(self.product)], [product_rate.code])

        other_category = Category.objects.create(tenant=self.other_tenant, name="Other category")
        other_product = Product.objects.create(
            tenant=self.other_tenant, category=other_category, name="Other", sku="OTHER",
            sales_price=Decimal("100"), cost_price=Decimal("1"), stock_quantity=Decimal("1"),
        )
        # Even a corrupted cross-tenant scope reference must not make a rate
        # owned by this tenant leak into another tenant's product calculation.
        TaxRate.objects.create(
            tenant=self.tenant, name="Foreign scope", code="FOREIGN-SCOPE", rate=Decimal("0.2000"),
            is_active=True, applies_to_all=False, category=other_category,
        )
        self.assertEqual(list(_active_rates_for(other_product)), [])

    def test_cross_tenant_assignment_is_rejected(self):
        foreign_rate = TaxRate.objects.create(
            tenant=self.other_tenant, name="Foreign", code="FOREIGN", rate=Decimal("0.2000"),
            is_active=True,
        )
        ProductTaxAssignment.objects.create(tenant=self.other_tenant, product=self.product, tax_rate=foreign_rate)
        with self.assertRaisesRegex(TaxConfigurationError, "crosses tenant boundaries"):
            _active_rates_for(self.product)

    def test_specific_exemption_removes_tax_and_scope_is_honoured(self):
        gst = self.rate("GST17", "0.1700")
        customer = Customer.objects.create(tenant=self.tenant, name="Exempt")
        TaxExemption.objects.create(
            tenant=self.tenant, scope=TaxExemption.SCOPE_CUSTOMER, customer=customer,
            tax_rate=gst, is_active=True,
        )
        self.assertEqual(compute_line_tax(self.product, Decimal("100.00"), customer), [])
        # A row carrying a customer FK but a different scope is not treated as a customer exemption.
        TaxExemption.objects.filter(customer=customer).update(scope=TaxExemption.SCOPE_PRODUCT)
        self.assertEqual(compute_line_tax(self.product, Decimal("100.00"), customer)[0]["amount"], "17.00")

    def test_inclusive_tax_is_reported_but_not_added_to_payable_price(self):
        self.rate("GST17", "0.1700", mode=TaxRate.MODE_INCLUSIVE)
        row = compute_line_tax(self.product, Decimal("24999.00"))[0]
        self.assertEqual(row["amount"], "3632.33")
        self.assertEqual(row["mode"], TaxRate.MODE_INCLUSIVE)

    def test_explicit_product_assignments_support_flat_additive_rates(self):
        first = self.rate("GST10", "0.1000", applies_to_all=False)
        second = self.rate("LEVY5", "0.0500", applies_to_all=False)
        ProductTaxAssignment.objects.create(tenant=self.tenant, product=self.product, tax_rate=first)
        ProductTaxAssignment.objects.create(tenant=self.tenant, product=self.product, tax_rate=second)
        rows = compute_line_tax(self.product, Decimal("100.00"))
        self.assertEqual([row["amount"] for row in rows], ["10.00", "5.00"])
        self.assertEqual(sum((Decimal(row["amount"]) for row in rows), Decimal("0")), Decimal("15.00"))

        # The combined additive amount is rounded once; breakdown cents are
        # apportioned deterministically so they still reconcile to line tax.
        penny = compute_line_tax(self.product, Decimal("0.04"))
        self.assertEqual(sum((Decimal(row["amount"]) for row in penny), Decimal("0")), Decimal("0.01"))

    def test_explicit_compound_rates_cascade(self):
        self.rate("GST10", "0.1000", compound_style=TaxRate.COMPOUND_COMPOUND)
        self.rate("LEVY5", "0.0500", compound_style=TaxRate.COMPOUND_COMPOUND)
        rows = compute_line_tax(self.product, Decimal("100.00"))
        self.assertEqual([row["amount"] for row in rows], ["10.00", "5.50"])

    def test_multiple_default_rates_are_rejected_not_arbitrarily_selected(self):
        self.rate("GST17", "0.1700")
        self.rate("GST7", "0.0700")
        with self.assertRaisesRegex(TaxConfigurationError, "mutually exclusive"):
            _active_rates_for(self.product)

    def test_fraction_input_contract_rejects_percent_points(self):
        request = SimpleNamespace(tenant=self.tenant)
        serializer = TaxRateSerializer(
            data={"name": "GST", "code": "GST", "rate": "17", "mode": "exclusive", "compound_style": "flat"},
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("rate", serializer.errors)
        self.assertIn("less than or equal to 1", str(serializer.errors["rate"]))

    def test_discount_allocation_rounding_remainder_is_exact(self):
        shares = allocate_order_discount([Decimal("10.25"), Decimal("20.25")], Decimal("1.00"))
        self.assertEqual(shares, [Decimal("0.34"), Decimal("0.66")])
        self.assertEqual(sum(shares), Decimal("1.00"))

    def test_paid_order_tax_and_breakdown_are_immutable_to_recomputation(self):
        rate = self.rate("GST17", "0.1700")
        order = Order.objects.create(
            tenant=self.tenant, payment_method="cash", subtotal=Decimal("100.00"),
            tax=Decimal("55.00"), total=Decimal("155.00"), status="paid",
        )
        breakdown = TaxBreakdown.objects.create(
            tenant=self.tenant, order=order, tax_rate=rate, tax_rate_code=rate.code,
            rate=rate.rate, taxable_amount=Decimal("100.00"), tax_amount=Decimal("55.00"),
            mode=rate.mode,
        )
        with self.assertRaisesRegex(ValueError, "only be recomputed for a draft"):
            compute_order_tax(order)
        order.refresh_from_db()
        self.assertEqual((order.tax, order.total), (Decimal("55.00"), Decimal("155.00")))
        self.assertTrue(TaxBreakdown.objects.filter(pk=breakdown.pk).exists())

    def test_rate_repair_command_is_report_only_by_default_and_explicit_when_applied(self):
        rate = self.rate("GST17", "17.0000")
        output = StringIO()
        call_command("review_tax_rate_repair", self.tenant.id, "--rate", f"{rate.id}=0.1700", stdout=output)
        rate.refresh_from_db()
        self.assertEqual(rate.rate, Decimal("17.0000"))
        self.assertIn("DRY RUN / REPORT ONLY", output.getvalue())
        self.assertIn("before=17.0000 after=0.1700", output.getvalue())

        call_command("review_tax_rate_repair", self.tenant.id, "--rate", f"{rate.id}=0.1700", "--apply", stdout=StringIO())
        rate.refresh_from_db()
        self.assertEqual(rate.rate, Decimal("0.1700"))

    def test_rate_repair_command_refuses_ambiguous_active_defaults_without_changes(self):
        first = self.rate("GST17", "17.0000")
        second = self.rate("GST7", "7.0000")
        with self.assertRaisesRegex(CommandError, "resolve duplicate or ambiguous"):
            call_command(
                "review_tax_rate_repair", self.tenant.id,
                "--rate", f"{first.id}=0.1700", "--rate", f"{second.id}=0.0700", "--apply",
                stdout=StringIO(),
            )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.rate, second.rate), (Decimal("17.0000"), Decimal("7.0000")))
