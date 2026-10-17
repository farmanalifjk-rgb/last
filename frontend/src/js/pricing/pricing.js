/**
 * Pricing and tax: price lists with their item prices, customer-group prices,
 * volume tiers, tax rates and tax exemptions.
 *
 * Route: #/pricing?tab=price-lists|group-prices|volume-tiers|tax-rates|tax-exemptions
 *        #/pricing?tab=price-lists&list=ID        (price list items)
 *
 * Endpoints used:
 *   /api/pricing/price-lists/                                  GET, POST
 *   /api/pricing/price-lists/{id}/                             GET, PATCH, DELETE
 *   /api/pricing/price-lists/{id}/items/                       GET, POST
 *   /api/pricing/price-lists/{id}/items/{item_id}/             PATCH, DELETE
 *   /api/pricing/group-prices/                                 GET, POST
 *   /api/pricing/group-prices/{id}/                            PATCH, DELETE
 *   /api/pricing/volume-tiers/                                 GET, POST
 *   /api/pricing/volume-tiers/{id}/                            PATCH, DELETE
 *   /api/pricing/customer-groups/                              GET (pickers)
 *   /api/tax/rates/                                            GET, POST
 *   /api/tax/rates/{id}/                                       GET, PATCH, DELETE
 *   /api/tax/exemptions/                                       GET, POST
 *   /api/tax/exemptions/{id}/                                  GET, PATCH, DELETE
 *   /api/products/?page_size=200                               GET (pickers)
 *   /api/categories/                                           GET (pickers)
 *   /api/customers/?page_size=200                              GET (pickers)
 */
import { createIcons, icons } from "lucide";
import { apiJson, apiList, buildQuery } from "../../services/api.js";
import {
    esc, formatDate, toast, errorMessage, openModal, confirmDialog,
    field, fieldGrid, readForm, requireValue, toNumber, dateOrNull, table, pager, tabs, statusBadge,
    pageHeader, primaryButton, actionButton, runAction, emptyStateCard,
    hashParam, setHashParam, secondaryButton,
} from "../../shared/ui.js";

const PAGE_SIZE = 10;
const TABS = [
    { id: "price-lists", label: "Price lists" },
    { id: "group-prices", label: "Group prices" },
    { id: "volume-tiers", label: "Volume tiers" },
    { id: "tax-rates", label: "Tax rates" },
    { id: "tax-exemptions", label: "Tax exemptions" },
];
const MODE_OPTIONS = [{ value: "exclusive", label: "Exclusive (added on top)" }, { value: "inclusive", label: "Inclusive (already in price)" }];
const COMPOUND_OPTIONS = [{ value: "flat", label: "Flat (additive)" }, { value: "compound", label: "Compound (cascading)" }];
const SCOPE_OPTIONS = [{ value: "customer", label: "Customer" }, { value: "product", label: "Product" }, { value: "category", label: "Category" }];

const state = {
    tab: "price-lists",
    page: 1,
    products: [],
    categories: [],
    customers: [],
    customerGroups: [],
    priceLists: [],
};

const root = () => document.getElementById("pricing-root");
const numberText = (value) => (value === null || value === undefined || value === "" ? "-" : String(value));
const productLabel = (p) => (p ? `${p.name}${p.sku ? ` (${p.sku})` : ""}` : "-");
const percentText = (rate) => (rate === null || rate === undefined || rate === "" ? "-" : `${(Number(rate) * 100).toFixed(2).replace(/\.?0+$/, "")}%`);

window.initializePricing = async function () {
    const container = root();
    if (!container) return;
    container.addEventListener("click", onClick);
    container.addEventListener("submit", (event) => event.preventDefault());
    container.addEventListener("change", onChange);
    const requested = hashParam("tab");
    state.tab = TABS.some((t) => t.id === requested) ? requested : "price-lists";
    state.page = 1;
    await loadReferenceData();
    return route();
};

async function loadReferenceData() {
    const safe = (promise) => promise.catch(() => ({ results: [] }));
    const [products, categories, customers, groups, priceLists] = await Promise.all([
        safe(apiList("/api/products/?page_size=200")),
        safe(apiList("/api/categories/")),
        safe(apiList("/api/customers/?page_size=200")),
        safe(apiList("/api/pricing/customer-groups/?page_size=200")),
        safe(apiList("/api/pricing/price-lists/?page_size=200")),
    ]);
    state.products = products.results;
    state.categories = categories.results;
    state.customers = customers.results;
    state.customerGroups = groups.results;
    state.priceLists = priceLists.results;
}

