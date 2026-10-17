/**
 * FBR / Fiscal controller: retail fiscalization setup and monitoring.
 *
 * Route: #/fbr?tab=configuration|profiles|sequences|invoices|submissions
 *
 * Endpoints used (all tenant-scoped, RBAC module "fiscal"):
 *   /api/fbr/eligibility/                        GET    (view)
 *   /api/fbr/configurations/                     GET, POST          (manage)
 *   /api/fbr/configurations/{id}/                PATCH, DELETE      (manage)
 *   /api/fbr/ims/health/?environment=            GET    (view; the BACKEND probes the component)
 *   /api/fbr/reference/{provinces,transaction-types,uom,sro-schedules,hs-codes}/ GET (view)
 *   /api/fbr/product-profiles/?page=&search=     GET, POST          (manage)
 *   /api/fbr/product-profiles/{id}/              PATCH, DELETE      (manage)
 *   /api/products/?search=                       GET    (products.view; product picker)
 *   /api/fiscal/sequences/                       GET, POST          (create)
 *   /api/fiscal/sequences/{id}/                  PATCH              (manage)
 *   /api/fiscal/invoices/?page=&search=&status=&fbr_status=  GET    (view)
 *   /api/fbr/submissions/?page=&search=&status=  GET    (view)
 *   /api/fbr/submissions/{id}/                   GET    (view)
 *   /api/fbr/submissions/{id}/retry/             POST   (create; only when allowed_actions.retry)
 *   /api/fbr/submissions/{id}/reconcile/         POST   (manage; only when allowed_actions.reconcile)
 *
 * Nothing here marks an invoice fiscalized: statuses come from the backend and
 * simulated acceptances are always labelled as not official.
 */
import { createIcons, icons } from "lucide";
import { apiJson, apiList, buildQuery } from "../../services/api.js";
import { hasPermission } from "../../services/auth.js";
import { formatCurrency } from "../../shared/currency.js";
import {
    esc, formatDateTime, formatDate, toast, errorMessage, openModal, confirmDialog,
    field, fieldGrid, readForm, table, badge, pager, tabs, pageHeader, primaryButton,
    actionButton, emptyStateCard, hashParam, setHashParam, selectInput, searchInput, debounce,
} from "../../shared/ui.js";
import {
    allowedTabs, configurationPayload, fieldErrorLines, nextInvoiceNumber, officialFbrNumber,
    profilePayload, retryOutcome, sequencePayload, statusInfo, submissionStatus,
} from "./fbr-logic.js";

const PAGE_SIZE = 20;
const state = { tab: "", page: 1, search: "", status: "", fbrStatus: "", refs: null, rows: [] };
const root = () => document.getElementById("fbr-root");
const can = (key) => hasPermission(key);

window.initializeFbr = async function () {
    const container = root();
    if (!container) return;
    container.addEventListener("click", onClick);
    container.addEventListener("change", onChange);
    container.addEventListener("input", debounce(onSearch, 350));
    container.addEventListener("submit", (event) => event.preventDefault());
    const available = allowedTabs(can);
    const requested = hashParam("tab");
    state.tab = available.some((t) => t.id === requested) ? requested : available[0]?.id || "";
    state.page = 1;
    state.search = hashParam("search") || "";
    state.status = "";
    state.fbrStatus = "";
    state.refs = null;
    return renderTab();
};

/* ── Shell & events ───────────────────────────────────────────────────────── */

function shell(body, actions = "") {
    const available = allowedTabs(can);
    root().innerHTML = `
        ${pageHeader({ title: "FBR / Fiscal", subtitle: "Retail fiscalization setup, invoice history and FBR submissions", actions })}
        ${available.length ? tabs(available, state.tab) : ""}
        <div class="mt-6">${body}</div>`;
    createIcons({ icons });
}

function loadingShell() {
    shell(`<div class="text-sm text-slate-500" role="status">Loading…</div>`);
}

function errorShell(error, what) {
    const permission = error?.status === 403;
    shell(emptyStateCard(
        permission ? "Not permitted" : `Could not load ${what}`,
        permission ? "Your role does not allow this part of FBR / Fiscal. Ask the business owner or an admin."
            : `${errorMessage(error, "The server could not be reached.")} Use the tab again to retry.`,
    ));
}

function onClick(event) {
    const actionEl = event.target.closest("[data-action]");
    if (actionEl && !actionEl.disabled) return handleAction(actionEl.dataset.action, actionEl);
    const pageEl = event.target.closest("[data-page]");
    if (pageEl && !pageEl.disabled) {
        state.page = Number(pageEl.dataset.page);
        return renderTab();
    }
    const tabEl = event.target.closest("[data-tab]");
    if (tabEl) return setHashParam("#/fbr", { tab: tabEl.dataset.tab });
}

function onChange(event) {
    if (event.target.id === "fbr-status-filter") {
        state.status = event.target.value;
        state.page = 1;
        renderTab();
    } else if (event.target.id === "fbr-fiscal-filter") {
        state.fbrStatus = event.target.value;
        state.page = 1;
        renderTab();
    }
}

function onSearch(event) {
    if (event.target.id !== "fbr-search") return;
    state.search = event.target.value.trim();
    state.page = 1;
    renderTab({ keepFocus: true });
}

