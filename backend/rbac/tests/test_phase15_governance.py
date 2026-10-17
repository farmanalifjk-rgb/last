from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from auth_app.models import AuthToken
from rbac.checker import has_permission, user_permissions
from rbac.models import Module, Permission, Role, RoleTemplate, UserRole
from saas.models import PlanEntitlement, Subscription, SubscriptionPlan, Tenant, TenantMembership


User = get_user_model()


class Phase15GovernanceTests(TestCase):
    def setUp(self):
        from rbac.checker import seed_modules_and_permissions
        seed_modules_and_permissions()
        self.owner = User.objects.create_user(username="p15-owner", password="StrongPass123!")
        self.viewer = User.objects.create_user(username="p15-viewer", password="StrongPass123!")
        self.other_owner = User.objects.create_user(username="p15-other-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase 15 Tenant", slug="phase15-tenant", owner=self.owner, status="active")
        self.other_tenant = Tenant.objects.create(name="Phase 15 Other Tenant", slug="phase15-other", owner=self.other_owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.tenant, user=self.viewer, role=TenantMembership.ROLE_STAFF, is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.other_tenant, user=self.viewer, role=TenantMembership.ROLE_STAFF, is_active_in_tenant=False)
        TenantMembership.objects.create(tenant=self.other_tenant, user=self.other_owner, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        products, _ = Module.objects.get_or_create(key="products", defaults={"label": "Products"})
        billing, _ = Module.objects.get_or_create(key="billing", defaults={"label": "Billing"})
        self.product_view, _ = Permission.objects.get_or_create(
            module=products, action="view",
            defaults={"scope": Permission.SCOPE_TENANT, "access_kind": Permission.ACCESS_READ},
        )
        self.billing_verify, _ = Permission.objects.get_or_create(
            module=billing, action="verify",
            defaults={"scope": Permission.SCOPE_PLATFORM, "access_kind": Permission.ACCESS_ADMIN, "risk_level": Permission.RISK_CRITICAL, "is_sensitive": True},
        )
        if self.billing_verify.scope != Permission.SCOPE_PLATFORM:
            self.billing_verify.scope = Permission.SCOPE_PLATFORM
            self.billing_verify.access_kind = Permission.ACCESS_ADMIN
            self.billing_verify.risk_level = Permission.RISK_CRITICAL
            self.billing_verify.is_sensitive = True
            self.billing_verify.save(update_fields=["scope", "access_kind", "risk_level", "is_sensitive"])
        accounting, _ = Module.objects.get_or_create(key="accounting", defaults={"label": "Accounting"})
        self.accounting_post, _ = Permission.objects.get_or_create(
            module=accounting, action="post",
            defaults={"scope": Permission.SCOPE_TENANT, "access_kind": Permission.ACCESS_APPROVE, "risk_level": Permission.RISK_CRITICAL, "is_sensitive": True},
        )
        if not self.accounting_post.is_sensitive:
            self.accounting_post.is_sensitive = True
            self.accounting_post.risk_level = Permission.RISK_CRITICAL
            self.accounting_post.access_kind = Permission.ACCESS_APPROVE
            self.accounting_post.save(update_fields=["is_sensitive", "risk_level", "access_kind"])

    def create_custom_role(self, *, tenant=None, key="viewer", permissions=None):
        role = Role.objects.create(
            key=f"tenant-{(tenant or self.tenant).id}-{key}", label=key.title(),
            tenant=tenant or self.tenant, scope=Permission.SCOPE_TENANT,
        )
        role.permissions.set(permissions or [self.product_view])
        return role

    def test_governance_endpoints_are_available_to_owner_and_global_legacy_crud_is_not(self):
        roles = self.client.get("/api/rbac/governance/roles/")
        permissions = self.client.get("/api/rbac/governance/permissions/")
        members = self.client.get("/api/rbac/governance/members/")
        self.assertEqual(roles.status_code, 200, roles.data)
        self.assertEqual(permissions.status_code, 200, permissions.data)
        self.assertEqual(members.status_code, 200, members.data)
        # A tenant owner is not a platform RBAC administrator.
        self.assertEqual(self.client.get("/api/rbac/roles/").status_code, 403)
        self.assertEqual(self.client.get("/api/users/").status_code, 403)

    def test_tenant_administrator_can_govern_only_their_active_tenant(self):
        administrator = User.objects.create_user(username="p15-tenant-admin", password="StrongPass123!")
        TenantMembership.objects.create(
            tenant=self.tenant, user=administrator,
            role=TenantMembership.ROLE_ADMIN, is_active_in_tenant=True,
        )
        administrator_client = APIClient()
        administrator_client.force_authenticate(administrator)
        self.assertEqual(administrator_client.get("/api/rbac/governance/roles/").status_code, 200)
        created = administrator_client.post("/api/rbac/governance/roles/", {
            "key": "admin-created", "label": "Admin created",
            "permission_ids": [self.product_view.id],
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["tenant"], self.tenant.id)
        self.assertEqual(administrator_client.get("/api/rbac/roles/").status_code, 403)

    def test_canonical_viewer_bundle_contains_only_documented_tenant_read_access(self):
        viewer = Role.objects.get(key="builtin-viewer")
        keys = set(viewer.permissions.select_related("module").values_list("module__key", "action"))
        self.assertEqual(keys, {
            ("products", "view"), ("customers", "view"), ("inventory", "view"),
            ("suppliers", "view"), ("purchasing", "view"), ("pos", "view"),
            ("payments", "view"), ("reports", "view"),
        })

    def test_role_creation_requires_sensitive_acknowledgement_and_rejects_platform_permissions(self):
        requires_confirmation = self.client.post("/api/rbac/governance/roles/", {
            "key": "sensitive-finance", "label": "Sensitive finance",
            "permission_ids": [self.accounting_post.id], "confirm_sensitive": False,
        }, format="json")
        self.assertEqual(requires_confirmation.status_code, 400)
        response = self.client.post("/api/rbac/governance/roles/", {
            "key": "sensitive-finance", "label": "Sensitive finance",
            "permission_ids": [self.accounting_post.id], "confirm_sensitive": True,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["tenant"], self.tenant.id)
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant, action="rbac.role.created").exists())
        platform = self.client.post("/api/rbac/governance/roles/", {
            "key": "illicit-platform", "label": "Illicit platform",
            "permission_ids": [self.billing_verify.id], "confirm_sensitive": True,
        }, format="json")
        self.assertEqual(platform.status_code, 400)

    def test_assignment_is_tenant_scoped_revokes_sessions_and_cannot_self_escalate(self):
        role = self.create_custom_role()
        token = AuthToken.objects.create(user=self.viewer)
        assigned = self.client.post("/api/rbac/governance/assignments/", {
            "user": self.viewer.id, "role": role.id,
        }, format="json")
        self.assertEqual(assigned.status_code, 201, assigned.data)
        token.refresh_from_db()
        self.assertTrue(token.is_revoked)
        self.assertTrue(has_permission(self.viewer, "products", "view", tenant=self.tenant))
        self.assertFalse(has_permission(self.viewer, "products", "view", tenant=self.other_tenant))
        self.assertEqual(user_permissions(self.viewer, tenant=self.other_tenant), set())
        viewer_client = APIClient()
        viewer_client.force_authenticate(self.viewer)
        self.assertIn("products.view", viewer_client.get("/api/rbac/me/").data["permissions"])
        switched = viewer_client.post("/api/saas/tenants/switch/", {"tenant_id": self.other_tenant.id}, format="json")
        self.assertEqual(switched.status_code, 200, switched.data)
        self.assertNotIn("products.view", viewer_client.get("/api/rbac/me/").data["permissions"])
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant, action="rbac.role.assigned").exists())
        self_escalation = self.client.post("/api/rbac/governance/assignments/", {
            "user": self.owner.id, "role": role.id,
        }, format="json")
        self.assertEqual(self_escalation.status_code, 403)

    def test_cross_tenant_role_and_assignment_tampering_are_rejected(self):
        foreign_role = self.create_custom_role(tenant=self.other_tenant, key="foreign")
        assignment = self.client.post("/api/rbac/governance/assignments/", {
            "user": self.viewer.id, "role": foreign_role.id,
        }, format="json")
        self.assertEqual(assignment.status_code, 400)
        foreign_detail = self.client.get(f"/api/rbac/governance/roles/{foreign_role.id}/")
        self.assertEqual(foreign_detail.status_code, 403)

    def test_effective_permissions_and_deactivation_are_tenant_safe(self):
        role = self.create_custom_role(key="effective")
        assignment = UserRole.objects.create(user=self.viewer, role=role, tenant=self.tenant, assigned_by=self.owner)
        effective = self.client.get(f"/api/rbac/governance/effective/{self.viewer.id}/")
        self.assertEqual(effective.status_code, 200, effective.data)
        self.assertEqual(effective.data["membership_role"], TenantMembership.ROLE_STAFF)
        self.assertIn("products.view", effective.data["permissions"])
        self.assertEqual(effective.data["roles"][0]["key"], role.key)
        removed = self.client.delete(f"/api/rbac/governance/assignments/{assignment.id}/")
        self.assertEqual(removed.status_code, 204)
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertFalse(has_permission(self.viewer, "products", "view", tenant=self.tenant))
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant, action="rbac.role.removed").exists())

    def test_role_governance_does_not_mutate_or_replace_plan_entitlements(self):
        plan = SubscriptionPlan.objects.create(name="Phase 15 Plan", slug="phase15-plan", max_users=3)
        Subscription.objects.create(tenant=self.tenant, plan=plan, status=Subscription.STATUS_ACTIVE)
        entitlement = PlanEntitlement.objects.create(plan=plan, code="advanced_reports", label="Advanced reports", enabled=False)
        before = list(PlanEntitlement.objects.filter(plan=plan).values_list("code", "enabled", "limit_value"))
        role = self.create_custom_role(key="entitlement-separation")
        assigned = self.client.post("/api/rbac/governance/assignments/", {"user": self.viewer.id, "role": role.id}, format="json")
        self.assertEqual(assigned.status_code, 201, assigned.data)
        entitlement.refresh_from_db()
        self.assertEqual(list(PlanEntitlement.objects.filter(plan=plan).values_list("code", "enabled", "limit_value")), before)
        self.assertFalse(entitlement.enabled)

    def test_permission_overrides_are_restricted_to_tenant_governance(self):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get('/api/rbac/overrides/').status_code, 403)

        denied = self.client.post("/api/rbac/overrides/", {
            "user": self.viewer.id,
            "permission": self.product_view.id,
            "decision": "allow",
        }, format="json")
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/rbac/overrides/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_apply_template_endpoint_uses_global_template_and_tenant_role(self):
        role = self.create_custom_role(key="template-api")
        template = RoleTemplate.objects.get(key="manager")
        response = self.client.post(
            f"/api/rbac/roles/{role.id}/apply-template/",
            {"template_id": template.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("pos.create", response.data["added"])

        role.refresh_from_db()
        permission_keys = set(
            role.permissions.select_related("module").values_list(
                "module__key", "action"
            )
        )
        self.assertIn(("pos", "create"), permission_keys)        

    def test_non_admin_member_cannot_read_or_mutate_tenant_governance(self):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get("/api/rbac/governance/roles/").status_code, 403)
        self.assertEqual(self.client.post("/api/rbac/governance/roles/", {
            "key": "unauthorized", "label": "Unauthorized", "permission_ids": [self.product_view.id],
        }, format="json").status_code, 403)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-specific row-locking and uniqueness test")
class Phase15GovernanceConcurrencyTests(TransactionTestCase):
    def setUp(self):
        from rbac.checker import seed_modules_and_permissions
        seed_modules_and_permissions()
        self.owner = User.objects.create_user(username="p15-concurrent-owner", password="StrongPass123!")
        self.viewer = User.objects.create_user(username="p15-concurrent-viewer", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase 15 Concurrency", slug="phase15-concurrency", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.tenant, user=self.viewer, role=TenantMembership.ROLE_STAFF, is_active_in_tenant=True)
        products, _ = Module.objects.get_or_create(key="products", defaults={"label": "Products"})
        product_view, _ = Permission.objects.get_or_create(
            module=products, action="view",
            defaults={"scope": Permission.SCOPE_TENANT, "access_kind": Permission.ACCESS_READ},
        )
        self.role = Role.objects.create(key=f"tenant-{self.tenant.id}-concurrent", label="Concurrent", tenant=self.tenant, scope=Permission.SCOPE_TENANT)
        self.role.permissions.add(product_view)

    def test_duplicate_scoped_assignment_is_prevented_under_contention(self):
        def create_assignment():
            close_old_connections()
            try:
                UserRole.objects.create(user_id=self.viewer.id, role_id=self.role.id, tenant_id=self.tenant.id, assigned_by_id=self.owner.id)
                return "created"
            except IntegrityError:
                return "duplicate"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: create_assignment(), range(2)))
        self.assertEqual(outcomes.count("created"), 1)
        self.assertEqual(outcomes.count("duplicate"), 1)
        self.assertEqual(UserRole.objects.filter(user=self.viewer, role=self.role, tenant=self.tenant).count(), 1)


