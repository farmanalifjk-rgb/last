from django.db import migrations


PERMISSIONS = ("view", "approve", "manage")


def seed_operations_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    module, _ = Module.objects.get_or_create(key="operations", defaults={"label": "Operations"})
    for action in PERMISSIONS:
        Permission.objects.get_or_create(module=module, action=action)


def unseed_operations_permissions(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Permission.objects.filter(module__key="operations", action__in=PERMISSIONS).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0008_seed_reports_permissions")]
    operations = [migrations.RunPython(seed_operations_permissions, unseed_operations_permissions)]
