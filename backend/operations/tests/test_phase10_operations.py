from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from enterprise.models import Warehouse
from operations.models import ApprovalRequest, ApprovalRule, InAppNotification
from operations.services import create_notification, decide_approval, request_approval
from pos.models import Category, Product, Supplier
from rbac.models import Module, Permission, Role, UserRole
from saas.models import Tenant, TenantMembership
from system.models import APIKey


User = get_user_model()


def grant(user, *keys):
    role = Role.objects.create(key=f"phase10-{user.username}", label=f"Phase 10 {user.username}")
    for key in keys:
        module_key, action = key.split(".", 1)
        module, _ = Module.objects.get_or_create(key=module_key, defaults={"label": module_key.title()})
        permission, _ = Permission.objects.get_or_create(module=module, action=action)
        role.permissions.add(permission)
    UserRole.objects.create(user=user, role=role)


class Phase10OperationsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="phase10-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase Ten", slug="phase-ten", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        self.reviewer = User.objects.create_user(username="phase10-reviewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant, user=self.reviewer, role=TenantMembership.ROLE_MANAGER, is_active_in_tenant=True)
        grant(self.reviewer, "operations.view", "operations.approve", "audit.view", "settings.manage")
        self.viewer = User.objects.create_user(username="phase10-viewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant, user=self.viewer, role=TenantMembership.ROLE_MANAGER, is_active_in_tenant=True)
        grant(self.viewer, "operations.view", "audit.view")
        self.other_owner = User.objects.create_user(username="phase10-other", password="StrongPass123!")
        self.other_tenant = Tenant.objects.create(name="Phase Ten Other", slug="phase-ten-other", owner=self.other_owner, status="active")
        TenantMembership.objects.create(tenant=self.other_tenant, user=self.other_owner, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        self.client = APIClient()

    def source(self, source_id=1):
        return type("Source", (), {"pk": source_id, "tenant": self.tenant, "__str__": lambda self: "PO-PHASE10"})()

    def create_rule(self, **kwargs):
        values = {"tenant": self.tenant, "module": "purchase_order", "action": "confirm", "approver_role": "", "min_amount": Decimal("1.00")}
        values.update(kwargs)
        return ApprovalRule.objects.create(**values)

    def test_approval_rule_identity_is_tenant_local_and_request_creation_is_idempotent(self):
        self.create_rule()
        ApprovalRule.objects.create(tenant=self.other_tenant, module="purchase_order", action="confirm")
        first, created = request_approval(
            tenant=self.tenant, module="purchase_order", action="confirm", source=self.source(),
            requested_by=self.owner, amount=Decimal("50.00"), reference_str="PO-PHASE10",
        )
        replay, replay_created = request_approval(
            tenant=self.tenant, module="purchase_order", action="confirm", source=self.source(),
            requested_by=self.owner, amount=Decimal("50.00"), reference_str="PO-PHASE10",
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(first.pk, replay.pk)
        self.assertEqual(ApprovalRequest.objects.filter(tenant=self.tenant).count(), 1)

    def test_requester_cannot_self_approve_and_reviewer_can_decide_once(self):
        self.create_rule()
        approval, _ = request_approval(
            tenant=self.tenant, module="purchase_order", action="confirm", source=self.source(),
            requested_by=self.owner, amount=Decimal("50.00"), reference_str="PO-PHASE10",
        )
        with self.assertRaisesMessage(Exception, "cannot decide their own"):
            decide_approval(tenant=self.tenant, approval_id=approval.id, actor=self.owner, decision="approved")
        decided, _ = decide_approval(tenant=self.tenant, approval_id=approval.id, actor=self.reviewer, decision="rejected", note="Budget rejected")
        self.assertEqual(decided.status, ApprovalRequest.STATUS_REJECTED)
        with self.assertRaisesMessage(Exception, "already been decided"):
            decide_approval(tenant=self.tenant, approval_id=approval.id, actor=self.reviewer, decision="approved")

    def test_approval_and_notification_apis_are_tenant_scoped_and_direct_creation_is_blocked(self):
        self.create_rule()
        approval, _ = request_approval(
            tenant=self.tenant, module="purchase_order", action="confirm", source=self.source(),
            requested_by=self.owner, amount=Decimal("50.00"), reference_str="PO-PHASE10",
        )
        foreign = ApprovalRequest.objects.create(
            tenant=self.other_tenant, module="purchase_order", action="confirm", reference_id=99,
            requested_by=self.other_owner,
        )
        create_notification(tenant=self.tenant, user=self.viewer, event_key="phase10-source", notification_type="warning", title="Needs review", message="Review this.")
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get("/api/workflow/requests/").status_code, 200)
        requests = self.client.get("/api/workflow/requests/").data
        self.assertEqual((requests.get("results") if isinstance(requests, dict) else requests)[0]["id"], approval.id)
        self.assertEqual(self.client.get(f"/api/workflow/requests/{foreign.id}/").status_code, 404)
        self.assertEqual(self.client.post("/api/workflow/requests/", {}, format="json").status_code, 405)
        self.assertEqual(self.client.post(f"/api/workflow/requests/{approval.id}/approve/", {}, format="json").status_code, 403)
        inbox = self.client.get("/api/operations/notifications/")
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual((inbox.data.get("results") if isinstance(inbox.data, dict) else inbox.data)[0]["title"], "Needs review")

    def test_notification_event_identity_and_read_state_are_user_and_tenant_scoped(self):
        first = create_notification(tenant=self.tenant, user=self.viewer, event_key="approve:1", notification_type="warning", title="Approval", message="Review")
        replay = create_notification(tenant=self.tenant, user=self.viewer, event_key="approve:1", notification_type="warning", title="Approval", message="Review")
        self.assertEqual(first.id, replay.id)
        self.client.force_authenticate(self.viewer)
        marked = self.client.post(f"/api/operations/notifications/{first.id}/mark_read/", format="json")
        self.assertEqual(marked.status_code, 200)
        self.assertTrue(marked.data["is_read"])
        self.client.force_authenticate(self.other_owner)
        self.assertEqual(self.client.get(f"/api/operations/notifications/{first.id}/").status_code, 404)

    def test_audit_register_is_tenant_scoped_and_redacts_secret_keys(self):
        AuditEvent.objects.create(
            tenant=self.tenant, actor=self.owner, actor_name=self.owner.username, action="create",
            entity_type="system", entity_id="1", entity_label="System configuration",
            before={"api_key": "should-not-leak"}, after={"safe": "value", "token": "should-not-leak"},
        )
        AuditEvent.objects.create(
            tenant=self.other_tenant, actor=self.other_owner, actor_name=self.other_owner.username, action="create",
            entity_type="system", entity_id="2", entity_label="Other tenant",
        )
        self.client.force_authenticate(self.viewer)
        response = self.client.get("/api/audit/events/")
        self.assertEqual(response.status_code, 200)
        audit_rows = response.data.get("results") if isinstance(response.data, dict) else response.data
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(audit_rows[0]["before"]["api_key"], "[redacted]")
        self.assertEqual(audit_rows[0]["after"]["token"], "[redacted]")

    def test_api_key_is_tenant_scoped_and_secret_is_returned_only_at_creation(self):
        self.client.force_authenticate(self.reviewer)
        created = self.client.post("/api/api-keys/", {"name": "Phase 10 integration", "scopes": ["read:products"]}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(created.data["secret"].startswith("pos_"))
        key = APIKey.objects.get(tenant=self.tenant, pk=created.data["id"])
        self.assertNotEqual(key.key, created.data["secret"])
        listed = self.client.get("/api/api-keys/")
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn("secret", listed.data[0])
        self.assertNotIn(key.key, str(listed.data))

    def test_configured_purchase_order_confirmation_waits_for_approval_then_continues_canonical_source_transition(self):
        warehouse = Warehouse.objects.create(tenant=self.tenant, code="P10", name="Phase Ten Warehouse")
        category = Category.objects.create(tenant=self.tenant, name="Phase Ten Category")
        product = Product.objects.create(
            tenant=self.tenant, category=category, name="Phase Ten Product", sku="PHASE10-PO",
            sales_price=Decimal("9.00"), cost_price=Decimal("5.00"), stock_quantity=Decimal("0.00"), is_active=True,
        )
        supplier = Supplier.objects.create(tenant=self.tenant, name="Phase Ten Supply")
        self.create_rule(min_amount=Decimal("1.00"))
        self.client.force_authenticate(self.owner)
        created = self.client.post(
            "/api/purchasing/purchase-orders/",
            {"supplier_id": supplier.id, "warehouse_id": warehouse.id, "items": [{"product_id": product.id, "quantity": "2.00", "unit_cost": "5.00"}]},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        gated = self.client.post(f"/api/purchasing/purchase-orders/{created.data['id']}/confirm/", format="json")
        self.assertEqual(gated.status_code, 202, gated.data)
        approval = ApprovalRequest.objects.get(pk=gated.data["approval_request_id"], tenant=self.tenant)
        self.assertEqual(approval.status, ApprovalRequest.STATUS_PENDING)
        self.client.force_authenticate(self.reviewer)
        decided = self.client.post(f"/api/workflow/requests/{approval.id}/approve/", {"note": "Approved for acceptance"}, format="json")
        self.assertEqual(decided.status_code, 200, decided.data)
        self.assertEqual(decided.data["status"], ApprovalRequest.STATUS_APPROVED)
        self.assertEqual(decided.data["source_status"], "ordered")


@skipUnless(connection.vendor == "postgresql", "PostgreSQL-only approval locking coverage")
class Phase10ApprovalConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user(username="phase10-concurrent-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase Ten Locking", slug="phase-ten-locking", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        self.reviewer_one = User.objects.create_user(username="phase10-reviewer-one", password="StrongPass123!")
        self.reviewer_two = User.objects.create_user(username="phase10-reviewer-two", password="StrongPass123!")
        for reviewer in (self.reviewer_one, self.reviewer_two):
            TenantMembership.objects.create(tenant=self.tenant, user=reviewer, role=TenantMembership.ROLE_MANAGER, is_active_in_tenant=True)
            grant(reviewer, "operations.approve")
        ApprovalRule.objects.create(tenant=self.tenant, module="purchase_order", action="confirm")
        self.approval, _ = request_approval(
            tenant=self.tenant, module="purchase_order", action="confirm",
            source=type("Source", (), {"pk": 77, "tenant": self.tenant, "__str__": lambda self: "PO-LOCK"})(),
            requested_by=self.owner, amount=Decimal("20.00"), reference_str="PO-LOCK",
        )

    def _decide(self, user_id):
        close_old_connections()
        try:
            user = User.objects.get(pk=user_id)
            decide_approval(tenant=Tenant.objects.get(pk=self.tenant.pk), approval_id=self.approval.pk, actor=user, decision="rejected")
            return "decided"
        except Exception:
            return "blocked"
        finally:
            close_old_connections()

    def test_only_one_concurrent_decision_transitions_the_request(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self._decide, [self.reviewer_one.pk, self.reviewer_two.pk]))
        self.assertEqual(results.count("decided"), 1)
        self.approval.refresh_from_db()
        self.assertEqual(self.approval.status, ApprovalRequest.STATUS_REJECTED)
