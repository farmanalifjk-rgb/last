/**
 * Stock control: stock levels, movements, reorder rules and alerts, bin
 * locations, cycle counts (create, run, delete), stock reservations (create,
 * release, availability check) and stock aging.
 *
 * Route: #/stock-control?tab=stock|movements|reorder|bins|cycle-counts|reservations|aging
 *        #/stock-control?tab=cycle-counts&count=ID
 *
 * Endpoints used:
 *   /api/inventory/stock/                                  GET
 *   /api/inventory/movements/                              GET
 *   /api/inventory/reorder-rules/                          GET, POST
 *   /api/inventory/reorder-rules/{id}/                     GET, PATCH, DELETE
 *   /api/inventory/reorder-alerts/                         GET
 *   /api/inventory/bins/                                   GET, POST
 *   /api/inventory/bins/{id}/                              GET, PATCH, DELETE
 *   /api/inventory/cycle-counts/                           GET, POST
 *   /api/inventory/cycle-counts/{id}/                      GET, DELETE
 *   /api/inventory/cycle-counts/{id}/run/                  POST
 *   /api/inventory/reservations/                           GET, POST
 *   /api/inventory/reservations/{id}/release/              POST
 *   /api/inventory/available/                              GET
 *   /api/inventory/aging/                                  GET
 *   /api/inventory/warehouses/                             GET (pickers)
 *   /api/products/                                         GET (pickers)
 *   /api/suppliers/                                        GET (pickers)
 */
import { createIcons, icons } from "lucide";
import { apiJson, apiList, buildQuery } from "../../services/api.js";
import {
    esc, formatDateTime, formatDate, toast, errorMessage, openModal, confirmDialog,
    field, fieldGrid, readForm, toNumber, dateOrNull, table, pager, tabs, statusBadge,
    pageHeader, primaryButton, actionButton, runAction, emptyStateCard,
    hashParam, setHashParam, selectInput, secondaryButton,
} from "../../shared/ui.js";

const PAGE_SIZE = 10;
const TABS = [
    { id: "stock", label: "Stock levels" },
    { id: "movements", label: "Movements" },
    { id: "reorder", label: "Reorder rules" },
    { id: "bins", label: "Bin locations" },
    { id: "cycle-counts", label: "Cycle counts" },
    { id: "reservations", label: "Reservations" },
    { id: "aging", label: "Aging" },
];
// Tabs whose backend list accepts a warehouse_id filter.
const WAREHOUSE_FILTER_TABS = new Set(["stock", "movements", "bins", "reservations"]);
const AGING_BUCKETS = ["0-30", "31-60", "61-90", "90+"];

const state = {
    tab: "stock",
    page: 1,
    warehouseId: "",
    bucket: "",
    warehouses: [],
    products: [],
    suppliers: [],
};

const root = () => document.getElementById("stock-control-root");

window.initializeStockControl = async function () {
    const container = root();
    if (!container) return;
    container.addEventListener("click", onClick);
    container.addEventListener("submit", (event) => event.preventDefault());
    container.addEventListener("change", onChange);
    const requested = hashParam("tab");
    state.tab = TABS.some((t) => t.id === requested) ? requested : "stock";
    state.page = 1;
    state.warehouseId = "";
    state.bucket = "";
    await loadReferenceData();
    if (state.tab === "cycle-counts" && hashParam("count")) return renderCycleCount(hashParam("count"));
    return renderTab();
};

async function loadReferenceData() {
    const [warehouses, products, suppliers] = await Promise.all([
        apiList("/api/inventory/warehouses/?page_size=200").catch(() => ({ results: [] })),
        apiList("/api/products/?page_size=200").catch(() => ({ results: [] })),
        apiList("/api/suppliers/?page_size=200").catch(() => ({ results: [] })),
    ]);
    state.warehouses = warehouses.results;
    state.products = products.results;
    state.suppliers = suppliers.results;
}

/* ── Events ───────────────────────────────────────────────────────────────── */

