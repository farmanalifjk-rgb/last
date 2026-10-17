# Frontend ↔ Backend API Alignment and Completion Plan

> **Update (current round):** the API explorer now covers every in-scope operation (819
> of 823; 4 are server-only). The deferred-domain question was answered: all domains are
> in scope. The generated status is in `docs/API_OPERATIONS.md`. This plan and its counts
> describe earlier rounds.
> Changes this round: `scripts/map-api.py` (DEFERRED set emptied); `src/js/api-map/`
> (ops, forms, views, plan, explorer); `scripts/check-api-coverage.mjs`; route
> `#/api-explorer` and a sidebar entry under Configuration.


Status: working document. Generated from a static and live audit of the
repository on branch `arena/6acd2283-production`.

## 1. How the audit was done

- **Backend surface.** The Django URL configuration was loaded and
  `manage.py spectacular` produced an OpenAPI schema. Result: **493 paths,
  823 operations** across ~50 domains (accounting, catalog, hr, inventory,
  pricing, reports, saas, suppliers/purchasing, transfers, loyalty, …).
- **Frontend surface.** Every `/api/…` and `${BASE_URL}/…` literal in
  `frontend/src` was extracted (92 distinct paths) and matched against the
  full backend route table.
- **Live verification.** The backend was run locally (SQLite scratch
  settings, outside the repo), a demo tenant was seeded, and endpoints were
  called with a real token.

## 2. Findings

### 2.1 Broken frontend calls (55 of 92 distinct paths do not exist)

