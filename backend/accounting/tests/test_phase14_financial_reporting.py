from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from accounting.models import (
    AccountType,
    AccountingEvent,
    AccountingEventStatus,
    AccountingEventType,
    ChartOfAccount,
    FinancialAccountMapping,
    FinancialStatementRole,
    JournalEntry,
    JournalEntryLine,
    PostingRule,
)
from accounting.services import emit_accounting_event
from rbac.models import Permission, Role, UserRole
from saas.models import Tenant, TenantMembership


User = get_user_model()


def financial_tenant(*, suffix):
    owner = User.objects.create_user(username=f"phase14-owner-{suffix}", password="StrongPass123!")
    tenant = Tenant.objects.create(name=f"Phase 14 Tenant {suffix}", slug=f"phase14-tenant-{suffix}", owner=owner, status="active")
    TenantMembership.objects.create(tenant=tenant, user=owner, role="owner", is_active_in_tenant=True)
    cash = ChartOfAccount.objects.create(tenant=tenant, code="1000", name="Cash", type=AccountType.ASSET)
    retained = ChartOfAccount.objects.create(tenant=tenant, code="3000", name="Retained earnings", type=AccountType.EQUITY)
    revenue = ChartOfAccount.objects.create(tenant=tenant, code="4000", name="Revenue", type=AccountType.REVENUE)
    cogs = ChartOfAccount.objects.create(tenant=tenant, code="5000", name="COGS", type=AccountType.EXPENSE)
    operating = ChartOfAccount.objects.create(tenant=tenant, code="6000", name="Operating expense", type=AccountType.EXPENSE)
    return tenant, owner, cash, retained, revenue, cogs, operating


