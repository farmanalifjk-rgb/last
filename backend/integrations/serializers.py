from rest_framework import serializers
from .models import Integration, SyncLog, SyncMapping


class IntegrationSerializer(serializers.ModelSerializer):
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    # Never return provider credentials or refresh tokens after they have been submitted.
    config = serializers.JSONField(write_only=True, required=False)

    def validate_kind(self, value):
        # QuickBooks has only a stub adapter and Xero has no adapter at all.
        # Existing configurations remain readable for operator review, but new
        # or updated configurations cannot claim an unsupported capability.
        if value in {Integration.KIND_QUICKBOOKS, Integration.KIND_XERO}:
            raise serializers.ValidationError(f"{value} is not implemented and cannot be activated.")
        return value

    def validate(self, attrs):
        if attrs.get("is_active") is True:
            kind = attrs.get("kind", getattr(self.instance, "kind", None))
            if kind in {Integration.KIND_QUICKBOOKS, Integration.KIND_XERO}:
                raise serializers.ValidationError({"is_active": "Unsupported integrations must remain inactive."})
        return attrs

    class Meta:
        model = Integration
        fields = ["id", "tenant", "kind", "name", "is_active", "last_synced_at", "created_at", "config"]


class SyncLogSerializer(serializers.ModelSerializer):
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = SyncLog
        fields = ["id","tenant","integration","direction","entity_type","entity_id","remote_id","status","message","payload","created_at"]


class SyncMappingSerializer(serializers.ModelSerializer):
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = SyncMapping
        fields = ["id","tenant","integration","entity_type","local_id","remote_id","last_hash","updated_at"]
