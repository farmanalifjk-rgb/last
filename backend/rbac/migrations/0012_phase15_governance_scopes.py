from django.db import migrations, models
import django.db.models.deletion


def seed_phase15_governance(apps, schema_editor):
    Module = apps.get_model("rbac", "Module")
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    UserRole = apps.get_model("rbac", "UserRole")
    PermissionOverride = apps.get_model("rbac", "PermissionOverride")
    TenantMembership = apps.get_model("saas", "TenantMembership")

    def permission(module_key, action, **metadata):
        module, _ = Module.objects.get_or_create(key=module_key, defaults={"label": module_key.replace("_", " ").title(), "is_active": True})
        item, _ = Permission.objects.get_or_create(module=module, action=action)
        Permission.objects.filter(pk=item.pk).update(**metadata)
        return Permission.objects.get(pk=item.pk)

    sensitive = {
        ("billing", "verify"), ("payments", "refund"), ("payments", "manage"),
        ("accounting", "post"), ("accounting", "manage"), ("fiscal", "manage"),
        ("hr", "manage"), ("operations", "approve"), ("settings", "manage"),
        ("system", "manage"), ("rbac", "manage"),
    }
    access_admin = {"manage", "verify"}
    access_approve = {"approve", "post", "refund"}
    access_mutate = {"create", "update", "delete", "void", "discount", "receive", "return", "request"}
    platform = {("billing", "verify"), ("system", "manage"), ("rbac", "manage")}
    for item in Permission.objects.select_related("module"):
        key = (item.module.key, item.action)
        if key in platform:
            scope = "platform"
        else:
            scope = "tenant"
        if item.action in access_admin:
            kind = "admin"
        elif item.action in access_approve:
            kind = "approve"
        elif item.action in access_mutate:
            kind = "mutate"
        else:
            kind = "read"
        risk = "critical" if key in sensitive else "high" if kind in {"admin", "approve"} else "medium" if kind == "mutate" else "low"
        Permission.objects.filter(pk=item.pk).update(scope=scope, access_kind=kind, risk_level=risk, is_sensitive=key in sensitive)

    for module_key, action, metadata in [
        ("rbac", "view", {"scope": "tenant", "access_kind": "read", "risk_level": "medium", "is_sensitive": False}),
        ("rbac", "manage", {"scope": "platform", "access_kind": "admin", "risk_level": "critical", "is_sensitive": True}),
        ("system", "manage", {"scope": "platform", "access_kind": "admin", "risk_level": "critical", "is_sensitive": True}),
        ("billing", "verify", {"scope": "platform", "access_kind": "admin", "risk_level": "critical", "is_sensitive": True}),
    ]:
        permission(module_key, action, **metadata)

    # Existing unscoped rows are migration-compatible only for a user with exactly one membership.
    for assignment in UserRole.objects.filter(tenant__isnull=True).iterator():
        tenant_ids = list(TenantMembership.objects.filter(user_id=assignment.user_id).values_list("tenant_id", flat=True)[:2])
        if len(tenant_ids) == 1:
            assignment.tenant_id = tenant_ids[0]
            assignment.save(update_fields=["tenant"])
    for override in PermissionOverride.objects.filter(tenant__isnull=True).iterator():
        tenant_ids = list(TenantMembership.objects.filter(user_id=override.user_id).values_list("tenant_id", flat=True)[:2])
        if len(tenant_ids) == 1:
            override.tenant_id = tenant_ids[0]
            override.save(update_fields=["tenant"])

    bundles = {
        "builtin-cashier": ("Cashier", "Tenant", ["pos.view", "pos.create", "products.view", "customers.view", "customers.create"]),
        "builtin-pos-manager": ("POS Manager", "Tenant", ["pos.view", "pos.create", "pos.update", "pos.refund", "pos.void", "pos.discount", "customers.view", "customers.create", "customers.update", "products.view", "payments.view", "payments.manage"]),
        "builtin-inventory-manager": ("Inventory Manager", "Tenant", ["inventory.view", "inventory.create", "inventory.update", "inventory.delete", "inventory.manage", "products.view", "products.create", "products.update", "products.delete"]),
        "builtin-warehouse-staff": ("Warehouse Staff", "Tenant", ["inventory.view", "inventory.create", "inventory.update", "products.view"]),
        "builtin-purchasing-manager": ("Purchasing Manager", "Tenant", ["suppliers.view", "suppliers.create", "suppliers.update", "purchasing.view", "purchasing.create", "purchasing.update", "purchasing.approve", "purchasing.receive", "purchasing.return"]),
        "builtin-purchasing-staff": ("Purchasing Staff", "Tenant", ["suppliers.view", "purchasing.view", "purchasing.create", "purchasing.update"]),
        "builtin-finance-manager": ("Finance Manager", "Tenant", ["accounting.view", "accounting.create", "accounting.update", "accounting.post", "accounting.manage", "reports.view", "reports.report", "reports.export", "tax.view", "tax.manage", "tax.report", "fiscal.view", "fiscal.create", "fiscal.manage", "audit.view"]),
        "builtin-accountant": ("Accountant", "Tenant", ["accounting.view", "accounting.create", "accounting.update", "accounting.post", "reports.view", "reports.report", "tax.view", "tax.report", "fiscal.view", "audit.view"]),
        "builtin-hr-manager": ("HR Manager", "Tenant", ["hr.view", "hr.create", "hr.update", "hr.manage"]),
        "builtin-hr-staff": ("HR Staff", "Tenant", ["hr.view", "hr.create", "hr.update"]),
        "builtin-operations-manager": ("Operations Manager", "Tenant", ["operations.view", "operations.manage", "operations.approve", "audit.view"]),
        "builtin-auditor": ("Auditor", "Tenant", ["accounting.view", "reports.view", "reports.report", "audit.view", "operations.view"]),
        "builtin-viewer": ("Viewer", "Tenant", ["products.view", "customers.view", "inventory.view", "suppliers.view", "purchasing.view", "pos.view", "payments.view", "reports.view"]),
        "builtin-platform-developer": ("Platform Developer", "Platform", ["rbac.manage", "system.manage"]),
        "builtin-global-billing-verifier": ("Global Billing Verifier", "Platform", ["billing.verify"]),
    }
    for key, (label, scope_label, keys) in bundles.items():
        role, _ = Role.objects.update_or_create(
            key=key,
            defaults={"label": label, "description": "Phase 15 built-in governance permission bundle.", "is_system": True, "is_active": True, "scope": scope_label.lower(), "tenant": None},
        )
        perms = []
        for value in keys:
            module_key, action = value.split(".", 1)
            item = Permission.objects.filter(module__key=module_key, action=action).first()
            if item:
                perms.append(item)
        role.permissions.set(perms)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0011_phase13c_billing_permissions"), ("saas", "0004_manual_billing")]

    operations = [
        migrations.AddField(model_name="permission", name="access_kind", field=models.CharField(choices=[("read", "Read"), ("mutate", "Mutate"), ("approve", "Approve"), ("admin", "Admin")], default="read", max_length=12)),
        migrations.AddField(model_name="permission", name="is_sensitive", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="permission", name="risk_level", field=models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], default="low", max_length=12)),
        migrations.AddField(model_name="permission", name="scope", field=models.CharField(choices=[("tenant", "Tenant"), ("platform", "Platform")], default="tenant", max_length=12)),
        migrations.AddField(model_name="role", name="is_active", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="role", name="scope", field=models.CharField(choices=[("tenant", "Tenant"), ("platform", "Platform")], default="tenant", max_length=12)),
        migrations.AddField(model_name="role", name="tenant", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="rbac_roles", to="saas.tenant")),
        migrations.AddField(model_name="userrole", name="tenant", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="rbac_role_assignments", to="saas.tenant")),
        migrations.AddField(model_name="permissionoverride", name="tenant", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="rbac_permission_overrides", to="saas.tenant")),
        migrations.AlterField(model_name="permission", name="action", field=models.CharField(choices=[("view", "View"), ("create", "Create"), ("update", "Update"), ("delete", "Delete"), ("refund", "Refund"), ("void", "Void"), ("discount", "Discount"), ("report", "Report"), ("manage", "Manage"), ("request", "Request"), ("verify", "Verify"), ("approve", "Approve"), ("receive", "Receive"), ("return", "Return"), ("post", "Post"), ("export", "Export")], max_length=20)),
        migrations.AlterUniqueTogether(name="userrole", unique_together=set()),
        migrations.AlterUniqueTogether(name="permissionoverride", unique_together=set()),
        migrations.AddConstraint(model_name="userrole", constraint=models.UniqueConstraint(fields=("user", "role", "tenant", "branch"), name="rbac_unique_user_role_scope")),
        migrations.AddConstraint(model_name="permissionoverride", constraint=models.UniqueConstraint(fields=("user", "permission", "tenant"), name="rbac_unique_user_permission_scope")),
        migrations.RunPython(seed_phase15_governance, migrations.RunPython.noop),
    ]
