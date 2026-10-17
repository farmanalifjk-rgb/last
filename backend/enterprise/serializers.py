from rest_framework import serializers

from .models import Warehouse, WarehouseStock


class WarehouseSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Warehouse
        fields = [
            "id",
            "tenant",
            "store",
            "store_name",
            "code",
            "name",
            "address",
            "is_active",
            "created_at",
        ]


class WarehouseStockSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = WarehouseStock
        fields = [
            "id",
            "tenant",
            "warehouse",
            "product",
            "product_name",
            "quantity",
            "reorder_point",
            "bin_location",
            "updated_at",
        ]