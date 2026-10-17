from decimal import Decimal

from rest_framework import serializers

from .models import ManualPaymentMethod, ManualSubscriptionPayment, SubscriptionRequest


def _money(value):
    return str(value) if value is not None else None


class ManualPaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManualPaymentMethod
        fields = ["id", "code", "label", "reference_required", "is_active", "sort_order", "created_at", "updated_at"]


class SubscriptionRequestSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    invoice_id = serializers.IntegerField(source="invoice.id", read_only=True)
    manual_payment_id = serializers.IntegerField(source="manual_payment.id", read_only=True)
    expected_amount = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionRequest
        fields = [
            "id", "plan", "plan_name", "expected_amount", "expected_currency",
            "period_start", "period_end", "status", "requested_by", "requested_at",
            "activated_by", "activated_at", "invoice_id", "manual_payment_id",
        ]
        read_only_fields = fields

    def get_expected_amount(self, obj):
        return _money(obj.expected_amount)


class ManualSubscriptionPaymentSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    payment_method_code = serializers.CharField(source="payment_method.code", read_only=True)
    payment_method_label = serializers.CharField(source="payment_method.label", read_only=True)
    expected_amount = serializers.SerializerMethodField()
    expected_currency = serializers.CharField(source="subscription_request.expected_currency", read_only=True)
    request_status = serializers.CharField(source="subscription_request.status", read_only=True)
    paid_amount = serializers.SerializerMethodField()
    submitted_by_name = serializers.SerializerMethodField()
    verified_by_name = serializers.SerializerMethodField()
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = ManualSubscriptionPayment
        fields = [
            "id", "tenant", "tenant_name", "subscription_request", "request_status", "plan", "plan_name",
            "expected_amount", "expected_currency", "payment_method", "payment_method_code", "payment_method_label",
            "paid_amount", "paid_currency", "payment_reference", "payment_date", "proof_reference", "notes",
            "status", "submitted_by", "submitted_by_name", "submitted_at", "verified_by", "verified_by_name",
            "verified_at", "rejection_reason", "review_note",
        ]
        read_only_fields = fields

    def get_expected_amount(self, obj):
        return _money(obj.subscription_request.expected_amount)

    def get_paid_amount(self, obj):
        return _money(obj.paid_amount)

    def get_submitted_by_name(self, obj):
        return getattr(obj.submitted_by, "username", "") if obj.submitted_by_id else ""

    def get_verified_by_name(self, obj):
        return getattr(obj.verified_by, "username", "") if obj.verified_by_id else ""


class SubscriptionRequestCreateSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(min_value=1)


class ManualPaymentSubmissionSerializer(serializers.Serializer):
    payment_method_id = serializers.IntegerField(min_value=1)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    paid_currency = serializers.CharField(max_length=10)
    payment_date = serializers.DateField()
    payment_reference = serializers.CharField(max_length=160, required=False, allow_blank=True)
    proof_reference = serializers.CharField(max_length=240, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class ManualPaymentDecisionSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    review_note = serializers.CharField(max_length=2000, required=False, allow_blank=True)
