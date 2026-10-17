# Backend API coverage matrix

> **Current state (generated):** `docs/API_OPERATIONS.md` is the source of truth. It is
> produced by `scripts/map-api.py` from the backend OpenAPI schema. The counts below are
> from that generator run on 2026-10-10.
>
> | Status | Operations |
> |---|---:|
> | total | 823 |
> | server-only (excluded from UI) | 4 |
> | in scope (planned in the API explorer) | 819 |
>
> Deferred domains are now in scope (the user asked to map and build all remaining APIs).
> Server-only: `/api/health/`, `/api/system-health/`, and the two webhook receivers
> (paths containing `/webhook/`).
>
> Every in-scope operation is reachable from the API explorer (`#/api-explorer`), which
> is built from `src/js/api-map/operations.json` by `src/js/api-map/plan.mjs`.
> `node scripts/check-api-coverage.mjs` verifies that each operation is planned exactly once.
>
> The sections below are the round-2 snapshot and are historical. Their counts were not
> recomputed. Use `API_OPERATIONS.md` for current status.

Regenerated 2026-10-10 after the round 2 business-domain work. Operation count: 823 across 493 paths (from the OpenAPI operation list).

> **Update (round 2, section 7.5):** the rows for pricing (price lists, items,
> group prices, volume tiers), tax (rates, exemptions) and customer groups
> (update and delete) are now connected and verified. The summary and per-domain
> counts below were generated before that update and were not recomputed. Treat
> the per-domain counts as a baseline, and read `API_ALIGNMENT_PLAN.md` section
> 7.5 for the current state.

## How to read the status

- **connected (round 2)**: method and path are called by a page added or updated in this round (customers, suppliers, purchasing, transfers and warehouses, stock adjustment creation, dashboard summary). These were checked against a live backend and in a headless browser.
- **connected**: the path was already referenced by the frontend before this round. This status comes from the earlier path-level matcher, so the method may not be used everywhere.
- **not connected**: in scope for this product but not yet wired. The remaining work is listed in `docs/API_ALIGNMENT_PLAN.md`, section 7.3.
- **deferred (out of this round)**: accounting, HR, FBR/fiscal, SaaS, RBAC governance, loyalty, notifications, backups, security, integrations and webhooks. Scope was agreed with the user for a later round.
- **server-only (excluded from UI)**: payment-provider and Stripe webhook receivers, and health probes. These are called by external systems or monitors, not by a user-facing page.
- **server-to-server (proposed)**: called by another service. These are excluded from the UI and listed here for review.

Note: rows marked `connected` come from the earlier path-level matcher, which counted 81 operations. Six of those are also wired in round 2 and are shown as `connected (round 2)`, which leaves 75. The per-method status for round 2 rows is exact; the earlier rows are not verified per method.

## Summary

| Status | Operations |
|---|---:|
| connected (round 2) | 66 |
| connected (before round 2, path-level) | 75 |
| not connected | 396 |
| deferred (out of this round) | 266 |
| server-only (excluded from UI) | 5 |
| server-to-server (proposed) | 15 |

## By domain

| Domain | Operations | Connected | Not connected | Deferred | Server-only / S2S |
|---|---:|---:|---:|---:|---:|
| settings | 57 | 3 | 54 | 0 | 0 |
| accounting | 56 | 0 | 0 | 50 | 6 |
| catalog | 51 | 13 | 38 | 0 | 0 |
| hr | 50 | 0 | 0 | 50 | 0 |
| inventory | 38 | 8 | 30 | 0 | 0 |
| pricing | 38 | 0 | 38 | 0 | 0 |
| reports | 38 | 0 | 38 | 0 | 0 |
| fbr | 33 | 0 | 0 | 32 | 1 |
| rbac | 33 | 0 | 0 | 33 | 0 |
| dashboard | 30 | 3 | 27 | 0 | 0 |
| loyalty | 27 | 0 | 0 | 27 | 0 |
| payments | 26 | 0 | 25 | 0 | 1 |
| saas | 26 | 0 | 0 | 25 | 1 |
| tax | 22 | 0 | 22 | 0 | 0 |
| customers | 18 | 16 | 2 | 0 | 0 |
| notifications | 16 | 0 | 0 | 16 | 0 |
| pos | 16 | 15 | 1 | 0 | 0 |
| i18n | 15 | 0 | 15 | 0 | 0 |
| purchasing | 15 | 14 | 1 | 0 | 0 |
| auth | 13 | 8 | 5 | 0 | 0 |
| workflow | 12 | 0 | 12 | 0 | 0 |
| fiscal | 11 | 0 | 0 | 11 | 0 |
| transfers | 11 | 6 | 5 | 0 | 0 |
| ai | 10 | 0 | 10 | 0 | 0 |
| integrations | 10 | 0 | 0 | 9 | 1 |
| suppliers | 10 | 9 | 1 | 0 | 0 |
| data | 9 | 0 | 9 | 0 | 0 |
| categories | 8 | 7 | 1 | 0 | 0 |
| security | 8 | 0 | 0 | 8 | 0 |
| products | 7 | 7 | 0 | 0 | 0 |
| webhooks | 7 | 0 | 0 | 0 | 7 |
| api-keys | 6 | 0 | 6 | 0 | 0 |
| backups | 6 | 0 | 0 | 5 | 1 |
| customer-groups | 6 | 2 | 4 | 0 | 0 |
| hardware-devices | 6 | 0 | 6 | 0 | 0 |
| operations | 6 | 0 | 6 | 0 | 0 |
| custom-fields | 5 | 0 | 5 | 0 | 0 |
| email-templates | 5 | 0 | 5 | 0 | 0 |
| payment-methods | 5 | 5 | 0 | 0 | 0 |
| roles | 5 | 5 | 0 | 0 | 0 |
| scheduled-reports | 5 | 0 | 5 | 0 | 0 |
| sms-templates | 5 | 0 | 5 | 0 | 0 |
| stores | 5 | 1 | 4 | 0 | 0 |
| taxes | 5 | 5 | 0 | 0 | 0 |
| users | 5 | 5 | 0 | 0 | 0 |
| audit | 4 | 0 | 4 | 0 | 0 |
| customer-addresses | 4 | 2 | 2 | 0 | 0 |
| customer-notes | 4 | 2 | 2 | 0 | 0 |
| supplier-contacts | 4 | 2 | 2 | 0 | 0 |
| customer-documents | 3 | 2 | 1 | 0 | 0 |
| error-logs | 3 | 0 | 3 | 0 | 0 |
| company | 1 | 1 | 0 | 0 | 0 |
| draft-order | 1 | 0 | 1 | 0 | 0 |
| health | 1 | 0 | 0 | 0 | 1 |
| product | 1 | 0 | 1 | 0 | 0 |
| system-health | 1 | 0 | 0 | 0 | 1 |

## Operations

