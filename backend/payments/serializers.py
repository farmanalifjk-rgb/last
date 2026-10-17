from decimal import Decimal

from rest_framework import serializers

from .models import GiftCard, GiftCardTransaction, PaymentReconciliation, ProviderPaymentOperation, ProviderRefundOperation, ReconciliationLine, RefundCreditNote, RefundSettlement, StoreCredit, StoreCreditTransaction, TenderedPayment


def masked_code(value):
    value = value or ""
    return f"••••{value[-4:]}" if len(value) > 4 else "••••"


class GiftCardTransactionSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True, default=None)

    class Meta:
        model = GiftCardTransaction
        fields = ["id", "tenant", "gift_card", "kind", "amount", "order", "order_number", "note", "created_at", "created_by"]


class GiftCardSerializer(serializers.ModelSerializer):
    code_masked = serializers.SerializerMethodField()
    customer_id = serializers.IntegerField(source="issued_to_id", read_only=True)
    customer_name = serializers.CharField(source="issued_to.name", read_only=True, default=None)
    transactions = GiftCardTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = GiftCard
        fields = ["id", "tenant", "code", "code_masked", "initial_balance", "balance", "currency", "is_active", "expires_at", "issued_to", "issued_at", "created_by", "customer_id", "customer_name", "transactions"]

    def get_code_masked(self, obj):
        return masked_code(obj.code)


class GiftCardIssueSerializer(serializers.Serializer):
    initial_balance = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    expires_at = serializers.DateField(required=False, allow_null=True)


class AmountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class StoreCreditTransactionSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True, default=None)

    class Meta:
        model = StoreCreditTransaction
        fields = ["id", "kind", "amount", "order_number", "note", "created_at"]


class StoreCreditSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField(read_only=True)
    transactions = StoreCreditTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = StoreCredit
        fields = ["id", "tenant", "customer", "customer_id", "balance", "currency", "updated_at", "created_at", "transactions"]


class StoreCreditIssueSerializer(AmountSerializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class PaymentRegisterSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    order_id = serializers.IntegerField(read_only=True)
    customer_id = serializers.IntegerField(source="order.customer_id", read_only=True, default=None)
    customer_name = serializers.CharField(source="order.customer.name", read_only=True, default=None)
    settlement_id = serializers.IntegerField(read_only=True, allow_null=True)
    status = serializers.SerializerMethodField()
    reference_masked = serializers.SerializerMethodField()

    class Meta:
        model = TenderedPayment
        fields = ["id", "tenant", "settlement", "settlement_id", "order", "order_number", "order_id", "tender_type", "amount", "currency", "reference", "reference_masked", "is_settled", "status", "created_at", "created_by", "customer_id", "customer_name"]

    def get_status(self, obj):
        return "settled" if obj.is_settled else "pending"

    def get_reference_masked(self, obj):
        if not obj.reference:
            return ""
        if obj.tender_type == TenderedPayment.TENDER_GIFT_CARD:
            return masked_code(obj.reference)
        return obj.reference[-4:] if len(obj.reference) > 4 else obj.reference


class ReconciliationLineInputSerializer(serializers.Serializer):
    tender_type = serializers.ChoiceField(choices=[choice for choice, _label in TenderedPayment.TENDER_CHOICES])
    counted_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ReconciliationCreateSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    lines = ReconciliationLineInputSerializer(many=True)


class ReconciliationLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationLine
        fields = ["id", "tenant", "reconciliation", "tender_type", "expected_amount", "counted_amount", "variance", "note"]


class PaymentReconciliationSerializer(serializers.ModelSerializer):
    session_id = serializers.IntegerField(read_only=True)
    lines = ReconciliationLineSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentReconciliation
        fields = ["id", "session_id", "expected_total", "counted_total", "variance", "status", "note", "created_at", "closed_at", "lines"]


class RefundSettlementSerializer(serializers.ModelSerializer):
    refund_id = serializers.IntegerField(read_only=True)
    order_id = serializers.IntegerField(source="refund.order_id", read_only=True)
    order_number = serializers.CharField(source="refund.order.order_number", read_only=True)

    class Meta:
        model = RefundSettlement
        fields = ["id", "tenant", "refund", "refund_id", "order_id", "order_number", "original_settlement", "amount", "cash_amount", "currency", "method", "status", "reference", "created_at", "created_by"]


class RefundCreditNoteRequestSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()


class RefundCreditNoteSerializer(serializers.ModelSerializer):
    refund_id = serializers.IntegerField(read_only=True)
    customer_id = serializers.IntegerField(read_only=True, allow_null=True)
    code_masked = serializers.SerializerMethodField()

    class Meta:
        model = RefundCreditNote
        fields = ["id", "tenant", "refund", "refund_id", "customer", "customer_id", "amount", "code", "code_masked", "is_redeemed", "created_at"]

    def get_code_masked(self, obj):
        return masked_code(obj.code)


class ProviderCheckoutRequestSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=Decimal("0"), default=Decimal("0"))


class ProviderPaymentOperationSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    reference_masked = serializers.SerializerMethodField()

    class Meta:
        model = ProviderPaymentOperation
        fields = [
            "id", "order_id", "order_number", "provider", "reference_masked",
            "provider_status", "status", "amount", "currency", "failure_code",
            "failure_reason", "created_at", "updated_at", "verified_at",
        ]

    def get_reference_masked(self, obj):
        return obj.provider_payment_id[-12:] if obj.provider_payment_id else ""


class ProviderRefundOperationSerializer(serializers.ModelSerializer):
    refund_id = serializers.IntegerField(read_only=True)
    order_id = serializers.IntegerField(source="refund.order_id", read_only=True)
    reference_masked = serializers.SerializerMethodField()

    class Meta:
        model = ProviderRefundOperation
        fields = [
            "id", "refund_id", "order_id", "provider", "reference_masked",
            "provider_status", "status", "amount", "currency", "failure_code",
            "failure_reason", "created_at", "updated_at", "verified_at",
        ]

    def get_reference_masked(self, obj):
        return obj.provider_refund_id[-12:] if obj.provider_refund_id else ""
