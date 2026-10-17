from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from django.test import TestCase

from accounting.models import ChartOfAccount, JournalEntry, JournalEntryLine
from payments.models import PaymentSettlement, TenderedPayment
from pos.models import CashSession, Category, Customer, Order, OrderItem, Product
from rbac.models import Permission, Role, UserRole
from saas.models import Tenant, TenantMembership


User = get_user_model()


def report_tenant(*, suffix):
    owner = User.objects.create_user(username=f"phase9-report-owner-{suffix}", password="StrongPass123!")
    tenant = Tenant.objects.create(name=f"Phase 9 Reporting {suffix}", slug=f"phase9-report-{suffix}", owner=owner, status="active")
    TenantMembership.objects.create(tenant=tenant, user=owner, role="owner", is_active_in_tenant=True)
    return tenant, owner


def create_paid_order(*, tenant, owner, total="30.00"):
    category = Category.objects.create(tenant=tenant, name=f"Category {tenant.id}")
    product = Product.objects.create(tenant=tenant, category=category, name=f"Product {tenant.id}", sku=f"SKU-{tenant.id}", sales_price=total, cost_price="10.00", stock_quantity="4.000")
    customer = Customer.objects.create(tenant=tenant, name=f"Customer {tenant.id}", customer_code=f"C-{tenant.id}")
    session = CashSession.objects.create(tenant=tenant, opened_by=owner, employee_name="Owner", opening_balance="0.00", is_open=True)
    order = Order.objects.create(tenant=tenant, customer=customer, session=session, payment_method="cash", subtotal=total, discount="0.00", tax="0.00", total=total, status="paid")
    OrderItem.objects.create(tenant=tenant, order=order, product=product, quantity="1.00", unit_price=total, subtotal=total)
    settlement = PaymentSettlement.objects.create(tenant=tenant, order=order, total_amount=total, idempotency_key=f"report-{tenant.id}", settled_by=owner)
    TenderedPayment.objects.create(tenant=tenant, settlement=settlement, order=order, tender_type="cash", amount=total, created_by=owner)
    return order, product


class Phase9ReportingTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = report_tenant(suffix="primary")
        self.order, self.product = create_paid_order(tenant=self.tenant, owner=self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_sales_and_operational_reports_return_real_tenant_scoped_data_with_stable_pagination(self):
        summary = self.client.get("/api/reports/sales-summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data["gross_sales"], "30.00")
        products = self.client.get("/api/reports/top-products/?page=1&page_size=10")
        self.assertEqual(products.status_code, 200, products.data)
        self.assertEqual(products.data["count"], 1)
        self.assertEqual(products.data["results"][0]["product_id"], self.product.id)
        payments = self.client.get("/api/reports/sales-by-payment/")
        self.assertEqual(payments.status_code, 200, payments.data)
        self.assertEqual(payments.data[0]["method"], "cash")
        valuation = self.client.get("/api/reports/inventory-valuation/?page=1&page_size=10")
        self.assertEqual(valuation.status_code, 200, valuation.data)
        self.assertEqual(valuation.data["results"][0]["product_id"], self.product.id)

    def test_report_date_filter_validation_and_cross_tenant_data_isolation(self):
        other_tenant, other_owner = report_tenant(suffix="other")
        create_paid_order(tenant=other_tenant, owner=other_owner, total="99.00")
        response = self.client.get("/api/reports/sales-summary/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["gross_sales"], "30.00")
        self.assertNotIn("99.00", str(response.data))
        invalid = self.client.get("/api/reports/sales-summary/?start=not-a-date")
        self.assertEqual(invalid.status_code, 400, invalid.data)

    def test_financial_trial_balance_only_reads_active_tenant_posted_ledger(self):
        cash = ChartOfAccount.objects.create(tenant=self.tenant, code="1000", name="Cash", type="asset")
        revenue = ChartOfAccount.objects.create(tenant=self.tenant, code="4000", name="Revenue", type="revenue")
        entry = JournalEntry.objects.create(tenant=self.tenant, reference="REP-TB-1", date=timezone.localdate(), status="posted")
        JournalEntryLine.objects.create(tenant=self.tenant, entry=entry, account=cash, debit="20.00", credit="0.00")
        JournalEntryLine.objects.create(tenant=self.tenant, entry=entry, account=revenue, debit="0.00", credit="20.00")
        other_tenant, other_owner = report_tenant(suffix="financial-other")
        other_cash = ChartOfAccount.objects.create(tenant=other_tenant, code="1000", name="Other cash", type="asset")
        other_revenue = ChartOfAccount.objects.create(tenant=other_tenant, code="4000", name="Other revenue", type="revenue")
        other_entry = JournalEntry.objects.create(tenant=other_tenant, reference="REP-TB-OTHER", date=timezone.localdate(), status="posted", created_by=other_owner)
        JournalEntryLine.objects.create(tenant=other_tenant, entry=other_entry, account=other_cash, debit="99.00", credit="0.00")
        JournalEntryLine.objects.create(tenant=other_tenant, entry=other_entry, account=other_revenue, debit="0.00", credit="99.00")
        response = self.client.get("/api/reports/financial-trial-balance/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("20.00", str(response.data))
        self.assertNotIn("99.00", str(response.data))

    def test_report_viewer_can_read_but_export_requires_separate_reports_export_permission(self):
        viewer = User.objects.create_user(username="phase9-report-viewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant, user=viewer, role="staff", is_active_in_tenant=True)
        role = Role.objects.create(key="phase9-report-viewer", label="Phase 9 Report Viewer")
        role.permissions.add(Permission.objects.get(module__key="reports", action="view"))
        UserRole.objects.create(user=viewer, role=role)
        viewer_client = APIClient()
        viewer_client.force_authenticate(viewer)
        self.assertEqual(viewer_client.get("/api/reports/sales-summary/").status_code, 200)
        self.assertEqual(viewer_client.get("/api/reports/export/sales-by-day/").status_code, 403)
        role.permissions.add(Permission.objects.get(module__key="reports", action="export"))
        exported = viewer_client.get("/api/reports/export/sales-by-day/")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported["Content-Type"], "text/csv")
