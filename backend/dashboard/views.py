# backend/backend/dashboard/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from saas.permissions import HasActiveTenant, TenantRBACPermission
from .services.dashboard_service import DashboardService


def _safe_limit(request, default=10, maximum=100):
    try:
        value = int(request.query_params.get('limit', default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, 1), maximum)



class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        return Response(DashboardService(request).get_summary())


class DashboardKPIsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = request.query_params.get('period', 'today')
        return Response(DashboardService(request).get_kpis(period))


class DashboardSalesChartView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = request.query_params.get('period', 'today')
        return Response(DashboardService(request).get_sales_chart(period))


class DashboardPaymentMethodsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = request.query_params.get('period', 'today')
        return Response(DashboardService(request).get_payment_methods(period))


class DashboardTodaySummaryView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        return Response(DashboardService(request).get_today_summary())


class DashboardRecentOrdersView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        limit = _safe_limit(request)
        return Response(DashboardService(request).get_recent_orders(limit))


class DashboardTopProductsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        limit = _safe_limit(request)
        period = request.query_params.get('period', 'today')
        return Response(DashboardService(request).get_top_products(limit, period))


class DashboardLowStockView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        limit = _safe_limit(request)
        return Response(DashboardService(request).get_low_stock(limit))


class DashboardActiveSessionsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        return Response(DashboardService(request).get_active_sessions())


class DashboardRecentNotificationsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        limit = _safe_limit(request)
        return Response(DashboardService(request).get_recent_notifications(limit))


class DashboardQuickActionsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        return Response(DashboardService(request).get_quick_actions())


class DashboardOrderStatisticsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        return Response(DashboardService(request).get_order_statistics())


class DashboardInventoryStatsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        return Response(DashboardService(request).get_inventory_stats())


class DashboardCustomerStatsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        return Response(DashboardService(request).get_customer_stats())


class DashboardRevenueView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = request.query_params.get('period', 'today')
        return Response(DashboardService(request).get_revenue(period))

class DashboardTopCustomersView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        limit = min(max(_safe_limit(request), 1), 100)
        period = request.query_params.get('period', 'month')
        return Response(DashboardService(request).get_top_customers(limit, period))


class DashboardTopCategoriesView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        limit = min(max(_safe_limit(request), 1), 100)
        period = request.query_params.get('period', 'month')
        return Response(DashboardService(request).get_top_categories(limit, period))


class DashboardOrderStatisticsHeatmapView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = request.query_params.get('period', 'week')
        return Response(DashboardService(request).get_order_statistics_heatmap(period))


class DashboardRecentTransactionsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        limit = min(max(_safe_limit(request), 1), 100)
        transaction_type = request.query_params.get('type', 'sales')
        return Response(DashboardService(request).get_recent_transactions(transaction_type, limit))


class DashboardSalesStatisticsView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = request.query_params.get('period', 'year')
        return Response(DashboardService(request).get_sales_statistics(period))


class DashboardOverviewView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = request.query_params.get('period', 'today')
        return Response(DashboardService(request).get_dashboard_overview(period))


# ═══════════════════════════════════════════════════════════════════════════
# Standardized Chart Endpoints (new API contract)
# ═══════════════════════════════════════════════════════════════════════════

from .services.standardized_service import (
    StandardizedDashboardService, VALID_PERIODS, VALID_GROUP_BY,
)
from rest_framework.exceptions import ParseError


def _validated_period(request, default='month'):
    period = request.query_params.get('period', default)
    if period not in VALID_PERIODS:
        raise ParseError(f"Invalid period '{period}'.  Choose from: {', '.join(sorted(VALID_PERIODS))}")
    return period


def _validated_group_by(request):
    gb = request.query_params.get('group_by')
    if gb is not None and gb not in VALID_GROUP_BY - {None}:
        raise ParseError(f"Invalid group_by '{gb}'.  Choose from: hour, day, week, month")
    return gb


def _safe_limit_v2(request, default=10, maximum=100):
    try:
        value = int(request.query_params.get('limit', default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, 1), maximum)


class StandardizedOverviewView(APIView):
    """GET /api/dashboard/overview/ - lightweight KPI cards with sparklines."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = _validated_period(request, 'today')
        return Response(StandardizedDashboardService(request).get_overview(period))


class SalesTrendChartView(APIView):
    """GET /api/dashboard/charts/sales-trend/ - gross_sales / net_sales / transactions time series."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = _validated_period(request)
        group_by = _validated_group_by(request)
        return Response(StandardizedDashboardService(request).get_sales_trend(period, group_by))


class SalesByCategoryChartView(APIView):
    """GET /api/dashboard/charts/sales-by-category/ - revenue + quantity per category."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = _validated_period(request)
        return Response(StandardizedDashboardService(request).get_sales_by_category(period))


class TopProductsChartView(APIView):
    """GET /api/dashboard/charts/top-products/ - ranked products with revenue + quantity."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = _validated_period(request)
        limit = _safe_limit_v2(request)
        return Response(StandardizedDashboardService(request).get_top_products(period, limit))


class PaymentMethodsChartView(APIView):
    """GET /api/dashboard/charts/payment-methods/   -  amount + transactions + percentage."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = _validated_period(request)
        return Response(StandardizedDashboardService(request).get_payment_methods(period))


class ProfitLossChartView(APIView):
    """GET /api/dashboard/charts/profit-loss/   -  revenue / COGS / gross_profit time series."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = _validated_period(request)
        group_by = _validated_group_by(request)
        return Response(StandardizedDashboardService(request).get_profit_loss(period, group_by))


class SalesHeatmapChartView(APIView):
    """GET /api/dashboard/charts/sales-heatmap/   -  day × hour matrix with revenue + transactions."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = _validated_period(request, 'week')
        return Response(StandardizedDashboardService(request).get_sales_heatmap(period))


class SalesPerformanceChartView(APIView):
    """GET /api/dashboard/charts/sales-performance/   -  sales + transactions + AOV per period."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        period = _validated_period(request)
        group_by = _validated_group_by(request)
        return Response(StandardizedDashboardService(request).get_sales_performance(period, group_by))


class InventorySummaryView(APIView):
    """GET /api/dashboard/inventory/summary/   -  SKU counts + inventory value."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        return Response(StandardizedDashboardService(request).get_inventory_summary())

