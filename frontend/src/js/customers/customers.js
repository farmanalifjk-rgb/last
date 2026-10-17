/**
 * Customers controller: list, create/edit, archive, customer groups and the
 * customer detail view (overview, credit limit, addresses, notes, loyalty,
 * activity, documents).
 *
 * Endpoints used:
 *   /api/customers/                         GET, POST
 *   /api/customers/{id}/                    GET, PATCH
 *   /api/customers/{id}/archive/            POST
 *   /api/customers/{id}/summary/            GET
 *   /api/customers/{id}/activity/           GET
 *   /api/customers/{id}/loyalty/            GET
 *   /api/customers/{id}/credit-limit/       GET, POST
 *   /api/customers/{id}/addresses/          GET, POST
 *   /api/customer-addresses/{id}/           PATCH, DELETE
 *   /api/customers/{id}/notes/              GET, POST
 *   /api/customer-notes/{id}/               PATCH, DELETE
 *   /api/customers/{id}/documents/          GET, POST (multipart)
 *   /api/customer-documents/{id}/           DELETE
 *   /api/customer-documents/{id}/download/  GET
 *   /api/customer-groups/                   GET, POST
 *   /api/customer-groups/{id}/              PATCH, DELETE
 */
import { createIcons, icons } from "lucide";
import { apiJson, apiList, apiDownload, buildQuery } from "../../services/api.js";
import {
    esc, formatMoney, formatDate, formatDateTime, toast, errorMessage, openModal, confirmDialog,
    field, fieldGrid, readForm, requireValue, toNumber, table, badge, pager, tabs, statusBadge,
    pageHeader, primaryButton, secondaryButton, actionButton, searchInput, debounce, runAction,
    emptyStateCard, hashParam, setHashParam, dateOrNull,
} from "../../shared/ui.js";

const PAGE_SIZE = 10;
const state = {
    list: { search: "", page: 1 },
    detail: { id: null, tab: "overview", page: 1 },
    groups: [],
};

const root = () => document.getElementById("customers-root");

window.initializeCustomers = async function () {
    const container = root();
    if (!container) return;
    // Delegated listeners on the stable root: no user data is placed in inline handlers.
    container.addEventListener("click", onClick);
    container.addEventListener("submit", (event) => event.preventDefault());
    container.addEventListener("input", onInput);
    state.detail.tab = "overview";
    state.detail.page = 1;
    await route();
};

async function route() {
    const id = hashParam("id");
    if (id) return renderDetail(id);
    return renderList();
}

/* ── Shell ────────────────────────────────────────────────────────────────── */

function listHeader() {
    return pageHeader({
        title: "Customers",
        subtitle: "Customer records, credit limits, loyalty and history",
        actions: `<button type="button" data-action="groups" class="h-11 rounded-xl border border-slate-200 bg-white px-5 text-sm font-semibold text-slate-700 hover:bg-slate-50">Customer groups</button>${primaryButton("New customer", "create")}`,
    });
}

/* ── Event handling ───────────────────────────────────────────────────────── */

function onClick(event) {
    const actionEl = event.target.closest("[data-action]");
    if (actionEl && !actionEl.disabled) return handleAction(actionEl.dataset.action, actionEl);
    const pageEl = event.target.closest("[data-page]");
    if (pageEl && !pageEl.disabled) {
        const target = Number(pageEl.dataset.page);
        if (state.detail.id) return renderDetailPanel(target);
        state.list.page = target;
        return renderList();
    }
    const tabEl = event.target.closest("[data-tab]");
    if (tabEl) {
        state.detail.tab = tabEl.dataset.tab;
        state.detail.page = 1;
        return renderDetail(state.detail.id);
    }
    const openEl = event.target.closest("[data-open]");
    if (openEl) setHashParam("#/customers", { id: openEl.dataset.open });
}

function onInput(event) {
    if (event.target.id === "customers-search") debouncedSearch(event.target.value);
}

const debouncedSearch = debounce((value) => {
    state.list.search = value.trim();
    state.list.page = 1;
    renderList();
}, 350);

