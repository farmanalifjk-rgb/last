/**
 * Generic views built from the operations map. A hub config (hubs.js) picks a
 * view and its endpoints; the view builds the UI from the schema.
 *
 *   resourceView  list, create, edit, delete, row actions and toolbar actions
 *   queryView     GET with query filters, rendered result, optional exports
 *   settingsView  object GET with a form, saved with PATCH or PUT
 *   actionView    one request with an optional form and a result panel
 *   uploadView    multipart file upload
 *   mountHub      tab bar; each tab mounts one of the views above
 *
 * Every view mounts into a fresh container, so re-mounting a tab never stacks
 * event listeners. All server data is escaped before it reaches the DOM.
 */
import { createIcons, icons } from "lucide";
import { apiDownload, apiFetch, apiJson } from "../../services/api.js";
import {
    esc, formatDateTime, toast, errorMessage, openModal, confirmDialog, table, badge, pager,
    emptyStateCard, primaryButton, secondaryButton, runAction, tabs, hashParam, setHashParam,
} from "../../shared/ui.js";
import { findOp, getOp, fillPath, withQuery, callOp, listOp } from "./ops.js";
import { mergeSpecs, resolveRefs, fieldsHtml, readBody, queryFromForm, humanize } from "./forms.js";

const PAGE_SIZE = 10;
const LIST_SKIP = /(^id$|_id$|^tenant|_at$|password|secret|token)/;
const SETTING_SKIP = new Set(["id", "tenant", "created_at", "updated_at"]);


const isScalar = (v) => v === null || v === undefined || typeof v !== "object";

function cellText(value, name = "") {
    if (value === null || value === undefined || value === "") return `<span class="text-slate-400">-</span>`;
    if (typeof value === "boolean") return badge(value ? "Yes" : "No", value ? "green" : "slate");
    if (name.endsWith("_at") || /T\d\d:\d\d/.test(String(value))) return esc(formatDateTime(value));
    if (typeof value === "object") {
        const text = JSON.stringify(value);
        return `<span class="font-mono text-xs text-slate-600">${esc(text.length > 80 ? `${text.slice(0, 80)}…` : text)}</span>`;
    }
    return esc(value);
}

/** Columns from the list response: the first readable scalar fields. */
function defaultColumns(op, limit = 6) {
    const fields = (op?.response?.fields || []).filter((f) => f.type !== "json" && !LIST_SKIP.test(f.name));
    return fields.slice(0, limit).map((f) => ({ label: humanize(f.name), cell: (row) => cellText(row[f.name], f.name) }));
}

/** Columns from the first row when the schema does not describe the response. */
function columnsFromRows(rows) {
    if (!rows.length) return [];
    return Object.keys(rows[0]).filter((k) => !LIST_SKIP.test(k) && rows.some((r) => isScalar(r[k]))).slice(0, 6)
        .map((k) => ({ label: humanize(k), cell: (row) => cellText(row[k], k) }));
}

/** Table of plain rows. Columns are the scalar keys of the first row. */
export function rowsTable(rows) {
    if (!rows.length) return emptyStateCard("No rows", "Nothing to show for these filters.");
    const keys = Object.keys(rows[0]).filter((k) => rows.some((r) => isScalar(r[k]))).slice(0, 10);
    return table({
        columns: keys.map((k) => ({ label: humanize(k), cell: (row) => cellText(row[k], k) })),
        rows,
        empty: "No rows.",
    });
}

