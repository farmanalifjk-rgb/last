# backend/backend/dashboard/handlers/payment_handler.py

from django.db.models import F, Sum
from django.utils import timezone

from pos.models import CashSession, Order
from payments.models import TenderedPayment

from ..utils.helpers import calculate_growth, format_currency, get_date_range
from datetime import datetime, timedelta

class PaymentHandler:
    """Handles all payment-related dashboard data"""
    
    def __init__(self, request=None):
        self.request = request
        self.now = timezone.now()
    
    def get_today_summary(self):
        """Get today's financial summary"""
        today = self.now.date()
        today_start = timezone.make_aware(
            datetime.combine(today, datetime.min.time())
        )
        today_end = timezone.make_aware(
            datetime.combine(today, datetime.max.time())
        )
        
        # Opening balance (first cash session of the day)
        first_session = CashSession.objects.filter(
            opened_at__date=today
        ).order_by('opened_at').first()
        
        opening_balance = first_session.opening_balance if first_session else 0
        
        # Total sales today
        total_sales = Order.objects.filter(
            created_at__range=(today_start, today_end),
            status__in=['paid', 'completed']
        ).aggregate(total=Sum('total'))['total'] or 0
        
        # Total refunds today
        total_refunds = Order.objects.filter(
            created_at__range=(today_start, today_end),
            status='refunded'
        ).aggregate(total=Sum('total'))['total'] or 0
        
        # Total discounts today
        total_discounts = Order.objects.filter(
            created_at__range=(today_start, today_end),
            status__in=['paid', 'completed']
        ).aggregate(total=Sum('discount'))['total'] or 0
        
        net_sales = total_sales - total_refunds - total_discounts
        closing_balance = opening_balance + net_sales
        
        return {
            'opening_balance': format_currency(opening_balance),
            'total_sales': format_currency(total_sales),
            'total_refunds': format_currency(total_refunds),
            'total_discounts': format_currency(total_discounts),
            'net_sales': format_currency(net_sales),
            'closing_balance': format_currency(closing_balance),
        }
    
    def get_active_sessions(self):
        """Get currently open cash sessions"""
        sessions = CashSession.objects.filter(
            is_open=True
        ).order_by('opened_at')
        
        result = []
        for session in sessions:
            # Calculate duration
            duration = self.now - session.opened_at
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            
            # Get sales for this session
            total_sales = Order.objects.filter(
                session=session,
                status__in=['paid', 'completed']
            ).aggregate(total=Sum('total'))['total'] or 0
            
            result.append({
                'id': session.id,
                'cashier': session.employee_name or 'Admin',
                'opened_at': session.opened_at.isoformat(),
                'duration': f"{hours}h {minutes}m",
                'total_sales': float(total_sales),
                'order_count': Order.objects.filter(
                    session=session,
                    status__in=['paid', 'completed']
                ).count(),
            })
        
        return result
    
    def get_revenue(self, period='month'):
        """Get revenue widget data"""
        start_date, end_date = get_date_range(period)
        start_datetime = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_datetime = timezone.make_aware(
            datetime.combine(end_date, datetime.max.time())
        )
        
        # Current period
        orders = Order.objects.filter(
            created_at__range=(start_datetime, end_datetime),
            status__in=['paid', 'completed']
        )
        
        total_revenue = orders.aggregate(total=Sum('total'))['total'] or 0
        
        # Cost of goods
        from pos.models import OrderItem
        cogs = OrderItem.objects.filter(
            order__in=orders
        ).aggregate(
            total=Sum(F('quantity') * F('product__cost_price'))
        )['total'] or 0
        
        profit = total_revenue - cogs
        
        # Invoice due (pending orders)
        invoice_due = Order.objects.filter(
            status='draft',
            created_at__range=(start_datetime, end_datetime)
        ).aggregate(total=Sum('total'))['total'] or 0
        
        # Expenses from accounting
        from accounting.models import ChartOfAccount, JournalEntryLine
        expense_account = ChartOfAccount.objects.filter(
            type='expense'
        ).values_list('id', flat=True)
        
        expenses = JournalEntryLine.objects.filter(
            account_id__in=expense_account,
            entry__date__range=(start_date, end_date)
        ).aggregate(total=Sum('debit'))['total'] or 0
        
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
        prev_revenue = prev_orders.aggregate(total=Sum('total'))['total'] or 0
        prev_profit = prev_revenue - (OrderItem.objects.filter(
            order__in=prev_orders
        ).aggregate(total=Sum(F('quantity') * F('product__cost_price')))['total'] or 0)
        
        profit_growth = calculate_growth(prev_profit, profit)
        
        return {
            'profit': format_currency(profit),
            'profit_growth': profit_growth,
            'invoice_due': format_currency(invoice_due),
            'expenses': format_currency(expenses),
            'revenue': format_currency(total_revenue),
        }