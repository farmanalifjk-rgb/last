"""


Management command to backfill `tenant` (and optionally `branch`) FKs onto
existing models that didn't have them when first created.

Usage:
    python manage.py backfill_tenant --models=Order,Product,Customer --branch
"""
from django.core.management.base import BaseCommand
from django.apps import apps


class Command(BaseCommand):
    help = "Backfill tenant (and optionally branch) FKs onto existing records."

    def add_arguments(self, parser):
        parser.add_argument("--models", required=True, help="Comma-separated model labels (app.Model)")
        parser.add_argument("--tenant-id", type=int, required=True, help="Default tenant to assign")
        parser.add_argument("--branch-id", type=int, default=None, help="Optional default branch")
        parser.add_argument("--branch", action="store_true", help="Also set branch FK if field exists")

    def handle(self, *args, **opts):
        labels = opts["models"].split(",")
        tenant_id = opts["tenant_id"]
        branch_id = opts["branch_id"]
        set_branch = opts["branch"]
        for label in labels:
            label = label.strip()
            try:
                model = apps.get_model(label)
            except LookupError:
                self.stdout.write(self.style.WARNING(f"Unknown model {label}, skipping."))
                continue
            qs = model.objects.filter(tenant__isnull=True)
            count = qs.count()
            if count == 0:
                self.stdout.write(f"{label}: nothing to backfill.")
                continue
            updates = {"tenant_id": tenant_id}
            if set_branch and hasattr(model, "branch"):
                updates["branch_id"] = branch_id
            qs.update(**updates)
            self.stdout.write(self.style.SUCCESS(f"{label}: backfilled {count} records → tenant {tenant_id}."))