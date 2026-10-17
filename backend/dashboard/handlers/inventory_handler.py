# backend/backend/dashboard/handlers/inventory_handler.py

from django.db.models import Sum, F
from django.utils import timezone
from pos.models import Product, Supplier

from ..utils.helpers import format_currency, get_date_range


class InventoryHandler:
    """Handles all inventory-related dashboard data"""
    
    def __init__(self, request=None):
        self.request = request
    
    def get_summary(self):
        """Get inventory summary for dashboard header"""
        products = Product.objects.filter(is_active=True)
        
        return {
            'total_products': products.count(),
            'low_stock_count': products.filter(
                stock_quantity__lte=F('min_stock')
            ).count(),
            'out_of_stock_count': products.filter(stock_quantity=0).count(),
            'total_suppliers': Supplier.objects.filter(is_active=True).count(),
        }
    
    def get_low_stock(self, limit=10):
        """Get low stock products"""
        products = Product.objects.filter(
            is_active=True,
            stock_quantity__lte=F('min_stock')
        ).select_related('category').order_by('stock_quantity')[:limit]
        
        result = []
        for p in products:
            status = 'Out of Stock' if p.stock_quantity == 0 else 'Low Stock'
            result.append({
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'category': p.category.name if p.category else None,
                'stock': p.stock_quantity,
                'minimum_stock': p.min_stock or 0,
                'unit': p.unit or 'pcs',
                'image': p.image or '',
                'status': status,
            })
        
        return result
    
    def get_inventory_stats(self):
        """Get inventory statistics"""
        products = Product.objects.filter(is_active=True)
        
        total_products = products.count()
        total_stock = products.aggregate(total=Sum('stock_quantity'))['total'] or 0
        total_value = products.aggregate(
            total=Sum(F('stock_quantity') * F('cost_price'))
        )['total'] or 0
        
        low_stock = products.filter(
            stock_quantity__lte=F('min_stock')
        ).count()
        
        out_of_stock = products.filter(stock_quantity=0).count()
        
        return {
            'total_products': total_products,
            'total_stock': total_stock,
            'total_value': float(total_value),
            'low_stock': low_stock,
            'out_of_stock': out_of_stock,
        }