from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from accounting.models import (
    AccountingEvent,
    AccountingEventStatus,
    AccountingEventType,
    AccountingPeriod,
    ChartOfAccount,
    Expense,
    ExpenseCategory,
    JournalEntry,
    PostingRule,
)
from accounting.services import emit_accounting_event, post_expense_to_journal
from rbac.models import Permission, Role, UserRole
from saas.models import Tenant, TenantMembership


User = get_user_model()


def make_tenant(*, suffix):
    owner = User.objects.create_user(username=f"phase9-owner-{suffix}", password="StrongPass123!")
    tenant = Tenant.objects.create(name=f"Phase 9 Tenant {suffix}", slug=f"phase9-tenant-{suffix}", owner=owner, status="active")
    TenantMembership.objects.create(tenant=tenant, user=owner, role="owner", is_active_in_tenant=True)
    cash = ChartOfAccount.objects.create(tenant=tenant, code="1000", name="Cash", type="asset")
    revenue = ChartOfAccount.objects.create(tenant=tenant, code="4000", name="Revenue", type="revenue")
    expense = ChartOfAccount.objects.create(tenant=tenant, code="6000", name="Expense", type="expense")
    return tenant, owner, cash, revenue, expense


class Phase9PostingEngineTests(TestCase):
    def setUp(self):
        self.tenant, self.owner, self.cash, self.revenue, self.expense_account = make_tenant(suffix="primary")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def create_rule(self, *, event_type=AccountingEventType.POS_SALE_NET, debit=None, credit=None, **kwargs):
        return PostingRule.objects.create(
            tenant=self.tenant,
            event_type=event_type,
            name=kwargs.pop("name", f"{event_type} rule"),
            debit_account=debit or self.cash,
            credit_account=credit or self.revenue,
            created_by=self.owner,
            updated_by=self.owner,
            **kwargs,
        )

    def test_configured_event_posts_one_balanced_traceable_journal_and_duplicate_identity_is_idempotent(self):
        rule = self.create_rule()
        first = emit_accounting_event(
            tenant=self.tenant,
            source_domain="pos",
            event_type=AccountingEventType.POS_SALE_NET,
            source_id="sale-1",
            source_reference="ORD-0001",
            event_date=date(2026, 8, 16),
            amount="125.25",
            payload={"order_id": 1},
            user=self.owner,
        )
        replay = emit_accounting_event(
            tenant=self.tenant,
            source_domain="pos",
            event_type=AccountingEventType.POS_SALE_NET,
            source_id="sale-1",
            source_reference="ORD-0001",
            event_date=date(2026, 8, 16),
            amount="125.25",
            payload={"order_id": 1},
            user=self.owner,
        )
        self.assertEqual(first.status, AccountingEventStatus.POSTED)
        self.assertEqual(replay.id, first.id)
        self.assertEqual(PostingRule.objects.get(pk=rule.id), first.rule)
        self.assertEqual(AccountingEvent.objects.filter(tenant=self.tenant, source_domain="pos", event_type=AccountingEventType.POS_SALE_NET, source_id="sale-1").count(), 1)
        self.assertEqual(JournalEntry.objects.filter(tenant=self.tenant, accounting_event=first).count(), 1)
        first.journal_entry.refresh_from_db()
        self.assertTrue(first.journal_entry.is_balanced)
        self.assertTrue(first.journal_entry.is_auto_posted)

    def test_missing_mapping_creates_visible_configuration_required_event_without_a_journal(self):
        event = emit_accounting_event(
            tenant=self.tenant,
            source_domain="purchasing",
            event_type=AccountingEventType.GOODS_RECEIPT,
            source_id="receipt-1",
            source_reference="GR-1",
            event_date=date(2026, 8, 16),
            amount="40.00",
            user=self.owner,
        )
        self.assertEqual(event.status, AccountingEventStatus.CONFIGURATION_REQUIRED)
        self.assertIn("No active accounting posting rule", event.exception_reason)
        self.assertIsNone(event.journal_entry_id)

    def test_closed_period_records_observable_failed_event_without_silent_journal_effect(self):
        AccountingPeriod.objects.create(
            tenant=self.tenant,
            code="2026-08",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            status=AccountingPeriod.STATUS_CLOSED,
        )
        self.create_rule()
        event = emit_accounting_event(
            tenant=self.tenant,
            source_domain="pos",
            event_type=AccountingEventType.POS_SALE_NET,
            source_id="closed-sale",
            source_reference="ORD-CLOSED",
            event_date=date(2026, 8, 16),
            amount="10.00",
            user=self.owner,
        )
        self.assertEqual(event.status, AccountingEventStatus.FAILED)
        self.assertIn("closed", event.exception_reason.lower())
        self.assertIsNone(event.journal_entry_id)

    def test_expense_manual_posting_uses_the_canonical_event_engine_once(self):
        category = ExpenseCategory.objects.create(tenant=self.tenant, name="Travel")
        expense = Expense.objects.create(
            tenant=self.tenant,
            category=category,
            amount=Decimal("34.50"),
            description="Taxi",
            date=date(2026, 8, 16),
            paid_by=self.owner,
            status=Expense.STATUS_APPROVED,
        )
        posted = post_expense_to_journal(
            tenant=self.tenant,
            expense_id=expense.id,
            expense_account_id=self.expense_account.id,
            payment_account_id=self.cash.id,
            reference="EXP-P9-001",
            user=self.owner,
        )
        replay = post_expense_to_journal(
            tenant=self.tenant,
            expense_id=expense.id,
            expense_account_id=self.expense_account.id,
            payment_account_id=self.cash.id,
            reference="ignored-on-replay",
            user=self.owner,
        )
        event = AccountingEvent.objects.get(tenant=self.tenant, event_type=AccountingEventType.EXPENSE_MANUAL, source_id=str(expense.id))
        self.assertEqual(posted.journal_entry_id, replay.journal_entry_id)
        self.assertEqual(event.status, AccountingEventStatus.POSTED)
        self.assertEqual(event.journal_entry_id, posted.journal_entry_id)
        self.assertFalse(event.journal_entry.is_auto_posted)

    def test_event_and_rule_api_are_tenant_isolated_and_view_only_user_cannot_manage_or_post(self):
        rule = self.create_rule()
        event = emit_accounting_event(
            tenant=self.tenant,
            source_domain="pos",
            event_type=AccountingEventType.POS_SALE_NET,
            source_id="secured-sale",
            event_date=date(2026, 8, 16),
            amount="12.00",
            user=self.owner,
        )
        other_tenant, _other_owner, _cash, _revenue, _expense = make_tenant(suffix="other")
        other_rule = PostingRule.objects.create(tenant=other_tenant, event_type=AccountingEventType.POS_SALE_NET, name="Other", debit_account=_cash, credit_account=_revenue)
        viewer = User.objects.create_user(username="phase9-viewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant, user=viewer, role="staff", is_active_in_tenant=True)
        role = Role.objects.create(key="phase9-accounting-viewer", label="Phase 9 Accounting Viewer")
        role.permissions.add(Permission.objects.get(module__key="accounting", action="view"))
        UserRole.objects.create(user=viewer, role=role)
        viewer_client = APIClient()
        viewer_client.force_authenticate(viewer)
        self.assertEqual(viewer_client.get("/api/accounting/events/").status_code, 200)
        self.assertEqual(viewer_client.get("/api/accounting/posting-rules/").status_code, 200)
        self.assertEqual(viewer_client.get(f"/api/accounting/events/{event.id}/").status_code, 200)
        self.assertEqual(viewer_client.get(f"/api/accounting/events/{event.id}/retry/").status_code, 405)
        self.assertEqual(viewer_client.post(f"/api/accounting/events/{event.id}/retry/", {}, format="json").status_code, 403)
        self.assertEqual(viewer_client.post("/api/accounting/posting-rules/", {"event_type": "pos_sale_tax"}, format="json").status_code, 403)
        self.assertEqual(self.client.get(f"/api/accounting/posting-rules/{other_rule.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/accounting/events/{event.id}/").status_code, 200)
        self.assertEqual(rule.tenant_id, self.tenant.id)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row-level locking semantics.")
class Phase9PostingEngineConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner, self.cash, self.revenue, _expense = make_tenant(suffix="concurrency")
        PostingRule.objects.create(
            tenant=self.tenant,
            event_type=AccountingEventType.POS_SALE_NET,
            name="Concurrent sale rule",
            debit_account=self.cash,
            credit_account=self.revenue,
            created_by=self.owner,
            updated_by=self.owner,
        )

    def _emit_in_separate_connection(self):
        close_old_connections()
        try:
            event = emit_accounting_event(
                tenant=self.tenant,
                source_domain="pos",
                event_type=AccountingEventType.POS_SALE_NET,
                source_id="concurrent-sale",
                source_reference="ORD-CONCURRENT",
                event_date=date(2026, 8, 16),
                amount="40.00",
                user=self.owner,
            )
            return event.status
        finally:
            close_old_connections()

    def test_concurrent_source_delivery_creates_one_event_and_one_posted_journal(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _index: self._emit_in_separate_connection(), range(2)))
        self.assertEqual(statuses, [AccountingEventStatus.POSTED, AccountingEventStatus.POSTED])
        events = AccountingEvent.objects.filter(
            tenant=self.tenant,
            source_domain="pos",
            event_type=AccountingEventType.POS_SALE_NET,
            source_id="concurrent-sale",
        )
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.status, AccountingEventStatus.POSTED)
        self.assertEqual(JournalEntry.objects.filter(tenant=self.tenant, accounting_event=event).count(), 1)
