"""Bridge dormant tenancy records into the canonical SaaS ownership graph.

The old ``tenancy`` tables remain intact.  This one-way compatibility migration
creates canonical tenant and membership records only where a safe owner can be
identified.  Branches and settings are intentionally not copied because their
canonical target and foreign-key consumers require an operator-reviewed mapping.
"""

from django.conf import settings
from django.db import migrations
from django.utils.text import slugify


def _unique_slug(Tenant, raw_value, legacy_id):
    base = (slugify(raw_value) or f"legacy-tenant-{legacy_id}")[:70]
    candidate = base
    counter = 2
    while Tenant.objects.filter(slug=candidate).exists():
        suffix = f"-{counter}"
        candidate = f"{base[:80 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def bridge_legacy_tenancy(apps, schema_editor):
    LegacyTenant = apps.get_model("tenancy", "Tenant")
    LegacyMembership = apps.get_model("tenancy", "UserTenantMembership")
    Tenant = apps.get_model("saas", "Tenant")
    TenantMembership = apps.get_model("saas", "TenantMembership")
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app_label, user_model_name)

    fallback_owner = User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
    role_map = {
        "tenant_admin": "admin",
        "branch_manager": "manager",
        "staff": "staff",
    }

    for legacy_tenant in LegacyTenant.objects.all().iterator():
        legacy_memberships = list(
            LegacyMembership.objects.filter(tenant_id=legacy_tenant.pk)
            .select_related("user")
            .order_by("created_at", "id")
        )
        owner_membership = next(
            (membership for membership in legacy_memberships if membership.role == "tenant_admin" and membership.user.is_active),
            None,
        )
        owner = owner_membership.user if owner_membership else fallback_owner
        if owner is None:
            # Keeping the legacy record untouched is safer than creating a
            # canonical tenant with an invented or inactive owner.
            continue

        requested_slug = slugify(legacy_tenant.code or legacy_tenant.name)[:80]
        tenant = Tenant.objects.filter(slug=requested_slug).first() if requested_slug else None
        if tenant is None:
            tenant = Tenant.objects.create(
                name=legacy_tenant.name,
                slug=_unique_slug(Tenant, legacy_tenant.code or legacy_tenant.name, legacy_tenant.pk),
                owner=owner,
                status="active" if legacy_tenant.is_active else "suspended",
                is_active=legacy_tenant.is_active,
                suspended_reason="Migrated from deprecated tenancy.Tenant" if not legacy_tenant.is_active else "",
            )

        TenantMembership.objects.get_or_create(
            tenant=tenant,
            user=owner,
            defaults={"role": "owner", "is_active_in_tenant": False},
        )
        for legacy_membership in legacy_memberships:
            role = role_map.get(legacy_membership.role, "staff")
            canonical_membership, _ = TenantMembership.objects.get_or_create(
                tenant=tenant,
                user=legacy_membership.user,
                defaults={"role": role, "is_active_in_tenant": False},
            )
            if legacy_membership.is_active and not TenantMembership.objects.filter(
                user=legacy_membership.user,
                is_active_in_tenant=True,
            ).exists():
                canonical_membership.is_active_in_tenant = True
                canonical_membership.save(update_fields=["is_active_in_tenant"])


def noop_reverse(apps, schema_editor):
    # The bridge intentionally does not delete canonical data on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_initial"),
        ("saas", "0005_phase19_active_membership_constraint"),
    ]

    operations = [
        migrations.RunPython(bridge_legacy_tenancy, noop_reverse),
    ]