function route() {
    if (state.tab === "price-lists" && hashParam("list")) return renderPriceListItems(hashParam("list"));
    return renderTab();
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
    if (tabEl) return setHashParam("#/pricing", { tab: tabEl.dataset.tab });
    const openEl = event.target.closest("[data-open-list]");
    if (openEl) return setHashParam("#/pricing", { tab: "price-lists", list: openEl.dataset.openList });
}

function onChange() {
    // No client-side filters: every list uses server pagination only.
}

async function handleAction(action, el) {
    const id = el.dataset.id;
    switch (action) {
        case "new-price-list": return priceListForm(null);
        case "edit-price-list": return priceListForm(id);
        case "delete-price-list": return deleteRecord(`/api/pricing/price-lists/${id}/`, "Delete this price list?", "Price list deleted.", () => renderTab());
        case "new-price-item": return priceItemForm(el.dataset.list, null);
        case "edit-price-item": return priceItemForm(el.dataset.list, id);
        case "delete-price-item": return deleteRecord(`/api/pricing/price-lists/${el.dataset.list}/items/${id}/`, "Delete this price?", "Price removed.", () => renderPriceListItems(el.dataset.list));
        case "new-group-price": return groupPriceForm(null);
        case "edit-group-price": return groupPriceForm(id);
        case "delete-group-price": return deleteRecord(`/api/pricing/group-prices/${id}/`, "Delete this group price?", "Group price deleted.", () => renderTab());
        case "new-volume-tier": return volumeTierForm(null);
        case "edit-volume-tier": return volumeTierForm(id);
        case "delete-volume-tier": return deleteRecord(`/api/pricing/volume-tiers/${id}/`, "Delete this volume tier?", "Volume tier deleted.", () => renderTab());
        case "new-tax-rate": return taxRateForm(null);
        case "edit-tax-rate": return taxRateForm(id);
        case "delete-tax-rate": return deleteRecord(`/api/tax/rates/${id}/`, "Delete this tax rate?", "Tax rate deleted.", () => renderTab());
        case "new-exemption": return exemptionForm(null);
        case "edit-exemption": return exemptionForm(id);
        case "delete-exemption": return deleteRecord(`/api/tax/exemptions/${id}/`, "Delete this exemption?", "Exemption deleted.", () => renderTab());
        case "back-to-lists": return setHashParam("#/pricing", { tab: "price-lists" });
        default: return undefined;
    }
}

/* ── Shell ────────────────────────────────────────────────────────────────── */

const TAB_ACTIONS = {
    "price-lists": () => primaryButton("New price list", "new-price-list"),
    "group-prices": () => primaryButton("New group price", "new-group-price"),
    "volume-tiers": () => primaryButton("New volume tier", "new-volume-tier"),
    "tax-rates": () => primaryButton("New tax rate", "new-tax-rate"),
    "tax-exemptions": () => primaryButton("New exemption", "new-exemption"),
};

function frame(content, actions = TAB_ACTIONS[state.tab]?.() || "") {
    root().innerHTML = `${pageHeader({ title: "Pricing & tax", subtitle: "Price lists, customer-group prices, volume tiers, tax rates and tax exemptions", actions })}
    <div class="mb-6">${tabs(TABS, state.tab)}</div>${content}`;
}

async function renderTab() {
    const container = root();
    if (!container) return;
    if (!document.getElementById("pricing-body") || container.dataset.tab !== state.tab) {
        frame(`<div id="pricing-body"></div>`);
        container.dataset.tab = state.tab;
    }
    const body = document.getElementById("pricing-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        if (state.tab === "price-lists") await renderPriceLists(body);
        else if (state.tab === "group-prices") await renderGroupPrices(body);
        else if (state.tab === "volume-tiers") await renderVolumeTiers(body);
        else if (state.tab === "tax-rates") await renderTaxRates(body);
        else await renderExemptions(body);
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this list", errorMessage(error));
    }
    createIcons({ icons });
}

const paged = (data) => pager({ page: data.page, totalPages: data.total_pages, count: data.count });
const listQuery = (extra = {}) => buildQuery({ page: state.page, page_size: PAGE_SIZE, ...extra });

/* ── Price lists ──────────────────────────────────────────────────────────── */

