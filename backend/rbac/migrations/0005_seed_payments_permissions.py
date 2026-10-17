from django.db import migrations


PAYMENT_ACTIONS = ("view", "create", "update", "refund", "void", "manage")


def seed_payments_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    module, _ = Module.objects.get_or_create(key="payments", defaults={"label": "Payments"})
    for action in PAYMENT_ACTIONS:
        Permission.objects.get_or_create(module=module, action=action)


def unseed_payments_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    module = Module.objects.filter(key="payments").first()
    if module:
        module.permissions.filter(action__in=PAYMENT_ACTIONS).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0004_seed_pos_permissions")]
    operations = [migrations.RunPython(seed_payments_permissions, unseed_payments_permissions)]
