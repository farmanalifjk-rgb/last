/**
 * Purchasing controller: suppliers (with contacts, archive, portal access),
 * purchase orders (create, edit draft, confirm, cancel), goods receipts and
 * purchase returns (create, process, cancel).
 *
 * Route: #/purchasing?tab=orders|receipts|returns|suppliers
 *        plus ?po=ID, ?supplier=ID for detail panels.
 *
 * Endpoints used:
 *   /api/suppliers/                              GET, POST
 *   /api/suppliers/{id}/                         GET, PATCH
 *   /api/suppliers/{id}/archive/                 POST
 *   /api/suppliers/{id}/summary/                 GET
 *   /api/suppliers/{id}/portal-token/            POST
 *   /api/suppliers/{id}/contacts/                GET, POST
 *   /api/supplier-contacts/{id}/                 PATCH, DELETE
 *   /api/purchasing/purchase-orders/             GET, POST
 *   /api/purchasing/purchase-orders/{id}/        GET, PATCH
 *   /api/purchasing/purchase-orders/{id}/confirm/ POST
 *   /api/purchasing/purchase-orders/{id}/cancel/  POST
 *   /api/purchasing/receipts/                    GET, POST
 *   /api/purchasing/receipts/{id}/               GET
 *   /api/purchasing/purchase-returns/            GET, POST
 *   /api/purchasing/purchase-returns/{id}/       GET
 *   /api/purchasing/purchase-returns/{id}/process/ POST
 *   /api/purchasing/purchase-returns/{id}/cancel/  POST
 */
import { createIcons, icons } from "lucide";
import { apiJson, apiList, buildQuery } from "../../services/api.js";
import {
    esc, formatMoney, formatDate, formatDateTime, toast, errorMessage, openModal, confirmDialog,
    field, fieldGrid, readForm, requireValue, toNumber, table, badge, pager, tabs, statusBadge,
    pageHeader, primaryButton, secondaryButton, actionButton, searchInput, debounce, runAction,
    emptyStateCard, hashParam, setHashParam,
} from "../../shared/ui.js";

const PAGE_SIZE = 10;
const TABS = [
    { id: "orders", label: "Purchase orders" },
    { id: "receipts", label: "Goods receipts" },
    { id: "returns", label: "Returns" },
    { id: "suppliers", label: "Suppliers" },
];
const PO_STATUSES = [
    { value: "", label: "All statuses" },
    { value: "draft", label: "Draft" },
    { value: "ordered", label: "Ordered" },
    { value: "received", label: "Received" },
    { value: "cancelled", label: "Cancelled" },
];

const state = {
    tab: "orders",
    page: 1,
    search: "",
    status: "",
    warehouses: [],
    suppliers: [],
};

const root = () => document.getElementById("purchasing-root");

window.initializePurchasing = async function () {
    const container = root();
    if (!container) return;
    container.addEventListener("click", onClick);
    container.addEventListener("submit", (event) => event.preventDefault());
    container.addEventListener("input", onInput);
    container.addEventListener("change", onChange);
    state.tab = hashParam("tab") || (window.location.hash.startsWith("#/suppliers") ? "suppliers" : "orders");
    if (!TABS.some((t) => t.id === state.tab)) state.tab = "orders";
    state.page = 1;
    state.search = "";
    state.status = "";
    await loadReference();
    await route();
};

async function loadReference() {
    try { state.warehouses = (await apiList("/api/inventory/warehouses/")).results; } catch { state.warehouses = []; }
}

async function route() {
    if (hashParam("po")) return renderPurchaseOrder(hashParam("po"));
    if (hashParam("supplier")) return renderSupplier(hashParam("supplier"));
    return renderTab();
}

function go(params) {
    setHashParam("#/purchasing", params);
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
    if (tabEl) return go({ tab: tabEl.dataset.tab });
    const openEl = event.target.closest("[data-open]");
    if (openEl) {
        const kind = openEl.dataset.open;
        return go({ [kind]: openEl.dataset.id });
    }
}

function onInput(event) {
    if (event.target.id === "po-search") debouncedSearch(event.target.value);
}

function onChange(event) {
    if (event.target.id === "po-status") {
        state.status = event.target.value;
        state.page = 1;
        renderTab();
    }
}

const debouncedSearch = debounce((value) => {
    state.search = value.trim();
    state.page = 1;
    renderTab();
}, 350);

