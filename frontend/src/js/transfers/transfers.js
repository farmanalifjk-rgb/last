/**
 * Transfers controller: stock transfers between warehouses (create, receive),
 * bin replenishment tasks (list, generate) and warehouse management
 * (create, edit, archive).
 *
 * Route: #/transfers?tab=transfers|replenishment|warehouses
 *
 * Endpoints used:
 *   /api/transfers/transfers/                          GET, POST
 *   /api/transfers/transfers/{id}/                     GET
 *   /api/transfers/transfers/{id}/receive/             POST
 *   /api/transfers/replenishment/                      GET
 *   /api/transfers/warehouses/{id}/replenishment/generate/ POST
 *   /api/inventory/warehouses/                         GET, POST
 *   /api/inventory/warehouses/{id}/                    GET, PATCH
 *   /api/inventory/warehouses/{id}/archive/            POST
 *   /api/stores/                                       GET (store picker)
 *   /api/products/                                     GET (line picker)
 */
import { createIcons, icons } from "lucide";
import { apiJson, apiList, buildQuery } from "../../services/api.js";
import {
    esc, formatDateTime, toast, errorMessage, openModal, confirmDialog,
    field, fieldGrid, readForm, requireValue, toNumber, table, badge, pager, tabs, statusBadge,
    pageHeader, primaryButton, secondaryButton, actionButton, runAction, emptyStateCard,
    hashParam, setHashParam, selectInput,
} from "../../shared/ui.js";

const PAGE_SIZE = 10;
const TABS = [
    { id: "transfers", label: "Transfers" },
    { id: "replenishment", label: "Replenishment" },
    { id: "warehouses", label: "Warehouses" },
];

const state = { tab: "transfers", page: 1, warehouseFilter: "", warehouses: [], products: {} };

const root = () => document.getElementById("transfers-root");

window.initializeTransfers = async function () {
    const container = root();
    if (!container) return;
    container.addEventListener("click", onClick);
    container.addEventListener("submit", (event) => event.preventDefault());
    container.addEventListener("change", onChange);
    const requested = hashParam("tab") || (window.location.hash.startsWith("#/warehouses") ? "warehouses" : "transfers");
    state.tab = TABS.some((t) => t.id === requested) ? requested : "transfers";
    state.page = 1;
    state.warehouseFilter = "";
    await loadWarehouses();
    if (hashParam("transfer")) return renderTransfer(hashParam("transfer"));
    return renderTab();
};

async function loadWarehouses() {
    try { state.warehouses = (await apiList("/api/inventory/warehouses/?page_size=200")).results; } catch { state.warehouses = []; }
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
    if (tabEl) return setHashParam("#/transfers", { tab: tabEl.dataset.tab });
    const openEl = event.target.closest("[data-open]");
    if (openEl) return setHashParam("#/transfers", { transfer: openEl.dataset.open });
}

function onChange(event) {
    if (event.target.id === "transfer-warehouse") {
        state.warehouseFilter = event.target.value;
        state.page = 1;
        renderTab();
    }
}

async function handleAction(action, el) {
    const id = el.dataset.id;
    switch (action) {
        case "new-transfer": return transferForm();
        case "receive": return receiveForm(id);
        case "new-warehouse": return warehouseForm(null);
        case "edit-warehouse": return warehouseForm(id);
        case "archive-warehouse": return archiveWarehouse(id);
        case "generate-replenishment": return generateReplenishment();
        case "back": return setHashParam("#/transfers", { tab: "transfers" });
        default: return undefined;
    }
}

/* ── Shell ────────────────────────────────────────────────────────────────── */

function frame(content) {
    const actions = state.tab === "transfers" ? primaryButton("New transfer", "new-transfer")
        : state.tab === "warehouses" ? primaryButton("New warehouse", "new-warehouse")
        : primaryButton("Generate tasks", "generate-replenishment");
    root().innerHTML = `${pageHeader({ title: "Transfers & warehouses", subtitle: "Move stock between warehouses, replenish bins and manage locations", actions })}
    <div class="mb-6">${tabs(TABS, state.tab)}</div>${content}`;
}