/** Render any API response: arrays, paginated results, nested objects, scalars. */
export function renderResult(data, depth = 0) {
    if (Array.isArray(data)) return rowsTable(data.filter((r) => r && typeof r === "object"));
    if (data && typeof data === "object") {
        if (Array.isArray(data.results)) {
            const count = data.count !== undefined ? `<p class="mb-3 text-sm text-slate-500">${esc(data.count)} record(s)</p>` : "";
            return count + rowsTable(data.results);
        }
        if (depth > 2) return `<pre class="whitespace-pre-wrap text-xs text-slate-600">${esc(JSON.stringify(data, null, 2))}</pre>`;
        const entries = Object.entries(data);
        const scalars = entries.filter(([, v]) => isScalar(v));
        const nested = entries.filter(([, v]) => !isScalar(v));
        const scalarHtml = scalars.length
            ? `<dl class="grid grid-cols-2 gap-x-6 gap-y-3 rounded-2xl border border-slate-200 bg-white p-5">${scalars.map(([k, v]) => `<dt class="text-sm font-medium text-slate-500">${esc(humanize(k))}</dt><dd class="text-sm text-slate-900">${cellText(v, k)}</dd>`).join("")}</dl>`
            : "";
        const nestedHtml = nested.map(([k, v]) => `<div class="mt-5"><h4 class="mb-2 text-sm font-semibold text-slate-800">${esc(humanize(k))}</h4>${renderResult(v, depth + 1)}</div>`).join("");
        return scalarHtml + nestedHtml;
    }
    return `<p class="text-sm text-slate-800">${cellText(data)}</p>`;
}

/** Primary button that submits its form. */
function submitButton(label) {
    return primaryButton(label, "").replace('type="button"', 'type="submit"');
}

/** Specs for a request body: schema fields, or the declared fields when the schema is untyped. */
function bodySpecs(op, { overrides = {}, genericFields = null } = {}) {
    const base = genericFields || (op.body || []);
    return mergeSpecs(base, overrides);
}

/** Path placeholders not fixed by `values`, as integer or string inputs. */
export function pathSpecsFor(template, values = {}) {
    return [...new Set([...template.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))]
        .filter((name) => !(name in values))
        .map((name) => ({ name, label: humanize(name), type: /(^id$|_id$)/.test(name) ? "integer" : "string", required: true }));
}

/* ─────────────────────────────── resourceView ─────────────────────────────── */

/**
 * cfg
 *   base            schema list path, e.g. "/api/stores/"
 *   title           singular noun for buttons, e.g. "store"
 *   plural?         plural noun for the empty state
 *   columns?        [{ label, cell(row) }] replaces the default columns
 *   overrides?      { field: { label, type, options, help, full, placeholder } }
 *   genericFields?  specs for create/edit when the schema is untyped
 *   refs?           { field: { refPath, refLabel } } foreign-key select options
 *   search?         list query parameter for the search box, e.g. "search"
 *   listQuery?      fixed query parameters for the list
 *   readOnly?       hide create, edit and delete
 *   rowActions?     [{ label, suffix, method, confirm?, danger?, fields?, genericFields?, overrides?, success?, show?, when? }]
 *                   suffix follows the item path, e.g. "{id}/approve/"
 *   toolbar?        [{ label, suffix, method, fields?, genericFields?, overrides?, success?, confirm?, show? }]
 */
