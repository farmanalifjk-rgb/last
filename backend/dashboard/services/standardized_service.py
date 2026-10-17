"""
Standardized Dashboard Service - production-ready API contract.

Reuses the existing POS/payment/inventory models but returns consistent,
predictable responses for the frontend chart components.

MONETARY PRECISION:
All financial amounts are returned as decimal strings ("123456.78") to
avoid float precision loss.  The frontend is responsible for formatting.
Integer counts (transactions, quantities) remain JSON integers.

COGS / PROFIT:
Uses OrderItem.cost_price (snapshot at time of sale) when available,
falling back to Product.cost_price for legacy rows.  When a fallback
is used, the data point includes "cogs_is_estimated": true so the
frontend can flag it.

CURRENCY:
Resolved from Company.currency → Store.currency → "USD" fallback.
Dashboard always reports at the tenant's base currency.  Cross-currency
aggregation is not supported.

CANONICAL METRIC DEFINITIONS:
  gross_sales  = SUM(Order.total) for paid/completed orders in period
  discounts    = SUM(Order.discount) for same orders
  refunds      = SUM(Refund.total_amount) for refunds in period
  net_sales    = gross_sales − discounts − refunds
  revenue      = gross_sales (same as net_sales in product/category reports)
  transactions = COUNT(DISTINCT Order.id) for paid/completed orders
  AOV          = net_sales / transactions (0 when no transactions)
  COGS         = SUM(OrderItem.quantity × effective_cost_price)
  gross_profit = revenue − COGS
"""

from __future__ import annotations

from calendar import day_name
from datetime import datetime, timedelta, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db.models import Sum, Count, F, Q, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth, TruncHour, Coalesce
from django.utils import timezone

from pos.models import Order, OrderItem, Product, Category, Refund, StockMovement
from payments.models import TenderedPayment
from saas.tenant_context import get_current_tenant

from ..utils.helpers import get_date_range, calculate_growth


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_currency(tenant) -> str:
    """Resolve the tenant's base currency.

    Priority: Company.currency → Store (default).currency → 'USD'.
    This is the *reporting* currency; individual orders may have been
    settled in other tenders but the dashboard aggregates in the base.
    """
    if tenant is None:
        return "USD"
    try:
        from pos.models import Company
        company = Company.objects.filter(tenant=tenant).first()
        if company and company.currency:
            return company.currency
    except Exception:
        pass
    try:
        from system.models import Store
        store = Store.objects.filter(tenant=tenant, is_default=True).first()
        if store and store.currency:
            return store.currency
    except Exception:
        pass
    return "USD"


def _money_str(value) -> str:
    """Convert a Decimal or numeric value to a decimal string for JSON.

    Ensures exactly 2 decimal places for monetary values.
    Returns "0.00" for None/zero.
    """
    if value is None:
        return "0.00"
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return str(d)


def _int(value) -> int:
    """Safe integer conversion."""
    if value is None:
        return 0
    return int(value)


def _growth(previous, current):
    """Safe percentage growth.

    Returns None when the comparison is mathematically undefined
    (previous=0 and current=0, or both None).
    Returns 100.0 when previous=0 and current>0 (new data appeared).
    """
    p = _safe_decimal(previous)
    c = _safe_decimal(current)
    if p == 0 and c == 0:
        return None  # undefined — no data to compare
    if p == 0:
        return 100.0  # appeared from nothing
    return round(((c - p) / abs(p)) * 100, 1)


