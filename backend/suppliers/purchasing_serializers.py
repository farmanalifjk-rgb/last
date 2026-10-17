from decimal import Decimal

from rest_framework import serializers

from pos.models import PurchaseOrder, PurchaseOrderItem, Supplier

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseReturn, PurchaseReturnLine, SupplierContact, SupplierPortalToken


class SupplierContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierContact
        fields = ["id", "tenant", "supplier", "name", "role", "email", "phone", "is_primary", "created_at"]
        read_only_fields = ["id", "tenant", "supplier", "created_at"]


class SupplierListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "company", "contact_person", "phone", "email", "address", "tax_number", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "name", "company", "contact_person", "phone", "email", "address", "tax_number", "is_active", "created_at", "updated_at"]


class SupplierWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "company", "contact_person", "phone", "email", "address", "tax_number"]
        read_only_fields = ["id", "name", "company", "contact_person", "phone", "email", "address", "tax_number"]

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("A supplier name is required.")
        tenant = getattr(self.context.get("request"), "tenant", None)
        query = Supplier.objects.filter(tenant=tenant, name__iexact=name)
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        if tenant and query.exists():
            raise serializers.ValidationError("A supplier with this name already exists in the active tenant.")
        return name


class SupplierDetailSerializer(SupplierListSerializer):
    contacts = SupplierContactSerializer(many=True, read_only=True)

    class Meta(SupplierListSerializer.Meta):
        fields = SupplierListSerializer.Meta.fields + ["contacts"]


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    remaining_quantity = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "tenant", "purchase_order", "product", "product_id", "product_name", "product_sku", "quantity", "received_quantity", "unit_cost", "subtotal", "returned_quantity", "remaining_quantity"]

    def get_remaining_quantity(self, instance):
        return str(max(instance.quantity - instance.received_quantity, 0))


class PurchaseOrderLineWriteSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))