async function handleAction(action, el) {
    const id = el.dataset.id;
    switch (action) {
        case "create": return openCustomerForm(null);
        case "edit": return openCustomerForm(id);
        case "archive": return archiveCustomer(id);
        case "groups": return openGroups();
        case "back": return setHashParam("#/customers");
        case "add-address": return openAddressForm(null);
        case "edit-address": return openAddressForm(el.dataset.row);
        case "delete-address": return deleteRecord(`/api/customer-addresses/${id}/`, "Delete this address?", refreshPanel);
        case "set-credit": return openCreditForm();
        case "add-note": return openNoteForm(null);
        case "edit-note": return openNoteForm(el.dataset.row);
        case "delete-note": return deleteRecord(`/api/customer-notes/${id}/`, "Delete this note?", refreshPanel);
        case "toggle-pin": return togglePin(id, el.dataset.pinned === "true");
        case "upload-doc": return openDocumentForm();
        case "download-doc": return runAction(el, () => apiDownload(`/api/customer-documents/${id}/download/`, el.dataset.name || "document"), { errorFallback: "Download failed." });
        case "delete-doc": return deleteRecord(`/api/customer-documents/${id}/`, "Delete this document? This cannot be undone.", refreshPanel);
        default: return undefined;
    }
}

function refreshPanel() {
    return renderDetailPanel(state.detail.page);
}

/* ── List view ────────────────────────────────────────────────────────────── */

async function renderList() {
    state.detail.id = null;
    const container = root();
    if (!document.getElementById("customers-table")) {
        container.innerHTML = `${listHeader()}
        <div class="mb-5 flex flex-wrap items-center gap-3">${searchInput("customers-search", "Search name, phone, email or code")}</div>
        <div id="customers-table"></div>`;
        const searchEl = document.getElementById("customers-search");
        if (searchEl && state.list.search) searchEl.value = state.list.search;
    }
    const target = document.getElementById("customers-table");
    target.innerHTML = table({ columns: [], rows: [], loading: true });
    try {
        const query = buildQuery({ search: state.list.search, page: state.list.page, page_size: PAGE_SIZE });
        const data = await apiList(`/api/customers/${query}`);
        target.innerHTML = `${table({
            columns: [
                { label: "Name", cell: (r) => `<button type="button" data-open="${esc(r.id)}" class="text-left font-semibold text-violet-700 hover:underline">${esc(r.name)}</button>` },
                { label: "Code", cell: (r) => `<span class="font-mono text-xs">${esc(r.customer_code)}</span>` },
                { label: "Phone", cell: (r) => esc(r.phone || "-") },
                { label: "Group", cell: (r) => esc(r.group_name || "-") },
                { label: "Loyalty", align: "right", cell: (r) => esc(r.loyalty_points ?? 0) },
                { label: "Orders", align: "right", cell: (r) => esc(r.order_count ?? 0) },
                { label: "Total spent", align: "right", cell: (r) => esc(formatMoney(r.total_spent)) },
                { label: "Status", cell: (r) => (r.is_active ? badge("Active", "green") : badge("Archived", "slate")) },
            ],
            rows: data.results,
            empty: state.list.search ? "No customers match your search." : "No customers yet. Create the first one.",
            actions: (r) => actionButton("Edit", "edit", { data: { id: r.id } })
                + (r.is_active ? actionButton("Archive", "archive", { tone: "danger", data: { id: r.id } }) : ""),
        })}${pager({ page: data.page, totalPages: data.total_pages, count: data.count })}`;
    } catch (error) {
        target.innerHTML = emptyStateCard("Could not load customers", errorMessage(error));
    }
    createIcons({ icons });
}

async function loadGroups() {
    try {
        state.groups = (await apiList("/api/customer-groups/")).results;
    } catch {
        state.groups = [];
    }
    return state.groups;
}

