from rest_framework import serializers
from .models import AlertRule, Notification, NotificationDigest


class AlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertRule
        fields = ["id","tenant","kind","is_active","channel","low_stock_threshold","expiry_days","email_recipients","created_at"]
        # The tenant comes from the request (perform_create); it must never be
        # client-writable or a PATCH could move a rule into another tenant.
        read_only_fields = ["tenant", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "tenant", "rule", "kind", "title", "body", "severity", "target_user", "is_read", "is_sent_email", "link", "created_at"]


class NotificationDigestSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationDigest
        fields = ["id","tenant","day","fired_count","email_count","summary","created_at"]