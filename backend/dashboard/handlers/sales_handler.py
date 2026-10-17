# backend/backend/dashboard/handlers/sales_handler.py

from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek, TruncDay
from django.utils import timezone

from pos.models import Order, OrderItem, CashSession
from accounting.models import ChartOfAccount, JournalEntryLine
from datetime import datetime, timedelta

from ..utils.helpers import get_date_range, format_currency, calculate_growth, get_payment_color


class SalesHandler:
    """Handles all sales-related dashboard data"""
    
    def __init__(self, request=None):
        self.request = request
        self.now = timezone.now()
    
    def get_kpis(self, period='today'):
        """Get KPI data for dashboard cards"""
        start_date, end_date = get_date_range(period)
        start_datetime = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_datetime = timezone.make_aware(
            datetime.combine(end_date, datetime.max.time())
        )
        
        # Current period orders
        current_orders = Order.objects.filter(
            created_at__range=(start_datetime, end_datetime),
            status__in=['paid', 'completed']
        )
        
        total_sales = current_orders.aggregate(total=Sum('total'))['total'] or 0
        total_orders = current_orders.count()
        avg_order = total_sales / total_orders if total_orders > 0 else 0
        
        # Previous period for comparison
        period_days = (end_date - start_date).days + 1
        prev_start = start_date - timedelta(days=period_days)
        prev_end = start_date - timedelta(days=1)
        prev_start_dt = timezone.make_aware(
            datetime.combine(prev_start, datetime.min.time())
        )
        prev_end_dt = timezone.make_aware(
            datetime.combine(prev_end, datetime.max.time())
        )
        
        prev_orders = Order.objects.filter(
            created_at__range=(prev_start_dt, prev_end_dt),
            status__in=['paid', 'completed']
        )
        prev_sales = prev_orders.aggregate(total=Sum('total'))['total'] or 0
        prev_orders_count = prev_orders.count()
        
        # Calculate growth
        sales_growth = calculate_growth(prev_sales, total_sales)
        orders_growth = calculate_growth(prev_orders_count, total_orders)
        
        # Gross profit
        cost_of_goods = OrderItem.objects.filter(
            order__created_at__range=(start_datetime, end_datetime),
            order__status__in=['paid', 'completed']
        ).aggregate(
            total=Sum(F('quantity') * F('product__cost_price'))
        )['total'] or 0
        
        gross_profit = total_sales - cost_of_goods
        
        prev_cogs = OrderItem.objects.filter(
            order__created_at__range=(prev_start_dt, prev_end_dt),
            order__status__in=['paid', 'completed']
        ).aggregate(
            total=Sum(F('quantity') * F('product__cost_price'))
        )['total'] or 0
        prev_gross_profit = prev_sales - prev_cogs
        profit_growth = calculate_growth(prev_gross_profit, gross_profit)
        
        # Customers (from customer handler)
        from .customer_handler import CustomerHandler
        customer_handler = CustomerHandler(self.request)
        total_customers = customer_handler.get_total_customers()
        prev_customers = customer_handler.get_total_customers(prev_end)
        customers_growth = calculate_growth(prev_customers, total_customers)
        
        return {
            'total_sales': format_currency(total_sales),
            'total_sales_change': sales_growth,
            'orders': total_orders,
            'orders_change': orders_growth,
            'avg_order': format_currency(avg_order),
            'avg_order_change': 0,
            'customers': total_customers,
            'customers_change': customers_growth,
            'gross_profit': format_currency(gross_profit),
            'gross_profit_change': profit_growth,
        }
    
    def get_sales_chart(self, period='year'):
        """Get sales vs purchase chart data"""
        start_date, end_date = get_date_range(period)
        start_datetime = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_datetime = timezone.make_aware(
            datetime.combine(end_date, datetime.max.time())
        )
        
        # Determine grouping
        if period in ['today', 'week']:
            trunc_func = TruncDay
            date_format = '%d %b'
        elif period in ['month', 'quarter']:
            trunc_func = TruncWeek
            date_format = '%d %b'
        else:
            trunc_func = TruncMonth
            date_format = '%b %Y'
        
        # Sales data
        sales_data = Order.objects.filter(
            created_at__range=(start_datetime, end_datetime),
            status__in=['paid', 'completed']
        ).annotate(
            date=trunc_func('created_at')
        ).values('date').annotate(
            total=Sum('total')
        ).order_by('date')
        
        # Purchase data (StockMovements)
        from inventory.models import StockMovement
        purchase_data = StockMovement.objects.filter(
            created_at__range=(start_datetime, end_datetime),
            movement_type__in=['purchase', 'receiving']
        ).annotate(
            date=trunc_func('created_at')
        ).values('date').annotate(
            total=Sum('quantity')
        ).order_by('date')
        
        # Merge data
        dates = set()
        sales_dict = {}
        purchase_dict = {}
        
        for item in sales_data:
            if item['date']:
                date_key = item['date'].strftime(date_format)
                dates.add(date_key)
                sales_dict[date_key] = float(item['total'] or 0)
        
        for item in purchase_data:
            if item['date']:
                date_key = item['date'].strftime(date_format)
                dates.add(date_key)
                purchase_dict[date_key] = float(item['total'] or 0)
        
        sorted_dates = sorted(list(dates))
        
        return {
            'labels': sorted_dates,
            'sales': [sales_dict.get(d, 0) for d in sorted_dates],
            'purchase': [purchase_dict.get(d, 0) for d in sorted_dates]
        }
    
    def get_payment_methods(self, period='today'):
        """Get payment method breakdown"""
        start_date, end_date = get_date_range(period)
        start_datetime = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_datetime = timezone.make_aware(
            datetime.combine(end_date, datetime.max.time())
        )
        
        payments = TenderedPayment.objects.filter(
            created_at__range=(start_datetime, end_datetime)
        ).values('tender_type').annotate(
            total=Sum('amount')
        ).order_by('-total')
        
        total_amount = sum(p['total'] for p in payments) or 1
        
        result = []
        for p in payments:
            result.append({
                'label': p['tender_type'].replace('_', ' ').title(),
                'value': round((p['total'] / total_amount) * 100, 1),
                'amount': float(p['total'] or 0),
                'color': get_payment_color(p['tender_type'])
            })
        
        return result
    
    def get_recent_orders(self, limit=10):
        """Get recent orders"""
        orders = Order.objects.select_related('customer').filter(
            status__in=['paid', 'completed']
        ).order_by('-created_at')[:limit]
        
        result = []
        for order in orders:
            result.append({
                'id': order.id,
                'order_number': order.order_number,
                'customer': order.customer.name if order.customer else 'Walk-in Customer',
                'amount': float(order.total or 0),
                'status': order.status,
                'payment_method': order.payment_method,
                'created_at': order.created_at.isoformat() if order.created_at else None,
            })
        
        return result
    
    def get_top_products(self, limit=10, period='month'):
        """Get top selling products"""
        start_date, end_date = get_date_range(period)
        start_datetime = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_datetime = timezone.make_aware(
            datetime.combine(end_date, datetime.max.time())
        )
        
        products = OrderItem.objects.filter(
            order__created_at__range=(start_datetime, end_datetime),
            order__status__in=['paid', 'completed']
        ).values(
            'product__id',
            'product__name',
            'product__sku',
            'product__sales_price',
            'product__image'
        ).annotate(
            total_sold=Sum('quantity'),
            total_revenue=Sum('subtotal')
        ).order_by('-total_sold')[:limit]
        
        result = []
        for p in products:
            # Calculate growth
            growth = self._get_product_growth(p['product__id'])
            
            result.append({
                'id': p['product__id'],
                'name': p['product__name'],
                'sku': p['product__sku'],
                'price': float(p['product__sales_price'] or 0),
                'image': p['product__image'] or '',
                'sold': p['total_sold'] or 0,
                'revenue': float(p['total_revenue'] or 0),
                'growth': growth
            })
        
        return result
    
    def _get_product_growth(self, product_id):
        """Calculate month-over-month growth for a product"""
        today = timezone.now().date()
        this_month_start = today.replace(day=1)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
        
        this_month = OrderItem.objects.filter(
            product_id=product_id,
            order__status__in=['paid', 'completed'],
            order__created_at__date__gte=this_month_start
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        last_month = OrderItem.objects.filter(
            product_id=product_id,
            order__status__in=['paid', 'completed'],
            order__created_at__date__gte=last_month_start,
            order__created_at__date__lt=this_month_start
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        return calculate_growth(last_month, this_month)
    
    def get_order_statistics(self):
        """Get order status breakdown"""
        stats = Order.objects.values('status').annotate(
            count=Count('id')
        )
        
        result = {
            'completed': 0,
            'draft': 0,
            'cancelled': 0,
            'refunded': 0,
            'pending': 0,
            'partial_refunded': 0,
        }
        
        for stat in stats:
            status = stat['status']
            count = stat['count']
            if status in result:
                result[status] = count
            else:
                result['pending'] += count
        
        return result