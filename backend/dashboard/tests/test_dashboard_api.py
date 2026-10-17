from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from dashboard import views
from saas.permissions import TenantRBACPermission


class DashboardApiContractTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, pk=1)

    def get(self, view_class, path, params=None):
        request = self.factory.get(path, params or {})
        force_authenticate(request, user=self.user)
        with patch.object(views.HasActiveTenant, "has_permission", return_value=True), \
             patch.object(TenantRBACPermission, "has_permission", return_value=True):
            response = view_class.as_view()(request)
        response.render()
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_overview_returns_composite_dashboard_payload(self):
        payload = {'period': 'today', 'summary': {}, 'kpis': {}, 'sales_chart': {}}
        with patch('dashboard.views.DashboardService.get_dashboard_overview', return_value=payload) as method:
            result = self.get(views.DashboardOverviewView, '/api/dashboard/overview/', {'period': 'today'})
        self.assertEqual(result, payload)
        method.assert_called_once_with('today')

    def test_top_customers_passes_limit_and_period(self):
        payload = {'period': 'month', 'items': []}
        with patch('dashboard.views.DashboardService.get_top_customers', return_value=payload) as method:
            result = self.get(views.DashboardTopCustomersView, '/api/dashboard/top-customers/', {'limit': '5', 'period': 'month'})
        self.assertEqual(result, payload)
        method.assert_called_once_with(5, 'month')

    def test_top_categories_passes_limit_and_period(self):
        payload = {'period': 'week', 'total_sales': 0, 'items': []}
        with patch('dashboard.views.DashboardService.get_top_categories', return_value=payload) as method:
            result = self.get(views.DashboardTopCategoriesView, '/api/dashboard/top-categories/', {'limit': '8', 'period': 'week'})
        self.assertEqual(result, payload)
        method.assert_called_once_with(8, 'week')

    def test_heatmap_passes_period(self):
        payload = {'period': 'week', 'days': [], 'times': [], 'cells': [], 'max_orders': 0}
        with patch('dashboard.views.DashboardService.get_order_statistics_heatmap', return_value=payload) as method:
            result = self.get(views.DashboardOrderStatisticsHeatmapView, '/api/dashboard/order-statistics-heatmap/', {'period': 'week'})
        self.assertEqual(result, payload)
        method.assert_called_once_with('week')

    def test_transactions_passes_type_and_limit(self):
        payload = {'type': 'expenses', 'columns': [], 'items': []}
        with patch('dashboard.views.DashboardService.get_recent_transactions', return_value=payload) as method:
            result = self.get(views.DashboardRecentTransactionsView, '/api/dashboard/recent-transactions/', {'type': 'expenses', 'limit': '7'})
        self.assertEqual(result, payload)
        method.assert_called_once_with('expenses', 7)

    def test_sales_statistics_passes_period(self):
        payload = {'period': 'year', 'labels': [], 'revenue': [], 'expense': []}
        with patch('dashboard.views.DashboardService.get_sales_statistics', return_value=payload) as method:
            result = self.get(views.DashboardSalesStatisticsView, '/api/dashboard/sales-statistics/', {'period': 'year'})
        self.assertEqual(result, payload)
        method.assert_called_once_with('year')

    def test_dashboard_endpoint_requires_authentication(self):
        request = self.factory.get('/api/dashboard/top-customers/')
        response = views.DashboardTopCustomersView.as_view()(request)
        self.assertEqual(response.status_code, 401)
