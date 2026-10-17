from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from accounting.models import AccountingPeriod, ChartOfAccount, Expense, ExpenseCategory, JournalEntry, JournalEntryLine
from accounting.services import post_journal_entry
from audit.models import AuditEvent
from rbac.models import Permission, Role, UserRole
from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant


User = get_user_model()


def create_tenant_owner(*, suffix):
    owner = User.objects.create_user(username=f"phase8-owner-{suffix}", password="StrongPass123!")
    tenant = Tenant.objects.create(name=f"Phase 8 Tenant {suffix}", slug=f"phase8-tenant-{suffix}", owner=owner, status="active")
    TenantMembership.objects.create(tenant=tenant, user=owner, role="owner", is_active_in_tenant=True)
    return tenant, owner


def create_accounts(tenant):
    cash = ChartOfAccount.objects.create(tenant=tenant, code="1000", name="Cash", type="asset")
    revenue = ChartOfAccount.objects.create(tenant=tenant, code="4000", name="Sales", type="revenue")
    expense = ChartOfAccount.objects.create(tenant=tenant, code="6000", name="Operating expense", type="expense")
    return cash, revenue, expense


class Phase8AccountingTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = create_tenant_owner(suffix="primary")
        self.cash, self.revenue, self.expense_account = create_accounts(self.tenant)
        set_current_tenant(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def journal_payload(self, *, reference="JE-P8-001", entry_date="2026-08-16", amount="125.00"):
        return {
            "reference": reference,
            "date": entry_date,
            "description": "Phase 8 regression journal",
            "lines": [
                {"account": self.cash.id, "debit": amount, "credit": "0.00", "description": "Cash received"},
                {"account": self.revenue.id, "debit": "0.00", "credit": amount, "description": "Sales revenue"},
            ],
        }

    def create_draft(self, **kwargs):
        response = self.client.post("/api/accounting/journal/", self.journal_payload(**kwargs), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_balanced_journal_posts_with_decimal_safe_lines_and_audit_trail(self):
        created = self.create_draft()
        entry = JournalEntry.objects.get(tenant=self.tenant, pk=created.data["id"])
        self.assertEqual(entry.status, JournalEntry.STATUS_DRAFT)
        self.assertTrue(entry.is_balanced)
        self.assertEqual(entry.lines.count(), 2)
        self.assertTrue(all(line.tenant_id == self.tenant.id for line in entry.lines.all()))
        posted = self.client.post(f"/api/accounting/journal/{entry.id}/post/", {}, format="json")
        self.assertEqual(posted.status_code, 200, posted.data)
        entry.refresh_from_db()
        self.assertEqual(entry.status, JournalEntry.STATUS_POSTED)
        self.assertEqual(entry.posted_by, self.owner)
        self.assertIsNotNone(entry.posted_at)
        self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant, entity_type="journalentry", entity_id=str(entry.id), action="post").count(), 1)
        trial_balance = self.client.get("/api/accounting/trial-balance/")
        self.assertEqual(trial_balance.status_code, 200, trial_balance.data)
        self.assertEqual(trial_balance.data["total_debit"], trial_balance.data["total_credit"])
        self.assertTrue(all(isinstance(row["debit"], str) for row in trial_balance.data["rows"]))

    def test_unbalanced_journal_is_rejected_without_persisting_any_header_or_line(self):
        payload = self.journal_payload(reference="JE-P8-UNBALANCED")
        payload["lines"][1]["credit"] = "124.99"
        rejected = self.client.post("/api/accounting/journal/", payload, format="json")
        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.assertEqual(JournalEntry.objects.filter(tenant=self.tenant, reference="JE-P8-UNBALANCED").count(), 0)
        self.assertEqual(JournalEntryLine.objects.filter(tenant=self.tenant).count(), 0)

    def test_posted_journal_is_immutable_and_reversal_is_the_only_correction_path(self):
        entry_id = self.create_draft(reference="JE-P8-IMMUTABLE").data["id"]
        self.assertEqual(self.client.post(f"/api/accounting/journal/{entry_id}/post/", {}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/accounting/journal/{entry_id}/", {"description": "altered"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/accounting/journal/{entry_id}/replace-lines/", {"lines": self.journal_payload()["lines"]}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/accounting/journal/{entry_id}/").status_code, 400)
        reversed_response = self.client.post(f"/api/accounting/journal/{entry_id}/reverse/", {"date": "2026-08-16"}, format="json")
        self.assertEqual(reversed_response.status_code, 201, reversed_response.data)
        reversal = JournalEntry.objects.get(tenant=self.tenant, pk=reversed_response.data["id"])
        self.assertEqual(reversal.status, JournalEntry.STATUS_POSTED)
        self.assertEqual(reversal.reversal_of_id, entry_id)
        self.assertTrue(reversal.is_balanced)
        self.assertEqual(self.client.post(f"/api/accounting/journal/{entry_id}/reverse/", {}, format="json").status_code, 400)

    def test_accounting_objects_and_reports_are_tenant_isolated_including_idor_routes(self):
        other_tenant, other_owner = create_tenant_owner(suffix="other")
        other_cash, other_revenue, _ = create_accounts(other_tenant)
        other_entry = JournalEntry.objects.create(tenant=other_tenant, reference="OTHER-JE", date=date(2026, 8, 16), description="Other tenant", created_by=other_owner)
        JournalEntryLine.objects.create(tenant=other_tenant, entry=other_entry, account=other_cash, debit=Decimal("99.00"), credit=Decimal("0.00"))
        JournalEntryLine.objects.create(tenant=other_tenant, entry=other_entry, account=other_revenue, debit=Decimal("0.00"), credit=Decimal("99.00"))
        other_entry.status = JournalEntry.STATUS_POSTED
        other_entry.save(update_fields=["status"])
        self.assertEqual(self.client.get(f"/api/accounting/accounts/{other_cash.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/accounting/journal/{other_entry.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/accounting/ledger/{other_cash.id}/").status_code, 404)
        trial_balance = self.client.get("/api/accounting/trial-balance/")
        self.assertEqual(trial_balance.status_code, 200, trial_balance.data)
        self.assertNotIn("OTHER-JE", str(trial_balance.data))
        self.assertNotIn("99.00", str(trial_balance.data))

    def test_view_only_accounting_role_can_read_but_cannot_create_post_update_or_manage(self):
        viewer = User.objects.create_user(username="phase8-accounting-viewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant, user=viewer, role="staff", is_active_in_tenant=True)
        role = Role.objects.create(key="phase8-accounting-viewer", label="Phase 8 Accounting Viewer")
        role.permissions.add(Permission.objects.get(module__key="accounting", action="view"))
        UserRole.objects.create(user=viewer, role=role)
        viewer_client = APIClient()
        viewer_client.force_authenticate(viewer)
        self.assertEqual(viewer_client.get("/api/accounting/accounts/").status_code, 200)
        self.assertEqual(viewer_client.get("/api/accounting/trial-balance/").status_code, 200)
        self.assertEqual(viewer_client.post("/api/accounting/journal/", self.journal_payload(reference="JE-P8-FORBIDDEN"), format="json").status_code, 403)
        entry_id = self.create_draft(reference="JE-P8-VIEWER-POST").data["id"]
        self.assertEqual(viewer_client.post(f"/api/accounting/journal/{entry_id}/post/", {}, format="json").status_code, 403)
        self.assertEqual(viewer_client.patch(f"/api/accounting/accounts/{self.cash.id}/", {"name": "Forbidden"}, format="json").status_code, 403)
        self.assertEqual(viewer_client.delete(f"/api/accounting/accounts/{self.cash.id}/").status_code, 403)

    def test_active_tenant_owner_permission_identity_matches_the_backend_owner_bypass(self):
        response = self.client.get("/api/rbac/me/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("*.*", response.data["permissions"])

    def test_expense_lifecycle_is_tenant_safe_and_transition_only_from_pending(self):
        category = ExpenseCategory.objects.create(tenant=self.tenant, name="Office supplies")
        created = self.client.post("/api/accounting/expenses/", {"category": category.id, "amount": "12.50", "description": "Paper", "date": "2026-08-16"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        expense = Expense.objects.get(tenant=self.tenant, pk=created.data["id"])
        self.assertEqual(expense.status, Expense.STATUS_PENDING)
        approved = self.client.post(f"/api/accounting/expenses/{expense.id}/approve/", {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        expense.refresh_from_db()
        self.assertEqual(expense.status, Expense.STATUS_APPROVED)
        self.assertEqual(self.client.patch(f"/api/accounting/expenses/{expense.id}/", {"description": "Mutated"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/accounting/expenses/{expense.id}/reject/", {}, format="json").status_code, 400)
        other_tenant, _ = create_tenant_owner(suffix="expense-other")
        other_category = ExpenseCategory.objects.create(tenant=other_tenant, name="Other category")
        rejected = self.client.post("/api/accounting/expenses/", {"category": other_category.id, "amount": "1.00", "description": "Tenant escape", "date": "2026-08-16"}, format="json")
        self.assertEqual(rejected.status_code, 400, rejected.data)

    def test_approved_expense_can_be_manually_posted_once_to_a_balanced_journal(self):
        category = ExpenseCategory.objects.create(tenant=self.tenant, name="Travel")
        expense = Expense.objects.create(tenant=self.tenant, category=category, amount="25.00", description="Taxi", date=date(2026, 8, 16), paid_by=self.owner, status=Expense.STATUS_APPROVED)
        posted = self.client.post(
            f"/api/accounting/expenses/{expense.id}/post-to-journal/",
            {"expense_account": self.expense_account.id, "payment_account": self.cash.id, "reference": "EXP-P8-TAXI"},
            format="json",
        )
        self.assertEqual(posted.status_code, 200, posted.data)
        expense.refresh_from_db()
        self.assertIsNotNone(expense.journal_entry_id)
        self.assertEqual(expense.journal_entry.status, JournalEntry.STATUS_POSTED)
        self.assertTrue(expense.journal_entry.is_balanced)
        replay = self.client.post(
            f"/api/accounting/expenses/{expense.id}/post-to-journal/",
            {"expense_account": self.expense_account.id, "payment_account": self.cash.id, "reference": "ignored"},
            format="json",
        )
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(JournalEntry.objects.filter(tenant=self.tenant, reference="EXP-P8-TAXI").count(), 1)

    def test_period_close_blocks_drafts_and_new_postings_then_preserves_closed_period_immutability(self):
        period = self.client.post("/api/accounting/periods/", {"code": "2026-08", "start_date": "2026-08-01", "end_date": "2026-08-31"}, format="json")
        self.assertEqual(period.status_code, 201, period.data)
        period_id = period.data["id"]
        draft_id = self.create_draft(reference="JE-P8-PERIOD-DRAFT").data["id"]
        self.assertEqual(self.client.post(f"/api/accounting/periods/{period_id}/close/", {}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/accounting/journal/{draft_id}/").status_code, 204)
        closed = self.client.post(f"/api/accounting/periods/{period_id}/close/", {}, format="json")
        self.assertEqual(closed.status_code, 200, closed.data)
        self.assertEqual(closed.data["status"], AccountingPeriod.STATUS_CLOSED)
        closed_period = AccountingPeriod.objects.get(tenant=self.tenant, pk=period_id)
        self.assertEqual(self.client.patch(f"/api/accounting/periods/{period_id}/", {"code": "mutated"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/accounting/periods/{period_id}/").status_code, 400)
        blocked = self.create_draft(reference="JE-P8-PERIOD-BLOCKED")
        self.assertEqual(self.client.post(f"/api/accounting/journal/{blocked.data['id']}/post/", {}, format="json").status_code, 400)
        closed_period.refresh_from_db()
        self.assertEqual(closed_period.status, AccountingPeriod.STATUS_CLOSED)

    def test_unique_codes_and_references_are_tenant_local(self):
        other_tenant, other_owner = create_tenant_owner(suffix="same-code")
        duplicate_elsewhere, other_revenue, _ = create_accounts(other_tenant)
        self.assertEqual(duplicate_elsewhere.code, self.cash.code)
        self.create_draft(reference="JE-P8-LOCAL-REF")
        other_entry = JournalEntry.objects.create(tenant=other_tenant, reference="JE-P8-LOCAL-REF", date=date(2026, 8, 16), created_by=other_owner)
        JournalEntryLine.objects.create(tenant=other_tenant, entry=other_entry, account=duplicate_elsewhere, debit="1.00", credit="0.00")
        JournalEntryLine.objects.create(tenant=other_tenant, entry=other_entry, account=other_revenue, debit="0.00", credit="1.00")
        self.assertEqual(other_entry.reference, "JE-P8-LOCAL-REF")


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row-level locking semantics.")
class PostgresAccountingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = create_tenant_owner(suffix="concurrency")
        cash, revenue, _ = create_accounts(self.tenant)
        self.entry = JournalEntry.objects.create(tenant=self.tenant, reference="JE-P8-CONCURRENT", date=date(2026, 8, 16), created_by=self.owner)
        JournalEntryLine.objects.create(tenant=self.tenant, entry=self.entry, account=cash, debit="20.00", credit="0.00")
        JournalEntryLine.objects.create(tenant=self.tenant, entry=self.entry, account=revenue, debit="0.00", credit="20.00")

    def _post_in_separate_connection(self):
        close_old_connections()
        try:
            result = post_journal_entry(tenant=self.tenant, entry_id=self.entry.id, user=self.owner)
            return result.status
        finally:
            close_old_connections()

    def test_concurrent_post_attempts_produce_one_posted_entry_and_one_post_audit_event(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: self._post_in_separate_connection(), range(2)))
        self.entry.refresh_from_db()
        self.assertEqual(statuses, [JournalEntry.STATUS_POSTED, JournalEntry.STATUS_POSTED])
        self.assertEqual(self.entry.status, JournalEntry.STATUS_POSTED)
        self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant, entity_type="journalentry", entity_id=str(self.entry.id), action="post").count(), 1)
