import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, F

from accounting.models import AccountingEvent, AccountingEventStatus, JournalEntry, JournalEntryLine
from saas.models import Subscription, Tenant, TenantMembership


class Command(BaseCommand):
    help = "Run read-only Phase 17 integrity checks. No records are created, changed, or deleted."

    def add_arguments(self, parser):
        parser.add_argument("--fail-on-findings", action="store_true")
        parser.add_argument("--max-details", type=int, default=20)

    @staticmethod
    def _details(queryset, max_details):
        return list(queryset[:max_details])

    def handle(self, *args, **options):
        max_details = max(1, options["max_details"])
        owner_membership_tenant_ids = TenantMembership.objects.filter(
            role=TenantMembership.ROLE_OWNER,
            user_id=F("tenant__owner_id"),
        ).values_list("tenant_id", flat=True)

        active_context_conflicts = TenantMembership.objects.filter(
            is_active_in_tenant=True
        ).values("user_id").annotate(count=Count("id")).filter(count__gt=1)
        duplicate_accounting_events = AccountingEvent.objects.values(
            "tenant_id", "source_domain", "event_type", "source_id"
        ).annotate(count=Count("id")).filter(count__gt=1)
        unbalanced_journal_ids = [
            entry.id
            for entry in JournalEntry.objects.filter(status=JournalEntry.STATUS_POSTED).iterator()
            if not entry.is_balanced
        ]

        findings = {
            "tenant_missing_owner_membership": self._details(
                Tenant.objects.exclude(id__in=owner_membership_tenant_ids).values_list("id", flat=True),
                max_details,
            ),
            "multiple_active_tenant_contexts": self._details(
                active_context_conflicts.values_list("user_id", flat=True), max_details
            ),
            "active_subscription_for_inactive_tenant": self._details(
                Subscription.objects.filter(
                    status=Subscription.STATUS_ACTIVE,
                    tenant__is_active=False,
                ).values_list("id", flat=True),
                max_details,
            ),
            "unbalanced_posted_journals": unbalanced_journal_ids[:max_details],
            "journal_line_entry_tenant_mismatch": self._details(
                JournalEntryLine.objects.exclude(tenant_id=F("entry__tenant_id")).values_list("id", flat=True),
                max_details,
            ),
            "journal_line_account_tenant_mismatch": self._details(
                JournalEntryLine.objects.exclude(tenant_id=F("account__tenant_id")).values_list("id", flat=True),
                max_details,
            ),
            "posted_event_without_journal": self._details(
                AccountingEvent.objects.filter(
                    status=AccountingEventStatus.POSTED,
                    journal_entry__isnull=True,
                ).values_list("id", flat=True),
                max_details,
            ),
            "duplicate_accounting_event_identities": self._details(
                duplicate_accounting_events.values_list("tenant_id", "source_domain", "event_type", "source_id"),
                max_details,
            ),
        }
        finding_count = sum(len(values) for values in findings.values())
        result = {
            "command": "phase17_integrity_audit",
            "read_only": True,
            "finding_count": finding_count,
            "truncated_to": max_details,
            "findings": findings,
        }
        self.stdout.write(json.dumps(result, sort_keys=True, default=str))
        if options["fail_on_findings"] and finding_count:
            raise CommandError("Phase 17 integrity audit found data-integrity exceptions.")