function warehouseSelect(id, label) {
    const options = [{ value: "", label }, ...state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }))];
    return selectInput(id, options, id === "transfer-warehouse" ? state.warehouseFilter : "");
}

async function renderTab() {
    const container = root();
    if (!container) return;
    if (!document.getElementById("transfers-body") || container.dataset.tab !== state.tab) {
        const filters = state.tab === "transfers"
            ? warehouseSelect("transfer-warehouse", "All warehouses")
            : "";
        frame(`<div class="mb-5 flex flex-wrap items-center gap-3">${filters}</div><div id="transfers-body"></div>`);
        container.dataset.tab = state.tab;
    }
    const body = document.getElementById("transfers-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        if (state.tab === "transfers") await renderTransfers(body);
        else if (state.tab === "replenishment") await renderReplenishment(body);
        else await renderWarehouses(body);
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this list", errorMessage(error));
    }
    createIcons({ icons });
}

const paged = (data) => pager({ page: data.page, totalPages: data.total_pages, count: data.count });

/* ── Transfers ────────────────────────────────────────────────────────────── */

async function renderTransfers(body) {
    const query = buildQuery({ warehouse_id: state.warehouseFilter, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/transfers/transfers/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Transfer", cell: (t) => `<button type="button" data-open="${esc(t.id)}" class="font-mono text-xs font-semibold text-violet-700 hover:underline">${esc(t.transfer_number)}</button>` },
            { label: "From", cell: (t) => esc(t.source_name || "-") },
            { label: "To", cell: (t) => esc(t.destination_name || "-") },
            { label: "Lines", align: "right", cell: (t) => esc(Array.isArray(t.items) ? t.items.length : "-") },
            { label: "Created", cell: (t) => esc(formatDateTime(t.created_at)) },
            { label: "Received", cell: (t) => esc(formatDateTime(t.received_at)) },
            { label: "Status", cell: (t) => statusBadge(t.status) },
        ],
        rows: data.results,
        empty: "No transfers yet.",
        actions: (t) => (t.status === "in_transit" ? actionButton("Receive", "receive", { data: { id: t.id } }) : ""),
    })}${paged(data)}`;
}

async function renderTransfer(id) {
    const container = root();
    let t;
    try {
        t = await apiJson(`/api/transfers/transfers/${id}/`);
    } catch (error) {
        container.innerHTML = `${pageHeader({ title: "Transfer", actions: secondaryButton("Back to transfers", "back") })}${emptyStateCard("Transfer not found", errorMessage(error))}`;
        return;
    }
    const items = Array.isArray(t.items) ? t.items : [];
    container.innerHTML = `${pageHeader({
        title: t.transfer_number,
        subtitle: `${t.source_name || "-"} → ${t.destination_name || "-"}`,
        actions: secondaryButton("Back to transfers", "back")
            + (t.status === "in_transit" ? actionButton("Receive", "receive", { data: { id: t.id } }) : ""),
    })}
    <div class="mb-6 flex flex-wrap items-center gap-3">${statusBadge(t.status)}
        <span class="text-sm text-slate-500">Shipped ${esc(formatDateTime(t.shipped_at))} · Received ${esc(formatDateTime(t.received_at))} · By ${esc(t.created_by || "-")}</span>
    </div>
    ${t.note ? `<div class="mb-6 rounded-2xl border border-slate-200 bg-white p-5 text-sm whitespace-pre-wrap">${esc(t.note)}</div>` : ""}
    ${table({
        columns: [
            { label: "Product", cell: (i) => `<span class="font-semibold">${esc(i.product_name || "-")}</span> <span class="text-xs text-slate-500">${esc(i.product_sku || "")}</span>` },
            { label: "Sent", align: "right", cell: (i) => esc(i.quantity) },
            { label: "Received", align: "right", cell: (i) => esc(i.received_quantity) },
            { label: "Outstanding", align: "right", cell: (i) => esc(Math.max(0, Number(i.quantity) - Number(i.received_quantity || 0))) },
        ],
        rows: items,
        empty: "No lines on this transfer.",
    })}`;
    createIcons({ icons });
}

async function transferForm() {
    const products = await apiList("/api/products/?page_size=200");
    const whOptions = state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }));
    const productOptions = products.results.map((p) => ({ value: p.id, label: `${p.name}${p.sku ? ` · ${p.sku}` : ""}` }));
    if (whOptions.length < 2) return toast("You need at least two warehouses to transfer stock.", "error");
    const done = openModal({
        title: "New stock transfer",
        size: "max-w-3xl",
        submitLabel: "Ship transfer",
        html: `${fieldGrid([
            field({ name: "source_warehouse", label: "From warehouse", type: "select", options: whOptions, value: whOptions[0].value, required: true }),
            field({ name: "destination_warehouse", label: "To warehouse", type: "select", options: whOptions, value: whOptions[1].value, required: true }),
            field({ name: "note", label: "Note", type: "textarea", full: true }),
        ])}
        <div class="mt-6">
            <div class="mb-3 flex items-center justify-between">
                <p class="text-sm font-semibold text-slate-800">Lines</p>
                <button type="button" data-tr-add class="h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50">Add line</button>
            </div>
            <div id="tr-lines" class="space-y-3"></div>
            <p class="mt-2 text-xs text-slate-500">Stock is taken from the source warehouse when the transfer ships. Quantities must be positive.</p>
        </div>`,
        onSubmit: async (form) => {
            const d = readForm(form);
            const rows = [...form.querySelectorAll("[data-tr-line]")];
            const items = rows.map((row, i) => {
                const product = row.querySelector("select").value;
                const quantity = row.querySelector("input").value;
                if (!product) throw new Error(`Line ${i + 1}: choose a product.`);
                return { product_id: toNumber(product, "Product", { min: 1 }), quantity: toNumber(quantity, `Line ${i + 1} quantity`, { min: 0.01 }) };
            });
            if (!items.length) throw new Error("Add at least one line.");
            if (new Set(items.map((i) => i.product_id)).size !== items.length) throw new Error("A product may appear only once per transfer.");
            const created = await apiJson("/api/transfers/transfers/", {
                method: "POST",
                body: JSON.stringify({
                    source_warehouse: toNumber(requireValue(d.source_warehouse, "Choose a source warehouse."), "Source warehouse"),
                    destination_warehouse: toNumber(requireValue(d.destination_warehouse, "Choose a destination warehouse."), "Destination warehouse"),
                    note: d.note || "",
                    items,
                }),
            });
            toast(created.transfer_number ? `Transfer ${created.transfer_number} shipped.` : "Transfer shipped.", "success");
            setHashParam("#/transfers", { transfer: created.id });
            return true;
        },
    });
    mountLines(productOptions);
    await done;
}

function mountLines(productOptions) {
    const host = document.getElementById("tr-lines");
    if (!host) return;
    let counter = 0;
    const addLine = () => {
        const wrap = document.createElement("div");
        const n = counter++;
        wrap.innerHTML = `<div class="grid grid-cols-12 items-end gap-3" data-tr-line>
            <div class="col-span-8">${field({ name: `tl_p_${n}`, label: n === 0 ? "Product" : "", type: "select", options: [{ value: "", label: "Select product" }, ...productOptions] })}</div>
            <div class="col-span-3">${field({ name: `tl_q_${n}`, label: n === 0 ? "Quantity" : "", type: "number", step: "0.01", min: "0" })}</div>
            <div class="col-span-1 pb-1"><button type="button" data-tr-remove class="h-11 w-full rounded-xl border border-rose-200 text-rose-600 hover:bg-rose-50" aria-label="Remove line">✕</button></div>
        </div>`;
        host.appendChild(wrap.firstElementChild);
    };
    addLine();
    document.querySelector("#ui-modal-root [data-tr-add]")?.addEventListener("click", addLine);
    host.addEventListener("click", (event) => {
        const remove = event.target.closest("[data-tr-remove]");
        if (remove && host.querySelectorAll("[data-tr-line]").length > 1) remove.closest("[data-tr-line]").remove();
    });
}

async function receiveForm(id) {
    const t = await apiJson(`/api/transfers/transfers/${id}/`);
    const open = (t.items || []).filter((i) => Number(i.quantity) - Number(i.received_quantity || 0) > 0);
    if (!open.length) return toast("Nothing left to receive on this transfer.", "info");
    await openModal({
        title: `Receive ${t.transfer_number}`,
        size: "max-w-2xl",
        submitLabel: "Post receipt",
        html: `<p class="mb-4 text-sm text-slate-600">Enter the quantity that arrived at ${esc(t.destination_name || "the destination")}. Leave a line blank to keep it open for a later receipt.</p>
        <div class="space-y-3">
            ${open.map((i, n) => {
                const remaining = Number(i.quantity) - Number(i.received_quantity || 0);
                return `<div class="grid grid-cols-12 items-end gap-3" data-recv data-item="${esc(i.id)}" data-remaining="${esc(remaining)}">
                    <div class="col-span-7 text-sm"><p class="font-semibold text-slate-800">${esc(i.product_name)}</p><p class="text-xs text-slate-500">Outstanding ${esc(remaining)}</p></div>
                    <div class="col-span-5">${field({ name: `rv_${n}`, label: n === 0 ? "Received quantity" : "", type: "number", step: "0.01", min: "0", value: String(remaining) })}</div>
                </div>`;
            }).join("")}
        </div>`,
        onSubmit: async (form) => {
            const lines = open.map((item, n) => {
                const remaining = Number(item.quantity) - Number(item.received_quantity || 0);
                const raw = form.querySelector(`[name="rv_${n}"]`).value;
                const received = raw === "" ? 0 : toNumber(raw, `${item.product_name} quantity`, { min: 0 });
                if (received > remaining) throw new Error(`${item.product_name}: cannot receive more than the outstanding ${remaining}.`);
                return { item_id: item.id, received_quantity: received };
            });
            await apiJson(`/api/transfers/transfers/${id}/receive/`, { method: "POST", body: JSON.stringify({ lines }) });
            toast("Receipt posted to the destination warehouse.", "success");
            await renderTransfer(id);
            return true;
        },
    });
}

/* ── Replenishment ────────────────────────────────────────────────────────── */

async function renderReplenishment(body) {
    const data = await apiList(`/api/transfers/replenishment/${buildQuery({ page: state.page, page_size: PAGE_SIZE })}`);
    if (!Object.keys(state.products).length) {
        try {
            const products = await apiList("/api/products/?page_size=200");
            state.products = Object.fromEntries(products.results.map((p) => [p.id, p.name]));
        } catch { state.products = {}; }
    }
    const warehouseName = (id) => state.warehouses.find((w) => String(w.id) === String(id))?.name || `Warehouse #${id}`;
    body.innerHTML = `<div class="mb-4 rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        Generate tasks for a warehouse to create bin replenishment work for products below the threshold. Tasks already open are not duplicated.
    </div>${table({
        columns: [
            { label: "Warehouse", cell: (r) => esc(warehouseName(r.warehouse)) },
            { label: "Product", cell: (r) => esc(state.products[r.product] || `Product #${r.product}`) },
            { label: "From bin", cell: (r) => esc(r.from_bin ? `Bin #${r.from_bin}` : "-") },
            { label: "To bin", cell: (r) => esc(r.to_bin ? `Bin #${r.to_bin}` : "-") },
            { label: "Quantity", align: "right", cell: (r) => esc(r.quantity) },
            { label: "Created", cell: (r) => esc(formatDateTime(r.created_at)) },
            { label: "Status", cell: (r) => statusBadge(r.status) },
        ],
        rows: data.results,
        empty: "No replenishment tasks.",
    })}${paged(data)}`;
}

async function generateReplenishment() {
    if (!state.warehouses.length) return toast("Create a warehouse first.", "error");
    const options = state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }));
    await openModal({
        title: "Generate replenishment tasks",
        size: "max-w-md",
        submitLabel: "Generate",
        html: fieldGrid([
            field({ name: "warehouse", label: "Warehouse", type: "select", options, value: options[0].value, required: true, full: true }),
            field({ name: "threshold", label: "Low-stock threshold", type: "number", step: "0.01", min: "0", value: "5", help: "Products at or below this quantity in a bin are queued for replenishment.", full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const warehouseId = toNumber(requireValue(d.warehouse, "Choose a warehouse."), "Warehouse", { min: 1 });
            const threshold = toNumber(d.threshold, "Threshold", { min: 0 });
            const result = await apiJson(`/api/transfers/warehouses/${warehouseId}/replenishment/generate/`, {
                method: "POST",
                body: JSON.stringify({ threshold }),
            });
            const count = Array.isArray(result?.created) ? result.created.length : 0;
            toast(`${count} replenishment task${count === 1 ? "" : "s"} created.`, "success");
            state.tab = "replenishment";
            await renderTab();
            return true;
        },
    });
}

/* ── Warehouses ───────────────────────────────────────────────────────────── */

async function renderWarehouses(body) {
    const data = await apiList(`/api/inventory/warehouses/${buildQuery({ page: state.page, page_size: PAGE_SIZE })}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Code", cell: (w) => `<span class="font-mono text-xs font-semibold">${esc(w.code)}</span>` },
            { label: "Name", cell: (w) => `<span class="font-semibold">${esc(w.name)}</span>` },
            { label: "Store", cell: (w) => esc(w.store_name || (w.store ? `Store #${w.store}` : "-")) },
            { label: "Address", cell: (w) => esc(w.address || "-") },
            { label: "Status", cell: (w) => (w.is_active ? badge("Active", "green") : badge("Archived", "slate")) },
        ],
        rows: data.results,
        empty: "No warehouses yet.",
        actions: (w) => actionButton("Edit", "edit-warehouse", { data: { id: w.id } })
            + (w.is_active ? actionButton("Archive", "archive-warehouse", { tone: "danger", data: { id: w.id } }) : ""),
    })}${paged(data)}`;
}

async function warehouseForm(id) {
    let w = {};
    if (id) {
        try { w = await apiJson(`/api/inventory/warehouses/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    let stores = [];
    try { stores = (await apiList("/api/stores/?page_size=200")).results; } catch { stores = []; }
    const storeOptions = stores.map((s) => ({ value: s.id, label: s.name }));
    if (!storeOptions.length) return toast("No store is configured. Add a store before creating warehouses.", "error");
    await openModal({
        title: id ? "Edit warehouse" : "New warehouse",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create warehouse",
        html: fieldGrid([
            field({ name: "code", label: "Code", value: w.code || "", required: true, help: "Short unique code, e.g. MAIN-WH." }),
            field({ name: "name", label: "Name", value: w.name || "", required: true }),
            field({ name: "store", label: "Store", type: "select", options: storeOptions, value: w.store ?? storeOptions[0].value, required: true, full: true }),
            field({ name: "address", label: "Address", type: "textarea", value: w.address || "", full: true }),
            field({ name: "is_active", label: "Active", type: "checkbox", value: w.is_active ?? true, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = {
                code: requireValue(d.code, "Warehouse code is required.").toUpperCase(),
                name: requireValue(d.name, "Warehouse name is required."),
                store: toNumber(d.store, "Store", { min: 1 }),
                address: d.address || "",
                is_active: d.is_active,
            };
            await apiJson(id ? `/api/inventory/warehouses/${id}/` : "/api/inventory/warehouses/", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Warehouse updated." : "Warehouse created.", "success");
            await loadWarehouses();
            await renderTab();
            return true;
        },
    });
}

async function archiveWarehouse(id) {
    const ok = await confirmDialog({
        title: "Archive warehouse?",
        message: "Warehouses with on-hand stock cannot be archived. Archived warehouses stop accepting transfers and receipts.",
        confirmLabel: "Archive",
    });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(`/api/inventory/warehouses/${id}/archive/`, { method: "POST" }), { successMessage: "Warehouse archived.", errorFallback: "Could not archive the warehouse." });
    if (result === undefined) return;
    await loadWarehouses();
    await renderTab();
}
