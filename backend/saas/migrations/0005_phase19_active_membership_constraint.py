from django.db import migrations, models
from django.db.models import Q


def normalize_active_memberships(apps, schema_editor):
    """Keep the latest active membership per user before adding the constraint.

    This is deliberately non-destructive: memberships remain intact and only
    duplicate active selection flags are cleared.  Operators can switch the
    user's active tenant again through the canonical SaaS API after migration.
    """
    TenantMembership = apps.get_model("saas", "TenantMembership")
    user_ids = (
        TenantMembership.objects.filter(is_active_in_tenant=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    for user_id in user_ids.iterator():
        memberships = TenantMembership.objects.filter(
            user_id=user_id,
            is_active_in_tenant=True,
        ).order_by("-joined_at", "-id")
        keeper = memberships.first()
        if keeper is not None:
            memberships.exclude(pk=keeper.pk).update(is_active_in_tenant=False)


def noop_reverse(apps, schema_editor):
    # Restoring ambiguous active flags would be unsafe and provides no data value.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("saas", "0004_manual_billing"),
    ]

    operations = [
        migrations.RunPython(normalize_active_memberships, noop_reverse),
        migrations.AddConstraint(
            model_name="tenantmembership",
            constraint=models.UniqueConstraint(
                condition=Q(is_active_in_tenant=True),
                fields=("user",),
                name="saas_one_active_tenant_per_user",
            ),
        ),
    ]
