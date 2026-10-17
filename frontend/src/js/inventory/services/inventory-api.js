/**
 * Inventory, catalog and reporting API client.
 *
 * Every function targets a route that exists in the backend (see
 * frontend/docs/API_ALIGNMENT_PLAN.md). Where the page expects a richer shape
 * than the endpoint returns, the adapter in this file performs the mapping and
 * the mapping is documented next to the function.
 */
import { apiJson, apiFetch, apiList, apiDownload, apiError, buildQuery } from "../../../services/api.js";

const PAGE_SIZE = 20;

// ─── Internal helpers ─────────────────────────────────────────────────────────

/** Throw an Error that carries the backend's message and status. */
async function failIfNotOk(response) {
    if (response.ok) return;
    let data = {};
    try { data = await response.json(); } catch { /* not JSON */ }
    throw apiError(response.status, data);
}

/** Multipart write (product images). Lets the browser set the boundary header. */
async function sendForm(path, method, formData) {
    const response = await apiFetch(path, { method, body: formData });
    await failIfNotOk(response);
    if (response.status === 204) return null;
    return response.json();
}

/** Client-side paging for endpoints that return a bare array. */
function paginateArray(rows, { page = 1, page_size = PAGE_SIZE, search = "" } = {}) {
    const needle = String(search || "").trim().toLowerCase();
    const filtered = needle
        ? rows.filter((row) => JSON.stringify(row).toLowerCase().includes(needle))
        : rows;
    const size = Number(page_size) || PAGE_SIZE;
    const pageNo = Math.max(1, Number(page) || 1);
    const start = (pageNo - 1) * size;
    const totalPages = Math.max(1, Math.ceil(filtered.length / size));
    return {
        count: filtered.length,
        page: pageNo,
        total_pages: totalPages,
        has_next: pageNo < totalPages,
        has_previous: pageNo > 1,
        next: pageNo < totalPages ? "next" : null,
        previous: pageNo > 1 ? "prev" : null,
        results: filtered.slice(start, start + size),
    };
}

// ═══════════════════════════════════════════════════════════════════════════════
// INVENTORY OVERVIEW AND MOVEMENTS
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Stat cards for the inventory dashboard.
 * Backend: /api/inventory/overview/ (stock totals) + /api/dashboard/summary/ (product counts).
 * `overstock_products` has no backend endpoint, so it is returned as null and rendered as "—".
 */
export async function getDashboard() {
    const [overview, summary] = await Promise.all([
        apiJson("/api/inventory/overview/"),
        apiJson("/api/dashboard/summary/"),
    ]);
    return {
        total_products: summary.total_products ?? 0,
        low_stock_products: summary.low_stock_count ?? overview.low_stock_count ?? 0,
        out_of_stock_products: summary.out_of_stock_count ?? overview.out_of_stock_count ?? 0,
        overstock_products: null,
        top_category: null,
        total_units: overview.total_units,
        total_stock_value: overview.total_stock_value,
        warehouse_count: overview.warehouse_count,
        recent_movements: overview.recent_movements || [],
        reorder_alerts: overview.reorder_alerts || [],
    };
}

/** Product list for the inventory table. Tab ids map to the product `stock` filter. */
export function getInventory(query = "") {
    const params = new URLSearchParams(query.replace(/^\?/, ""));
    const tab = params.get("status");
    const stock = tab === "low" || tab === "out" ? tab : "";
    // "inactive" maps to the product status filter; "all" applies no filter.
    const status = tab === "inactive" ? "inactive" : "";
    return apiList(`/api/products/${buildQuery({
        page: params.get("page") || 1,
        search: params.get("search") || "",
        stock,
        status,
    })}`);
}

export function getSummary() {
    return getDashboard();
}

/** Products at or below their minimum stock level. */
export async function getLowStock() {
    return normalizeArrayish(await apiJson("/api/dashboard/low-stock/"));
}

function normalizeArrayish(data) {
    return Array.isArray(data) ? { count: data.length, results: data } : data;
}

export function getProduct(id) {
    return apiJson(`/api/products/${id}/`);
}

/**
 * Stock adjustments. The backend lists one row per adjustment with nested items
 * (previous_stock / new_stock). The page expects quantity_before / quantity_after
 * and a net change, so each row is mapped here.
 */
