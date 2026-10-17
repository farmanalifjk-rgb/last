import { escapeHtml, safeWebUrl } from "./html-safety.mjs";

export { escapeHtml, safeWebUrl };

/**
 * Return `value` only when it is a URL that is safe to place in an href/src:
 * http(s) absolute URLs or same-origin relative paths ("/media/x.png",
 * "media/x.png"). Anything else (javascript:, data:, vbscript:, protocol-relative
 * "//host", malformed input) returns "". The result still has to be passed
 * through escapeHtml() when it is interpolated into an attribute.
 */
export function safeUrl(value) {
    if (value === null || value === undefined) return "";
    // Browsers ignore ASCII whitespace/control characters inside a scheme
    // ("java\tscript:"), so strip them before inspecting the scheme.
    const raw = String(value).trim();
    if (!raw) return "";
    const compact = raw.replace(/[\u0000-\u0020\u007f]/g, "");
    if (compact.startsWith("//") || compact.startsWith("\\\\") || compact.startsWith("/\\")) return "";
    const scheme = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(compact);
    if (scheme) {
        const name = scheme[1].toLowerCase();
        return name === "http" || name === "https" ? raw : "";
    }
    return raw;
}

/** Format a number or numeric string as money with 2 decimals (no currency symbol). */
export function formatMoney(value) {
    const number = Number.parseFloat(value);
    if (!Number.isFinite(number)) return "0.00";
    return number.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Format an ISO timestamp for display; returns "-" when missing or invalid. */
export function formatDateTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString("en-PK");
}

/** Format an ISO date (YYYY-MM-DD) for display. */
export function formatDate(value) {
    if (!value) return "-";
    const date = new Date(`${String(value).slice(0, 10)}T00:00:00`);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleDateString("en-PK");
}

/**
 * Download rows as a CSV file, generated in the browser from rows already loaded.
 * columns: [{ label, value: (row) => any }]
 */
/**
 * One CSV cell: quoted when needed and neutralised against spreadsheet formula
 * injection (a leading = + - @ tab or CR makes Excel/Sheets evaluate user text
 * such as a product name or note). Plain numbers like -5 stay numeric. Same
 * rule as the backend's pos.helpers.sanitize_csv_cell.
 */
export function csvCell(value) {
    let text = value === null || value === undefined ? "" : String(value);
    if (/^[=+\-@\t\r]/.test(text) && !/^-?\d+(\.\d+)?$/.test(text)) text = `'${text}`;
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function downloadCsv(filename, columns, rows) {
    const cell = (value) => csvCell(value);
    const lines = [columns.map((c) => cell(c.label)).join(",")];
    rows.forEach((row) => lines.push(columns.map((c) => cell(c.value(row))).join(",")));
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Escaped, user-facing block for a failed list load. Uses the `kind` set by
 * services/api.js so permission problems are not presented as empty data.
 */
export function loadErrorHtml(error, label = "data") {
    const kind = error?.kind || (error?.isNetworkError ? "network" : "");
    const titles = {
        permission: `You do not have permission to view ${label}.`,
        auth: "Your session has expired. Please sign in again.",
        network: "The POS server could not be reached.",
        rate_limited: "Too many requests. Wait a moment, then reload this page.",
        server: `The server failed to load ${label}.`,
    };
    const title = titles[kind] || `Could not load ${label}.`;
    const detail = error?.message && error.message !== title ? error.message : "";
    return `<div role="alert" class="rounded-2xl border ${kind === "permission" ? "border-amber-200 bg-amber-50 text-amber-800" : "border-rose-200 bg-rose-50 text-rose-700"} px-6 py-8 text-center">
        <p class="font-semibold">${escapeHtml(title)}</p>
        ${detail ? `<p class="mt-1 text-sm opacity-80">${escapeHtml(detail)}</p>` : ""}
    </div>`;
}