| Domain | Method | Path | Status |
|---|---|---|---|
| accounting | GET | `/api/accounting/accounts/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/accounts/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/accounts/{id}/` | deferred (out of this round) |
| accounting | PUT | `/api/accounting/accounts/{id}/` | deferred (out of this round) |
| accounting | PATCH | `/api/accounting/accounts/{id}/` | deferred (out of this round) |
| accounting | DELETE | `/api/accounting/accounts/{id}/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/events/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/events/{id}/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/events/{id}/retry/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/events/{id}/reverse/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/expense-categories/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/expense-categories/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/expense-categories/{id}/` | deferred (out of this round) |
| accounting | PUT | `/api/accounting/expense-categories/{id}/` | deferred (out of this round) |
| accounting | PATCH | `/api/accounting/expense-categories/{id}/` | deferred (out of this round) |
| accounting | DELETE | `/api/accounting/expense-categories/{id}/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/expenses/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/expenses/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/expenses/{id}/` | deferred (out of this round) |
| accounting | PUT | `/api/accounting/expenses/{id}/` | deferred (out of this round) |
| accounting | PATCH | `/api/accounting/expenses/{id}/` | deferred (out of this round) |
| accounting | DELETE | `/api/accounting/expenses/{id}/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/expenses/{id}/approve/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/expenses/{id}/post-to-journal/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/expenses/{id}/reject/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/financial-account-mappings/` | server-to-server (proposed) |
| accounting | POST | `/api/accounting/financial-account-mappings/` | server-to-server (proposed) |
| accounting | GET | `/api/accounting/financial-account-mappings/{id}/` | server-to-server (proposed) |
| accounting | PUT | `/api/accounting/financial-account-mappings/{id}/` | server-to-server (proposed) |
| accounting | PATCH | `/api/accounting/financial-account-mappings/{id}/` | server-to-server (proposed) |
| accounting | DELETE | `/api/accounting/financial-account-mappings/{id}/` | server-to-server (proposed) |
| accounting | GET | `/api/accounting/journal/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/journal/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/journal/{id}/` | deferred (out of this round) |
| accounting | PUT | `/api/accounting/journal/{id}/` | deferred (out of this round) |
| accounting | PATCH | `/api/accounting/journal/{id}/` | deferred (out of this round) |
| accounting | DELETE | `/api/accounting/journal/{id}/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/journal/{id}/post/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/journal/{id}/replace-lines/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/journal/{id}/reverse/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/journal/create-with-lines/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/ledger/{account_id}/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/periods/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/periods/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/periods/{id}/` | deferred (out of this round) |
| accounting | PUT | `/api/accounting/periods/{id}/` | deferred (out of this round) |
| accounting | PATCH | `/api/accounting/periods/{id}/` | deferred (out of this round) |
| accounting | DELETE | `/api/accounting/periods/{id}/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/periods/{id}/close/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/posting-rules/` | deferred (out of this round) |
| accounting | POST | `/api/accounting/posting-rules/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/posting-rules/{id}/` | deferred (out of this round) |
| accounting | PUT | `/api/accounting/posting-rules/{id}/` | deferred (out of this round) |
| accounting | PATCH | `/api/accounting/posting-rules/{id}/` | deferred (out of this round) |
| accounting | DELETE | `/api/accounting/posting-rules/{id}/` | deferred (out of this round) |
| accounting | GET | `/api/accounting/trial-balance/` | deferred (out of this round) |
| ai | POST | `/api/ai/ask/` | not connected |
| ai | GET | `/api/ai/daily-summary/` | not connected |
| ai | GET | `/api/ai/history/` | not connected |
| ai | GET | `/api/ai/reorder/` | not connected |
| ai | GET | `/api/ai/reorder/{id}/` | not connected |
| ai | PUT | `/api/ai/reorder/{id}/` | not connected |
| ai | PATCH | `/api/ai/reorder/{id}/` | not connected |
| ai | POST | `/api/ai/reorder/generate/` | not connected |
| ai | GET | `/api/ai/templates/` | not connected |
| ai | POST | `/api/ai/templates/` | not connected |
| api-keys | GET | `/api/api-keys/` | not connected |
| api-keys | POST | `/api/api-keys/` | not connected |
| api-keys | GET | `/api/api-keys/{id}/` | not connected |
| api-keys | PUT | `/api/api-keys/{id}/` | not connected |
| api-keys | DELETE | `/api/api-keys/{id}/` | not connected |
| api-keys | POST | `/api/api-keys/{id}/regenerate/` | not connected |
| audit | GET | `/api/audit/events/` | not connected |
| audit | GET | `/api/audit/events/{id}/` | not connected |
| audit | GET | `/api/audit/feed/` | not connected |
| audit | GET | `/api/audit/stats/` | not connected |
| auth | POST | `/api/auth/admin/unlock-account/` | not connected |
| auth | POST | `/api/auth/admin/users/{user_id}/revoke-sessions/` | not connected |
| auth | POST | `/api/auth/change-password/` | not connected |
| auth | POST | `/api/auth/expired-password-change/` | connected |
| auth | POST | `/api/auth/login/` | connected |
| auth | POST | `/api/auth/logout/` | connected |
| auth | GET | `/api/auth/me/` | connected |
| auth | POST | `/api/auth/password-reset/confirm/` | connected |
| auth | POST | `/api/auth/password-reset/request/` | connected |
| auth | POST | `/api/auth/resend-otp/` | connected |
| auth | GET | `/api/auth/sessions/` | not connected |
| auth | POST | `/api/auth/sessions/{id}/revoke/` | not connected |
| auth | POST | `/api/auth/verify-otp/` | connected |
| backups | GET | `/api/backups/` | deferred (out of this round) |
| backups | GET | `/api/backups/{id}/download/` | deferred (out of this round) |
| backups | POST | `/api/backups/create/` | deferred (out of this round) |
| backups | GET | `/api/backups/export-database/` | server-to-server (proposed) |
| backups | POST | `/api/backups/import-database/` | deferred (out of this round) |
| backups | POST | `/api/backups/restore/` | deferred (out of this round) |
| catalog | GET | `/api/catalog/attributes/` | connected |
| catalog | POST | `/api/catalog/attributes/` | connected |
| catalog | GET | `/api/catalog/attributes/{id}/` | connected |
| catalog | PUT | `/api/catalog/attributes/{id}/` | connected |
| catalog | PATCH | `/api/catalog/attributes/{id}/` | connected |
| catalog | DELETE | `/api/catalog/attributes/{id}/` | connected |
| catalog | GET | `/api/catalog/batches/` | not connected |
| catalog | POST | `/api/catalog/batches/` | not connected |
| catalog | GET | `/api/catalog/batches/{id}/` | not connected |
| catalog | PUT | `/api/catalog/batches/{id}/` | not connected |
| catalog | PATCH | `/api/catalog/batches/{id}/` | not connected |
| catalog | DELETE | `/api/catalog/batches/{id}/` | not connected |
| catalog | GET | `/api/catalog/batches/{id}/movements/` | not connected |
| catalog | POST | `/api/catalog/batches/{id}/recall/` | not connected |
| catalog | POST | `/api/catalog/batches/fefo-allocate/` | not connected |
| catalog | GET | `/api/catalog/brands/` | connected |
| catalog | POST | `/api/catalog/brands/` | connected |
| catalog | GET | `/api/catalog/brands/{id}/` | connected |
| catalog | PUT | `/api/catalog/brands/{id}/` | connected |
| catalog | PATCH | `/api/catalog/brands/{id}/` | connected |
| catalog | DELETE | `/api/catalog/brands/{id}/` | connected |
| catalog | GET | `/api/catalog/bundles/` | not connected |
| catalog | POST | `/api/catalog/bundles/` | not connected |
| catalog | GET | `/api/catalog/bundles/{id}/` | not connected |
| catalog | PUT | `/api/catalog/bundles/{id}/` | not connected |
| catalog | PATCH | `/api/catalog/bundles/{id}/` | not connected |
| catalog | DELETE | `/api/catalog/bundles/{id}/` | not connected |
| catalog | GET | `/api/catalog/media/{id}/` | not connected |
| catalog | PUT | `/api/catalog/media/{id}/` | not connected |
| catalog | PATCH | `/api/catalog/media/{id}/` | not connected |
| catalog | DELETE | `/api/catalog/media/{id}/` | not connected |
| catalog | GET | `/api/catalog/products/{product_id}/media/` | not connected |
| catalog | POST | `/api/catalog/products/{product_id}/media/` | not connected |
| catalog | POST | `/api/catalog/products/{product_id}/media/reorder/` | not connected |
| catalog | GET | `/api/catalog/products/{product_id}/variants/` | not connected |
| catalog | POST | `/api/catalog/products/{product_id}/variants/` | not connected |
| catalog | GET | `/api/catalog/products/export/csv/` | connected |
| catalog | POST | `/api/catalog/products/import/csv/` | not connected |
| catalog | GET | `/api/catalog/serials/` | not connected |
| catalog | POST | `/api/catalog/serials/` | not connected |
| catalog | GET | `/api/catalog/serials/{id}/` | not connected |
| catalog | PUT | `/api/catalog/serials/{id}/` | not connected |
| catalog | PATCH | `/api/catalog/serials/{id}/` | not connected |
| catalog | DELETE | `/api/catalog/serials/{id}/` | not connected |
| catalog | POST | `/api/catalog/serials/validate/` | not connected |
| catalog | GET | `/api/catalog/variants/` | not connected |
| catalog | POST | `/api/catalog/variants/` | not connected |
| catalog | GET | `/api/catalog/variants/{id}/` | not connected |
| catalog | PUT | `/api/catalog/variants/{id}/` | not connected |
| catalog | PATCH | `/api/catalog/variants/{id}/` | not connected |
| catalog | DELETE | `/api/catalog/variants/{id}/` | not connected |
| categories | GET | `/api/categories/` | connected |
| categories | POST | `/api/categories/` | connected |
| categories | GET | `/api/categories/{id}/` | connected |
| categories | PUT | `/api/categories/{id}/` | connected |
| categories | PATCH | `/api/categories/{id}/` | connected |
| categories | DELETE | `/api/categories/{id}/` | connected |
| categories | POST | `/api/categories/{id}/archive/` | connected |
| categories | GET | `/api/categories/tree/` | not connected |
| company | GET | `/api/company/` | connected |
| custom-fields | GET | `/api/custom-fields/` | not connected |
| custom-fields | POST | `/api/custom-fields/` | not connected |
| custom-fields | GET | `/api/custom-fields/{id}/` | not connected |
| custom-fields | PUT | `/api/custom-fields/{id}/` | not connected |
| custom-fields | DELETE | `/api/custom-fields/{id}/` | not connected |
| customer-addresses | GET | `/api/customer-addresses/{id}/` | not connected |
| customer-addresses | PUT | `/api/customer-addresses/{id}/` | not connected |
| customer-addresses | PATCH | `/api/customer-addresses/{id}/` | connected (round 2) |
| customer-addresses | DELETE | `/api/customer-addresses/{id}/` | connected (round 2) |
| customer-documents | GET | `/api/customer-documents/{id}/` | not connected |
| customer-documents | DELETE | `/api/customer-documents/{id}/` | connected (round 2) |
| customer-documents | GET | `/api/customer-documents/{id}/download/` | connected (round 2) |
| customer-groups | GET | `/api/customer-groups/` | connected (round 2) |
| customer-groups | POST | `/api/customer-groups/` | connected (round 2) |
| customer-groups | GET | `/api/customer-groups/{id}/` | not connected |
| customer-groups | PUT | `/api/customer-groups/{id}/` | not connected |
| customer-groups | PATCH | `/api/customer-groups/{id}/` | not connected |
| customer-groups | DELETE | `/api/customer-groups/{id}/` | not connected |
| customer-notes | GET | `/api/customer-notes/{id}/` | not connected |
| customer-notes | PUT | `/api/customer-notes/{id}/` | not connected |
| customer-notes | PATCH | `/api/customer-notes/{id}/` | connected (round 2) |
| customer-notes | DELETE | `/api/customer-notes/{id}/` | connected (round 2) |
| customers | GET | `/api/customers/` | connected (round 2) |
| customers | POST | `/api/customers/` | connected (round 2) |
| customers | GET | `/api/customers/{customer_id}/addresses/` | connected (round 2) |
| customers | POST | `/api/customers/{customer_id}/addresses/` | connected (round 2) |
| customers | GET | `/api/customers/{customer_id}/credit-limit/` | connected (round 2) |
| customers | POST | `/api/customers/{customer_id}/credit-limit/` | connected (round 2) |
| customers | GET | `/api/customers/{customer_id}/documents/` | connected (round 2) |
| customers | POST | `/api/customers/{customer_id}/documents/` | connected (round 2) |
| customers | GET | `/api/customers/{customer_id}/loyalty/` | connected (round 2) |
| customers | GET | `/api/customers/{customer_id}/notes/` | connected (round 2) |
| customers | POST | `/api/customers/{customer_id}/notes/` | connected (round 2) |
| customers | GET | `/api/customers/{id}/` | connected (round 2) |
| customers | PUT | `/api/customers/{id}/` | not connected |
| customers | PATCH | `/api/customers/{id}/` | connected (round 2) |
| customers | DELETE | `/api/customers/{id}/` | not connected |
| customers | GET | `/api/customers/{id}/activity/` | connected (round 2) |
| customers | POST | `/api/customers/{id}/archive/` | connected (round 2) |
| customers | GET | `/api/customers/{id}/summary/` | connected (round 2) |
| dashboard | GET | `/api/dashboard/active-sessions/` | not connected |
| dashboard | GET | `/api/dashboard/charts/payment-methods/` | not connected |
| dashboard | GET | `/api/dashboard/charts/profit-loss/` | not connected |
| dashboard | GET | `/api/dashboard/charts/sales-by-category/` | not connected |
| dashboard | GET | `/api/dashboard/charts/sales-heatmap/` | not connected |
| dashboard | GET | `/api/dashboard/charts/sales-performance/` | not connected |
| dashboard | GET | `/api/dashboard/charts/sales-trend/` | not connected |
| dashboard | GET | `/api/dashboard/charts/top-products/` | not connected |
| dashboard | GET | `/api/dashboard/customer-stats/` | not connected |
| dashboard | GET | `/api/dashboard/inventory-stats/` | not connected |
| dashboard | GET | `/api/dashboard/inventory/summary/` | not connected |
| dashboard | GET | `/api/dashboard/kpis/` | not connected |
| dashboard | GET | `/api/dashboard/legacy/overview/` | not connected |
| dashboard | GET | `/api/dashboard/low-stock/` | connected (round 2) |
| dashboard | GET | `/api/dashboard/order-statistics/` | not connected |
| dashboard | GET | `/api/dashboard/order-statistics-heatmap/` | not connected |
| dashboard | GET | `/api/dashboard/overview/` | not connected |
| dashboard | GET | `/api/dashboard/payment-methods-legacy/` | not connected |
| dashboard | GET | `/api/dashboard/quick-actions/` | not connected |
| dashboard | GET | `/api/dashboard/recent-notifications/` | not connected |
| dashboard | GET | `/api/dashboard/recent-orders/` | connected (round 2) |
| dashboard | GET | `/api/dashboard/recent-transactions/` | not connected |
| dashboard | GET | `/api/dashboard/revenue/` | not connected |
| dashboard | GET | `/api/dashboard/sales-chart/` | not connected |
| dashboard | GET | `/api/dashboard/sales-statistics/` | not connected |
| dashboard | GET | `/api/dashboard/summary/` | connected (round 2) |
| dashboard | GET | `/api/dashboard/today-summary/` | not connected |
| dashboard | GET | `/api/dashboard/top-categories/` | not connected |
| dashboard | GET | `/api/dashboard/top-customers/` | not connected |
| dashboard | GET | `/api/dashboard/top-products-legacy/` | not connected |
| data | POST | `/api/data/clear-cache/` | not connected |
| data | GET | `/api/data/export/customers/` | not connected |
| data | GET | `/api/data/export/inventory/` | not connected |
| data | GET | `/api/data/export/products/` | not connected |
| data | GET | `/api/data/export/sales/` | not connected |
| data | POST | `/api/data/import/customers/` | not connected |
| data | POST | `/api/data/import/products/` | not connected |
| data | POST | `/api/data/optimize-database/` | not connected |
| data | POST | `/api/data/rebuild-search-index/` | not connected |
| draft-order | POST | `/api/draft-order/customer/` | not connected |
| email-templates | GET | `/api/email-templates/` | not connected |
| email-templates | POST | `/api/email-templates/` | not connected |
| email-templates | GET | `/api/email-templates/{id}/` | not connected |
| email-templates | PUT | `/api/email-templates/{id}/` | not connected |
| email-templates | DELETE | `/api/email-templates/{id}/` | not connected |
| error-logs | GET | `/api/error-logs/` | not connected |
| error-logs | POST | `/api/error-logs/` | not connected |
| error-logs | POST | `/api/error-logs/{id}/resolve/` | not connected |
| fbr | GET | `/api/fbr/buyer-profiles/` | deferred (out of this round) |
| fbr | POST | `/api/fbr/buyer-profiles/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/buyer-profiles/{id}/` | deferred (out of this round) |
| fbr | PUT | `/api/fbr/buyer-profiles/{id}/` | deferred (out of this round) |
| fbr | PATCH | `/api/fbr/buyer-profiles/{id}/` | deferred (out of this round) |
| fbr | DELETE | `/api/fbr/buyer-profiles/{id}/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/configurations/` | deferred (out of this round) |
| fbr | POST | `/api/fbr/configurations/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/configurations/{id}/` | deferred (out of this round) |
| fbr | PUT | `/api/fbr/configurations/{id}/` | deferred (out of this round) |
| fbr | PATCH | `/api/fbr/configurations/{id}/` | deferred (out of this round) |
| fbr | DELETE | `/api/fbr/configurations/{id}/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/eligibility/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/ims/health/` | server-only (excluded from UI) |
| fbr | GET | `/api/fbr/invoices/{invoice_id}/preview/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/invoices/{invoice_id}/qr.png` | deferred (out of this round) |
| fbr | POST | `/api/fbr/invoices/{invoice_id}/submit/` | deferred (out of this round) |
| fbr | POST | `/api/fbr/invoices/{invoice_id}/validate/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/product-profiles/` | deferred (out of this round) |
| fbr | POST | `/api/fbr/product-profiles/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/product-profiles/{id}/` | deferred (out of this round) |
| fbr | PUT | `/api/fbr/product-profiles/{id}/` | deferred (out of this round) |
| fbr | PATCH | `/api/fbr/product-profiles/{id}/` | deferred (out of this round) |
| fbr | DELETE | `/api/fbr/product-profiles/{id}/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/reference/hs-codes/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/reference/provinces/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/reference/sro-schedules/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/reference/transaction-types/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/reference/uom/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/submissions/` | deferred (out of this round) |
| fbr | GET | `/api/fbr/submissions/{id}/` | deferred (out of this round) |
| fbr | POST | `/api/fbr/submissions/{id}/reconcile/` | deferred (out of this round) |
| fbr | POST | `/api/fbr/submissions/{id}/retry/` | deferred (out of this round) |
| fiscal | GET | `/api/fiscal/devices/` | deferred (out of this round) |
| fiscal | POST | `/api/fiscal/devices/` | deferred (out of this round) |
| fiscal | GET | `/api/fiscal/invoices/` | deferred (out of this round) |
| fiscal | POST | `/api/fiscal/invoices/{invoice_id}/submit/` | deferred (out of this round) |
| fiscal | GET | `/api/fiscal/invoices/{id}/` | deferred (out of this round) |
| fiscal | POST | `/api/fiscal/invoices/{id}/cancel/` | deferred (out of this round) |
| fiscal | GET | `/api/fiscal/invoices/{id}/xml/` | deferred (out of this round) |
| fiscal | POST | `/api/fiscal/invoices/issue/` | deferred (out of this round) |
| fiscal | GET | `/api/fiscal/sequences/` | deferred (out of this round) |
| fiscal | POST | `/api/fiscal/sequences/` | deferred (out of this round) |
| fiscal | GET | `/api/fiscal/submissions/` | deferred (out of this round) |
| hardware-devices | GET | `/api/hardware-devices/` | not connected |
| hardware-devices | POST | `/api/hardware-devices/` | not connected |
| hardware-devices | GET | `/api/hardware-devices/{id}/` | not connected |
| hardware-devices | PUT | `/api/hardware-devices/{id}/` | not connected |
| hardware-devices | DELETE | `/api/hardware-devices/{id}/` | not connected |
| hardware-devices | POST | `/api/hardware-devices/{id}/test/` | not connected |
| health | GET | `/api/health/` | server-only (excluded from UI) |
| hr | GET | `/api/hr/attendance/` | deferred (out of this round) |
| hr | POST | `/api/hr/attendance/` | deferred (out of this round) |
| hr | GET | `/api/hr/attendance/{id}/` | deferred (out of this round) |
| hr | PUT | `/api/hr/attendance/{id}/` | deferred (out of this round) |
| hr | PATCH | `/api/hr/attendance/{id}/` | deferred (out of this round) |
| hr | DELETE | `/api/hr/attendance/{id}/` | deferred (out of this round) |
| hr | POST | `/api/hr/attendance/{id}/clock_in/` | deferred (out of this round) |
| hr | POST | `/api/hr/attendance/{id}/clock_out/` | deferred (out of this round) |
| hr | GET | `/api/hr/departments/` | deferred (out of this round) |
| hr | POST | `/api/hr/departments/` | deferred (out of this round) |
| hr | GET | `/api/hr/departments/{id}/` | deferred (out of this round) |
| hr | PUT | `/api/hr/departments/{id}/` | deferred (out of this round) |
| hr | PATCH | `/api/hr/departments/{id}/` | deferred (out of this round) |
| hr | DELETE | `/api/hr/departments/{id}/` | deferred (out of this round) |
| hr | GET | `/api/hr/employees/` | deferred (out of this round) |
| hr | POST | `/api/hr/employees/` | deferred (out of this round) |
| hr | GET | `/api/hr/employees/{id}/` | deferred (out of this round) |
| hr | PUT | `/api/hr/employees/{id}/` | deferred (out of this round) |
| hr | PATCH | `/api/hr/employees/{id}/` | deferred (out of this round) |
| hr | DELETE | `/api/hr/employees/{id}/` | deferred (out of this round) |
| hr | GET | `/api/hr/leave-requests/` | deferred (out of this round) |
| hr | POST | `/api/hr/leave-requests/` | deferred (out of this round) |
| hr | GET | `/api/hr/leave-requests/{id}/` | deferred (out of this round) |
| hr | PUT | `/api/hr/leave-requests/{id}/` | deferred (out of this round) |
| hr | PATCH | `/api/hr/leave-requests/{id}/` | deferred (out of this round) |
| hr | DELETE | `/api/hr/leave-requests/{id}/` | deferred (out of this round) |
| hr | POST | `/api/hr/leave-requests/{id}/approve/` | deferred (out of this round) |
| hr | POST | `/api/hr/leave-requests/{id}/reject/` | deferred (out of this round) |
| hr | GET | `/api/hr/leave-types/` | deferred (out of this round) |
| hr | POST | `/api/hr/leave-types/` | deferred (out of this round) |
| hr | GET | `/api/hr/leave-types/{id}/` | deferred (out of this round) |
| hr | PUT | `/api/hr/leave-types/{id}/` | deferred (out of this round) |
| hr | PATCH | `/api/hr/leave-types/{id}/` | deferred (out of this round) |
| hr | DELETE | `/api/hr/leave-types/{id}/` | deferred (out of this round) |
| hr | GET | `/api/hr/payroll/` | deferred (out of this round) |
| hr | POST | `/api/hr/payroll/` | deferred (out of this round) |
| hr | GET | `/api/hr/payroll-entries/` | deferred (out of this round) |
| hr | GET | `/api/hr/payroll-entries/{id}/` | deferred (out of this round) |
| hr | GET | `/api/hr/payroll/{id}/` | deferred (out of this round) |
| hr | PUT | `/api/hr/payroll/{id}/` | deferred (out of this round) |
| hr | PATCH | `/api/hr/payroll/{id}/` | deferred (out of this round) |
| hr | DELETE | `/api/hr/payroll/{id}/` | deferred (out of this round) |
| hr | POST | `/api/hr/payroll/{id}/generate_entries/` | deferred (out of this round) |
| hr | POST | `/api/hr/payroll/{id}/post_payroll/` | deferred (out of this round) |
| hr | GET | `/api/hr/shifts/` | deferred (out of this round) |
| hr | POST | `/api/hr/shifts/` | deferred (out of this round) |
| hr | GET | `/api/hr/shifts/{id}/` | deferred (out of this round) |
| hr | PUT | `/api/hr/shifts/{id}/` | deferred (out of this round) |
| hr | PATCH | `/api/hr/shifts/{id}/` | deferred (out of this round) |
| hr | DELETE | `/api/hr/shifts/{id}/` | deferred (out of this round) |
| i18n | GET | `/api/i18n/convert/` | not connected |
| i18n | GET | `/api/i18n/currencies/` | not connected |
| i18n | POST | `/api/i18n/currencies/` | not connected |
| i18n | GET | `/api/i18n/currencies/{id}/` | not connected |
| i18n | PUT | `/api/i18n/currencies/{id}/` | not connected |
| i18n | PATCH | `/api/i18n/currencies/{id}/` | not connected |
| i18n | DELETE | `/api/i18n/currencies/{id}/` | not connected |
| i18n | GET | `/api/i18n/format/` | not connected |
| i18n | GET | `/api/i18n/languages/` | not connected |
| i18n | POST | `/api/i18n/languages/` | not connected |
| i18n | GET | `/api/i18n/me/locale/` | not connected |
| i18n | PUT | `/api/i18n/me/locale/` | not connected |
| i18n | GET | `/api/i18n/translations/` | not connected |
| i18n | POST | `/api/i18n/translations/` | not connected |
| i18n | POST | `/api/i18n/translations/batch/` | not connected |
| integrations | GET | `/api/integrations/` | deferred (out of this round) |
| integrations | POST | `/api/integrations/` | deferred (out of this round) |
| integrations | POST | `/api/integrations/{integration_id}/push-invoice/` | deferred (out of this round) |
| integrations | POST | `/api/integrations/{integration_id}/sync/` | deferred (out of this round) |
| integrations | GET | `/api/integrations/{id}/` | deferred (out of this round) |
| integrations | PUT | `/api/integrations/{id}/` | deferred (out of this round) |
| integrations | PATCH | `/api/integrations/{id}/` | deferred (out of this round) |
| integrations | DELETE | `/api/integrations/{id}/` | deferred (out of this round) |
| integrations | GET | `/api/integrations/logs/` | deferred (out of this round) |
| integrations | GET | `/api/integrations/mappings/` | server-to-server (proposed) |
| inventory | GET | `/api/inventory/abc/` | not connected |
| inventory | GET | `/api/inventory/adjustments/` | connected (round 2) |
| inventory | POST | `/api/inventory/adjustments/` | connected (round 2) |
| inventory | GET | `/api/inventory/aging/` | not connected |
| inventory | GET | `/api/inventory/available/` | not connected |
| inventory | GET | `/api/inventory/bins/` | not connected |
| inventory | POST | `/api/inventory/bins/` | not connected |
| inventory | GET | `/api/inventory/bins/{id}/` | not connected |
| inventory | PUT | `/api/inventory/bins/{id}/` | not connected |
| inventory | PATCH | `/api/inventory/bins/{id}/` | not connected |
| inventory | DELETE | `/api/inventory/bins/{id}/` | not connected |
| inventory | GET | `/api/inventory/cycle-counts/` | not connected |
| inventory | POST | `/api/inventory/cycle-counts/` | not connected |
| inventory | GET | `/api/inventory/cycle-counts/{id}/` | not connected |
| inventory | PUT | `/api/inventory/cycle-counts/{id}/` | not connected |
| inventory | PATCH | `/api/inventory/cycle-counts/{id}/` | not connected |
| inventory | DELETE | `/api/inventory/cycle-counts/{id}/` | not connected |
| inventory | POST | `/api/inventory/cycle-counts/{id}/run/` | not connected |
| inventory | GET | `/api/inventory/movements/` | not connected |
| inventory | GET | `/api/inventory/overview/` | connected |
| inventory | GET | `/api/inventory/reorder-alerts/` | not connected |
| inventory | GET | `/api/inventory/reorder-rules/` | not connected |
| inventory | POST | `/api/inventory/reorder-rules/` | not connected |
| inventory | GET | `/api/inventory/reorder-rules/{id}/` | not connected |
| inventory | PUT | `/api/inventory/reorder-rules/{id}/` | not connected |
| inventory | PATCH | `/api/inventory/reorder-rules/{id}/` | not connected |
| inventory | DELETE | `/api/inventory/reorder-rules/{id}/` | not connected |
| inventory | GET | `/api/inventory/reservations/` | not connected |
| inventory | POST | `/api/inventory/reservations/` | not connected |
| inventory | POST | `/api/inventory/reservations/{id}/release/` | not connected |
| inventory | GET | `/api/inventory/stock/` | not connected |
| inventory | GET | `/api/inventory/warehouses/` | connected (round 2) |
| inventory | POST | `/api/inventory/warehouses/` | connected (round 2) |
| inventory | GET | `/api/inventory/warehouses/{id}/` | connected (round 2) |
| inventory | PUT | `/api/inventory/warehouses/{id}/` | not connected |
| inventory | PATCH | `/api/inventory/warehouses/{id}/` | connected (round 2) |
| inventory | DELETE | `/api/inventory/warehouses/{id}/` | not connected |
| inventory | POST | `/api/inventory/warehouses/{id}/archive/` | connected (round 2) |
| loyalty | GET | `/api/loyalty/coupons/` | deferred (out of this round) |
| loyalty | POST | `/api/loyalty/coupons/` | deferred (out of this round) |
| loyalty | GET | `/api/loyalty/coupons/{id}/` | deferred (out of this round) |
| loyalty | PUT | `/api/loyalty/coupons/{id}/` | deferred (out of this round) |
| loyalty | PATCH | `/api/loyalty/coupons/{id}/` | deferred (out of this round) |
| loyalty | DELETE | `/api/loyalty/coupons/{id}/` | deferred (out of this round) |
| loyalty | POST | `/api/loyalty/coupons/validate/` | deferred (out of this round) |
| loyalty | GET | `/api/loyalty/program/` | deferred (out of this round) |
| loyalty | PUT | `/api/loyalty/program/` | deferred (out of this round) |
| loyalty | GET | `/api/loyalty/promotions/` | deferred (out of this round) |
| loyalty | POST | `/api/loyalty/promotions/` | deferred (out of this round) |
| loyalty | GET | `/api/loyalty/promotions/{id}/` | deferred (out of this round) |
| loyalty | PUT | `/api/loyalty/promotions/{id}/` | deferred (out of this round) |
| loyalty | PATCH | `/api/loyalty/promotions/{id}/` | deferred (out of this round) |
| loyalty | DELETE | `/api/loyalty/promotions/{id}/` | deferred (out of this round) |
| loyalty | GET | `/api/loyalty/tiers/` | deferred (out of this round) |
| loyalty | POST | `/api/loyalty/tiers/` | deferred (out of this round) |
| loyalty | GET | `/api/loyalty/tiers/{id}/` | deferred (out of this round) |
| loyalty | PUT | `/api/loyalty/tiers/{id}/` | deferred (out of this round) |
| loyalty | PATCH | `/api/loyalty/tiers/{id}/` | deferred (out of this round) |
| loyalty | DELETE | `/api/loyalty/tiers/{id}/` | deferred (out of this round) |
| loyalty | GET | `/api/loyalty/transactions/` | deferred (out of this round) |
| loyalty | POST | `/api/loyalty/transactions/` | deferred (out of this round) |
| loyalty | GET | `/api/loyalty/transactions/{id}/` | deferred (out of this round) |
| loyalty | PUT | `/api/loyalty/transactions/{id}/` | deferred (out of this round) |
| loyalty | PATCH | `/api/loyalty/transactions/{id}/` | deferred (out of this round) |
| loyalty | DELETE | `/api/loyalty/transactions/{id}/` | deferred (out of this round) |
| notifications | GET | `/api/notifications/digests/` | deferred (out of this round) |
| notifications | GET | `/api/notifications/email-queue/` | deferred (out of this round) |
| notifications | GET | `/api/notifications/email-queue/{id}/` | deferred (out of this round) |
| notifications | GET | `/api/notifications/notifications/` | deferred (out of this round) |
| notifications | GET | `/api/notifications/notifications/{id}/` | deferred (out of this round) |
| notifications | POST | `/api/notifications/notifications/{id}/read/` | deferred (out of this round) |
| notifications | POST | `/api/notifications/notifications/read-all/` | deferred (out of this round) |
| notifications | GET | `/api/notifications/rules/` | deferred (out of this round) |
| notifications | POST | `/api/notifications/rules/` | deferred (out of this round) |
| notifications | GET | `/api/notifications/rules/{id}/` | deferred (out of this round) |
| notifications | PUT | `/api/notifications/rules/{id}/` | deferred (out of this round) |
| notifications | PATCH | `/api/notifications/rules/{id}/` | deferred (out of this round) |
| notifications | DELETE | `/api/notifications/rules/{id}/` | deferred (out of this round) |
| notifications | POST | `/api/notifications/scans/run/` | deferred (out of this round) |
| notifications | GET | `/api/notifications/sms-queue/` | deferred (out of this round) |
| notifications | GET | `/api/notifications/sms-queue/{id}/` | deferred (out of this round) |
| operations | GET | `/api/operations/notifications/` | not connected |
| operations | POST | `/api/operations/notifications/` | not connected |
| operations | GET | `/api/operations/notifications/{id}/` | not connected |
| operations | POST | `/api/operations/notifications/{id}/mark_read/` | not connected |
| operations | POST | `/api/operations/notifications/mark_all_read/` | not connected |
| operations | GET | `/api/operations/notifications/unread_count/` | not connected |
| payment-methods | GET | `/api/payment-methods/` | connected |
| payment-methods | POST | `/api/payment-methods/` | connected |
| payment-methods | GET | `/api/payment-methods/{id}/` | connected |
| payment-methods | PUT | `/api/payment-methods/{id}/` | connected |
| payment-methods | DELETE | `/api/payment-methods/{id}/` | connected |
| payments | GET | `/api/payments/gift-cards/` | not connected |
| payments | POST | `/api/payments/gift-cards/` | not connected |
| payments | GET | `/api/payments/gift-cards/{id}/` | not connected |
| payments | POST | `/api/payments/gift-cards/{id}/disable/` | not connected |
| payments | POST | `/api/payments/gift-cards/{id}/topup/` | not connected |
| payments | GET | `/api/payments/providers/` | not connected |
| payments | POST | `/api/payments/providers/{provider}/checkout/` | not connected |
| payments | GET | `/api/payments/providers/{provider}/config/` | not connected |
| payments | GET | `/api/payments/providers/{provider}/operations/` | not connected |
| payments | GET | `/api/payments/providers/{provider}/operations/{id}/` | not connected |
| payments | POST | `/api/payments/providers/{provider}/operations/{id}/cancel/` | not connected |
| payments | POST | `/api/payments/providers/{provider}/operations/{id}/verify/` | not connected |
| payments | GET | `/api/payments/providers/{provider}/refund-operations/{id}/` | not connected |
| payments | POST | `/api/payments/providers/{provider}/refund-operations/{id}/verify/` | not connected |
| payments | POST | `/api/payments/providers/{provider}/refunds/{refund_id}/` | not connected |
| payments | POST | `/api/payments/providers/{provider}/webhook/` | server-only (excluded from UI) |
| payments | GET | `/api/payments/reconciliations/` | not connected |
| payments | POST | `/api/payments/reconciliations/` | not connected |
| payments | GET | `/api/payments/reconciliations/{id}/` | not connected |
| payments | POST | `/api/payments/reconciliations/{id}/close/` | not connected |
| payments | GET | `/api/payments/refund-settlements/` | not connected |
| payments | POST | `/api/payments/refunds/{refund_id}/store-credit/` | not connected |
| payments | GET | `/api/payments/register/` | not connected |
| payments | GET | `/api/payments/register/{id}/` | not connected |
| payments | GET | `/api/payments/store-credit/{customer_id}/` | not connected |
| payments | POST | `/api/payments/store-credit/{customer_id}/issue/` | not connected |
| pos | POST | `/api/pos/cash-movements/` | connected |
| pos | POST | `/api/pos/checkout/` | connected |
| pos | GET | `/api/pos/customers/` | connected |
| pos | GET | `/api/pos/orders/` | not connected |
| pos | GET | `/api/pos/orders/{order_id}/receipt/` | connected |
| pos | GET | `/api/pos/orders/{id}/` | connected |
| pos | GET | `/api/pos/parked-sales/` | connected |
| pos | POST | `/api/pos/parked-sales/` | connected |
| pos | POST | `/api/pos/parked-sales/{id}/resume/` | connected |
| pos | POST | `/api/pos/preview/` | connected |
| pos | GET | `/api/pos/products/` | connected |
| pos | POST | `/api/pos/refunds/` | connected |
| pos | GET | `/api/pos/refunds/order/{order_id}/` | connected |
| pos | GET | `/api/pos/sessions/active/` | connected |
| pos | POST | `/api/pos/sessions/close/` | connected |
| pos | POST | `/api/pos/sessions/open/` | connected |
| pricing | GET | `/api/pricing/buyx-gety/` | not connected |
| pricing | POST | `/api/pricing/buyx-gety/` | not connected |
| pricing | GET | `/api/pricing/buyx-gety/{id}/` | not connected |
| pricing | PUT | `/api/pricing/buyx-gety/{id}/` | not connected |
| pricing | PATCH | `/api/pricing/buyx-gety/{id}/` | not connected |
| pricing | DELETE | `/api/pricing/buyx-gety/{id}/` | not connected |
| pricing | GET | `/api/pricing/customer-groups/` | not connected |
| pricing | GET | `/api/pricing/group-prices/` | not connected |
| pricing | POST | `/api/pricing/group-prices/` | not connected |
| pricing | GET | `/api/pricing/group-prices/{id}/` | not connected |
| pricing | PUT | `/api/pricing/group-prices/{id}/` | not connected |
| pricing | PATCH | `/api/pricing/group-prices/{id}/` | not connected |
| pricing | DELETE | `/api/pricing/group-prices/{id}/` | not connected |
| pricing | GET | `/api/pricing/price-lists/` | not connected |
| pricing | POST | `/api/pricing/price-lists/` | not connected |
| pricing | GET | `/api/pricing/price-lists/{id}/` | not connected |
| pricing | PUT | `/api/pricing/price-lists/{id}/` | not connected |
| pricing | PATCH | `/api/pricing/price-lists/{id}/` | not connected |
| pricing | DELETE | `/api/pricing/price-lists/{id}/` | not connected |
| pricing | GET | `/api/pricing/price-lists/{price_list_id}/items/` | not connected |
| pricing | POST | `/api/pricing/price-lists/{price_list_id}/items/` | not connected |
| pricing | GET | `/api/pricing/price-lists/{price_list_id}/items/{id}/` | not connected |
| pricing | PUT | `/api/pricing/price-lists/{price_list_id}/items/{id}/` | not connected |
| pricing | PATCH | `/api/pricing/price-lists/{price_list_id}/items/{id}/` | not connected |
| pricing | DELETE | `/api/pricing/price-lists/{price_list_id}/items/{id}/` | not connected |
| pricing | GET | `/api/pricing/resolve/` | not connected |
| pricing | GET | `/api/pricing/time-prices/` | not connected |
| pricing | POST | `/api/pricing/time-prices/` | not connected |
| pricing | GET | `/api/pricing/time-prices/{id}/` | not connected |
| pricing | PUT | `/api/pricing/time-prices/{id}/` | not connected |
| pricing | PATCH | `/api/pricing/time-prices/{id}/` | not connected |
| pricing | DELETE | `/api/pricing/time-prices/{id}/` | not connected |
| pricing | GET | `/api/pricing/volume-tiers/` | not connected |
| pricing | POST | `/api/pricing/volume-tiers/` | not connected |
| pricing | GET | `/api/pricing/volume-tiers/{id}/` | not connected |
| pricing | PUT | `/api/pricing/volume-tiers/{id}/` | not connected |
| pricing | PATCH | `/api/pricing/volume-tiers/{id}/` | not connected |
| pricing | DELETE | `/api/pricing/volume-tiers/{id}/` | not connected |
| product | GET | `/api/product/barcode/{barcode}/` | not connected |
| products | GET | `/api/products/` | connected |
| products | POST | `/api/products/` | connected |
| products | GET | `/api/products/{id}/` | connected |
| products | PUT | `/api/products/{id}/` | connected |
| products | PATCH | `/api/products/{id}/` | connected |
| products | DELETE | `/api/products/{id}/` | connected |
| products | POST | `/api/products/{id}/archive/` | connected |
| purchasing | GET | `/api/purchasing/purchase-orders/` | connected (round 2) |
| purchasing | POST | `/api/purchasing/purchase-orders/` | connected (round 2) |
| purchasing | GET | `/api/purchasing/purchase-orders/{id}/` | connected (round 2) |
| purchasing | PUT | `/api/purchasing/purchase-orders/{id}/` | not connected |
| purchasing | PATCH | `/api/purchasing/purchase-orders/{id}/` | connected (round 2) |
| purchasing | POST | `/api/purchasing/purchase-orders/{id}/cancel/` | connected (round 2) |
| purchasing | POST | `/api/purchasing/purchase-orders/{id}/confirm/` | connected (round 2) |
| purchasing | GET | `/api/purchasing/purchase-returns/` | connected (round 2) |
| purchasing | POST | `/api/purchasing/purchase-returns/` | connected (round 2) |
| purchasing | GET | `/api/purchasing/purchase-returns/{id}/` | connected (round 2) |
| purchasing | POST | `/api/purchasing/purchase-returns/{id}/cancel/` | connected (round 2) |
| purchasing | POST | `/api/purchasing/purchase-returns/{id}/process/` | connected (round 2) |
| purchasing | GET | `/api/purchasing/receipts/` | connected (round 2) |
| purchasing | POST | `/api/purchasing/receipts/` | connected (round 2) |
| purchasing | GET | `/api/purchasing/receipts/{id}/` | connected (round 2) |
| rbac | GET | `/api/rbac/check/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/governance/assignments/` | deferred (out of this round) |
| rbac | POST | `/api/rbac/governance/assignments/` | deferred (out of this round) |
| rbac | DELETE | `/api/rbac/governance/assignments/{id}/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/governance/effective/{user_id}/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/governance/members/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/governance/permissions/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/governance/roles/` | deferred (out of this round) |
| rbac | POST | `/api/rbac/governance/roles/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/governance/roles/{id}/` | deferred (out of this round) |
| rbac | PATCH | `/api/rbac/governance/roles/{id}/` | deferred (out of this round) |
| rbac | DELETE | `/api/rbac/governance/roles/{id}/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/me/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/modules/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/overrides/` | deferred (out of this round) |
| rbac | POST | `/api/rbac/overrides/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/permissions/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/roles/` | deferred (out of this round) |
| rbac | POST | `/api/rbac/roles/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/roles/{id}/` | deferred (out of this round) |
| rbac | PUT | `/api/rbac/roles/{id}/` | deferred (out of this round) |
| rbac | PATCH | `/api/rbac/roles/{id}/` | deferred (out of this round) |
| rbac | DELETE | `/api/rbac/roles/{id}/` | deferred (out of this round) |
| rbac | POST | `/api/rbac/roles/{role_id}/apply-template/` | deferred (out of this round) |
| rbac | POST | `/api/rbac/seed/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/templates/` | deferred (out of this round) |
| rbac | POST | `/api/rbac/templates/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/user-roles/` | deferred (out of this round) |
| rbac | POST | `/api/rbac/user-roles/` | deferred (out of this round) |
| rbac | GET | `/api/rbac/user-roles/{id}/` | deferred (out of this round) |
| rbac | PUT | `/api/rbac/user-roles/{id}/` | deferred (out of this round) |
| rbac | PATCH | `/api/rbac/user-roles/{id}/` | deferred (out of this round) |
| rbac | DELETE | `/api/rbac/user-roles/{id}/` | deferred (out of this round) |
| reports | GET | `/api/reports/balance-sheet/` | not connected |
| reports | GET | `/api/reports/cash-flow/` | not connected |
| reports | GET | `/api/reports/customer-sales/` | not connected |
| reports | GET | `/api/reports/export/{report_key}/` | not connected |
| reports | GET | `/api/reports/financial-balance-sheet/` | not connected |
| reports | GET | `/api/reports/financial-cash-flow/` | not connected |
| reports | GET | `/api/reports/financial-dashboard/` | not connected |
| reports | GET | `/api/reports/financial-exceptions/` | not connected |
| reports | GET | `/api/reports/financial-general-ledger/{account_id}/` | not connected |
| reports | GET | `/api/reports/financial-profit-loss/` | not connected |
| reports | GET | `/api/reports/financial-trial-balance/` | not connected |
| reports | GET | `/api/reports/inventory-valuation/` | not connected |
| reports | GET | `/api/reports/products/` | not connected |
| reports | GET | `/api/reports/products/export/csv/` | not connected |
| reports | GET | `/api/reports/products/export/excel/` | not connected |
| reports | GET | `/api/reports/products/export/pdf/` | not connected |
| reports | GET | `/api/reports/profit-loss/` | not connected |
| reports | GET | `/api/reports/profit-margin/` | not connected |
| reports | GET | `/api/reports/purchase-summary/` | not connected |
| reports | GET | `/api/reports/sales/` | not connected |
| reports | GET | `/api/reports/sales-by-category/` | not connected |
| reports | GET | `/api/reports/sales-by-day/` | not connected |
| reports | GET | `/api/reports/sales-by-payment/` | not connected |
| reports | GET | `/api/reports/sales-summary/` | not connected |
| reports | GET | `/api/reports/sales/export/csv/` | not connected |
| reports | GET | `/api/reports/sales/export/excel/` | not connected |
| reports | GET | `/api/reports/sales/export/pdf/` | not connected |
| reports | GET | `/api/reports/stock/` | not connected |
| reports | GET | `/api/reports/stock-movements/` | not connected |
| reports | GET | `/api/reports/stock/export/csv/` | not connected |
| reports | GET | `/api/reports/stock/export/excel/` | not connected |
| reports | GET | `/api/reports/stock/export/pdf/` | not connected |
| reports | GET | `/api/reports/supplier-spend/` | not connected |
| reports | GET | `/api/reports/tax/` | not connected |
| reports | GET | `/api/reports/tax/export/csv/` | not connected |
| reports | GET | `/api/reports/tax/export/excel/` | not connected |
| reports | GET | `/api/reports/tax/export/pdf/` | not connected |
| reports | GET | `/api/reports/top-products/` | not connected |
| roles | GET | `/api/roles/` | connected |
| roles | POST | `/api/roles/` | connected |
| roles | GET | `/api/roles/{id}/` | connected |
| roles | PUT | `/api/roles/{id}/` | connected |
| roles | DELETE | `/api/roles/{id}/` | connected |
| saas | GET | `/api/saas/billing/admin/payments/` | deferred (out of this round) |
| saas | POST | `/api/saas/billing/admin/payments/{payment_id}/reject/` | deferred (out of this round) |
| saas | POST | `/api/saas/billing/admin/payments/{payment_id}/verify/` | deferred (out of this round) |
| saas | GET | `/api/saas/billing/invoices/` | deferred (out of this round) |
| saas | GET | `/api/saas/billing/manual-methods/` | deferred (out of this round) |
| saas | GET | `/api/saas/billing/overview/` | deferred (out of this round) |
| saas | GET | `/api/saas/billing/payments/` | deferred (out of this round) |
| saas | GET | `/api/saas/billing/plans/` | deferred (out of this round) |
| saas | GET | `/api/saas/billing/provider-status/` | deferred (out of this round) |
| saas | GET | `/api/saas/billing/requests/` | deferred (out of this round) |
| saas | POST | `/api/saas/billing/requests/` | deferred (out of this round) |
| saas | POST | `/api/saas/billing/requests/{request_id}/submit-payment/` | deferred (out of this round) |
| saas | GET | `/api/saas/billing/subscription/` | deferred (out of this round) |
| saas | GET | `/api/saas/billing/usage/` | deferred (out of this round) |
| saas | GET | `/api/saas/invoices/` | deferred (out of this round) |
| saas | GET | `/api/saas/limits/` | deferred (out of this round) |
| saas | GET | `/api/saas/plans/` | deferred (out of this round) |
| saas | POST | `/api/saas/stripe/webhook/` | server-only (excluded from UI) |
| saas | POST | `/api/saas/subscription/cancel/` | deferred (out of this round) |
| saas | POST | `/api/saas/subscription/checkout/` | deferred (out of this round) |
| saas | GET | `/api/saas/tenant/` | deferred (out of this round) |
| saas | GET | `/api/saas/tenants/` | deferred (out of this round) |
| saas | POST | `/api/saas/tenants/` | deferred (out of this round) |
| saas | GET | `/api/saas/tenants/members/` | deferred (out of this round) |
| saas | POST | `/api/saas/tenants/members/` | deferred (out of this round) |
| saas | POST | `/api/saas/tenants/switch/` | deferred (out of this round) |
| scheduled-reports | GET | `/api/scheduled-reports/` | not connected |
| scheduled-reports | POST | `/api/scheduled-reports/` | not connected |
| scheduled-reports | GET | `/api/scheduled-reports/{id}/` | not connected |
| scheduled-reports | PUT | `/api/scheduled-reports/{id}/` | not connected |
| scheduled-reports | DELETE | `/api/scheduled-reports/{id}/` | not connected |
| security | GET | `/api/security/login-attempts/` | deferred (out of this round) |
| security | POST | `/api/security/login-attempts/` | deferred (out of this round) |
| security | POST | `/api/security/password-policy-check/` | deferred (out of this round) |
| security | GET | `/api/security/trusted-devices/` | deferred (out of this round) |
| security | POST | `/api/security/trusted-devices/` | deferred (out of this round) |
| security | DELETE | `/api/security/trusted-devices/{id}/` | deferred (out of this round) |
| security | POST | `/api/security/trusted-devices/{id}/authorize/` | deferred (out of this round) |
| security | POST | `/api/security/trusted-devices/{id}/revoke/` | deferred (out of this round) |
| settings | GET | `/api/settings/` | not connected |
| settings | PUT | `/api/settings/` | not connected |
| settings | GET | `/api/settings/about/` | not connected |
| settings | PUT | `/api/settings/about/` | not connected |
| settings | PATCH | `/api/settings/about/` | not connected |
| settings | POST | `/api/settings/about/check-updates/` | not connected |
| settings | GET | `/api/settings/all/` | not connected |
| settings | GET | `/api/settings/appearance/` | not connected |
| settings | PUT | `/api/settings/appearance/` | not connected |
| settings | PATCH | `/api/settings/appearance/` | not connected |
| settings | GET | `/api/settings/backup/` | not connected |
| settings | PUT | `/api/settings/backup/` | not connected |
| settings | PATCH | `/api/settings/backup/` | not connected |
| settings | GET | `/api/settings/barcode/` | not connected |
| settings | PUT | `/api/settings/barcode/` | not connected |
| settings | PATCH | `/api/settings/barcode/` | not connected |
| settings | GET | `/api/settings/company/` | connected |
| settings | PUT | `/api/settings/company/` | connected |
| settings | PATCH | `/api/settings/company/` | connected |
| settings | GET | `/api/settings/customer/` | not connected |
| settings | PUT | `/api/settings/customer/` | not connected |
| settings | PATCH | `/api/settings/customer/` | not connected |
| settings | GET | `/api/settings/data-management/` | not connected |
| settings | PUT | `/api/settings/data-management/` | not connected |
| settings | PATCH | `/api/settings/data-management/` | not connected |
| settings | GET | `/api/settings/feature-flags/` | not connected |
| settings | PUT | `/api/settings/feature-flags/` | not connected |
| settings | PATCH | `/api/settings/feature-flags/` | not connected |
| settings | GET | `/api/settings/inventory/` | not connected |
| settings | PUT | `/api/settings/inventory/` | not connected |
| settings | PATCH | `/api/settings/inventory/` | not connected |
| settings | GET | `/api/settings/notifications/` | not connected |
| settings | PUT | `/api/settings/notifications/` | not connected |
| settings | PATCH | `/api/settings/notifications/` | not connected |
| settings | GET | `/api/settings/pos/` | not connected |
| settings | PUT | `/api/settings/pos/` | not connected |
| settings | PATCH | `/api/settings/pos/` | not connected |
| settings | GET | `/api/settings/product/` | not connected |
| settings | PUT | `/api/settings/product/` | not connected |
| settings | PATCH | `/api/settings/product/` | not connected |
| settings | GET | `/api/settings/receipt/` | not connected |
| settings | PUT | `/api/settings/receipt/` | not connected |
| settings | PATCH | `/api/settings/receipt/` | not connected |
| settings | GET | `/api/settings/receipt/templates/` | not connected |
| settings | POST | `/api/settings/receipt/templates/` | not connected |
| settings | GET | `/api/settings/receipt/templates/{id}/` | not connected |
| settings | PUT | `/api/settings/receipt/templates/{id}/` | not connected |
| settings | DELETE | `/api/settings/receipt/templates/{id}/` | not connected |
| settings | GET | `/api/settings/reports/` | not connected |
| settings | PUT | `/api/settings/reports/` | not connected |
| settings | PATCH | `/api/settings/reports/` | not connected |
| settings | GET | `/api/settings/security/` | not connected |
| settings | PUT | `/api/settings/security/` | not connected |
| settings | PATCH | `/api/settings/security/` | not connected |
| settings | GET | `/api/settings/tax/` | not connected |
| settings | PUT | `/api/settings/tax/` | not connected |
| settings | PATCH | `/api/settings/tax/` | not connected |
| sms-templates | GET | `/api/sms-templates/` | not connected |
| sms-templates | POST | `/api/sms-templates/` | not connected |
| sms-templates | GET | `/api/sms-templates/{id}/` | not connected |
| sms-templates | PUT | `/api/sms-templates/{id}/` | not connected |
| sms-templates | DELETE | `/api/sms-templates/{id}/` | not connected |
| stores | GET | `/api/stores/` | connected (round 2) |
| stores | POST | `/api/stores/` | not connected |
| stores | GET | `/api/stores/{id}/` | not connected |
| stores | PUT | `/api/stores/{id}/` | not connected |
| stores | DELETE | `/api/stores/{id}/` | not connected |
| supplier-contacts | GET | `/api/supplier-contacts/{id}/` | not connected |
| supplier-contacts | PUT | `/api/supplier-contacts/{id}/` | not connected |
| supplier-contacts | PATCH | `/api/supplier-contacts/{id}/` | connected (round 2) |
| supplier-contacts | DELETE | `/api/supplier-contacts/{id}/` | connected (round 2) |
| suppliers | GET | `/api/suppliers/` | connected (round 2) |
| suppliers | POST | `/api/suppliers/` | connected (round 2) |
| suppliers | GET | `/api/suppliers/{id}/` | connected (round 2) |
| suppliers | PUT | `/api/suppliers/{id}/` | not connected |
| suppliers | PATCH | `/api/suppliers/{id}/` | connected (round 2) |
| suppliers | POST | `/api/suppliers/{id}/archive/` | connected (round 2) |
| suppliers | POST | `/api/suppliers/{id}/portal-token/` | connected (round 2) |
| suppliers | GET | `/api/suppliers/{id}/summary/` | connected (round 2) |
| suppliers | GET | `/api/suppliers/{supplier_id}/contacts/` | connected (round 2) |
| suppliers | POST | `/api/suppliers/{supplier_id}/contacts/` | connected (round 2) |
| system-health | GET | `/api/system-health/` | server-only (excluded from UI) |
| tax | GET | `/api/tax/breakdowns/` | not connected |
| tax | GET | `/api/tax/exemptions/` | not connected |
| tax | POST | `/api/tax/exemptions/` | not connected |
| tax | GET | `/api/tax/exemptions/{id}/` | not connected |
| tax | PUT | `/api/tax/exemptions/{id}/` | not connected |
| tax | PATCH | `/api/tax/exemptions/{id}/` | not connected |
| tax | DELETE | `/api/tax/exemptions/{id}/` | not connected |
| tax | POST | `/api/tax/orders/{order_id}/compute/` | not connected |
| tax | POST | `/api/tax/preview-line/` | not connected |
| tax | GET | `/api/tax/products/{product_id}/assignments/` | not connected |
| tax | POST | `/api/tax/products/{product_id}/assignments/` | not connected |
| tax | GET | `/api/tax/products/{product_id}/assignments/{id}/` | not connected |
| tax | PUT | `/api/tax/products/{product_id}/assignments/{id}/` | not connected |
| tax | PATCH | `/api/tax/products/{product_id}/assignments/{id}/` | not connected |
| tax | DELETE | `/api/tax/products/{product_id}/assignments/{id}/` | not connected |
| tax | GET | `/api/tax/rates/` | not connected |
| tax | POST | `/api/tax/rates/` | not connected |
| tax | GET | `/api/tax/rates/{id}/` | not connected |
| tax | PUT | `/api/tax/rates/{id}/` | not connected |
| tax | PATCH | `/api/tax/rates/{id}/` | not connected |
| tax | DELETE | `/api/tax/rates/{id}/` | not connected |
| tax | GET | `/api/tax/report/` | not connected |
| taxes | GET | `/api/taxes/` | connected |
| taxes | POST | `/api/taxes/` | connected |
| taxes | GET | `/api/taxes/{id}/` | connected |
| taxes | PUT | `/api/taxes/{id}/` | connected |
| taxes | DELETE | `/api/taxes/{id}/` | connected |
| transfers | GET | `/api/transfers/putaway-rules/` | not connected |
| transfers | POST | `/api/transfers/putaway-rules/` | not connected |
| transfers | GET | `/api/transfers/putaway-tasks/` | not connected |
| transfers | POST | `/api/transfers/putaway-tasks/{id}/complete/` | not connected |
| transfers | POST | `/api/transfers/putaway/suggest/` | not connected |
| transfers | GET | `/api/transfers/replenishment/` | connected (round 2) |
| transfers | GET | `/api/transfers/transfers/` | connected (round 2) |
| transfers | POST | `/api/transfers/transfers/` | connected (round 2) |
| transfers | GET | `/api/transfers/transfers/{id}/` | connected (round 2) |
| transfers | POST | `/api/transfers/transfers/{id}/receive/` | connected (round 2) |
| transfers | POST | `/api/transfers/warehouses/{id}/replenishment/generate/` | connected (round 2) |
| users | GET | `/api/users/` | connected |
| users | POST | `/api/users/` | connected |
| users | GET | `/api/users/{id}/` | connected |
| users | PUT | `/api/users/{id}/` | connected |
| users | DELETE | `/api/users/{id}/` | connected |
| webhooks | GET | `/api/webhooks/` | server-to-server (proposed) |
| webhooks | POST | `/api/webhooks/` | server-to-server (proposed) |
| webhooks | GET | `/api/webhooks/{id}/` | server-to-server (proposed) |
| webhooks | PUT | `/api/webhooks/{id}/` | server-to-server (proposed) |
| webhooks | DELETE | `/api/webhooks/{id}/` | server-to-server (proposed) |
| webhooks | GET | `/api/webhooks/{id}/deliveries/` | server-to-server (proposed) |
| webhooks | POST | `/api/webhooks/{id}/test/` | server-to-server (proposed) |
| workflow | GET | `/api/workflow/requests/` | not connected |
| workflow | POST | `/api/workflow/requests/` | not connected |
| workflow | GET | `/api/workflow/requests/{id}/` | not connected |
| workflow | POST | `/api/workflow/requests/{id}/approve/` | not connected |
| workflow | POST | `/api/workflow/requests/{id}/reject/` | not connected |
| workflow | GET | `/api/workflow/requests/pending_count/` | not connected |
| workflow | GET | `/api/workflow/rules/` | not connected |
| workflow | POST | `/api/workflow/rules/` | not connected |
| workflow | GET | `/api/workflow/rules/{id}/` | not connected |
| workflow | PUT | `/api/workflow/rules/{id}/` | not connected |
| workflow | PATCH | `/api/workflow/rules/{id}/` | not connected |
| workflow | DELETE | `/api/workflow/rules/{id}/` | not connected |
