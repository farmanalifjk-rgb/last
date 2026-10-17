"""Process pending accounting events for all active tenants.

Usage::

    python manage.py post_accounting_events          # process up to 50 events per tenant
    python manage.py post_accounting_events --limit 200
"""

from django.core.management.base import BaseCommand

from accounting.services import process_pending_events
from saas.models import Tenant


class Command(BaseCommand):
    help = "Attempt to post pending accounting events for every active tenant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum events to process per tenant (default: 50).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        tenants = Tenant.objects.filter(is_active=True)
        total_posted, total_failed, total_skipped = 0, 0, 0

        for tenant in tenants:
            result = process_pending_events(tenant=tenant, limit=limit)
            total_posted += result["posted"]
            total_failed += result["failed"]
            total_skipped += result["skipped"]
            if result["posted"] or result["failed"]:
                self.stdout.write(
                    f"  Tenant {tenant.pk} ({tenant.name}): "
                    f"posted={result['posted']} failed={result['failed']} skipped={result['skipped']}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Total: posted={total_posted} failed={total_failed} skipped={total_skipped}"
            )
        )