async function renderTab(options = {}) {
    if (!state.tab) {
        return shell(emptyStateCard("Not permitted", "Your role does not include fiscal permissions."));
    }
    const renderers = {
        configuration: renderConfiguration, profiles: renderProfiles, sequences: renderSequences,
        invoices: renderInvoices, submissions: renderSubmissions,
    };
    if (!options.keepFocus) loadingShell();
    await renderers[state.tab](options);
    if (options.keepFocus) {
        const input = document.getElementById("fbr-search");
        if (input) {
            input.focus();
            input.setSelectionRange(input.value.length, input.value.length);
        }
    }
}

async function handleAction(action, el) {
    const id = el.dataset.id ? Number(el.dataset.id) : null;
    const handlers = {
        "config-new": () => editConfiguration(null, el.dataset.environment),
        "config-edit": () => editConfiguration(findRow(id)),
        "config-delete": () => deleteConfiguration(findRow(id)),
        "ims-health": () => checkImsHealth(el),
        "profile-new": () => editProfile(null),
        "profile-edit": () => editProfile(findRow(id)),
        "profile-delete": () => deleteProfile(findRow(id)),
        "sequence-new": () => editSequence(null),
        "sequence-edit": () => editSequence(findRow(id)),
        "sequence-toggle": () => toggleSequence(findRow(id), el),
        "invoice-submissions": () => setHashParam("#/fbr", { tab: "submissions", search: el.dataset.search }),
        "submission-view": () => viewSubmission(id),
        "submission-retry": () => retrySubmission(findRow(id), el),
        "submission-reconcile": () => reconcileSubmission(findRow(id)),
    };
    return handlers[action]?.();
}

function findRow(id) {
    return state.rows.find((row) => Number(row.id) === Number(id)) || null;
}

function statusBadgeFor(status) {
    const info = statusInfo(status);
    return badge(info.label, info.tone);
}

function filterBar(controls) {
    return `<div class="mb-4 flex flex-wrap items-center gap-3">${controls}</div>`;
}

function searchBox(placeholder) {
    return searchInput("fbr-search", placeholder).replace("<input ", `<input value="${esc(state.search)}" aria-label="${esc(placeholder)}" `);
}

async function references() {
    if (state.refs) return state.refs;
    const get = (path) => apiJson(path).then((data) => (Array.isArray(data) ? data : data?.results || [])).catch(() => []);
    const [provinces, transactionTypes, uoms, sroSchedules] = await Promise.all([
        get("/api/fbr/reference/provinces/"), get("/api/fbr/reference/transaction-types/"),
        get("/api/fbr/reference/uom/"), get("/api/fbr/reference/sro-schedules/"),
    ]);
    state.refs = { provinces, transactionTypes, uoms, sroSchedules };
    return state.refs;
}

const refOptions = (rows, blank = "— None —") => [
    { value: "", label: blank },
    ...rows.map((row) => ({ value: row.id, label: row.description ? `${row.code} — ${row.description}` : row.code })),
];

/** Make field errors visible inside a modal (openModal shows error.message). */
function withFieldErrors(error) {
    const lines = fieldErrorLines(error);
    if (lines.length) error.message = `Please fix: ${lines.join(" · ")}`;
    return error;
}

/* ── Configuration ────────────────────────────────────────────────────────── */

async function renderConfiguration() {
    let configs;
    let eligibility;
    try {
        [configs, eligibility] = await Promise.all([
            apiJson("/api/fbr/configurations/"),
            apiJson("/api/fbr/eligibility/").catch(() => ({ allowed_modes: ["di"], verified: false })),
        ]);
    } catch (error) {
        return errorShell(error, "the FBR configuration");
    }
    state.rows = Array.isArray(configs) ? configs : configs?.results || [];
    state.eligibility = eligibility;
    const missing = ["sandbox", "production"].filter((env) => !state.rows.some((row) => row.environment === env));
    const actions = missing.map((env) => actionButton(`Add ${env} configuration`, "config-new", { data: { environment: env } })).join(" ");
    const modes = (eligibility.allowed_modes || []).map((mode) => (mode === "ims" ? "Tier-1 IMS (retail)" : "Digital Invoicing")).join(", ");
    const intro = `<div class="mb-6 rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">
        <p><b>Eligible fiscalization tracks:</b> ${esc(modes || "Digital Invoicing")} ${eligibility.verified ? "" : "(eligibility not yet verified by the platform)"}</p>
        <p class="mt-1">Tier-1 retail uses the FBR IMS fiscal component: the <b>backend server</b> sends each sale to the component URL configured below (or to the FBR cloud endpoint), so the component must be reachable from the server. Sales are never blocked when fiscalization fails; they stay pending/failed until resolved.</p>
    </div>`;
    const cards = state.rows.length
        ? state.rows.map(configurationCard).join("")
        : emptyStateCard("No FBR configuration yet", "Add a sandbox configuration first and test it before configuring production.");
    shell(`${intro}<div class="grid gap-6 lg:grid-cols-2">${cards}</div>`, actions);
}

