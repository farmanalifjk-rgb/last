"""Audit support for platform-global actions that intentionally have no tenant."""

from system.models import AuditLog


def record_platform_action(*, request, action, entity, entity_id="", description="", metadata=None):
    """Record platform administrative activity without fabricating tenant ownership."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    return AuditLog.objects.create(
        user=request.user if getattr(request.user, "is_authenticated", False) else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id or ""),
        description=description[:500],
        ip_address=ip_address or None,
        metadata={"scope": "platform", **(metadata or {})},
    )
