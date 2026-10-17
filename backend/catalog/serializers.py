from rest_framework import serializers

from pos.models import Brand, Product, Supplier, Variant, VariantValue
from .models import (
    Batch,
    BatchMovement,
    BundleComponent,
    ProductBundle,
    ProductMedia,
    ProductVariant,
    ProductVariantAttribute,
    SerialNumber,
)


class ProductVariantAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariantAttribute
        fields = ["id", "tenant", "variant", "name", "value"]
        read_only_fields = ["id"]


class ProductVariantSerializer(serializers.ModelSerializer):
    attributes = ProductVariantAttributeSerializer(many=True, required=False)

    class Meta:
        model = ProductVariant
        fields = ["id", "tenant", "product", "sku", "barcode", "price", "cost_price", "stock_quantity", "image", "is_active", "created_at", "attributes"]
        read_only_fields = ["id", "tenant", "product", "created_at"]

    def create(self, validated_data):
        attributes = validated_data.pop("attributes", [])
        variant = ProductVariant.objects.create(**validated_data)
        ProductVariantAttribute.objects.bulk_create([
            ProductVariantAttribute(tenant=variant.tenant, variant=variant, **attribute)
            for attribute in attributes
        ])
        return variant

    def update(self, instance, validated_data):
        attributes = validated_data.pop("attributes", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if attributes is not None:
            instance.attributes.all().delete()
            ProductVariantAttribute.objects.bulk_create([
                ProductVariantAttribute(tenant=instance.tenant, variant=instance, **attribute)
                for attribute in attributes
            ])
        return instance


class BundleComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BundleComponent
        fields = ["id", "product", "variant", "quantity", "override_price"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        product = attrs.get("product")
        variant = attrs.get("variant")
        if bool(product) == bool(variant):
            raise serializers.ValidationError("Select exactly one product or concrete product variant.")
        return attrs


class ProductBundleSerializer(serializers.ModelSerializer):
    components = BundleComponentSerializer(many=True, required=False)
    computed_price = serializers.SerializerMethodField()

    class Meta:
        model = ProductBundle
        fields = ["id", "tenant", "name", "sku", "description", "image", "price_strategy", "fixed_price", "discount_percent", "is_active", "valid_from", "valid_to", "created_at", "components", "computed_price"]
        read_only_fields = ["id", "tenant", "created_at", "computed_price"]

    def _validate_components(self, tenant, components):
        for component in components:
            product = component.get("product")
            variant = component.get("variant")
            if product and product.tenant_id != tenant.id:
                raise serializers.ValidationError({"components": "Each bundle product must belong to the active tenant."})
            if variant and variant.tenant_id != tenant.id:
                raise serializers.ValidationError({"components": "Each bundle variant must belong to the active tenant."})
            if bool(product) == bool(variant):
                raise serializers.ValidationError({"components": "Each bundle component must reference exactly one product or product variant."})

    def _sync_components(self, bundle, components):
        self._validate_components(bundle.tenant, components)
        bundle.components.all().delete()
        BundleComponent.objects.bulk_create([
            BundleComponent(tenant=bundle.tenant, bundle=bundle, **component)
            for component in components
        ])

    def create(self, validated_data):
        components = validated_data.pop("components", [])
        bundle = ProductBundle.objects.create(**validated_data)
        self._sync_components(bundle, components)
        return bundle

    def update(self, instance, validated_data):
        components = validated_data.pop("components", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if components is not None:
            self._sync_components(instance, components)
        return instance

    def get_computed_price(self, obj):
        return obj.computed_price()


class TenantProductRelationSerializer(serializers.ModelSerializer):
    def _require_tenant_relation(self, value, field):
        tenant = self.context["request"].tenant
        if value is not None and getattr(value, "tenant_id", None) != tenant.id:
            raise serializers.ValidationError({field: "The selected record does not belong to the active tenant."})
        return value


class SerialNumberSerializer(TenantProductRelationSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    order_number = serializers.CharField(source="sold_in_order.order_number", read_only=True)

    class Meta:
        model = SerialNumber
        fields = ["id", "tenant", "product", "product_name", "product_sku", "variant", "batch", "batch_number", "serial_number", "status", "purchased_at", "sold_at", "sold_in_order", "order_number", "cost_price", "warranty_months", "warranty_expires", "notes", "created_at"]
        read_only_fields = ["id", "tenant", "created_at"]

    def validate_product(self, value):
        return self._require_tenant_relation(value, "product")

    def validate_variant(self, value):
        return self._require_tenant_relation(value, "variant")

    def validate_sold_in_order(self, value):
        return self._require_tenant_relation(value, "sold_in_order")

    def validate_batch(self, value):
        return self._require_tenant_relation(value, "batch")

    def validate(self, attrs):
        product = attrs.get("product") or getattr(self.instance, "product", None)
        batch = attrs.get("batch") or getattr(self.instance, "batch", None)
        variant = attrs.get("variant") or getattr(self.instance, "variant", None)
        if batch and product and batch.product_id != product.id:
            raise serializers.ValidationError({"batch": "The selected batch does not belong to this product."})
        if variant and product and variant.product_id != product.id:
            raise serializers.ValidationError({"variant": "The selected variant does not belong to this product."})
        return attrs


class BatchSerializer(TenantProductRelationSerializer):
    is_expired = serializers.BooleanField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = Batch
        fields = ["id", "tenant", "product", "product_name", "product_sku", "batch_number", "quantity", "remaining_quantity", "manufacturing_date", "expiry_date", "received_at", "supplier", "is_recalled", "notes", "created_at", "is_expired"]
        read_only_fields = ["id", "tenant", "created_at", "is_expired"]

    def validate_product(self, value):
        return self._require_tenant_relation(value, "product")

    def validate_supplier(self, value):
        return self._require_tenant_relation(value, "supplier")


class BatchMovementSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    operator_name = serializers.SerializerMethodField()

    class Meta:
        model = BatchMovement
        fields = ["id", "tenant", "batch", "kind", "quantity", "order", "order_number", "reference", "created_at", "created_by", "operator_name"]
        read_only_fields = fields

    def get_operator_name(self, obj):
        if not obj.created_by:
            return "System"
        return obj.created_by.get_full_name() or obj.created_by.get_username()


class ProductMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductMedia
        fields = ["id", "tenant", "product", "kind", "file", "caption", "sort_order", "is_primary", "created_at"]
        read_only_fields = ["id", "tenant", "product", "created_at"]

    def validate_file(self, value):
        maximum_size = 15 * 1024 * 1024
        if value.size > maximum_size:
            raise serializers.ValidationError("Media files must be 15 MB or smaller.")
        content_type = getattr(value, "content_type", "")
        kind = self.initial_data.get("kind", getattr(self.instance, "kind", "image"))
        allowed = {
            "image": {"image/jpeg", "image/png", "image/webp", "image/gif"},
            "video": {"video/mp4", "video/webm"},
            "360": {"image/jpeg", "image/png", "image/webp"},
        }
        if content_type and content_type not in allowed.get(kind, set()):
            raise serializers.ValidationError("The selected file type is not supported for this media kind.")
        return value


class BrandSerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = ["id", "tenant", "name", "description", "logo", "is_active", "created_at", "product_count"]
        read_only_fields = ["id", "tenant", "created_at", "product_count"]

    def get_product_count(self, obj):
        return Product.objects.filter(tenant=obj.tenant, brand=obj).count()


class VariantValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = VariantValue
        fields = ["id", "value"]
        read_only_fields = ["id"]


class VariantDefinitionSerializer(serializers.ModelSerializer):
    values = VariantValueSerializer(many=True, required=False)

    class Meta:
        model = Variant
        fields = ["id", "tenant", "name", "created_at", "values"]
        read_only_fields = ["id", "tenant", "created_at"]

    def _sync_values(self, variant, values):
        variant.values.all().delete()
        VariantValue.objects.bulk_create([
            VariantValue(tenant=variant.tenant, variant=variant, **value)
            for value in values
        ])

    def create(self, validated_data):
        values = validated_data.pop("values", [])
        variant = Variant.objects.create(**validated_data)
        self._sync_values(variant, values)
        return variant

    def update(self, instance, validated_data):
        values = validated_data.pop("values", None)
        instance.name = validated_data.get("name", instance.name)
        instance.save(update_fields=['name'])
        if values is not None:
            self._sync_values(instance, values)
        return instance