async function handleAction(action, el) {
    const id = el.dataset.id;
    switch (action) {
        case "new-supplier": return supplierForm(null);
        case "edit-supplier": return supplierForm(id);
        case "archive-supplier": return archiveSupplier(id);
        case "portal-access": return enablePortal(id);
        case "add-contact": return contactForm(hashParam("supplier"), null);
        case "edit-contact": return contactForm(hashParam("supplier"), el.dataset.row);
        case "delete-contact": return deleteRecord(`/api/supplier-contacts/${id}/`, "Remove this contact?", () => renderSupplier(hashParam("supplier")));
        case "new-po": return purchaseOrderForm(null);
        case "edit-po": return purchaseOrderForm(id);
        case "confirm-po": return confirmPurchaseOrder(id);
        case "cancel-po": return cancelPurchaseOrder(id);
        case "receive-po": return receiveForm(id);
        case "return-po": return returnForm(id);
        case "view-receipt": return viewReceipt(id);
        case "view-return": return viewReturn(id);
        case "process-return": return transitionReturn(id, "process", "Process this return? Stock will be reduced and the credit recorded.");
        case "cancel-return": return transitionReturn(id, "cancel", "Cancel this return?");
        case "back": return go({ tab: state.tab === "suppliers" ? "suppliers" : "orders" });
        default: return undefined;
    }
}

/* ── Tab rendering ────────────────────────────────────────────────────────── */

function frame(content) {
    const container = root();
    container.innerHTML = `${pageHeader({
        title: "Purchasing",
        subtitle: "Suppliers, purchase orders, goods receipts and returns",
        actions: state.tab === "suppliers" ? primaryButton("New supplier", "new-supplier")
            : state.tab === "orders" ? primaryButton("New purchase order", "new-po") : "",
    })}
    <div class="mb-6">${tabs(TABS, state.tab)}</div>
    ${content}`;
}

function filtersHtml() {
    if (state.tab === "orders") {
        const statusSelect = `<select id="po-status" class="h-11 rounded-xl border border-slate-200 bg-white px-4 text-sm">${PO_STATUSES.map((s) => `<option value="${esc(s.value)}" ${s.value === state.status ? "selected" : ""}>${esc(s.label)}</option>`).join("")}</select>`;
        return `${searchInput("po-search", "Search order number or supplier")}${statusSelect}`;
    }
    if (state.tab === "suppliers") return searchInput("po-search", "Search name, company, phone or email");
    return "";
}

async function renderTab() {
    const container = root();
    if (!container) return;
    // Rebuild the chrome only when the tab changes, so the search box keeps focus while typing.
    if (!document.getElementById("purchasing-body") || container.dataset.tab !== state.tab) {
        frame(`<div id="purchasing-filters" class="mb-5 flex flex-wrap items-center gap-3">${filtersHtml()}</div><div id="purchasing-body"></div>`);
        container.dataset.tab = state.tab;
        const search = document.getElementById("po-search");
        if (search && state.search) search.value = state.search;
    }
    const body = document.getElementById("purchasing-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        if (state.tab === "orders") await renderOrders(body);
        else if (state.tab === "receipts") await renderReceipts(body);
        else if (state.tab === "returns") await renderReturns(body);
        else await renderSuppliers(body);
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this list", errorMessage(error));
    }
    createIcons({ icons });
}

function paged(data) {
    return pager({ page: data.page, totalPages: data.total_pages, count: data.count });
}

