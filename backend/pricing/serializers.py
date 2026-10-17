from rest_framework import serializers

from .models import BuyXGetY, CustomerGroupPrice, PriceList, PriceListItem, TimeBasedPrice, VolumeTier


class CustomerGroupOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    is_active = serializers.BooleanField(read_only=True)


class TenantPricingRelationSerializer(serializers.ModelSerializer):
    def _tenant_record(self, value, field):
        tenant = self.context["request"].tenant
        if value is not None and getattr(value, "tenant_id", None) != tenant.id:
            raise serializers.ValidationError({field: "The selected record does not belong to the active tenant."})
        return value


class PriceListSerializer(TenantPricingRelationSerializer):
    class Meta:
        model = PriceList
        fields = ["id","tenant","name","currency","is_default","is_active","valid_from","valid_to","created_at"]
        read_only_fields = ["tenant", "created_at"]

    def validate(self, attrs):
        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_to = attrs.get("valid_to", getattr(self.instance, "valid_to", None))
        if valid_from and valid_to and valid_to < valid_from:
            raise serializers.ValidationError({"valid_to": "Valid to must be on or after valid from."})
        return attrs


class PriceListItemSerializer(TenantPricingRelationSerializer):
    price_list_name = serializers.CharField(source="price_list.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PriceListItem
        fields = ["id","tenant","price_list","price_list_name","product","product_name","variant","price","min_quantity","created_at"]
        read_only_fields = ["tenant", "price_list", "created_at"]

    def validate_product(self, value):
        return self._tenant_record(value, "product")

    def validate_variant(self, value):
        return self._tenant_record(value, "variant")

    def validate(self, attrs):
        product = attrs.get("product") or getattr(self.instance, "product", None)
        variant = attrs.get("variant") or getattr(self.instance, "variant", None)
        if variant and product and variant.product_id != product.id:
            raise serializers.ValidationError({"variant": "The selected variant does not belong to this product."})
        return attrs


class CustomerGroupPriceSerializer(TenantPricingRelationSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = CustomerGroupPrice
        fields = ["id","tenant","customer_group","product","product_name","price","created_at"]
        read_only_fields = ["tenant", "created_at"]

    def validate_product(self, value):
        return self._tenant_record(value, "product")

    def validate_customer_group(self, value):
        return self._tenant_record(value, "customer_group")


class VolumeTierSerializer(TenantPricingRelationSerializer):
    class Meta:
        model = VolumeTier
        fields = ["id","tenant","product","min_quantity","unit_price","created_at"]
        read_only_fields = ["tenant", "created_at"]

    def validate_product(self, value):
        return self._tenant_record(value, "product")


class TimeBasedPriceSerializer(TenantPricingRelationSerializer):
    class Meta:
        model = TimeBasedPrice
        fields = ["id","tenant","product","price","start_time","end_time","weekdays","valid_from","valid_to","is_active","created_at"]
        read_only_fields = ["tenant", "created_at"]

    def validate_product(self, value):
        return self._tenant_record(value, "product")


class BuyXGetYSerializer(TenantPricingRelationSerializer):
    class Meta:
        model = BuyXGetY
        fields = ["id","tenant","product","buy_quantity","get_quantity","get_product","get_percent_off","valid_from","valid_to","is_active","created_at"]
        read_only_fields = ["tenant", "created_at"]

    def validate_product(self, value):
        return self._tenant_record(value, "product")

    def validate_get_product(self, value):
        return self._tenant_record(value, "get_product")