function configurationCard(config) {
    const ims = config.integration_mode === "ims";
    const rows = [
        ["Integration", ims ? "Tier-1 IMS fiscal component" : "PRAL Digital Invoicing"],
        ["Seller", `${config.seller_business_name || "—"} · NTN/CNIC ${config.seller_ntn_cnic || "—"}`],
        ["Province", config.resolved_seller_province || "—"],
        ims ? ["POS registration (POSID)", config.pos_registration_number || "Not set"] : ["Scenario", config.scenario_id || "—"],
        ims ? ["Component", config.ims_use_cloud ? "FBR cloud endpoint" : config.ims_local_base_url || "—"] : ["Endpoint", config.resolved_endpoint_url || "—"],
        ["Security token", config.has_security_token ? "Stored (hidden)" : "Not set"],
    ];
    if (ims && !config.ims_use_cloud && config.environment === "production") {
        rows.push(["Production component confirmed", config.ims_local_confirmed ? "Yes" : "No"]);
    }
    return `<div class="rounded-2xl border border-slate-200 bg-white p-6">
        <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
                <h2 class="text-lg font-semibold capitalize text-slate-900">${esc(config.environment)}</h2>
                ${config.is_active ? badge("Active", "green") : badge("Inactive", "slate")}
                ${config.use_simulator ? badge("Simulator — not official", "violet") : ""}
            </div>
            <div class="flex gap-2">
                ${ims && !config.ims_use_cloud ? actionButton("Check component", "ims-health", { data: { environment: config.environment } }) : ""}
                ${actionButton("Edit", "config-edit", { data: { id: config.id } })}
                ${actionButton("Delete", "config-delete", { tone: "danger", data: { id: config.id } })}
            </div>
        </div>
        ${config.use_simulator ? `<p class="mt-3 rounded-lg bg-violet-50 p-3 text-xs text-violet-800">This configuration fiscalizes through the development simulator. Simulated results are never official and never print an FBR number or QR.</p>` : ""}
        <dl class="mt-4 grid grid-cols-1 gap-y-2 text-sm sm:grid-cols-2">
            ${rows.map(([label, value]) => `<dt class="text-slate-500">${esc(label)}</dt><dd class="font-medium text-slate-800 break-all">${esc(value)}</dd>`).join("")}
        </dl>
        <p class="mt-4 text-xs text-slate-400">Updated ${esc(formatDateTime(config.updated_at))}</p>
    </div>`;
}

async function editConfiguration(config, environment = "sandbox") {
    const refs = await references();
    const creating = !config;
    const c = config || { environment, integration_mode: (state.eligibility?.allowed_modes || ["di"]).includes("ims") ? "ims" : "di", is_active: true, verify_tls: true, timeout_seconds: 30, max_retries: 3, ims_local_base_url: "http://localhost:8524" };
    const modes = (state.eligibility?.allowed_modes || ["di"]);
    const modeOptions = [
        { value: "ims", label: "Tier-1 IMS fiscal component (retail)" },
        { value: "di", label: "PRAL Digital Invoicing" },
    ].filter((option) => modes.includes(option.value) || option.value === c.integration_mode);
    const section = (title, inner, attrs = "") => `<fieldset class="mt-6" ${attrs}><legend class="mb-3 text-sm font-semibold text-slate-900">${esc(title)}</legend>${fieldGrid(inner)}</fieldset>`;
    const html = `
        ${fieldGrid([
            creating
                ? field({ name: "environment", label: "Environment", type: "select", value: c.environment, options: [{ value: "sandbox", label: "Sandbox (testing)" }, { value: "production", label: "Production (live FBR)" }] })
                : `<div><p class="mb-1.5 text-sm font-medium text-slate-700">Environment</p><p class="h-11 py-2.5 text-sm font-semibold capitalize">${esc(c.environment)}</p></div>`,
            field({ name: "integration_mode", label: "Integration mode", type: "select", value: c.integration_mode, options: modeOptions }),
            field({ name: "is_active", label: "Active (fiscalize sales with this configuration)", type: "checkbox", value: c.is_active, full: true }),
        ])}
        ${section("Seller (as registered with FBR)", [
            field({ name: "seller_business_name", label: "Business name", value: c.seller_business_name || "" }),
            field({ name: "seller_ntn_cnic", label: "NTN / CNIC", value: c.seller_ntn_cnic || "", help: "Required for production." }),
            field({ name: "seller_address", label: "Address", value: c.seller_address || "", full: true }),
            field({ name: "seller_province", label: "Province", type: "select", value: c.seller_province ?? "", options: refOptions(refs.provinces, "— Select —") }),
        ])}
        ${section("Tier-1 IMS fiscal component", [
            field({ name: "pos_registration_number", label: "POS registration number (POSID)", type: "number", min: 1, value: c.pos_registration_number ?? "", help: "Issued by FBR on POS registration (required for IMS)." }),
            field({ name: "ims_use_cloud", label: "Use the FBR cloud endpoint instead of a local component", type: "checkbox", value: c.ims_use_cloud }),
            field({ name: "ims_local_base_url", label: "Local component URL", type: "url", value: c.ims_local_base_url || "", help: "Must be reachable from the backend server." }),
            field({ name: "ims_local_confirmed", label: "I confirm this component was installed in PRODUCTION mode", type: "checkbox", value: c.ims_local_confirmed, help: "Required for a production local component." }),
        ], 'data-mode="ims"')}
        ${section("Digital Invoicing (PRAL)", [
            field({ name: "scenario_id", label: "Sandbox scenario", type: "select", value: c.scenario_id || "", options: [{ value: "", label: "— None —" }, ...Array.from({ length: 28 }, (_, i) => { const id = `SN${String(i + 1).padStart(3, "0")}`; return { value: id, label: id }; })] }),
            field({ name: "default_transaction_type", label: "Default transaction type", type: "select", value: c.default_transaction_type ?? "", options: refOptions(refs.transactionTypes) }),
            field({ name: "endpoint_url", label: "Endpoint override (optional)", type: "url", value: c.endpoint_url || "", full: true }),
        ], 'data-mode="di"')}
        ${section("Credentials & connection", [
            field({ name: "security_token", label: "FBR security token", type: "password", value: "", placeholder: c.has_security_token ? "Stored — leave blank to keep" : "Not set", help: "Write-only: never shown again after saving." }),
            field({ name: "timeout_seconds", label: "Timeout (seconds)", type: "number", min: 1, value: c.timeout_seconds ?? 30 }),
            field({ name: "max_retries", label: "Max automatic retries", type: "number", min: 0, value: c.max_retries ?? 3 }),
            field({ name: "verify_tls", label: "Verify TLS certificates (required in production)", type: "checkbox", value: c.verify_tls }),
            field({ name: "use_simulator", label: "Development only: use the IMS simulator (never official)", type: "checkbox", value: c.use_simulator, full: true }),
        ])}`;
    const pending = openModal({
        title: creating ? `New ${c.environment} FBR configuration` : `Edit ${c.environment} FBR configuration`,
        html, size: "max-w-3xl", submitLabel: "Save configuration",
        onSubmit: async (form) => {
            const body = configurationPayload(readForm(form), { creating });
            try {
                return creating
                    ? await apiJson("/api/fbr/configurations/", { method: "POST", body: JSON.stringify(body) })
                    : await apiJson(`/api/fbr/configurations/${c.id}/`, { method: "PATCH", body: JSON.stringify(body) });
            } catch (error) {
                throw withFieldErrors(error);
            }
        },
    });
    const modal = document.getElementById("ui-modal-root");
    const modeSelect = modal?.querySelector('[name="integration_mode"]');
    const syncMode = () => modal.querySelectorAll("fieldset[data-mode]").forEach((set) => {
        set.hidden = set.dataset.mode !== modeSelect.value;
    });
    if (modeSelect) {
        modeSelect.addEventListener("change", syncMode);
        syncMode();
    }
    const saved = await pending;
    if (saved) {
        toast("FBR configuration saved.", "success");
        renderTab();
    }
}