function onClick(event) {
    const actionEl = event.target.closest("[data-action]");
    if (actionEl && !actionEl.disabled) return handleAction(actionEl.dataset.action, actionEl);
    const pageEl = event.target.closest("[data-page]");
    if (pageEl && !pageEl.disabled) {
        state.page = Number(pageEl.dataset.page);
        return renderTab();
    }
    const tabEl = event.target.closest("[data-tab]");
    if (tabEl) return setHashParam("#/stock-control", { tab: tabEl.dataset.tab });
    const openEl = event.target.closest("[data-open-count]");
    if (openEl) return setHashParam("#/stock-control", { tab: "cycle-counts", count: openEl.dataset.openCount });
}

function onChange(event) {
    if (event.target.id === "stock-warehouse") {
        state.warehouseId = event.target.value;
        state.page = 1;
        return renderTab();
    }
    if (event.target.id === "stock-bucket") {
        state.bucket = event.target.value;
        state.page = 1;
        return renderTab();
    }
}

async function handleAction(action, el) {
    const id = el.dataset.id;
    switch (action) {
        case "new-rule": return ruleForm(null);
        case "edit-rule": return ruleForm(id);
        case "delete-rule": return deleteRecord(`/api/inventory/reorder-rules/${id}/`, "Delete this reorder rule?", "Reorder rule deleted.");
        case "new-bin": return binForm(null);
        case "edit-bin": return binForm(id);
        case "delete-bin": return deleteRecord(`/api/inventory/bins/${id}/`, "Delete this bin location?", "Bin location deleted.");
        case "new-count": return countForm();
        case "run-count": return runCountForm(id);
        case "delete-count": return deleteRecord(`/api/inventory/cycle-counts/${id}/`, "Delete this cycle count?", "Cycle count deleted.", () => setHashParam("#/stock-control", { tab: "cycle-counts" }));
        case "new-reservation": return reservationForm();
        case "release-reservation": return releaseReservation(id);
        case "check-availability": return availabilityForm();
        case "back-to-counts": return setHashParam("#/stock-control", { tab: "cycle-counts" });
        default: return undefined;
    }
}

/* ── Shell ────────────────────────────────────────────────────────────────── */

const TAB_ACTIONS = {
    reorder: () => primaryButton("New reorder rule", "new-rule"),
    bins: () => primaryButton("New bin location", "new-bin"),
    "cycle-counts": () => primaryButton("New cycle count", "new-count"),
    reservations: () => `${secondaryButton("Check availability", "check-availability")} ${primaryButton("New reservation", "new-reservation")}`,
};

function frame(content) {
    const actions = TAB_ACTIONS[state.tab] ? TAB_ACTIONS[state.tab]() : "";
    root().innerHTML = `${pageHeader({ title: "Stock control", subtitle: "Stock levels, reorder rules, bin locations, cycle counts and reservations", actions })}
    <div class="mb-6">${tabs(TABS, state.tab)}</div>${content}`;
}

function warehouseSelect() {
    const options = [{ value: "", label: "All warehouses" }, ...state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }))];
    return selectInput("stock-warehouse", options, state.warehouseId);
}

function bucketSelect() {
    const options = [{ value: "", label: "All buckets (days since last stock-in)" }, ...AGING_BUCKETS.map((b) => ({ value: b, label: `${b} days` }))];
    return selectInput("stock-bucket", options, state.bucket);
}

async function renderTab() {
    const container = root();
    if (!container) return;
    if (!document.getElementById("stock-body") || container.dataset.tab !== state.tab) {
        let filters = "";
        if (WAREHOUSE_FILTER_TABS.has(state.tab)) filters = warehouseSelect();
        if (state.tab === "aging") filters = bucketSelect();
        frame(`<div class="mb-5 flex flex-wrap items-center gap-3">${filters}</div><div id="stock-body"></div>`);
        container.dataset.tab = state.tab;
    }
    const body = document.getElementById("stock-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        if (state.tab === "stock") await renderStock(body);
        else if (state.tab === "movements") await renderMovements(body);
        else if (state.tab === "reorder") await renderReorder(body);
        else if (state.tab === "bins") await renderBins(body);
        else if (state.tab === "cycle-counts") await renderCycleCounts(body);
        else if (state.tab === "reservations") await renderReservations(body);
        else await renderAging(body);
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this list", errorMessage(error));
    }
    createIcons({ icons });
}

