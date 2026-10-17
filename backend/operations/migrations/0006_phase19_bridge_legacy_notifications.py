"""Copy recipient-addressable legacy notifications into the canonical operations inbox.

Rows without a target user remain preserved in ``notifications.Notification``
for operator reconciliation.  The migration never deletes source data and uses
an event key derived from the legacy primary key to make the copy idempotent.
"""

from django.db import migrations


def bridge_recipient_notifications(apps, schema_editor):
    LegacyNotification = apps.get_model("notifications", "Notification")
    InAppNotification = apps.get_model("operations", "InAppNotification")
    type_map = {
        "info": "info",
        "warning": "warning",
        "critical": "error",
    }

    for legacy in LegacyNotification.objects.exclude(target_user__isnull=True).iterator():
        event_key = f"legacy-notification:{legacy.pk}"
        InAppNotification.objects.get_or_create(
            tenant_id=legacy.tenant_id,
            user_id=legacy.target_user_id,
            event_key=event_key,
            defaults={
                "type": type_map.get(legacy.severity, "warning"),
                "title": legacy.title,
                "message": legacy.body,
                "link": legacy.link,
                "is_read": legacy.is_read,
            },
        )


def noop_reverse(apps, schema_editor):
    # Source rows and migrated records are retained for traceability.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0004_phase19_alertrule_tenant_uniqueness"),
        ("operations", "0005_alter_approvalrequest_reference_id_and_more"),
    ]

    operations = [
        migrations.RunPython(bridge_recipient_notifications, noop_reverse),
    ]