async function deleteConfiguration(config) {
    if (!config) return;
    const ok = await confirmDialog({
        title: `Delete the ${config.environment} configuration?`,
        message: "Sales will no longer be fiscalized with it. Existing invoices and submissions are kept.",
        confirmLabel: "Delete",
    });
    if (!ok) return;
    try {
        await apiJson(`/api/fbr/configurations/${config.id}/`, { method: "DELETE" });
        toast("Configuration deleted.", "success");
        renderTab();
    } catch (error) {
        toast(errorMessage(error, "The configuration could not be deleted."), "error");
    }
}

async function checkImsHealth(button) {
    const environment = button.dataset.environment;
    button.disabled = true;
    try {
        const result = await apiJson(`/api/fbr/ims/health/${buildQuery({ environment })}`);
        toast(result.simulated ? "Simulator is responding (not a real FBR component)." : "The IMS fiscal component is responding.", result.simulated ? "info" : "success");
    } catch (error) {
        const reason = error?.data?.error || errorMessage(error, "The IMS fiscal component did not respond.");
        toast(`Component check failed: ${reason}`, "error");
    } finally {
        button.disabled = false;
    }
}

/* ── Product fiscal profiles ──────────────────────────────────────────────── */

async function renderProfiles() {
    let data;
    try {
        data = await apiList(`/api/fbr/product-profiles/${buildQuery({ page: state.page, page_size: PAGE_SIZE, search: state.search })}`);
    } catch (error) {
        return errorShell(error, "product fiscal profiles");
    }
    state.rows = data.results;
    const body = `
        <p class="mb-4 text-sm text-slate-600">Every product sold through FBR needs an HS code, unit of measure and tax rate. Sales of products without a profile cannot be fiscalized.</p>
        ${filterBar(searchBox("Search product, SKU or HS code"))}
        ${table({
            columns: [
                { label: "Product", cell: (r) => `<div class="font-medium text-slate-900">${esc(r.product_name || `#${r.product}`)}</div><div class="text-xs text-slate-500">${esc(r.product_sku || "")}</div>` },
                { label: "HS code", cell: (r) => esc(r.hs_code_dotted || r.hs_code_value || "—") },
                { label: "UoM", cell: (r) => esc(r.uom_description || r.uom_value || "—") },
                { label: "Sales tax", align: "right", cell: (r) => `${esc(Number(r.sales_tax_rate || 0))}%` },
                { label: "PCT code", cell: (r) => esc(r.pct_code || "—") },
                { label: "Status", cell: (r) => (r.is_active ? badge("Active", "green") : badge("Inactive", "slate")) },
            ],
            rows: data.results,
            empty: state.search ? "No profiles match your search." : "No product fiscal profiles yet.",
            actions: (r) => `${actionButton("Edit", "profile-edit", { data: { id: r.id } })} ${actionButton("Delete", "profile-delete", { tone: "danger", data: { id: r.id } })}`,
        })}
        ${pager({ page: data.page, totalPages: data.total_pages, count: data.count })}`;
    shell(body, primaryButton("Add product profile", "profile-new"));
}

