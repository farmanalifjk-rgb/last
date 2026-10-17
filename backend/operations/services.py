"""Canonical Phase 10 operational orchestration services.

Business domains retain their source records. This module stores only approval
references and user inbox rows, then invokes a supported source transition only
after a valid, locked approval decision.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from audit.recorder import record, snapshot
from rbac.models import UserRole
from saas.models import TenantMembership

from .models import ApprovalRequest, ApprovalRule, InAppNotification


def _amount_matches(rule, amount):
    if rule.min_amount is None:
        return True
    if amount is None:
        return False
    return Decimal(str(amount)) >= rule.min_amount


def matching_rule(*, tenant, module, action, amount):
    rule = ApprovalRule.objects.filter(
        tenant=tenant,
        module=module,
        action=action,
        is_active=True,
        requires_approval=True,
    ).first()
    return rule if rule and _amount_matches(rule, amount) else None


def create_notification(*, tenant, user, event_key, notification_type, title, message, link=""):
    """Create one tenant-scoped inbox row per durable event and recipient."""
    if not user:
        return None
    defaults = {
        "type": notification_type,
        "title": title,
        "message": message,
        "link": link,
    }
    if not event_key:
        return InAppNotification.objects.create(tenant=tenant, user=user, **defaults)
    notification, _ = InAppNotification.objects.get_or_create(
        tenant=tenant,
        user=user,
        event_key=event_key,
        defaults=defaults,
    )
    return notification


def request_approval(*, tenant, module, action, source, requested_by, amount=None, reference_str="", request=None):
    """Return a durable approval request for a supported source action.

    The source object remains authoritative. The unique source identity makes
    repeated confirmation attempts idempotent rather than creating a queue of
    duplicate approvals.
    """
    source_tenant_id = getattr(source, "tenant_id", None)
    if source_tenant_id is not None and source_tenant_id != tenant.id:
        raise PermissionDenied("The approval source does not belong to the active tenant.")
    rule = matching_rule(tenant=tenant, module=module, action=action, amount=amount)
    if not rule:
        return None, False
    values = {
        "reference_str": reference_str or str(source),
        "amount": amount,
        "requested_by": requested_by,
    }
    try:
        approval, created = ApprovalRequest.objects.get_or_create(
            tenant=tenant,
            module=module,
            action=action,
            reference_id=source.pk,
            defaults=values,
        )
    except IntegrityError:
        approval = ApprovalRequest.objects.get(
            tenant=tenant, module=module, action=action, reference_id=source.pk,
        )
        created = False
    if created:
        record(
            tenant=tenant,
            actor=requested_by,
            action="create",
            instance=approval,
            request=request,
            summary=f"Requested approval for {approval.reference_str or module}",
            icon="clipboard-check",
            after=snapshot(approval, fields=["module", "action", "reference_id", "amount", "status"]),
        )
        _notify_approvers(approval, rule)
    return approval, created


def _notify_approvers(approval, rule):
    # Role-targeted delivery is intentionally bounded to active tenant members.
    memberships = TenantMembership.objects.filter(
        tenant=approval.tenant,
        is_active_in_tenant=True,
    ).select_related("user")
    for membership in memberships:
        has_configured_role = UserRole.objects.filter(
            user=membership.user,
            tenant=approval.tenant,
            is_active=True,
            role__is_active=True,
            role__key=rule.approver_role,
        ).exists()
        if rule.approver_role and membership.role not in {TenantMembership.ROLE_OWNER, TenantMembership.ROLE_ADMIN} and not has_configured_role:
            continue
        create_notification(
            tenant=approval.tenant,
            user=membership.user,
            event_key=f"approval:{approval.pk}:requested:{membership.user_id}",
            notification_type=InAppNotification.TYPE_WARNING,
            title="Approval requested",
            message=f"{approval.reference_str or approval.module} requires a decision.",
            link="/operations?tab=approvals",
        )


def _actor_is_allowed_approver(*, actor, tenant, rule):
    membership = TenantMembership.objects.filter(
        tenant=tenant, user=actor, is_active_in_tenant=True,
    ).first()
    if membership is None:
        return False
    if membership.role in {TenantMembership.ROLE_OWNER, TenantMembership.ROLE_ADMIN}:
        return True
    if not rule.approver_role:
        return True
    return UserRole.objects.filter(
        user=actor,
        tenant=tenant,
        is_active=True,
        role__is_active=True,
        role__key=rule.approver_role,
    ).exists()


def _continue_supported_source(approval):
    """Continue only source transitions explicitly integrated by Phase 10."""
    if approval.module == "purchase_order" and approval.action == "confirm":
        from pos.models import PurchaseOrder
        from suppliers.purchasing_services import confirm_purchase_order

        order = PurchaseOrder.objects.select_for_update().get(
            tenant=approval.tenant, pk=approval.reference_id,
        )
        if approval.amount is not None and Decimal(str(order.total)) != approval.amount:
            raise ValidationError({"detail": "The purchase order amount changed after approval was requested; submit the current source for a new decision."})
        return confirm_purchase_order(tenant=approval.tenant, order=order)
    return None


@transaction.atomic
def decide_approval(*, tenant, approval_id, actor, decision, note="", request=None):
    """Lock once, validate once, decide once, and continue a supported source."""
    approval = ApprovalRequest.objects.select_for_update().select_related("requested_by").get(
        tenant=tenant, pk=approval_id,
    )
    if approval.status != ApprovalRequest.STATUS_PENDING:
        raise ValidationError({"detail": "This approval request has already been decided."})
    if approval.requested_by_id == actor.id:
        raise PermissionDenied("A requester cannot decide their own approval request.")
    rule = ApprovalRule.objects.filter(
        tenant=tenant, module=approval.module, action=approval.action, is_active=True,
    ).first()
    if rule is None:
        raise ValidationError({"detail": "The governing approval rule is no longer active."})
    if not _actor_is_allowed_approver(actor=actor, tenant=tenant, rule=rule):
        raise PermissionDenied("Your active tenant role cannot decide this approval request.")
    if decision not in {ApprovalRequest.STATUS_APPROVED, ApprovalRequest.STATUS_REJECTED}:
        raise ValidationError({"decision": "Use approved or rejected."})

    before = snapshot(approval, fields=["status", "reviewed_by", "reviewed_at", "note"])
    approval.status = decision
    approval.reviewed_by = actor
    approval.reviewed_at = timezone.now()
    approval.note = note.strip()
    approval.save(update_fields=["status", "reviewed_by", "reviewed_at", "note"])
    source = _continue_supported_source(approval) if decision == ApprovalRequest.STATUS_APPROVED else None
    record(
        tenant=tenant,
        actor=actor,
        action="update",
        instance=approval,
        request=request,
        summary=f"{decision.title()} approval for {approval.reference_str or approval.module}",
        icon="check-circle-2" if decision == ApprovalRequest.STATUS_APPROVED else "circle-x",
        before=before,
        after=snapshot(approval, fields=["status", "reviewed_by", "reviewed_at", "note"]),
    )
    create_notification(
        tenant=tenant,
        user=approval.requested_by,
        event_key=f"approval:{approval.pk}:{decision}:{approval.requested_by_id}",
        notification_type=(InAppNotification.TYPE_SUCCESS if decision == ApprovalRequest.STATUS_APPROVED else InAppNotification.TYPE_ERROR),
        title=f"Approval {decision}",
        message=f"{approval.reference_str or approval.module} was {decision}.",
        link="/operations?tab=approvals",
    )
    return approval, source