class Phase14FinancialReportingTests(TestCase):
    def setUp(self):
        self.tenant, self.owner, self.cash, self.retained, self.revenue, self.cogs, self.operating = financial_tenant(suffix="primary")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        PostingRule.objects.create(
            tenant=self.tenant, event_type=AccountingEventType.POS_SALE_NET, name="Sale revenue",
            debit_account=self.cash, credit_account=self.revenue, created_by=self.owner, updated_by=self.owner,
        )
        self.sale = emit_accounting_event(
            tenant=self.tenant, source_domain="pos", event_type=AccountingEventType.POS_SALE_NET,
            source_id="p14-sale-1", source_reference="P14-ORD-1", event_date=date(2026, 8, 20),
            amount="100.00", user=self.owner,
        )

    def map_role(self, account, role):
        return FinancialAccountMapping.objects.create(tenant=self.tenant, account=account, role=role, created_by=self.owner, updated_by=self.owner)

    def test_trial_balance_and_general_ledger_read_only_posted_tenant_lines_with_traceability(self):
        second = emit_accounting_event(
            tenant=self.tenant, source_domain="pos", event_type=AccountingEventType.POS_SALE_NET,
            source_id="p14-sale-2", source_reference="P14-ORD-2", event_date=date(2026, 8, 21),
            amount="50.00", user=self.owner,
        )
        response = self.client.get("/api/reports/financial-trial-balance/?start=2026-08-01&end=2026-08-31")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_balanced"])
        self.assertEqual(response.data["total_debit"], "150.00")
        self.assertEqual(response.data["total_credit"], "150.00")
        ledger = self.client.get(f"/api/reports/financial-general-ledger/{self.cash.id}/?start=2026-08-01&end=2026-08-31&page=2&page_size=1")
        self.assertEqual(ledger.status_code, 200)
        self.assertEqual(ledger.data["results"][0]["source_event_id"], second.id)
        self.assertEqual(ledger.data["results"][0]["source_reference"], "P14-ORD-2")
        self.assertEqual(ledger.data["results"][0]["balance"], "150.00")

    def test_statement_endpoints_return_controlled_policy_and_mapping_gates_without_heuristics(self):
        pnl = self.client.get("/api/reports/financial-profit-loss/")
        self.assertEqual(pnl.status_code, 409)
        self.assertEqual(pnl.data["status"], "accounting_mapping_required")
        balance_sheet = self.client.get("/api/reports/financial-balance-sheet/")
        self.assertEqual(balance_sheet.status_code, 409)
        self.assertEqual(balance_sheet.data["status"], "accounting_policy_required")
        cash_flow = self.client.get("/api/reports/financial-cash-flow/")
        self.assertEqual(cash_flow.status_code, 409)
        self.assertEqual(cash_flow.data["status"], "accounting_policy_required")

    def test_mapped_profit_loss_and_balance_sheet_derive_only_from_posted_ledger(self):
        self.map_role(self.cogs, FinancialStatementRole.COGS)
        self.map_role(self.operating, FinancialStatementRole.OPERATING_EXPENSE)
        self.map_role(self.retained, FinancialStatementRole.RETAINED_EARNINGS)
        pnl = self.client.get("/api/reports/financial-profit-loss/")
        self.assertEqual(pnl.status_code, 200)
        self.assertEqual(pnl.data["revenue"], "100.00")
        self.assertEqual(pnl.data["cogs"], "0.00")
        # Existing open-period revenue has not been closed into equity. The API must surface this instead of claiming balance.
        balance_sheet = self.client.get("/api/reports/financial-balance-sheet/")
        self.assertEqual(balance_sheet.status_code, 409)
        self.assertFalse(balance_sheet.data["is_balanced"])

    def test_mapping_api_enforces_tenant_account_type_and_manage_permission(self):
        viewer = User.objects.create_user(username="phase14-viewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant, user=viewer, role="staff", is_active_in_tenant=True)
        role = Role.objects.create(key="phase14-accounting-viewer", label="Phase 14 Accounting Viewer")
        role.permissions.add(Permission.objects.get(module__key="accounting", action="view"))
        UserRole.objects.create(user=viewer, role=role)
        viewer_client = APIClient()
        viewer_client.force_authenticate(viewer)
        self.assertEqual(viewer_client.get("/api/accounting/financial-account-mappings/").status_code, 200)
        self.assertEqual(viewer_client.post("/api/accounting/financial-account-mappings/", {"account": self.cogs.id, "role": FinancialStatementRole.COGS}, format="json").status_code, 403)
        wrong = self.client.post("/api/accounting/financial-account-mappings/", {"account": self.cash.id, "role": FinancialStatementRole.COGS}, format="json")
        self.assertEqual(wrong.status_code, 400)
        other, _owner, other_cash, _retained, _revenue, _cogs, _operating = financial_tenant(suffix="other")
        cross = self.client.post("/api/accounting/financial-account-mappings/", {"account": other_cash.id, "role": FinancialStatementRole.CASH_BANK}, format="json")
        self.assertEqual(cross.status_code, 400)
        self.assertEqual(other.id, other_cash.tenant_id)

    def test_dashboard_exceptions_and_financial_export_are_tenant_scoped(self):
        failed = AccountingEvent.objects.create(
            tenant=self.tenant, source_domain="purchasing", event_type=AccountingEventType.GOODS_RECEIPT,
            source_id="p14-unmapped", event_date=date(2026, 8, 20), amount=Decimal("4.00"),
            status=AccountingEventStatus.CONFIGURATION_REQUIRED, exception_reason="No active accounting posting rule is configured.",
        )
        dashboard = self.client.get("/api/reports/financial-dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["exception_count"], 1)
        exceptions = self.client.get("/api/reports/financial-exceptions/")
        self.assertEqual(exceptions.status_code, 200)
        self.assertEqual(exceptions.data["results"][0]["id"], failed.id)
        export = self.client.get("/api/reports/export/financial-trial-balance/?start=2026-08-01&end=2026-08-31")
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export["Content-Type"], "text/csv")


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row-level locking semantics.")
class Phase14FinancialMappingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner, _cash, _retained, _revenue, self.cogs, _operating = financial_tenant(suffix="concurrency")

    def _create_mapping(self):
        close_old_connections()
        try:
            try:
                mapping = FinancialAccountMapping.objects.create(
                    tenant=self.tenant, account=self.cogs, role=FinancialStatementRole.COGS,
                )
                return ("created", mapping.id)
            except IntegrityError:
                return ("conflict", None)
        finally:
            close_old_connections()

    def test_concurrent_role_configuration_creates_one_mapping_for_one_account(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: self._create_mapping(), range(2)))
        self.assertEqual(sum(1 for status, _id in outcomes if status == "created"), 1)
        self.assertEqual(FinancialAccountMapping.objects.filter(tenant=self.tenant, account=self.cogs).count(), 1)