async function editProfile(profile) {
    const refs = await references();
    const creating = !profile;
    const p = profile || { sales_tax_rate: "18.000", is_active: true };
    const hsOption = p.hs_code ? [{ value: p.hs_code, label: `${p.hs_code_dotted || p.hs_code_value}` }] : [];
    const productControl = creating
        ? `<div class="col-span-2">
              <label class="mb-1.5 block text-sm font-medium text-slate-700" for="fbr-product-search">Product <span class="text-rose-500">*</span></label>
              <input id="fbr-product-search" type="search" placeholder="Type a product name, SKU or barcode" class="h-11 w-full rounded-xl border border-slate-200 px-3 text-sm">
              <select name="product" required class="mt-2 h-11 w-full rounded-xl border border-slate-200 px-3 text-sm"><option value="">— Search to choose a product —</option></select>
           </div>`
        : `<div class="col-span-2"><p class="mb-1.5 text-sm font-medium text-slate-700">Product</p><p class="font-semibold">${esc(p.product_name)} <span class="text-xs text-slate-500">${esc(p.product_sku || "")}</span></p></div>`;
    const html = fieldGrid([
        productControl,
        `<div class="col-span-2">
            <label class="mb-1.5 block text-sm font-medium text-slate-700" for="fbr-hs-search">HS code <span class="text-rose-500">*</span></label>
            <input id="fbr-hs-search" type="search" placeholder="Type at least 2 characters of the code or description" class="h-11 w-full rounded-xl border border-slate-200 px-3 text-sm">
            <select name="hs_code" required class="mt-2 h-11 w-full rounded-xl border border-slate-200 px-3 text-sm">
                ${hsOption.length ? hsOption.map((o) => `<option value="${esc(o.value)}" selected>${esc(o.label)}</option>`).join("") : `<option value="">— Search to choose an HS code —</option>`}
            </select>
         </div>`,
        field({ name: "uom", label: "Unit of measure", type: "select", required: true, value: p.uom ?? "", options: refOptions(refs.uoms, "— Select —") }),
        field({ name: "sales_tax_rate", label: "Sales tax rate (%)", type: "number", step: "0.001", min: 0, value: p.sales_tax_rate ?? "18.000" }),
        field({ name: "transaction_type", label: "Transaction type", type: "select", value: p.transaction_type ?? "", options: refOptions(refs.transactionTypes, "— Use configuration default —") }),
        field({ name: "pct_code", label: "PCT code (IMS)", value: p.pct_code || "", help: "Up to 8 digits; falls back to the HS code digits." }),
        field({ name: "product_code", label: "Product code", value: p.product_code || "", help: "Defaults to the SKU." }),
        field({ name: "retail_price", label: "Fixed retail price (3rd schedule)", type: "number", step: "0.01", min: 0, value: p.retail_price ?? "" }),
        field({ name: "third_schedule", label: "Third schedule goods (tax on printed retail price)", type: "checkbox", value: p.third_schedule }),
        field({ name: "sro_schedule", label: "SRO schedule", type: "select", value: p.sro_schedule ?? "", options: refOptions(refs.sroSchedules) }),
        field({ name: "sro_item_serial_no", label: "SRO item serial no.", value: p.sro_item_serial_no || "" }),
        field({ name: "extra_tax_rate", label: "Extra tax (%)", type: "number", step: "0.001", min: 0, value: p.extra_tax_rate ?? "" }),
        field({ name: "further_tax_rate", label: "Further tax (%)", type: "number", step: "0.001", min: 0, value: p.further_tax_rate ?? "" }),
        field({ name: "fed_payable_rate", label: "FED payable (%)", type: "number", step: "0.001", min: 0, value: p.fed_payable_rate ?? "" }),
        field({ name: "is_active", label: "Active", type: "checkbox", value: p.is_active }),
    ]);
    const pending = openModal({
        title: creating ? "New product fiscal profile" : "Edit product fiscal profile",
        html, size: "max-w-3xl", submitLabel: "Save profile",
        onSubmit: async (form) => {
            const values = readForm(form);
            delete values[""];
            const body = profilePayload(values, { creating });
            if (creating && !body.product) throw new Error("Choose a product.");
            if (!body.hs_code) throw new Error("Choose an HS code.");
            try {
                return creating
                    ? await apiJson("/api/fbr/product-profiles/", { method: "POST", body: JSON.stringify(body) })
                    : await apiJson(`/api/fbr/product-profiles/${p.id}/`, { method: "PATCH", body: JSON.stringify(body) });
            } catch (error) {
                throw withFieldErrors(error);
            }
        },
    });
    const modal = document.getElementById("ui-modal-root");
    wireLookup(modal, "#fbr-hs-search", '[name="hs_code"]', async (term) => {
        if (term.length < 2) return null;
        const rows = await apiJson(`/api/fbr/reference/hs-codes/${buildQuery({ search: term })}`);
        return (Array.isArray(rows) ? rows : rows?.results || []).slice(0, 50)
            .map((r) => ({ value: r.id, label: `${r.dotted_code || r.code} — ${r.description || ""}` }));
    });
    if (creating) {
        wireLookup(modal, "#fbr-product-search", '[name="product"]', async (term) => {
            if (term.length < 1) return null;
            const data = await apiList(`/api/products/${buildQuery({ search: term, page_size: 25 })}`);
            return data.results.map((r) => ({ value: r.id, label: `${r.name}${r.sku ? ` (${r.sku})` : ""}` }));
        });
    }
    const saved = await pending;
    if (saved) {
        toast("Product fiscal profile saved.", "success");
        renderTab();
    }
}

/** Debounced search box that fills a <select> with matches. */
function wireLookup(modal, inputSelector, selectSelector, search) {
    const input = modal?.querySelector(inputSelector);
    const select = modal?.querySelector(selectSelector);
    if (!input || !select) return;
    let seq = 0;
    input.addEventListener("input", debounce(async () => {
        const mine = ++seq;
        const term = input.value.trim();
        try {
            const options = await search(term);
            if (mine !== seq || options === null) return;
            select.innerHTML = options.length
                ? options.map((o, i) => `<option value="${esc(o.value)}" ${i === 0 ? "selected" : ""}>${esc(o.label)}</option>`).join("")
                : `<option value="">No matches</option>`;
        } catch (error) {
            if (mine !== seq) return;
            select.innerHTML = `<option value="">${esc(errorMessage(error, "Search failed"))}</option>`;
        }
    }, 300));
}