class PurchaseOrderWriteSerializer(serializers.Serializer):
    supplier_id = serializers.IntegerField(min_value=1)
    warehouse_id = serializers.IntegerField(min_value=1)
    expected_date = serializers.DateField(required=False, allow_null=True)
    supplier_invoice_number = serializers.CharField(required=False, allow_blank=True, max_length=100)
    note = serializers.CharField(required=False, allow_blank=True)
    items = PurchaseOrderLineWriteSerializer(many=True, allow_empty=False)

    def validate_items(self, value):
        product_ids = [line["product_id"] for line in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("A product may appear only once on a purchase order.")
        return value


class PurchaseOrderListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    item_count = serializers.SerializerMethodField()
    remaining_quantity = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = ["id", "tenant", "supplier", "supplier_name", "warehouse", "warehouse_name", "order_number", "status", "subtotal", "tax", "total", "expected_date", "item_count", "remaining_quantity", "created_at", "updated_at"]

    def get_item_count(self, instance):
        return instance.items.count()

    def get_remaining_quantity(self, instance):
        return str(sum((line.quantity - line.received_quantity for line in instance.items.all()), start=0))


class PurchaseOrderDetailSerializer(PurchaseOrderListSerializer):
    items = PurchaseOrderLineSerializer(many=True, read_only=True)
    receipt_count = serializers.SerializerMethodField()
    return_count = serializers.SerializerMethodField()

    class Meta(PurchaseOrderListSerializer.Meta):
        fields = PurchaseOrderListSerializer.Meta.fields + ["supplier_invoice_number", "note", "items", "receipt_count", "return_count"]

    def get_receipt_count(self, instance):
        return instance.receipts.count()

    def get_return_count(self, instance):
        return instance.supplier_returns.count()


class ReceiptLineWriteSerializer(serializers.Serializer):
    purchase_order_item_id = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    batch_number = serializers.CharField(required=False, allow_blank=True, max_length=100)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    serial_numbers = serializers.ListField(child=serializers.CharField(max_length=100), required=False, allow_empty=True)

    def validate_serial_numbers(self, value):
        cleaned = [serial.strip() for serial in value if serial.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise serializers.ValidationError("Serial numbers must be unique within a receipt line.")
        return cleaned


class ReceiptWriteSerializer(serializers.Serializer):
    supplier_invoice_number = serializers.CharField(required=False, allow_blank=True, max_length=100)
    note = serializers.CharField(required=False, allow_blank=True)
    lines = ReceiptLineWriteSerializer(many=True, allow_empty=False)

    def validate_lines(self, value):
        item_ids = [line["purchase_order_item_id"] for line in value]
        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError("A purchase order line may appear only once in a receipt.")
        return value


class GoodsReceiptLineSerializer(serializers.ModelSerializer):
    purchase_order_item_id = serializers.IntegerField(source="purchase_order_item.id", read_only=True)
    product_id = serializers.IntegerField(source="purchase_order_item.product.id", read_only=True)
    product_name = serializers.CharField(source="purchase_order_item.product.name", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True, default="")

    class Meta:
        model = GoodsReceiptLine
        fields = ["id", "tenant", "receipt", "purchase_order_item", "purchase_order_item_id", "product_id", "product_name", "batch", "batch_number", "quantity_ordered", "quantity_received", "quantity_accepted", "quantity_rejected", "rejection_reason"]


class GoodsReceiptSerializer(serializers.ModelSerializer):
    purchase_order_number = serializers.CharField(source="purchase_order.order_number", read_only=True)
    supplier_name = serializers.CharField(source="purchase_order.supplier.name", read_only=True)
    warehouse_name = serializers.CharField(source="purchase_order.warehouse.name", read_only=True)
    received_by_name = serializers.CharField(source="received_by.get_username", read_only=True, default="")
    lines = GoodsReceiptLineSerializer(many=True, read_only=True)

    class Meta:
        model = GoodsReceipt
        fields = ["id", "receipt_number", "purchase_order", "purchase_order_number", "supplier_name", "warehouse_name", "supplier_invoice_number", "status", "received_at", "received_by", "received_by_name", "note", "lines"]


class PurchaseReturnLineWriteSerializer(serializers.Serializer):
    purchase_order_item_id = serializers.IntegerField(min_value=1)
    receipt_line_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class PurchaseReturnWriteSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)
    supplier_credit_note = serializers.CharField(required=False, allow_blank=True, max_length=100)
    lines = PurchaseReturnLineWriteSerializer(many=True, allow_empty=False)

    def validate_lines(self, value):
        item_ids = [line["purchase_order_item_id"] for line in value]
        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError("A purchase order line may appear only once in a return.")
        return value


class PurchaseReturnLineSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="purchase_order_item.product.id", read_only=True)
    product_name = serializers.CharField(source="purchase_order_item.product.name", read_only=True)
    product_sku = serializers.CharField(source="purchase_order_item.product.sku", read_only=True)

    class Meta:
        model = PurchaseReturnLine
        fields = ["id", "tenant", "purchase_return", "purchase_order_item", "receipt_line", "quantity", "unit_cost", "reason", "product_id", "product_name", "product_sku"]


class PurchaseReturnSerializer(serializers.ModelSerializer):
    purchase_order_number = serializers.CharField(source="purchase_order.order_number", read_only=True)
    supplier_name = serializers.CharField(source="purchase_order.supplier.name", read_only=True)
    warehouse_name = serializers.CharField(source="purchase_order.warehouse.name", read_only=True)
    lines = PurchaseReturnLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = ["id", "tenant", "purchase_order", "return_number", "supplier_credit_note", "status", "total_amount", "reason", "created_at", "created_by", "processed_at", "processed_by", "purchase_order_number", "supplier_name", "warehouse_name", "lines"]


class SupplierPortalTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierPortalToken
        fields = ["id", "contact_email", "is_active", "last_login", "created_at"]
        read_only_fields = ["id", "last_login", "created_at"]
