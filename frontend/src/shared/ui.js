/**
 * Shared UI kit for the business pages (customers, purchasing, transfers,
 * adjustments). Everything rendered here escapes its inputs by default.
 *
 * Design notes:
 *  - Pages use event delegation on their own root element (data-action
 *    attributes) instead of inline onclick globals, so user data never has
 *    to be embedded in JavaScript strings.
 *  - Modals are created on demand in a single root element and return a
 *    Promise so callers can await the user's decision.
 */
import { escapeHtml, formatMoney, formatDate, formatDateTime, safeUrl } from "./format.js";

export const esc = escapeHtml;
export { formatMoney, formatDate, formatDateTime, safeUrl };

/* ── Toasts ───────────────────────────────────────────────────────────────── */

function toastRoot() {
    let root = document.getElementById("ui-toast-root");
    if (!root) {
        root = document.createElement("div");
        root.id = "ui-toast-root";
        root.className = "fixed bottom-6 right-6 z-[70] flex flex-col gap-2 pointer-events-none";
        document.body.appendChild(root);
    }
    return root;
}

const TOAST_STYLES = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    error: "border-rose-200 bg-rose-50 text-rose-800",
    info: "border-slate-200 bg-white text-slate-800",
};

export function toast(message, type = "info") {
    const el = document.createElement("div");
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.className = `pointer-events-auto max-w-sm rounded-xl border px-4 py-3 text-sm font-medium shadow-lg ${TOAST_STYLES[type] || TOAST_STYLES.info}`;
    el.textContent = String(message ?? "");
    toastRoot().appendChild(el);
    setTimeout(() => el.remove(), type === "error" ? 6000 : 3500);
}

/** Convert an error (API or network) to a readable message. */
export function errorMessage(error, fallback = "Something went wrong.") {
    return error?.message || fallback;
}

/* ── Modal ────────────────────────────────────────────────────────────────── */

function modalRoot() {
    let root = document.getElementById("ui-modal-root");
    if (!root) {
        root = document.createElement("div");
        root.id = "ui-modal-root";
        document.body.appendChild(root);
    }
    return root;
}

/**
 * Open a modal containing `html`. `onSubmit(form)` runs on submit; it may
 * throw to show an inline error and keep the modal open. Resolves with the
 * value returned by onSubmit when the modal succeeds, or null if cancelled.
 */
export function openModal({ title, html, submitLabel = "Save", size = "max-w-lg", onSubmit, danger = false, hideSubmit = false }) {
    return new Promise((resolve) => {
        const root = modalRoot();
        const titleId = `ui-modal-title-${Date.now()}`;
        root.innerHTML = `
        <div class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/40 p-6 backdrop-blur-sm" data-ui-backdrop>
            <div role="dialog" aria-modal="true" aria-labelledby="${titleId}" class="flex max-h-[90vh] w-full ${size} flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
                <div class="flex items-center justify-between border-b border-slate-100 px-7 py-5">
                    <h2 id="${titleId}" class="text-xl font-bold text-slate-900">${esc(title)}</h2>
                    <button type="button" data-ui-cancel class="flex h-9 w-9 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-100" aria-label="Close">✕</button>
                </div>
                <form data-ui-form class="flex min-h-0 flex-1 flex-col">
                    <div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-7 py-6">${html}</div>
                    <div data-ui-error class="hidden mx-7 mb-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"></div>
                    <div class="flex justify-end gap-3 border-t border-slate-100 px-7 py-4">
                        <button type="button" data-ui-cancel class="h-11 rounded-xl border border-slate-200 px-5 text-sm font-semibold text-slate-700 hover:bg-slate-50">Cancel</button>
                        ${hideSubmit ? "" : `<button type="submit" data-ui-submit class="h-11 rounded-xl px-6 text-sm font-semibold text-white shadow-sm ${danger ? "bg-rose-600 hover:bg-rose-700" : "bg-violet-600 hover:bg-violet-700"}">${esc(submitLabel)}</button>`}
                    </div>
                </form>
            </div>
        </div>`;

        const form = root.querySelector("[data-ui-form]");
        const errorBox = root.querySelector("[data-ui-error]");
        let settled = false;
        const close = (value = null) => {
            if (settled) return;
            settled = true;
            document.removeEventListener("keydown", onKey);
            root.innerHTML = "";
            resolve(value);
        };
        const onKey = (event) => { if (event.key === "Escape") close(null); };
        document.addEventListener("keydown", onKey);

        root.querySelectorAll("[data-ui-cancel]").forEach((btn) => btn.addEventListener("click", () => close(null)));
        root.querySelector("[data-ui-backdrop]").addEventListener("mousedown", (event) => {
            if (event.target.hasAttribute("data-ui-backdrop")) close(null);
        });

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (!onSubmit) return close(true);
            const submit = form.querySelector("[data-ui-submit]");
            errorBox.classList.add("hidden");
            setBusy(submit, true);
            try {
                const result = await onSubmit(form);
                close(result ?? true);
            } catch (error) {
                errorBox.textContent = errorMessage(error, "Could not save. Please try again.");
                errorBox.classList.remove("hidden");
                setBusy(submit, false);
            }
        });

        // Focus the first editable control for keyboard users.
        form.querySelector("input:not([type=hidden]), select, textarea")?.focus();
    });
}