/** Local calendar date (YYYY-MM-DD) n days before today. */
function localDate(daysAgo = 0) {
    const date = new Date();
    date.setDate(date.getDate() - daysAgo);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** Toolbar period (today/yesterday/week/month) → inclusive date range. */
export function adjustmentDateRange(period) {
    const now = new Date();
    switch (period) {
        case "today": return { date_from: localDate(0), date_to: localDate(0) };
        case "yesterday": return { date_from: localDate(1), date_to: localDate(1) };
        case "week": return { date_from: localDate((now.getDay() + 6) % 7), date_to: localDate(0) }; // since Monday
        case "month": return { date_from: localDate(now.getDate() - 1), date_to: localDate(0) };
        default: return {};
    }
}

export async function getAdjustments(filters = {}) {
    const query = buildQuery({
        page: filters.page || 1,
        page_size: filters.page_size || PAGE_SIZE,
        search: filters.search,
        reason: filters.reason,
        ...adjustmentDateRange(filters.date),
    });
    const response = await apiList(`/api/inventory/adjustments/${query}`);
    return { ...response, results: response.results.map(mapAdjustment) };
}

function mapAdjustment(row) {
    const items = (row.items || []).map((item) => {
        const before = Number(item.previous_stock) || 0;
        const after = Number(item.new_stock) || 0;
        return {
            ...item,
            reason: row.reason,
            quantity_before: before,
            quantity_after: after,
            change: after - before,
        };
    });
    const netChange = items.reduce((sum, item) => sum + item.change, 0);
    return { ...row, items, items_count: items.length, net_change: netChange };
}

/** One CSV row per adjusted item; an adjustment without items still gets a row. */
export function adjustmentCsvRows(adjustments) {
    return adjustments.flatMap((adjustment) => {
        const items = adjustment.items?.length ? adjustment.items : [null];
        return items.map((item) => ({ adjustment, item }));
    });
}

/**
 * The backend has no adjustment detail route. The adjustment is located in the
 * list (most recent first), which covers the detail view for normal volumes.
 */
export async function getAdjustment(number) {
    const response = await getAdjustments({ page: 1, page_size: 100 });
    const found = response.results.find((row) => row.adjustment_number === number);
    if (!found) throw new Error("Adjustment not found in the most recent 100 records.");
    return found;
}

/**
 * Create a stock adjustment.
 * payload: { product, warehouse?, new_quantity | adjustment_quantity, reason, note? }
 */
export async function createAdjustment(payload) {
    return apiJson("/api/inventory/adjustments/", { method: "POST", body: JSON.stringify(payload) });
}

/** Inventory valuation report (per product). */
export function getValuation(filters = {}) {
    return apiList(`/api/reports/inventory-valuation/${buildQuery(filters)}`);
}

/** Stock report (summary totals plus product rows). */
export function getReports(filters = {}) {
    return apiJson(`/api/reports/stock/${buildQuery(filters)}`);
}

/** ABC classification of products by annual value. */
export function getAnalytics(filters = {}) {
    return apiList(`/api/inventory/abc/${buildQuery(filters)}`);
}

/** Stock ageing buckets, used as the slow-moving view. */
export function getSlowMoving(filters = {}) {
    return apiList(`/api/inventory/aging/${buildQuery(filters)}`);
}

/** Top products by returns (derived from the product report). */
export function getMostReturned(filters = {}) {
    return apiList(`/api/reports/top-products/${buildQuery(filters)}`);
}

/** Stock movement history. movement_type is exposed as `movement` for the page. */
export async function getMovements(filters = {}) {
    const response = await apiList(`/api/inventory/movements/${buildQuery({
        page: filters.page || 1,
        page_size: filters.page_size || PAGE_SIZE,
        product_id: filters.product_id,
        warehouse_id: filters.warehouse_id,
        movement_type: filters.movement_type || filters.movement,
    })}`);
    return { ...response, results: response.results.map(mapMovement) };
}

function mapMovement(row) {
    return { ...row, movement: row.movement_type };
}

/**
 * The backend has no movement detail route. The movement is taken from the
 * most recent 500 records.
 */
export async function getMovement(id) {
    const response = await getMovements({ page: 1, page_size: 500 });
    const found = response.results.find((row) => String(row.id) === String(id));
    if (!found) throw new Error("Movement not found in the most recent 500 records.");
    return found;
}

/**
 * Summary totals for movements, computed from the most recent 500 records
 * (the backend has no movement summary endpoint).
 */
export async function getMovementSummary() {
    const response = await getMovements({ page: 1, page_size: 500 });
    let added = 0;
    let removed = 0;
    response.results.forEach((row) => {
        const qty = Number(row.quantity) || 0;
        if (qty >= 0) added += qty; else removed += Math.abs(qty);
    });
    return {
        total_movements: response.count,
        stock_added: added,
        stock_removed: removed,
        net_change: added - removed,
        sample_size: response.results.length,
    };
}

// ═══════════════════════════════════════════════════════════════════════════════
// PRODUCTS  (canonical: /api/products/)
// ═══════════════════════════════════════════════════════════════════════════════

export function getProducts(filters = {}) {
    return apiList(`/api/products/${buildQuery({
        page: filters.page,
        page_size: filters.page_size,
        search: filters.search,
        category: filters.category,
        brand: filters.brand,
        status: filters.status,
        stock: filters.stock,
        ordering: filters.ordering,
    })}`);
}

/** Create a product. formData is multipart so the product image can be uploaded. */
export function createProduct(formData) {
    return sendForm("/api/products/", "POST", formData);
}

/** Partially update a product (multipart). */
export function updateProduct(id, formData) {
    return sendForm(`/api/products/${id}/`, "PATCH", formData);
}

/** Same as updateProduct; kept because AllProducts imports this name. */
export const updateProduct2 = updateProduct;

/** Products are archived rather than deleted so historical sales stay intact. */
export async function deleteProduct(id) {
    return apiJson(`/api/products/${id}/archive/`, { method: "POST" });
}

/** Full product CSV export. */
export function exportProducts() {
    return apiDownload("/api/catalog/products/export/csv/", "products.csv");
}

// ═══════════════════════════════════════════════════════════════════════════════
// CATEGORIES  (canonical: /api/categories/ returns a bare array)
// ═══════════════════════════════════════════════════════════════════════════════

export async function getCategories(filters = {}) {
    const rows = await apiJson("/api/categories/");
    return paginateArray(Array.isArray(rows) ? rows : rows.results || [], filters);
}

export function createCategory(data) {
    return apiJson("/api/categories/", { method: "POST", body: JSON.stringify(data) });
}

export function updateCategory(id, data) {
    return apiJson(`/api/categories/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}

/** Categories are archived (the backend has no hard-delete action). */
export function deleteCategory(id) {
    return apiJson(`/api/categories/${id}/archive/`, { method: "POST" });
}

// ═══════════════════════════════════════════════════════════════════════════════
// BRANDS  (canonical: /api/catalog/brands/)
// ═══════════════════════════════════════════════════════════════════════════════

export function getBrands(filters = {}) {
    return apiList(`/api/catalog/brands/${buildQuery({ page: filters.page, page_size: filters.page_size, search: filters.search })}`);
}

export function createBrand(data) {
    return apiJson("/api/catalog/brands/", { method: "POST", body: JSON.stringify(data) });
}

export function updateBrand(id, data) {
    return apiJson(`/api/catalog/brands/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}

export function deleteBrand(id) {
    return apiJson(`/api/catalog/brands/${id}/`, { method: "DELETE" });
}

// ═══════════════════════════════════════════════════════════════════════════════
// VARIANTS  (canonical: attribute definitions at /api/catalog/attributes/)
// A definition is { id, name, values: [{ id, value }] }. Values are stored as a
// full list, so adding or removing one value is a read-modify-write.
// ═══════════════════════════════════════════════════════════════════════════════

export function getVariants(filters = {}) {
    return apiList(`/api/catalog/attributes/${buildQuery({ page: filters.page, page_size: filters.page_size, search: filters.search })}`);
}

export function createVariant(data) {
    return apiJson("/api/catalog/attributes/", { method: "POST", body: JSON.stringify(data) });
}

export function updateVariant(id, data) {
    return apiJson(`/api/catalog/attributes/${id}/`, { method: "PUT", body: JSON.stringify(data) });
}

export function deleteVariant(id) {
    return apiJson(`/api/catalog/attributes/${id}/`, { method: "DELETE" });
}

export async function addVariantValue(variantId, { value }) {
    const current = await apiJson(`/api/catalog/attributes/${variantId}/`);
    const values = [...(current.values || []).map((v) => ({ value: v.value })), { value }];
    return updateVariant(variantId, { name: current.name, values });
}

export async function deleteVariantValue(variantId, valueId) {
    const current = await apiJson(`/api/catalog/attributes/${variantId}/`);
    const values = (current.values || [])
        .filter((v) => String(v.id) !== String(valueId))
        .map((v) => ({ value: v.value }));
    return updateVariant(variantId, { name: current.name, values });
}

// ═══════════════════════════════════════════════════════════════════════════════
// REPORTS  (canonical: /api/reports/<name>/ and /export/<csv|excel|pdf>/)
// ═══════════════════════════════════════════════════════════════════════════════

export function getSalesReport(filters = {}) {
    return apiJson(`/api/reports/sales/${buildQuery(filters)}`);
}

export function exportSalesReport(format, filters = {}) {
    return apiDownload(`/api/reports/sales/export/${format}/${buildQuery(filters)}`, `sales-report.${extensionFor(format)}`);
}

export function getProductReport(filters = {}) {
    return apiJson(`/api/reports/products/${buildQuery(filters)}`);
}

export function exportProductReport(format, filters = {}) {
    return apiDownload(`/api/reports/products/export/${format}/${buildQuery(filters)}`, `products-report.${extensionFor(format)}`);
}

export function getStockReport(filters = {}) {
    return apiJson(`/api/reports/stock/${buildQuery(filters)}`);
}

export function exportStockReport(format, filters = {}) {
    return apiDownload(`/api/reports/stock/export/${format}/${buildQuery(filters)}`, `stock-report.${extensionFor(format)}`);
}

export function getTaxReport(filters = {}) {
    return apiJson(`/api/reports/tax/${buildQuery(filters)}`);
}

export function exportTaxReport(format, filters = {}) {
    return apiDownload(`/api/reports/tax/export/${format}/${buildQuery(filters)}`, `tax-report.${extensionFor(format)}`);
}

function extensionFor(format) {
    return format === "excel" ? "xlsx" : format;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONFIGURATION  (users, roles, taxes, payment methods)
// ═══════════════════════════════════════════════════════════════════════════════

export function getUsers(filters = {}) {
    return apiList(`/api/users/${buildQuery({ page: filters.page, page_size: filters.page_size, search: filters.search })}`);
}

export function createUser(data) {
    return apiJson("/api/users/", { method: "POST", body: JSON.stringify(data) });
}

export function updateUser(id, data) {
    return apiJson(`/api/users/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}

export function deleteUser2(id) {
    return apiJson(`/api/users/${id}/`, { method: "DELETE" });
}

/**
 * Tenant-safe role governance. The active tenant is derived by the backend
 * from the authenticated principal; clients must not submit tenant IDs.
 */
export async function getRoles(filters = {}) {
    const response = await apiList("/api/rbac/governance/roles/");
    const needle = String(filters.search || "").trim().toLowerCase();
    const filtered = needle
        ? response.results.filter((role) =>
            [role.label, role.key, role.description]
                .some((value) => String(value || "").toLowerCase().includes(needle)))
        : response.results;
    const pageSize = Math.max(1, Number(filters.page_size) || 10);
    const page = Math.max(1, Number(filters.page) || 1);
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    return {
        ...response,
        count: filtered.length,
        active_count: filtered.filter((role) => role.is_active).length,
        page,
        total_pages: totalPages,
        has_next: page < totalPages,
        has_previous: page > 1,
        next: page < totalPages ? "next" : null,
        previous: page > 1 ? "prev" : null,
        results: filtered.slice((page - 1) * pageSize, page * pageSize)
    };
}

export function getGovernancePermissions() {
    return apiList("/api/rbac/governance/permissions/");
}

export function createRole(data) {
    return apiJson("/api/rbac/governance/roles/", { method: "POST", body: JSON.stringify(data) });
}

export function updateRole(id, data) {
    return apiJson(`/api/rbac/governance/roles/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}

export function deleteRole(id) {
    return apiJson(`/api/rbac/governance/roles/${id}/`, { method: "DELETE" });
}

export function getTaxes(filters = {}) {
    return apiList(`/api/taxes/${buildQuery({ page: filters.page, page_size: filters.page_size, search: filters.search })}`);
}

export function createTax(data) {
    return apiJson("/api/taxes/", { method: "POST", body: JSON.stringify(data) });
}

export function updateTax(id, data) {
    return apiJson(`/api/taxes/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}

export function deleteTax(id) {
    return apiJson(`/api/taxes/${id}/`, { method: "DELETE" });
}

export function getPaymentMethods(filters = {}) {
    return apiList(`/api/payment-methods/${buildQuery({ page: filters.page, page_size: filters.page_size, search: filters.search })}`);
}

export function createPaymentMethod(data) {
    return apiJson("/api/payment-methods/", { method: "POST", body: JSON.stringify(data) });
}

export function updatePaymentMethod(id, data) {
    return apiJson(`/api/payment-methods/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}

export function deletePaymentMethod(id) {
    return apiJson(`/api/payment-methods/${id}/`, { method: "DELETE" });
}

/** Company profile and receipt settings (canonical: /api/settings/company/). */
export function getSettings() {
    return apiJson("/api/settings/company/");
}

export async function updateSettings(formData) {
    return sendForm("/api/settings/company/", "PATCH", formData);
}