const paged = (data) => pager({ page: data.page, totalPages: data.total_pages, count: data.count });
const warehouseName = (id) => state.warehouses.find((w) => String(w.id) === String(id))?.name || "-";
const productLabel = (p) => (p ? `${p.name}${p.sku ? ` (${p.sku})` : ""}` : "-");
const numberText = (value) => (value === null || value === undefined || value === "" ? "-" : String(value));

/* ── Stock levels and movements (read only) ───────────────────────────────── */

async function renderStock(body) {
    const query = buildQuery({ warehouse_id: state.warehouseId, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/inventory/stock/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Product", cell: (r) => `${esc(r.product_name || "-")} <span class="text-xs text-slate-400">${esc(r.product_sku || "")}</span>` },
            { label: "Warehouse", cell: (r) => esc(r.warehouse_name || "-") },
            { label: "On hand", align: "right", cell: (r) => esc(numberText(r.quantity)) },
            { label: "Available", align: "right", cell: (r) => esc(numberText(r.available_quantity)) },
            { label: "Reorder point", align: "right", cell: (r) => esc(numberText(r.reorder_point)) },
            { label: "Bin", cell: (r) => esc(numberText(r.bin_location)) },
        ],
        rows: data.results,
        empty: "No stock records found.",
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function renderMovements(body) {
    const query = buildQuery({ warehouse_id: state.warehouseId, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/inventory/movements/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "When", cell: (m) => esc(formatDateTime(m.created_at)) },
            { label: "Product", cell: (m) => esc(m.product_name || "-") },
            { label: "Warehouse", cell: (m) => esc(m.warehouse_name || "-") },
            { label: "Type", cell: (m) => esc(m.movement_type || "-") },
            { label: "Change", align: "right", cell: (m) => esc(numberText(m.quantity)) },
            { label: "Stock", align: "right", cell: (m) => esc(`${numberText(m.previous_stock)} → ${numberText(m.new_stock)}`) },
            { label: "Reference", cell: (m) => esc(m.reference || "-") },
            { label: "Note", cell: (m) => esc(m.note || "") },
        ],
        rows: data.results,
        empty: "No stock movements found.",
    })}<div class="mt-4">${paged(data)}</div>`;
}

/* ── Reorder rules and alerts ─────────────────────────────────────────────── */

async function renderReorder(body) {
    const [alerts, data] = await Promise.all([
        apiJson("/api/inventory/reorder-alerts/"),
        apiList(`/api/inventory/reorder-rules/${buildQuery({ page: state.page, page_size: PAGE_SIZE })}`),
    ]);
    const alertRows = Array.isArray(alerts) ? alerts : [];
    body.innerHTML = `
    <h2 class="mb-3 text-sm font-semibold text-slate-700">Below reorder point now (${alertRows.length})</h2>
    <div class="mb-8">${table({
        columns: [
            { label: "Product", cell: (a) => esc(`${a.product_name || "-"} ${a.sku ? `(${a.sku})` : ""}`) },
            { label: "Warehouse", cell: (a) => esc(warehouseName(a.warehouse_id)) },
            { label: "Available", align: "right", cell: (a) => esc(numberText(a.available)) },
            { label: "Reorder point", align: "right", cell: (a) => esc(numberText(a.reorder_point)) },
            { label: "Target", align: "right", cell: (a) => esc(numberText(a.target_stock)) },
            { label: "Suggested order", align: "right", cell: (a) => esc(numberText(a.suggested_quantity)) },
        ],
        rows: alertRows,
        empty: "Every product with a reorder rule is above its reorder point.",
    })}</div>
    <h2 class="mb-3 text-sm font-semibold text-slate-700">Rules</h2>
    ${table({
        columns: [
            { label: "Product", cell: (r) => esc(r.product_name || "-") },
            { label: "Warehouse", cell: (r) => esc(r.warehouse_name || "-") },
            { label: "Reorder point", align: "right", cell: (r) => esc(numberText(r.reorder_point)) },
            { label: "Target stock", align: "right", cell: (r) => esc(numberText(r.target_stock)) },
            { label: "Supplier", cell: (r) => esc(r.supplier_name || "-") },
            { label: "Auto PO", cell: (r) => (r.auto_generate_po ? "Yes" : "No") },
            { label: "Status", cell: (r) => statusBadge(r.is_active ? "active" : "inactive") },
        ],
        rows: data.results,
        empty: "No reorder rules yet.",
        actions: (r) => `${actionButton("Edit", "edit-rule", { data: { id: r.id } })} ${actionButton("Delete", "delete-rule", { tone: "danger", data: { id: r.id } })}`,
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function ruleForm(id) {
    let rule = {};
    if (id) {
        try { rule = await apiJson(`/api/inventory/reorder-rules/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    const productOptions = state.products.map((p) => ({ value: p.id, label: productLabel(p) }));
    const warehouseOptions = state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }));
    const supplierOptions = [{ value: "", label: "None" }, ...state.suppliers.map((s) => ({ value: s.id, label: s.name }))];
    if (!productOptions.length || !warehouseOptions.length) return toast("Add at least one product and one warehouse first.", "error");
    await openModal({
        title: id ? "Edit reorder rule" : "New reorder rule",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create rule",
        html: fieldGrid([
            field({ name: "product", label: "Product", type: "select", options: productOptions, value: rule.product ?? productOptions[0].value, required: true, full: true }),
            field({ name: "warehouse", label: "Warehouse", type: "select", options: warehouseOptions, value: rule.warehouse ?? warehouseOptions[0].value, required: true, full: true }),
            field({ name: "reorder_point", label: "Reorder point", type: "number", step: "any", min: 0, value: rule.reorder_point ?? 0, required: true }),
            field({ name: "target_stock", label: "Target stock", type: "number", step: "any", min: 0, value: rule.target_stock ?? 0, required: true }),
            field({ name: "supplier", label: "Preferred supplier", type: "select", options: supplierOptions, value: rule.supplier ?? "", full: true }),
            field({ name: "auto_generate_po", label: "Generate purchase orders automatically", type: "checkbox", value: rule.auto_generate_po ?? false, full: true }),
            field({ name: "is_active", label: "Active", type: "checkbox", value: rule.is_active ?? true, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const reorderPoint = toNumber(d.reorder_point, "Reorder point", { min: 0 });
            const targetStock = toNumber(d.target_stock, "Target stock", { min: 0 });
            if (targetStock < reorderPoint) throw new Error("Target stock must be at least the reorder point.");
            const payload = {
                product: toNumber(d.product, "Product", { min: 1 }),
                warehouse: toNumber(d.warehouse, "Warehouse", { min: 1 }),
                reorder_point: reorderPoint,
                target_stock: targetStock,
                supplier: d.supplier ? toNumber(d.supplier, "Supplier", { min: 1 }) : null,
                auto_generate_po: d.auto_generate_po,
                is_active: d.is_active,
            };
            await apiJson(id ? `/api/inventory/reorder-rules/${id}/` : "/api/inventory/reorder-rules/", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Reorder rule updated." : "Reorder rule created.", "success");
            await renderTab();
            return true;
        },
    });
}

/* ── Bin locations ────────────────────────────────────────────────────────── */

async function renderBins(body) {
    const query = buildQuery({ warehouse_id: state.warehouseId, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/inventory/bins/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Code", cell: (b) => `<span class="font-mono text-xs">${esc(b.code || "-")}</span>` },
            { label: "Warehouse", cell: (b) => esc(b.warehouse_name || warehouseName(b.warehouse)) },
            { label: "Zone", cell: (b) => esc(b.zone || "-") },
            { label: "Aisle", cell: (b) => esc(b.aisle || "-") },
            { label: "Rack", cell: (b) => esc(b.rack || "-") },
            { label: "Bin", cell: (b) => esc(b.bin || "-") },
            { label: "Status", cell: (b) => statusBadge(b.is_active ? "active" : "inactive") },
        ],
        rows: data.results,
        empty: "No bin locations yet.",
        actions: (b) => `${actionButton("Edit", "edit-bin", { data: { id: b.id } })} ${actionButton("Delete", "delete-bin", { tone: "danger", data: { id: b.id } })}`,
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function binForm(id) {
    let bin = {};
    if (id) {
        try { bin = await apiJson(`/api/inventory/bins/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    const warehouseOptions = state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }));
    if (!warehouseOptions.length) return toast("Add a warehouse before creating bin locations.", "error");
    await openModal({
        title: id ? "Edit bin location" : "New bin location",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create bin",
        html: fieldGrid([
            field({ name: "warehouse", label: "Warehouse", type: "select", options: warehouseOptions, value: bin.warehouse ?? warehouseOptions[0].value, required: true, full: true }),
            field({ name: "code", label: "Code", value: bin.code || "", help: "Unique label for the location, e.g. A-01-02." }),
            field({ name: "zone", label: "Zone", value: bin.zone || "" }),
            field({ name: "aisle", label: "Aisle", value: bin.aisle || "" }),
            field({ name: "rack", label: "Rack", value: bin.rack || "" }),
            field({ name: "bin", label: "Bin", value: bin.bin || "" }),
            field({ name: "is_active", label: "Active", type: "checkbox", value: bin.is_active ?? true, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = {
                warehouse: toNumber(d.warehouse, "Warehouse", { min: 1 }),
                code: d.code || "",
                zone: d.zone || "",
                aisle: d.aisle || "",
                rack: d.rack || "",
                bin: d.bin || "",
                is_active: d.is_active,
            };
            await apiJson(id ? `/api/inventory/bins/${id}/` : "/api/inventory/bins/", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Bin location updated." : "Bin location created.", "success");
            await renderTab();
            return true;
        },
    });
}

/* ── Cycle counts ─────────────────────────────────────────────────────────── */

async function renderCycleCounts(body) {
    const data = await apiList(`/api/inventory/cycle-counts/${buildQuery({ page: state.page, page_size: PAGE_SIZE })}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Reference", cell: (c) => `<button type="button" data-open-count="${esc(c.id)}" class="font-mono text-xs font-semibold text-violet-700 hover:underline">${esc(c.reference || `#${c.id}`)}</button>` },
            { label: "Warehouse", cell: (c) => esc(c.warehouse_name || "-") },
            { label: "Lines", align: "right", cell: (c) => esc(Array.isArray(c.lines) ? c.lines.length : "-") },
            { label: "Started", cell: (c) => esc(formatDateTime(c.created_at)) },
            { label: "Completed", cell: (c) => esc(formatDateTime(c.completed_at)) },
            { label: "Status", cell: (c) => statusBadge(c.status || "draft") },
        ],
        rows: data.results,
        empty: "No cycle counts yet.",
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function renderCycleCount(id) {
    frame(`<div id="stock-body"></div>`);
    const body = document.getElementById("stock-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        const count = await apiJson(`/api/inventory/cycle-counts/${id}/`);
        const open = count.status !== "reconciled";
        const actions = open
            ? `${secondaryButton("Back to counts", "back-to-counts")} ${primaryButton("Run count", "run-count")} <button type="button" data-action="delete-count" data-id="${esc(count.id)}" class="h-11 rounded-xl border border-rose-200 px-5 text-sm font-semibold text-rose-600 hover:bg-rose-50">Delete</button>`
            : secondaryButton("Back to counts", "back-to-counts");
        body.innerHTML = `
        <div class="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span>Warehouse: <strong>${esc(count.warehouse_name || "-")}</strong></span>
            <span>Started: ${esc(formatDateTime(count.created_at))}</span>
            <span>Completed: ${esc(formatDateTime(count.completed_at))}</span>
            ${statusBadge(count.status)}
        </div>
        <div class="mb-4 flex flex-wrap gap-3">${actions}</div>
        ${table({
            columns: [
                { label: "Product", cell: (l) => esc(l.product_name || "-") },
                { label: "Expected", align: "right", cell: (l) => esc(numberText(l.expected_quantity)) },
                { label: "Counted", align: "right", cell: (l) => esc(numberText(l.counted_quantity)) },
                { label: "Variance", align: "right", cell: (l) => esc(numberText(l.variance)) },
                { label: "Note", cell: (l) => esc(l.note || "") },
            ],
            rows: Array.isArray(count.lines) ? count.lines : [],
            empty: "No counted lines yet. Run the count to record quantities.",
        })}`;
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this cycle count", errorMessage(error));
    }
    createIcons({ icons });
}

async function countForm() {
    const warehouseOptions = state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }));
    if (!warehouseOptions.length) return toast("Add a warehouse before starting a cycle count.", "error");
    await openModal({
        title: "New cycle count",
        submitLabel: "Create count",
        html: fieldGrid([
            field({ name: "warehouse", label: "Warehouse", type: "select", options: warehouseOptions, value: warehouseOptions[0].value, required: true, full: true }),
            field({ name: "reference", label: "Reference", value: "", placeholder: "e.g. COUNT-2026-10", full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = {
                warehouse: toNumber(d.warehouse, "Warehouse", { min: 1 }),
                reference: d.reference || "",
            };
            const created = await apiJson("/api/inventory/cycle-counts/", { method: "POST", body: JSON.stringify(payload) });
            toast("Cycle count created.", "success");
            return setHashParam("#/stock-control", { tab: "cycle-counts", count: created.id });
        },
    });
}

async function runCountForm(id) {
    let count;
    try { count = await apiJson(`/api/inventory/cycle-counts/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    if (count.status === "reconciled") return toast("This cycle count is already reconciled.", "error");
    let stock = [];
    try {
        stock = (await apiList(`/api/inventory/stock/${buildQuery({ warehouse_id: count.warehouse, page_size: 200 })}`)).results;
    } catch (error) {
        return toast(errorMessage(error), "error");
    }
    if (!stock.length) return toast("This warehouse has no stock records to count.", "error");
    await openModal({
        title: `Run count ${count.reference || `#${count.id}`}`,
        size: "max-w-2xl",
        submitLabel: "Apply counted quantities",
        html: `<p class="mb-4 text-xs text-slate-500">Enter the physically counted quantity for each product you counted. Leave a row empty to skip it. Differences are posted as stock adjustments and the count is then reconciled.</p>
            ${fieldGrid(stock.map((row) => field({
                name: `q_${row.product}`,
                label: `${row.product_name || "Product"} (book ${numberText(row.quantity)})`,
                type: "number",
                step: "any",
                min: 0,
                value: "",
                full: true,
            })).join(""))}`,
        onSubmit: async (form) => {
            const d = readForm(form);
            const lines = Object.entries(d)
                .filter(([key, value]) => key.startsWith("q_") && value !== "")
                .map(([key, value]) => ({
                    product_id: Number(key.slice(2)),
                    counted_quantity: toNumber(value, "Counted quantity", { min: 0 }),
                }));
            if (!lines.length) throw new Error("Enter at least one counted quantity.");
            const result = await apiJson(`/api/inventory/cycle-counts/${id}/run/`, { method: "POST", body: JSON.stringify({ lines }) });
            toast(`Count reconciled with ${result.movements.length} adjustment(s).`, "success");
            return setHashParam("#/stock-control", { tab: "cycle-counts", count: id });
        },
    });
}

/* ── Reservations and availability ────────────────────────────────────────── */

async function renderReservations(body) {
    const query = buildQuery({ warehouse_id: state.warehouseId, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/inventory/reservations/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Product", cell: (r) => esc(r.product_name || "-") },
            { label: "Warehouse", cell: (r) => esc(r.warehouse_name || "-") },
            { label: "Quantity", align: "right", cell: (r) => esc(numberText(r.quantity)) },
            { label: "Reference", cell: (r) => esc(r.reference || "-") },
            { label: "Expires", cell: (r) => esc(r.expires_at ? formatDate(r.expires_at) : "-") },
            { label: "Status", cell: (r) => statusBadge(r.status) },
        ],
        rows: data.results,
        empty: "No reservations found.",
        actions: (r) => (r.status === "active" ? actionButton("Release", "release-reservation", { tone: "danger", data: { id: r.id } }) : ""),
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function reservationForm() {
    const productOptions = state.products.map((p) => ({ value: p.id, label: productLabel(p) }));
    const warehouseOptions = state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }));
    if (!productOptions.length || !warehouseOptions.length) return toast("Add at least one product and one warehouse first.", "error");
    await openModal({
        title: "New stock reservation",
        size: "max-w-2xl",
        submitLabel: "Reserve stock",
        html: fieldGrid([
            field({ name: "product", label: "Product", type: "select", options: productOptions, value: productOptions[0].value, required: true, full: true }),
            field({ name: "warehouse", label: "Warehouse", type: "select", options: warehouseOptions, value: warehouseOptions[0].value, required: true, full: true }),
            field({ name: "quantity", label: "Quantity", type: "number", step: "any", min: 0, value: "1", required: true }),
            field({ name: "expires_at", label: "Expires on", type: "date", value: "" }),
            field({ name: "reference", label: "Reference", value: "", full: true, placeholder: "e.g. ORDER-1024 or a hold note" }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const quantity = toNumber(d.quantity, "Quantity", { min: 0 });
            if (quantity <= 0) throw new Error("Quantity must be greater than zero.");
            const payload = {
                product: toNumber(d.product, "Product", { min: 1 }),
                warehouse: toNumber(d.warehouse, "Warehouse", { min: 1 }),
                quantity,
                reference: d.reference || "",
                expires_at: dateOrNull(d.expires_at),
            };
            await apiJson("/api/inventory/reservations/", { method: "POST", body: JSON.stringify(payload) });
            toast("Stock reserved.", "success");
            await renderTab();
            return true;
        },
    });
}

async function releaseReservation(id) {
    const ok = await confirmDialog({
        title: "Release this reservation?",
        message: "The reserved quantity becomes available to other sales again.",
        confirmLabel: "Release",
    });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(`/api/inventory/reservations/${id}/release/`, { method: "POST" }), { successMessage: "Reservation released.", errorFallback: "Could not release the reservation." });
    if (result === undefined) return;
    await renderTab();
}

async function availabilityForm() {
    const productOptions = state.products.map((p) => ({ value: p.id, label: productLabel(p) }));
    if (!productOptions.length) return toast("No products to check.", "error");
    const warehouseOptions = [{ value: "", label: "All warehouses" }, ...state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }))];
    await openModal({
        title: "Check available stock",
        submitLabel: "Check",
        html: fieldGrid([
            field({ name: "product", label: "Product", type: "select", options: productOptions, value: productOptions[0].value, required: true, full: true }),
            field({ name: "warehouse", label: "Warehouse", type: "select", options: warehouseOptions, value: "", full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const query = buildQuery({ product: toNumber(d.product, "Product", { min: 1 }), warehouse_id: d.warehouse });
            const result = await apiJson(`/api/inventory/available/${query}`);
            const where = d.warehouse ? warehouseName(d.warehouse) : "all warehouses";
            toast(`Available in ${where}: ${result.available}`, "success");
            return true;
        },
    });
}

/* ── Aging ────────────────────────────────────────────────────────────────── */

async function renderAging(body) {
    const query = buildQuery({ bucket: state.bucket, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/inventory/aging/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Product", cell: (a) => esc(a.product_name || "-") },
            { label: "SKU", cell: (a) => `<span class="font-mono text-xs">${esc(a.product_sku || "-")}</span>` },
            { label: "Days since last stock-in", cell: (a) => esc(a.bucket || "-") },
            { label: "Quantity", align: "right", cell: (a) => esc(numberText(a.quantity)) },
            { label: "Captured", cell: (a) => esc(formatDateTime(a.captured_at)) },
        ],
        rows: data.results,
        empty: "No aging data found.",
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function deleteRecord(url, question, success, after) {
    const ok = await confirmDialog({ title: question, message: "This cannot be undone.", confirmLabel: "Delete" });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(url, { method: "DELETE" }), { successMessage: success, errorFallback: "Could not delete this record." });
    if (result === undefined) return;
    if (after) return after();
    await renderTab();
}

