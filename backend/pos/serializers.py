from rest_framework import serializers
from .models import *
from decimal import Decimal
from django.db import transaction
from .services.pricing import resolve_unit_price
from .services.tax import calculate_order_tax


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    child_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id","tenant","name","parent","parent_name","is_active","product_count","child_count"]
        read_only_fields = ["tenant"]

    def validate_parent(self, parent):
        if parent is None:
            return parent
        tenant = self.context["request"].tenant
        if parent.tenant_id != tenant.id:
            raise serializers.ValidationError("The selected parent category does not belong to the active tenant.")
        instance = self.instance
        if instance and parent.pk == instance.pk:
            raise serializers.ValidationError("A category cannot be its own parent.")
        current = parent
        while current is not None:
            if instance and current.pk == instance.pk:
                raise serializers.ValidationError("A category cannot be moved under one of its descendants.")
            current = current.parent
        return parent


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    stock_status = serializers.SerializerMethodField()
    stock_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id","tenant","category","category_name","brand","brand_name","name","sku","barcode","description","sales_price","cost_price","stock_quantity","min_stock","max_stock","unit","image","is_active","expiry_date","batch_number","stock_status","stock_percentage"]
        read_only_fields = ["id", "tenant"]

    def validate_category(self, value):
        if value is not None and value.tenant_id != self.context["request"].tenant.id:
            raise serializers.ValidationError("The selected category does not belong to the active tenant.")
        return value

    def validate_brand(self, value):
        if value is not None and value.tenant_id != self.context["request"].tenant.id:
            raise serializers.ValidationError("The selected brand does not belong to the active tenant.")
        return value

    def get_stock_status(self, obj):

        if obj.stock_quantity == 0:
            return "Out of Stock"

        if obj.stock_quantity <= obj.min_stock:
            return "Low Stock"

        if (
            obj.max_stock is not None and
            obj.stock_quantity > obj.max_stock
        ):
            return "Overstock"

        return "In Stock"

    def get_stock_percentage(self, obj):

        if not obj.max_stock:
            return None

        if obj.max_stock == 0:
            return 0

        percentage = (obj.stock_quantity / obj.max_stock) * 100

        return round(percentage, 1)

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id","tenant","name","phone","email","address","customer_code","is_active","created_at","updated_at","group","loyalty_points","date_of_birth"]


class CashSessionSerializer(serializers.ModelSerializer):
    expected_cash = serializers.SerializerMethodField()
    difference = serializers.SerializerMethodField()
    total_sales = serializers.SerializerMethodField()
    cash_payments = serializers.SerializerMethodField()
    card_payments = serializers.SerializerMethodField()
    bank_payments = serializers.SerializerMethodField()
    total_orders = serializers.SerializerMethodField()

    class Meta:
        model = CashSession
        fields = ["id","tenant","warehouse","opened_at","opened_by","closed_by","closed_at","opening_balance","closing_balance","actual_closing_balance","is_open","next_draft_number","employee_name","notes","expected_cash","difference","total_sales","cash_payments","card_payments","bank_payments","total_orders"]

    def get_total_sales(self, obj):
        from django.db.models import Sum
        return obj.orders.exclude(status='draft').exclude(status='cancelled').aggregate(total=Sum('total'))['total'] or 0

    def get_total_orders(self, obj):
        return obj.orders.exclude(status='draft').exclude(status='cancelled').count()

    def get_cash_payments(self, obj):
        from django.db.models import Sum
        return obj.orders.exclude(status='draft').exclude(status='cancelled').filter(payment_method='cash').aggregate(total=Sum('total'))['total'] or 0

    def get_card_payments(self, obj):
        from django.db.models import Sum
        return obj.orders.exclude(status='draft').exclude(status='cancelled').filter(payment_method='card').aggregate(total=Sum('total'))['total'] or 0

    def get_bank_payments(self, obj):
        from django.db.models import Sum
        return obj.orders.exclude(status='draft').exclude(status='cancelled').filter(payment_method='bank').aggregate(total=Sum('total'))['total'] or 0

    def get_expected_cash(self, obj):
        cash_sales = self.get_cash_payments(obj)
        from django.db.models import Sum
        cash_in = obj.transactions.filter(transaction_type='in').aggregate(total=Sum('amount'))['total'] or 0
        cash_out = obj.transactions.filter(transaction_type='out').aggregate(total=Sum('amount'))['total'] or 0
        return (obj.opening_balance or 0) + cash_sales + cash_in - cash_out

    def get_difference(self, obj):
        if obj.actual_closing_balance is not None:
            return obj.actual_closing_balance - self.get_expected_cash(obj)
        return 0

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id","tenant","order","amount","payment_method","paid_at"]

class OrderItemSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(
        source="product.image",
        read_only=True
    )
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "quantity",
            "unit_price",
            "subtotal",
            "image",
            "product_name",
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Order
        fields = ["id","tenant","warehouse","customer","note","session","created_at","payment_method","subtotal","tax","discount","total","status","order_number","amount_received","change_amount","idempotency_key","idempotency_request_hash"]
        read_only_fields = ["id", "tenant", "warehouse", "session", "created_at", "subtotal", "tax", "discount", "total", "status", "order_number", "amount_received", "change_amount", "idempotency_key", "idempotency_request_hash"]


class CartItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)

    def validate_quantity(self, quantity):
        if quantity <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return quantity



        

class DraftOrderSerializer(serializers.ModelSerializer):

    customer_id = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()

    class Meta:
        model = DraftOrder
        fields = ["id","tenant","session","order_number","status","customer","note","created_at"]

    def get_customer_id(self, obj):
        return obj.customer.id if obj.customer else None

    def get_payment_method(self, obj):
        return "Cash"


class DraftOrderItemSerializer(serializers.ModelSerializer):

    product_name = serializers.CharField(source="product.name",read_only=True)
    sales_price = serializers.DecimalField(source="product.sales_price",max_digits=10,decimal_places=2,read_only=True)
    image = serializers.ImageField(source="product.image",read_only=True)

    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = DraftOrderItem
        fields = [
            "product_name",
            "id",
            "product",
            "quantity",
            "sales_price",
            "subtotal",
            "image",
        ]

    def get_subtotal(self, obj):
        return obj.product.sales_price * obj.quantity
    

class CompanySerializer(serializers.ModelSerializer):

    class Meta:
        model = Company
        fields = ["id","tenant","name","tagline","address","phone","email","website","tax_number","footer_message","logo","currency","receipt_paper","gst","legal_name","cover_image","business_type","industry","business_registration_number","country","state","city","postal_code","full_address","receipt_header","thank_you_message","return_policy","show_qr_code_on_receipt","show_logo_on_receipt"]        


class OrderHistorySerializer(serializers.ModelSerializer):

    customer_name = serializers.SerializerMethodField()
    record_type = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer_name",
            "payment_method",
            "total",
            "created_at",
            "status",
            "record_type",
        ]

    def get_customer_name(self, obj):
        if obj.customer:
            return obj.customer.name
        return "Walk-in Customer"
    
    def get_record_type(self, obj):
        return "order"
    

class DraftOrderHistorySerializer(serializers.ModelSerializer):

    customer = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    record_type = serializers.SerializerMethodField()

    class Meta:
        model = DraftOrder
        fields = [
            "id",
            "order_number",
            "customer",
            "total",
            "payment_method",
            "created_at",
            "status",
            "record_type",
        ]

    def get_customer(self, obj):
        return obj.customer.name if obj.customer else "Walk-in Customer"

    def get_total(self, obj):
        total = 0

        for item in obj.items.all():
            total += item.product.sales_price * item.quantity

        return total

    def get_payment_method(self, obj):
        return "Cash"

    def get_status(self, obj):
        return "draft"

    def get_record_type(self, obj):
        return "draft"


class StockAdjustmentItemSerializer(serializers.Serializer):

    product_id = serializers.IntegerField()

    adjustment_type = serializers.ChoiceField(
        choices=["increase", "decrease"]
    )

    quantity = serializers.IntegerField(min_value=1)

    note = serializers.CharField(
        required=False,
        allow_blank=True
    )


class StockAdjustmentSerializer(serializers.Serializer):

    reason = serializers.CharField()

    note = serializers.CharField(
        required=False,
        allow_blank=True
    )

    items = StockAdjustmentItemSerializer(
        many=True
    )         


