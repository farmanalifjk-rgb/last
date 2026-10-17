"""Management command to audit and safely migrate/repair TaxRate records.

Contract:
- 17% is stored and processed as 0.17
- 7% is stored and processed as 0.07
- 0% is stored and processed as 0.00
- Any rate > 1.0 (e.g. 17.00) is a legacy percentage-point rate and should be divided by 100
- Rates <= 1.0 are already fractional and must NOT be divided again

Usage:
    # Audit only (dry-run, default):
    python manage.py audit_tax_rates

    # Audit for a specific tenant:
    python manage.py audit_tax_rates --tenant=<slug_or_id>

    # Apply fixes (requires explicit --fix flag):
    python manage.py audit_tax_rates --fix
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from tax.models import TaxRate
from saas.models import Tenant


class Command(BaseCommand):
    help = "Audit and repair TaxRate records to conform to the single fractional contract (e.g., 0.17 for 17%)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            type=str,
            help="Filter audit/repair to a specific tenant slug or ID",
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            default=False,
            help="Apply the corrections to the database. Without this flag, command runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        tenant_filter = options.get("tenant")
        apply_fix = options.get("fix")

        qs = TaxRate.objects.select_related("tenant").all().order_by("tenant_id", "id")
        if tenant_filter:
            if tenant_filter.isdigit():
                qs = qs.filter(tenant_id=int(tenant_filter))
            else:
                qs = qs.filter(tenant__slug=tenant_filter)

        total_checked = 0
        anomalies = []

        self.stdout.write(self.style.MIGRATE_HEADING("=== Tax Rate Audit Report ==="))
        self.stdout.write(f"Mode: {'APPLY FIXES' if apply_fix else 'DRY RUN (Report Only)'}\n")

        for tax_rate in qs:
            total_checked += 1
            rate = tax_rate.rate

            # Check anomalies
            issue = None
            suggested_rate = rate

            if rate is None:
                issue = "NULL rate"
                suggested_rate = Decimal("0.0000")
            elif rate < Decimal("0"):
                issue = f"Negative rate: {rate}"
                suggested_rate = Decimal("0.0000")
            elif rate > Decimal("1.0"):
                # Clearly a percentage point representation (e.g., 17.00 -> 0.1700)
                suggested_rate = (rate / Decimal("100")).quantize(Decimal("0.0001"))
                issue = f"Legacy percentage-point format: {rate} -> should be {suggested_rate}"
            elif rate > Decimal("0") and rate < Decimal("0.001"):
                # Possible double-division anomaly (e.g. 0.0017 instead of 0.17)
                suggested_rate = (rate * Decimal("100")).quantize(Decimal("0.0001"))
                issue = f"Suspected double-divided rate: {rate} -> review (candidate: {suggested_rate})"

            if issue:
                anomalies.append({
                    "id": tax_rate.id,
                    "tenant": tax_rate.tenant.name if tax_rate.tenant else "None",
                    "code": tax_rate.code,
                    "name": tax_rate.name,
                    "current_rate": rate,
                    "suggested_rate": suggested_rate,
                    "issue": issue,
                    "obj": tax_rate,
                })

        self.stdout.write(f"Total TaxRate records scanned: {total_checked}")
        self.stdout.write(f"Anomalous records found: {len(anomalies)}\n")

        if anomalies:
            self.stdout.write(self.style.WARNING("Anomalous Records:"))
            for item in anomalies:
                self.stdout.write(
                    f"  [ID {item['id']}] Tenant: {item['tenant']} | Code: {item['code']} | Name: {item['name']}\n"
                    f"    Current: {item['current_rate']} | Issue: {item['issue']} | Suggested: {item['suggested_rate']}\n"
                )

            if apply_fix:
                with transaction.atomic():
                    fixed_count = 0
                    for item in anomalies:
                        # Only auto-fix percentage-point (> 1.0) and negative rates
                        if item["current_rate"] > Decimal("1.0") or item["current_rate"] < Decimal("0"):
                            tax_obj = item["obj"]
                            old_val = tax_obj.rate
                            tax_obj.rate = item["suggested_rate"]
                            tax_obj.save(update_fields=["rate"])
                            fixed_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Fixed TaxRate {item['id']} ({item['code']}): {old_val} -> {tax_obj.rate}"
                                )
                            )
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Skipped TaxRate {item['id']} ({item['code']}): Requires manual verification."
                                )
                            )
                    self.stdout.write(self.style.SUCCESS(f"\nSuccessfully updated {fixed_count} TaxRate records."))
            else:
                self.stdout.write(
                    self.style.NOTICE("To apply corrections, rerun command with --fix flag.")
                )
        else:
            self.stdout.write(self.style.SUCCESS("All TaxRate records conform to the fractional contract! No anomalies found."))