async function renderOrders(body) {
    const query = buildQuery({ search: state.search, status: state.status, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/purchasing/purchase-orders/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Order", cell: (o) => `<button type="button" data-open="po" data-id="${esc(o.id)}" class="font-mono text-xs font-semibold text-violet-700 hover:underline">${esc(o.order_number)}</button>` },
            { label: "Supplier", cell: (o) => esc(o.supplier_name || "-") },
            { label: "Warehouse", cell: (o) => esc(o.warehouse_name || "-") },
            { label: "Expected", cell: (o) => esc(formatDate(o.expected_date)) },
            { label: "Total", align: "right", cell: (o) => esc(formatMoney(o.total)) },
            { label: "Remaining qty", align: "right", cell: (o) => esc(o.remaining_quantity ?? "-") },
            { label: "Status", cell: (o) => statusBadge(o.status) },
        ],
        rows: data.results,
        empty: "No purchase orders yet.",
    })}${paged(data)}`;
}

async function renderReceipts(body) {
    const data = await apiList(`/api/purchasing/receipts/${buildQuery({ page: state.page, page_size: PAGE_SIZE })}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Receipt", cell: (r) => `<button type="button" data-action="view-receipt" data-id="${esc(r.id)}" class="font-mono text-xs font-semibold text-violet-700 hover:underline">${esc(r.receipt_number)}</button>` },
            { label: "Purchase order", cell: (r) => `<button type="button" data-open="po" data-id="${esc(r.purchase_order)}" class="font-mono text-xs hover:underline">${esc(r.purchase_order_number || "-")}</button>` },
            { label: "Supplier", cell: (r) => esc(r.supplier_name || "-") },
            { label: "Warehouse", cell: (r) => esc(r.warehouse_name || "-") },
            { label: "Invoice", cell: (r) => esc(r.supplier_invoice_number || "-") },
            { label: "Received", cell: (r) => esc(formatDateTime(r.received_at)) },
            { label: "Status", cell: (r) => statusBadge(r.status) },
        ],
        rows: data.results,
        empty: "No goods receipts yet. Receive stock from a confirmed purchase order.",
    })}${paged(data)}`;
}

async function renderReturns(body) {
    const data = await apiList(`/api/purchasing/purchase-returns/${buildQuery({ page: state.page, page_size: PAGE_SIZE })}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Return", cell: (r) => `<button type="button" data-action="view-return" data-id="${esc(r.id)}" class="font-mono text-xs font-semibold text-violet-700 hover:underline">${esc(r.return_number)}</button>` },
            { label: "Purchase order", cell: (r) => esc(r.purchase_order_number || "-") },
            { label: "Supplier", cell: (r) => esc(r.supplier_name || "-") },
            { label: "Reason", cell: (r) => esc(r.reason || "-") },
            { label: "Credit note", cell: (r) => esc(r.supplier_credit_note || "-") },
            { label: "Total", align: "right", cell: (r) => esc(formatMoney(r.total_amount)) },
            { label: "Status", cell: (r) => statusBadge(r.status) },
        ],
        rows: data.results,
        empty: "No purchase returns recorded.",
        actions: (r) => (r.status === "draft"
            ? actionButton("Process", "process-return", { data: { id: r.id } }) + actionButton("Cancel", "cancel-return", { tone: "danger", data: { id: r.id } })
            : ""),
    })}${paged(data)}`;
}

async function renderSuppliers(body) {
    const query = buildQuery({ search: state.search, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/suppliers/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Supplier", cell: (s) => `<button type="button" data-open="supplier" data-id="${esc(s.id)}" class="text-left font-semibold text-violet-700 hover:underline">${esc(s.name)}</button>` },
            { label: "Company", cell: (s) => esc(s.company || "-") },
            { label: "Contact", cell: (s) => esc(s.contact_person || "-") },
            { label: "Phone", cell: (s) => esc(s.phone || "-") },
            { label: "Email", cell: (s) => esc(s.email || "-") },
            { label: "Tax no.", cell: (s) => esc(s.tax_number || "-") },
            { label: "Status", cell: (s) => (s.is_active ? badge("Active", "green") : badge("Archived", "slate")) },
        ],
        rows: data.results,
        empty: state.search ? "No suppliers match your search." : "No suppliers yet.",
        actions: (s) => actionButton("Edit", "edit-supplier", { data: { id: s.id } })
            + (s.is_active ? actionButton("Archive", "archive-supplier", { tone: "danger", data: { id: s.id } }) : ""),
    })}${paged(data)}`;
}

/* ── Suppliers ────────────────────────────────────────────────────────────── */

