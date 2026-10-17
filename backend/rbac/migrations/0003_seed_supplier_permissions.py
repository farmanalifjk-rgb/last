from django.db import migrations


def seed_supplier_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    module, _ = Module.objects.get_or_create(key="suppliers", defaults={"label": "Suppliers", "is_active": True})
    for action in ("view", "create", "update"):
        Permission.objects.get_or_create(module=module, action=action)


def unseed_supplier_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Module.objects.filter(key="suppliers").delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0002_seed_purchasing_permissions")]

    operations = [migrations.RunPython(seed_supplier_permissions, unseed_supplier_permissions)]
