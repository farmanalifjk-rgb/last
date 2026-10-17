from django.db import migrations


TENANT_CATALOG = {
    "dashboard": ["view"],
    "pos": ["view", "create", "update", "refund", "void", "discount"],
    "payments": ["view", "create", "update", "refund", "void", "manage"],
    "inventory": ["view", "create", "update", "delete", "manage"],
    "transfers": ["view", "create", "update", "approve", "receive"],
    "products": ["view", "create", "update", "delete"],
    "catalog": ["view", "create", "update", "manage"],
    "pricing": ["view", "create", "update", "manage"],
    "customers": ["view", "create", "update", "delete"],
    "loyalty": ["view", "create", "update", "manage"],
    "suppliers": ["view", "create", "update"],
    "purchasing": ["view", "create", "update", "approve", "receive", "return"],
    "accounting": ["view", "create", "update", "post", "manage"],
    "reports": ["view", "report", "export"],
    "tax": ["view", "manage", "report"],
    "hr": ["view", "create", "update", "manage"],
    "fiscal": ["view", "create", "manage"],
    "audit": ["view"],
    "operations": ["view", "manage", "approve"],
    "notifications": ["view", "manage"],
    "integrations": ["view", "manage"],
    "ai": ["view", "create", "update", "manage"],
    "hardware": ["view", "manage"],
    "settings": ["view", "manage"],
    "billing": ["view", "manage", "request"],
    "rbac": ["view", "manage"],
}
PLATFORM_CATALOG = {
    "settings": ["view", "manage"],
    "billing": ["verify"],
    "rbac": ["view", "manage"],
    "system": ["manage"],
}


def metadata(module_key, action, scope):
    sensitive = (module_key, action) in {
        ("billing", "verify"), ("payments", "refund"), ("payments", "manage"),
        ("accounting", "post"), ("accounting", "manage"), ("fiscal", "manage"),
        ("hr", "manage"), ("operations", "approve"), ("settings", "manage"),
        ("system", "manage"), ("rbac", "manage"), ("integrations", "manage"),
    }
    if action in {"manage", "verify"}:
        access_kind = "admin"
    elif action in {"approve", "post", "refund"}:
        access_kind = "approve"
    elif action in {"create", "update", "delete", "void", "discount", "receive", "return", "request"}:
        access_kind = "mutate"
    else:
        access_kind = "read"
    return {
        "scope": scope,
        "is_sensitive": sensitive,
        "access_kind": access_kind,
        "risk_level": "critical" if sensitive else "high" if access_kind in {"admin", "approve"} else "medium" if access_kind == "mutate" else "low",
    }


def seed_scoped_catalog(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RoleTemplate = apps.get_model("rbac", "RoleTemplate")

    for scope, catalog in (("tenant", TENANT_CATALOG), ("platform", PLATFORM_CATALOG)):
        for module_key, actions in catalog.items():
            module, _ = Module.objects.get_or_create(
                key=module_key,
                defaults={"label": module_key.replace("_", " ").title(), "is_active": True},
            )
            for action in actions:
                Permission.objects.update_or_create(
                    module=module,
                    action=action,
                    scope=scope,
                    defaults=metadata(module_key, action, scope),
                )

    RoleTemplate.objects.update_or_create(
        key="manager",
        defaults={"label": "Manager", "permission_keys": ["*.*"]},
    )
    # The old manager template stored a wildcard that earlier code could not
    # materialize. Existing tenant Manager roles receive the explicit atomic
    # tenant catalog represented by that documented wildcard intent.
    tenant_permissions = list(Permission.objects.filter(scope="tenant"))
    for role in Role.objects.filter(key__iexact="manager", scope="tenant"):
        role.permissions.add(*tenant_permissions)


def noop_reverse(apps, schema_editor):
    # Seeding only adds catalog metadata; it must not strip operator-granted roles.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0014_phase15_complete_permission_registry"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="permission",
            unique_together={("module", "action", "scope")},
        ),
        migrations.RunPython(seed_scoped_catalog, noop_reverse),
    ]
