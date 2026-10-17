# backend/backend/dashboard/utils/helpers.py

from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone


def get_date_range(period):
    """Get start and end dates for a given period"""
    today = timezone.now().date()
    
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
    else:
        return today.replace(day=1), today


def format_currency(amount):
    """Format currency value"""
    if amount is None:
        return 0.0
    return float(amount)


def calculate_growth(previous, current):
    """Calculate percentage growth between two values"""
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / abs(previous)) * 100, 1)


def time_ago(dt, now=None):
    """Convert datetime to human-readable time ago"""
    if not dt:
        return 'Just now'
    
    if now is None:
        now = timezone.now()
    
    diff = now - dt
    
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
    else:
        return 'Just now'


def get_payment_color(method):
    """Get color for payment method"""
    colors = {
        'cash': '#10B981',
        'card': '#6366F1',
        'bank': '#60A5FA',
        'gift_card': '#F59E0B',
        'store_credit': '#8B5CF6',
        'loyalty': '#EC4899',
        'wallet': '#14B8A6',
    }
    return colors.get(method, '#6B7280')


def get_status_badge(status):
    """Get CSS class for order status badge"""
    badges = {
        'paid': 'bg-emerald-100 text-emerald-700',
        'completed': 'bg-emerald-100 text-emerald-700',
        'draft': 'bg-slate-100 text-slate-600',
        'refunded': 'bg-rose-100 text-rose-700',
        'cancelled': 'bg-red-100 text-red-700',
        'partial_refunded': 'bg-amber-100 text-amber-700',
        'pending': 'bg-yellow-100 text-yellow-700',
    }
    return badges.get(status, 'bg-slate-100 text-slate-600')


def get_period_label(period):
    """Get human-readable label for period"""
    labels = {
        'today': 'Today',
        'week': 'This Week',
        'month': 'This Month',
        'quarter': 'This Quarter',
        'year': 'This Year',
    }
    return labels.get(period, period)