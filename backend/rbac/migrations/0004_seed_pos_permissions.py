from django.db import migrations


def seed_pos_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    module, _ = Module.objects.get_or_create(key="pos", defaults={"label": "POS"})
    for action in ("view", "create", "update", "refund", "void", "discount"):
        Permission.objects.get_or_create(module=module, action=action)


def unseed_pos_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    module = Module.objects.filter(key="pos").first()
    if module:
        module.permissions.filter(action__in=("view", "create", "update", "refund", "void", "discount")).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0003_seed_supplier_permissions")]
    operations = [migrations.RunPython(seed_pos_permissions, unseed_pos_permissions)]
