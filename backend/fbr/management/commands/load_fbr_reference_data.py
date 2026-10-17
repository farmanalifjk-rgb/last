"""Load the FBR published code lists (annexures of the technical specification).

The JSON fixtures under ``fbr/data`` were extracted from the annexures of the
PRAL Digital Invoicing technical specification v1.12.  The command is idempotent, so
it can be re-run whenever FBR republishes a list.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from fbr.models import FBRHSCode, FBRProvince, FBRSROSchedule, FBRTransactionType, FBRUnitOfMeasure

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATASETS = [
    ("provinces.json", FBRProvince),
    ("transaction_types.json", FBRTransactionType),
    ("sro_schedules.json", FBRSROSchedule),
    ("uom_codes.json", FBRUnitOfMeasure),
    ("hs_codes.json", FBRHSCode),
]


class Command(BaseCommand):
    help = "Load or refresh the FBR reference code lists shipped with the fbr app."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset",
            choices=[name.removesuffix(".json") for name, _ in DATASETS],
            help="Load a single dataset instead of all of them.",
        )

    def handle(self, *args, **options):
        selected = options.get("dataset")
        for filename, model in DATASETS:
            if selected and filename.removesuffix(".json") != selected:
                continue
            created, updated = self._load(DATA_DIR / filename, model)
            self.stdout.write(
                self.style.SUCCESS(f"{model.__name__}: {created} created, {updated} updated")
            )

    @transaction.atomic
    def _load(self, path, model):
        records = json.loads(path.read_text())
        existing = {obj.code: obj for obj in model.objects.all()}
        to_create, to_update = [], []
        for record in records:
            code = record["code"].strip()
            description = (record.get("description") or "").strip()[:512]
            obj = existing.get(code)
            if obj is None:
                to_create.append(model(code=code, description=description))
            elif obj.description != description or not obj.is_active:
                obj.description = description
                # for models with is_active
                if hasattr(obj, "is_active"):
                    obj.is_active = True
                to_update.append(obj)
        model.objects.bulk_create(to_create, batch_size=1000)
        # Determine fields to update
        if to_update:
            update_fields = ["description"]
            if hasattr(to_update[0], "is_active"):
                update_fields.append("is_active")
            model.objects.bulk_update(to_update, update_fields, batch_size=1000)
        return len(to_create), len(to_update)