/** Confirmation dialog. Resolves true when the user confirms. */
export async function confirmDialog({ title = "Are you sure?", message = "", confirmLabel = "Confirm", danger = true }) {
    const result = await openModal({
        title,
        size: "max-w-md",
        submitLabel: confirmLabel,
        danger,
        html: `<p class="text-sm text-slate-600">${esc(message)}</p>`,
        onSubmit: () => true,
    });
    return result === true;
}

/* ── Form fields ──────────────────────────────────────────────────────────── */

const INPUT_CLASS = "w-full h-11 rounded-xl border border-slate-200 bg-white px-4 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-violet-200 focus:border-violet-400";

/**
 * Build a labelled form control. type: text|email|tel|number|date|select|textarea|checkbox.
 * options (select): [{value,label}]. Values are escaped.
 */
export function field({ name, label, type = "text", value = "", required = false, options = [], step, min, placeholder = "", full = false, help = "" }) {
    const id = `f-${name}-${Math.random().toString(36).slice(2, 8)}`;
    const req = required ? "required" : "";
    const labelHtml = `<label for="${id}" class="mb-1.5 block text-sm font-medium text-slate-700">${esc(label)}${required ? ' <span class="text-rose-500">*</span>' : ""}</label>`;
    const helpHtml = help ? `<p class="mt-1 text-xs text-slate-500">${esc(help)}</p>` : "";
    const wrap = full ? "col-span-2" : "";
    if (type === "checkbox") {
        return `<div class="${wrap} flex items-center gap-3">
            <input id="${id}" name="${esc(name)}" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-violet-600" ${value ? "checked" : ""}>
            <label for="${id}" class="text-sm font-medium text-slate-700">${esc(label)}</label>
        </div>`;
    }
    let control;
    if (type === "select") {
        control = `<select id="${id}" name="${esc(name)}" class="${INPUT_CLASS}" ${req}>
            ${options.map((o) => `<option value="${esc(o.value)}" ${String(o.value) === String(value) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}
        </select>`;
    } else if (type === "textarea") {
        control = `<textarea id="${id}" name="${esc(name)}" rows="3" class="${INPUT_CLASS} h-auto py-3" placeholder="${esc(placeholder)}" ${req}>${esc(value)}</textarea>`;
    } else {
        const attrs = [
            step !== undefined ? `step="${esc(step)}"` : "",
            min !== undefined ? `min="${esc(min)}"` : "",
        ].join(" ");
        control = `<input id="${id}" name="${esc(name)}" type="${esc(type)}" value="${esc(value)}" placeholder="${esc(placeholder)}" class="${INPUT_CLASS}" ${attrs} ${req}>`;
    }
    return `<div class="${wrap}">${labelHtml}${control}${helpHtml}</div>`;
}

/** Wrap several fields in a two-column grid. */
export function fieldGrid(fieldsHtml) {
    // Accept a list of field() results or one pre-joined string. An array
    // interpolated directly would put commas between the fields.
    const inner = Array.isArray(fieldsHtml) ? fieldsHtml.join("") : fieldsHtml;
    return `<div class="grid grid-cols-2 gap-x-5 gap-y-5">${inner}</div>`;
}

/** Read named controls of a form into a plain object (checkboxes → boolean). */
export function readForm(form) {
    const data = {};
    form.querySelectorAll("[name]").forEach((el) => {
        if (el.type === "checkbox") data[el.name] = el.checked;
        else data[el.name] = el.value.trim();
    });
    return data;
}

/** Throw a validation error for a missing required value. */
export function requireValue(value, message) {
    if (value === null || value === undefined || String(value).trim() === "") throw new Error(message);
    return value;
}

/* ── Tables, badges, pager ────────────────────────────────────────────────── */

/**
 * columns: [{ label, cell(row) => string (already escaped), align?, className? }]
 * actions: optional (row) => html for the last column (already escaped).
 */
export function table({ columns, rows, empty = "No records found.", actions = null, loading = false }) {
    const head = columns.map((c) => `<th scope="col" class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 ${c.align === "right" ? "text-right" : ""}">${esc(c.label)}</th>`).join("")
        + (actions ? `<th scope="col" class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Actions</th>` : "");
    let body;
    if (loading) {
        body = `<tr><td colspan="${columns.length + (actions ? 1 : 0)}" class="px-4 py-10 text-center text-sm text-slate-500">Loading…</td></tr>`;
    } else if (!rows.length) {
        body = `<tr><td colspan="${columns.length + (actions ? 1 : 0)}" class="px-4 py-10 text-center text-sm text-slate-500">${esc(empty)}</td></tr>`;
    } else {
        body = rows.map((row) => `<tr class="border-t border-slate-100 hover:bg-slate-50/70">
            ${columns.map((c) => `<td class="px-4 py-3 text-sm text-slate-700 ${c.align === "right" ? "text-right tabular-nums" : ""} ${c.className || ""}">${c.cell(row)}</td>`).join("")}
            ${actions ? `<td class="px-4 py-3 text-right whitespace-nowrap">${actions(row)}</td>` : ""}
        </tr>`).join("");
    }
    return `<div class="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
        <table class="min-w-full divide-y divide-slate-100"><thead class="bg-slate-50"><tr>${head}</tr></thead><tbody>${body}</tbody></table>
    </div>`;
}

const BADGE_TONES = {
    green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    amber: "bg-amber-50 text-amber-700 ring-amber-200",
    red: "bg-rose-50 text-rose-700 ring-rose-200",
    blue: "bg-sky-50 text-sky-700 ring-sky-200",
    slate: "bg-slate-100 text-slate-600 ring-slate-200",
    violet: "bg-violet-50 text-violet-700 ring-violet-200",
};

export function badge(text, tone = "slate") {
    return `<span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${BADGE_TONES[tone] || BADGE_TONES.slate}">${esc(text)}</span>`;
}

/** Status text → tone, shared by purchasing and transfers. */
export function statusBadge(status) {
    const tones = {
        draft: "slate", confirmed: "blue", ordered: "blue", partially_received: "amber", received: "green", closed: "green",
        cancelled: "red", in_transit: "amber", completed: "green", pending: "amber", processed: "green",
        active: "green", inactive: "slate", archived: "slate", open: "blue",
    };
    const label = String(status ?? "").replace(/_/g, " ");
    return badge(label ? label.charAt(0).toUpperCase() + label.slice(1) : "-", tones[status] || "slate");
}

/** Pager markup. Buttons carry data-page, handled by the page's delegated click listener. */
export function pager({ page = 1, totalPages = 1, count = 0 }) {
    const btn = (target, label, disabled) => `<button type="button" data-page="${target}" ${disabled ? "disabled" : ""} class="h-9 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">${label}</button>`;
    return `<div class="mt-4 flex items-center justify-between text-sm text-slate-500">
        <span>${count} record${count === 1 ? "" : "s"}</span>
        <div class="flex items-center gap-2">
            ${btn(page - 1, "Previous", page <= 1)}
            <span class="px-2">Page ${page} of ${Math.max(totalPages, 1)}</span>
            ${btn(page + 1, "Next", page >= totalPages)}
        </div>
    </div>`;
}

/* ── Buttons, busy state, misc ────────────────────────────────────────────── */

export function setBusy(button, busy) {
    if (!button) return;
    if (busy) {
        button.dataset.label = button.dataset.label || button.textContent;
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        button.textContent = "Working…";
    } else {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        if (button.dataset.label) button.textContent = button.dataset.label;
    }
}

/** Run an async action on a button with busy state and a toast on failure. */
export async function runAction(button, action, { successMessage = "", errorFallback = "Action failed." } = {}) {
    setBusy(button, true);
    try {
        const result = await action();
        if (successMessage) toast(successMessage, "success");
        return result;
    } catch (error) {
        toast(errorMessage(error, errorFallback), "error");
        return undefined;
    } finally {
        setBusy(button, false);
    }
}

/** Parse a query parameter from the hash route (e.g. #/customers?id=3). */
export function hashParam(name) {
    const query = window.location.hash.split("?")[1] || "";
    return new URLSearchParams(query).get(name);
}

/** Set a query parameter on the hash route without re-rendering a different page. */
export function setHashParam(path, params = {}) {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== "")).toString();
    window.location.hash = qs ? `${path}?${qs}` : path;
}