def _safe_decimal(value) -> Decimal:
    """Convert any value to Decimal safely."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _trend(value):
    if value is None:
        return "flat"
    return "up" if value > 0 else ("down" if value < 0 else "flat")


def _parse_period(period: str) -> str:
    """Normalise UI period aliases to canonical names."""
    aliases = {
        "1d": "today", "day": "today", "today": "today",
        "1w": "week", "weekly": "week", "week": "week",
        "1m": "month", "monthly": "month", "month": "month",
        "3m": "quarter", "quarter": "quarter",
        "6m": "year", "1y": "year", "year": "year",
    }
    return aliases.get(str(period or "").strip().lower(), "month")


def _date_range(period: str):
    """Return (start_date, end_date) as date objects."""
    today = timezone.now().date()
    mapping = {
        "today": (today, today),
        "week": (today - timedelta(days=6), today),
        "month": (today - timedelta(days=29), today),
        "quarter": (today - timedelta(days=89), today),
        "year": (today - timedelta(days=364), today),
    }
    return mapping.get(period, (today.replace(day=1), today))


def _to_datetime_range(start_date, end_date):
    """Convert date pair to timezone-aware datetime pair."""
    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
    return start_dt, end_dt


def _previous_period(start_date, end_date):
    """Return (prev_start, prev_end) for the immediately preceding equal-length span."""
    days = (end_date - start_date).days + 1
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return prev_start, prev_end


def _trunc_func(period: str, group_by: str | None = None):
    """Return (trunc_func, date_fmt, granularity_label)."""
    if group_by == "hour":
        return TruncHour, "%Y-%m-%d %H:00", "hour"
    if group_by == "day":
        return TruncDate, "%Y-%m-%d", "day"
    if group_by == "week":
        return TruncWeek, "%Y-%m-%d", "week"
    if group_by == "month":
        return TruncMonth, "%Y-%m", "month"
    # Auto-select based on period
    if period in ("today",):
        return TruncHour, "%Y-%m-%d %H:00", "hour"
    if period in ("week",):
        return TruncDate, "%Y-%m-%d", "day"
    if period in ("month", "quarter"):
        return TruncDate, "%Y-%m-%d", "day"
    return TruncMonth, "%Y-%m", "month"


def _scoped_qs(model, tenant):
    """Apply tenant filter to a queryset.  Returns .none() when tenant is None."""
    qs = model.objects.all()
    if tenant is None:
        return qs.none()
    return qs.filter(tenant=tenant)


VALID_PERIODS = {"today", "week", "month", "quarter", "year"}
VALID_GROUP_BY = {"hour", "day", "week", "month", None}


# ═══════════════════════════════════════════════════════════════════════════
#  DASHBOARD SERVICE
# ═══════════════════════════════════════════════════════════════════════════


class StandardizedDashboardService:
    """All dashboard data in one place, following the strict API contract."""

    def __init__(self, request=None):
        self.request = request
        self._tenant = None

    def _active_tenant(self):
        if self._tenant is None:
            self._tenant = getattr(self.request, "tenant", None) if self.request else None
            if self._tenant is None:
                self._tenant = get_current_tenant()
        return self._tenant

    def _scoped(self, model):
        return _scoped_qs(model, self._active_tenant())

    def _currency(self):
        return _resolve_currency(self._active_tenant())

    # ─── shared query builders ────────────────────────────────────────

    def _order_qs_range(self, start_dt, end_dt):
        return self._scoped(Order).filter(
            created_at__range=(start_dt, end_dt),
            status__in=["paid", "completed"],
        )

    def _order_item_qs_range(self, start_dt, end_dt):
        return self._scoped(OrderItem).filter(
            order__created_at__range=(start_dt, end_dt),
            order__status__in=["paid", "completed"],
        )

    def _period_aggregates(self, start_dt, end_dt):
        """Compute gross, discounts, refunds, transactions for a period.

        Returns a dict with Decimal values (not floats).
        """
        orders = self._order_qs_range(start_dt, end_dt)
        agg = orders.aggregate(
            gross=Sum("total"),
            discounts=Sum("discount"),
            count=Count("id"),
        )
        gross = agg["gross"] or Decimal("0")
        discounts = agg["discounts"] or Decimal("0")
        transactions = agg["count"]

        refund_total = (
            self._scoped(Refund)
            .filter(order__created_at__range=(start_dt, end_dt))
            .aggregate(r=Sum("total_amount"))["r"]
            or Decimal("0")
        )

        net_sales = gross - discounts - refund_total
        avg_order = (net_sales / transactions) if transactions > 0 else Decimal("0")

        return {
            "gross": gross,
            "discounts": discounts,
            "refunds": refund_total,
            "net_sales": net_sales,
            "transactions": transactions,
            "avg_order": avg_order,
        }

    # ─── 1. OVERVIEW ──────────────────────────────────────────────────

    def get_overview(self, period: str = "today") -> dict:
        """Lightweight KPI cards with sparkline history."""
        period = _parse_period(period)
        start_date, end_date = _date_range(period)
        start_dt, end_dt = _to_datetime_range(start_date, end_date)
        prev_start, prev_end = _previous_period(start_date, end_date)
        prev_start_dt, prev_end_dt = _to_datetime_range(prev_start, prev_end)

        current = self._period_aggregates(start_dt, end_dt)
        previous = self._period_aggregates(prev_start_dt, prev_end_dt)

        # ── Sparkline: single query with conditional aggregation ──
        # Build sparkline ranges
        if period == "today":
            history_unit = "hour"
            n = 7
        elif period == "week":
            history_unit = "day"
            n = 7
        elif period in ("month", "quarter"):
            history_unit = "day"
            n = 7
        else:
            history_unit = "month"
            n = 7

        history_ranges = self._last_n_periods(n, history_unit)

        # Optimized: fetch all sparkline data in one query using conditional sum
        from django.db.models import Case, When, Value, CharField

        order_conditions = []
        for idx, (hs, he) in enumerate(history_ranges):
            order_conditions.append(
                When(
                    created_at__range=(hs, he),
                    status__in=["paid", "completed"],
                    then=Value(idx, output_field=CharField()),
                )
            )

        # Build Case expressions for each sparkline bucket
        spark_cases = {}
        for idx, (hs, he) in enumerate(history_ranges):
            bucket_filter = Q(created_at__range=(hs, he), status__in=["paid", "completed"])
            spark_cases[f"gross_{idx}"] = Sum(
                "total",
                filter=bucket_filter,
                output_field=DecimalField(),
            )
            spark_cases[f"count_{idx}"] = Count(
                "id",
                filter=bucket_filter,
            )

        spark_agg = self._scoped(Order).aggregate(**spark_cases)

        # Pre-fetch discounts & refunds per bucket in two grouped queries (instead of 2*N)
        # Build maps keyed by bucket index derived from order/refund date ranges via conditional sums
        # Simpler: run two annotated grouped queries over the full sparkline window
        spark_window_start = history_ranges[0][0]
        spark_window_end = history_ranges[-1][1]
        # Discounts per spark bucket via conditional annotation (one query)
        discount_cases = {f"d_{idx}": Sum("discount", filter=Q(created_at__range=(hs, he), status__in=["paid", "completed"])) for idx, (hs, he) in enumerate(history_ranges)}
        discount_agg = self._scoped(Order).filter(created_at__range=(spark_window_start, spark_window_end)).aggregate(**discount_cases) if history_ranges else {}
        # Refunds per bucket: need to filter by order__created_at range; use conditional sum on order__created_at
        refund_cases = {f"r_{idx}": Sum("total_amount", filter=Q(order__created_at__range=(hs, he))) for idx, (hs, he) in enumerate(history_ranges)}
        refund_agg = self._scoped(Refund).filter(order__created_at__range=(spark_window_start, spark_window_end)).aggregate(**refund_cases) if history_ranges else {}

        # Build sparkline arrays
        spark_gross = []
        spark_net = []
        spark_txn = []
        spark_aov = []

        for idx in range(n):
            g = spark_agg.get(f"gross_{idx}") or Decimal("0")
            c = spark_agg.get(f"count_{idx}") or 0

            bucket_discounts = discount_agg.get(f"d_{idx}") or Decimal("0")
            bucket_refunds = refund_agg.get(f"r_{idx}") or Decimal("0")
            n_val = g - bucket_discounts - bucket_refunds
            a_val = (n_val / c) if c > 0 else Decimal("0")

            spark_gross.append(_money_str(g))
            spark_net.append(_money_str(n_val))
            spark_txn.append(c)
            spark_aov.append(_money_str(a_val))

        g_pct = _growth(previous["gross"], current["gross"])
        n_pct = _growth(previous["net_sales"], current["net_sales"])
        t_pct = _growth(previous["transactions"], current["transactions"])
        a_pct = _growth(previous["avg_order"], current["avg_order"])

        return {
            "currency": self._currency(),
            "period": {
                "key": period,
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
            },
            "cards": {
                "gross_sales": {
                    "value": _money_str(current["gross"]),
                    "change_percent": g_pct,
                    "trend": _trend(g_pct),
                    "history": spark_gross,
                },
                "net_sales": {
                    "value": _money_str(current["net_sales"]),
                    "change_percent": n_pct,
                    "trend": _trend(n_pct),
                    "history": spark_net,
                },
                "transactions": {
                    "value": current["transactions"],
                    "change_percent": t_pct,
                    "trend": _trend(t_pct),
                    "history": spark_txn,
                },
                "average_order_value": {
                    "value": _money_str(current["avg_order"]),
                    "change_percent": a_pct,
                    "trend": _trend(a_pct),
                    "history": spark_aov,
                },
            },
        }

    # ─── 2. SALES TREND ───────────────────────────────────────────────

    def get_sales_trend(self, period: str = "month", group_by: str | None = None) -> dict:
        period = _parse_period(period)
        if group_by not in VALID_GROUP_BY:
            group_by = None
        start_date, end_date = _date_range(period)
        start_dt, end_dt = _to_datetime_range(start_date, end_date)

        trunc_fn, date_fmt, granularity = _trunc_func(period, group_by)

        # Revenue per bucket
        revenue_rows = (
            self._scoped(Order)
            .filter(created_at__range=(start_dt, end_dt), status__in=["paid", "completed"])
            .annotate(bucket=trunc_fn("created_at"))
            .values("bucket")
            .annotate(gross=Sum("total"), txn_count=Count("id"))
            .order_by("bucket")
        )
        # Discounts + refunds per bucket
        discount_rows = (
            self._scoped(Order)
            .filter(created_at__range=(start_dt, end_dt), status__in=["paid", "completed"])
            .annotate(bucket=trunc_fn("created_at"))
            .values("bucket")
            .annotate(d=Sum("discount"))
        )
        discount_map = {r["bucket"]: r["d"] or Decimal("0") for r in discount_rows if r["bucket"]}
        refund_rows = (
            self._scoped(Refund)
            .filter(order__created_at__range=(start_dt, end_dt))
            .annotate(bucket=trunc_fn("created_at"))
            .values("bucket")
            .annotate(r=Sum("total_amount"))
        )
        refund_map = {r["bucket"]: r["r"] or Decimal("0") for r in refund_rows if r["bucket"]}

        data = []
        for row in revenue_rows:
            bucket = row["bucket"]
            if bucket is None:
                continue
            gross = row["gross"] or Decimal("0")
            disc = discount_map.get(bucket, Decimal("0"))
            ref = refund_map.get(bucket, Decimal("0"))
            data.append({
                "date": bucket.strftime(date_fmt),
                "gross_sales": _money_str(gross),
                "net_sales": _money_str(gross - disc - ref),
                "transactions": row["txn_count"],
            })

        return {
            "currency": self._currency(),
            "granularity": granularity,
            "data": data,
        }

    # ─── 3. SALES BY CATEGORY ─────────────────────────────────────────

    def get_sales_by_category(self, period: str = "month") -> dict:
        period = _parse_period(period)
        start_date, end_date = _date_range(period)
        start_dt, end_dt = _to_datetime_range(start_date, end_date)

        rows = (
            self._scoped(OrderItem)
            .filter(
                order__created_at__range=(start_dt, end_dt),
                order__status__in=["paid", "completed"],
            )
            .values("product__category_id", "product__category__name")
            .annotate(revenue=Sum("subtotal"), quantity=Sum("quantity"))
            .order_by("-revenue")
        )

        data = []
        for row in rows:
            data.append({
                "category": row["product__category__name"] or "Uncategorized",
                "revenue": _money_str(row["revenue"]),
                "quantity": _int(row["quantity"]),
            })

        return {"currency": self._currency(), "data": data}

    # ─── 4. TOP PRODUCTS ──────────────────────────────────────────────

    def get_top_products(self, period: str = "month", limit: int = 10) -> dict:
        period = _parse_period(period)
        limit = max(1, min(limit, 100))
        start_date, end_date = _date_range(period)
        start_dt, end_dt = _to_datetime_range(start_date, end_date)

        rows = (
            self._scoped(OrderItem)
            .filter(
                order__created_at__range=(start_dt, end_dt),
                order__status__in=["paid", "completed"],
            )
            .values("product__id", "product__name", "product__sku")
            .annotate(quantity_sold=Sum("quantity"), revenue=Sum("subtotal"))
            .order_by("-quantity_sold")[:limit]
        )

        data = []
        for row in rows:
            data.append({
                "product_id": row["product__id"],
                "name": row["product__name"],
                "sku": row["product__sku"],
                "quantity_sold": _int(row["quantity_sold"]),
                "revenue": _money_str(row["revenue"]),
            })

        return {"currency": self._currency(), "data": data}

    # ─── 5. PAYMENT METHODS ───────────────────────────────────────────

    def get_payment_methods(self, period: str = "month") -> dict:
        period = _parse_period(period)
        start_date, end_date = _date_range(period)
        start_dt, end_dt = _to_datetime_range(start_date, end_date)

        rows = (
            self._scoped(TenderedPayment)
            .filter(order__created_at__range=(start_dt, end_dt))
            .values("tender_type")
            .annotate(amount=Sum("amount"), transactions=Count("id"))
            .order_by("-amount")
        )

        total_amount = sum((r["amount"] or Decimal("0")) for r in rows)
        total_for_pct = total_amount if total_amount > 0 else Decimal("1")

        data = []
        for row in rows:
            amt = row["amount"] or Decimal("0")
            data.append({
                "name": (row["tender_type"] or "unknown").replace("_", " ").title(),
                "amount": _money_str(amt),
                "transactions": row["transactions"],
                "percentage": _money_str(amt / total_for_pct * 100),
            })

        return {"currency": self._currency(), "data": data}

    # ─── 6. PROFIT & LOSS ─────────────────────────────────────────────

    def get_profit_loss(self, period: str = "month", group_by: str | None = None) -> dict:
        period = _parse_period(period)
        if group_by not in VALID_GROUP_BY:
            group_by = None
        start_date, end_date = _date_range(period)
        start_dt, end_dt = _to_datetime_range(start_date, end_date)

        trunc_fn, date_fmt, granularity = _trunc_func(period, group_by)

        # Revenue per bucket
        rev_rows = (
            self._scoped(Order)
            .filter(created_at__range=(start_dt, end_dt), status__in=["paid", "completed"])
            .annotate(bucket=trunc_fn("created_at"))
            .values("bucket")
            .annotate(revenue=Sum("total"))
            .order_by("bucket")
        )

        # COGS per bucket — uses OrderItem.cost_price (snapshot) with
        # fallback to Product.cost_price (current) for legacy rows.
        cogs_rows = (
            self._scoped(OrderItem)
            .filter(order__created_at__range=(start_dt, end_dt), order__status__in=["paid", "completed"])
            .annotate(
                bucket=trunc_fn("order__created_at"),
                effective_cost=Coalesce(F("cost_price"), F("product__cost_price"), Decimal("0")),
            )
            .values("bucket")
            .annotate(cogs=Sum(F("quantity") * F("effective_cost")))
            .order_by("bucket")
        )
        cogs_map = {r["bucket"]: r["cogs"] or Decimal("0") for r in cogs_rows if r["bucket"]}

        # Check if any COGS used fallback (cost_price IS NULL on OrderItem)
        fallback_count = (
            self._scoped(OrderItem)
            .filter(
                order__created_at__range=(start_dt, end_dt),
                order__status__in=["paid", "completed"],
                cost_price__isnull=True,
            )
            .count()
        )

        data = []
        total_rev = Decimal("0")
        total_cogs = Decimal("0")
        for row in rev_rows:
            bucket = row["bucket"]
            if bucket is None:
                continue
            rev = row["revenue"] or Decimal("0")
            cogs = cogs_map.get(bucket, Decimal("0"))
            gp = rev - cogs
            total_rev += rev
            total_cogs += cogs
            data.append({
                "date": bucket.strftime(date_fmt),
                "revenue": _money_str(rev),
                "cost_of_goods": _money_str(cogs),
                "gross_profit": _money_str(gp),
            })

        return {
            "currency": self._currency(),
            "granularity": granularity,
            "data": data,
            "summary": {
                "revenue": _money_str(total_rev),
                "cost_of_goods": _money_str(total_cogs),
                "gross_profit": _money_str(total_rev - total_cogs),
            },
            "cogs_is_estimated": fallback_count > 0,
        }

    # ─── 7. SALES HEATMAP ─────────────────────────────────────────────

    def get_sales_heatmap(self, period: str = "week") -> dict:
        period = _parse_period(period)
        start_date, end_date = _date_range(period)
        start_dt, end_dt = _to_datetime_range(start_date, end_date)

        orders = (
            self._scoped(Order)
            .filter(created_at__range=(start_dt, end_dt), status__in=["paid", "completed"])
            .only("created_at", "total")
        )

        # Aggregate in Python — unavoidable because we need (day_of_week, hour)
        # grouping which PostgreSQL TRUNC doesn't natively support.
        # Scoped to a small date range and pre-filtered by tenant.
        cells: dict[tuple[str, int], dict] = {}
        for order in orders.iterator(chunk_size=1000):
            local_dt = timezone.localtime(order.created_at)
            day_label = day_name[local_dt.weekday()]  # Monday … Sunday
            hour = local_dt.hour
            key = (day_label, hour)
            if key not in cells:
                cells[key] = {"day": day_label, "hour": hour, "sales": Decimal("0"), "transactions": 0}
            cells[key]["sales"] += order.total or Decimal("0")
            cells[key]["transactions"] += 1

        # Sort: Monday first, then by hour
        day_order = {name: i for i, name in enumerate(day_name)}
        data = sorted(
            [
                {
                    "day": v["day"],
                    "hour": v["hour"],
                    "sales": _money_str(v["sales"]),
                    "transactions": v["transactions"],
                }
                for v in cells.values()
            ],
            key=lambda x: (day_order.get(x["day"], 7), x["hour"]),
        )

        return {"currency": self._currency(), "data": data}

    # ─── 8. SALES PERFORMANCE ─────────────────────────────────────────

    def get_sales_performance(self, period: str = "month", group_by: str | None = None) -> dict:
        period = _parse_period(period)
        if group_by not in VALID_GROUP_BY:
            group_by = None
        start_date, end_date = _date_range(period)
        start_dt, end_dt = _to_datetime_range(start_date, end_date)

        trunc_fn, date_fmt, granularity = _trunc_func(period, group_by)

        rows = (
            self._scoped(Order)
            .filter(created_at__range=(start_dt, end_dt), status__in=["paid", "completed"])
            .annotate(bucket=trunc_fn("created_at"))
            .values("bucket")
            .annotate(sales=Sum("total"), transactions=Count("id"))
            .order_by("bucket")
        )

        data = []
        for row in rows:
            bucket = row["bucket"]
            if bucket is None:
                continue
            txn = row["transactions"]
            sales = row["sales"] or Decimal("0")
            aov = (sales / txn) if txn > 0 else Decimal("0")
            data.append({
                "date": bucket.strftime(date_fmt),
                "sales": _money_str(sales),
                "transactions": txn,
                "average_order_value": _money_str(aov),
            })

        return {
            "currency": self._currency(),
            "granularity": granularity,
            "data": data,
        }

    # ─── 9. INVENTORY SUMMARY ─────────────────────────────────────────

    def get_inventory_summary(self) -> dict:
        """Inventory summary using Product.stock_quantity.

        NOTE: Product.stock_quantity is the denormalized aggregate updated
        by apply_adjustment().  The canonical per-warehouse stock lives in
        enterprise.WarehouseStock.  For tenant-wide dashboard summaries
        the Product aggregate is correct; for warehouse-level detail use
        the inventory API.

        If the tenant has warehouses and WarehouseStock data, the true
        stock truth may diverge from Product.stock_quantity.  A future
        enhancement should reconcile these or use WarehouseStock as the
        source of truth for the dashboard.
        """
        products = self._scoped(Product).filter(is_active=True)

        total_skus = products.count()
        in_stock = products.filter(stock_quantity__gt=0).count()
        low_stock_qs = products.filter(stock_quantity__gt=0, stock_quantity__lte=F("min_stock"))
        low_stock = low_stock_qs.count()
        out_of_stock = products.filter(stock_quantity=0).count()
        inventory_value = products.aggregate(
            v=Sum(F("stock_quantity") * F("cost_price"))
        )["v"] or Decimal("0")

        return {
            "currency": self._currency(),
            "total_skus": total_skus,
            "in_stock": in_stock,
            "low_stock": low_stock,
            "out_of_stock": out_of_stock,
            "inventory_value": _money_str(inventory_value),
        }

    # ─── sparkline helper ─────────────────────────────────────────────

    def _last_n_periods(self, n: int, unit: str):
        """Return a list of (start_dt, end_dt) for the last *n* equal-length periods."""
        now = timezone.now()
        results = []
        for i in range(n - 1, -1, -1):
            if unit == "day":
                d = (now - timedelta(days=i)).date()
                s = timezone.make_aware(datetime.combine(d, datetime.min.time()))
                e = timezone.make_aware(datetime.combine(d, datetime.max.time()))
            elif unit == "week":
                end = (now - timedelta(weeks=i)).date()
                start = end - timedelta(days=6)
                s = timezone.make_aware(datetime.combine(start, datetime.min.time()))
                e = timezone.make_aware(datetime.combine(end, datetime.max.time()))
            elif unit == "month":
                end = (now - timedelta(days=30 * i)).date()
                start = end - timedelta(days=29)
                s = timezone.make_aware(datetime.combine(start, datetime.min.time()))
                e = timezone.make_aware(datetime.combine(end, datetime.max.time()))
            else:
                d = (now - timedelta(days=i)).date()
                s = timezone.make_aware(datetime.combine(d, datetime.min.time()))
                e = timezone.make_aware(datetime.combine(d, datetime.max.time()))
            results.append((s, e))
        return results
