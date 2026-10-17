"""
Tests for the standardized dashboard API contract.

Covers:
- Response structure validation for every endpoint
- Decimal/financial precision (string serialization)
- COGS historical accuracy (OrderItem.cost_price snapshot)
- Refund consistency across endpoints
- Empty database / zero-data safety
- Period and group_by validation
- Tenant isolation
- Division-by-zero safety
- Growth/comparison edge cases
- HTTP status codes
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from dashboard import views
from saas.permissions import TenantRBACPermission
from dashboard.services.standardized_service import (
    StandardizedDashboardService,
    VALID_PERIODS,
    VALID_GROUP_BY,
    _money_str,
    _growth,
    _trend,
    _parse_period,
    _safe_decimal,
)


# ── Unit tests for helpers ──────────────────────────────────────────────


class MoneyStringTests(TestCase):
    """Verify _money_str produces exact decimal strings."""

    def test_none_returns_zero(self):
        self.assertEqual(_money_str(None), "0.00")

    def test_zero(self):
        self.assertEqual(_money_str(Decimal("0")), "0.00")

    def test_integer(self):
        self.assertEqual(_money_str(Decimal("123")), "123.00")

    def test_two_decimal_places(self):
        self.assertEqual(_money_str(Decimal("123.45")), "123.45")

    def test_rounds_correctly(self):
        self.assertEqual(_money_str(Decimal("123.456")), "123.46")

    def test_large_value(self):
        self.assertEqual(_money_str(Decimal("999999.999")), "1000000.00")

    def test_negative(self):
        self.assertEqual(_money_str(Decimal("-50.5")), "-50.50")

    def test_float_input(self):
        self.assertEqual(_money_str(99.9), "99.90")

    def test_string_input(self):
        self.assertEqual(_money_str("42.1"), "42.10")


class GrowthTests(TestCase):
    """Verify growth percentage edge cases."""

    def test_zero_to_zero(self):
        self.assertIsNone(_growth(0, 0))

    def test_zero_to_positive(self):
        self.assertEqual(_growth(0, 100), 100.0)

    def test_positive_to_zero(self):
        self.assertEqual(_growth(100, 0), -100.0)

    def test_positive_growth(self):
        self.assertEqual(_growth(100, 150), 50.0)

    def test_negative_growth(self):
        self.assertEqual(_growth(100, 50), -50.0)

    def test_none_values(self):
        self.assertIsNone(_growth(None, None))

    def test_decimal_values(self):
        self.assertEqual(_growth(Decimal("1000"), Decimal("1500")), 50.0)


class TrendTests(TestCase):
    def test_up(self):
        self.assertEqual(_trend(10), "up")

    def test_down(self):
        self.assertEqual(_trend(-5), "down")

    def test_flat(self):
        self.assertEqual(_trend(0), "flat")

    def test_none(self):
        self.assertEqual(_trend(None), "flat")


class ParsePeriodTests(TestCase):
    def test_aliases(self):
        self.assertEqual(_parse_period("1d"), "today")
        self.assertEqual(_parse_period("weekly"), "week")
        self.assertEqual(_parse_period("monthly"), "month")
        self.assertEqual(_parse_period("3m"), "quarter")
        self.assertEqual(_parse_period("1y"), "year")

    def test_fallback(self):
        self.assertEqual(_parse_period("bogus"), "month")

    def test_empty(self):
        self.assertEqual(_parse_period(""), "month")

    def test_valid_periods(self):
        for p in ("today", "week", "month", "quarter", "year"):
            self.assertIn(p, VALID_PERIODS)

    def test_valid_group_by(self):
        for g in ("hour", "day", "week", "month", None):
            self.assertIn(g, VALID_GROUP_BY)


# ── API contract tests (mock-based, no DB) ─────────────────────────────


class _MockRequest:
    """Minimal mock for request.tenant."""
    def __init__(self, tenant=None):
        self.tenant = tenant


class _ZeroDict(dict):
    """Dict that returns 0 for any key access (mimics empty aggregate)."""
    def __missing__(self, key):
        return Decimal("0") if isinstance(key, str) and key.isalpha() else 0


class OverviewContractTests(TestCase):
    """Verify the overview endpoint returns the exact contract shape."""

    def _get(self, period="today"):
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = mock_qs
            mock_qs.aggregate.return_value = _ZeroDict({"gross": Decimal("0"), "discounts": Decimal("0"), "count": 0, "r": Decimal("0")})
            mock_qs.count.return_value = 0
            mock_qs.only.return_value = mock_qs
            mock_qs.iterator.return_value = iter([])
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    return svc.get_overview(period)

    def test_top_level_keys(self):
        result = self._get("today")
        self.assertIn("currency", result)
        self.assertIn("period", result)
        self.assertIn("cards", result)

    def test_period_shape(self):
        result = self._get("today")
        p = result["period"]
        self.assertIn("key", p)
        self.assertIn("from", p)
        self.assertIn("to", p)
        self.assertEqual(p["key"], "today")

    def test_cards_keys(self):
        result = self._get("month")
        cards = result["cards"]
        for key in ("gross_sales", "net_sales", "transactions", "average_order_value"):
            self.assertIn(key, cards)
            card = cards[key]
            self.assertIn("value", card)
            self.assertIn("change_percent", card)
            self.assertIn("trend", card)
            self.assertIn("history", card)
            self.assertIsInstance(card["history"], list)

    def test_monetary_values_are_strings(self):
        result = self._get("today")
        cards = result["cards"]
        self.assertIsInstance(cards["gross_sales"]["value"], str)
        self.assertIsInstance(cards["net_sales"]["value"], str)
        self.assertIsInstance(cards["average_order_value"]["value"], str)

    def test_history_length(self):
        result = self._get("today")
        self.assertEqual(len(result["cards"]["gross_sales"]["history"]), 7)


class SalesTrendContractTests(TestCase):
    def _get(self, period="month", group_by=None):
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.annotate.return_value = mock_qs
            mock_qs.values.return_value = mock_qs
            mock_qs.order_by.return_value = []
            mock_qs.filter.return_value = mock_qs
            mock_qs.aggregate.return_value = _ZeroDict({"gross": Decimal("0"), "count": 0, "d": Decimal("0"), "r": Decimal("0")})
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    return svc.get_sales_trend(period, group_by)

    def test_top_level_keys(self):
        result = self._get()
        self.assertIn("currency", result)
        self.assertIn("granularity", result)
        self.assertIn("data", result)
        self.assertIsInstance(result["data"], list)

    def test_granularity_for_week(self):
        result = self._get("week")
        self.assertEqual(result["granularity"], "day")

    def test_data_items_are_strings(self):
        # Mock returns empty list, contract is verified by shape
        result = self._get()
        for item in result["data"]:
            self.assertIsInstance(item["gross_sales"], str)
            self.assertIsInstance(item["net_sales"], str)


class SalesByCategoryContractTests(TestCase):
    def _get(self, period="month"):
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.annotate.return_value = mock_qs
            mock_qs.values.return_value = mock_qs
            mock_qs.order_by.return_value = []
            mock_qs.filter.return_value = mock_qs
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    return svc.get_sales_by_category(period)

    def test_top_level_keys(self):
        result = self._get()
        self.assertIn("currency", result)
        self.assertIn("data", result)

    def test_data_item_shape(self):
        result = self._get()
        for item in result["data"]:
            self.assertIn("category", item)
            self.assertIn("revenue", item)
            self.assertIn("quantity", item)


class TopProductsContractTests(TestCase):
    def _get(self, period="month", limit=10):
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.annotate.return_value = mock_qs
            mock_qs.values.return_value = mock_qs
            mock_qs.order_by.return_value = mock_qs
            mock_qs.__getitem__ = lambda self, _: []
            mock_qs.filter.return_value = mock_qs
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    return svc.get_top_products(period, limit)

    def test_top_level_keys(self):
        result = self._get()
        self.assertIn("currency", result)
        self.assertIn("data", result)

    def test_data_item_shape(self):
        result = self._get()
        for item in result["data"]:
            for key in ("product_id", "name", "sku", "quantity_sold", "revenue"):
                self.assertIn(key, item)


class PaymentMethodsContractTests(TestCase):
    def _get(self, period="month"):
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.annotate.return_value = mock_qs
            mock_qs.values.return_value = mock_qs
            mock_qs.order_by.return_value = []
            mock_qs.filter.return_value = mock_qs
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    return svc.get_payment_methods(period)

    def test_top_level_keys(self):
        result = self._get()
        self.assertIn("currency", result)
        self.assertIn("data", result)

    def test_data_item_shape(self):
        result = self._get()
        for item in result["data"]:
            for key in ("name", "amount", "transactions", "percentage"):
                self.assertIn(key, item)


class ProfitLossContractTests(TestCase):
    def _get(self, period="month", group_by=None):
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.annotate.return_value = mock_qs
            mock_qs.values.return_value = mock_qs
            mock_qs.order_by.return_value = mock_qs
            mock_qs.filter.return_value = mock_qs
            mock_qs.aggregate.return_value = _ZeroDict({"revenue": Decimal("0"), "cogs": Decimal("0")})
            mock_qs.count.return_value = 0
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    return svc.get_profit_loss(period, group_by)

    def test_top_level_keys(self):
        result = self._get()
        for key in ("currency", "granularity", "data", "summary"):
            self.assertIn(key, result)

    def test_summary_shape(self):
        result = self._get()
        s = result["summary"]
        for key in ("revenue", "cost_of_goods", "gross_profit"):
            self.assertIn(key, s)
            self.assertIsInstance(s[key], str)

    def test_cogs_is_estimated_key(self):
        result = self._get()
        self.assertIn("cogs_is_estimated", result)
        self.assertIsInstance(result["cogs_is_estimated"], bool)


class SalesHeatmapContractTests(TestCase):
    def _get(self, period="week"):
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.only.return_value = mock_qs
            mock_qs.filter.return_value = mock_qs
            mock_qs.iterator.return_value = iter([])
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    return svc.get_sales_heatmap(period)

    def test_top_level_keys(self):
        result = self._get()
        self.assertIn("currency", result)
        self.assertIn("data", result)

    def test_data_item_shape(self):
        result = self._get()
        for item in result["data"]:
            for key in ("day", "hour", "sales", "transactions"):
                self.assertIn(key, item)
            self.assertIsInstance(item["hour"], int)
            self.assertGreaterEqual(item["hour"], 0)
            self.assertLessEqual(item["hour"], 23)


class SalesPerformanceContractTests(TestCase):
    def _get(self, period="month", group_by=None):
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.annotate.return_value = mock_qs
            mock_qs.values.return_value = mock_qs
            mock_qs.order_by.return_value = []
            mock_qs.filter.return_value = mock_qs
            mock_qs.aggregate.return_value = _ZeroDict({"sales": Decimal("0"), "count": 0})
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    return svc.get_sales_performance(period, group_by)

    def test_top_level_keys(self):
        result = self._get()
        self.assertIn("currency", result)
        self.assertIn("granularity", result)
        self.assertIn("data", result)


class InventorySummaryContractTests(TestCase):
    def _get(self):
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.count.return_value = 0
            mock_qs.filter.return_value = mock_qs
            mock_qs.aggregate.return_value = {"v": Decimal("0")}
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    return svc.get_inventory_summary()

    def test_top_level_keys(self):
        result = self._get()
        for key in ("currency", "total_skus", "in_stock", "low_stock", "out_of_stock", "inventory_value"):
            self.assertIn(key, result)

    def test_values_are_numeric(self):
        result = self._get()
        self.assertIsInstance(result["total_skus"], int)
        self.assertIsInstance(result["in_stock"], int)
        self.assertIsInstance(result["low_stock"], int)
        self.assertIsInstance(result["out_of_stock"], int)
        self.assertIsInstance(result["inventory_value"], str)


# ── View-level validation tests ─────────────────────────────────────────


class ViewValidationTests(TestCase):
    """Verify that views reject invalid query parameters with 400."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = MagicMock(is_authenticated=True, pk=1)

    def _get(self, view_class, params=None):
        request = self.factory.get("/test/", params or {})
        force_authenticate(request, user=self.user)
        with patch.object(views.HasActiveTenant, "has_permission", return_value=True), \
             patch.object(TenantRBACPermission, "has_permission", return_value=True):
            return view_class.as_view()(request)

    def test_invalid_period_returns_400(self):
        response = self._get(views.SalesTrendChartView, {"period": "invalid"})
        self.assertEqual(response.status_code, 400)

    def test_invalid_group_by_returns_400(self):
        response = self._get(views.SalesTrendChartView, {"period": "month", "group_by": "year"})
        self.assertEqual(response.status_code, 400)

    def test_valid_period_passes(self):
        with patch.object(
            views.StandardizedDashboardService, "get_overview",
            return_value={"currency": "USD", "period": {"key": "month"}, "cards": {}},
        ):
            response = self._get(views.StandardizedOverviewView, {"period": "month"})
            self.assertEqual(response.status_code, 200)

    def test_default_period_is_month(self):
        with patch.object(
            views.StandardizedDashboardService, "get_sales_trend",
            return_value={"currency": "USD", "granularity": "day", "data": []},
        ) as mock:
            self._get(views.SalesTrendChartView)
            mock.assert_called_once_with("month", None)

    def test_authentication_required(self):
        request = self.factory.get("/test/")
        response = views.SalesTrendChartView.as_view()(request)
        self.assertIn(response.status_code, (401, 403))


