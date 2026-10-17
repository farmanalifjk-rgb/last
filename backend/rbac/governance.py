"""Tenant-safe role governance built on the existing RBAC and audit systems."""
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from audit.recorder import record
from auth_app.models import AuthToken
from operations.models import InAppNotification
from operations.services import create_notification
from saas.models import TenantMembership

from .checker import user_permissions
from .models import Permission, Role, UserRole


User = get_user_model()


def active_membership(*, user, tenant):
    return TenantMembership.objects.filter(
        tenant=tenant, user=user, is_active_in_tenant=True
    ).first()


def tenant_membership(*, user, tenant):
    """A member can be governed even while they currently work in another tenant."""
    return TenantMembership.objects.filter(tenant=tenant, user=user).first()


def require_tenant_governance(*, actor, tenant):
    membership = active_membership(user=actor, tenant=tenant)
    if actor.is_superuser:
        return membership
    if membership is None or membership.role not in {
        TenantMembership.ROLE_OWNER,
        TenantMembership.ROLE_ADMIN,
    }:
        raise PermissionDenied("Tenant owner or administrator authority is required for role governance.")
    return membership


def tenant_roles(*, tenant, include_inactive=False):
    queryset = Role.objects.filter(scope=Permission.SCOPE_TENANT).filter(
        tenant=tenant
    ) | Role.objects.filter(scope=Permission.SCOPE_TENANT, tenant__isnull=True, is_system=True)
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset.distinct().prefetch_related("permissions__module")


def tenant_permissions():
    return Permission.objects.filter(scope=Permission.SCOPE_TENANT).select_related("module")


def _assert_role_belongs_to_tenant(*, role, tenant):
    if role.scope != Permission.SCOPE_TENANT:
        raise ValidationError({"role": "Platform roles cannot be managed from a tenant."})
    if role.tenant_id not in {None, tenant.id}:
        raise ValidationError({"role": "The role does not belong to the active tenant."})


def _resolve_permissions(*, permission_ids, tenant, confirm_sensitive):
    permissions = list(Permission.objects.filter(id__in=permission_ids).select_related("module"))
    if len(permissions) != len(set(permission_ids)):
        raise ValidationError({"permission_ids": "One or more permissions do not exist."})
    invalid = [f"{item.module.key}.{item.action}" for item in permissions if item.scope != Permission.SCOPE_TENANT]
    if invalid:
        raise ValidationError({"permission_ids": f"Platform permissions cannot be used in a tenant role: {', '.join(invalid)}."})
    sensitive = [f"{item.module.key}.{item.action}" for item in permissions if item.is_sensitive]
    if sensitive and not confirm_sensitive:
        raise ValidationError({"confirm_sensitive": f"Explicit confirmation is required for sensitive permissions: {', '.join(sensitive)}."})
    return permissions, sensitive


@transaction.atomic
def create_tenant_role(*, actor, tenant, key, label, description, permission_ids, confirm_sensitive, request=None):
    require_tenant_governance(actor=actor, tenant=tenant)
    normalized = str(key or "").strip().lower().replace(" ", "-")
    if not normalized or normalized.startswith("builtin-"):
        raise ValidationError({"key": "Provide a tenant-local role key that does not use the reserved builtin- prefix."})
    scoped_key = f"tenant-{tenant.id}-{normalized}"
    if Role.objects.filter(key=scoped_key).exists():
        raise ValidationError({"key": "A role with this key already exists in the active tenant."})
    permissions, sensitive = _resolve_permissions(
        permission_ids=permission_ids, tenant=tenant, confirm_sensitive=confirm_sensitive
    )
    role = Role.objects.create(
        key=scoped_key,
        label=label,
        description=description or "",
        scope=Permission.SCOPE_TENANT,
        tenant=tenant,
        is_system=False,
        is_active=True,
    )
    role.permissions.set(permissions)
    record(
        tenant=tenant, actor=actor, action="rbac.role.created", entity_type="Role", entity_id=str(role.id),
        entity_label=role.label, after={"key": role.key, "permissions": sorted(f"{p.module.key}.{p.action}" for p in permissions), "sensitive": sensitive},
        request=request, summary=f"Created tenant role {role.label}", icon="shield-check",
    )
    return role


@transaction.atomic
def update_tenant_role(*, actor, tenant, role, label, description, permission_ids, confirm_sensitive, request=None):
    require_tenant_governance(actor=actor, tenant=tenant)
    _assert_role_belongs_to_tenant(role=role, tenant=tenant)
    if role.is_system:
        raise PermissionDenied("Built-in roles are immutable. Create a tenant-local custom role instead.")
    before = {"label": role.label, "description": role.description, "permissions": sorted(f"{p.module.key}.{p.action}" for p in role.permissions.select_related("module"))}
    permissions, sensitive = _resolve_permissions(
        permission_ids=permission_ids, tenant=tenant, confirm_sensitive=confirm_sensitive
    )
    role.label = label
    role.description = description or ""
    role.save(update_fields=["label", "description"])
    role.permissions.set(permissions)
    record(
        tenant=tenant, actor=actor, action="rbac.role.updated", entity_type="Role", entity_id=str(role.id),
        entity_label=role.label, before=before,
        after={"label": role.label, "description": role.description, "permissions": sorted(f"{p.module.key}.{p.action}" for p in permissions), "sensitive": sensitive},
        request=request, summary=f"Updated tenant role {role.label}", icon="shield-check",
    )
    return role


