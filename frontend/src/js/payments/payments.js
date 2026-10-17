/**
 * Payments and credit: gift cards (issue, detail, top up, disable), store
 * credit (balance, issue), the settled tender register (read only), cash
 * reconciliation (create, detail, close) and refund settlements (store credit).
 *
 * Route: #/payments?tab=gift-cards|store-credit|registers|reconciliations|refunds
 *        #/payments?tab=gift-cards&card=ID
 *        #/payments?tab=store-credit&customer=ID
 *        #/payments?tab=registers&tender=ID
 *        #/payments?tab=reconciliations&reconciliation=ID
 *
 * Endpoints used:
 *   /api/payments/gift-cards/                              GET, POST
 *   /api/payments/gift-cards/{id}/                         GET
 *   /api/payments/gift-cards/{id}/topup/                   POST
 *   /api/payments/gift-cards/{id}/disable/                 POST
 *   /api/payments/store-credit/{customer_id}/              GET
 *   /api/payments/store-credit/{customer_id}/issue/        POST
 *   /api/payments/register/                                GET
 *   /api/payments/register/{id}/                           GET
 *   /api/payments/reconciliations/                         GET, POST
 *   /api/payments/reconciliations/{id}/                    GET
 *   /api/payments/reconciliations/{id}/close/              POST
 *   /api/payments/refund-settlements/                      GET
 *   /api/payments/refunds/{refund_id}/store-credit/        POST
 *   /api/pos/sessions/active/                              GET (session picker)
 *   /api/customers/?page_size=200                          GET (pickers)
 */
import { createIcons, icons } from "lucide";
import { apiJson, apiList, buildQuery } from "../../services/api.js";
import {
    esc, formatDateTime, formatDate, toast, errorMessage, openModal, confirmDialog,
    field, fieldGrid, readForm, toNumber, dateOrNull, table, pager, tabs, statusBadge,
    pageHeader, primaryButton, actionButton, runAction, emptyStateCard,
    hashParam, setHashParam, selectInput, searchInput, secondaryButton, debounce,
} from "../../shared/ui.js";

const PAGE_SIZE = 10;
const TABS = [
    { id: "gift-cards", label: "Gift cards" },
    { id: "store-credit", label: "Store credit" },
    { id: "registers", label: "Tender register" },
    { id: "reconciliations", label: "Cash reconciliation" },
    { id: "refunds", label: "Refund credit" },
];
const TENDERS = [
    ["cash", "Cash"], ["card", "Card"], ["bank", "Bank"], ["gift_card", "Gift card"],
    ["store_credit", "Store credit"], ["loyalty", "Loyalty points"], ["wallet", "Wallet"],
];

const state = {
    tab: "gift-cards",
    page: 1,
    active: "",
    search: "",
    tender: "",
    status: "",
    customers: [],
    issuedCode: null,
};

const root = () => document.getElementById("payments-root");
const numberText = (value) => (value === null || value === undefined || value === "" ? "-" : String(value));
const moneyText = (value, currency = "") => (value === null || value === undefined || value === "" ? "-" : `${value}${currency ? ` ${currency}` : ""}`);

window.initializePayments = async function () {
    const container = root();
    if (!container) return;
    container.addEventListener("click", onClick);
    container.addEventListener("submit", (event) => event.preventDefault());
    container.addEventListener("change", onChange);
    container.addEventListener("input", onInput);
    const requested = hashParam("tab");
    state.tab = TABS.some((t) => t.id === requested) ? requested : "gift-cards";
    state.page = 1;
    state.active = "";
    state.search = "";
    state.tender = "";
    state.status = "";
    try { state.customers = (await apiList("/api/customers/?page_size=200")).results; } catch { state.customers = []; }
    return route();
};