class InventorySerializer(serializers.ModelSerializer):

    category = serializers.CharField(
        source="category.name",
        default="",
        read_only=True
    )

    image_url = serializers.SerializerMethodField()

    stock_status = serializers.SerializerMethodField()

    inventory_value = serializers.SerializerMethodField()

    class Meta:
        model = Product

        fields = [
            "id",
            "name",
            "sku",
            "barcode",
            "description",

            "category",

            "sales_price",
            "cost_price",

            "stock_quantity",
            "min_stock",
            "max_stock",
            "unit",

            "image_url",

            "stock_status",
            "inventory_value",

            "is_active",
        ]

    def get_stock_status(self, obj):

        if obj.stock_quantity <= 0:
            return "Out of Stock"

        elif obj.stock_quantity <= obj.min_stock:
            return "Low Stock"

        return "In Stock"

    def get_inventory_value(self, obj):
        return float(obj.cost_price) * obj.stock_quantity

    def get_image_url(self, obj):

        if not obj.image:
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(obj.image.url)

        return obj.image.url
    

    def get_stock_status(self, obj):

        if obj.stock_quantity <= 0:
            return "Out of Stock"

        if obj.stock_quantity <= 10:
            return "Low Stock"

        return "In Stock"

    def get_inventory_value(self, obj):

        return obj.stock_quantity * obj.cost_price        


class StockMovementSerializer(serializers.ModelSerializer):

    product = serializers.CharField(source="product.name")

    image = serializers.ImageField(
        source="product.image",
        read_only=True
    )

    movement = serializers.CharField(
        source="get_movement_type_display"
    )

    class Meta:
        model = StockMovement

        fields = [
            "id",
            "product",
            "image",
            "movement_type",
            "movement",
            "quantity",
            "previous_stock",
            "new_stock",
            "reference",
            "note",
            "created_at",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):

    category = serializers.CharField(
        source="category.name",
        read_only=True
    )

    stock_status = serializers.SerializerMethodField()

    profit_per_unit = serializers.SerializerMethodField()

    markup_percentage = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:

        model = Product

        fields = [

            "id",

            "name",

            "sku",

            "barcode",

            "category",

            "sales_price",

            "cost_price",

            "stock_quantity",

            "min_stock",

            "max_stock",

            "unit",

            "image",
            "image_url",

            "stock_status",

            "profit_per_unit",

            "markup_percentage",

            "is_active",

        ]

    def get_stock_status(self, obj):

        if obj.stock_quantity == 0:
            return "Out of Stock"

        if obj.stock_quantity <= obj.min_stock:
            return "Low Stock"

        if (
            obj.max_stock and
            obj.stock_quantity > obj.max_stock
        ):
            return "Overstock"

        return "In Stock"

    def get_stock_percentage(self, obj):

        if not obj.max_stock:
            return None

        if obj.max_stock == 0:
            return 0

        percentage = (obj.stock_quantity / obj.max_stock) * 100

        return round(percentage, 1)




class PurchaseOrderItemSerializer(serializers.Serializer):

    product = serializers.IntegerField()

    quantity = serializers.IntegerField()

    unit_cost = serializers.DecimalField(max_digits=10,decimal_places=2)

    class Meta:
        model = Supplier
        fields = ["id", "tenant", "name", "company", "contact_person", "phone", "email", "address", "tax_number", "is_active", "created_at", "updated_at"]


class PurchaseOrderCreateSerializer(serializers.Serializer):

    supplier = serializers.IntegerField()

    note = serializers.CharField(
        required=False,
        allow_blank=True
    )

    items = PurchaseOrderItemSerializer(
        many=True
    )


class ReceiveItemSerializer(serializers.Serializer):

    purchase_item = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class ReceivePurchaseSerializer(serializers.Serializer):

    items = ReceiveItemSerializer(many=True)


class PurchaseOrderItemDetailSerializer(serializers.ModelSerializer):

    product = serializers.CharField(
        source="product.name"
    )

    class Meta:

        model = PurchaseOrderItem

        fields = [
            "id",
            "product",
            "quantity",
            "received_quantity",
            "unit_cost",
            "subtotal",
        ]


class PurchaseOrderListSerializer(serializers.ModelSerializer):

    supplier = serializers.CharField(
        source="supplier.name",
        read_only=True,
    )

    total_items = serializers.SerializerMethodField()

    class Meta:

        model = PurchaseOrder

        fields = [

            "id",

            "order_number",

            "supplier",

            "status",

            "subtotal",

            "tax",

            "total",

            "total_items",

            "created_at",

        ]

    def get_total_items(self, obj):

        return obj.items.count()

    
