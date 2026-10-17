from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver

from .tenant_context import get_current_tenant


@receiver(pre_save)
def enforce_tenant_ownership(sender, instance, raw=False, **kwargs):
    if raw or not hasattr(instance, "_meta"):
        return
    try:
        field = instance._meta.get_field("tenant")
    except Exception:
        return
    if field.model is not sender:
        return
    if instance._meta.app_label == "saas":
        return
    # SingletonModel subclasses (settings) may legitimately have tenant=None
    # for the global default row (pk=1).  Skip enforcement for them.
    from system.models import SingletonModel
    if issubclass(sender, SingletonModel):
        return
    if instance.tenant_id is None:
        # Platform governance is intentionally separate from tenant authority.
        # Only an explicitly platform-scoped RBAC role or an assignment of one
        # may be tenant-null; all tenant roles, custom roles, permissions, and
        # business records continue through the normal bound-tenant path.
        # Role definitions are catalog/template records. Their assignments—not
        # the definition itself—carry tenant scope, so a definition may remain
        # tenant-null without granting a user cross-tenant access.
        if instance._meta.label_lower == "rbac.role":
            return
        if instance._meta.label_lower == "rbac.userrole":
            # Resolve scope via role_id FK in case the cached relation is
            # not yet populated on the pre_save instance.
            _role_scope = getattr(getattr(instance, "role", None), "scope", None)
            if _role_scope is None and instance.role_id is not None:
                from rbac.models import Role
                _role_scope = Role.objects.filter(pk=instance.role_id).values_list("scope", flat=True).first()
            if _role_scope == "platform":
                return
        if instance._meta.label_lower == "rbac.userrole":
            # Older direct test/setup callers omitted a tenant. Preserve only
            # the unambiguous one-membership case; a multi-tenant user must be
            # assigned through the governance API with an explicit tenant.
            from saas.models import TenantMembership
            memberships = list(TenantMembership.objects.filter(user_id=instance.user_id).values_list("tenant_id", flat=True)[:2])
            if len(memberships) == 1:
                instance.tenant_id = memberships[0]
                return
            raise ValidationError(
                "Tenant-scoped role assignments require an explicit tenant unless the user has exactly one membership."
            )
        # A verified provider delivery can legitimately precede a local tenant
        # match. The webhook inbox therefore permits only this explicit model to
        # remain tenant-null for a signed, ignored/unmatched event. Matched
        # events are bound atomically to their owning operation by the payment
        # provider service before persistence.
        if instance._meta.label_lower == "payments.providerwebhookevent":
            return
        tenant = get_current_tenant()
        if tenant is None:
            raise ValidationError(
                f"{sender.__name__} requires an explicit tenant or an active tenant context."
            )
        instance.tenant_id = tenant.pk
