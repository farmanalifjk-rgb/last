from django.db import migrations


def seed_reports_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    module, _ = Module.objects.get_or_create(key="reports", defaults={"label": "Reports"})
    for action in ("view", "report", "export"):
        Permission.objects.get_or_create(module=module, action=action)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0007_seed_reports_export_permission")]

    operations = [migrations.RunPython(seed_reports_permissions, migrations.RunPython.noop)]
