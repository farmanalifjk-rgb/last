from rest_framework import serializers

from .models import ActivityFeed, AuditEvent


SENSITIVE_KEY_PARTS = ("password", "token", "secret", "api_key", "authorization", "credential", "key")


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[redacted]" if any(part in key.lower() for part in SENSITIVE_KEY_PARTS) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:500]}…"
    return value


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(read_only=True)
    before = serializers.SerializerMethodField()
    after = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id", "actor", "actor_name", "action", "entity_type", "entity_id",
            "entity_label", "before", "after", "ip_address", "created_at",
        ]
        read_only_fields = fields

    def get_before(self, obj):
        return redact(obj.before)

    def get_after(self, obj):
        return redact(obj.after)


class ActivityFeedSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityFeed
        fields = ["id", "tenant", "actor_name", "summary", "icon", "entity_type", "entity_id", "link", "created_at"]
        read_only_fields = fields
