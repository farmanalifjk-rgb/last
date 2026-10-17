"""Report or explicitly normalize selected tenant tax rates without touching orders.

Dry-run example::

    python manage.py review_tax_rate_repair 235 --rate 12=0.1700 --rate 13=0.0700

Apply only after reviewing the report and fixing tax-scope ambiguity::

    python manage.py review_tax_rate_repair 235 --rate 12=0.1700 --rate 13=0.0700 --apply

Mappings are explicit rate-primary-key=fraction pairs. The command never infers
that every value above one should be divided by 100 and never edits breakdowns,
orders, payments, stock, or receipts.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from saas.models import Tenant
from tax.models import ProductTaxAssignment, TaxRate


class Command(BaseCommand):
    help = "Dry-run or explicitly repair selected tax rates for one tenant; historical orders are never changed."

    def add_arguments(self, parser):
        parser.add_argument("tenant_id", type=int, help="Explicit tenant primary key (required; no global mode).")
        parser.add_argument(
            "--rate", action="append", default=[], metavar="ID=FRACTION",
            help="Explicit target fraction for a tenant tax-rate ID; may be repeated.",
        )
        parser.add_argument("--apply", action="store_true", help="Apply reviewed mappings; default is report-only.")

    @staticmethod
    def _parse_mappings(values):
        mappings = {}
        for raw in values:
            try:
                raw_id, raw_value = raw.split("=", 1)
                rate_id = int(raw_id)
                value = Decimal(raw_value)
            except (ValueError, InvalidOperation):
                raise CommandError(f"Invalid --rate {raw!r}; expected ID=FRACTION, for example 12=0.1700.") from None
            if rate_id <= 0 or not value.is_finite() or value < 0 or value > 1 or value.as_tuple().exponent < -4:
                raise CommandError(f"Invalid target for rate {rate_id}: use a finite fraction from 0 to 1 with at most four decimal places.")
            if rate_id in mappings:
                raise CommandError(f"Tax rate {rate_id} was specified more than once.")
            mappings[rate_id] = value
        return mappings

    @staticmethod
    def _scope(rate):
        if rate.product_id is not None:
            return ("product", rate.product_id)
        if rate.category_id is not None:
            return ("category", rate.category_id)
        if rate.applies_to_all:
            return ("default", None)
        return ("inactive-scope", None)

    def _configuration_warnings(self, tenant, replacements):
        rates = list(TaxRate.objects.filter(tenant=tenant, is_active=True).order_by("priority", "id"))
        values = {rate.id: replacements.get(rate.id, rate.rate) for rate in rates}
        groups = defaultdict(list)
        for rate in rates:
            groups[self._scope(rate)].append(rate)
        warnings = []
        for scope, rows in groups.items():
            if len(rows) > 1 and (
                any(values[row.id] == 0 for row in rows)
                or not all(row.compound_style == TaxRate.COMPOUND_COMPOUND for row in rows)
                or len({row.mode for row in rows}) > 1
                or rows[0].mode == TaxRate.MODE_INCLUSIVE
            ):
                labels = ", ".join(f"{row.code}={values[row.id]}" for row in rows)
                warnings.append(f"Ambiguous active {scope[0]} scope {scope[1] or '(default)'}: {labels}")
        assignments = defaultdict(list)
        for assignment in ProductTaxAssignment.objects.filter(tenant=tenant, is_active=True).select_related("tax_rate"):
            if assignment.tax_rate.tenant_id == tenant.id and assignment.tax_rate.is_active:
                assignments[assignment.product_id].append(assignment.tax_rate)
        for product_id, rows in assignments.items():
            selected = list({row.id: row for row in rows}.values())
            styles = {row.compound_style for row in selected}
            if len(selected) > 1 and (
                any(values.get(row.id, row.rate) == 0 for row in selected)
                or len(styles) > 1
                or len({row.mode for row in selected}) > 1
                or selected[0].mode == TaxRate.MODE_INCLUSIVE
            ):
                labels = ", ".join(f"{row.code}={values.get(row.id, row.rate)}" for row in selected)
                warnings.append(f"Ambiguous active product {product_id} assignments: {labels}")
        duplicate_groups = defaultdict(list)
        for rate in rates:
            duplicate_groups[(self._scope(rate), values[rate.id], rate.mode)].append(rate.code)
        for (scope, value, mode), codes in duplicate_groups.items():
            if len(codes) > 1:
                warnings.append(f"Duplicate treatment at {scope}: {', '.join(sorted(codes))} ({value}, {mode})")
        return warnings

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(pk=options["tenant_id"]).first()
        if tenant is None:
            raise CommandError(f"No tenant with ID {options['tenant_id']}.")
        mappings = self._parse_mappings(options["rate"])
        rows = list(TaxRate.objects.filter(tenant=tenant).order_by("id"))
        by_id = {row.id: row for row in rows}
        missing = set(mappings) - set(by_id)
        if missing:
            raise CommandError(f"Tax rate IDs do not belong to tenant {tenant.id}: {', '.join(map(str, sorted(missing)))}")
        if options["apply"] and not mappings:
            raise CommandError("--apply requires one or more explicit --rate ID=FRACTION mappings.")

        self.stdout.write(f"Tenant {tenant.id} ({tenant.name}) — {'APPLY' if options['apply'] else 'DRY RUN / REPORT ONLY'}")
        for rate in rows:
            target = mappings.get(rate.id, rate.rate)
            marker = " (selected)" if rate.id in mappings else ""
            self.stdout.write(
                f"TaxRate {rate.id} {rate.code}: before={rate.rate} after={target} "
                f"active={rate.is_active} applies_to_all={rate.applies_to_all} "
                f"product={rate.product_id or '-'} category={rate.category_id or '-'}{marker}"
            )
        warnings = self._configuration_warnings(tenant, mappings)
        for warning in warnings:
            self.stdout.write(self.style.WARNING(warning))
        if not mappings:
            self.stdout.write("No target mappings supplied; no values will change.")
            return
        if options["apply"] and warnings:
            raise CommandError("No tax-rate changes applied: resolve duplicate or ambiguous active treatments, then rerun.")
        if options["apply"]:
            with transaction.atomic():
                locked = {row.id: row for row in TaxRate.objects.select_for_update().filter(tenant=tenant, id__in=mappings)}
                for rate_id, value in mappings.items():
                    rate = locked[rate_id]
                    rate.rate = value
                    rate.save(update_fields=["rate"])
            self.stdout.write(self.style.SUCCESS("Selected tax-rate values updated. Historical orders and TaxBreakdown rows were not modified."))
        else:
            self.stdout.write("Report only: no database values changed. Re-run with --apply only after reviewing scopes and warnings.")