function route() {
    if (state.tab === "gift-cards" && hashParam("card")) return renderGiftCard(hashParam("card"));
    if (state.tab === "store-credit" && hashParam("customer")) return renderStoreCredit(hashParam("customer"));
    if (state.tab === "registers" && hashParam("tender")) return renderRegisterEntry(hashParam("tender"));
    if (state.tab === "reconciliations" && hashParam("reconciliation")) return renderReconciliation(hashParam("reconciliation"));
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
    if (tabEl) return setHashParam("#/payments", { tab: tabEl.dataset.tab });
    const openEl = event.target.closest("[data-open]");
    if (openEl) return setHashParam("#/payments", { tab: state.tab, [openEl.dataset.param]: openEl.dataset.open });
}

function onChange(event) {
    const id = event.target.id;
    if (id === "pay-active") { state.active = event.target.value; state.page = 1; return renderTab(); }
    if (id === "pay-tender") { state.tender = event.target.value; state.page = 1; return renderTab(); }
    if (id === "pay-status") { state.status = event.target.value; state.page = 1; return renderTab(); }
    if (id === "pay-customer") { return setHashParam("#/payments", { tab: "store-credit", customer: event.target.value }); }
}

const runSearch = debounce((value) => {
    state.search = value;
    state.page = 1;
    renderTab();
}, 350);

function onInput(event) {
    if (event.target.id !== "pay-search") return;
    runSearch(event.target.value.trim());
}

async function handleAction(action, el) {
    const id = el.dataset.id;
    switch (action) {
        case "issue-gift-card": return issueGiftCardForm();
        case "topup-gift-card": return topupForm(id);
        case "disable-gift-card": return disableGiftCard(id);
        case "issue-store-credit": return issueStoreCreditForm(el.dataset.customer);
        case "new-reconciliation": return reconciliationForm();
        case "close-reconciliation": return closeReconciliation(id);
        case "refund-store-credit": return refundStoreCreditForm(id, el.dataset.order);
        case "back-to-tab": return setHashParam("#/payments", { tab: state.tab });
        case "dismiss-issued-code": state.issuedCode = null; return renderGiftCard(hashParam("card"));
        default: return undefined;
    }
}

/* ── Shell ────────────────────────────────────────────────────────────────── */

const TAB_ACTIONS = {
    "gift-cards": () => primaryButton("Issue gift card", "issue-gift-card"),
    reconciliations: () => primaryButton("New reconciliation", "new-reconciliation"),
};

function frame(content) {
    const actions = TAB_ACTIONS[state.tab] ? TAB_ACTIONS[state.tab]() : "";
    root().innerHTML = `${pageHeader({ title: "Payments & credit", subtitle: "Gift cards, store credit, tender register, cash reconciliation and refund credit", actions })}
    <div class="mb-6">${tabs(TABS, state.tab)}</div>${content}`;
}

function filterBar() {
    if (state.tab === "gift-cards") {
        return selectInput("pay-active", [
            { value: "", label: "All gift cards" }, { value: "true", label: "Active" }, { value: "false", label: "Disabled" },
        ], state.active) + searchInput("pay-search", "Search by code").replace("<input ", `<input value="${esc(state.search)}" `);
    }
    if (state.tab === "registers") {
        return selectInput("pay-tender", [{ value: "", label: "All tenders" }, ...TENDERS.map(([v, l]) => ({ value: v, label: l }))], state.tender)
            + searchInput("pay-search", "Search by order or reference").replace("<input ", `<input value="${esc(state.search)}" `);
    }
    if (state.tab === "reconciliations") {
        return selectInput("pay-status", [{ value: "", label: "All statuses" }, { value: "open", label: "Open" }, { value: "closed", label: "Closed" }], state.status);
    }
    if (state.tab === "store-credit") {
        const options = [{ value: "", label: "Choose a customer" }, ...state.customers.map((c) => ({ value: c.id, label: c.name }))];
        return selectInput("pay-customer", options, "");
    }
    return "";
}

