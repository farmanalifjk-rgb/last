from django.db import migrations, models


def seed_purchasing_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    module, _ = Module.objects.get_or_create(key="purchasing", defaults={"label": "Purchasing", "is_active": True})
    for action in ("view", "create", "update", "approve", "receive", "return"):
        Permission.objects.get_or_create(module=module, action=action)


def unseed_purchasing_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Module.objects.filter(key="purchasing").delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="permission",
            name="action",
            field=models.CharField(
                choices=[
                    ("view", "View"), ("create", "Create"), ("update", "Update"), ("delete", "Delete"),
                    ("refund", "Refund"), ("void", "Void"), ("discount", "Discount"), ("report", "Report"),
                    ("manage", "Manage"), ("approve", "Approve"), ("receive", "Receive"), ("return", "Return"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(seed_purchasing_permissions, unseed_purchasing_permissions),
    ]