class PurchaseOrderDetailSerializer(serializers.ModelSerializer):

    supplier = serializers.CharField(
        source="supplier.name"
    )

    items = PurchaseOrderItemDetailSerializer(
        many=True
    )

    class Meta:

        model = PurchaseOrder

        fields = ["id","tenant","supplier","warehouse","order_number","status","subtotal","tax","supplier_invoice_number","expected_date","total","note","created_at","updated_at"]


class StockAdjustmentListSerializer(serializers.ModelSerializer):

    created_by = serializers.CharField(
        source="created_by.username",
        default=None
    )

    total_items = serializers.SerializerMethodField()

    net_change = serializers.SerializerMethodField()

    class Meta:

        model = StockAdjustment

        fields = [

            "id",

            "adjustment_number",

            "reason",

            "note",

            "created_by",

            "created_at",

            "total_items",

            "net_change",

        ]

    def get_total_items(self, obj):

        return obj.items.count()

    def get_net_change(self, obj):

        total = 0

        for item in obj.items.all():

            total += item.new_stock - item.previous_stock

        return total


class StockAdjustmentItemDetailSerializer(serializers.ModelSerializer):

    product = serializers.CharField(
        source="product.name"
    )

    sku = serializers.CharField(
        source="product.sku"
    )

    adjustment_type = serializers.SerializerMethodField()

    class Meta:

        model = StockAdjustmentItem

        fields = [

            "product",

            "sku",

            "adjustment_type",

            "quantity",

            "previous_stock",

            "new_stock",

            "note",

        ]

    def get_adjustment_type(self, obj):

        if obj.new_stock > obj.previous_stock:
            return "increase"

        return "decrease"


class StockAdjustmentDetailSerializer(serializers.ModelSerializer):

    created_by = serializers.SerializerMethodField()

    items = StockAdjustmentItemDetailSerializer(
        many=True,
        read_only=True
    )

    class Meta:

        model = StockAdjustment

        fields = [

            "id",

            "adjustment_number",

            "reason",

            "note",

            "created_at",

            "created_by",

            "items",

        ]

    def get_created_by(self, obj):

        if obj.created_by:

            return obj.created_by.username

        return None  


class InventoryValuationSerializer(serializers.Serializer):

    total_products = serializers.IntegerField()

    total_stock_units = serializers.IntegerField()

    inventory_cost_value = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    inventory_sale_value = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    expected_profit = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )


class ProductInventoryValuationSerializer(serializers.ModelSerializer):

    category = serializers.CharField(
        source="category.name",
        default=""
    )

    cost_value = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    sale_value = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    expected_profit = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:

        model = Product

        fields = [

            "id",

            "name",

            "sku",

            "category",

            "stock_quantity",

            "cost_price",

            "sales_price",

            "cost_value",

            "sale_value",

            "expected_profit",
        ]


class InventoryReportSerializer(serializers.Serializer):

    total_products = serializers.IntegerField()

    total_stock = serializers.IntegerField()

    total_cost = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    total_sale = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    total_profit = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
    ) 


class InventoryAnalyticsSerializer(serializers.Serializer):

    total_products = serializers.IntegerField()

    total_stock = serializers.IntegerField()

    low_stock = serializers.IntegerField()

    out_of_stock = serializers.IntegerField()

    overstock = serializers.IntegerField()


class TopSellingProductSerializer(serializers.Serializer):

    product__id = serializers.IntegerField()

    product__name = serializers.CharField()

    product__sku = serializers.CharField()

    total_sold = serializers.IntegerField()


class SlowMovingProductSerializer(serializers.ModelSerializer):

    total_sold = serializers.IntegerField()

    category = serializers.CharField(
        source="category.name",
        default=""
    )

    class Meta:

        model = Product

        fields = [

            "id",

            "name",

            "sku",

            "category",

            "stock_quantity",

            "total_sold",

            "cost_price",

            "sales_price",

        ]


class MostReturnedProductSerializer(serializers.Serializer):

    product_id = serializers.IntegerField()

    product_name = serializers.CharField()

    sku = serializers.CharField()

    total_returned = serializers.IntegerField()                                                                                                                     
