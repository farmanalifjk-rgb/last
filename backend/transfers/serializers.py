from rest_framework import serializers

from enterprise.models import Warehouse
from pos.models import Product

from .models import BinReplenishmentTask, PutAwayRule, PutAwayTask, StockTransfer, StockTransferItem


class TenantTransferSerializer(serializers.ModelSerializer):
    def _tenant(self): return self.context["request"].tenant
    def _require_tenant(self, value, field):
        if value is not None and getattr(value, "tenant_id", None) != self._tenant().id:
            raise serializers.ValidationError({field: "The selected record does not belong to the active tenant."})
        return value


class StockTransferItemSerializer(TenantTransferSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    class Meta:
        model = StockTransferItem
        fields = ["id", "tenant", "transfer", "product", "quantity", "received_quantity", "product_name", "product_sku"]
        read_only_fields = ["id", "tenant", "received_quantity"]

    def validate_product(self, value): return self._require_tenant(value, "product")


class StockTransferSerializer(TenantTransferSerializer):
    items = StockTransferItemSerializer(many=True, read_only=True)
    source_name = serializers.CharField(source="source_warehouse.name", read_only=True)
    destination_name = serializers.CharField(source="destination_warehouse.name", read_only=True)
    class Meta:
        model = StockTransfer
        fields = ["id", "tenant", "transfer_number", "source_warehouse", "source_name", "destination_warehouse", "destination_name", "status", "shipped_at", "received_at", "note", "created_by", "created_at", "items"]
        read_only_fields = ["id", "tenant", "transfer_number", "status", "shipped_at", "received_at", "created_by", "created_at", "items"]


class TransferCreateSerializer(serializers.Serializer):
    source_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    destination_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    note = serializers.CharField(required=False, allow_blank=True)
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)

    def validate(self, attrs):
        tenant = self.context["request"].tenant
        if attrs["source_warehouse"].tenant_id != tenant.id or attrs["destination_warehouse"].tenant_id != tenant.id:
            raise serializers.ValidationError("Transfer warehouses must belong to the active tenant.")
        if attrs["source_warehouse"].id == attrs["destination_warehouse"].id:
            raise serializers.ValidationError("Source and destination warehouses must differ.")
        normalised = []
        for row in attrs["items"]:
            product = Product.objects.filter(tenant=tenant, pk=row.get("product_id")).first()
            if product is None: raise serializers.ValidationError({"items": "Every transfer product must belong to the active tenant."})
            try: quantity = float(row.get("quantity"))
            except (TypeError, ValueError): raise serializers.ValidationError({"items": "Every transfer quantity must be numeric."})
            if quantity <= 0: raise serializers.ValidationError({"items": "Transfer quantities must be positive."})
            normalised.append({"product_id": product.id, "quantity": row["quantity"]})
        attrs["items"] = normalised
        return attrs


class PutAwayRuleSerializer(TenantTransferSerializer):
    class Meta:
        model = PutAwayRule
        fields = ["id", "tenant", "warehouse", "strategy", "category", "abc_class", "target_bin", "is_active", "created_at"]
        read_only_fields = ["id", "tenant", "created_at"]


class PutAwayTaskSerializer(TenantTransferSerializer):
    class Meta:
        model = PutAwayTask
        fields = ["id","tenant","warehouse","product","quantity","suggested_bin","status","reference","created_at","completed_at","completed_by"]
        read_only_fields = ["id", "tenant", "created_at", "completed_at", "completed_by"]


class BinReplenishmentTaskSerializer(TenantTransferSerializer):
    class Meta:
        model = BinReplenishmentTask
        fields = ["id","tenant","warehouse","product","from_bin","to_bin","quantity","status","created_at","completed_at"]
        read_only_fields = ["id", "tenant", "created_at", "completed_at"]