export function resourceView(el, cfg) {
    const base = cfg.base;
    const item = `${base}{id}/`;
    const listDef = getOp("GET", base);
    const createOp = cfg.readOnly ? null : findOp("POST", base);
    const updateOp = cfg.readOnly ? null : (findOp("PATCH", item) || findOp("PUT", item));
    const updateMethod = findOp("PATCH", item) ? "PATCH" : "PUT";
    const deleteOp = cfg.readOnly ? null : findOp("DELETE", item);
    const rowActions = cfg.rowActions || [];
    const toolbar = cfg.toolbar || [];
    const templateOf = (a) => a.template || `${base}${a.suffix}`;
    rowActions.forEach((a) => getOp(a.method, templateOf(a)));
    toolbar.forEach((a) => getOp(a.method, templateOf(a)));
    const declaredColumns = cfg.columns || defaultColumns(listDef);

    const container = document.createElement("div");
    container.className = "space-y-5";
    el.replaceChildren(container);
    const state = { page: 1, rows: [], count: 0, totalPages: 1, q: "" };

    async function resolveSpecs(op, declared) {
        const specs = bodySpecs(op, { overrides: cfg.overrides, genericFields: declared || null });
        const refSpecs = specs.filter((s) => cfg.refs && cfg.refs[s.name]);
        refSpecs.forEach((s) => Object.assign(s, cfg.refs[s.name]));
        await resolveRefs(refSpecs);
        return specs;
    }

    async function load() {
        container.innerHTML = `<p class="text-sm text-slate-500">Loading…</p>`;
        try {
            const query = { page: state.page, page_size: PAGE_SIZE, ...(cfg.listQuery || {}) };
            if (cfg.search && state.q) query[cfg.search] = state.q;
            const data = await listOp(base, query);
            state.rows = data.results;
            state.columns = declaredColumns.length ? declaredColumns : columnsFromRows(data.results);
            state.count = data.count ?? data.results.length;
            state.totalPages = data.total_pages ?? 1;
            render();
        } catch (error) {
            container.innerHTML = emptyStateCard("Could not load", errorMessage(error));
        }
    }

    function render() {
        const buttons = [];
        if (cfg.search) buttons.push(`<input data-rv="search" type="search" value="${esc(state.q)}" placeholder="Search" class="h-10 w-64 rounded-xl border border-slate-200 bg-white px-3 text-sm">`);
        if (createOp) buttons.push(primaryButton(`New ${cfg.title}`, "", "h-10 px-4 text-sm").replace('data-action=""', 'data-rv="new"'));
        toolbar.forEach((a, i) => buttons.push(secondaryButton(a.label, "", "").replace('data-action=""', `data-rv="tool" data-idx="${i}"`)));
        const hasRowActions = !!(updateOp || deleteOp || rowActions.length);
        container.innerHTML = `
            <div class="flex flex-wrap items-center justify-between gap-3">
                <p class="text-sm text-slate-500">${esc(state.count)} record(s)</p>
                <div class="flex flex-wrap items-center gap-2">${buttons.join("")}</div>
            </div>
            ${table({
                columns: (state.columns || []).map((c) => ({ label: c.label, align: c.align, cell: c.cell })),
                rows: state.rows,
                empty: `No ${cfg.plural || `${cfg.title}s`} yet.`,
                actions: hasRowActions ? (row) => rowButtons(row) : null,
            })}
            ${pager({ page: state.page, totalPages: state.totalPages, count: state.count })}`;
        createIcons({ icons });
    }

    function rowButtons(row) {
        const out = [];
        if (updateOp) out.push(btn("edit", "", row.id, "Edit"));
        rowActions.forEach((a, i) => {
            if (!a.when || a.when(row)) out.push(btn("row", i, row.id, a.label, a.danger));
        });
        if (deleteOp) out.push(btn("delete", "", row.id, "Delete", true));
        return `<div class="flex flex-wrap justify-end gap-2">${out.join("")}</div>`;
    }

    function btn(kind, idx, id, label, danger = false) {
        const tone = danger ? "border-rose-200 text-rose-700 hover:bg-rose-50" : "border-slate-200 text-slate-700 hover:bg-slate-50";
        return `<button type="button" data-rv="${kind}" data-idx="${esc(idx)}" data-id="${esc(id)}" class="h-8 rounded-lg border ${tone} px-3 text-xs font-semibold">${esc(label)}</button>`;
    }

    async function openForm(mode, row = null) {
        const op = mode === "create" ? createOp : updateOp;
        const specs = await resolveSpecs(op, mode === "create" ? cfg.createFields : cfg.updateFields);
        await openModal({
            title: mode === "create" ? `New ${cfg.title}` : `Edit ${cfg.title}`,
            size: "max-w-2xl",
            submitLabel: mode === "create" ? "Create" : "Save",
            html: fieldsHtml(specs, row || {}),
            onSubmit: async (form) => {
                const body = readBody(form, specs);
                if (mode === "create") await callOp("POST", base, { body });
                else await callOp(updateMethod, item, { values: { id: row.id }, body });
                toast(`${cfg.title} ${mode === "create" ? "created" : "saved"}.`, "success");
                return true;
            },
        });
        await load();
    }

    /** Run a row or toolbar action. Results with `show` open in a dialog after any form closes. */
    async function runRowAction(action, row) {
        const template = templateOf(action);
        const op = getOp(action.method, template);
        const values = row ? { id: row.id, order_id: row.id } : {};
        const showResult = async (data) => {
            if (action.show) {
                await openModal({ title: action.label, size: "max-w-3xl", submitLabel: "Close", hideSubmit: true, html: renderResult(data ?? { status: "Done." }) });
            } else {
                toast(action.success || `${action.label} done.`, "success");
            }
        };
        const declared = action.fields || (op.bodyGeneric ? action.genericFields : null);
        if (declared && declared.length) {
            const specs = mergeSpecs(action.fields || declared, action.overrides || {});
            await resolveRefs(specs.filter((s) => cfg.refs && cfg.refs[s.name]).map((s) => Object.assign(s, cfg.refs[s.name])));
            let data;
            const ok = await openModal({
                title: action.label,
                submitLabel: action.label,
                html: fieldsHtml(specs),
                danger: !!action.danger,
                onSubmit: async (form) => {
                    data = await callOp(action.method, template, { values, body: readBody(form, specs) });
                    return true;
                },
            });
            if (ok) { await showResult(data); await load(); }
            return;
        }
        if (action.confirm) {
            const ok = await confirmDialog({ title: action.label, message: action.confirm, confirmLabel: action.label, danger: !!action.danger });
            if (!ok) return;
        }
        try {
            await showResult(await callOp(action.method, template, { values }));
        } catch (error) {
            toast(errorMessage(error, `Could not ${action.label.toLowerCase()}.`), "error");
        }
        await load();
    }

    container.addEventListener("click", async (event) => {
        const pageBtn = event.target.closest("[data-page]");
        if (pageBtn && !pageBtn.disabled) {
            state.page = Number(pageBtn.dataset.page);
            return load();
        }
        const button = event.target.closest("[data-rv]");
        if (!button) return;
        event.preventDefault();
        const kind = button.dataset.rv;
        const row = state.rows.find((r) => String(r.id) === button.dataset.id);
        try {
            if (kind === "new") return await openForm("create");
            if (kind === "edit") return await openForm("edit", row);
            if (kind === "row") return await runRowAction(rowActions[Number(button.dataset.idx)], row);
            if (kind === "tool") return await runRowAction(toolbar[Number(button.dataset.idx)], null);
            if (kind === "delete") {
                const ok = await confirmDialog({ title: `Delete this ${cfg.title}?`, message: "This cannot be undone.", confirmLabel: "Delete" });
                if (!ok) return;
                await callOp("DELETE", item, { values: { id: row.id } });
                toast(`${cfg.title} deleted.`, "success");
                return await load();
            }
        } catch (error) {
            toast(errorMessage(error, "Action failed."), "error");
        }
    });

    let timer;
    container.addEventListener("input", (event) => {
        if (!event.target.matches("[data-rv='search']")) return;
        clearTimeout(timer);
        timer = setTimeout(() => { state.q = event.target.value.trim(); state.page = 1; load(); }, 300);
    });

    load();
}

