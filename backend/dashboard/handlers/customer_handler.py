# backend/backend/dashboard/handlers/customer_handler.py

from django.db.models import Count, Avg, Sum
from django.utils import timezone

from pos.models import Customer, Order

from ..utils.helpers import format_currency, calculate_growth


class CustomerHandler:
    """Handles all customer-related dashboard data"""
    
    def __init__(self, request=None):
        self.request = request
        self.today = timezone.now().date()
    
    def get_total_customers(self, up_to_date=None):
        """Get total customers count"""
        qs = Customer.objects.all()
        if up_to_date:
            qs = qs.filter(created_at__date__lte=up_to_date)
        return qs.count()
    
    def get_summary(self):
        """Get customer summary for dashboard header"""
        return {
            'total_customers': Customer.objects.count(),
        }
    
    def get_customer_stats(self):
        """Get customer insights"""
        total_customers = Customer.objects.count()
        
        # New customers this month
        this_month_start = self.today.replace(day=1)
        new_customers = Customer.objects.filter(
            created_at__date__gte=this_month_start
        ).count()
        
        # Returning customers (have more than 1 order)
        returning = Customer.objects.annotate(
            order_count=Count('orders')
        ).filter(order_count__gt=1).count()
        
        # Average order per customer
        avg_orders = Order.objects.filter(
            status__in=['paid', 'completed']
        ).values('customer').annotate(
            count=Count('id')
        ).aggregate(avg=Avg('count'))['avg'] or 0
        
        return {
            'total': total_customers,
            'new_this_month': new_customers,
            'returning': returning,
            'avg_orders_per_customer': round(avg_orders, 1),
        }
    
    def get_recent_customers(self, limit=10):
        """Get recent customers"""
        customers = Customer.objects.order_by('-created_at')[:limit]
        
        result = []
        for c in customers:
            order_count = c.orders.filter(status__in=['paid', 'completed']).count()
            total_spent = c.orders.filter(
                status__in=['paid', 'completed']
            ).aggregate(total=Sum('total'))['total'] or 0
            
            result.append({
                'id': c.id,
                'name': c.name,
                'email': c.email,
                'phone': c.phone,
                'orders': order_count,
                'total_spent': float(total_spent),
                'joined_at': c.created_at.isoformat() if c.created_at else None,
            })
        
        return result