@transaction.atomic
def deactivate_tenant_role(*, actor, tenant, role, request=None):
    require_tenant_governance(actor=actor, tenant=tenant)
    _assert_role_belongs_to_tenant(role=role, tenant=tenant)
    if role.is_system:
        raise PermissionDenied("Built-in roles cannot be deactivated.")
    role.is_active = False
    role.save(update_fields=["is_active"])
    assignments = list(UserRole.objects.select_for_update().filter(tenant=tenant, role=role, is_active=True))
    UserRole.objects.filter(id__in=[assignment.id for assignment in assignments]).update(is_active=False)
    AuthToken.objects.filter(user_id__in=[assignment.user_id for assignment in assignments], is_revoked=False).update(is_revoked=True)
    record(
        tenant=tenant, actor=actor, action="rbac.role.deactivated", entity_type="Role", entity_id=str(role.id),
        entity_label=role.label, before={"is_active": True}, after={"is_active": False, "assignment_count": len(assignments)},
        request=request, summary=f"Deactivated tenant role {role.label}", icon="shield-off",
    )


@transaction.atomic
def assign_tenant_role(*, actor, tenant, target_user, role, branch=None, request=None):
    require_tenant_governance(actor=actor, tenant=tenant)
    if actor.id == target_user.id:
        raise PermissionDenied("Users cannot assign roles to themselves.")
    _assert_role_belongs_to_tenant(role=role, tenant=tenant)
    if not role.is_active:
        raise ValidationError({"role": "The selected role is inactive."})
    if tenant_membership(user=target_user, tenant=tenant) is None:
        raise ValidationError({"user": "The target user is not a member of this tenant."})
    if branch and branch.tenant_id != tenant.id:
        raise ValidationError({"branch": "The branch does not belong to the active tenant."})
    assignment, created = UserRole.objects.get_or_create(
        user=target_user, role=role, tenant=tenant, branch=branch,
        defaults={"assigned_by": actor, "is_active": True},
    )
    changed = created
    if not created and not assignment.is_active:
        assignment.is_active = True
        assignment.assigned_by = actor
        assignment.save(update_fields=["is_active", "assigned_by"])
        changed = True
    if changed:
        role_permissions = list(role.permissions.select_related("module"))
        sensitive = [f"{p.module.key}.{p.action}" for p in role_permissions if p.is_sensitive]
        record(
            tenant=tenant, actor=actor, action="rbac.role.assigned", entity_type="UserRole", entity_id=str(assignment.id),
            entity_label=f"{target_user.username} — {role.label}",
            after={"user_id": target_user.id, "role": role.key, "branch_id": getattr(branch, "id", None), "sensitive": sensitive},
            request=request, summary=f"Assigned {role.label} to {target_user.username}", icon="user-check",
        )
        create_notification(
            tenant=tenant, user=target_user, event_key=f"rbac:{assignment.id}:assigned",
            notification_type=InAppNotification.TYPE_WARNING if sensitive else InAppNotification.TYPE_INFO,
            title="Role assigned", message=f"You were assigned the {role.label} role.", link="/admin",
        )
        AuthToken.objects.filter(user=target_user, is_revoked=False).update(is_revoked=True)
    return assignment


@transaction.atomic
def remove_tenant_role_assignment(*, actor, tenant, assignment, request=None):
    require_tenant_governance(actor=actor, tenant=tenant)
    if assignment.tenant_id != tenant.id:
        raise PermissionDenied("The role assignment does not belong to the active tenant.")
    if assignment.user_id == actor.id:
        raise PermissionDenied("Users cannot remove their own role assignment.")
    assignment.is_active = False
    assignment.save(update_fields=["is_active"])
    AuthToken.objects.filter(user_id=assignment.user_id, is_revoked=False).update(is_revoked=True)
    record(
        tenant=tenant, actor=actor, action="rbac.role.removed", entity_type="UserRole", entity_id=str(assignment.id),
        entity_label=f"{assignment.user.username} — {assignment.role.label}", before={"is_active": True}, after={"is_active": False},
        request=request, summary=f"Removed {assignment.role.label} from {assignment.user.username}", icon="user-minus",
    )
    create_notification(
        tenant=tenant, user=assignment.user, event_key=f"rbac:{assignment.id}:removed",
        notification_type=InAppNotification.TYPE_WARNING, title="Role removed",
        message=f"Your {assignment.role.label} role was removed.", link="/admin",
    )


def effective_permissions(*, user, tenant):
    membership = tenant_membership(user=user, tenant=tenant)
    if membership is None:
        raise ValidationError({"user": "The selected user is not a tenant member."})
    if user.is_superuser or membership.role in {TenantMembership.ROLE_OWNER, TenantMembership.ROLE_ADMIN}:
        keys = {"*.*"}
    else:
        keys = user_permissions(user, tenant=tenant)
    assignments = UserRole.objects.filter(user=user, tenant=tenant, is_active=True, role__is_active=True).select_related("role").prefetch_related("role__permissions__module")
    return {
        "user": {"id": user.id, "username": user.username},
        "membership_role": membership.role,
        "roles": [{"id": row.role_id, "key": row.role.key, "label": row.role.label, "branch_id": row.branch_id} for row in assignments],
        "permissions": sorted(keys),
    }