/* ─────────────────────────────── queryView ─────────────────────────────── */

/**
 * GET with filters taken from the operation's query parameters.
 *   path            schema path with no placeholders
 *   exports?        [{ label, path, filename? }] download endpoints that take the same filters
 *   defaults?       { param: value }
 *   autoRun?        run on open (default true when no filter is required)
 */
export function queryView(el, cfg) {
    const op = getOp("GET", cfg.path);
    const url = fillPath(cfg.path, cfg.values || {});
    const specs = (op.params || []).map((p) => {
        const type = p.enum ? "enum" : /date/.test(p.name) ? "date" : p.type === "integer" ? "integer" : p.type === "number" ? "number" : "string";
        return {
            name: p.name, label: humanize(p.name), type, required: p.required,
            options: p.enum ? p.enum.map((v) => ({ value: v, label: humanize(String(v)) })) : undefined,
        };
    });
    const exportsList = (cfg.exports || []).map((e) => { getOp("GET", e.path); return e; });
    if (cfg.download) {
        const label = cfg.label || "Download";
        el.innerHTML = `<form data-qv="form" class="rounded-2xl border border-slate-200 bg-white p-5">
            ${specs.length ? fieldsHtml(specs, cfg.defaults || {}) : `<p class="text-sm text-slate-500">No filters.</p>`}
            <div class="mt-5 flex justify-end">${submitButton(label)}</div>
        </form><div data-qv="result"></div>`;
        const dlForm = el.querySelector("[data-qv='form']");
        dlForm.addEventListener("submit", (event) => {
            event.preventDefault();
            runAction(null, () => apiDownload(withQuery(url, queryFromForm(dlForm, specs)), cfg.filename || filenameFor(cfg.path)), { errorFallback: "Could not download." });
        });
        return;
    }
    const defaults = cfg.defaults || {};
    const container = document.createElement("div");
    container.className = "space-y-5";
    el.replaceChildren(container);
    container.innerHTML = `
        <form data-qv="form" class="rounded-2xl border border-slate-200 bg-white p-5">
            ${specs.length ? fieldsHtml(specs, defaults) : `<p class="text-sm text-slate-500">No filters.</p>`}
            <div class="mt-5 flex flex-wrap justify-end gap-2">
                ${exportsList.map((e, i) => secondaryButton(e.label, "", "").replace('data-action=""', `data-qv="export" data-idx="${i}"`)).join("")}
                ${submitButton("Run")}
            </div>
        </form>
        <div data-qv="result"></div>`;
    const form = container.querySelector("[data-qv='form']");
    const result = container.querySelector("[data-qv='result']");

    async function run() {
        result.innerHTML = `<p class="text-sm text-slate-500">Loading…</p>`;
        try {
            if (cfg.download) {
                await apiDownload(withQuery(url, queryFromForm(form, specs)), cfg.filename || filenameFor(cfg.path));
                result.innerHTML = `<p class="text-sm text-slate-500">Download started.</p>`;
                return;
            }
            const data = await apiJson(withQuery(url, queryFromForm(form, specs)));
            result.innerHTML = renderResult(data);
            createIcons({ icons });
        } catch (error) {
            result.innerHTML = emptyStateCard("Could not load", errorMessage(error));
        }
    }

    form.addEventListener("submit", (event) => { event.preventDefault(); run(); });
    container.addEventListener("click", (event) => {
        const button = event.target.closest("[data-qv='export']");
        if (!button) return;
        const e = exportsList[Number(button.dataset.idx)];
        const filename = e.filename || e.path.split("/").filter(Boolean).slice(-2).join("-");
        runAction(null, () => apiDownload(withQuery(e.path, queryFromForm(form, specs)), filename), { errorFallback: "Could not export." });
    });
    if (cfg.autoRun !== false && !cfg.download && specs.every((s) => !s.required)) run();
}