export function emptyStateCard(title, text) {
    return `<div class="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center">
        <p class="font-semibold text-slate-800">${esc(title)}</p>
        <p class="mt-1 text-sm text-slate-500">${esc(text)}</p>
    </div>`;
}

export function tabs(items, activeId, attr = "data-tab") {
    return `<div role="tablist" class="flex gap-1 border-b border-slate-200">
        ${items.map((item) => `<button type="button" role="tab" aria-selected="${item.id === activeId}" ${attr}="${esc(item.id)}"
            class="-mb-px border-b-2 px-4 py-2.5 text-sm font-semibold ${item.id === activeId ? "border-violet-600 text-violet-700" : "border-transparent text-slate-500 hover:text-slate-800"}">${esc(item.label)}</button>`).join("")}
    </div>`;
}

export function pageHeader({ title, subtitle = "", actions = "" }) {
    return `<div class="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
            <h1 class="text-3xl font-bold text-slate-900">${esc(title)}</h1>
            ${subtitle ? `<p class="mt-1 text-slate-500">${esc(subtitle)}</p>` : ""}
        </div>
        <div class="flex flex-wrap items-center gap-3">${actions}</div>
    </div>`;
}

export function primaryButton(label, action, extra = "") {
    return `<button type="button" data-action="${esc(action)}" class="h-11 rounded-xl bg-violet-600 px-5 text-sm font-semibold text-white shadow-sm hover:bg-violet-700 ${extra}">${esc(label)}</button>`;
}

