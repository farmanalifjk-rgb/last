# Dashboard API Documentation

**Base URL:** `/api/dashboard/`
**Authentication:** Token-based (`Authorization: Token <key>`)
**Tenant:** Resolved automatically from the authenticated user's active membership

---

## Table of Contents

1. [Standardized Endpoints (New)](#1-standardized-endpoints-new)
   - [GET /overview/](#11-get-api dashboardoverview)
   - [GET /charts/sales-trend/](#12-get-api-dashboardchartssales-trend)
   - [GET /charts/sales-by-category/](#13-get-api-dashboardchartssales-by-category)
   - [GET /charts/top-products/](#14-get-api-dashboardchartstop-products)
   - [GET /charts/payment-methods/](#15-get-api-dashboardchartspayment-methods)
   - [GET /charts/profit-loss/](#16-get-api-dashboardchartsprofit-loss)
   - [GET /charts/sales-heatmap/](#17-get-api-dashboardchartssales-heatmap)
   - [GET /charts/sales-performance/](#18-get-api-dashboardchartssales-performance)
   - [GET /inventory/summary/](#19-get-api-dashboardinventorysummary)
2. [Legacy Endpoints](#2-legacy-endpoints)
   - [GET /legacy/overview/](#21-get-apidashboardlegacyoverview)
   - [GET /summary/](#22-get-apidashboardsummary)
   - [GET /kpis/](#23-get-apidashboardkpis)
   - [GET /revenue/](#24-get-apidashboardrevenue)
   - [GET /sales-chart/](#25-get-apidashboardsales-chart)
   - [GET /payment-methods-legacy/](#26-get-apidashboardpayment-methods-legacy)
   - [GET /today-summary/](#27-get-apidashboardtoday-summary)
   - [GET /recent-orders/](#28-get-apidashboardrecent-orders)
   - [GET /top-products-legacy/](#29-get-apidashboardsales-top-products-legacy)
   - [GET /low-stock/](#210-get-apidashboardlow-stock)
   - [GET /active-sessions/](#211-get-apidashboardactive-sessions)
   - [GET /recent-notifications/](#212-get-apidashboardrecent-notifications)
   - [GET /quick-actions/](#213-get-apidashboardquick-actions)
   - [GET /order-statistics/](#214-get-apidashboardorder-statistics)
   - [GET /inventory-stats/](#215-get-apidashboardinventory-stats)
   - [GET /customer-stats/](#216-get-apidashboardcustomer-stats)
   - [GET /top-customers/](#217-get-apidashboardtop-customers)
   - [GET /top-categories/](#218-get-apidashboardtop-categories)
   - [GET /order-statistics-heatmap/](#219-get-apidashboardorder-statistics-heatmap)
   - [GET /recent-transactions/](#220-get-apidashboardrecent-transactions)
   - [GET /sales-statistics/](#221-get-apidashboardsales-statistics)

---

## Common Query Parameters

| Parameter   | Type    | Default    | Description                                      |
|-------------|---------|------------|--------------------------------------------------|
| `period`    | string  | varies     | `today`, `week`, `month`, `quarter`, `year`      |
| `limit`     | integer | 10         | Max items returned (1–100)                       |
| `group_by`  | string  | auto       | `hour`, `day`, `week`, `month` (standardized only) |

---

# 1. Standardized Endpoints (New)

These endpoints return **decimal strings** for all monetary values (e.g. `"1234.56"`) to prevent float precision loss. They include a `currency` field resolved from the tenant's Company or Store settings.

---

## 1.1. GET `/api/dashboard/overview/`

**Purpose:** Lightweight KPI cards with sparkline history for the main dashboard.

**Query Parameters:**

| Param    | Type   | Default  | Valid Values                                |
|----------|--------|----------|---------------------------------------------|
| `period` | string | `today`  | `today`, `week`, `month`, `quarter`, `year` |

**Response `200 OK`:**

```json
{
  "currency": "USD",
  "period": {
    "key": "month",
    "from": "2026-08-01",
    "to": "2026-08-31"
  },
  "cards": {
    "gross_sales": {
      "value": "12450.00",
      "change_percent": 12.3,
      "trend": "up",
      "history": ["1100.00", "1200.00", "1350.00", "1400.00", "1300.00", "1500.00", "1600.00"]
    },
    "net_sales": {
      "value": "11200.00",
      "change_percent": 10.1,
      "trend": "up",
      "history": ["990.00", "1080.00", "1200.00", "1260.00", "1170.00", "1350.00", "1440.00"]
    },
    "transactions": {
      "value": 156,
      "change_percent": 8.5,
      "trend": "up",
      "history": [18, 20, 22, 24, 23, 25, 24]
    },
    "average_order_value": {
      "value": "71.79",
      "change_percent": 1.7,
      "trend": "up",
      "history": ["55.00", "54.00", "54.55", "52.50", "50.87", "54.00", "60.00"]
    }
  }
}
```

**Fields:**
- `value` — current period value (decimal string for money, integer for counts)
- `change_percent` — percentage change vs previous equal-length period (`null` when undefined)
- `trend` — `"up"`, `"down"`, or `"flat"`
- `history` — sparkline array of 7 values for the last 7 sub-periods

---

## 1.2. GET `/api/dashboard/charts/sales-trend/`

**Purpose:** Time series of gross_sales, net_sales, and transaction counts.

**Query Parameters:**

| Param      | Type   | Default  | Valid Values                                |
|------------|--------|----------|---------------------------------------------|
| `period`   | string | `month`  | `today`, `week`, `month`, `quarter`, `year` |
| `group_by` | string | auto     | `hour`, `day`, `week`, `month`              |

**Auto-selection:** `today` → hourly, `week` → daily, `month`/`quarter` → daily, `year` → monthly.

**Response `200 OK`:**

```json
{
  "currency": "USD",
  "granularity": "day",
  "data": [
    {
      "date": "2026-08-01",
      "gross_sales": "1250.00",
      "net_sales": "1180.00",
      "transactions": 15
    },
    {
      "date": "2026-08-02",
      "gross_sales": "980.00",
      "net_sales": "920.00",
      "transactions": 12
    }
  ]
}
```

---

## 1.3. GET `/api/dashboard/charts/sales-by-category/`

**Purpose:** Revenue and quantity sold per product category.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `month`  |

**Response `200 OK`:**

```json
{
  "currency": "USD",
  "data": [
    {
      "category": "Electronics",
      "revenue": "5420.00",
      "quantity": 89
    },
    {
      "category": "Clothing",
      "revenue": "3210.00",
      "quantity": 145
    },
    {
      "category": "Uncategorized",
      "revenue": "890.00",
      "quantity": 34
    }
  ]
}
```

---

## 1.4. GET `/api/dashboard/charts/top-products/`

**Purpose:** Ranked list of best-selling products with revenue and quantity.

**Query Parameters:**

| Param    | Type    | Default  |
|----------|---------|----------|
| `period` | string  | `month`  |
| `limit`  | integer | 10       |

**Response `200 OK`:**

```json
{
  "currency": "USD",
  "data": [
    {
      "product_id": 42,
      "name": "Wireless Mouse",
      "sku": "WM-001",
      "quantity_sold": 234,
      "revenue": "5616.00"
    },
    {
      "product_id": 15,
      "name": "USB-C Cable",
      "sku": "UC-015",
      "quantity_sold": 189,
      "revenue": "1890.00"
    }
  ]
}
```

---

## 1.5. GET `/api/dashboard/charts/payment-methods/`

**Purpose:** Payment method breakdown with amounts, transaction counts, and percentages.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `month`  |

**Response `200 OK`:**

```json
{
  "currency": "USD",
  "data": [
    {
      "name": "Cash",
      "amount": "8500.00",
      "transactions": 95,
      "percentage": "52.30"
    },
    {
      "name": "Card",
      "amount": "6200.00",
      "transactions": 72,
      "percentage": "38.15"
    },
    {
      "name": "Bank Transfer",
      "amount": "1550.00",
      "transactions": 12,
      "percentage": "9.55"
    }
  ]
}
```

---

## 1.6. GET `/api/dashboard/charts/profit-loss/`

**Purpose:** Revenue, COGS, and gross profit time series. Uses `OrderItem.cost_price` snapshot when available, falling back to `Product.cost_price` for legacy rows.

**Query Parameters:**

| Param      | Type   | Default  |
|------------|--------|----------|
| `period`   | string | `month`  |
| `group_by` | string | auto     |

**Response `200 OK`:**

```json
{
  "currency": "USD",
  "granularity": "day",
  "data": [
    {
      "date": "2026-08-01",
      "revenue": "1250.00",
      "cost_of_goods": "750.00",
      "gross_profit": "500.00"
    },
    {
      "date": "2026-08-02",
      "revenue": "980.00",
      "cost_of_goods": "588.00",
      "gross_profit": "392.00"
    }
  ],
  "summary": {
    "revenue": "2230.00",
    "cost_of_goods": "1338.00",
    "gross_profit": "892.00"
  },
  "cogs_is_estimated": false
}
```

**Notes:**
- `cogs_is_estimated` — `true` when some OrderItems lack a `cost_price` snapshot and fell back to current `Product.cost_price`

---

## 1.7. GET `/api/dashboard/charts/sales-heatmap/`

**Purpose:** Day × hour matrix showing sales volume and transaction counts for the heatmap widget.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `week`   |

**Response `200 OK`:**

```json
{
  "currency": "USD",
  "data": [
    {
      "day": "Monday",
      "hour": 9,
      "sales": "450.00",
      "transactions": 5
    },
    {
      "day": "Monday",
      "hour": 10,
      "sales": "720.00",
      "transactions": 8
    },
    {
      "day": "Tuesday",
      "hour": 9,
      "sales": "380.00",
      "transactions": 4
    }
  ]
}
```

**Notes:**
- Only cells with at least 1 transaction appear in the array
- Hours are in the tenant's local timezone
- Sorted by day (Monday first) then by hour

---

## 1.8. GET `/api/dashboard/charts/sales-performance/`

**Purpose:** Sales, transactions, and average order value per time bucket.

**Query Parameters:**

| Param      | Type   | Default  |
|------------|--------|----------|
| `period`   | string | `month`  |
| `group_by` | string | auto     |

**Response `200 OK`:**

```json
{
  "currency": "USD",
  "granularity": "day",
  "data": [
    {
      "date": "2026-08-01",
      "sales": "1250.00",
      "transactions": 15,
      "average_order_value": "83.33"
    },
    {
      "date": "2026-08-02",
      "sales": "980.00",
      "transactions": 12,
      "average_order_value": "81.67"
    }
  ]
}
```

---

## 1.9. GET `/api/dashboard/inventory/summary/`

**Purpose:** SKU counts and total inventory value. No query parameters.

**Response `200 OK`:**

```json
{
  "currency": "USD",
  "total_skus": 342,
  "in_stock": 298,
  "low_stock": 28,
  "out_of_stock": 44,
  "inventory_value": "45230.00"
}
```

---

# 2. Legacy Endpoints

These endpoints return **floats** for monetary values. They are retained for backward compatibility. Prefer the Standardized endpoints above for new integrations.

---

## 2.1. GET `/api/dashboard/legacy/overview/`

**Purpose:** All-in-one dashboard payload for initial page load. Combines every widget into a single response.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `today`  |

**Response `200 OK`:**

```json
{
  "period": "today",
  "summary": {
    "today_orders": 45,
    "today_sales": 3420.50,
    "total_customers": 234,
    "total_products": 512,
    "total_suppliers": 28,
    "low_stock_count": 12,
    "out_of_stock_count": 3,
    "open_sessions": 2,
    "pending_orders": 5,
    "total_employees": 8
  },
  "kpis": {
    "total_sales": 3420.50,
    "total_sales_change": 12.3,
    "orders": 45,
    "orders_change": 8.5,
    "avg_order": 76.01,
    "avg_order_change": 3.5,
    "customers": 234,
    "customers_change": 5.2,
    "gross_profit": 1368.20,
    "gross_profit_change": 15.1
  },
  "sales_chart": {
    "labels": ["01 Aug", "02 Aug", "03 Aug"],
    "sales": [1200.00, 1350.00, 870.50],
    "purchase": [450.00, 320.00, 280.00]
  },
  "sales_statistics": {
    "period": "year",
    "labels": ["Jan 2026", "Feb 2026", "Mar 2026"],
    "revenue": [45000.00, 52000.00, 48000.00],
    "expense": [12000.00, 14000.00, 11000.00],
    "total_revenue": 145000.00,
    "total_expense": 37000.00
  },
  "payment_methods": [
    {
      "label": "Cash",
      "value": 52.3,
      "amount": 1788.06,
      "color": "#10B981"
    },
    {
      "label": "Card",
      "value": 38.1,
      "amount": 1303.21,
      "color": "#6366F1"
    }
  ],
  "today_summary": {
    "opening_balance": 500.00,
    "total_sales": 3420.50,
    "total_refunds": 45.00,
    "total_discounts": 120.00,
    "net_sales": 3255.50,
    "closing_balance": 3755.50
  },
  "recent_sales": [
    {
      "id": 1001,
      "order_number": "ORD-001001",
      "customer": "John Smith",
      "amount": 89.99,
      "status": "paid",
      "payment_method": "cash",
      "created_at": "2026-08-31T14:30:00+00:00"
    }
  ],
  "top_products": [
    {
      "id": 42,
      "name": "Wireless Mouse",
      "sku": "WM-001",
      "price": 24.99,
      "image": "",
      "sold": 234,
      "revenue": 5847.66,
      "growth": 15.2
    }
  ],
  "low_stock": [
    {
      "id": 88,
      "name": "USB-C Hub",
      "sku": "UCH-088",
      "category": "Electronics",
      "stock": 3,
      "minimum_stock": 10,
      "unit": "pcs",
      "image": "",
      "status": "Low Stock"
    }
  ],
  "order_statistics": {
    "completed": 145,
    "draft": 5,
    "cancelled": 3,
    "refunded": 8,
    "pending": 2,
    "partial_refunded": 1
  },
  "order_statistics_heatmap": {
    "period": "week",
    "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "times": ["2 Am", "4 Am", "6 Am", "8 Am", "10 Am", "12 Am", "14 Pm", "16 Pm", "18 Am"],
    "cells": [
      {"day": "Mon", "time": "2 Am", "orders": 0},
      {"day": "Mon", "time": "10 Am", "orders": 12}
    ],
    "max_orders": 18
  },
  "inventory_stats": {
    "total_products": 512,
    "total_stock": 4520,
    "total_value": 45230.00,
    "low_stock": 12,
    "out_of_stock": 3
  },
  "customer_stats": {
    "total": 234,
    "new_this_month": 18,
    "returning": 89,
    "avg_orders_per_customer": 4.2
  },
  "top_customers": {
    "period": "month",
    "items": [
      {
        "id": 12,
        "name": "Acme Corp",
        "orders": 15,
        "revenue": 4500.00,
        "growth": 22.5
      }
    ]
  },
  "top_categories": {
    "period": "month",
    "total_sales": 520,
    "items": [
      {
        "id": 5,
        "name": "Electronics",
        "sales": 234,
        "share": 45.0
      }
    ]
  },
  "recent_transactions": {
    "type": "sales",
    "columns": ["reference", "party", "date", "amount", "status"],
    "items": [
      {
        "id": 1001,
        "reference": "ORD-001001",
        "party": "John Smith",
        "date": "2026-08-31T14:30:00+00:00",
        "amount": 89.99,
        "status": "paid"
      }
    ]
  }
}
```

---

## 2.2. GET `/api/dashboard/summary/`

**Purpose:** Dashboard header summary counts.

**Response `200 OK`:**

```json
{
  "today_orders": 45,
  "today_sales": 3420.50,
  "total_customers": 234,
  "total_products": 512,
  "total_suppliers": 28,
  "low_stock_count": 12,
  "out_of_stock_count": 3,
  "open_sessions": 2,
  "pending_orders": 5,
  "total_employees": 8
}
```

---

## 2.3. GET `/api/dashboard/kpis/`

**Purpose:** KPI cards with period-over-period change percentages.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `today`  |

**Response `200 OK`:**

```json
{
  "total_sales": 3420.50,
  "total_sales_change": 12.3,
  "orders": 45,
  "orders_change": 8.5,
  "avg_order": 76.01,
  "avg_order_change": 3.5,
  "customers": 234,
  "customers_change": 5.2,
  "gross_profit": 1368.20,
  "gross_profit_change": 15.1
}
```

---

## 2.4. GET `/api/dashboard/revenue/`

**Purpose:** Revenue widget with profit, invoice dues, and expenses.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `today`  |

**Response `200 OK`:**

```json
{
  "profit": 1368.20,
  "profit_growth": 15.1,
  "invoice_due": 450.00,
  "expenses": 890.00,
  "revenue": 3420.50
}
```

---

## 2.5. GET `/api/dashboard/sales-chart/`

**Purpose:** Sales vs Purchase time series for the bar chart.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `today`  |

**Response `200 OK`:**

```json
{
  "labels": ["01 Aug", "02 Aug", "03 Aug", "04 Aug"],
  "sales": [1200.00, 1350.00, 870.50, 1100.00],
  "purchase": [450.00, 320.00, 280.00, 400.00]
}
```

---

## 2.6. GET `/api/dashboard/payment-methods-legacy/`

**Purpose:** Payment method breakdown with colors for the donut chart.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `today`  |

**Response `200 OK`:**

```json
[
  {
    "label": "Cash",
    "value": 52.3,
    "amount": 1788.06,
    "color": "#10B981"
  },
  {
    "label": "Card",
    "value": 38.1,
    "amount": 1303.21,
    "color": "#6366F1"
  },
  {
    "label": "Bank Transfer",
    "value": 9.6,
    "amount": 329.23,
    "color": "#60A5FA"
  }
]
```

**Color Map:**
| Method        | Color     |
|---------------|-----------|
| `cash`        | `#10B981` |
| `card`        | `#6366F1` |
| `bank`        | `#60A5FA` |
| `gift_card`   | `#F59E0B` |
| `store_credit`| `#8B5CF6` |
| `loyalty`     | `#EC4899` |
| `wallet`      | `#14B8A6` |
| (other)       | `#6B7280` |

---

## 2.7. GET `/api/dashboard/today-summary/`

**Purpose:** Today's financial summary (opening balance, sales, refunds, discounts, net, closing).

**Response `200 OK`:**

```json
{
  "opening_balance": 500.00,
  "total_sales": 3420.50,
  "total_refunds": 45.00,
  "total_discounts": 120.00,
  "net_sales": 3255.50,
  "closing_balance": 3755.50
}
```

---

## 2.8. GET `/api/dashboard/recent-orders/`

**Purpose:** List of most recent paid/completed orders.

**Query Parameters:**

| Param  | Type    | Default |
|--------|---------|---------|
| `limit`| integer | 10      |

**Response `200 OK`:**

```json
[
  {
    "id": 1001,
    "order_number": "ORD-001001",
    "customer": "John Smith",
    "amount": 89.99,
    "status": "paid",
    "payment_method": "cash",
    "created_at": "2026-08-31T14:30:00+00:00"
  },
  {
    "id": 1000,
    "order_number": "ORD-001000",
    "customer": "Walk-in Customer",
    "amount": 34.50,
    "status": "completed",
    "payment_method": "card",
    "created_at": "2026-08-31T14:15:00+00:00"
  }
]
```

---

## 2.9. GET `/api/dashboard/top-products-legacy/`

**Purpose:** Best-selling products with growth percentage.

**Query Parameters:**

| Param    | Type    | Default  |
|----------|---------|----------|
| `limit`  | integer | 10       |
| `period` | string  | `today`  |

**Response `200 OK`:**

```json
[
  {
    "id": 42,
    "name": "Wireless Mouse",
    "sku": "WM-001",
    "price": 24.99,
    "image": "",
    "sold": 234,
    "revenue": 5847.66,
    "growth": 15.2
  },
  {
    "id": 15,
    "name": "USB-C Cable",
    "sku": "UC-015",
    "price": 9.99,
    "image": "",
    "sold": 189,
    "revenue": 1888.11,
    "growth": -5.3
  }
]
```

---

## 2.10. GET `/api/dashboard/low-stock/`

**Purpose:** Products below minimum stock level.

**Query Parameters:**

| Param  | Type    | Default |
|--------|---------|---------|
| `limit`| integer | 10      |

**Response `200 OK`:**

```json
[
  {
    "id": 88,
    "name": "USB-C Hub",
    "sku": "UCH-088",
    "category": "Electronics",
    "stock": 3,
    "minimum_stock": 10,
    "unit": "pcs",
    "image": "",
    "status": "Low Stock"
  },
  {
    "id": 92,
    "name": "HDMI Adapter",
    "sku": "HDMI-092",
    "category": "Electronics",
    "stock": 0,
    "minimum_stock": 5,
    "unit": "pcs",
    "image": "",
    "status": "Out of Stock"
  }
]
```

**`status` values:** `"Low Stock"` (stock > 0 but ≤ min_stock), `"Out of Stock"` (stock = 0)

---

## 2.11. GET `/api/dashboard/active-sessions/`

**Purpose:** Currently open cash register sessions.

**Response `200 OK`:**

```json
[
  {
    "id": 12,
    "cashier": "Ahmad",
    "opened_at": "2026-08-31T08:00:00+00:00",
    "duration": "6h 30m",
    "total_sales": 2450.00,
    "order_count": 32
  },
  {
    "id": 13,
    "cashier": "Sara",
    "opened_at": "2026-08-31T10:00:00+00:00",
    "duration": "4h 30m",
    "total_sales": 1820.00,
    "order_count": 24
  }
]
```

---

## 2.12. GET `/api/dashboard/recent-notifications/`

**Purpose:** Combined feed of low-stock alerts, recent orders, and recent payments.

**Query Parameters:**

| Param  | Type    | Default |
|--------|---------|---------|
| `limit`| integer | 10      |

**Response `200 OK`:**

```json
[
  {
    "type": "alert",
    "text": "Low stock: USB-C Hub (3 left)",
    "time": "Just now",
    "link": "#/inventory/products"
  },
  {
    "type": "order",
    "text": "Order #ORD-001001 from John Smith",
    "time": "5m ago",
    "link": "#/orders/1001"
  },
  {
    "type": "payment",
    "text": "Payment of $89.99 for #ORD-001001",
    "time": "5m ago",
    "link": "#/orders/1001"
  }
]
```

**`type` values:** `"alert"`, `"order"`, `"payment"`

---

## 2.13. GET `/api/dashboard/quick-actions/`

**Purpose:** Static list of quick-action shortcuts for the dashboard.

**Response `200 OK`:**

```json
[
  {"id": "new_sale", "label": "New Sale", "icon": "plus-circle", "route": "#/pos"},
  {"id": "new_order", "label": "New Order", "icon": "credit-card", "route": "#/orders"},
  {"id": "add_product", "label": "Add Product", "icon": "package-plus", "route": "#/products"},
  {"id": "add_customer", "label": "Add Customer", "icon": "user-plus", "route": "#/customers"},
  {"id": "expense", "label": "Expense", "icon": "dollar-sign", "route": "#/accounting/expenses"},
  {"id": "reports", "label": "Reports", "icon": "bar-chart-2", "route": "#/reports/sales"}
]
```

---

## 2.14. GET `/api/dashboard/order-statistics/`

**Purpose:** Order count breakdown by status.

**Response `200 OK`:**

```json
{
  "completed": 145,
  "draft": 5,
  "cancelled": 3,
  "refunded": 8,
  "pending": 2,
  "partial_refunded": 1
}
```

---

## 2.15. GET `/api/dashboard/inventory-stats/`

**Purpose:** Aggregate inventory statistics.

**Response `200 OK`:**

```json
{
  "total_products": 512,
  "total_stock": 4520,
  "total_value": 45230.00,
  "low_stock": 12,
  "out_of_stock": 3
}
```

---

## 2.16. GET `/api/dashboard/customer-stats/`

**Purpose:** Customer statistics overview.

**Response `200 OK`:**

```json
{
  "total": 234,
  "new_this_month": 18,
  "returning": 89,
  "avg_orders_per_customer": 4.2
}
```

---

## 2.17. GET `/api/dashboard/top-customers/`

**Purpose:** Ranked customers by completed sales revenue with growth.

**Query Parameters:**

| Param    | Type    | Default  |
|----------|---------|----------|
| `limit`  | integer | 10       |
| `period` | string  | `month`  |

**Response `200 OK`:**

```json
{
  "period": "month",
  "items": [
    {
      "id": 12,
      "name": "Acme Corp",
      "orders": 15,
      "revenue": 4500.00,
      "growth": 22.5
    },
    {
      "id": 8,
      "name": "Tech Solutions",
      "orders": 12,
      "revenue": 3200.00,
      "growth": -8.3
    }
  ]
}
```

---

## 2.18. GET `/api/dashboard/top-categories/`

**Purpose:** Ranked product categories by sales quantity with market share.

**Query Parameters:**

| Param    | Type    | Default  |
|----------|---------|----------|
| `limit`  | integer | 10       |
| `period` | string  | `month`  |

**Response `200 OK`:**

```json
{
  "period": "month",
  "total_sales": 520,
  "items": [
    {
      "id": 5,
      "name": "Electronics",
      "sales": 234,
      "share": 45.0
    },
    {
      "id": 3,
      "name": "Clothing",
      "sales": 156,
      "share": 30.0
    },
    {
      "id": null,
      "name": "Uncategorized",
      "sales": 130,
      "share": 25.0
    }
  ]
}
```

---

## 2.19. GET `/api/dashboard/order-statistics-heatmap/`

**Purpose:** Mon-Sun × 2-hour order activity matrix for the heatmap widget.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `week`   |

**Response `200 OK`:**

```json
{
  "period": "week",
  "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  "times": ["2 Am", "4 Am", "6 Am", "8 Am", "10 Am", "12 Am", "14 Pm", "16 Pm", "18 Am"],
  "cells": [
    {"day": "Mon", "time": "2 Am", "orders": 0},
    {"day": "Mon", "time": "8 Am", "orders": 5},
    {"day": "Mon", "time": "10 Am", "orders": 12},
    {"day": "Mon", "time": "14 Pm", "orders": 8},
    {"day": "Tue", "time": "10 Am", "orders": 15}
  ],
  "max_orders": 18
}
```

---

## 2.20. GET `/api/dashboard/recent-transactions/`

**Purpose:** Tabbed transaction feed (sales, purchases, invoices, expenses).

**Query Parameters:**

| Param    | Type    | Default  | Valid Values                                    |
|----------|---------|----------|-------------------------------------------------|
| `type`   | string  | `sales`  | `sales`, `purchases`, `invoices`, `quotations`  |
| `limit`  | integer | 10       | 1–100                                           |

**Response `200 OK`:**

```json
{
  "type": "sales",
  "columns": ["reference", "party", "date", "amount", "status"],
  "items": [
    {
      "id": 1001,
      "reference": "ORD-001001",
      "party": "John Smith",
      "date": "2026-08-31T14:30:00+00:00",
      "amount": 89.99,
      "status": "paid"
    },
    {
      "id": 1000,
      "reference": "ORD-001000",
      "party": "Walk-in Customer",
      "date": "2026-08-31T14:15:00+00:00",
      "amount": 34.50,
      "status": "completed"
    }
  ]
}
```

**`type` behavior:**
- `sales` / `sale` → paid/completed orders
- `purchases` / `purchase` → purchase orders (if model exists)
- `invoices` / `invoice` → falls back to sales data
- `quotations` / `quotation` → falls back to sales data

---

## 2.21. GET `/api/dashboard/sales-statistics/`

**Purpose:** Aligned revenue and expense time series for the overview chart.

**Query Parameters:**

| Param    | Type   | Default  |
|----------|--------|----------|
| `period` | string | `year`   |

**Response `200 OK`:**

```json
{
  "period": "year",
  "labels": ["Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026"],
  "revenue": [45000.00, 52000.00, 48000.00, 51000.00],
  "expense": [12000.00, 14000.00, 11000.00, 13000.00],
  "total_revenue": 196000.00,
  "total_expense": 50000.00
}
```

---

## Error Responses

All endpoints return standard DRF error responses:

**401 Unauthorized:**
```json
{"detail": "Authentication credentials were not provided."}
```

**403 Forbidden (no active tenant):**
```json
{"detail": "You do not have an active tenant."}
```

**400 Bad Request (invalid period):**
```json
{"detail": "Invalid period 'xyz'. Choose from: month, quarter, today, week, year"}
```

---

## Period Aliases

The following aliases are accepted and normalized:

| Input      | Normalized |
|------------|------------|
| `1d`       | `today`    |
| `day`      | `today`    |
| `today`    | `today`    |
| `1w`       | `week`     |
| `weekly`   | `week`     |
| `week`     | `week`     |
| `1m`       | `month`    |
| `monthly`  | `month`    |
| `month`    | `month`    |
| `3m`       | `quarter`  |
| `quarter`  | `quarter`  |
| `6m`       | `year`     |
| `1y`       | `year`     |
| `year`     | `year`     |
