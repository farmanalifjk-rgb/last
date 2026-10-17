from django.db import migrations


REGISTRY = {
    "pos": ("POS", ["view", "create", "update", "refund", "void", "discount"]),
    "payments": ("Payments", ["view", "create", "update", "refund", "void", "manage"]),
    "inventory": ("Inventory", ["view", "create", "update", "delete", "manage"]),
    "products": ("Products", ["view", "create", "update", "delete"]),
    "customers": ("Customers", ["view", "create", "update", "delete"]),
    "suppliers": ("Suppliers", ["view", "create", "update"]),
    "purchasing": ("Purchasing", ["view", "create", "update", "approve", "receive", "return"]),
    "accounting": ("Accounting", ["view", "create", "update", "post", "manage"]),
    "reports": ("Reports", ["view", "report", "export"]),
    "tax": ("Tax", ["view", "manage", "report"]),
    "hr": ("HR", ["view", "create", "update", "manage"]),
    "fiscal": ("Fiscal", ["view", "create", "manage"]),
    "audit": ("Audit", ["view"]),
    "operations": ("Operations", ["view", "manage", "approve"]),
    "settings": ("Settings", ["view", "manage"]),
    "billing": ("SaaS billing", ["view", "manage", "request", "verify"]),
    "rbac": ("RBAC", ["view", "manage"]),
    "system": ("System", ["manage"]),
}

BUNDLES = {
    "builtin-cashier": ["pos.view", "pos.create", "products.view", "customers.view", "customers.create"],
    "builtin-pos-manager": ["pos.view", "pos.create", "pos.update", "pos.refund", "pos.void", "pos.discount", "customers.view", "customers.create", "customers.update", "products.view", "payments.view", "payments.manage"],
    "builtin-inventory-manager": ["inventory.view", "inventory.create", "inventory.update", "inventory.delete", "inventory.manage", "products.view", "products.create", "products.update", "products.delete"],
    "builtin-warehouse-staff": ["inventory.view", "inventory.create", "inventory.update", "products.view"],
    "builtin-purchasing-manager": ["suppliers.view", "suppliers.create", "suppliers.update", "purchasing.view", "purchasing.create", "purchasing.update", "purchasing.approve", "purchasing.receive", "purchasing.return"],
    "builtin-purchasing-staff": ["suppliers.view", "purchasing.view", "purchasing.create", "purchasing.update"],
    "builtin-finance-manager": ["accounting.view", "accounting.create", "accounting.update", "accounting.post", "accounting.manage", "reports.view", "reports.report", "reports.export", "tax.view", "tax.manage", "tax.report", "fiscal.view", "fiscal.create", "fiscal.manage", "audit.view"],
    "builtin-accountant": ["accounting.view", "accounting.create", "accounting.update", "accounting.post", "reports.view", "reports.report", "tax.view", "tax.report", "fiscal.view", "audit.view"],
    "builtin-hr-manager": ["hr.view", "hr.create", "hr.update", "hr.manage"],
    "builtin-hr-staff": ["hr.view", "hr.create", "hr.update"],
    "builtin-operations-manager": ["operations.view", "operations.manage", "operations.approve", "audit.view"],
    "builtin-auditor": ["accounting.view", "reports.view", "reports.report", "audit.view", "operations.view"],
    "builtin-viewer": ["products.view", "customers.view", "inventory.view", "suppliers.view", "purchasing.view", "pos.view", "payments.view", "reports.view"],
    "builtin-platform-developer": ["rbac.manage", "system.manage"],
    "builtin-global-billing-verifier": ["billing.verify"],
}


def apply_metadata(item):
    key = (item.module.key, item.action)
    platform = key in {("billing", "verify"), ("system", "manage"), ("rbac", "manage")}
    sensitive = key in {
        ("billing", "verify"), ("payments", "refund"), ("payments", "manage"),
        ("accounting", "post"), ("accounting", "manage"), ("fiscal", "manage"),
        ("hr", "manage"), ("operations", "approve"), ("settings", "manage"),
        ("system", "manage"), ("rbac", "manage"),
    }
    if item.action in {"manage", "verify"}:
        access_kind = "admin"
    elif item.action in {"approve", "post", "refund"}:
        access_kind = "approve"
    elif item.action in {"create", "update", "delete", "void", "discount", "receive", "return", "request"}:
        access_kind = "mutate"
    else:
        access_kind = "read"
    risk = "critical" if sensitive else "high" if access_kind in {"admin", "approve"} else "medium" if access_kind == "mutate" else "low"
    item.scope = "platform" if platform else "tenant"
    item.access_kind = access_kind
    item.risk_level = risk
    item.is_sensitive = sensitive
    item.save(update_fields=["scope", "access_kind", "risk_level", "is_sensitive"])


def seed_complete_registry(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    for module_key, (label, actions) in REGISTRY.items():
        module, _ = Module.objects.get_or_create(key=module_key, defaults={"label": label, "is_active": True})
        for action in actions:
            item, _ = Permission.objects.get_or_create(module=module, action=action)
            apply_metadata(item)
    for role_key, keys in BUNDLES.items():
        role = Role.objects.filter(key=role_key).first()
        if role is None:
            continue
        items = []
        for key in keys:
            module_key, action = key.split(".", 1)
            items.append(Permission.objects.get(module__key=module_key, action=action))
        role.permissions.set(items)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0013_phase15_assignment_null_scope_unique")]

    operations = [migrations.RunPython(seed_complete_registry, migrations.RunPython.noop)]
