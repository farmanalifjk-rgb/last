from rest_framework import serializers

from enterprise.models import Warehouse, WarehouseStock
from pos.models import Product, StockMovement

from .models import ABCAnalysis, BinLocation, CycleCount, CycleCountLine, InventoryAgingSnapshot, ReorderRule, StockReservation


class TenantRelationSerializer(serializers.ModelSerializer):
    def _tenant(self):
        return self.context["request"].tenant

    def _require_tenant(self, value, field):
        if value is not None and getattr(value, "tenant_id", None) != self._tenant().id:
            raise serializers.ValidationError({field: "The selected record does not belong to the active tenant."})
        return value


class WarehouseSerializer(TenantRelationSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "tenant", "store", "code", "name", "address", "is_active", "created_at"]
        read_only_fields = ["id", "tenant", "created_at"]

    def validate_store(self, value):
        return self._require_tenant(value, "store")


class BinLocationSerializer(TenantRelationSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = BinLocation
        fields = ["id", "tenant", "warehouse", "warehouse_name", "zone", "aisle", "rack", "bin", "code", "is_active", "created_at"]
        read_only_fields = ["id", "tenant", "created_at"]

    def validate_warehouse(self, value):
        return self._require_tenant(value, "warehouse")


class WarehouseStockSerializer(TenantRelationSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    available_quantity = serializers.SerializerMethodField()

    class Meta:
        model = WarehouseStock
        fields = ["id", "tenant", "warehouse", "warehouse_name", "product", "product_name", "product_sku", "quantity", "reorder_point", "bin_location", "updated_at", "available_quantity"]
        read_only_fields = fields

    def get_available_quantity(self, obj):
        from .services import available_stock
        return str(available_stock(obj.tenant, obj.product, obj.warehouse))


class StockMovementSerializer(TenantRelationSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "tenant", "product", "product_name", "product_sku", "warehouse", "warehouse_name", "reference", "quantity", "movement_type", "previous_stock", "new_stock", "note", "created_at"]
        read_only_fields = fields


class StockReservationSerializer(TenantRelationSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = StockReservation
        fields = ["id", "tenant", "product", "product_name", "product_sku", "warehouse", "warehouse_name", "quantity", "status", "reserved_by", "reference", "expires_at", "created_at"]
        read_only_fields = ["id", "tenant", "status", "reserved_by", "created_at"]

    def validate_product(self, value):
        return self._require_tenant(value, "product")

    def validate_warehouse(self, value):
        return self._require_tenant(value, "warehouse")


class AdjustmentRequestSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all(), required=False, allow_null=True)
    new_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, required=False)
    adjustment_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, required=False)
    reason = serializers.CharField(max_length=255)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        tenant = self.context["request"].tenant
        if attrs["product"].tenant_id != tenant.id:
            raise serializers.ValidationError({"product": "The product does not belong to the active tenant."})
        if attrs.get("warehouse") and attrs["warehouse"].tenant_id != tenant.id:
            raise serializers.ValidationError({"warehouse": "The warehouse does not belong to the active tenant."})
        if attrs.get("new_quantity") is None and attrs.get("adjustment_quantity") is None:
            raise serializers.ValidationError("Provide a new quantity or adjustment quantity.")
        if attrs.get("new_quantity") is not None and attrs.get("adjustment_quantity") is not None:
            raise serializers.ValidationError("Provide only one adjustment mode.")
        return attrs


class CycleCountLineSerializer(TenantRelationSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = CycleCountLine
        fields = ["id", "tenant", "count", "product", "product_name", "expected_quantity", "counted_quantity", "variance", "note"]
        read_only_fields = ["id", "tenant", "count", "expected_quantity", "variance"]


class CycleCountSerializer(TenantRelationSerializer):
    lines = CycleCountLineSerializer(many=True, read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = CycleCount
        fields = ["id", "tenant", "warehouse", "warehouse_name", "reference", "status", "started_by", "created_at", "completed_at", "lines"]
        read_only_fields = ["id", "tenant", "status", "started_by", "created_at", "completed_at", "lines"]

    def validate_warehouse(self, value):
        return self._require_tenant(value, "warehouse")


class ReorderRuleSerializer(TenantRelationSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = ReorderRule
        fields = ["id", "tenant", "product", "product_name", "warehouse", "warehouse_name", "reorder_point", "target_stock", "supplier", "supplier_name", "auto_generate_po", "is_active", "created_at"]
        read_only_fields = ["id", "tenant", "created_at"]

    def validate_product(self, value):
        return self._require_tenant(value, "product")

    def validate_warehouse(self, value):
        return self._require_tenant(value, "warehouse")

    def validate_supplier(self, value):
        return self._require_tenant(value, "supplier")


class ABCAnalysisSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = ABCAnalysis
        fields = ["id", "tenant", "product", "product_name", "product_sku", "annual_value", "cumulative_share", "abc_class", "computed_at"]
        read_only_fields = fields


class InventoryAgingSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = InventoryAgingSnapshot
        fields = ["id", "tenant", "product", "product_name", "product_sku", "bucket", "quantity", "captured_at"]
        read_only_fields = fields