async function renderTab() {
    const container = root();
    if (!container) return;
    if (!document.getElementById("payments-body") || container.dataset.tab !== state.tab) {
        frame(`<div class="mb-5 flex flex-wrap items-center gap-3">${filterBar()}</div><div id="payments-body"></div>`);
        container.dataset.tab = state.tab;
    }
    const body = document.getElementById("payments-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        if (state.tab === "gift-cards") await renderGiftCards(body);
        else if (state.tab === "store-credit") await renderStoreCreditPicker(body);
        else if (state.tab === "registers") await renderRegister(body);
        else if (state.tab === "reconciliations") await renderReconciliations(body);
        else await renderRefunds(body);
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this list", errorMessage(error));
    }
    createIcons({ icons });
}

const paged = (data) => pager({ page: data.page, totalPages: data.total_pages, count: data.count });
const customerName = (id) => state.customers.find((c) => String(c.id) === String(id))?.name || "-";

/* ── Gift cards ───────────────────────────────────────────────────────────── */

async function renderGiftCards(body) {
    const query = buildQuery({ active: state.active, search: state.search, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/payments/gift-cards/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "Card", cell: (c) => `<button type="button" data-open="${esc(c.id)}" data-param="card" class="font-mono text-xs font-semibold text-violet-700 hover:underline">${esc(c.code_masked || `#${c.id}`)}</button>` },
            { label: "Balance", align: "right", cell: (c) => esc(moneyText(c.balance, c.currency)) },
            { label: "Initial", align: "right", cell: (c) => esc(moneyText(c.initial_balance, c.currency)) },
            { label: "Customer", cell: (c) => esc(c.customer_name || "-") },
            { label: "Expires", cell: (c) => esc(c.expires_at ? formatDate(c.expires_at) : "-") },
            { label: "Status", cell: (c) => statusBadge(c.is_active ? "active" : "inactive") },
        ],
        rows: data.results,
        empty: "No gift cards found.",
    })}<div class="mt-4">${paged(data)}</div>`;
}

async function renderGiftCard(id) {
    frame(`<div id="payments-body"></div>`);
    const body = document.getElementById("payments-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        const card = await apiJson(`/api/payments/gift-cards/${id}/`);
        const banner = state.issuedCode
            ? `<div class="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                <div class="font-semibold">Gift card code (shown only once)</div>
                <div class="mt-1 font-mono text-base">${esc(state.issuedCode)}</div>
                <div class="mt-2 text-xs">Record this code now. It cannot be shown again.</div>
                <button type="button" data-action="dismiss-issued-code" class="mt-3 h-9 rounded-lg border border-amber-300 px-3 text-xs font-semibold">Done</button>
               </div>`
            : "";
        body.innerHTML = `${banner}
        <div class="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span>Code: <span class="font-mono">${esc(card.code_masked || "-")}</span></span>
            <span>Balance: <strong>${esc(moneyText(card.balance, card.currency))}</strong></span>
            <span>Initial: ${esc(moneyText(card.initial_balance, card.currency))}</span>
            <span>Customer: ${esc(card.customer_name || "-")}</span>
            <span>Expires: ${esc(card.expires_at ? formatDate(card.expires_at) : "never")}</span>
            ${statusBadge(card.is_active ? "active" : "inactive")}
        </div>
        <div class="mb-4 flex flex-wrap gap-3">
            ${secondaryButton("Back to gift cards", "back-to-tab")}
            ${card.is_active ? primaryButton("Top up", "topup-gift-card", `data-id="${esc(card.id)}"`) : ""}
            ${card.is_active ? `<button type="button" data-action="disable-gift-card" data-id="${esc(card.id)}" class="h-11 rounded-xl border border-rose-200 px-5 text-sm font-semibold text-rose-600 hover:bg-rose-50">Disable</button>` : ""}
        </div>
        ${table({
            columns: [
                { label: "When", cell: (t) => esc(formatDateTime(t.created_at)) },
                { label: "Kind", cell: (t) => esc(t.kind || "-") },
                { label: "Amount", align: "right", cell: (t) => esc(numberText(t.amount)) },
                { label: "Order", cell: (t) => esc(t.order_number || "-") },
                { label: "Note", cell: (t) => esc(t.note || "") },
            ],
            rows: Array.isArray(card.transactions) ? card.transactions : [],
            empty: "No transactions yet.",
        })}`;
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this gift card", errorMessage(error));
    }
    createIcons({ icons });
}

async function issueGiftCardForm() {
    const customerOptions = [{ value: "", label: "No customer" }, ...state.customers.map((c) => ({ value: c.id, label: c.name }))];
    await openModal({
        title: "Issue gift card",
        size: "max-w-2xl",
        submitLabel: "Issue card",
        html: fieldGrid([
            field({ name: "initial_balance", label: "Initial balance", type: "number", step: "0.01", min: 0.01, value: "", required: true }),
            field({ name: "expires_at", label: "Expires on", type: "date", value: "" }),
            field({ name: "customer", label: "Customer", type: "select", options: customerOptions, value: "", full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const amount = toNumber(d.initial_balance, "Initial balance", { min: 0.01 });
            if (amount <= 0) throw new Error("Initial balance must be greater than zero.");
            const payload = {
                initial_balance: amount,
                customer_id: d.customer ? toNumber(d.customer, "Customer", { min: 1 }) : null,
                expires_at: dateOrNull(d.expires_at),
            };
            const created = await apiJson("/api/payments/gift-cards/", { method: "POST", body: JSON.stringify(payload) });
            state.issuedCode = created.issued_code || null;
            toast("Gift card issued.", "success");
            return setHashParam("#/payments", { tab: "gift-cards", card: created.id });
        },
    });
}

async function topupForm(id) {
    await openModal({
        title: "Top up gift card",
        submitLabel: "Add balance",
        html: fieldGrid([field({ name: "amount", label: "Amount", type: "number", step: "0.01", min: 0.01, value: "", required: true, full: true })]),
        onSubmit: async (form) => {
            const amount = toNumber(readForm(form).amount, "Amount", { min: 0.01 });
            if (amount <= 0) throw new Error("Amount must be greater than zero.");
            await apiJson(`/api/payments/gift-cards/${id}/topup/`, { method: "POST", body: JSON.stringify({ amount }) });
            toast("Gift card topped up.", "success");
            await renderGiftCard(id);
            return true;
        },
    });
}

async function disableGiftCard(id) {
    const ok = await confirmDialog({
        title: "Disable this gift card?",
        message: "A disabled card cannot be used for payment. Its remaining balance is kept on record.",
        confirmLabel: "Disable",
    });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(`/api/payments/gift-cards/${id}/disable/`, { method: "POST" }), { successMessage: "Gift card disabled.", errorFallback: "Could not disable the gift card." });
    if (result === undefined) return;
    await renderGiftCard(id);
}

/* ── Store credit ─────────────────────────────────────────────────────────── */

async function renderStoreCreditPicker(body) {
    body.innerHTML = emptyStateCard("Choose a customer", "Select a customer above to see their store credit balance and history.");
}

async function renderStoreCredit(customerId) {
    frame(`<div class="mb-5 flex flex-wrap items-center gap-3">${filterBar()}</div><div id="payments-body"></div>`);
    const container = root();
    container.dataset.tab = state.tab;
    const select = document.getElementById("pay-customer");
    if (select) select.value = customerId;
    const body = document.getElementById("payments-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        const credit = await apiJson(`/api/payments/store-credit/${customerId}/`);
        body.innerHTML = `
        <div class="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span>Customer: <strong>${esc(customerName(customerId))}</strong></span>
            <span>Balance: <strong>${esc(moneyText(credit.balance, credit.currency))}</strong></span>
        </div>
        <div class="mb-4">${primaryButton("Issue store credit", "issue-store-credit", `data-customer="${esc(customerId)}"`)}</div>
        ${table({
            columns: [
                { label: "When", cell: (t) => esc(formatDateTime(t.created_at)) },
                { label: "Kind", cell: (t) => esc(t.kind || "-") },
                { label: "Amount", align: "right", cell: (t) => esc(numberText(t.amount)) },
                { label: "Order", cell: (t) => esc(t.order_number || "-") },
                { label: "Note", cell: (t) => esc(t.note || "") },
            ],
            rows: Array.isArray(credit.transactions) ? credit.transactions : [],
            empty: "No store credit activity for this customer.",
        })}`;
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load store credit", errorMessage(error));
    }
    createIcons({ icons });
}

async function issueStoreCreditForm(customerId) {
    await openModal({
        title: "Issue store credit",
        submitLabel: "Issue credit",
        html: fieldGrid([
            field({ name: "amount", label: "Amount", type: "number", step: "0.01", min: 0.01, value: "", required: true, full: true }),
            field({ name: "note", label: "Note", value: "", full: true, placeholder: "Reason for the credit" }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const amount = toNumber(d.amount, "Amount", { min: 0.01 });
            if (amount <= 0) throw new Error("Amount must be greater than zero.");
            await apiJson(`/api/payments/store-credit/${customerId}/issue/`, { method: "POST", body: JSON.stringify({ amount, note: d.note || "" }) });
            toast("Store credit issued.", "success");
            await renderStoreCredit(customerId);
            return true;
        },
    });
}

/* ── Tender register (read only) ──────────────────────────────────────────── */

async function renderRegister(body) {
    const query = buildQuery({ tender_type: state.tender, search: state.search, page: state.page, page_size: PAGE_SIZE });
    const data = await apiList(`/api/payments/register/${query}`);
    body.innerHTML = `${table({
        columns: [
            { label: "When", cell: (r) => esc(formatDateTime(r.created_at)) },
            { label: "Order", cell: (r) => `<button type="button" data-open="${esc(r.id)}" data-param="tender" class="font-mono text-xs font-semibold text-violet-700 hover:underline">${esc(r.order_number || `#${r.id}`)}</button>` },
            { label: "Tender", cell: (r) => esc(r.tender_type || "-") },
            { label: "Amount", align: "right", cell: (r) => esc(moneyText(r.amount, r.currency)) },
            { label: "Reference", cell: (r) => esc(r.reference_masked || "-") },
            { label: "Customer", cell: (r) => esc(r.customer_name || "-") },
            { label: "Settled", cell: (r) => statusBadge(r.is_settled ? "completed" : "pending") },
        ],
        rows: data.results,
        empty: "No settled tenders found.",
    })}<div class="mt-4">${paged(data)}</div>`;
}

const REGISTER_FIELDS = [
    ["order_number", "Order"], ["tender_type", "Tender"], ["amount", "Amount"], ["currency", "Currency"],
    ["reference_masked", "Reference"], ["status", "Status"], ["is_settled", "Settled"],
    ["created_at", "Created"], ["created_by", "Recorded by"], ["customer_name", "Customer"],
];

async function renderRegisterEntry(id) {
    frame(`<div id="payments-body"></div>`);
    const body = document.getElementById("payments-body");
    try {
        const r = await apiJson(`/api/payments/register/${id}/`);
        const rows = REGISTER_FIELDS.filter(([key]) => r[key] !== undefined).map(([key, label]) => {
            const value = key === "created_at" ? formatDateTime(r[key]) : (typeof r[key] === "boolean" ? (r[key] ? "Yes" : "No") : r[key]);
            return `<div><dt class="text-xs font-semibold uppercase tracking-wide text-slate-500">${esc(label)}</dt><dd class="mt-1 text-sm text-slate-800">${esc(value ?? "-")}</dd></div>`;
        });
        body.innerHTML = `<div class="mb-4">${secondaryButton("Back to register", "back-to-tab")}</div>
            <dl class="grid grid-cols-2 gap-x-6 gap-y-4 rounded-xl border border-slate-200 bg-white p-6">${rows.join("")}</dl>`;
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this tender", errorMessage(error));
    }
    createIcons({ icons });
}

/* ── Cash reconciliation ──────────────────────────────────────────────────── */

async function renderReconciliations(body) {
    const query = buildQuery({ status: state.status });
    const rows = (await apiList(`/api/payments/reconciliations/${query}`)).results;
    const start = (state.page - 1) * PAGE_SIZE;
    const pageRows = rows.slice(start, start + PAGE_SIZE);
    const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    body.innerHTML = `${table({
        columns: [
            { label: "Reconciliation", cell: (r) => `<button type="button" data-open="${esc(r.id)}" data-param="reconciliation" class="font-mono text-xs font-semibold text-violet-700 hover:underline">#${esc(r.id)}</button>` },
            { label: "Session", align: "right", cell: (r) => esc(numberText(r.session_id)) },
            { label: "Expected", align: "right", cell: (r) => esc(numberText(r.expected_total)) },
            { label: "Counted", align: "right", cell: (r) => esc(numberText(r.counted_total)) },
            { label: "Variance", align: "right", cell: (r) => esc(numberText(r.variance)) },
            { label: "Created", cell: (r) => esc(formatDateTime(r.created_at)) },
            { label: "Status", cell: (r) => statusBadge(r.status) },
        ],
        rows: pageRows,
        empty: "No reconciliations yet.",
    })}<div class="mt-4">${pager({ page: state.page, totalPages, count: rows.length })}</div>`;
}

async function renderReconciliation(id) {
    frame(`<div id="payments-body"></div>`);
    const body = document.getElementById("payments-body");
    body.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        const rec = await apiJson(`/api/payments/reconciliations/${id}/`);
        const open = rec.status !== "closed";
        body.innerHTML = `
        <div class="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span>Session: <strong>${esc(numberText(rec.session_id))}</strong></span>
            <span>Expected: ${esc(numberText(rec.expected_total))}</span>
            <span>Counted: ${esc(numberText(rec.counted_total))}</span>
            <span>Variance: ${esc(numberText(rec.variance))}</span>
            ${statusBadge(rec.status)}
        </div>
        <div class="mb-4 flex flex-wrap gap-3">
            ${secondaryButton("Back to reconciliations", "back-to-tab")}
            ${open ? primaryButton("Close reconciliation", "close-reconciliation", `data-id="${esc(rec.id)}"`) : ""}
        </div>
        ${table({
            columns: [
                { label: "Tender", cell: (l) => esc(TENDERS.find(([v]) => v === l.tender_type)?.[1] || l.tender_type || "-") },
                { label: "Expected", align: "right", cell: (l) => esc(numberText(l.expected_amount)) },
                { label: "Counted", align: "right", cell: (l) => esc(numberText(l.counted_amount)) },
                { label: "Variance", align: "right", cell: (l) => esc(numberText(l.variance)) },
                { label: "Note", cell: (l) => esc(l.note || "") },
            ],
            rows: Array.isArray(rec.lines) ? rec.lines : [],
            empty: "No counted lines.",
        })}`;
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not load this reconciliation", errorMessage(error));
    }
    createIcons({ icons });
}

async function reconciliationForm() {
    let sessionId = "";
    try {
        const active = await apiJson("/api/pos/sessions/active/");
        sessionId = active?.id ?? active?.session?.id ?? "";
    } catch {
        sessionId = "";
    }
    await openModal({
        title: "New cash reconciliation",
        size: "max-w-2xl",
        submitLabel: "Reconcile",
        html: `<p class="mb-4 text-xs text-slate-500">Count each tender you received in the session and enter the amount. Leave a tender empty if none was taken. Each session can be reconciled once.</p>
            ${fieldGrid([
                field({ name: "session_id", label: "POS session ID", type: "number", step: "1", min: 1, value: sessionId, required: true, help: "Filled from your active session when there is one.", full: true }),
                ...TENDERS.map(([value, label]) => field({ name: `t_${value}`, label, type: "number", step: "0.01", min: 0, value: "" })),
                field({ name: "note", label: "Note", type: "textarea", value: "", full: true }),
            ])}`,
        onSubmit: async (form) => {
            const d = readForm(form);
            const lines = TENDERS
                .filter(([value]) => d[`t_${value}`] !== "" && d[`t_${value}`] !== undefined)
                .map(([value]) => ({ tender_type: value, counted_amount: toNumber(d[`t_${value}`], `Counted ${value}`, { min: 0 }) }));
            if (!lines.length) throw new Error("Enter at least one counted tender amount.");
            const payload = {
                session_id: toNumber(d.session_id, "POS session ID", { min: 1 }),
                note: d.note || "",
                lines,
            };
            const created = await apiJson("/api/payments/reconciliations/", { method: "POST", body: JSON.stringify(payload) });
            toast("Reconciliation created.", "success");
            return setHashParam("#/payments", { tab: "reconciliations", reconciliation: created.id });
        },
    });
}

async function closeReconciliation(id) {
    const ok = await confirmDialog({
        title: "Close this reconciliation?",
        message: "Closed reconciliations cannot be edited. Make sure every counted amount is entered.",
        confirmLabel: "Close",
    });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(`/api/payments/reconciliations/${id}/close/`, { method: "POST" }), { successMessage: "Reconciliation closed.", errorFallback: "Could not close the reconciliation." });
    if (result === undefined) return;
    await renderReconciliation(id);
}

/* ── Refund credit ────────────────────────────────────────────────────────── */

async function renderRefunds(body) {
    const rows = await apiJson("/api/payments/refund-settlements/");
    const list = Array.isArray(rows) ? rows : (rows?.results || []);
    const start = (state.page - 1) * PAGE_SIZE;
    const pageRows = list.slice(start, start + PAGE_SIZE);
    const totalPages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
    body.innerHTML = `${table({
        columns: [
            { label: "When", cell: (r) => esc(formatDateTime(r.created_at)) },
            { label: "Order", cell: (r) => esc(r.order_number || "-") },
            { label: "Refund", cell: (r) => esc(numberText(r.refund_id)) },
            { label: "Amount", align: "right", cell: (r) => esc(moneyText(r.amount, r.currency)) },
            { label: "Cash", align: "right", cell: (r) => esc(numberText(r.cash_amount)) },
            { label: "Method", cell: (r) => esc(r.method || "-") },
            { label: "Status", cell: (r) => statusBadge(r.status) },
        ],
        rows: pageRows,
        empty: "No refund settlements found.",
        actions: (r) => (r.refund_id ? actionButton("Issue store credit", "refund-store-credit", { data: { id: r.refund_id, order: r.order_id ?? "" } }) : ""),
    })}<div class="mt-4">${pager({ page: state.page, totalPages, count: list.length })}</div>`;
}

async function refundStoreCreditForm(refundId, orderId) {
    if (!state.customers.length) return toast("Add a customer before issuing store credit.", "error");
    const options = state.customers.map((c) => ({ value: c.id, label: c.name }));
    await openModal({
        title: `Refund ${refundId} as store credit`,
        submitLabel: "Issue credit note",
        html: fieldGrid([
            field({ name: "customer", label: "Customer", type: "select", options, value: options[0].value, required: true, full: true, help: orderId ? `Order ${orderId}` : "" }),
        ]),
        onSubmit: async (form) => {
            const customerId = toNumber(readForm(form).customer, "Customer", { min: 1 });
            await apiJson(`/api/payments/refunds/${refundId}/store-credit/`, { method: "POST", body: JSON.stringify({ customer_id: customerId }) });
            toast("Refund issued as store credit.", "success");
            await renderTab();
            return true;
        },
    });
}