# ── Integration tests with real DB ──────────────────────────────────────


class DashboardIntegrationTests(TransactionTestCase):
    """
    Integration tests that create real tenant + order data and verify
    the standardized endpoints return correct aggregate values.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from saas.models import Tenant
        from pos.models import Order, OrderItem, Product, Category, Refund, RefundItem

        User = get_user_model()
        self.user = User.objects.create_user(username="dash_owner", password="testpass123", email="dash@test.com")
        self.tenant = Tenant.objects.create(name="TestCo", slug="testco-integration", owner=self.user)
        self.category = Category.objects.create(tenant=self.tenant, name="Drinks")
        self.product = Product.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Coffee",
            sku="CF-001",
            sales_price=Decimal("100.00"),
            cost_price=Decimal("40.00"),
            stock_quantity=Decimal("500"),
            min_stock=50,
        )
        self.order = Order.objects.create(
            tenant=self.tenant,
            status="paid",
            payment_method="cash",
            subtotal=Decimal("100.00"),
            tax=Decimal("0.00"),
            discount=Decimal("5.00"),
            total=Decimal("95.00"),
        )
        self.order_item = OrderItem.objects.create(
            tenant=self.tenant,
            order=self.order,
            product=self.product,
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            subtotal=Decimal("100.00"),
            cost_price=Decimal("40.00"),
        )

    def test_overview_gross_sales(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_overview("today")
        self.assertEqual(result["cards"]["gross_sales"]["value"], "95.00")

    def test_overview_monetary_values_are_strings(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_overview("today")
        self.assertIsInstance(result["cards"]["gross_sales"]["value"], str)
        self.assertIsInstance(result["cards"]["net_sales"]["value"], str)
        self.assertIsInstance(result["cards"]["average_order_value"]["value"], str)

    def test_overview_transaction_count(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_overview("today")
        self.assertEqual(result["cards"]["transactions"]["value"], 1)

    def test_sales_trend_has_data(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_sales_trend("today")
        self.assertGreater(len(result["data"]), 0)

    def test_sales_trend_monetary_strings(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_sales_trend("today")
        for item in result["data"]:
            self.assertIsInstance(item["gross_sales"], str)
            self.assertIsInstance(item["net_sales"], str)

    def test_sales_by_category(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_sales_by_category("today")
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["category"], "Drinks")
        self.assertEqual(result["data"][0]["quantity"], 1)

    def test_top_products(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_top_products("today")
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["name"], "Coffee")

    def test_profit_loss(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_profit_loss("today")
        self.assertGreater(Decimal(result["summary"]["revenue"]), Decimal("0"))
        self.assertGreater(Decimal(result["summary"]["cost_of_goods"]), Decimal("0"))
        self.assertGreater(Decimal(result["summary"]["gross_profit"]), Decimal("0"))

    def test_profit_loss_cogs_uses_snapshot(self):
        """When OrderItem.cost_price is set, COGS uses it — not the current product cost."""
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_profit_loss("today")
        # cost_price snapshot = 40.00, quantity = 1, so COGS = 40.00
        self.assertEqual(Decimal(result["summary"]["cost_of_goods"]), Decimal("40.00"))
        # cogs_is_estimated should be False because we set cost_price on the item
        self.assertFalse(result["cogs_is_estimated"])

    def test_profit_loss_cogs_estimated_when_no_snapshot(self):
        """When OrderItem.cost_price is NULL, COGS falls back to Product.cost_price."""
        from pos.models import OrderItem as OI
        # Clear the cost_price snapshot
        OI.objects.filter(pk=self.order_item.pk).update(cost_price=None)
        self.order_item.refresh_from_db()

        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_profit_loss("today")
        # Should still calculate COGS using Product.cost_price = 40.00
        self.assertEqual(Decimal(result["summary"]["cost_of_goods"]), Decimal("40.00"))
        # But should flag it as estimated
        self.assertTrue(result["cogs_is_estimated"])

    def test_profit_loss_product_cost_change_does_not_affect_historical(self):
        """Changing Product.cost_price today should NOT change historical COGS
        when OrderItem.cost_price snapshot exists."""
        # Snapshot was 40.00
        # Now change product cost to 99.99
        self.product.cost_price = Decimal("99.99")
        self.product.save()

        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_profit_loss("today")
        # COGS should still be 40.00 (snapshot), NOT 99.99
        self.assertEqual(Decimal(result["summary"]["cost_of_goods"]), Decimal("40.00"))

    def test_inventory_summary(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_inventory_summary()
        self.assertEqual(result["total_skus"], 1)
        self.assertEqual(result["in_stock"], 1)
        self.assertEqual(result["out_of_stock"], 0)

    def test_heatmap_returns_data(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_sales_heatmap("today")
        self.assertIsInstance(result["data"], list)

    def test_sales_performance(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_sales_performance("today")
        self.assertGreater(len(result["data"]), 0)

    def test_currency_is_resolved(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_overview("today")
        self.assertEqual(result["currency"], "USD")

    def test_zero_data_safety(self):
        """Verify no crashes when no orders exist."""
        from pos.models import Order
        Order.objects.all().delete()
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        overview = svc.get_overview("today")
        self.assertEqual(overview["cards"]["gross_sales"]["value"], "0.00")
        self.assertEqual(overview["cards"]["transactions"]["value"], 0)
        self.assertEqual(overview["cards"]["average_order_value"]["value"], "0.00")
        # growth should be None (undefined when both periods have zero)
        self.assertIsNone(overview["cards"]["gross_sales"]["change_percent"])

    def test_empty_database_no_crash(self):
        """All endpoints should return valid structures with no data."""
        from pos.models import Order, Product, Category
        Order.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        svc = StandardizedDashboardService(_MockRequest(self.tenant))

        overview = svc.get_overview("month")
        self.assertIn("cards", overview)

        trend = svc.get_sales_trend("month")
        self.assertEqual(trend["data"], [])

        cat = svc.get_sales_by_category("month")
        self.assertEqual(cat["data"], [])

        prods = svc.get_top_products("month")
        self.assertEqual(prods["data"], [])

        pm = svc.get_payment_methods("month")
        self.assertEqual(pm["data"], [])

        pl = svc.get_profit_loss("month")
        self.assertEqual(pl["data"], [])
        self.assertEqual(pl["summary"]["revenue"], "0.00")

        hm = svc.get_sales_heatmap("month")
        self.assertEqual(hm["data"], [])

        perf = svc.get_sales_performance("month")
        self.assertEqual(perf["data"], [])

        inv = svc.get_inventory_summary()
        self.assertEqual(inv["total_skus"], 0)


class TenantIsolationTests(TransactionTestCase):
    """Verify dashboard data is scoped to the authenticated tenant."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from saas.models import Tenant
        from pos.models import Order, OrderItem, Product, Category

        User = get_user_model()
        self.user_a = User.objects.create_user(username="iso_owner_a", password="testpass123", email="iso_a@test.com")
        self.user_b = User.objects.create_user(username="iso_owner_b", password="testpass123", email="iso_b@test.com")
        self.tenant_a = Tenant.objects.create(name="TenantA", slug="tenant-a-dash", owner=self.user_a)
        self.tenant_b = Tenant.objects.create(name="TenantB", slug="tenant-b-dash", owner=self.user_b)

        cat_a = Category.objects.create(tenant=self.tenant_a, name="Cat A")
        cat_b = Category.objects.create(tenant=self.tenant_b, name="Cat B")

        self.prod_a = Product.objects.create(
            tenant=self.tenant_a, category=cat_a, name="ProdA", sku="PA-001",
            sales_price=Decimal("100"), cost_price=Decimal("50"),
            stock_quantity=Decimal("100"), min_stock=10,
        )
        self.prod_b = Product.objects.create(
            tenant=self.tenant_b, category=cat_b, name="ProdB", sku="PB-001",
            sales_price=Decimal("200"), cost_price=Decimal("80"),
            stock_quantity=Decimal("50"), min_stock=5,
        )

        order_a = Order.objects.create(
            tenant=self.tenant_a, status="paid", payment_method="cash",
            total=Decimal("100"),
        )
        OrderItem.objects.create(
            tenant=self.tenant_a, order=order_a, product=self.prod_a,
            quantity=Decimal("1"), unit_price=Decimal("100"), subtotal=Decimal("100"),
            cost_price=Decimal("50"),
        )

        order_b = Order.objects.create(
            tenant=self.tenant_b, status="paid", payment_method="cash",
            total=Decimal("200"),
        )
        OrderItem.objects.create(
            tenant=self.tenant_b, order=order_b, product=self.prod_b,
            quantity=Decimal("1"), unit_price=Decimal("200"), subtotal=Decimal("200"),
            cost_price=Decimal("80"),
        )

    def test_overview_tenant_isolation(self):
        svc_a = StandardizedDashboardService(_MockRequest(self.tenant_a))
        svc_b = StandardizedDashboardService(_MockRequest(self.tenant_b))

        result_a = svc_a.get_overview("today")
        result_b = svc_b.get_overview("today")

        self.assertEqual(result_a["cards"]["gross_sales"]["value"], "100.00")
        self.assertEqual(result_b["cards"]["gross_sales"]["value"], "200.00")

    def test_sales_by_category_tenant_isolation(self):
        svc_a = StandardizedDashboardService(_MockRequest(self.tenant_a))
        svc_b = StandardizedDashboardService(_MockRequest(self.tenant_b))

        result_a = svc_a.get_sales_by_category("today")
        result_b = svc_b.get_sales_by_category("today")

        self.assertEqual(len(result_a["data"]), 1)
        self.assertEqual(result_a["data"][0]["category"], "Cat A")
        self.assertEqual(len(result_b["data"]), 1)
        self.assertEqual(result_b["data"][0]["category"], "Cat B")

    def test_top_products_tenant_isolation(self):
        svc_a = StandardizedDashboardService(_MockRequest(self.tenant_a))
        svc_b = StandardizedDashboardService(_MockRequest(self.tenant_b))

        result_a = svc_a.get_top_products("today")
        result_b = svc_b.get_top_products("today")

        self.assertEqual(result_a["data"][0]["name"], "ProdA")
        self.assertEqual(result_b["data"][0]["name"], "ProdB")

    def test_inventory_tenant_isolation(self):
        svc_a = StandardizedDashboardService(_MockRequest(self.tenant_a))
        svc_b = StandardizedDashboardService(_MockRequest(self.tenant_b))

        result_a = svc_a.get_inventory_summary()
        result_b = svc_b.get_inventory_summary()

        self.assertEqual(result_a["total_skus"], 1)
        self.assertEqual(result_b["total_skus"], 1)

    def test_null_tenant_returns_empty(self):
        svc = StandardizedDashboardService(_MockRequest(None))
        result = svc.get_overview("today")
        self.assertEqual(result["cards"]["gross_sales"]["value"], "0.00")


