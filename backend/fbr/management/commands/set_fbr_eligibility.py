"""Record platform-verified FBR fiscalization eligibility for a tenant.

Fiscal-scheme selection (PRAL DI API vs Tier-1 IMS Software Fiscal Component)
is a taxpayer-registration fact, so only the platform operator may grant a
track. This command is the operator entry point (audit H8):

    python manage.py set_fbr_eligibility tenant-slug --modes di,ims \
        --reference "eFBR Tier-1 registration verified 2026-09-05"

Omitting ``--modes`` defaults to the PRAL DI track only.
"""
from django.core.management.base import BaseCommand, CommandError

from fbr.constants import INTEGRATION_MODE_DI, INTEGRATION_MODE_IMS
from fbr.models import FBRTenantEligibility
from saas.models import Tenant

VALID_MODES = {INTEGRATION_MODE_DI, INTEGRATION_MODE_IMS}


class Command(BaseCommand):
    help = "Set the FBR fiscalization tracks a tenant is eligible to configure."

    def add_arguments(self, parser):
        parser.add_argument("tenant_slug")
        parser.add_argument(
            "--modes", default=INTEGRATION_MODE_DI,
            help="Comma-separated tracks to grant: di, ims (default: di)",
        )
        parser.add_argument("--reference", default="", help="Verification reference (eFBR record / ticket)")
        parser.add_argument("--verified-by", default="", help="Username of the verifying operator")
        parser.add_argument("--deactivate", action="store_true", help="Deactivate the eligibility record")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            raise CommandError(f"No tenant with slug '{options['tenant_slug']}'.")
        modes = [m.strip().lower() for m in options["modes"].split(",") if m.strip()]
        invalid = [m for m in modes if m not in VALID_MODES]
        if invalid:
            raise CommandError(f"Unknown tracks: {', '.join(invalid)} (valid: di, ims).")
        row, _created = FBRTenantEligibility.objects.get_or_create(tenant=tenant)
        row.allowed_modes = ",".join(modes)
        row.reference = options["reference"]
        row.is_active = not options["deactivate"]
        if options["verified_by"]:
            from django.contrib.auth import get_user_model

            user = get_user_model().objects.filter(username=options["verified_by"]).first()
            if user is None:
                raise CommandError(f"No user named '{options['verified_by']}'.")
            row.verified_by = user
        row.full_clean()
        row.save()
        state = "deactivated" if not row.is_active else "active"
        self.stdout.write(
            self.style.SUCCESS(
                f"Eligibility for '{tenant.slug}' is now {state}: {row.allowed_modes} "
                f"(reference: {row.reference or '-'})"
            )
        )
