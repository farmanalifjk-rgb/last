from rest_framework import serializers
from .models import (ParkedOrder, Layaway, LayawayPayment, SplitBill, SplitBillShare,
                     ExchangeOrder, OfflineSyncQueue, ReceiptTemplate, CashDrawerEvent)


class ParkedOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParkedOrder
        fields = ["id","tenant","session","label","customer","payload","status","parked_by","parked_at","resumed_at"]


class LayawayPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LayawayPayment
        fields = ["id", "tenant", "layaway", "amount", "payment_method", "paid_at"]


class LayawaySerializer(serializers.ModelSerializer):
    installments = LayawayPaymentSerializer(many=True, read_only=True)
    class Meta:
        model = Layaway
        fields = ["id","tenant","order","customer","total_amount","deposit_amount","balance_due","due_date","status","created_at","updated_at"]


class SplitBillShareSerializer(serializers.ModelSerializer):
    class Meta:
        model = SplitBillShare
        fields = ["id","tenant","split","amount","is_paid","payment_method"]


class SplitBillSerializer(serializers.ModelSerializer):
    shares = SplitBillShareSerializer(many=True, read_only=True)
    class Meta:
        model = SplitBill
        fields = ["id","tenant","order","total_amount","share_count","created_at"]


class ExchangeOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeOrder
        fields = ["id","tenant","original_order","returned_items","replacement_items","net_amount","created_at"]


class OfflineSyncQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfflineSyncQueue
        fields = ["id","tenant","device_id","payload","status","error","created_at","synced_at"]


class ReceiptTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptTemplate
        fields = ["id","tenant","name","is_default","header_text","footer_text","layout_config","created_at"]
        ref_name = "PosCoreReceiptTemplate"


class CashDrawerEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashDrawerEvent
        fields = ["id","tenant","session","kind","amount","note","created_by","created_at"]