The backend code explicitly *retired* several legacy route groups
(`pos/urls.py` comments: "former products-management endpoints are retired",
"legacy POS purchasing routes are retired", "legacy tenancy routes are
retired"). The frontend still calls them.

| Frontend call (broken) | Used by | Canonical replacement |
|---|---|---|
| `/api/products-manage/*` (list/stats/CRUD/export) | AllProducts, Inventory | `/api/products/` (ProductViewSet, paginated, `archive/`) |
| `/api/categories-manage/*` | Categories | `/api/categories/` (array, `tree/`, `{id}/archive/`) |
| `/api/brands/*`, `/api/variants/*` | Brands, Variants | `/api/catalog/brands/`, `/api/catalog/variants/`, `/api/catalog/attributes/` |
| `/api/inventory/summary/`, `/inventory/dashboard/`, `/inventory/products/{id}/…`, `/inventory/analytics/*`, `/inventory/valuation/`, `/inventory/reports/`, `/inventory/stock-adjustments/*`, `/inventory/movements/summary/` | Inventory, Movements, Adjustments | `/api/inventory/overview/`, `/api/inventory/stock/`, `/api/inventory/movements/`, `/api/inventory/adjustments/`, `/api/inventory/abc/`, `/api/inventory/aging/`, `/api/reports/inventory-valuation/` |
| `/api/order-history/*` | OrderHistory | `/api/pos/orders/`, `/api/pos/orders/{id}/` |
| `/api/order-stats/` | OrderHistory | `/api/dashboard/order-statistics/` |
| `/api/refund/process/`, `/api/refund/{id}/`, `/api/refund-history/*` | OrderHistory | `/api/pos/refunds/` (POST), `/api/pos/refunds/order/{order_id}/` |
| `/api/draft-orders/*` | OrderHistory | none mounted (`pos/api_urls/drafts.py` is not included). Feature removed from UI. |
| `/api/cash-sessions/` | OrderHistory | none. Sessions only via `/api/pos/sessions/{open,close,active}/`. |
| `/api/reports/{sales,products,stock,tax}/export/{format}/` | Report pages | `/api/reports/<name>/export/{csv,excel,pdf}/` |
| `/api/pos/products/{id}/`, `/api/pos/customers/{id}/` | pos-api.js (unused) | not needed |

### 2.2 Other frontend defects

- **Build fails on Linux:** `MovementHistoryPage.js` imported `js/movements/…`
  but the folder is `js/Movements/`. *(fixed)*
- **Dead routes:** the sidebar links to `#/inventory/products`,
  `#/inventory/valuation`, `#/inventory/reports`, `#/inventory/analytics`,
  `#/orders?filter=…` variants. The router had no handler for the first four,
  so every click fell through to the placeholder dashboard. *(fixed: aliases and pages)*
- **Hardcoded local backend:** `receipt.js`, `Sidebar.js`, and the product and
  movement image URLs used `http://127.0.0.1:8000`. *(fixed: relative URLs)*
  The only remaining literal is the dev-proxy default in `vite.config.js`, which
  `BACKEND_URL` overrides. Browser code never reads it.
- **Dead files:** `frontend/app.js` (imports a missing module, not loaded by
  `index.html`), `frontend/ex.html` (empty), `src/services/pos-api.js`
  (never imported), `src/components/ProductCard.js` and
  `Layouts/MainLayout.js` (never imported). *(removed)*
- **Unescaped rendering:** controllers interpolate API data straight into
  `innerHTML` (XSS risk). Rewritten code (order history, receipt, insights,
  shared helpers) escapes output. Legacy controllers do not yet (section 5).
- **Shape mismatches:** `/api/categories/` returns a bare array, but
  `Categories.js` reads `response.count` / `response.results`. Pagination
  envelope differs per endpoint, so a single `apiList()` normaliser is needed.
- **No tenant awareness:** the frontend never references tenants. That is
  workable, because the backend derives the active tenant from the user's
  membership. The workspace switcher (`/api/saas/tenants/switch/`) is still
  unexposed, so users with several tenants cannot change workspace.
- **Media not proxied in dev:** `vite.config.js` proxies only `/api`, but
  company logos and product images are served from `/media/`. *(fixed: proxied)*

### 2.3 Missing POS capabilities (backend exists, no UI)

- Parked sales (hold / resume a cart): `/api/pos/parked-sales/`, `…/resume/`
- Cash shift list, cash-in/cash-out: `/api/pos/cash-movements/`
- Customer management (CRUD, addresses, notes, credit limit, loyalty, activity)
- Refund history and processing UI, by order
- Purchasing: suppliers, purchase orders (create/confirm/cancel), goods receipts
- Warehouses and stock transfers (create, receive)
- Pricing: price lists, volume tiers, time-based prices
- Loyalty: programme, tiers, coupons, promotions
- Dashboard: `/api/dashboard/summary/` and KPIs (the current Dashboard is a stub)

### 2.4 Backend defects found during the audit

- **Startup crash:** `backend/audit/middleware.py` had `from httpx import request`.
  `httpx` is not in `requirements.txt`, so a clean install failed at boot.
  The import was unused. *(removed)*
- **Debug output in production:** `backend/backend/urls.py` prints the
  requesting user on every schema request. *(not changed: backend out of scope
  for this frontend task; recommended follow-up)*

## 3. Implementation phases

### Phase 1: Repair and alignment (this change): done, with the open items in section 5
1. Build fix, dead-file removal, relative backend URLs. **Done.**
2. Shared client helpers: `apiList()`, `apiDownload()`, `buildQuery()` in
   `services/api.js`; `escapeHtml()`, `formatMoney()`, `formatDateTime()`,
   `downloadCsv()` in `shared/format.js`. **Done.**
3. `inventory-api.js` rewritten so every function targets a canonical endpoint,
   with adapters where the page needs a different shape. Categories, Brands,
   Variants, All Products, Inventory dashboard, Movements and Adjustments now read
   the real shapes. **Done.**
4. Order history repointed to `/api/pos/orders/` and `/api/pos/refunds/`. The
   controller was rewritten. Draft orders are listed as `status=draft`. Session
   and payment filters were removed because no backend supports them. **Done.**
   Refund processing was exercised against the live backend (order moved to
   `partially_refunded`).
5. Report exports use `apiDownload()` (they previously used `window.open`, which
   cannot send the auth header). Movements and Adjustments export CSV in the
   browser because the backend has no export endpoint for them. **Done.**
6. Sidebar: every link resolves. Legacy hashes are aliased in `main.js`.
   Valuation and ABC analysis got a page. **Done.**

Backend defects fixed during Phase 1:
- `pos/views/reports.py`: `float * Decimal` in the stock report row and in the
  CSV/Excel/PDF exports raised `TypeError`. `/api/reports/stock/` returned 500
  on every request with data. **Fixed.**

### Phase 2: New pages for a production POS
7. **Customers**: list, search, create/edit, archive, detail with summary,
   addresses, notes, credit limit, loyalty and activity.
8. **Cash shifts**: open, active, close with count, cash in/out.
9. **Parked sales**: park the current cart and resume it from the POS.
10. **Purchasing**: suppliers (+contacts), purchase orders (create, confirm,
    cancel), goods receipts.
11. **Warehouses and transfers**: warehouses, stock transfers, receive.
12. **Dashboard**: real KPIs and summary from `/api/dashboard/…`.

### Phase 3: Remaining domains (roadmap, not in this change)
Pricing (price lists, volume tiers, time prices), loyalty, accounting (journal,
ledger, periods, expenses), HR (employees, attendance, leave, payroll),
SaaS billing and tenant switcher, RBAC governance, integrations and webhooks,
FBR / fiscal invoicing, notifications, audit log, admin data tools.

## 4. Acceptance criteria

- `vite build` succeeds on Linux.
- A scripted smoke test calls every endpoint the frontend uses against a live
  backend and gets a non-404 response with the expected envelope.
- Every sidebar route renders a page; no route falls through to the dashboard.
- No API data is interpolated into HTML without escaping.
- No hardcoded `localhost` or `127.0.0.1` in browser code.

## 5. Status and open items (end of Phase 1)

### 5.1 Verification run

- `npx vite build` (Linux, Node 22, lockfile install): **passes**. Warnings only:
  an ineffective dynamic import of `auth.js` and a chunk over 500 kB.
- `node scripts/check-routes.mjs`: **23 of 23** sidebar routes resolve.
- `node scripts/smoke-api.mjs` against a live backend (scratch instance,
  `DJANGO_DEBUG=true`): **38 of 38** read endpoints return 200 with the expected
  envelope.
- Write paths exercised live: stock adjustment create (201), POS checkout (201),
  refund process (201), company settings multipart PATCH (200).
- Vite dev server: `/`, `/receipt.html`, and `/api/*` proxying verified. The
  `/media` proxy reaches the backend.

### 5.2 Not verified

- **No browser-level test.** There is no browser in the sandbox and none can be
  downloaded (only the package and git hosts are reachable). Rendering of each
  page, and the receipt print, have not been seen. The static route check and the
  API smoke test are the evidence.

### 5.3 Open items

1. **Escaping is incomplete.** About 470 interpolations in roughly 30 legacy
   controllers and components (for example `pos.js`, `Roles.js`, `Users.js`,
   `Taxes.js`, `AllProducts.js`, the report pages, and the inventory and movement
   modals) still write API data into `innerHTML` without `escapeHtml`. A blind
   wrap would break HTML fragments built with `.map().join()`, so each one needs
   review. This is required by section 4 and is not done.
2. **Stock adjustment creation has no UI.** `createAdjustment` is imported by
   `Adjustment.js` but never called. The endpoint works (verified live).
3. **Refund receipts** have no backend endpoint. `receipt.html?type=refund` says
   so explicitly.
4. **Order status counters** (`/api/dashboard/order-statistics/`) are not shown.
   The sidebar counter elements do not exist in the markup.
5. **Overstock count** is not provided by any endpoint. The card shows "—".
6. **Movement summary** and **movement or adjustment detail** are computed from
   the most recent 500 records, because the backend has no summary or detail
   route for them.
7. **ABC analysis** shows an empty state until the backend computes it. No
   compute action is wired.
8. **Backend hygiene (not changed here):** `backend/backend/urls.py` prints the
   requesting user on schema requests. 513 `__pycache__/*.cpython-314.pyc` files
   are tracked in Git. Three 0-byte stray files sit under `backend/`. The
   `backend/media/customers/docs/identity*.txt` files (56) have not been
   inspected for personal data.

### 5.4 Phase 2 status

Partly done. Round 2 (section 7) covers customers, suppliers and purchasing,
transfers and warehouses, stock adjustment creation, and the dashboard summary.
Parked sales and cash in/out for POS were added earlier (commit f22b44b).
Section 7.3 lists what is still open.

### 5.5 Running the checks

```
cd frontend
npm ci && npx vite build
node scripts/check-routes.mjs
API_BASE=http://127.0.0.1:8000 SMOKE_USER=... SMOKE_PASSWORD=... SMOKE_DEVICE=... node scripts/smoke-api.mjs
```

## 6. Coverage matrix

`docs/API_COVERAGE.md` lists all 823 backend operations with their frontend
status. Coverage is path-level and approximate: methods are not checked, and
dynamic URLs built at runtime are not traced. Current status: 81 connected,
722 not connected, 20 proposed server-to-server.

Phase 2 in this change: the POS now connects parked sales (create, list,
resume), cash in and cash out, and the parked-sales count in the header. Its
controller escapes API data. Every POS route in the backend is connected.

## 7. Round 2: business domains

Scope agreed with the user: POS plus the core business domains, about 300
operations. Deferred to a later round: accounting, HR, FBR/fiscal, SaaS, RBAC
governance, loyalty, notifications, backups, security, integrations and
webhooks. Server-only endpoints are excluded from the UI and listed in 7.4.
The per-operation status is in `docs/API_COVERAGE.md`.

### 7.1 Delivered in this round

- **Shared UI kit** (`src/shared/ui.js`): escaped rendering helpers, modal
  forms with inline errors, confirm dialog, toasts, tables, pager, status
  badges and action buttons. Pages use delegated listeners and `data-*`
  attributes, so server data never goes into inline handlers.
- **Customers** (`#/customers`): list with search, create, edit, archive,
  customer groups (list and create); detail view with overview, credit limit,
  addresses, notes (pin, edit, delete), loyalty history, activity feed and
  documents (upload, download, delete).
- **Suppliers and purchasing** (`#/purchasing`, alias `#/suppliers`): suppliers
  (create, edit, archive, contacts, portal access); purchase orders (create,
  edit draft, confirm, cancel, detail); goods receipts (list, detail, post a
  receipt against a confirmed order); supplier returns (list, create, process,
  cancel).
- **Transfers and warehouses** (`#/transfers`, alias `#/warehouses`): stock
  transfers (list, create, detail, receive); replenishment tasks (list,
  generate); warehouses (create, edit, archive).
- **Stock adjustment creation**: "New adjustment" on `#/inventory/adjustments`.
  It sets a new quantity or applies a signed change.
- **Dashboard** (`#/`): KPI cards from `/api/dashboard/summary/`, low-stock
  table, recent orders. The page was an empty stub before this round.

Defects fixed along the way:

- Frontend did not boot. `Inventory.js` and `Adjustment.js` bound
  `window.exportCSV`, `exportExcel`, `exportPdf` and `exportAdjustment*` to
  functions that did not exist. The module threw on load, so the whole app
  rendered blank. The bindings were removed; the markup uses the
  `exportProduct*` and `exportAdjustmentCSV` functions, which still exist.
- `GET /api/transfers/replenishment/` returned 500. The view selected
  `target_bin`, which the model does not have. It now selects `from_bin` and
  `to_bin`.
- `POST /api/inventory/adjustments/` returned 500 for business-rule errors (a
  zero change, or stock going negative). The view now returns 400 with the
  message.

### 7.2 Verification run (2026-10-10)

- `vite build`: passes. The output has a chunk-size warning (bundle over
  500 kB) and an `INEFFECTIVE_DYNAMIC_IMPORT` warning. The baseline was not
  recorded, so the warnings are not known to be new or old.
- Live API contract script against the scratch backend: 63 of 64 calls pass.
  The one non-200 is the expected business rule: a warehouse with stock cannot
  be archived.
- Headless Chromium (Vite dev server, live backend): 63 of 63 checks pass.
  Every sidebar route renders, and so do the detail routes. The UI flows are:
  customer create, detail tabs, note saved with the text escaped, credit
  modal, purchase order create (with line editor), supplier create, warehouse
  create, adjustment submit, and empty required fields blocking submit. No
  page errors and no console errors other than network failures to external
  hosts (Google Fonts and an avatar host, which the sandbox cannot reach).

These checks used a scratch database and a scratch backend copy. The test
scripts are not in the repository.

### 7.3 Still open

- **Escaping in legacy controllers.** About 470 interpolations in roughly 30
  older controllers are still unescaped. The new pages escape all server data.
  The older code needs a per-site review, because `.map().join()` fragments
  cannot be wrapped blindly.
- **Operations in scope but not wired** (measured in `docs/API_COVERAGE.md`,
  by domain): settings 54 of 57 not connected, catalog 38 of 51, pricing 38,
  reports 38 (the report pages build `/api/reports/...` URLs in template
  strings, which the path matcher cannot see, so these need a manual check),
  inventory 30 of 38, dashboard charts 27, tax 22, i18n 15, workflow 12, ai 10,
  data import and export 9, API keys 6, hardware devices 6, operations 6, and
  smaller domains (custom fields, email and SMS templates, scheduled reports,
  error logs, audit, draft orders). Payments has 25 not connected; POS is
  done. Pricing and tax were wired in section 7.5, and customer group update
  and delete in section 7.5 too.
- **Customer PUT and DELETE.** Not used. The UI uses PATCH and the archive
  action. Hard delete is not offered, because the customer has order history.
- **Refund receipts, overstock count, movement summary window (latest 500
  records), and ABC compute** remain as listed in section 5.3.
- **Backend hygiene** from section 5.3 is untouched.
- **Automated tests.** The browser and contract scripts are not committed. The
  repository has no frontend test runner for these pages yet.

### 7.4 Server-only endpoints (excluded from the UI)

| Endpoint | Reason |
|---|---|
| `POST /api/payments/providers/{provider}/webhook/` | Payment-provider webhook receiver, called by the provider |
| `POST /api/saas/stripe/webhook/` | Stripe webhook receiver, called by Stripe |
| `GET /api/health/` | Health probe for monitors |
| `GET /api/system-health/` | Health probe for monitors |
| `GET /api/fbr/ims/health/` | Health probe for the fiscal integration (FBR is deferred) |

The OTP endpoints `POST /api/auth/verify-otp/` and `POST /api/auth/resend-otp/`
are not in this list. They are used by the login flow in `src/services/auth.js`
and are counted as connected.

### 7.5 Round 2 continued: pricing, tax, customer groups

Delivered:

- **Pricing** (`#/pricing`, sidebar entries "Price lists" and "Tax rates"):
  - Price lists: list, create, edit, delete. Each list has its items (add,
    edit price and minimum quantity, remove).
  - Group prices: list, create, edit, delete. Group choices come from
    `/api/pricing/customer-groups/`.
  - Volume tiers: list, create, edit, delete.
  - Tax rates: list, create, edit, delete. Rates are entered as a percent and
    sent as a fraction (13 becomes 0.13, rounded to 4 places).
  - Tax exemptions: list, create, edit (including active toggle), delete.
    Scope is customer, product or category, and the matching target is required.
- **Customer groups** (Customers → Customer groups): edit (name, discount,
  description, status) and delete. Delete asks for confirmation and states how
  many customers will move to "No group". Groups are created and renamed
  through `/api/customer-groups/`.

Backend defects fixed:

- `GET /api/pricing/customer-groups/` returned 500 for every tenant. The view
  called `prefetch_related("members")`, which is not a relation on
  `CustomerGroup`. The prefetch was removed.
- `POST /api/tax/rates/` with a duplicate `code` returned 500. It now returns
  400 with "A tax rate with this code already exists."
- `POST` and `PATCH /api/customer-groups/` with a duplicate name returned 500.
  They now return 400. The check lives in `CustomerGroupTenantSerializer`, which
  the viewset uses.
- `POST /api/tax/exemptions/` accepted a scope with no target (for example
  scope `customer` and no customer). It now returns 400 naming the missing field.
- `POST /api/pricing/price-lists/` accepted `valid_to` before `valid_from`. It
  now returns 400 on `valid_to`.
- Earlier this round: reservation create, release and cycle-count run map
  business-rule errors to 400, and the gift card zero balance returns 400. The
  reconciliation close message is readable.

Verification (2026-10-10, live backend on the scratch database):

- Pricing and tax contract script: 26 of 26. It covers create, read, update
  and delete for every pricing and tax write path, plus the new 400 cases.
- Customer group contract script: 3 of 3 (create, rename, delete). Rename to a
  duplicate name returns 400.
- Stock control regression script: 26 of 26.
- Payments contract script: 3 of 3 (zero-count reconciliation lifecycle).
- Cycle-count variance check: a count with variance 1 returns one movement.
  The earlier empty `movements` result came from a count whose counted quantity
  equalled the expected quantity, which correctly produces no movement. No
  defect was found.
- Vite build: passes.
- Headless Chromium on the Vite dev server with the live backend: all 37 sidebar
  and detail routes render, including `#/pos`, `#/pricing?tab=price-lists`,
  `#/pricing?tab=tax-rates` and `#/payments?tab=reconciliations`. The customer
  group manager shows Edit and Delete on every row, and the edit dialog opens
  with the group's name. No page errors. The only console errors are failed
  requests to Google Fonts and an avatar host, which the sandbox cannot reach.
- `src/` has no `localhost` or `127.0.0.1` references.

Still open after this round section:

- **Stores, auth sessions, reports and export** are priority items from the
  round 2 list and are not wired in this change. They stay "not connected" in
  `API_COVERAGE.md`.
- **Legacy duplicate route.** `src/main.js` has a second `route === "/payments"`
  block that renders `PaymentMethodsPage`. It can never run, because the first
  `/payments` block returns earlier. It needs a decision: delete it, or give
  payment methods its own route.
- **Contract scripts are not in the repository.** They are kept in the sandbox
  only.
- **Matrix counts.** The summary counts in `API_COVERAGE.md` were not
  recomputed for section 7.5. The rows for the pricing, tax and customer-group
  operations are updated.

