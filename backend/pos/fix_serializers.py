import os

file_path = 'serializers.py'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False

missing_classes = """        return "In Stock"

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
        fields = ['id', 'tenant', 'name', 'phone', 'email', 'address', 'customer_code', 'is_active', 'created_at', 'updated_at', 'group', 'loyalty_points', 'date_of_birth']


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
        fields = ['id', 'tenant', 'warehouse', 'opened_at', 'opened_by', 'closed_by', 'closed_at', 'opening_balance', 'closing_balance', 'actual_closing_balance', 'is_open', 'next_draft_number', 'employee_name', 'notes']

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
        fields = ["id", "tenant", "order", "amount", "payment_method", "paid_at"]

class OrderItemSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(
        source="product.image",
        read_only=True
    )
    product_name = serializers.CharField(source='product.name', read_only=True)
"""

for i, line in enumerate(lines):
    if line.strip() == "return \"Overstock\"":
        new_lines.append(line)
        new_lines.append("\n" + missing_classes + "\n")
        skip = True
        continue
    
    if skip and line.strip() == "class Meta:":
        skip = False
    
    if not skip:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
