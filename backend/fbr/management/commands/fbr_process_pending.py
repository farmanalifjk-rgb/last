"""Finish FBR fiscalization that checkout could not complete (cashier audit E1).

Run on a schedule, e.g. every minute:

    python manage.py fbr_process_pending
    python manage.py fbr_process_pending --tenant shop-slug --dry-run

What it does and never does is described in ``fbr/pending.py``. In short:
stale ``pending`` -> ``unknown`` (never resent), never-dispatched POS invoices
-> submitted once, ``failed`` -> retried with backoff. ``unknown`` and
``rejected`` submissions are left for a person. Output carries ids and
statuses only, never payloads or credentials.
"""
from django.core.management.base import BaseCommand, CommandError

from fbr.pending import UNSUBMITTED_MAX_AGE_HOURS_DEFAULT, process_pending
from saas.models import Tenant


class Command(BaseCommand):
    help = "Submit or retry FBR fiscalization left unfinished by checkout (never resends unknown outcomes)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="", help="Only this tenant (slug).")
        parser.add_argument("--limit", type=int, default=50, help="Maximum rows per step (default 50).")
        parser.add_argument("--max-attempts", type=int, default=None,
                            help="Total attempts after which a failed submission is left for a person "
                                 "(default FBR_AUTO_RETRY_MAX_ATTEMPTS, 5).")
        parser.add_argument("--stale-minutes", type=int, default=None,
                            help="Minutes without a response before pending becomes unknown "
                                 "(default FBR_PENDING_STALE_MINUTES, 10; minimum 2).")
        parser.add_argument("--max-age-hours", type=int, default=UNSUBMITTED_MAX_AGE_HOURS_DEFAULT,
                            help="Only submit never-dispatched invoices issued within this many hours (default 72).")
        parser.add_argument("--dry-run", action="store_true", help="Report what would be done; change nothing.")

    def handle(self, *args, **options):
        tenant = None
        if options["tenant"]:
            tenant = Tenant.objects.filter(slug=options["tenant"]).first()
            if tenant is None:
                raise CommandError(f"No tenant with slug '{options['tenant']}'.")
        if options["limit"] < 1:
            raise CommandError("--limit must be at least 1.")
        try:
            report = process_pending(
                tenant=tenant,
                limit=options["limit"],
                max_attempts=options["max_attempts"],
                stale_minutes=options["stale_minutes"],
                max_age_hours=options["max_age_hours"],
                dry_run=options["dry_run"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from None

        prefix = "[dry run] " if report.dry_run else ""
        for submission_id in report.marked_unknown:
            self.stdout.write(f"{prefix}submission {submission_id}: no response recorded -> unknown (reconcile it)")
        for invoice_id, status in report.submitted:
            self.stdout.write(f"{prefix}invoice {invoice_id}: submitted -> {status}")
        for submission_id, status in report.retried:
            self.stdout.write(f"{prefix}submission {submission_id}: retried -> {status}")
        for kind, row_id, reason in report.skipped:
            self.stdout.write(f"{prefix}{kind} {row_id}: skipped ({reason})")
        for kind, row_id, message in report.errors:
            self.stderr.write(f"{prefix}{kind} {row_id}: {message}")
        self.stdout.write(
            f"{prefix}unknown={len(report.marked_unknown)} submitted={len(report.submitted)} "
            f"retried={len(report.retried)} skipped={len(report.skipped)} errors={len(report.errors)}"
        )