export function secondaryButton(label, action, extra = "") {
    return `<button type="button" data-action="${esc(action)}" class="h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50 ${extra}">${esc(label)}</button>`;
}

export function dangerButton(label, action) {
    return `<button type="button" data-action="${esc(action)}" class="h-9 rounded-lg border border-rose-200 px-3 text-xs font-semibold text-rose-600 hover:bg-rose-50">${esc(label)}</button>`;
}

export function searchInput(id, placeholder) {
    return `<input id="${esc(id)}" type="search" placeholder="${esc(placeholder)}" class="${INPUT_CLASS} w-72">`;
}

export function selectInput(id, options, value = "") {
    return `<select id="${esc(id)}" class="${INPUT_CLASS} w-auto pr-8">${options.map((o) => `<option value="${esc(o.value)}" ${String(o.value) === String(value) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select>`;
}

/** Debounce helper for search inputs. */
export function debounce(fn, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
}

/** Parse a numeric form value; throws a readable error when invalid. */
export function toNumber(value, label, { min = null, allowZero = true } = {}) {
    const number = Number(value);
    if (value === "" || !Number.isFinite(number)) throw new Error(`${label} must be a number.`);
    if (min !== null && number < min) throw new Error(`${label} must be at least ${min}.`);
    if (!allowZero && number === 0) throw new Error(`${label} must be greater than zero.`);
    return number;
}

export function dateOrNull(value) {
    return value ? value : null;
}

/**
 * Row/action button with escaped data attributes.
 * tone: "default" | "danger" | "primary". data: { id, row, pinned, name, ... } → data-* attributes.
 */
export function actionButton(label, action, { tone = "default", data = {} } = {}) {
    const attrs = Object.entries(data)
        .filter(([, v]) => v !== undefined && v !== null)
        .map(([k, v]) => `data-${k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}="${esc(v)}"`)
        .join(" ");
    const tones = {
        default: "border-slate-200 text-slate-700 hover:bg-slate-50",
        danger: "border-rose-200 text-rose-600 hover:bg-rose-50",
    };
    return `<button type="button" data-action="${esc(action)}" ${attrs} class="mr-1.5 h-9 rounded-lg border px-3 text-xs font-semibold ${tones[tone] || tones.default}">${esc(label)}</button>`;
}
