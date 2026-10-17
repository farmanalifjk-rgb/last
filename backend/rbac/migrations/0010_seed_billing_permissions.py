from django.db import migrations

PERMISSIONS = ("view", "manage")

def seed_billing_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    module, _ = Module.objects.get_or_create(key="billing", defaults={"label": "SaaS billing"})
    for action in PERMISSIONS:
        Permission.objects.get_or_create(module=module, action=action)

def unseed_billing_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    Permission.objects.filter(module__key="billing", action__in=PERMISSIONS).delete()
    Module.objects.filter(key="billing").delete()

class Migration(migrations.Migration):
    dependencies = [("rbac", "0009_seed_operations_permissions")]
    operations = [migrations.RunPython(seed_billing_permissions, unseed_billing_permissions)]