function filenameFor(path) {
    return path.split("/").filter(Boolean).slice(-3).join("-") || "export";
}

/* ─────────────────────────────── settingsView ─────────────────────────────── */

function inferType(value) {
    if (typeof value === "boolean") return "boolean";
    if (typeof value === "number") return Number.isInteger(value) ? "integer" : "number";
    if (value !== null && typeof value === "object") return "json";
    return "string";
}

/**
 * Settings section. GET the object, build the form from its keys, save with PATCH or PUT.
 *   path, overrides?
 */
export function settingsView(el, cfg) {
    getOp("GET", cfg.path);
    const writeMethod = findOp("PATCH", cfg.path) ? "PATCH" : findOp("PUT", cfg.path) ? "PUT" : null;
    const container = document.createElement("div");
    el.replaceChildren(container);

    async function load() {
        container.innerHTML = `<p class="text-sm text-slate-500">Loading…</p>`;
        try {
            const data = await apiJson(cfg.path);
            const specs = Object.keys(data)
                .filter((k) => !SETTING_SKIP.has(k))
                .map((k) => {
                    const type = inferType(data[k]);
                    const long = type === "string" && String(data[k] ?? "").length > 160;
                    return { name: k, label: humanize(k), type: long ? "textarea" : type, required: false, nullable: data[k] === null };
                });
            const merged = mergeSpecs(specs, cfg.overrides || {});
            container.innerHTML = `
                <form data-sv="form" class="rounded-2xl border border-slate-200 bg-white p-6">
                    ${fieldsHtml(merged, data)}
                    <div class="mt-6 flex justify-end">${writeMethod
                        ? submitButton("Save settings")
                        : `<p class="text-sm text-slate-500">This section is read-only.</p>`}</div>
                </form>`;
            container.querySelector("[data-sv='form']").addEventListener("submit", async (event) => {
                event.preventDefault();
                if (!writeMethod) return;
                try {
                    const body = readBody(event.currentTarget, merged, { includeEmpty: true });
                    await callOp(writeMethod, cfg.path, { body });
                    toast("Settings saved.", "success");
                } catch (error) {
                    toast(errorMessage(error, "Could not save."), "error");
                }
            });
        } catch (error) {
            container.innerHTML = emptyStateCard("Could not load settings", errorMessage(error));
        }
    }
    load();
}

