# backend/backend/pos/services/dashboard.py

"""
Dashboard Service - Single file, all-in-one dashboard data provider
Fixed to work with your actual models
"""

from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models import Sum, Count, Q, F, Avg
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay
from django.utils import timezone
from django.core.cache import cache

from pos.models import Order, OrderItem, CashSession, Customer, Product, StockMovement, Supplier
from payments.models import TenderedPayment
from accounting.models import ChartOfAccount, JournalEntryLine, Expense
from hr.models import Employee
from saas.tenant_context import get_current_tenant


class DashboardService:
    """
    Enterprise Dashboard Service - All dashboard data in one place
    """
    
    def __init__(self, request=None):
        self.request = request
        self.today = timezone.now().date()
        self.now = timezone.now()
    
    def _active_tenant(self):
        """Return the canonical tenant bound by middleware or task context."""
        request_tenant = getattr(self.request, "tenant", None) if self.request else None
        return request_tenant or get_current_tenant()

    def _scoped(self, queryset):
        """Apply the active canonical tenant to every dashboard business query."""
        tenant = self._active_tenant()
        if tenant is None:
            return queryset.none()
        return queryset.filter(tenant=tenant)

    # ─── Helpers ───────────────────────────────────────────────────────────────
    
    def _get_date_range(self, period):
        """Get start/end dates for a period"""
        today = self.today
        if period == 'today':
            return today, today
        elif period == 'week':
            return today - timedelta(days=7), today
        elif period == 'month':
            return today - timedelta(days=30), today
        elif period == 'quarter':
            return today - timedelta(days=90), today
        elif period == 'year':
            return today - timedelta(days=365), today
        return today.replace(day=1), today
    
    def _fmt(self, amount):
        """Format currency"""
        return float(amount or 0)
    
    def _growth(self, previous, current):
        """Calculate percentage growth"""
        if previous == 0:
            return 100 if current > 0 else 0
        return round(((current - previous) / abs(previous)) * 100, 1)
    
    def _time_ago(self, dt):
        """Human readable time ago"""
        if not dt:
            return 'Just now'
        diff = self.now - dt
        if diff.days > 30:
            return f'{diff.days // 30}m ago'
        elif diff.days > 0:
            return f'{diff.days}d ago' if diff.days > 1 else 'Yesterday'
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f'{hours}h ago' if hours > 1 else '1h ago'
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f'{minutes}m ago' if minutes > 1 else '1m ago'
        return 'Just now'
    
    def _payment_color(self, method):
        colors = {
            'cash': '#10B981', 'card': '#6366F1', 'bank': '#60A5FA',
            'gift_card': '#F59E0B', 'store_credit': '#8B5CF6',
            'loyalty': '#EC4899', 'wallet': '#14B8A6',
        }
        return colors.get(method, '#6B7280')
    
    # ─── 1. SUMMARY ──────────────────────────────────────────────────────────
    
    def get_summary(self):
        """Dashboard header summary"""
        cache_key = self._dashboard_cache_key('summary')
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        today_start = timezone.make_aware(datetime.combine(self.today, datetime.min.time()))
        today_end = timezone.make_aware(datetime.combine(self.today, datetime.max.time()))
        
        result = {
            'today_orders': self._scoped(self._scoped(Order.objects)).filter(
                created_at__range=(today_start, today_end),
                status__in=['paid', 'completed']
            ).count(),
            
            'today_sales': self._fmt(self._scoped(self._scoped(Order.objects)).filter(
                created_at__range=(today_start, today_end),
                status__in=['paid', 'completed']
            ).aggregate(total=Sum('total'))['total']),
            
            'total_customers': self._scoped(self._scoped(Customer.objects)).count(),
            'total_products': self._scoped(self._scoped(Product.objects)).filter(is_active=True).count(),
            'total_suppliers': self._scoped(self._scoped(Supplier.objects)).filter(is_active=True).count(),
            
            'low_stock_count': self._scoped(self._scoped(Product.objects)).filter(
                stock_quantity__lte=F('min_stock'), is_active=True
            ).count(),
            
            'out_of_stock_count': self._scoped(self._scoped(Product.objects)).filter(
                stock_quantity=0, is_active=True
            ).count(),
            
            'open_sessions': self._scoped(self._scoped(CashSession.objects)).filter(is_open=True).count(),
            'pending_orders': self._scoped(self._scoped(Order.objects)).filter(status='draft').count(),
            'total_employees': self._scoped(self._scoped(Employee.objects)).filter(status='active').count(),
        }
        
        cache.set(cache_key, result, 300)
        return result
    
    # ─── 2. KPI CARDS ──────────────────────────────────────────────────────
    
    def get_kpis(self, period='today'):
        """KPI card data"""
        start_date, end_date = self._get_date_range(period)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
        # Current period
        current_orders = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(start_dt, end_dt),
            status__in=['paid', 'completed']
        )
        
        total_sales = current_orders.aggregate(total=Sum('total'))['total'] or 0
        total_orders = current_orders.count()
        avg_order = total_sales / total_orders if total_orders > 0 else 0
        
        # Previous period
        period_days = (end_date - start_date).days + 1
        prev_start = start_date - timedelta(days=period_days)
        prev_end = start_date - timedelta(days=1)
        prev_start_dt = timezone.make_aware(datetime.combine(prev_start, datetime.min.time()))
        prev_end_dt = timezone.make_aware(datetime.combine(prev_end, datetime.max.time()))
        
        prev_orders = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(prev_start_dt, prev_end_dt),
            status__in=['paid', 'completed']
        )
        prev_sales = prev_orders.aggregate(total=Sum('total'))['total'] or 0
        prev_count = prev_orders.count()
        
        # Gross profit
        cogs = self._scoped(self._scoped(OrderItem.objects)).filter(
            order__created_at__range=(start_dt, end_dt),
            order__status__in=['paid', 'completed']
        ).aggregate(total=Sum(F('quantity') * F('product__cost_price')))['total'] or 0
        
        gross_profit = total_sales - cogs
        
        prev_cogs = self._scoped(self._scoped(OrderItem.objects)).filter(
            order__created_at__range=(prev_start_dt, prev_end_dt),
            order__status__in=['paid', 'completed']
        ).aggregate(total=Sum(F('quantity') * F('product__cost_price')))['total'] or 0
        prev_gross = prev_sales - prev_cogs
        
        # Customers (using id instead of created_at since Customer doesn't have created_at)
        total_customers = self._scoped(self._scoped(Customer.objects)).count()
        # Get customers with orders before start_date (approximate previous customers)
        prev_customers = self._scoped(self._scoped(Customer.objects)).filter(
            order__created_at__lt=start_dt
        ).distinct().count()
        
        return {
            'total_sales': self._fmt(total_sales),
            'total_sales_change': self._growth(prev_sales, total_sales),
            'orders': total_orders,
            'orders_change': self._growth(prev_count, total_orders),
            'avg_order': self._fmt(avg_order),
            'avg_order_change': 0,
            'customers': total_customers,
            'customers_change': self._growth(prev_customers, total_customers),
            'gross_profit': self._fmt(gross_profit),
            'gross_profit_change': self._growth(prev_gross, gross_profit),
        }
    
    # ─── 3. REVENUE ──────────────────────────────────────────────────────────
    
    def get_revenue(self, period='month'):
        """Revenue widget data"""
        start_date, end_date = self._get_date_range(period)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
        orders = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(start_dt, end_dt),
            status__in=['paid', 'completed']
        )
        
        total_revenue = orders.aggregate(total=Sum('total'))['total'] or 0
        
        cogs = self._scoped(self._scoped(OrderItem.objects)).filter(order__in=orders).aggregate(
            total=Sum(F('quantity') * F('product__cost_price'))
        )['total'] or 0
        
        profit = total_revenue - cogs
        
        invoice_due = self._scoped(self._scoped(Order.objects)).filter(
            status='draft',
            created_at__range=(start_dt, end_dt)
        ).aggregate(total=Sum('total'))['total'] or 0
        
        # Expenses (if accounting app is installed)
        try:
            expense_accounts = self._scoped(self._scoped(ChartOfAccount.objects)).filter(type='expense').values_list('id', flat=True)
            expenses = self._scoped(self._scoped(JournalEntryLine.objects)).filter(
                account_id__in=expense_accounts,
                entry__date__range=(start_date, end_date)
            ).aggregate(total=Sum('debit'))['total'] or 0
        except:
            expenses = 0
        
        # Previous period
        period_days = (end_date - start_date).days + 1
        prev_start = start_date - timedelta(days=period_days)
        prev_end = start_date - timedelta(days=1)
        prev_start_dt = timezone.make_aware(datetime.combine(prev_start, datetime.min.time()))
        prev_end_dt = timezone.make_aware(datetime.combine(prev_end, datetime.max.time()))
        
        prev_orders = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(prev_start_dt, prev_end_dt),
            status__in=['paid', 'completed']
        )
        prev_revenue = prev_orders.aggregate(total=Sum('total'))['total'] or 0
        prev_cogs = self._scoped(self._scoped(OrderItem.objects)).filter(order__in=prev_orders).aggregate(
            total=Sum(F('quantity') * F('product__cost_price'))
        )['total'] or 0
        prev_profit = prev_revenue - prev_cogs
        
        return {
            'profit': self._fmt(profit),
            'profit_growth': self._growth(prev_profit, profit),
            'invoice_due': self._fmt(invoice_due),
            'expenses': self._fmt(expenses),
            'revenue': self._fmt(total_revenue),
        }
    
    # ─── 4. SALES CHART ─────────────────────────────────────────────────────
    
    def get_sales_chart(self, period='year'):
        """Sales vs Purchase chart"""
        start_date, end_date = self._get_date_range(period)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
        # Determine grouping
        if period in ['today', 'week']:
            trunc_func = TruncDay
            fmt = '%d %b'
        elif period in ['month', 'quarter']:
            trunc_func = TruncWeek
            fmt = '%d %b'
        else:
            trunc_func = TruncMonth
            fmt = '%b %Y'
        
        # Sales
        sales = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(start_dt, end_dt),
            status__in=['paid', 'completed']
        ).annotate(date=trunc_func('created_at')).values('date').annotate(
            total=Sum('total')
        ).order_by('date')
        
        # Purchase (StockMovement from inventory app)
        purchase = self._scoped(self._scoped(StockMovement.objects)).filter(
            created_at__range=(start_dt, end_dt),
            movement_type__in=['purchase', 'receiving']
        ).annotate(date=trunc_func('created_at')).values('date').annotate(
            total=Sum('quantity')
        ).order_by('date')
        
        # Merge
        dates, sales_dict, purchase_dict = set(), {}, {}
        for item in sales:
            if item['date']:
                key = item['date'].strftime(fmt)
                dates.add(key)
                sales_dict[key] = float(item['total'] or 0)
        for item in purchase:
            if item['date']:
                key = item['date'].strftime(fmt)
                dates.add(key)
                purchase_dict[key] = float(item['total'] or 0)
        
        sorted_dates = sorted(list(dates))
        return {
            'labels': sorted_dates,
            'sales': [sales_dict.get(d, 0) for d in sorted_dates],
            'purchase': [purchase_dict.get(d, 0) for d in sorted_dates]
        }
    
    # ─── 5. PAYMENT METHODS ─────────────────────────────────────────────────
    
    def get_payment_methods(self, period='today'):
        """Payment method breakdown"""
        start_date, end_date = self._get_date_range(period)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
        payments = self._scoped(self._scoped(TenderedPayment.objects)).filter(
            created_at__range=(start_dt, end_dt)
        ).values('tender_type').annotate(total=Sum('amount')).order_by('-total')
        
        total = sum(p['total'] for p in payments) or 1
        
        return [{
            'label': p['tender_type'].replace('_', ' ').title(),
            'value': round((p['total'] / total) * 100, 1),
            'amount': float(p['total'] or 0),
            'color': self._payment_color(p['tender_type'])
        } for p in payments]
    
    # ─── 6. TODAY'S SUMMARY ─────────────────────────────────────────────────
    
    def get_today_summary(self):
        """Today's financial summary"""
        today_start = timezone.make_aware(datetime.combine(self.today, datetime.min.time()))
        today_end = timezone.make_aware(datetime.combine(self.today, datetime.max.time()))
        
        first_session = self._scoped(self._scoped(CashSession.objects)).filter(
            opened_at__date=self.today
        ).order_by('opened_at').first()
        
        opening = first_session.opening_balance if first_session else 0
        
        sales = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(today_start, today_end),
            status__in=['paid', 'completed']
        ).aggregate(total=Sum('total'))['total'] or 0
        
        refunds = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(today_start, today_end),
            status='refunded'
        ).aggregate(total=Sum('total'))['total'] or 0
        
        discounts = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(today_start, today_end),
            status__in=['paid', 'completed']
        ).aggregate(total=Sum('discount'))['total'] or 0
        
        net = sales - refunds - discounts
        
        return {
            'opening_balance': self._fmt(opening),
            'total_sales': self._fmt(sales),
            'total_refunds': self._fmt(refunds),
            'total_discounts': self._fmt(discounts),
            'net_sales': self._fmt(net),
            'closing_balance': self._fmt(opening + net),
        }
    
    # ─── 7. RECENT ORDERS ───────────────────────────────────────────────────
    
    def get_recent_orders(self, limit=10):
        """Recent orders"""
        orders = self._scoped(self._scoped(Order.objects)).select_related('customer').filter(
            status__in=['paid', 'completed']
        ).order_by('-created_at')[:limit]
        
        return [{
            'id': o.id,
            'order_number': o.order_number,
            'customer': o.customer.name if o.customer else 'Walk-in Customer',
            'amount': float(o.total or 0),
            'status': o.status,
            'payment_method': o.payment_method,
            'created_at': o.created_at.isoformat() if o.created_at else None,
        } for o in orders]
    
    # ─── 8. TOP PRODUCTS ────────────────────────────────────────────────────
    
    def get_top_products(self, limit=10, period='month'):
        """Top selling products"""
        start_date, end_date = self._get_date_range(period)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
        products = self._scoped(self._scoped(OrderItem.objects)).filter(
            order__created_at__range=(start_dt, end_dt),
            order__status__in=['paid', 'completed']
        ).values(
            'product__id', 'product__name', 'product__sku',
            'product__sales_price', 'product__image'
        ).annotate(
            total_sold=Sum('quantity'),
            total_revenue=Sum('subtotal')
        ).order_by('-total_sold')[:limit]
        
        result = []
        for p in products:
            # Growth (this month vs last month)
            today = self.today
            this_month_start = today.replace(day=1)
            last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
            
            this_month = self._scoped(self._scoped(OrderItem.objects)).filter(
                product_id=p['product__id'],
                order__status__in=['paid', 'completed'],
                order__created_at__date__gte=this_month_start
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            last_month = self._scoped(self._scoped(OrderItem.objects)).filter(
                product_id=p['product__id'],
                order__status__in=['paid', 'completed'],
                order__created_at__date__gte=last_month_start,
                order__created_at__date__lt=this_month_start
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            result.append({
                'id': p['product__id'],
                'name': p['product__name'],
                'sku': p['product__sku'],
                'price': float(p['product__sales_price'] or 0),
                'image': p['product__image'] or '',
                'sold': p['total_sold'] or 0,
                'revenue': float(p['total_revenue'] or 0),
                'growth': self._growth(last_month, this_month)
            })
        
        return result
    
    # ─── 9. LOW STOCK ──────────────────────────────────────────────────────
    
    def get_low_stock(self, limit=10):
        """Low stock products"""
        products = self._scoped(self._scoped(Product.objects)).filter(
            is_active=True,
            stock_quantity__lte=F('min_stock')
        ).select_related('category').order_by('stock_quantity')[:limit]
        
        return [{
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'category': p.category.name if p.category else None,
            'stock': p.stock_quantity,
            'minimum_stock': p.min_stock or 0,
            'unit': p.unit or 'pcs',
            'image': p.image or '',
            'status': 'Out of Stock' if p.stock_quantity == 0 else 'Low Stock',
        } for p in products]
    
    # ─── 10. ACTIVE SESSIONS ─────────────────────────────────────────────────
    
    def get_active_sessions(self):
        """Active cash sessions"""
        sessions = self._scoped(self._scoped(CashSession.objects)).filter(is_open=True).order_by('opened_at')
        
        result = []
        for s in sessions:
            duration = self.now - s.opened_at
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            
            total_sales = self._scoped(self._scoped(Order.objects)).filter(
                session=s,
                status__in=['paid', 'completed']
            ).aggregate(total=Sum('total'))['total'] or 0
            
            result.append({
                'id': s.id,
                'cashier': s.employee_name or 'Admin',
                'opened_at': s.opened_at.isoformat(),
                'duration': f"{hours}h {minutes}m",
                'total_sales': float(total_sales),
                'order_count': self._scoped(self._scoped(Order.objects)).filter(
                    session=s,
                    status__in=['paid', 'completed']
                ).count(),
            })
        
        return result
    
    # ─── 11. NOTIFICATIONS ──────────────────────────────────────────────────
    
    def get_recent_notifications(self, limit=10):
        """Recent notifications"""
        notifications = []
        
        # Low stock alerts
        for p in self._scoped(self._scoped(Product.objects)).filter(
            is_active=True,
            stock_quantity__lte=F('min_stock')
        )[:3]:
            notifications.append({
                'type': 'alert',
                'text': f'Low stock: {p.name} ({p.stock_quantity} left)',
                'time': 'Just now',
                'link': '#/inventory/products'
            })
        
        # Recent orders
        for o in self._scoped(self._scoped(Order.objects)).filter(
            status__in=['paid', 'completed']
        ).order_by('-created_at')[:5]:
            customer = o.customer.name if o.customer else 'Walk-in'
            notifications.append({
                'type': 'order',
                'text': f'Order #{o.order_number} from {customer}',
                'time': self._time_ago(o.created_at),
                'link': f'#/orders/{o.id}'
            })
        
        # Recent payments
        for p in self._scoped(self._scoped(TenderedPayment.objects)).select_related('order').order_by('-created_at')[:3]:
            order_no = p.order.order_number if p.order else 'Unknown'
            notifications.append({
                'type': 'payment',
                'text': f'Payment of ${float(p.amount):.2f} for #{order_no}',
                'time': self._time_ago(p.created_at),
                'link': f'#/orders/{p.order.id}' if p.order else '#/orders'
            })
        
        return notifications[:limit]
    
    # ─── 12. QUICK ACTIONS ──────────────────────────────────────────────────
    
    def get_quick_actions(self):
        """Quick action shortcuts"""
        return [
            {'id': 'new_sale', 'label': 'New Sale', 'icon': 'plus-circle', 'route': '#/pos'},
            {'id': 'new_order', 'label': 'New Order', 'icon': 'credit-card', 'route': '#/orders'},
            {'id': 'add_product', 'label': 'Add Product', 'icon': 'package-plus', 'route': '#/products'},
            {'id': 'add_customer', 'label': 'Add Customer', 'icon': 'user-plus', 'route': '#/customers'},
            {'id': 'expense', 'label': 'Expense', 'icon': 'dollar-sign', 'route': '#/accounting/expenses'},
            {'id': 'reports', 'label': 'Reports', 'icon': 'bar-chart-2', 'route': '#/reports/sales'},
        ]
    
    # ─── 13. ORDER STATISTICS ──────────────────────────────────────────────
    
    def get_order_statistics(self):
        """Order status breakdown"""
        stats = self._scoped(self._scoped(Order.objects)).values('status').annotate(count=Count('id'))
        
        result = {
            'completed': 0, 'draft': 0, 'cancelled': 0,
            'refunded': 0, 'pending': 0, 'partial_refunded': 0,
        }
        
        for stat in stats:
            if stat['status'] in result:
                result[stat['status']] = stat['count']
            else:
                result['pending'] += stat['count']
        
        return result
    
    # ─── 14. INVENTORY STATS ───────────────────────────────────────────────
    
    def get_inventory_stats(self):
        """Inventory statistics"""
        products = self._scoped(self._scoped(Product.objects)).filter(is_active=True)
        
        return {
            'total_products': products.count(),
            'total_stock': products.aggregate(total=Sum('stock_quantity'))['total'] or 0,
            'total_value': float(products.aggregate(
                total=Sum(F('stock_quantity') * F('cost_price'))
            )['total'] or 0),
            'low_stock': products.filter(stock_quantity__lte=F('min_stock')).count(),
            'out_of_stock': products.filter(stock_quantity=0).count(),
        }
    
    # ─── 15. CUSTOMER STATS ─────────────────────────────────────────────────
    

    def _dashboard_period(self, period='month'):
        """Normalize UI period names to the service's canonical ranges."""
        aliases = {
            '1d': 'today', 'day': 'today', 'today': 'today',
            '1w': 'week', 'weekly': 'week', 'week': 'week',
            '1m': 'month', 'monthly': 'month', 'month': 'month',
            '3m': 'quarter', 'quarter': 'quarter',
            '6m': 'year', '1y': 'year', 'year': 'year',
        }
        return aliases.get(str(period or '').strip().lower(), 'month')

    def _dashboard_cache_key(self, name, period=None, limit=None, extra=None):
        """Build a tenant/branch-safe cache key for dashboard responses."""
        request = self.request
        tenant = getattr(request, 'tenant', None) if request else None
        branch = getattr(request, 'branch', None) if request else None
        tenant_key = getattr(tenant, 'pk', None) or getattr(tenant, 'id', None) or 'global'
        branch_key = getattr(branch, 'pk', None) or getattr(branch, 'id', None) or 'all'
        bits = [str(name), str(tenant_key), str(branch_key)]
        if period is not None:
            bits.append(str(period))
        if limit is not None:
            bits.append(str(limit))
        if extra is not None:
            bits.append(str(extra))
        return 'dashboard:v2:' + ':'.join(bits)

    def get_top_customers(self, limit=10, period='month'):
        """Return ranked customers by completed sales in the selected period."""
        period = self._dashboard_period(period)
        start_date, end_date = self._get_date_range(period)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        limit = max(1, min(int(limit or 10), 100))
        orders = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(start_dt, end_dt),
            status__in=['paid', 'completed'],
            customer__isnull=False,
        )
        rows = list(orders.values('customer_id', 'customer__name').annotate(
            order_count=Count('id'), revenue=Sum('total')
        ).order_by('-revenue', '-order_count')[:limit])
        current_ids = [row['customer_id'] for row in rows]
        previous_start = start_date - (end_date - start_date) - timedelta(days=1)
        previous_end = start_date - timedelta(days=1)
        previous_start_dt = timezone.make_aware(datetime.combine(previous_start, datetime.min.time()))
        previous_end_dt = timezone.make_aware(datetime.combine(previous_end, datetime.max.time()))
        previous = dict(self._scoped(orders.model.objects).filter(
            created_at__range=(previous_start_dt, previous_end_dt),
            status__in=['paid', 'completed'], customer_id__in=current_ids,
        ).values('customer_id').annotate(revenue=Sum('total')).values_list('customer_id', 'revenue')) if current_ids else {}
        result = []
        for row in rows:
            revenue = float(row.get('revenue') or 0)
            previous_revenue = float(previous.get(row['customer_id']) or 0)
            result.append({
                'id': row['customer_id'],
                'name': row.get('customer__name') or 'Walk-in Customer',
                'orders': row['order_count'],
                'revenue': revenue,
                'growth': self._growth(previous_revenue, revenue),
            })
        return {'period': period, 'items': result}

    def get_top_categories(self, limit=10, period='month'):
        """Return ranked product categories by completed order-item quantity."""
        period = self._dashboard_period(period)
        start_date, end_date = self._get_date_range(period)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        limit = max(1, min(int(limit or 10), 100))
        rows = list(self._scoped(self._scoped(OrderItem.objects)).filter(
            order__created_at__range=(start_dt, end_dt),
            order__status__in=['paid', 'completed'],
        ).values('product__category_id', 'product__category__name').annotate(
            sales=Sum('quantity')
        ).order_by('-sales')[:limit])
        total = sum(int(row.get('sales') or 0) for row in rows)
        items = []
        for row in rows:
            sales = int(row.get('sales') or 0)
            items.append({
                'id': row.get('product__category_id'),
                'name': row.get('product__category__name') or 'Uncategorized',
                'sales': sales,
                'share': round((sales / total) * 100, 1) if total else 0,
            })
        return {'period': period, 'total_sales': total, 'items': items}

    def get_order_statistics_heatmap(self, period='week'):
        """Return a Mon-Sun by 2-hour order activity matrix for the heatmap widget."""
        period = self._dashboard_period(period)
        start_date, end_date = self._get_date_range(period)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        times = ['2 Am', '4 Am', '6 Am', '8 Am', '10 Am', '12 Am', '14 Pm', '16 Pm', '18 Am']
        cells = {(day, time): 0 for day in days for time in times}
        orders = self._scoped(self._scoped(Order.objects)).filter(created_at__range=(start_dt, end_dt)).only('created_at')
        for order in orders.iterator(chunk_size=1000):
            local_dt = timezone.localtime(order.created_at)
            bucket = min(max(((local_dt.hour // 2) * 2), 2), 18)
            time_label = f'{bucket} Am' if bucket in (2, 4, 6, 8, 10, 12, 18) else f'{bucket} Pm'
            key = (local_dt.strftime('%a'), time_label)
            if key in cells:
                cells[key] += 1
        flat_cells = [{'day': day, 'time': time, 'orders': cells[(day, time)]} for time in times for day in days]
        return {'period': period, 'days': days, 'times': times, 'cells': flat_cells, 'max_orders': max((cell['orders'] for cell in flat_cells), default=0)}

    def get_recent_transactions(self, transaction_type='sales', limit=10):
        """Return a normalized transaction feed for the dashboard tabbed table."""
        transaction_type = str(transaction_type or 'sales').lower()
        limit = max(1, min(int(limit or 10), 100))
        if transaction_type in ('sales', 'sale'):
            rows = []
            for order in self._scoped(self._scoped(Order.objects)).select_related('customer').order_by('-created_at')[:limit]:
                rows.append({
                    'id': order.id,
                    'reference': getattr(order, 'order_number', None) or f'ORD-{order.id:06d}',
                    'party': getattr(getattr(order, 'customer', None), 'name', None) or 'Walk-in Customer',
                    'date': order.created_at.isoformat() if order.created_at else None,
                    'amount': float(order.total or 0),
                    'status': order.status,
                })
            return {'type': 'sales', 'columns': ['reference', 'party', 'date', 'amount', 'status'], 'items': rows}
        try:
            from pos.models import PurchaseOrder
        except ImportError:
            PurchaseOrder = None
        if transaction_type in ('purchases', 'purchase') and PurchaseOrder is not None:
            rows = []
            for order in Purchaseself._scoped(self._scoped(Order.objects)).select_related('supplier').order_by('-created_at')[:limit]:
                supplier = getattr(order, 'supplier', None)
                rows.append({
                    'id': order.id,
                    'reference': getattr(order, 'order_number', None) or f'PO-{order.id:06d}',
                    'party': getattr(supplier, 'company', None) or getattr(supplier, 'name', None) or 'Supplier',
                    'date': order.created_at.isoformat() if order.created_at else None,
                    'amount': float(order.total or 0),
                    'status': order.status,
                })
            return {'type': 'purchases', 'columns': ['reference', 'party', 'date', 'amount', 'status'], 'items': rows}
        if transaction_type in ('invoices', 'invoice', 'quotations', 'quotation'):
            result = self.get_recent_transactions('sales', limit)
            result['type'] = 'invoices' if transaction_type.startswith('invoice') else 'quotations'
            return result
        try:
            from pos.models import CashTransaction
            queryset = self._scoped(self._scoped(CashTransaction.objects)).order_by('-created_at')
            if hasattr(CashTransaction, 'type'):
                queryset = queryset.filter(type='expense')
            rows = []
            for item in queryset[:limit]:
                rows.append({
                    'id': item.id,
                    'reference': f'EXP-{item.id:06d}',
                    'party': getattr(item, 'description', None) or 'Expense',
                    'date': item.created_at.isoformat() if getattr(item, 'created_at', None) else None,
                    'amount': float(getattr(item, 'amount', 0) or 0),
                    'status': 'completed',
                })
            return {'type': 'expenses', 'columns': ['reference', 'party', 'date', 'amount', 'status'], 'items': rows}
        except (ImportError, AttributeError):
            return {'type': transaction_type, 'columns': ['reference', 'party', 'date', 'amount', 'status'], 'items': []}

    def get_sales_statistics(self, period='year'):
        """Return aligned revenue and approved-expense time series for the chart."""
        normalized = self._dashboard_period(period)
        start_date, end_date = self._get_date_range(normalized)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        if normalized in ('today', 'week'):
            trunc_func = TruncDay
            label_format = '%d %b'
        elif normalized in ('month', 'quarter'):
            trunc_func = TruncWeek
            label_format = '%d %b'
        else:
            trunc_func = TruncMonth
            label_format = '%b %Y'
        sales_rows = self._scoped(self._scoped(Order.objects)).filter(
            created_at__range=(start_dt, end_dt), status__in=['paid', 'completed']
        ).annotate(bucket=trunc_func('created_at')).values('bucket').annotate(total=Sum('total'))
        sales_by_bucket = {row['bucket'].strftime(label_format): float(row['total'] or 0) for row in sales_rows if row['bucket']}
        expense_by_bucket = {}
        try:
            expense_rows = self._scoped(self._scoped(Expense.objects)).filter(
                date__range=(start_date, end_date), status=Expense.STATUS_APPROVED
            ).annotate(bucket=trunc_func('date')).values('bucket').annotate(total=Sum('amount'))
            expense_by_bucket = {row['bucket'].strftime(label_format): float(row['total'] or 0) for row in expense_rows if row['bucket']}
        except Exception:
            expense_by_bucket = {}
        labels = sorted(set(sales_by_bucket) | set(expense_by_bucket))
        revenue = [sales_by_bucket.get(label, 0) for label in labels]
        expense = [expense_by_bucket.get(label, 0) for label in labels]
        return {
            'period': normalized,
            'labels': labels,
            'revenue': revenue,
            'expense': expense,
            'total_revenue': round(sum(revenue), 2),
            'total_expense': round(sum(expense), 2),
        }

    def get_dashboard_overview(self, period='today'):
        """Return one authenticated dashboard payload for efficient initial loading."""
        return {
            'period': self._dashboard_period(period),
            'summary': self.get_summary(),
            'kpis': self.get_kpis(self._dashboard_period(period)),
            'sales_chart': self.get_sales_chart(self._dashboard_period(period)),
            'sales_statistics': self.get_sales_statistics('year'),
            'payment_methods': self.get_payment_methods(self._dashboard_period(period)),
            'today_summary': self.get_today_summary(),
            'recent_sales': self.get_recent_orders(10),
            'top_products': self.get_top_products(10, self._dashboard_period(period)),
            'low_stock': self.get_low_stock(10),
            'order_statistics': self.get_order_statistics(),
            'order_statistics_heatmap': self.get_order_statistics_heatmap('week'),
            'inventory_stats': self.get_inventory_stats(),
            'customer_stats': self.get_customer_stats(),
            'top_customers': self.get_top_customers(10, self._dashboard_period(period)),
            'top_categories': self.get_top_categories(10, self._dashboard_period(period)),
            'recent_transactions': self.get_recent_transactions('sales', 10),
        }

    def get_customer_stats(self):
        """Customer statistics"""
        total = self._scoped(self._scoped(Customer.objects)).count()
        
        # New customers this month - since Customer doesn't have created_at,
        # we use order creation date as a proxy
        this_month_start = self.today.replace(day=1)
        # Customers who placed their first order this month
        new = self._scoped(self._scoped(Customer.objects)).filter(
            order__created_at__date__gte=this_month_start
        ).distinct().count()
        
        # Returning customers (have more than 1 order)
        returning = self._scoped(self._scoped(Customer.objects)).annotate(
            order_count=Count('order')
        ).filter(order_count__gt=1).count()
        
        # Average order per customer
        avg_orders = self._scoped(self._scoped(Order.objects)).filter(
            status__in=['paid', 'completed']
        ).values('customer').annotate(
            count=Count('id')
        ).aggregate(avg=Avg('count'))['avg'] or 0
        
        return {
            'total': total,
            'new_this_month': new,
            'returning': returning,
            'avg_orders_per_customer': round(avg_orders, 1),
        }