async function deleteProfile(profile) {
    if (!profile) return;
    const ok = await confirmDialog({
        title: "Delete this product fiscal profile?",
        message: `${profile.product_name || "This product"} can no longer be fiscalized until a new profile is added.`,
        confirmLabel: "Delete",
    });
    if (!ok) return;
    try {
        await apiJson(`/api/fbr/product-profiles/${profile.id}/`, { method: "DELETE" });
        toast("Profile deleted.", "success");
        renderTab();
    } catch (error) {
        toast(errorMessage(error, "The profile could not be deleted."), "error");
    }
}

/* ── Invoice sequences ────────────────────────────────────────────────────── */

async function renderSequences() {
    let data;
    try {
        data = await apiList("/api/fiscal/sequences/");
    } catch (error) {
        return errorShell(error, "invoice sequences");
    }
    state.rows = data.results;
    const manage = can("fiscal.manage");
    const activeInvoice = state.rows.filter((r) => r.is_active && r.document_type === "invoice");
    const note = activeInvoice.length
        ? `POS sales are numbered from the oldest active invoice sequence: <b>${esc(activeInvoice[0].name)}</b>.`
        : `<b>No active invoice sequence:</b> POS sales are completed but not fiscalized until one is active.`;
    const body = `
        <p class="mb-4 rounded-xl border ${activeInvoice.length ? "border-slate-200 bg-white" : "border-amber-200 bg-amber-50"} p-4 text-sm text-slate-700">${note} Numbering cannot be changed once a sequence has issued invoices; sequences are deactivated, never deleted.</p>
        ${table({
            columns: [
                { label: "Name", cell: (r) => `<span class="font-medium text-slate-900">${esc(r.name)}</span>` },
                { label: "Type", cell: (r) => esc(String(r.document_type).replace(/_/g, " ")) },
                { label: "Next number", cell: (r) => `<span class="font-mono">${esc(nextInvoiceNumber(r))}</span>` },
                { label: "Issued", align: "right", cell: (r) => esc(r.invoices_issued ?? 0) },
                { label: "Status", cell: (r) => (r.is_active ? badge("Active", "green") : badge("Inactive", "slate")) },
            ],
            rows: state.rows,
            empty: "No invoice sequences yet.",
            actions: manage ? (r) => `${actionButton("Edit", "sequence-edit", { data: { id: r.id } })} ${actionButton(r.is_active ? "Deactivate" : "Activate", "sequence-toggle", { data: { id: r.id } })}` : null,
        })}`;
    shell(body, primaryButton("New sequence", "sequence-new"));
}

async function editSequence(sequence) {
    const creating = !sequence;
    const s = sequence || { name: "", prefix: "INV-", next_number: 1, padding: 6, document_type: "invoice", is_active: true, invoices_issued: 0 };
    const locked = Number(s.invoices_issued) > 0;
    const lockedNote = locked ? `<p class="col-span-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">${esc(s.invoices_issued)} invoice(s) were issued from this sequence, so its numbering is locked. Create a new sequence to change it.</p>` : "";
    const disable = (html) => (locked ? html.replace(/<(input|select)/, "<$1 disabled") : html);
    const html = fieldGrid([
        lockedNote,
        field({ name: "name", label: "Name", required: true, value: s.name, full: true }),
        disable(field({ name: "prefix", label: "Prefix", required: true, value: s.prefix })),
        disable(field({ name: "document_type", label: "Document type", type: "select", value: s.document_type, options: [{ value: "invoice", label: "Invoice" }, { value: "credit_note", label: "Credit note" }, { value: "proforma", label: "Proforma" }] })),
        disable(field({ name: "next_number", label: "Next number", type: "number", min: 1, required: true, value: s.next_number })),
        disable(field({ name: "padding", label: "Digits (1–12)", type: "number", min: 1, required: true, value: s.padding })),
        field({ name: "is_active", label: "Active", type: "checkbox", value: s.is_active }),
    ]);
    const saved = await openModal({
        title: creating ? "New invoice sequence" : `Edit ${s.name}`, html, submitLabel: "Save sequence",
        onSubmit: async (form) => {
            const values = readForm(form);
            const padding = Number(values.padding ?? s.padding);
            if (!locked && (!Number.isInteger(padding) || padding < 1 || padding > 12)) throw new Error("Digits must be between 1 and 12.");
            const body = sequencePayload(values, creating ? null : s);
            try {
                return creating
                    ? await apiJson("/api/fiscal/sequences/", { method: "POST", body: JSON.stringify(body) })
                    : await apiJson(`/api/fiscal/sequences/${s.id}/`, { method: "PATCH", body: JSON.stringify(body) });
            } catch (error) {
                throw withFieldErrors(error);
            }
        },
    });
    if (saved) {
        toast("Invoice sequence saved.", "success");
        renderTab();
    }
}

