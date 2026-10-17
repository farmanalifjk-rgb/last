import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounting.models import ChartOfAccount, JournalEntry, JournalEntryLine
from saas.models import Tenant, TenantMembership


User = get_user_model()


class Phase17IntegrityAuditTests(TestCase):
    def _tenant_with_owner(self, suffix):
        user = User.objects.create_user(username=f"phase17-{suffix}", password="StrongPass123!")
        tenant = Tenant.objects.create(name=f"Phase 17 {suffix}", slug=f"phase17-{suffix}", owner=user)
        TenantMembership.objects.create(
            tenant=tenant,
            user=user,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=False,
        )
        return tenant

    def test_audit_reports_clean_canonical_fixture(self):
        self._tenant_with_owner("clean")
        output = StringIO()
        call_command("phase17_integrity_audit", "--fail-on-findings", stdout=output)
        report = json.loads(output.getvalue())
        self.assertTrue(report["read_only"])
        self.assertEqual(report["finding_count"], 0)

    def test_audit_detects_unbalanced_posted_journal_without_mutating_it(self):
        tenant = self._tenant_with_owner("unbalanced")
        account = ChartOfAccount.objects.create(tenant=tenant, code="1000", name="Cash", type="asset")
        entry = JournalEntry.objects.create(tenant=tenant, reference="P17-UNBAL", date="2026-08-21", status=JournalEntry.STATUS_POSTED)
        JournalEntryLine.objects.create(tenant=tenant, entry=entry, account=account, debit="10.00")
        output = StringIO()
        call_command("phase17_integrity_audit", stdout=output)
        report = json.loads(output.getvalue())
        self.assertIn(entry.id, report["findings"]["unbalanced_posted_journals"])
        self.assertEqual(JournalEntryLine.objects.get(entry=entry).debit, 10)