async function supplierForm(id) {
    let s = {};
    if (id) {
        try { s = await apiJson(`/api/suppliers/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    await openModal({
        title: id ? "Edit supplier" : "New supplier",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create supplier",
        html: fieldGrid([
            field({ name: "name", label: "Name", value: s.name || "", required: true }),
            field({ name: "company", label: "Company", value: s.company || "" }),
            field({ name: "contact_person", label: "Contact person", value: s.contact_person || "" }),
            field({ name: "phone", label: "Phone", type: "tel", value: s.phone || "" }),
            field({ name: "email", label: "Email", type: "email", value: s.email || "" }),
            field({ name: "tax_number", label: "Tax number", value: s.tax_number || "" }),
            field({ name: "address", label: "Address", type: "textarea", value: s.address || "", full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = { ...d, name: requireValue(d.name, "Supplier name is required.") };
            await apiJson(id ? `/api/suppliers/${id}/` : "/api/suppliers/", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Supplier updated." : "Supplier created.", "success");
            if (hashParam("supplier")) await renderSupplier(hashParam("supplier"));
            else await renderTab();
            return true;
        },
    });
}

async function archiveSupplier(id) {
    const ok = await confirmDialog({
        title: "Archive supplier?",
        message: "Archived suppliers are hidden from new purchase orders. Existing orders and history are kept.",
        confirmLabel: "Archive",
    });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(`/api/suppliers/${id}/archive/`, { method: "POST" }), { successMessage: "Supplier archived.", errorFallback: "Could not archive the supplier." });
    if (result === undefined) return;
    if (hashParam("supplier")) go({ tab: "suppliers" }); else renderTab();
}

async function enablePortal(id) {
    const ok = await confirmDialog({
        title: "Enable supplier portal?",
        message: "This gives the supplier's contact email access to the supplier portal to view their purchase orders. Re-enabling rotates the access token.",
        confirmLabel: "Enable access",
        danger: false,
    });
    if (!ok) return;
    try {
        const token = await apiJson(`/api/suppliers/${id}/portal-token/`, { method: "POST" });
        toast(`Portal access enabled${token.contact_email ? ` for ${token.contact_email}` : ""}.`, "success");
    } catch (error) {
        toast(errorMessage(error), "error");
    }
}

async function renderSupplier(id) {
    const container = root();
    let summary;
    try {
        summary = await apiJson(`/api/suppliers/${id}/summary/`);
    } catch (error) {
        container.innerHTML = `${pageHeader({ title: "Supplier", actions: secondaryButton("Back to suppliers", "back") })}${emptyStateCard("Supplier not found", errorMessage(error))}`;
        return;
    }
    const s = summary.supplier || summary;
    const contacts = await apiList(`/api/suppliers/${id}/contacts/`).catch(() => ({ results: [] }));
    const figures = Object.entries(summary)
        .filter(([k, v]) => k !== "supplier" && (typeof v === "string" || typeof v === "number"))
        .map(([k, v]) => `<div class="rounded-2xl border border-slate-200 bg-white p-5"><p class="text-xs font-semibold uppercase tracking-wide text-slate-500">${esc(k.replace(/_/g, " "))}</p><p class="mt-2 text-xl font-bold text-slate-900 tabular-nums">${esc(v)}</p></div>`)
        .join("");
    container.innerHTML = `
    ${pageHeader({
        title: s.name || "Supplier",
        subtitle: s.company || "",
        actions: secondaryButton("Back to suppliers", "back")
            + actionButton("Edit", "edit-supplier", { data: { id: s.id ?? id } })
            + actionButton("Portal access", "portal-access", { data: { id: s.id ?? id } })
            + (s.is_active === false ? badge("Archived", "slate") : actionButton("Archive", "archive-supplier", { tone: "danger", data: { id: s.id ?? id } })),
    })}
    <div class="mb-6 grid grid-cols-2 gap-6">
        <div class="rounded-2xl border border-slate-200 bg-white p-6">
            <h3 class="mb-4 text-base font-bold text-slate-900">Details</h3>
            <dl class="grid grid-cols-3 gap-y-3 text-sm">
                <dt class="text-slate-500">Contact</dt><dd class="col-span-2">${esc(s.contact_person || "-")}</dd>
                <dt class="text-slate-500">Phone</dt><dd class="col-span-2">${esc(s.phone || "-")}</dd>
                <dt class="text-slate-500">Email</dt><dd class="col-span-2">${esc(s.email || "-")}</dd>
                <dt class="text-slate-500">Tax number</dt><dd class="col-span-2">${esc(s.tax_number || "-")}</dd>
                <dt class="text-slate-500">Address</dt><dd class="col-span-2">${esc(s.address || "-")}</dd>
            </dl>
        </div>
        <div class="grid grid-cols-2 content-start gap-4">${figures || emptyStateCard("No figures", "No summary figures are available yet.")}</div>
    </div>
    <div class="mb-3 flex items-center justify-between">
        <h3 class="text-base font-bold text-slate-900">Contacts</h3>
        ${primaryButton("Add contact", "add-contact")}
    </div>
    ${table({
        columns: [
            { label: "Name", cell: (c) => esc(c.name) },
            { label: "Role", cell: (c) => esc(c.role || "-") },
            { label: "Email", cell: (c) => esc(c.email || "-") },
            { label: "Phone", cell: (c) => esc(c.phone || "-") },
            { label: "Primary", cell: (c) => (c.is_primary ? badge("Primary", "violet") : "") },
        ],
        rows: contacts.results,
        empty: "No contacts yet.",
        actions: (c) => actionButton("Edit", "edit-contact", { data: { row: c.id } })
            + actionButton("Delete", "delete-contact", { tone: "danger", data: { id: c.id } }),
    })}`;
    createIcons({ icons });
}

async function contactForm(supplierId, contactId) {
    let c = {};
    if (contactId) {
        const data = await apiList(`/api/suppliers/${supplierId}/contacts/`);
        c = data.results.find((row) => String(row.id) === String(contactId)) || {};
    }
    await openModal({
        title: contactId ? "Edit contact" : "Add contact",
        size: "max-w-lg",
        html: fieldGrid([
            field({ name: "name", label: "Name", value: c.name || "", required: true, full: true }),
            field({ name: "role", label: "Role", value: c.role || "" }),
            field({ name: "email", label: "Email", type: "email", value: c.email || "" }),
            field({ name: "phone", label: "Phone", type: "tel", value: c.phone || "" }),
            field({ name: "is_primary", label: "Primary contact", type: "checkbox", value: c.is_primary || false, full: true }),
        ]),
        submitLabel: "Save contact",
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = { ...d, name: requireValue(d.name, "Contact name is required.") };
            if (contactId) await apiJson(`/api/supplier-contacts/${contactId}/`, { method: "PATCH", body: JSON.stringify(payload) });
            else await apiJson(`/api/suppliers/${supplierId}/contacts/`, { method: "POST", body: JSON.stringify(payload) });
            toast("Contact saved.", "success");
            await renderSupplier(supplierId);
            return true;
        },
    });
}

/* ── Purchase orders ──────────────────────────────────────────────────────── */

async function loadSuppliers() {
    try { state.suppliers = (await apiList("/api/suppliers/?page_size=200&is_active=true")).results; } catch { state.suppliers = []; }
    return state.suppliers;
}

async function purchaseOrderForm(orderId) {
    let order = null;
    if (orderId) {
        try { order = await apiJson(`/api/purchasing/purchase-orders/${orderId}/`); } catch (error) { return toast(errorMessage(error), "error"); }
        if (order.status !== "draft") return toast("Only draft purchase orders can be edited.", "error");
    }
    const suppliers = await loadSuppliers();
    const products = (await apiList("/api/products/?page_size=200")).results;
    const supplierOptions = suppliers.map((s) => ({ value: s.id, label: s.name }));
    const warehouseOptions = state.warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }));
    const productOptions = products.map((p) => ({ value: p.id, label: `${p.name}${p.sku ? ` · ${p.sku}` : ""}` }));
    const initialLines = order?.items?.length
        ? order.items.map((i) => ({ product_id: i.product, quantity: i.quantity, unit_cost: i.unit_cost }))
        : [{ product_id: "", quantity: "", unit_cost: "" }];

    const done = openModal({
        title: orderId ? `Edit ${order.order_number}` : "New purchase order",
        size: "max-w-3xl",
        submitLabel: orderId ? "Save order" : "Create draft",
        html: `${fieldGrid([
            field({ name: "supplier_id", label: "Supplier", type: "select", value: order?.supplier ?? "", options: [{ value: "", label: "Select supplier" }, ...supplierOptions], required: true }),
            field({ name: "warehouse_id", label: "Receiving warehouse", type: "select", value: order?.warehouse ?? state.warehouses[0]?.id ?? "", options: warehouseOptions, required: true }),
            field({ name: "expected_date", label: "Expected date", type: "date", value: order?.expected_date || "" }),
            field({ name: "supplier_invoice_number", label: "Supplier invoice no.", value: order?.supplier_invoice_number || "" }),
            field({ name: "note", label: "Note", type: "textarea", value: order?.note || "", full: true }),
        ])}
        <div class="mt-6">
            <div class="mb-3 flex items-center justify-between">
                <p class="text-sm font-semibold text-slate-800">Lines</p>
                <button type="button" data-po-add-line class="h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50">Add line</button>
            </div>
            <div id="po-lines" class="space-y-3"></div>
            <p class="mt-2 text-xs text-slate-500">A product can appear only once. Unit cost is the price per unit paid to the supplier.</p>
        </div>`,
        onSubmit: async (form) => {
            const d = readForm(form);
            const lines = collectLines(form);
            const payload = {
                supplier_id: toNumber(requireValue(d.supplier_id, "Choose a supplier."), "Supplier"),
                warehouse_id: toNumber(requireValue(d.warehouse_id, "Choose a warehouse."), "Warehouse"),
                expected_date: d.expected_date || null,
                supplier_invoice_number: d.supplier_invoice_number || "",
                note: d.note || "",
                items: lines,
            };
            await apiJson(orderId ? `/api/purchasing/purchase-orders/${orderId}/` : "/api/purchasing/purchase-orders/", {
                method: orderId ? "PATCH" : "POST",
                body: JSON.stringify(payload),
            });
            toast(orderId ? "Purchase order saved." : "Draft purchase order created.", "success");
            await renderTab();
            return true;
        },
    });
    mountLineEditor(productOptions, initialLines);
    await done;
}

function lineRowHtml(index, productOptions, line) {
    const options = [{ value: "", label: "Select product" }, ...productOptions];
    return `<div class="grid grid-cols-12 items-end gap-3" data-po-line>
        <div class="col-span-6">${field({ name: `line_product_${index}`, label: index === 0 ? "Product" : "", type: "select", value: line.product_id ?? "", options })}</div>
        <div class="col-span-2">${field({ name: `line_qty_${index}`, label: index === 0 ? "Quantity" : "", type: "number", step: "0.01", min: "0", value: line.quantity ?? "" })}</div>
        <div class="col-span-3">${field({ name: `line_cost_${index}`, label: index === 0 ? "Unit cost" : "", type: "number", step: "0.01", min: "0", value: line.unit_cost ?? "" })}</div>
        <div class="col-span-1 pb-1"><button type="button" data-po-remove-line class="h-11 w-full rounded-xl border border-rose-200 text-rose-600 hover:bg-rose-50" aria-label="Remove line">✕</button></div>
    </div>`;
}

function mountLineEditor(productOptions, lines) {
    const host = document.getElementById("po-lines");
    if (!host) return;
    let counter = 0;
    const addLine = (line = { product_id: "", quantity: "", unit_cost: "" }) => {
        const wrapper = document.createElement("div");
        wrapper.innerHTML = lineRowHtml(counter++, productOptions, line);
        host.appendChild(wrapper.firstElementChild);
    };
    lines.forEach((line) => addLine(line));
    document.querySelector("#ui-modal-root [data-po-add-line]")?.addEventListener("click", () => addLine());
    host.addEventListener("click", (event) => {
        const remove = event.target.closest("[data-po-remove-line]");
        if (remove && host.querySelectorAll("[data-po-line]").length > 1) remove.closest("[data-po-line]").remove();
    });
}

function collectLines(form) {
    const rows = [...form.querySelectorAll("[data-po-line]")];
    if (!rows.length) throw new Error("Add at least one line.");
    const seen = new Set();
    return rows.map((row, index) => {
        const product = row.querySelector("select").value;
        const quantity = row.querySelector('input[name^="line_qty"]').value;
        const cost = row.querySelector('input[name^="line_cost"]').value;
        if (!product) throw new Error(`Line ${index + 1}: choose a product.`);
        if (seen.has(product)) throw new Error("A product may appear only once on a purchase order.");
        seen.add(product);
        return {
            product_id: toNumber(product, "Product", { min: 1 }),
            quantity: toNumber(quantity, `Line ${index + 1} quantity`, { min: 0.01 }),
            unit_cost: toNumber(cost, `Line ${index + 1} unit cost`, { min: 0 }),
        };
    });
}

async function confirmPurchaseOrder(id) {
    const ok = await confirmDialog({ title: "Confirm order?", message: "Confirming sends the order to the supplier. Draft lines can no longer be edited.", confirmLabel: "Confirm", danger: false });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(`/api/purchasing/purchase-orders/${id}/confirm/`, { method: "POST" }), { successMessage: "Order confirmed.", errorFallback: "Could not confirm the order." });
    if (result !== undefined) renderPurchaseOrder(id);
}

async function cancelPurchaseOrder(id) {
    const ok = await confirmDialog({ title: "Cancel purchase order?", message: "Cancelled orders cannot be received. This cannot be undone.", confirmLabel: "Cancel order" });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(`/api/purchasing/purchase-orders/${id}/cancel/`, { method: "POST" }), { successMessage: "Order cancelled.", errorFallback: "Could not cancel the order." });
    if (result !== undefined) renderPurchaseOrder(id);
}

async function renderPurchaseOrder(id) {
    const container = root();
    let o;
    try {
        o = await apiJson(`/api/purchasing/purchase-orders/${id}/`);
    } catch (error) {
        container.innerHTML = `${pageHeader({ title: "Purchase order", actions: secondaryButton("Back", "back") })}${emptyStateCard("Order not found", errorMessage(error))}`;
        return;
    }
    const canEdit = o.status === "draft";
    const canConfirm = o.status === "draft";
    const canReceive = o.status === "ordered" || o.status === "partially_received";
    const canReturn = (o.receipt_count ?? 0) > 0 && o.status !== "cancelled";
    const canCancel = o.status === "draft" || o.status === "ordered";
    const itemRows = Array.isArray(o.items) ? o.items : [];
    container.innerHTML = `
    ${pageHeader({
        title: o.order_number,
        subtitle: `${o.supplier_name || "-"} · ${o.warehouse_name || "-"}`,
        actions: secondaryButton("Back to orders", "back")
            + (canEdit ? actionButton("Edit", "edit-po", { data: { id: o.id } }) : "")
            + (canConfirm ? actionButton("Confirm", "confirm-po", { data: { id: o.id } }) : "")
            + (canReceive ? actionButton("Receive stock", "receive-po", { data: { id: o.id } }) : "")
            + (canReturn ? actionButton("Create return", "return-po", { data: { id: o.id } }) : "")
            + (canCancel ? actionButton("Cancel order", "cancel-po", { tone: "danger", data: { id: o.id } }) : ""),
    })}
    <div class="mb-6 flex flex-wrap items-center gap-3">${statusBadge(o.status)}
        <span class="text-sm text-slate-500">Expected ${esc(formatDate(o.expected_date))} · Invoice ${esc(o.supplier_invoice_number || "-")} · Receipts ${esc(o.receipt_count ?? 0)} · Returns ${esc(o.return_count ?? 0)}</span>
    </div>
    ${table({
        columns: [
            { label: "Product", cell: (i) => `<span class="font-semibold">${esc(i.product_name || "-")}</span> <span class="text-xs text-slate-500">${esc(i.product_sku || "")}</span>` },
            { label: "Ordered", align: "right", cell: (i) => esc(i.quantity) },
            { label: "Received", align: "right", cell: (i) => esc(i.received_quantity) },
            { label: "Returned", align: "right", cell: (i) => esc(i.returned_quantity) },
            { label: "Remaining", align: "right", cell: (i) => esc(i.remaining_quantity) },
            { label: "Unit cost", align: "right", cell: (i) => esc(formatMoney(i.unit_cost)) },
            { label: "Subtotal", align: "right", cell: (i) => esc(formatMoney(i.subtotal)) },
        ],
        rows: itemRows,
        empty: "No lines on this order.",
    })}
    <div class="mt-6 ml-auto w-80 rounded-2xl border border-slate-200 bg-white p-5 text-sm">
        <div class="flex justify-between py-1"><span class="text-slate-500">Subtotal</span><span class="tabular-nums">${esc(formatMoney(o.subtotal))}</span></div>
        <div class="flex justify-between py-1"><span class="text-slate-500">Tax</span><span class="tabular-nums">${esc(formatMoney(o.tax))}</span></div>
        <div class="flex justify-between border-t border-slate-100 pt-2 font-bold"><span>Total</span><span class="tabular-nums">${esc(formatMoney(o.total))}</span></div>
    </div>
    ${o.note ? `<div class="mt-6 rounded-2xl border border-slate-200 bg-white p-5 text-sm whitespace-pre-wrap">${esc(o.note)}</div>` : ""}`;
    createIcons({ icons });
}

/* ── Receipts and returns ─────────────────────────────────────────────────── */

async function receiveForm(orderId) {
    const o = await apiJson(`/api/purchasing/purchase-orders/${orderId}/`);
    const open = (o.items || []).filter((i) => Number(i.remaining_quantity) > 0);
    if (!open.length) return toast("Nothing left to receive on this order.", "info");
    await openModal({
        title: `Receive stock · ${o.order_number}`,
        size: "max-w-3xl",
        submitLabel: "Post receipt",
        html: `${fieldGrid([
            field({ name: "supplier_invoice_number", label: "Supplier invoice no.", value: o.supplier_invoice_number || "" }),
            field({ name: "note", label: "Note", value: "" }),
        ])}
        <div class="mt-6 space-y-3" id="receive-lines">
            ${open.map((i, n) => `<div class="grid grid-cols-12 items-end gap-3" data-receive-line data-item="${esc(i.id)}">
                <div class="col-span-5 text-sm"><p class="font-semibold text-slate-800">${esc(i.product_name)}</p><p class="text-xs text-slate-500">Remaining ${esc(i.remaining_quantity)}</p></div>
                <div class="col-span-3">${field({ name: `rq_${n}`, label: n === 0 ? "Quantity" : "", type: "number", step: "0.01", min: "0", value: "" })}</div>
                <div class="col-span-2">${field({ name: `rb_${n}`, label: n === 0 ? "Batch no." : "", value: "" })}</div>
                <div class="col-span-2">${field({ name: `re_${n}`, label: n === 0 ? "Expiry" : "", type: "date", value: "" })}</div>
            </div>`).join("")}
        </div>
        <p class="mt-3 text-xs text-slate-500">Leave a quantity blank to skip that line. Quantities cannot exceed the remaining amount.</p>`,
        onSubmit: async (form) => {
            const d = readForm(form);
            const lines = [];
            open.forEach((item, n) => {
                const raw = form.querySelector(`[name="rq_${n}"]`).value;
                if (raw === "" || Number(raw) === 0) return;
                const qty = toNumber(raw, `${item.product_name} quantity`, { min: 0.01 });
                if (qty > Number(item.remaining_quantity)) throw new Error(`${item.product_name}: quantity exceeds the remaining ${item.remaining_quantity}.`);
                const line = { purchase_order_item_id: item.id, quantity: qty };
                const batch = form.querySelector(`[name="rb_${n}"]`).value.trim();
                const expiry = form.querySelector(`[name="re_${n}"]`).value;
                if (batch) line.batch_number = batch;
                if (expiry) line.expiry_date = expiry;
                lines.push(line);
            });
            if (!lines.length) throw new Error("Enter a quantity for at least one line.");
            await apiJson("/api/purchasing/receipts/", {
                method: "POST",
                body: JSON.stringify({ purchase_order_id: orderId, supplier_invoice_number: d.supplier_invoice_number, note: d.note, lines }),
            });
            toast("Goods receipt posted and stock updated.", "success");
            await renderPurchaseOrder(orderId);
            return true;
        },
    });
}

async function returnForm(orderId) {
    const o = await apiJson(`/api/purchasing/purchase-orders/${orderId}/`);
    const returnable = (o.items || []).filter((i) => Number(i.received_quantity) - Number(i.returned_quantity || 0) > 0);
    if (!returnable.length) return toast("Nothing is available to return on this order.", "info");
    await openModal({
        title: `Return to supplier · ${o.order_number}`,
        size: "max-w-3xl",
        submitLabel: "Create return",
        html: `${fieldGrid([
            field({ name: "reason", label: "Reason", value: "", required: true, full: true }),
            field({ name: "supplier_credit_note", label: "Supplier credit note no.", value: "" }),
        ])}
        <div class="mt-6 space-y-3">
            ${returnable.map((i, n) => `<div class="grid grid-cols-12 items-end gap-3" data-return-line data-item="${esc(i.id)}">
                <div class="col-span-6 text-sm"><p class="font-semibold text-slate-800">${esc(i.product_name)}</p><p class="text-xs text-slate-500">Returnable ${esc(Number(i.received_quantity) - Number(i.returned_quantity || 0))}</p></div>
                <div class="col-span-3">${field({ name: `ret_${n}`, label: n === 0 ? "Quantity" : "", type: "number", step: "0.01", min: "0", value: "" })}</div>
                <div class="col-span-3">${field({ name: `retr_${n}`, label: n === 0 ? "Line reason" : "", value: "" })}</div>
            </div>`).join("")}
        </div>`,
        onSubmit: async (form) => {
            const d = readForm(form);
            const lines = [];
            returnable.forEach((item, n) => {
                const raw = form.querySelector(`[name="ret_${n}"]`).value;
                if (raw === "" || Number(raw) === 0) return;
                const max = Number(item.received_quantity) - Number(item.returned_quantity || 0);
                const qty = toNumber(raw, `${item.product_name} quantity`, { min: 0.01 });
                if (qty > max) throw new Error(`${item.product_name}: quantity exceeds the returnable ${max}.`);
                const line = { purchase_order_item_id: item.id, quantity: qty };
                const reason = form.querySelector(`[name="retr_${n}"]`).value.trim();
                if (reason) line.reason = reason;
                lines.push(line);
            });
            if (!lines.length) throw new Error("Enter a quantity for at least one line.");
            await apiJson("/api/purchasing/purchase-returns/", {
                method: "POST",
                body: JSON.stringify({
                    purchase_order_id: orderId,
                    reason: requireValue(d.reason, "A reason is required for the return."),
                    supplier_credit_note: d.supplier_credit_note,
                    lines,
                }),
            });
            toast("Return created as draft. Process it to post the credit.", "success");
            await renderPurchaseOrder(orderId);
            return true;
        },
    });
}

async function viewReceipt(id) {
    const r = await apiJson(`/api/purchasing/receipts/${id}/`);
    const lines = Array.isArray(r.lines) ? r.lines : [];
    await openModal({
        title: `Receipt ${r.receipt_number}`,
        size: "max-w-3xl",
        hideSubmit: true,
        html: `<p class="text-sm text-slate-600">${esc(r.supplier_name || "")} · ${esc(r.warehouse_name || "")} · ${esc(formatDateTime(r.received_at))} · ${esc(r.received_by_name || "")}</p>
        ${table({
            columns: [
                { label: "Product", cell: (l) => esc(l.product_name || "-") },
                { label: "Batch", cell: (l) => esc(l.batch_number || "-") },
                { label: "Received", align: "right", cell: (l) => esc(l.quantity_received) },
                { label: "Accepted", align: "right", cell: (l) => esc(l.quantity_accepted) },
                { label: "Rejected", align: "right", cell: (l) => esc(l.quantity_rejected) },
            ],
            rows: lines,
            empty: "No lines.",
        })}`,
    });
}

async function viewReturn(id) {
    const r = await apiJson(`/api/purchasing/purchase-returns/${id}/`);
    await openModal({
        title: `Return ${r.return_number}`,
        size: "max-w-lg",
        hideSubmit: true,
        html: `<dl class="grid grid-cols-3 gap-y-3 text-sm">
            <dt class="text-slate-500">Status</dt><dd class="col-span-2">${statusBadge(r.status)}</dd>
            <dt class="text-slate-500">Supplier</dt><dd class="col-span-2">${esc(r.supplier_name || "-")}</dd>
            <dt class="text-slate-500">Order</dt><dd class="col-span-2">${esc(r.purchase_order_number || "-")}</dd>
            <dt class="text-slate-500">Total</dt><dd class="col-span-2 tabular-nums">${esc(formatMoney(r.total_amount))}</dd>
            <dt class="text-slate-500">Reason</dt><dd class="col-span-2">${esc(r.reason || "-")}</dd>
            <dt class="text-slate-500">Credit note</dt><dd class="col-span-2">${esc(r.supplier_credit_note || "-")}</dd>
            <dt class="text-slate-500">Processed</dt><dd class="col-span-2">${esc(formatDateTime(r.processed_at))}</dd>
        </dl>`,
    });
}

async function transitionReturn(id, verb, message) {
    const ok = await confirmDialog({ title: verb === "process" ? "Process return?" : "Cancel return?", message, confirmLabel: verb === "process" ? "Process" : "Cancel return", danger: verb !== "process" });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(`/api/purchasing/purchase-returns/${id}/${verb}/`, { method: "POST" }), { successMessage: verb === "process" ? "Return processed." : "Return cancelled.", errorFallback: "Action failed." });
    if (result !== undefined) renderTab();
}

async function deleteRecord(path, message, afterDelete) {
    const ok = await confirmDialog({ title: "Remove?", message, confirmLabel: "Remove" });
    if (!ok) return;
    try {
        await apiJson(path, { method: "DELETE" });
        toast("Removed.", "success");
        await afterDelete();
    } catch (error) {
        toast(errorMessage(error), "error");
    }
}
