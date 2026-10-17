# backend/backend/dashboard/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # ── Standardized API contract (new) ────────────────────────────────
    path('api/dashboard/overview/', views.StandardizedOverviewView.as_view(), name='dashboard-overview-v2'),
    path('api/dashboard/charts/sales-trend/', views.SalesTrendChartView.as_view(), name='dashboard-sales-trend'),
    path('api/dashboard/charts/sales-by-category/', views.SalesByCategoryChartView.as_view(), name='dashboard-sales-by-category'),
    path('api/dashboard/charts/top-products/', views.TopProductsChartView.as_view(), name='dashboard-top-products'),
    path('api/dashboard/charts/payment-methods/', views.PaymentMethodsChartView.as_view(), name='dashboard-payment-methods'),
    path('api/dashboard/charts/profit-loss/', views.ProfitLossChartView.as_view(), name='dashboard-profit-loss'),
    path('api/dashboard/charts/sales-heatmap/', views.SalesHeatmapChartView.as_view(), name='dashboard-sales-heatmap'),
    path('api/dashboard/charts/sales-performance/', views.SalesPerformanceChartView.as_view(), name='dashboard-sales-performance'),
    path('api/dashboard/inventory/summary/', views.InventorySummaryView.as_view(), name='dashboard-inventory-summary'),

    # ── Legacy endpoints (retained for backward compatibility) ──────────
    path('api/dashboard/legacy/overview/', views.DashboardOverviewView.as_view(), name='dashboard-overview-legacy'),
    path('api/dashboard/top-customers/', views.DashboardTopCustomersView.as_view(), name='dashboard-top-customers'),
    path('api/dashboard/top-categories/', views.DashboardTopCategoriesView.as_view(), name='dashboard-top-categories'),
    path('api/dashboard/order-statistics-heatmap/', views.DashboardOrderStatisticsHeatmapView.as_view(), name='dashboard-order-statistics-heatmap'),
    path('api/dashboard/recent-transactions/', views.DashboardRecentTransactionsView.as_view(), name='dashboard-recent-transactions'),
    path('api/dashboard/sales-statistics/', views.DashboardSalesStatisticsView.as_view(), name='dashboard-sales-statistics'),
    path('api/dashboard/summary/', views.DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('api/dashboard/kpis/', views.DashboardKPIsView.as_view(), name='dashboard-kpis'),
    path('api/dashboard/revenue/', views.DashboardRevenueView.as_view(), name='dashboard-revenue'),
    path('api/dashboard/sales-chart/', views.DashboardSalesChartView.as_view(), name='dashboard-sales-chart'),
    path('api/dashboard/payment-methods-legacy/', views.DashboardPaymentMethodsView.as_view(), name='dashboard-payment-methods-legacy'),
    path('api/dashboard/today-summary/', views.DashboardTodaySummaryView.as_view(), name='dashboard-today-summary'),
    path('api/dashboard/recent-orders/', views.DashboardRecentOrdersView.as_view(), name='dashboard-recent-orders'),
    path('api/dashboard/top-products-legacy/', views.DashboardTopProductsView.as_view(), name='dashboard-top-products-legacy'),
    path('api/dashboard/low-stock/', views.DashboardLowStockView.as_view(), name='dashboard-low-stock'),
    path('api/dashboard/active-sessions/', views.DashboardActiveSessionsView.as_view(), name='dashboard-active-sessions'),
    path('api/dashboard/recent-notifications/', views.DashboardRecentNotificationsView.as_view(), name='dashboard-recent-notifications'),
    path('api/dashboard/quick-actions/', views.DashboardQuickActionsView.as_view(), name='dashboard-quick-actions'),
    path('api/dashboard/order-statistics/', views.DashboardOrderStatisticsView.as_view(), name='dashboard-order-statistics'),
    path('api/dashboard/inventory-stats/', views.DashboardInventoryStatsView.as_view(), name='dashboard-inventory-stats'),
    path('api/dashboard/customer-stats/', views.DashboardCustomerStatsView.as_view(), name='dashboard-customer-stats'),
]