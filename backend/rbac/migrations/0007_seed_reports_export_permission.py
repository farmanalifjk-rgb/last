from django.db import migrations


def seed_reports_export_permission(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    module, _ = Module.objects.get_or_create(key="reports", defaults={"label": "Reports"})
    Permission.objects.get_or_create(module=module, action="export")


def unseed_reports_export_permission(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Permission.objects.filter(module__key="reports", action="export").delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0006_seed_accounting_permissions")]

    operations = [migrations.RunPython(seed_reports_export_permission, unseed_reports_export_permission)]