async function renderPriceLists(body) {
    const data = await apiList(`/api/pricing/price-lists/${listQuery()}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Name", cell: (l) => `<button type="button" data-open-list="${esc(l.id)}" class="font-semibold text-violet-700 hover:underline">${esc(l.name)}</button>` },
            { label: "Currency", cell: (l) => esc(l.currency || "-") },
            { label: "Valid", cell: (l) => esc(`${l.valid_from ? formatDate(l.valid_from) : "any"} → ${l.valid_to ? formatDate(l.valid_to) : "open"}`) },
            { label: "Default", cell: (l) => (l.is_default ? "Yes" : "No") },
            { label: "Status", cell: (l) => statusBadge(l.is_active ? "active" : "inactive") },
        ],
        rows: data.results,
        empty: "No price lists yet.",
        actions: (l) => `${actionButton("Edit", "edit-price-list", { data: { id: l.id } })} ${actionButton("Delete", "delete-price-list", { tone: "danger", data: { id: l.id } })}`,
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function renderPriceListItems(listId) {
    frame(`<div id="pricing-body"></div>`, secondaryButton("Back to price lists", "back-to-lists"));
    const body = document.getElementById("pricing-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        const list = await apiJson(`/api/pricing/price-lists/${listId}/`);
        const data = await apiList(`/api/pricing/price-lists/${listId}/items/${listQuery()}`);
        body.innerHTML = `
        <div class="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span>Price list: <strong>${esc(list.name)}</strong></span>
            <span>Currency: ${esc(list.currency || "-")}</span>
            ${statusBadge(list.is_active ? "active" : "inactive")}
        </div>
        <div class="mb-4">${primaryButton("New price", "new-price-item", `data-list="${esc(listId)}"`)}</div>
        ${table({
            columns: [
                { label: "Product", cell: (i) => esc(i.product_name || "-") },
                { label: "Price", align: "right", cell: (i) => esc(numberText(i.price)) },
                { label: "Minimum quantity", align: "right", cell: (i) => esc(numberText(i.min_quantity)) },
            ],
            rows: data.results,
            empty: "No prices in this list yet.",
            actions: (i) => `${actionButton("Edit", "edit-price-item", { data: { id: i.id, list: listId } })} ${actionButton("Delete", "delete-price-item", { tone: "danger", data: { id: i.id, list: listId } })}`,
        })}<div class="mt-4">${paged(data)}</div>`;
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this price list", errorMessage(error));
    }
    createIcons({ icons });
}

async function priceListForm(id) {
    let list = {};
    if (id) {
        try { list = await apiJson(`/api/pricing/price-lists/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    await openModal({
        title: id ? "Edit price list" : "New price list",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create price list",
        html: fieldGrid([
            field({ name: "name", label: "Name", value: list.name || "", required: true, full: true }),
            field({ name: "currency", label: "Currency code", value: list.currency || "", required: true, help: "The code shown on prices, e.g. the store currency." }),
            field({ name: "is_default", label: "Default list", type: "checkbox", value: list.is_default ?? false }),
            field({ name: "valid_from", label: "Valid from", type: "date", value: list.valid_from || "" }),
            field({ name: "valid_to", label: "Valid to", type: "date", value: list.valid_to || "" }),
            field({ name: "is_active", label: "Active", type: "checkbox", value: list.is_active ?? true, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = {
                name: requireValue(d.name, "Name is required."),
                currency: requireValue(d.currency, "Currency code is required.").toUpperCase(),
                is_default: d.is_default,
                is_active: d.is_active,
                valid_from: dateOrNull(d.valid_from),
                valid_to: dateOrNull(d.valid_to),
            };
            if (payload.valid_from && payload.valid_to && payload.valid_to < payload.valid_from) throw new Error("Valid to must be after valid from.");
            await apiJson(id ? `/api/pricing/price-lists/${id}/` : "/api/pricing/price-lists/", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Price list updated." : "Price list created.", "success");
            state.priceLists = (await apiList("/api/pricing/price-lists/?page_size=200")).results;
            await renderTab();
            return true;
        },
    });
}

async function priceItemForm(listId, id) {
    let item = {};
    if (id) {
        try { item = await apiJson(`/api/pricing/price-lists/${listId}/items/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    if (!state.products.length) return toast("Add a product before setting a price.", "error");
    await openModal({
        title: id ? "Edit price" : "New price",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Add price",
        html: fieldGrid([
            field({ name: "product", label: "Product", type: "select", options: state.products.map((p) => ({ value: p.id, label: productLabel(p) })), value: item.product ?? state.products[0].id, required: true, full: true }),
            field({ name: "price", label: "Price", type: "number", step: "0.01", min: 0, value: item.price ?? "", required: true }),
            field({ name: "min_quantity", label: "Minimum quantity", type: "number", step: "any", min: 0, value: item.min_quantity ?? 1 }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = {
                product: toNumber(d.product, "Product", { min: 1 }),
                price: toNumber(d.price, "Price", { min: 0 }),
                min_quantity: toNumber(d.min_quantity, "Minimum quantity", { min: 0 }),
            };
            await apiJson(id ? `/api/pricing/price-lists/${listId}/items/${id}/` : `/api/pricing/price-lists/${listId}/items/`, { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Price updated." : "Price added.", "success");
            await renderPriceListItems(listId);
            return true;
        },
    });
}

/* ── Customer-group prices ────────────────────────────────────────────────── */

async function renderGroupPrices(body) {
    const data = await apiList(`/api/pricing/group-prices/${listQuery()}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Customer group", cell: (g) => esc(state.customerGroups.find((x) => String(x.id) === String(g.customer_group))?.name || `#${g.customer_group}`) },
            { label: "Product", cell: (g) => esc(g.product_name || "-") },
            { label: "Price", align: "right", cell: (g) => esc(numberText(g.price)) },
        ],
        rows: data.results,
        empty: "No customer-group prices yet.",
        actions: (g) => `${actionButton("Edit", "edit-group-price", { data: { id: g.id } })} ${actionButton("Delete", "delete-group-price", { tone: "danger", data: { id: g.id } })}`,
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function groupPriceForm(id) {
    let row = {};
    if (id) {
        try { row = await apiJson(`/api/pricing/group-prices/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    if (!state.customerGroups.length) return toast("Create a customer group first (Customers > Groups).", "error");
    if (!state.products.length) return toast("Add a product before setting a price.", "error");
    await openModal({
        title: id ? "Edit group price" : "New group price",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create group price",
        html: fieldGrid([
            field({ name: "customer_group", label: "Customer group", type: "select", options: state.customerGroups.map((g) => ({ value: g.id, label: g.name })), value: row.customer_group ?? state.customerGroups[0].id, required: true, full: true }),
            field({ name: "product", label: "Product", type: "select", options: state.products.map((p) => ({ value: p.id, label: productLabel(p) })), value: row.product ?? state.products[0].id, required: true, full: true }),
            field({ name: "price", label: "Price", type: "number", step: "0.01", min: 0, value: row.price ?? "", required: true, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = {
                customer_group: toNumber(d.customer_group, "Customer group", { min: 1 }),
                product: toNumber(d.product, "Product", { min: 1 }),
                price: toNumber(d.price, "Price", { min: 0 }),
            };
            await apiJson(id ? `/api/pricing/group-prices/${id}/` : "/api/pricing/group-prices/", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Group price updated." : "Group price created.", "success");
            await renderTab();
            return true;
        },
    });
}

/* ── Volume tiers ─────────────────────────────────────────────────────────── */

async function renderVolumeTiers(body) {
    const data = await apiList(`/api/pricing/volume-tiers/${listQuery()}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Product", cell: (t) => esc(t.product_name || `#${t.product}`) },
            { label: "From quantity", align: "right", cell: (t) => esc(numberText(t.min_quantity)) },
            { label: "Unit price", align: "right", cell: (t) => esc(numberText(t.unit_price)) },
        ],
        rows: data.results,
        empty: "No volume tiers yet.",
        actions: (t) => `${actionButton("Edit", "edit-volume-tier", { data: { id: t.id } })} ${actionButton("Delete", "delete-volume-tier", { tone: "danger", data: { id: t.id } })}`,
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function volumeTierForm(id) {
    let row = {};
    if (id) {
        try { row = await apiJson(`/api/pricing/volume-tiers/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    if (!state.products.length) return toast("Add a product before setting a tier.", "error");
    await openModal({
        title: id ? "Edit volume tier" : "New volume tier",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create tier",
        html: fieldGrid([
            field({ name: "product", label: "Product", type: "select", options: state.products.map((p) => ({ value: p.id, label: productLabel(p) })), value: row.product ?? state.products[0].id, required: true, full: true }),
            field({ name: "min_quantity", label: "From quantity", type: "number", step: "any", min: 0, value: row.min_quantity ?? "", required: true }),
            field({ name: "unit_price", label: "Unit price", type: "number", step: "0.01", min: 0, value: row.unit_price ?? "", required: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = {
                product: toNumber(d.product, "Product", { min: 1 }),
                min_quantity: toNumber(d.min_quantity, "From quantity", { min: 0 }),
                unit_price: toNumber(d.unit_price, "Unit price", { min: 0 }),
            };
            await apiJson(id ? `/api/pricing/volume-tiers/${id}/` : "/api/pricing/volume-tiers/", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Volume tier updated." : "Volume tier created.", "success");
            await renderTab();
            return true;
        },
    });
}

/* ── Tax rates ────────────────────────────────────────────────────────────── */

async function renderTaxRates(body) {
    const data = await apiList(`/api/tax/rates/${listQuery()}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Name", cell: (r) => esc(r.name || "-") },
            { label: "Code", cell: (r) => `<span class="font-mono text-xs">${esc(r.code || "-")}</span>` },
            { label: "Rate", align: "right", cell: (r) => esc(percentText(r.rate)) },
            { label: "Mode", cell: (r) => esc(r.mode === "inclusive" ? "Inclusive" : "Exclusive") },
            { label: "Applies", cell: (r) => esc(r.applies_to_all ? "All products" : (r.product ? "Product" : r.category ? "Category" : "Specific")) },
            { label: "Priority", align: "right", cell: (r) => esc(numberText(r.priority)) },
            { label: "Status", cell: (r) => statusBadge(r.is_active ? "active" : "inactive") },
        ],
        rows: data.results,
        empty: "No tax rates yet.",
        actions: (r) => `${actionButton("Edit", "edit-tax-rate", { data: { id: r.id } })} ${actionButton("Delete", "delete-tax-rate", { tone: "danger", data: { id: r.id } })}`,
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function taxRateForm(id) {
    let rate = {};
    if (id) {
        try { rate = await apiJson(`/api/tax/rates/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    const categoryOptions = [{ value: "", label: "None" }, ...state.categories.map((c) => ({ value: c.id, label: c.name }))];
    const productOptions = [{ value: "", label: "None" }, ...state.products.map((p) => ({ value: p.id, label: productLabel(p) }))];
    await openModal({
        title: id ? "Edit tax rate" : "New tax rate",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create tax rate",
        html: fieldGrid([
            field({ name: "name", label: "Name", value: rate.name || "", required: true }),
            field({ name: "code", label: "Code", value: rate.code || "", required: true, help: "Unique per business, e.g. GST17." }),
            field({ name: "rate_percent", label: "Rate (%)", type: "number", step: "0.01", min: 0, value: rate.rate !== undefined ? String(Number(rate.rate) * 100) : "", required: true, help: "Enter 17 for 17%." }),
            field({ name: "priority", label: "Priority", type: "number", step: "1", min: 0, value: rate.priority ?? 0, help: "Lower numbers apply first." }),
            field({ name: "mode", label: "Mode", type: "select", options: MODE_OPTIONS, value: rate.mode || "exclusive", full: true }),
            field({ name: "compound_style", label: "Combination", type: "select", options: COMPOUND_OPTIONS, value: rate.compound_style || "flat", full: true }),
            field({ name: "applies_to_all", label: "Applies to all products", type: "checkbox", value: rate.applies_to_all ?? true, full: true }),
            field({ name: "category", label: "Category (when not all products)", type: "select", options: categoryOptions, value: rate.category ?? "", full: true }),
            field({ name: "product", label: "Product (when not all products)", type: "select", options: productOptions, value: rate.product ?? "", full: true }),
            field({ name: "is_active", label: "Active", type: "checkbox", value: rate.is_active ?? true, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const percent = toNumber(d.rate_percent, "Rate", { min: 0 });
            if (percent > 100) throw new Error("Rate must be 100% or less.");
            const payload = {
                name: requireValue(d.name, "Name is required."),
                code: requireValue(d.code, "Code is required.").toUpperCase(),
                rate: Math.round(percent * 100) / 10000,
                mode: d.mode,
                compound_style: d.compound_style,
                priority: toNumber(d.priority || "0", "Priority", { min: 0 }),
                applies_to_all: d.applies_to_all,
                category: d.category ? toNumber(d.category, "Category", { min: 1 }) : null,
                product: d.product ? toNumber(d.product, "Product", { min: 1 }) : null,
                is_active: d.is_active,
            };
            await apiJson(id ? `/api/tax/rates/${id}/` : "/api/tax/rates/", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Tax rate updated." : "Tax rate created.", "success");
            await renderTab();
            return true;
        },
    });
}

/* ── Tax exemptions ───────────────────────────────────────────────────────── */

async function renderExemptions(body) {
    const data = await apiList(`/api/tax/exemptions/${listQuery()}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Scope", cell: (e) => esc(e.scope || "-") },
            { label: "Customer", cell: (e) => esc(e.customer_name || (e.customer ? `#${e.customer}` : "-")) },
            { label: "Product / category", cell: (e) => esc(e.product_name || e.category_name || (e.product ? `#${e.product}` : e.category ? `#${e.category}` : "-")) },
            { label: "Tax rate", cell: (e) => esc(e.tax_rate_name || (e.tax_rate ? `#${e.tax_rate}` : "-")) },
            { label: "Certificate", cell: (e) => esc(e.certificate_number || "-") },
            { label: "Status", cell: (e) => statusBadge(e.is_active ? "active" : "inactive") },
        ],
        rows: data.results,
        empty: "No tax exemptions yet.",
        actions: (e) => `${actionButton("Edit", "edit-exemption", { data: { id: e.id } })} ${actionButton("Delete", "delete-exemption", { tone: "danger", data: { id: e.id } })}`,
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function exemptionForm(id) {
    let row = {};
    if (id) {
        try { row = await apiJson(`/api/tax/exemptions/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    let rates = [];
    try { rates = (await apiList("/api/tax/rates/?page_size=200")).results; } catch { rates = []; }
    if (!rates.length) return toast("Create a tax rate first.", "error");
    const customerOptions = [{ value: "", label: "None" }, ...state.customers.map((c) => ({ value: c.id, label: c.name }))];
    const productOptions = [{ value: "", label: "None" }, ...state.products.map((p) => ({ value: p.id, label: productLabel(p) }))];
    const categoryOptions = [{ value: "", label: "None" }, ...state.categories.map((c) => ({ value: c.id, label: c.name }))];
    await openModal({
        title: id ? "Edit tax exemption" : "New tax exemption",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create exemption",
        html: fieldGrid([
            field({ name: "scope", label: "Scope", type: "select", options: SCOPE_OPTIONS, value: row.scope || "customer", full: true, help: "Pick the target that matches the scope: customer, product or category." }),
            field({ name: "customer", label: "Customer", type: "select", options: customerOptions, value: row.customer ?? "" }),
            field({ name: "tax_rate", label: "Tax rate", type: "select", options: rates.map((r) => ({ value: r.id, label: `${r.name} (${percentText(r.rate)})` })), value: row.tax_rate ?? rates[0].id, required: true }),
            field({ name: "product", label: "Product", type: "select", options: productOptions, value: row.product ?? "", full: true }),
            field({ name: "category", label: "Category", type: "select", options: categoryOptions, value: row.category ?? "", full: true }),
            field({ name: "reason", label: "Reason", value: row.reason || "" }),
            field({ name: "certificate_number", label: "Certificate number", value: row.certificate_number || "" }),
            field({ name: "is_active", label: "Active", type: "checkbox", value: row.is_active ?? true, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const scope = d.scope;
            const payload = {
                scope,
                customer: scope === "customer" && d.customer ? toNumber(d.customer, "Customer", { min: 1 }) : null,
                product: scope === "product" && d.product ? toNumber(d.product, "Product", { min: 1 }) : null,
                category: scope === "category" && d.category ? toNumber(d.category, "Category", { min: 1 }) : null,
                tax_rate: toNumber(d.tax_rate, "Tax rate", { min: 1 }),
                reason: d.reason || "",
                certificate_number: d.certificate_number || "",
                is_active: d.is_active,
            };
            if (scope === "customer" && !payload.customer) throw new Error("Choose the customer this exemption applies to.");
            if (scope === "product" && !payload.product) throw new Error("Choose the product this exemption applies to.");
            if (scope === "category" && !payload.category) throw new Error("Choose the category this exemption applies to.");
            await apiJson(id ? `/api/tax/exemptions/${id}/` : "/api/tax/exemptions/", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
            toast(id ? "Exemption updated." : "Exemption created.", "success");
            await renderTab();
            return true;
        },
    });
}

/* ── Shared delete ────────────────────────────────────────────────────────── */

async function deleteRecord(url, question, success, after) {
    const ok = await confirmDialog({ title: question, message: "This cannot be undone.", confirmLabel: "Delete" });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(url, { method: "DELETE" }), { successMessage: success, errorFallback: "Could not delete this record." });
    if (result === undefined) return;
    if (after) await after();
}