async function toggleSequence(sequence, button) {
    if (!sequence) return;
    if (sequence.is_active) {
        const ok = await confirmDialog({
            title: `Deactivate ${sequence.name}?`,
            message: "If no other invoice sequence is active, new POS sales will not be fiscalized.",
            confirmLabel: "Deactivate",
        });
        if (!ok) return;
    }
    button.disabled = true;
    try {
        await apiJson(`/api/fiscal/sequences/${sequence.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !sequence.is_active }) });
        toast(sequence.is_active ? "Sequence deactivated." : "Sequence activated.", "success");
        renderTab();
    } catch (error) {
        toast(errorMessage(error, "The sequence could not be updated."), "error");
        button.disabled = false;
    }
}

/* ── Fiscal invoice history ───────────────────────────────────────────────── */

const FBR_FILTERS = [
    { value: "", label: "All FBR statuses" }, { value: "accepted", label: "Accepted by FBR" },
    { value: "pending", label: "Pending" }, { value: "unknown", label: "Outcome unknown" },
    { value: "rejected", label: "Rejected" }, { value: "failed", label: "Failed" },
    { value: "simulated", label: "Simulated (not official)" }, { value: "not_submitted", label: "Not submitted" },
];

async function renderInvoices() {
    let data;
    try {
        data = await apiList(`/api/fiscal/invoices/${buildQuery({ page: state.page, page_size: PAGE_SIZE, search: state.search, status: state.status, fbr_status: state.fbrStatus })}`);
    } catch (error) {
        return errorShell(error, "fiscal invoices");
    }
    state.rows = data.results;
    const filters = filterBar([
        searchBox("Invoice, FBR or sale number"),
        selectInput("fbr-status-filter", [{ value: "", label: "All invoice statuses" }, { value: "issued", label: "Issued" }, { value: "draft", label: "Draft" }, { value: "cancelled", label: "Cancelled" }, { value: "void", label: "Void" }], state.status),
        selectInput("fbr-fiscal-filter", FBR_FILTERS, state.fbrStatus),
    ].join(""));
    const body = `${filters}
        ${table({
            columns: [
                { label: "Invoice", cell: (r) => `<div class="font-mono font-medium text-slate-900">${esc(r.invoice_number)}</div><div class="text-xs text-slate-500">${esc(r.issue_date ? formatDate(r.issue_date) : formatDateTime(r.created_at))}</div>` },
                { label: "Sale", cell: (r) => esc(r.order_number || "—") },
                { label: "Total", align: "right", cell: (r) => esc(formatCurrency(r.total)) },
                { label: "Invoice status", cell: (r) => badge(String(r.status), r.status === "issued" ? "blue" : "slate") },
                { label: "FBR", cell: (r) => `${statusBadgeFor(r.fbr?.status)}${r.fbr?.environment ? `<div class="mt-1 text-xs capitalize text-slate-500">${esc(r.fbr.environment)} · ${esc(r.fbr.integration_mode || "")}</div>` : ""}` },
                { label: "FBR invoice no.", cell: (r) => (officialFbrNumber(r) ? `<span class="font-mono">${esc(officialFbrNumber(r))}</span>` : "—") },
                { label: "Last attempt", cell: (r) => (r.fbr?.submitted_at ? `${esc(formatDateTime(r.fbr.submitted_at))}${r.fbr.attempts ? `<div class="text-xs text-slate-500">${esc(r.fbr.attempts)} attempt(s)</div>` : ""}` : "—") },
                { label: "Error", className: "max-w-xs", cell: (r) => (r.fbr?.error_message ? `<span class="text-xs text-rose-700">${esc([r.fbr.error_code, r.fbr.error_message].filter(Boolean).join(": "))}</span>` : "") },
            ],
            rows: data.results,
            empty: state.search || state.status || state.fbrStatus ? "No invoices match these filters." : "No fiscal invoices yet. They are created when a sale is fiscalized.",
            actions: (r) => (r.fbr?.submission_id ? actionButton("Submissions", "invoice-submissions", { data: { search: r.invoice_number } }) : ""),
        })}
        ${pager({ page: data.page, totalPages: data.total_pages, count: data.count })}`;
    shell(body);
}

/* ── Submissions ──────────────────────────────────────────────────────────── */

const SUBMISSION_FILTERS = [
    { value: "", label: "All statuses" }, { value: "pending", label: "Pending" },
    { value: "accepted", label: "Accepted by FBR" }, { value: "simulated", label: "Simulated (not official)" },
    { value: "rejected", label: "Rejected" }, { value: "failed", label: "Failed" }, { value: "unknown", label: "Outcome unknown" },
];

async function renderSubmissions() {
    let data;
    try {
        data = await apiList(`/api/fbr/submissions/${buildQuery({ page: state.page, page_size: PAGE_SIZE, search: state.search, status: state.status })}`);
    } catch (error) {
        return errorShell(error, "FBR submissions");
    }
    state.rows = data.results;
    const filters = filterBar([searchBox("USIN, invoice, FBR or sale number"), selectInput("fbr-status-filter", SUBMISSION_FILTERS, state.status)].join(""));
    const body = `
        <p class="mb-4 text-sm text-slate-600">Retry is offered only for failed or rejected attempts the server allows. An <b>unknown</b> outcome may already be fiscalized, so it must be reconciled (checked against the component/FBR) before any new attempt.</p>
        ${filters}
        ${table({
            columns: [
                { label: "#", cell: (r) => `<span class="font-mono text-xs">${esc(r.id)}</span>${r.is_validate ? `<div class="text-xs text-slate-500">validation only</div>` : ""}` },
                { label: "Invoice / sale", cell: (r) => `<div class="font-mono">${esc(r.invoice_number || "—")}</div><div class="text-xs text-slate-500">${esc(r.order_number || "")}</div>` },
                { label: "Env / mode", cell: (r) => `<span class="capitalize">${esc(r.environment)}</span><div class="text-xs text-slate-500">${esc(r.integration_mode || "")}${r.usin ? ` · USIN ${esc(r.usin)}` : ""}</div>` },
                { label: "Status", cell: (r) => statusBadgeFor(submissionStatus(r)) },
                { label: "FBR invoice no.", cell: (r) => (officialFbrNumber(r) ? `<span class="font-mono">${esc(officialFbrNumber(r))}</span>` : "—") },
                { label: "Error", className: "max-w-xs", cell: (r) => (r.error_message ? `<span class="text-xs text-rose-700">${esc([r.error_code, String(r.error_message).slice(0, 240)].filter(Boolean).join(": "))}</span>` : "") },
                { label: "Attempts", align: "right", cell: (r) => esc(r.attempts ?? 0) },
                { label: "Submitted", cell: (r) => `${esc(formatDateTime(r.created_at))}${r.responded_at ? `<div class="text-xs text-slate-500">replied ${esc(formatDateTime(r.responded_at))}</div>` : ""}` },
            ],
            rows: data.results,
            empty: state.search || state.status ? "No submissions match these filters." : "No FBR submissions yet.",
            actions: (r) => [
                actionButton("Details", "submission-view", { data: { id: r.id } }),
                r.allowed_actions?.retry ? actionButton("Retry", "submission-retry", { data: { id: r.id } }) : "",
                r.allowed_actions?.reconcile ? actionButton("Reconcile", "submission-reconcile", { data: { id: r.id } }) : "",
            ].join(" "),
        })}
        ${pager({ page: data.page, totalPages: data.total_pages, count: data.count })}`;
    shell(body);
}

async function viewSubmission(id) {
    let submission;
    try {
        submission = await apiJson(`/api/fbr/submissions/${id}/`);
    } catch (error) {
        return toast(errorMessage(error, "The submission could not be loaded."), "error");
    }
    const pre = (value) => `<pre class="max-h-60 overflow-auto rounded-lg bg-slate-50 p-3 text-xs">${esc(JSON.stringify(value ?? {}, null, 2))}</pre>`;
    const status = submissionStatus(submission);
    await openModal({
        title: `Submission #${submission.id}`, size: "max-w-3xl", hideSubmit: true,
        html: `
            <div class="mb-4 flex flex-wrap items-center gap-2">${statusBadgeFor(status)} <span class="text-sm text-slate-600">${esc(submission.invoice_number || "")} · ${esc(submission.environment)} · ${esc(submission.integration_mode || "")}</span></div>
            ${status === "simulated" ? `<p class="mb-4 rounded-lg bg-violet-50 p-3 text-xs text-violet-800">Simulator response — not an FBR acceptance.</p>` : ""}
            ${submission.error_message ? `<p class="mb-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-800">${esc([submission.error_code, submission.error_message].filter(Boolean).join(": "))}</p>` : ""}
            <p class="mb-1 text-sm font-semibold">Request (credentials redacted)</p>${pre(submission.request_payload)}
            <p class="mb-1 mt-4 text-sm font-semibold">Response</p>${pre(submission.response_payload)}`,
    });
}

