import json

from django.db import transaction

from .models import AuditEvent, ActivityFeed


def _clean(value):
    """Make a value JSON-safe (handles Decimal, datetime, model instances)."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__dict__") and hasattr(value, "_meta"):
        return str(value)
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def snapshot(instance, fields=None):
    if instance is None:
        return {}
    out = {}
    meta = instance._meta
    for field in (fields or [field.name for field in meta.fields]):
        try:
            out[field] = _clean(getattr(instance, field))
        except Exception:
            out[field] = None
    return out


@transaction.atomic
def record(*, actor=None, action, instance=None, entity_type=None, entity_id=None,
           entity_label="", before=None, after=None, request=None, summary="", icon="", tenant=None):
    """Write a tenant-owned audit event without inferring financial secrets from a model snapshot."""
    if instance is not None:
        entity_type = entity_type or instance._meta.model_name
        entity_id = entity_id or str(getattr(instance, "id", ""))
        entity_label = entity_label or str(instance)
        tenant = tenant or getattr(instance, "tenant", None)
    tenant = tenant or getattr(request, "tenant", None)
    if tenant is None:
        raise ValueError("A tenant is required to record an audit event.")
    actor_name = getattr(actor, "username", "") or getattr(actor, "email", "") or ""
    ip = None
    user_agent = ""
    if request is not None:
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]
    AuditEvent.objects.create(
        tenant=tenant, actor=actor, actor_name=actor_name, action=action,
        entity_type=entity_type or "", entity_id=entity_id or "", entity_label=entity_label,
        before=before or {}, after=after or {}, ip_address=ip, user_agent=user_agent,
    )
    if summary:
        ActivityFeed.objects.create(
            tenant=tenant, actor_name=actor_name, summary=summary, icon=icon,
            entity_type=entity_type or "", entity_id=entity_id or "", link="",
        )
