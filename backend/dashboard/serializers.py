# backend/backend/dashboard/serializers.py

from rest_framework import serializers


class DashboardSummarySerializer(serializers.Serializer):
    today_orders = serializers.IntegerField()
    today_sales = serializers.FloatField()
    total_customers = serializers.IntegerField()
    total_products = serializers.IntegerField()
    total_suppliers = serializers.IntegerField()
    low_stock_count = serializers.IntegerField()
    out_of_stock_count = serializers.IntegerField()
    open_sessions = serializers.IntegerField()
    pending_orders = serializers.IntegerField()


class KPISerializer(serializers.Serializer):
    total_sales = serializers.FloatField()
    total_sales_change = serializers.FloatField()
    orders = serializers.IntegerField()
    orders_change = serializers.FloatField()
    avg_order = serializers.FloatField()
    avg_order_change = serializers.FloatField()
    customers = serializers.IntegerField()
    customers_change = serializers.FloatField()
    gross_profit = serializers.FloatField()
    gross_profit_change = serializers.FloatField()


class SalesChartSerializer(serializers.Serializer):
    labels = serializers.ListField(child=serializers.CharField())
    sales = serializers.ListField(child=serializers.FloatField())
    purchase = serializers.ListField(child=serializers.FloatField())


class PaymentMethodSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.FloatField()
    amount = serializers.FloatField()
    color = serializers.CharField()


class TodaySummarySerializer(serializers.Serializer):
    opening_balance = serializers.FloatField()
    total_sales = serializers.FloatField()
    total_refunds = serializers.FloatField()
    total_discounts = serializers.FloatField()
    net_sales = serializers.FloatField()
    closing_balance = serializers.FloatField()


class RecentOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order_number = serializers.CharField()
    customer = serializers.CharField()
    amount = serializers.FloatField()
    status = serializers.CharField()
    payment_method = serializers.CharField()
    created_at = serializers.CharField()


class TopProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    sku = serializers.CharField()
    price = serializers.FloatField()
    image = serializers.CharField()
    sold = serializers.IntegerField()
    revenue = serializers.FloatField()
    growth = serializers.FloatField()


class LowStockSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    sku = serializers.CharField()
    category = serializers.CharField(allow_null=True)
    stock = serializers.IntegerField()
    minimum_stock = serializers.IntegerField()
    unit = serializers.CharField()
    image = serializers.CharField()
    status = serializers.CharField()


class ActiveSessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    cashier = serializers.CharField()
    opened_at = serializers.CharField()
    duration = serializers.CharField()
    total_sales = serializers.FloatField()
    order_count = serializers.IntegerField()


class QuickActionSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField()
    route = serializers.CharField()


class OrderStatisticsSerializer(serializers.Serializer):
    completed = serializers.IntegerField()
    draft = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    refunded = serializers.IntegerField()
    pending = serializers.IntegerField()
    partial_refunded = serializers.IntegerField()


class InventoryStatsSerializer(serializers.Serializer):
    total_products = serializers.IntegerField()
    total_stock = serializers.IntegerField()
    total_value = serializers.FloatField()
    low_stock = serializers.IntegerField()
    out_of_stock = serializers.IntegerField()


class CustomerStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    new_this_month = serializers.IntegerField()
    returning = serializers.IntegerField()
    avg_orders_per_customer = serializers.FloatField()