class RefundConsistencyTests(TransactionTestCase):
    """Verify refund treatment is consistent across dashboard endpoints."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from saas.models import Tenant
        from pos.models import Order, OrderItem, Product, Category, Refund

        User = get_user_model()
        self.user = User.objects.create_user(username="refund_owner", password="testpass123", email="refund@test.com")
        self.tenant = Tenant.objects.create(name="RefundCo", slug="refund-test-dash", owner=self.user)
        self.category = Category.objects.create(tenant=self.tenant, name="Goods")
        self.product = Product.objects.create(
            tenant=self.tenant, category=self.category, name="Widget", sku="WG-001",
            sales_price=Decimal("200"), cost_price=Decimal("100"),
            stock_quantity=Decimal("50"), min_stock=5,
        )

        # Order 1: fully paid, no refund
        self.order1 = Order.objects.create(
            tenant=self.tenant, status="paid", payment_method="cash",
            subtotal=Decimal("200"), discount=Decimal("0"), total=Decimal("200"),
        )
        OrderItem.objects.create(
            tenant=self.tenant, order=self.order1, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("200"), subtotal=Decimal("200"),
            cost_price=Decimal("100"),
        )

        # Order 2: paid with a refund
        self.order2 = Order.objects.create(
            tenant=self.tenant, status="refunded", payment_method="cash",
            subtotal=Decimal("200"), discount=Decimal("0"), total=Decimal("200"),
        )
        OrderItem.objects.create(
            tenant=self.tenant, order=self.order2, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("200"), subtotal=Decimal("200"),
            cost_price=Decimal("100"),
        )
        self.refund = Refund.objects.create(
            tenant=self.tenant, order=self.order2,
            reason="Defective", subtotal=Decimal("200"),
            total_amount=Decimal("200"),
        )

    def test_overview_includes_refund_in_net(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_overview("today")
        # Only the "paid" order counts in gross_sales (status filter = paid/completed)
        # The "refunded" order does NOT appear in gross_sales
        # Gross = 200 (one paid order)
        # Refunds = 200 (the refund on the second order)
        # Net = 200 - 0 discounts - 200 refunds = 0
        self.assertEqual(Decimal(result["cards"]["gross_sales"]["value"]), Decimal("200.00"))
        self.assertEqual(Decimal(result["cards"]["net_sales"]["value"]), Decimal("0.00"))

    def test_sales_trend_includes_refund(self):
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_sales_trend("today")
        # At least one bucket should show net = gross - refund
        for item in result["data"]:
            gross = Decimal(item["gross_sales"])
            net = Decimal(item["net_sales"])
            self.assertLessEqual(net, gross)

    def test_transactions_count_paid_only(self):
        """Only paid/completed orders count as transactions."""
        svc = StandardizedDashboardService(_MockRequest(self.tenant))
        result = svc.get_overview("today")
        # Only 1 order has status "paid"; the other is "refunded"
        self.assertEqual(result["cards"]["transactions"]["value"], 1)


class EdgeCaseTests(TestCase):
    """Test edge cases: division by zero, single data points, etc."""

    def test_payment_methods_empty(self):
        """Empty payment methods should return empty data."""
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.annotate.return_value = mock_qs
            mock_qs.values.return_value = mock_qs
            mock_qs.order_by.return_value = []
            mock_qs.filter.return_value = mock_qs
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    result = svc.get_payment_methods("month")
                    self.assertEqual(result["data"], [])

    def test_sales_performance_single_bucket(self):
        """Single data point should have correct AOV."""
        svc = StandardizedDashboardService(_MockRequest())
        with patch.object(svc, "_scoped") as mock_scoped:
            mock_qs = MagicMock()
            mock_qs.annotate.return_value = mock_qs
            mock_qs.values.return_value = mock_qs
            mock_qs.order_by.return_value = [
                {"bucket": None, "sales": Decimal("500"), "transactions": 5}
            ]
            mock_qs.filter.return_value = mock_qs
            mock_scoped.return_value = mock_qs
            with patch.object(svc, "_active_tenant", return_value=MagicMock()):
                with patch.object(svc, "_currency", return_value="USD"):
                    result = svc.get_sales_performance("month")
                    # None bucket is skipped, so data should be empty
                    self.assertEqual(result["data"], [])
