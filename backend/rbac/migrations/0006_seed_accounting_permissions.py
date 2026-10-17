from django.db import migrations


ACCOUNTING_ACTIONS = ("view", "create", "update", "post", "manage")
ACCOUNTANT_PERMISSIONS = (
    "reports.view", "reports.report", "tax.view", "tax.report", "fiscal.view", "audit.view",
    "accounting.view", "accounting.create", "accounting.update", "accounting.post",
)


def seed_accounting_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    RoleTemplate = apps.get_model("rbac", "RoleTemplate")
    module, _ = Module.objects.get_or_create(key="accounting", defaults={"label": "Accounting"})
    for action in ACCOUNTING_ACTIONS:
        Permission.objects.get_or_create(module=module, action=action)
    RoleTemplate.objects.update_or_create(
        key="accountant",
        defaults={"label": "Accountant", "permission_keys": list(ACCOUNTANT_PERMISSIONS)},
    )


def unseed_accounting_permissions(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    module = Module.objects.filter(key="accounting").first()
    if module:
        module.permissions.filter(action__in=ACCOUNTING_ACTIONS).delete()


class Migration(migrations.Migration):
    dependencies = [("rbac", "0005_seed_payments_permissions")]

    operations = [migrations.RunPython(seed_accounting_permissions, unseed_accounting_permissions)]