/* ─────────────────────────────── actionView ─────────────────────────────── */

/**
 * One request with an optional form and a result panel.
 *   method, path, label
 *   pathParams?   [{ name, label }] integer inputs that fill {placeholders}
 *   fields?       specs for untyped (generic) request bodies
 *   overrides?    field overrides for the body
 *   description?
 */
export function actionView(el, cfg) {
    const op = getOp(cfg.method, cfg.path);
    const pathSpecs = (cfg.pathParams || pathSpecsFor(cfg.path, cfg.values)).map((p) => ({ type: "string", ...p, required: true }));
    const queryDefs = cfg.method === "GET" ? (op.params || []).map(paramSpec) : [];
    const specs = cfg.method === "GET" ? queryDefs : bodySpecs(op, { overrides: cfg.overrides, genericFields: cfg.fields || null });
    const container = document.createElement("div");
    container.className = "space-y-5";
    el.replaceChildren(container);
    container.innerHTML = `
        <div class="rounded-2xl border border-slate-200 bg-white p-6">
            ${cfg.description ? `<p class="mb-5 text-sm text-slate-600">${esc(cfg.description)}</p>` : ""}
            <form data-av="form" class="space-y-5">
                ${pathSpecs.length || specs.length ? fieldsHtml([...pathSpecs, ...specs]) : `<p class="text-sm text-slate-500">No input needed.</p>`}
                <div class="flex justify-end">${submitButton(cfg.label)}</div>
            </form>
        </div>
        <div data-av="result"></div>`;
    const form = container.querySelector("[data-av='form']");
    const result = container.querySelector("[data-av='result']");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const values = { ...(cfg.values || {}), ...readBody(form, pathSpecs) };
            let data;
            if (cfg.method === "GET") {
                data = await apiJson(withQuery(fillPath(cfg.path, values), queryFromForm(form, specs)));
            } else {
                const body = specs.length ? readBody(form, specs) : undefined;
                data = await callOp(cfg.method, cfg.path, { values, body });
            }
            result.innerHTML = `<div class="rounded-2xl border border-slate-200 bg-white p-6">${renderResult(data ?? { status: "Done." })}</div>`;
            createIcons({ icons });
            toast(`${cfg.label} done.`, "success");
        } catch (error) {
            toast(errorMessage(error, "Action failed."), "error");
        }
    });
}

/** Query-string parameter from a schema parameter entry. */
export function paramSpec(p) {
    const type = p.enum ? "enum" : /date/.test(p.name) ? "date" : p.type === "integer" ? "integer" : p.type === "number" ? "number" : "string";
    return { name: p.name, label: humanize(p.name), type, required: !!p.required, options: p.enum ? p.enum.map((v) => ({ value: v, label: humanize(String(v)) })) : undefined };
}