async function retrySubmission(submission, button) {
    if (!submission?.allowed_actions?.retry) return;
    const ok = await confirmDialog({
        title: `Retry submission #${submission.id}?`,
        message: `Invoice ${submission.invoice_number || ""} will be sent to ${submission.environment === "production" ? "LIVE FBR" : "the FBR sandbox"} again.`,
        confirmLabel: "Retry now", danger: submission.environment === "production",
    });
    if (!ok) return;
    button.disabled = true;
    let outcome;
    try {
        outcome = retryOutcome(await apiJson(`/api/fbr/submissions/${submission.id}/retry/`, { method: "POST", body: "{}" }), null);
    } catch (error) {
        outcome = retryOutcome(null, error);
    }
    toast(outcome.message, outcome.tone);
    renderTab();
}

async function reconcileSubmission(submission) {
    if (!submission?.allowed_actions?.reconcile) return;
    const html = `
        <p class="mb-4 text-sm text-slate-600">The result of this attempt was not received, so the sale may or may not be fiscalized. Check the IMS component / FBR records for <b>USIN ${esc(submission.usin || "n/a")}</b> (invoice ${esc(submission.invoice_number || "")}) and record what you found. This is audited.</p>
        ${fieldGrid([
            field({ name: "outcome", label: "Outcome", type: "select", required: true, value: "", options: [{ value: "", label: "— Select —" }, { value: "fiscalized", label: "Fiscalized — FBR issued an invoice number" }, { value: "not_fiscalized", label: "Not fiscalized — safe to retry" }], full: true }),
            field({ name: "fiscal_invoice_number", label: "FBR invoice number (required if fiscalized)", value: "", full: true }),
        ])}`;
    const saved = await openModal({
        title: `Reconcile submission #${submission.id}`, html, submitLabel: "Record outcome",
        onSubmit: async (form) => {
            const values = readForm(form);
            if (!values.outcome) throw new Error("Choose the outcome you verified.");
            if (values.outcome === "fiscalized" && !values.fiscal_invoice_number) throw new Error("Enter the FBR invoice number you verified.");
            try {
                return await apiJson(`/api/fbr/submissions/${submission.id}/reconcile/`, { method: "POST", body: JSON.stringify(values) });
            } catch (error) {
                throw withFieldErrors(error);
            }
        },
    });
    if (saved) {
        toast(`Submission reconciled: ${statusInfo(submissionStatus(saved)).label}.`, "success");
        renderTab();
    }
}
