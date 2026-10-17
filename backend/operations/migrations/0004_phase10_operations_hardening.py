from django.db import migrations, models
from django.db.models import Q


def assert_unique_approval_requests(apps, schema_editor):
    ApprovalRequest = apps.get_model("operations", "ApprovalRequest")
    duplicates = (
        ApprovalRequest.objects.values("tenant_id", "module", "action", "reference_id")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError("Phase 10 requires one approval request per tenant-scoped source action; resolve duplicate historical rows before migration.")


class Migration(migrations.Migration):
    dependencies = [("operations", "0003_alter_approvalrequest_tenant_and_more")]

    operations = [
        migrations.RunPython(assert_unique_approval_requests, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="approvalrule", name="unique_approval_rule_module_action"),
        migrations.AddConstraint(
            model_name="approvalrule",
            constraint=models.UniqueConstraint(fields=("tenant", "module", "action"), name="operations_unique_approval_rule_per_tenant"),
        ),
        migrations.AddConstraint(
            model_name="approvalrequest",
            constraint=models.UniqueConstraint(fields=("tenant", "module", "action", "reference_id"), name="operations_unique_approval_request_source"),
        ),
        migrations.AddField(
            model_name="inappnotification",
            name="event_key",
            field=models.CharField(blank=True, help_text="Optional durable source-event identity preventing duplicate inbox entries.", max_length=160),
        ),
        migrations.AddConstraint(
            model_name="inappnotification",
            constraint=models.UniqueConstraint(
                condition=~Q(("event_key", "")),
                fields=("tenant", "user", "event_key"),
                name="operations_unique_notification_event_per_user",
            ),
        ),
    ]