class Phase19ScopedCatalogTests(TestCase):
    def setUp(self):
        from rbac.checker import seed_modules_and_permissions
        seed_modules_and_permissions()
        from rbac.checker import apply_template_to_role, seed_modules_and_permissions
        from rbac.models import RoleTemplate

        seed_modules_and_permissions()
        self.apply_template_to_role = apply_template_to_role
        RoleTemplate = RoleTemplate
        self.user = User.objects.create_user(username="phase19-rbac", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase 19 RBAC", slug="phase19-rbac", owner=self.user)
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=TenantMembership.ROLE_STAFF,
            is_active_in_tenant=True,
        )

    def test_permission_key_can_exist_once_per_scope(self):
        settings_module = Module.objects.get(key="settings")
        tenant_permission = Permission.objects.get(
            module=settings_module,
            action="manage",
            scope=Permission.SCOPE_TENANT,
        )
        platform_permission = Permission.objects.get(
            module=settings_module,
            action="manage",
            scope=Permission.SCOPE_PLATFORM,
        )
        self.assertNotEqual(tenant_permission.id, platform_permission.id)

    def test_manager_template_materializes_atomic_tenant_permissions(self):
        role = Role.objects.create(
            key="phase19-manager",
            label="Phase 19 Manager",
            tenant=self.tenant,
            scope=Permission.SCOPE_TENANT,
        )
        manager = RoleTemplate.objects.get(key="manager")

        added = self.apply_template_to_role(role, manager)

        self.assertIn("pos.create", added)
        self.assertIn("integrations.manage", added)
        self.assertNotIn("settings.manage", [
            f"{permission.module.key}.{permission.action}"
            for permission in role.permissions.filter(scope=Permission.SCOPE_PLATFORM).select_related("module")
        ])
        self.assertTrue(has_permission(self.user, "pos", "create", tenant=self.tenant) is False)
        UserRole.objects.create(user=self.user, role=role, tenant=self.tenant)
        self.assertTrue(has_permission(self.user, "pos", "create", tenant=self.tenant))
        self.assertFalse(has_permission(self.user, "settings", "manage", scope=Permission.SCOPE_PLATFORM))