/* ─────────────────────────────── uploadView ─────────────────────────────── */

/**
 * Multipart upload.
 *   method, path, label, fileField (default "file"), accept?, fileLabel?
 *   fields?, overrides?   extra form fields sent with the file
 */
export function uploadView(el, cfg) {
    getOp(cfg.method, cfg.path);
    const pathSpecs = (cfg.pathParams || pathSpecsFor(cfg.path, cfg.values)).map((p) => ({ type: "string", ...p, required: true }));
    const specs = mergeSpecs(cfg.fields || [], cfg.overrides || {});
    const container = document.createElement("div");
    container.className = "space-y-5";
    el.replaceChildren(container);
    container.innerHTML = `
        <div class="rounded-2xl border border-slate-200 bg-white p-6">
            ${cfg.description ? `<p class="mb-5 text-sm text-slate-600">${esc(cfg.description)}</p>` : ""}
            <form data-uv="form" class="space-y-5">
                ${pathSpecs.length ? fieldsHtml(pathSpecs) : ""}
                <div>
                    <label class="mb-1.5 block text-sm font-medium text-slate-700">${esc(cfg.fileLabel || "File")} <span class="text-rose-500">*</span></label>
                    <input name="__file" type="file" accept="${esc(cfg.accept || "")}" required class="block w-full text-sm text-slate-700">
                </div>
                ${specs.length ? fieldsHtml(specs) : ""}
                <div class="flex justify-end">${submitButton(cfg.label)}</div>
            </form>
        </div>
        <div data-uv="result"></div>`;
    const form = container.querySelector("[data-uv='form']");
    const result = container.querySelector("[data-uv='result']");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const file = form.elements.namedItem("__file").files[0];
        if (!file) return toast("Choose a file first.", "error");
        let url;
        try {
            url = fillPath(cfg.path, { ...(cfg.values || {}), ...readBody(form, pathSpecs) });
        } catch (error) {
            return toast(errorMessage(error), "error");
        }
        const data = new FormData();
        data.append(cfg.fileField || "file", file);
        for (const spec of specs) {
            const input = form.elements.namedItem(spec.name);
            if (!input) continue;
            if (spec.type === "boolean") data.append(spec.name, String(input.checked));
            else if (String(input.value).trim() !== "") data.append(spec.name, input.value);
        }
        try {
            const response = await apiFetch(url, { method: cfg.method, body: data });
            const isJson = (response.headers.get("content-type") || "").includes("json");
            const payload = isJson ? await response.json() : await response.text();
            if (!response.ok) throw new Error(payload?.error?.message || payload?.detail || `Upload failed (${response.status}).`);
            result.innerHTML = `<div class="rounded-2xl border border-slate-200 bg-white p-6">${renderResult(payload)}</div>`;
            createIcons({ icons });
            toast(`${cfg.label} finished.`, "success");
        } catch (error) {
            toast(errorMessage(error, "Upload failed."), "error");
        }
    });
}

/* ─────────────────────────────── hub ─────────────────────────────── */

/**
 * Tab bar for a hub page. The active tab comes from ?tab=. Each tab.mount(el)
 * receives a fresh body element.
 *   tabs: [{ id, label, mount(el) }]
 */
export function mountHub(root, { tabs: items, defaultTab, routePath }) {
    const requested = hashParam("tab");
    const active = items.find((t) => t.id === requested) || items.find((t) => t.id === defaultTab) || items[0];
    root.innerHTML = `${tabs(items.map((t) => ({ id: t.id, label: t.label })), active.id)}<div data-hub-body class="mt-6"></div>`;
    root.addEventListener("click", (event) => {
        const tab = event.target.closest("[data-tab]");
        if (tab && tab.dataset.tab !== active.id) setHashParam(routePath, { tab: tab.dataset.tab });
    });
    const body = root.querySelector("[data-hub-body]");
    try {
        active.mount(body);
    } catch (error) {
        body.innerHTML = emptyStateCard("Could not open this section", errorMessage(error));
    }
    createIcons({ icons });
}
