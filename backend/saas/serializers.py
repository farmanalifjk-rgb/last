from rest_framework import serializers
from .models import (
    Tenant, TenantMembership, SubscriptionPlan, Subscription,
    Invoice, InvoiceItem, TenantUsage,
)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ["id","name","slug","description","price","currency","interval","trial_days","max_users","max_stores","max_warehouses","max_products","storage_mb","features","is_public","is_active","stripe_price_id","sort_order"]


class TenantMembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = TenantMembership
        fields = ["id", "tenant", "user", "user_email", "user_name", "role", "is_active_in_tenant", "joined_at"]

    def get_user_email(self, obj):
        return obj.user.email if obj.user_id else None

    def get_user_name(self, obj):
        return getattr(obj.user, "username", "") if obj.user_id else None


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "owner", "status", "is_active", "trial_ends_at", "suspended_reason", "created_at", "updated_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    class Meta:
        model = Subscription
        fields = ["id", "tenant", "plan", "status", "stripe_customer_id", "stripe_subscription_id", "current_period_start", "current_period_end", "cancel_at_period_end", "started_at", "ended_at", "created_at", "updated_at"]


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ["id","invoice","description","quantity","unit_amount","total"]


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    class Meta:
        model = Invoice
        fields = ["id","tenant","subscription","subscription_request","manual_payment","number","status","amount_due","amount_paid","currency","issued_at","due_at","paid_at","period_start","period_end","finalized_at","stripe_invoice_id","pdf_url","created_at","items"]


class TenantUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantUsage
        fields = ["id","tenant","metric","value","captured_at"]


class CreateTenantSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(max_length=80)
    plan_slug = serializers.SlugField(max_length=80)


class SwitchTenantSerializer(serializers.Serializer):
    tenant_id = serializers.IntegerField()