from django.db import migrations, models


PERMISSIONS = ("request", "verify")


def seed_phase13c_billing_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    module, _ = Module.objects.get_or_create(key="billing", defaults={"label": "SaaS billing"})
    for action in PERMISSIONS:
        Permission.objects.get_or_create(module=module, action=action)


def unseed_phase13c_billing_permissions(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Permission.objects.filter(module__key="billing", action__in=PERMISSIONS).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0010_seed_billing_permissions")]

    operations = [
        migrations.AlterField(
            model_name="permission",
            name="action",
            field=models.CharField(
                choices=[
                    ("view", "View"), ("create", "Create"), ("update", "Update"),
                    ("delete", "Delete"), ("refund", "Refund"), ("void", "Void"),
                    ("discount", "Discount"), ("report", "Report"), ("manage", "Manage"),
                    ("request", "Request"), ("verify", "Verify"),
                    ("approve", "Approve"), ("receive", "Receive"), ("return", "Return"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(seed_phase13c_billing_permissions, unseed_phase13c_billing_permissions),
    ]