async function openCustomerForm(id) {
    let customer = {};
    if (id) {
        try { customer = await apiJson(`/api/customers/${id}/`); } catch (error) { return toast(errorMessage(error), "error"); }
    }
    const groups = await loadGroups();
    const groupOptions = [{ value: "", label: "No group" }, ...groups.map((g) => ({ value: g.id, label: g.name }))];
    await openModal({
        title: id ? "Edit customer" : "New customer",
        size: "max-w-2xl",
        submitLabel: id ? "Save changes" : "Create customer",
        html: fieldGrid([
            field({ name: "name", label: "Full name", value: customer.name || "", required: true, full: true }),
            field({ name: "phone", label: "Phone", type: "tel", value: customer.phone || "" }),
            field({ name: "email", label: "Email", type: "email", value: customer.email || "" }),
            field({ name: "date_of_birth", label: "Date of birth", type: "date", value: customer.date_of_birth || "" }),
            field({ name: "group", label: "Group", type: "select", value: customer.group ?? "", options: groupOptions }),
            field({ name: "customer_code", label: "Customer code", value: customer.customer_code || "", help: "Leave blank to auto-generate." }),
            field({ name: "address", label: "Address", type: "textarea", value: customer.address || "", full: true }),
            field({ name: "is_active", label: "Active", type: "checkbox", value: customer.is_active ?? true, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = {
                name: requireValue(d.name, "Customer name is required."),
                phone: d.phone,
                email: d.email,
                date_of_birth: dateOrNull(d.date_of_birth),
                group: d.group ? Number(d.group) : null,
                address: d.address,
                is_active: d.is_active,
            };
            if (d.customer_code) payload.customer_code = d.customer_code;
            const saved = await apiJson(id ? `/api/customers/${id}/` : "/api/customers/", {
                method: id ? "PATCH" : "POST",
                body: JSON.stringify(payload),
            });
            toast(id ? "Customer updated." : `Customer ${saved.customer_code || ""} created.`.trim(), "success");
            if (state.detail.id) await renderDetail(state.detail.id);
            else await renderList();
            return true;
        },
    });
}

async function archiveCustomer(id) {
    const ok = await confirmDialog({
        title: "Archive customer?",
        message: "Archived customers keep their history but are hidden from new sales. You can reactivate them by editing the customer.",
        confirmLabel: "Archive",
    });
    if (!ok) return;
    const result = await runAction(null, () => apiJson(`/api/customers/${id}/archive/`, { method: "POST" }), { successMessage: "Customer archived.", errorFallback: "Could not archive the customer." });
    if (result === undefined) return;
    if (state.detail.id) setHashParam("#/customers");
    else await renderList();
}

/* ── Customer groups ──────────────────────────────────────────────────────── */

/**
 * Group manager. Each row offers Edit and Delete; the add form sits below the
 * table. Row actions close this modal with a pending action, the action runs,
 * and the manager reopens with fresh data.
 */
async function openGroups() {
    for (;;) {
        const groups = await loadGroups();
        const outcome = await openGroupManager(groups);
        if (!outcome) break;
        if (outcome === "created") continue;
        const group = groups.find((g) => g.id === outcome.id);
        if (!group) continue;
        if (outcome.type === "edit") await editGroup(group);
        else await removeGroup(group);
    }
    if (!state.detail.id) await renderList();
}

function openGroupManager(groups) {
    let pending = null;
    const onClick = (event) => {
        const button = event.target.closest?.("[data-group-action]");
        if (!button) return;
        event.preventDefault();
        pending = { type: button.dataset.groupAction, id: Number(button.dataset.id) };
        document.querySelector("[data-ui-backdrop] [data-ui-cancel]")?.click();
    };
    document.addEventListener("click", onClick);
    const actionCell = (g) => `<div class="flex justify-end gap-2">
        <button type="button" data-group-action="edit" data-id="${esc(g.id)}" class="h-8 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50">Edit</button>
        <button type="button" data-group-action="delete" data-id="${esc(g.id)}" class="h-8 rounded-lg border border-rose-200 px-3 text-xs font-semibold text-rose-700 hover:bg-rose-50">Delete</button>
    </div>`;
    return openModal({
        title: "Customer groups",
        size: "max-w-3xl",
        submitLabel: "Add group",
        html: `${table({
            columns: [
                { label: "Group", cell: (g) => `<span class="font-semibold">${esc(g.name)}</span>` },
                { label: "Discount %", align: "right", cell: (g) => esc(g.discount_percent) },
                { label: "Customers", align: "right", cell: (g) => esc(g.customers_count ?? 0) },
                { label: "Status", cell: (g) => (g.is_active ? badge("Active", "green") : badge("Inactive", "slate")) },
                { label: "Actions", align: "right", cell: actionCell },
            ],
            rows: groups,
            empty: "No customer groups yet.",
        })}
        <div class="mt-6 rounded-2xl border border-slate-200 p-5">
            <p class="mb-4 text-sm font-semibold text-slate-800">Add a group</p>
            ${fieldGrid([
                field({ name: "name", label: "Name", required: true }),
                field({ name: "discount_percent", label: "Discount %", type: "number", step: "0.01", min: "0", value: "0" }),
                field({ name: "description", label: "Description", full: true }),
            ])}
        </div>`,
        onSubmit: async (form) => {
            const d = readForm(form);
            await apiJson("/api/customer-groups/", {
                method: "POST",
                body: JSON.stringify({
                    name: requireValue(d.name, "Group name is required."),
                    description: d.description,
                    discount_percent: toNumber(d.discount_percent, "Discount", { min: 0 }),
                    is_active: true,
                }),
            });
            toast("Customer group added.", "success");
            return "created";
        },
    }).finally(() => document.removeEventListener("click", onClick))
        .then((result) => pending ?? result);
}

async function editGroup(group) {
    const saved = await openModal({
        title: `Edit ${group.name}`,
        submitLabel: "Save group",
        html: fieldGrid([
            field({ name: "name", label: "Name", required: true, value: group.name }),
            field({ name: "discount_percent", label: "Discount %", type: "number", step: "0.01", min: "0", value: group.discount_percent }),
            field({ name: "description", label: "Description", full: true, value: group.description || "" }),
            field({
                name: "is_active", label: "Status", type: "select", value: group.is_active ? "true" : "false",
                options: [{ value: "true", label: "Active" }, { value: "false", label: "Inactive" }],
            }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            await apiJson(`/api/customer-groups/${group.id}/`, {
                method: "PATCH",
                body: JSON.stringify({
                    name: requireValue(d.name, "Group name is required."),
                    description: d.description,
                    discount_percent: toNumber(d.discount_percent, "Discount", { min: 0 }),
                    is_active: d.is_active === "true",
                }),
            });
            toast("Customer group saved.", "success");
            return true;
        },
    });
    return saved;
}

async function removeGroup(group) {
    const confirmed = await confirmDialog({
        title: `Delete ${group.name}?`,
        message: group.customers_count
            ? `${group.customers_count} customer(s) will be moved to "No group". This cannot be undone.`
            : "This group has no customers. This cannot be undone.",
        confirmLabel: "Delete group",
    });
    if (!confirmed) return;
    await apiJson(`/api/customer-groups/${group.id}/`, { method: "DELETE" });
    toast("Customer group deleted.", "success");
}

/* ── Detail view ──────────────────────────────────────────────────────────── */

const DETAIL_TABS = [
    { id: "overview", label: "Overview" },
    { id: "addresses", label: "Addresses" },
    { id: "notes", label: "Notes" },
    { id: "loyalty", label: "Loyalty" },
    { id: "activity", label: "Activity" },
    { id: "documents", label: "Documents" },
];

async function renderDetail(id) {
    state.detail.id = id;
    const container = root();
    let summary;
    try {
        summary = await apiJson(`/api/customers/${id}/summary/`);
    } catch (error) {
        container.innerHTML = `${pageHeader({ title: "Customer", actions: secondaryButton("Back to customers", "back") })}${emptyStateCard("Customer not found", errorMessage(error))}`;
        return;
    }
    const c = summary.customer;
    container.innerHTML = `
        ${pageHeader({
            title: c.name,
            subtitle: `${c.customer_code || ""} · ${c.group_name || "No group"}`,
            actions: secondaryButton("Back to customers", "back")
                + actionButton("Edit", "edit", { data: { id: c.id } })
                + (c.is_active ? actionButton("Archive", "archive", { tone: "danger", data: { id: c.id } }) : badge("Archived", "slate")),
        })}
        <div class="mb-6">${tabs(DETAIL_TABS, state.detail.tab)}</div>
        <div id="customer-panel"></div>`;
    await renderDetailPanel(state.detail.page, summary);
}

async function renderDetailPanel(page = 1, summaryCache = null) {
    state.detail.page = page;
    const panel = document.getElementById("customer-panel");
    if (!panel) return;
    const id = state.detail.id;
    const tab = state.detail.tab;
    try {
        if (tab === "overview") {
            const summary = summaryCache || await apiJson(`/api/customers/${id}/summary/`);
            panel.innerHTML = renderOverview(summary);
        } else if (tab === "addresses") {
            const data = await apiList(`/api/customers/${id}/addresses/`);
            panel.innerHTML = `<div class="mb-4 flex justify-end">${primaryButton("Add address", "add-address")}</div>${table({
                columns: [
                    { label: "Kind", cell: (a) => esc(a.kind) },
                    { label: "Label", cell: (a) => esc(a.label || "-") },
                    { label: "Address", cell: (a) => esc([a.line1, a.line2, a.city, a.state, a.postal_code, a.country].filter(Boolean).join(", ")) },
                    { label: "Phone", cell: (a) => esc(a.phone || "-") },
                    { label: "Default", cell: (a) => (a.is_default ? badge("Default", "violet") : "") },
                ],
                rows: data.results,
                empty: "No addresses saved.",
                actions: (a) => actionButton("Edit", "edit-address", { data: { row: a.id } })
                    + actionButton("Delete", "delete-address", { tone: "danger", data: { id: a.id } }),
            })}`;
        } else if (tab === "notes") {
            const data = await apiList(`/api/customers/${id}/notes/`);
            panel.innerHTML = `<div class="mb-4 flex justify-end">${primaryButton("Add note", "add-note")}</div>${table({
                columns: [
                    { label: "Note", cell: (n) => `<div class="max-w-xl whitespace-pre-wrap">${esc(n.body)}</div>` },
                    { label: "Pinned", cell: (n) => (n.pinned ? badge("Pinned", "amber") : "") },
                    { label: "By", cell: (n) => esc(n.created_by_name || "-") },
                    { label: "Created", cell: (n) => esc(formatDateTime(n.created_at)) },
                ],
                rows: data.results,
                empty: "No notes yet.",
                actions: (n) => actionButton(n.pinned ? "Unpin" : "Pin", "toggle-pin", { data: { id: n.id, pinned: n.pinned ? "true" : "false" } })
                    + actionButton("Edit", "edit-note", { data: { row: n.id } })
                    + actionButton("Delete", "delete-note", { tone: "danger", data: { id: n.id } }),
            })}`;
        } else if (tab === "loyalty") {
            const data = await apiList(`/api/customers/${id}/loyalty/?page=${page}&page_size=${PAGE_SIZE}`);
            panel.innerHTML = `${table({
                columns: [
                    { label: "Date", cell: (t) => esc(formatDateTime(t.created_at)) },
                    { label: "Type", cell: (t) => statusBadge(t.type === "earn" ? "active" : t.type === "burn" ? "cancelled" : "open") },
                    { label: "Points", align: "right", cell: (t) => esc(t.points) },
                    { label: "Reference", cell: (t) => esc(t.reference || "-") },
                    { label: "Reason", cell: (t) => esc(t.reason || "-") },
                ],
                rows: data.results,
                empty: "No loyalty activity yet.",
            })}${pager({ page: data.page, totalPages: data.total_pages, count: data.count })}`;
        } else if (tab === "activity") {
            const data = await apiList(`/api/customers/${id}/activity/?page=${page}&page_size=${PAGE_SIZE}`);
            panel.innerHTML = `${table({
                columns: [
                    { label: "When", cell: (a) => esc(formatDateTime(a.created_at)) },
                    { label: "Event", cell: (a) => esc(a.summary || "-") },
                ],
                rows: data.results,
                empty: "No activity recorded.",
            })}${pager({ page: data.page, totalPages: data.total_pages, count: data.count })}`;
        } else if (tab === "documents") {
            const data = await apiList(`/api/customers/${id}/documents/`);
            panel.innerHTML = `<div class="mb-4 flex justify-end">${primaryButton("Upload document", "upload-doc")}</div>${table({
                columns: [
                    { label: "Name", cell: (d) => esc(d.name || "Document") },
                    { label: "Kind", cell: (d) => esc(d.kind || "-") },
                    { label: "Notes", cell: (d) => esc(d.notes || "-") },
                    { label: "Uploaded", cell: (d) => esc(formatDateTime(d.uploaded_at)) },
                    { label: "By", cell: (d) => esc(d.uploaded_by_name || "-") },
                ],
                rows: data.results,
                empty: "No documents uploaded.",
                actions: (d) => actionButton("Download", "download-doc", { data: { id: d.id, name: d.name || "document" } })
                    + actionButton("Delete", "delete-doc", { tone: "danger", data: { id: d.id } }),
            })}`;
        }
    } catch (error) {
        panel.innerHTML = emptyStateCard("Could not load this section", errorMessage(error));
    }
    createIcons({ icons });
}

function renderOverview(summary) {
    const c = summary.customer;
    const credit = summary.credit || {};
    const stat = (label, value) => `<div class="rounded-2xl border border-slate-200 bg-white p-5"><p class="text-xs font-semibold uppercase tracking-wide text-slate-500">${esc(label)}</p><p class="mt-2 text-2xl font-bold text-slate-900 tabular-nums">${esc(value)}</p></div>`;
    return `
    <div class="mb-6 grid grid-cols-4 gap-4">
        ${stat("Total orders", summary.total_orders ?? 0)}
        ${stat("Total spent", formatMoney(summary.total_spent))}
        ${stat("Average order", formatMoney(summary.average_order_value))}
        ${stat("Loyalty points", c.loyalty_points ?? 0)}
    </div>
    <div class="grid grid-cols-2 gap-6">
        <div class="rounded-2xl border border-slate-200 bg-white p-6">
            <h3 class="mb-4 text-base font-bold text-slate-900">Contact</h3>
            <dl class="grid grid-cols-3 gap-y-3 text-sm">
                <dt class="text-slate-500">Phone</dt><dd class="col-span-2 text-slate-800">${esc(c.phone || "-")}</dd>
                <dt class="text-slate-500">Email</dt><dd class="col-span-2 text-slate-800">${esc(c.email || "-")}</dd>
                <dt class="text-slate-500">Address</dt><dd class="col-span-2 text-slate-800">${esc(c.address || "-")}</dd>
                <dt class="text-slate-500">Date of birth</dt><dd class="col-span-2 text-slate-800">${esc(formatDate(c.date_of_birth))}</dd>
                <dt class="text-slate-500">Last purchase</dt><dd class="col-span-2 text-slate-800">${esc(formatDateTime(summary.last_purchase || c.last_purchase))}</dd>
                <dt class="text-slate-500">Status</dt><dd class="col-span-2">${c.is_active ? badge("Active", "green") : badge("Archived", "slate")}</dd>
            </dl>
        </div>
        <div class="rounded-2xl border border-slate-200 bg-white p-6">
            <div class="mb-4 flex items-center justify-between">
                <h3 class="text-base font-bold text-slate-900">Credit limit</h3>
                ${secondaryButton("Set limit", "set-credit")}
            </div>
            <dl class="grid grid-cols-3 gap-y-3 text-sm">
                <dt class="text-slate-500">Limit</dt><dd class="col-span-2 tabular-nums">${esc(formatMoney(credit.limit))}</dd>
                <dt class="text-slate-500">Used</dt><dd class="col-span-2 tabular-nums">${esc(formatMoney(credit.used))}</dd>
                <dt class="text-slate-500">Available</dt><dd class="col-span-2 tabular-nums">${esc(formatMoney(credit.available))}</dd>
                <dt class="text-slate-500">Terms</dt><dd class="col-span-2">${esc(credit.terms_days ?? 0)} days</dd>
            </dl>
        </div>
    </div>`;
}

/* ── Detail forms ─────────────────────────────────────────────────────────── */

async function findRow(path, rowId) {
    const data = await apiList(path);
    return data.results.find((row) => String(row.id) === String(rowId)) || {};
}

async function openAddressForm(addressId) {
    const customerId = state.detail.id;
    const a = addressId ? await findRow(`/api/customers/${customerId}/addresses/`, addressId) : {};
    await openModal({
        title: addressId ? "Edit address" : "Add address",
        size: "max-w-2xl",
        submitLabel: "Save address",
        html: fieldGrid([
            field({ name: "kind", label: "Kind", type: "select", value: a.kind || "shipping", options: [{ value: "billing", label: "Billing" }, { value: "shipping", label: "Shipping" }] }),
            field({ name: "label", label: "Label", value: a.label || "", placeholder: "Home, Office…" }),
            field({ name: "line1", label: "Address line 1", value: a.line1 || "", required: true, full: true }),
            field({ name: "line2", label: "Address line 2", value: a.line2 || "", full: true }),
            field({ name: "city", label: "City", value: a.city || "" }),
            field({ name: "state", label: "State / province", value: a.state || "" }),
            field({ name: "postal_code", label: "Postal code", value: a.postal_code || "" }),
            field({ name: "country", label: "Country", value: a.country || "PK" }),
            field({ name: "phone", label: "Phone", type: "tel", value: a.phone || "" }),
            field({ name: "is_default", label: "Default for this kind", type: "checkbox", value: a.is_default || false, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = { ...d, line1: requireValue(d.line1, "Address line 1 is required.") };
            if (addressId) await apiJson(`/api/customer-addresses/${addressId}/`, { method: "PATCH", body: JSON.stringify(payload) });
            else await apiJson(`/api/customers/${customerId}/addresses/`, { method: "POST", body: JSON.stringify(payload) });
            toast("Address saved.", "success");
            await refreshPanel();
            return true;
        },
    });
}

async function openCreditForm() {
    const credit = await apiJson(`/api/customers/${state.detail.id}/credit-limit/`);
    await openModal({
        title: "Set credit limit",
        size: "max-w-md",
        submitLabel: "Save limit",
        html: fieldGrid([
            field({ name: "limit", label: "Credit limit", type: "number", step: "0.01", min: "0", value: credit.limit ?? "0", required: true, full: true }),
            field({ name: "terms_days", label: "Payment terms (days)", type: "number", step: "1", min: "0", value: credit.terms_days ?? 0, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            await apiJson(`/api/customers/${state.detail.id}/credit-limit/`, {
                method: "POST",
                body: JSON.stringify({
                    limit: toNumber(d.limit, "Credit limit", { min: 0 }),
                    terms_days: toNumber(d.terms_days, "Payment terms", { min: 0 }),
                }),
            });
            toast("Credit limit updated.", "success");
            await renderDetail(state.detail.id);
            return true;
        },
    });
}

async function openNoteForm(noteId) {
    const note = noteId ? await findRow(`/api/customers/${state.detail.id}/notes/`, noteId) : {};
    await openModal({
        title: noteId ? "Edit note" : "Add note",
        size: "max-w-lg",
        submitLabel: "Save note",
        html: fieldGrid([
            field({ name: "body", label: "Note", type: "textarea", value: note.body || "", required: true, full: true }),
            field({ name: "pinned", label: "Pin to top", type: "checkbox", value: note.pinned || false, full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const payload = { body: requireValue(d.body, "Note text is required."), pinned: d.pinned };
            if (noteId) await apiJson(`/api/customer-notes/${noteId}/`, { method: "PATCH", body: JSON.stringify(payload) });
            else await apiJson(`/api/customers/${state.detail.id}/notes/`, { method: "POST", body: JSON.stringify(payload) });
            toast("Note saved.", "success");
            await refreshPanel();
            return true;
        },
    });
}

async function togglePin(noteId, currentlyPinned) {
    try {
        await apiJson(`/api/customer-notes/${noteId}/`, { method: "PATCH", body: JSON.stringify({ pinned: !currentlyPinned }) });
        await refreshPanel();
    } catch (error) {
        toast(errorMessage(error), "error");
    }
}

async function openDocumentForm() {
    const customerId = state.detail.id;
    await openModal({
        title: "Upload document",
        size: "max-w-lg",
        submitLabel: "Upload",
        html: fieldGrid([
            field({ name: "name", label: "Document name", required: true, full: true }),
            field({ name: "kind", label: "Kind", placeholder: "ID, contract, tax certificate…", full: true }),
            field({ name: "notes", label: "Notes", type: "textarea", full: true }),
            `<div class="col-span-2">
                <label class="mb-1.5 block text-sm font-medium text-slate-700" for="doc-file">File <span class="text-rose-500">*</span></label>
                <input id="doc-file" type="file" accept=".pdf,.png,.jpg,.jpeg,.doc,.docx" class="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-violet-50 file:px-4 file:py-2 file:font-semibold file:text-violet-700">
                <p class="mt-1 text-xs text-slate-500">Maximum 10 MB.</p>
            </div>`,
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const file = form.querySelector("#doc-file").files[0];
            if (!file) throw new Error("Choose a file to upload.");
            if (file.size > 10 * 1024 * 1024) throw new Error("Customer documents must not exceed 10 MB.");
            const body = new FormData();
            body.append("file", file);
            body.append("name", requireValue(d.name, "Document name is required."));
            body.append("kind", d.kind || "");
            body.append("notes", d.notes || "");
            await apiJson(`/api/customers/${customerId}/documents/`, { method: "POST", body });
            toast("Document uploaded.", "success");
            await refreshPanel();
            return true;
        },
    });
}

async function deleteRecord(path, message, afterDelete) {
    const ok = await confirmDialog({ title: "Delete?", message, confirmLabel: "Delete" });
    if (!ok) return;
    try {
        await apiJson(path, { method: "DELETE" });
        toast("Deleted.", "success");
        await afterDelete();
    } catch (error) {
        toast(errorMessage(error), "error");
    }
}
