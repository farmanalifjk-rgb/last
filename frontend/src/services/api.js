const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export function getApiBaseUrl() {
    const fallback = typeof window !== "undefined" ? window.location.origin : "http://localhost";
    try {
        return new URL(API_BASE || fallback, fallback).href;
    } catch {
        return fallback;
    }
}

const PUBLIC_AUTH_PATHS = new Set([
    "/api/auth/login/",
    "/api/auth/verify-otp/",
    "/api/auth/resend-otp/",
    "/api/auth/expired-password-change/",
    "/api/auth/password-reset/request/",
    "/api/auth/password-reset/confirm/",
]);
let unauthorizedTokenHandled = null;

export function getToken() {
    return localStorage.getItem("pos_auth_token");
}

export function clearAuthentication() {
    localStorage.removeItem("pos_auth_token");
    localStorage.removeItem("pos_user");
    window.dispatchEvent(new CustomEvent("pos:auth-cleared"));
}

function redirectToLogin() {
    clearAuthentication();
    if (window.location.hash !== "#/login") window.location.hash = "#/login";
}

function isPublicAuthPath(path) {
    const pathname = String(path).split("?")[0];
    return PUBLIC_AUTH_PATHS.has(pathname);
}

/**
 * fetch() with auth headers.
 *
 * `options.timeoutMs` (opt-in): abort the request after that many
 * milliseconds and throw an Error with `isTimeout`/`isNetworkError` set and
 * kind "timeout". A timeout does NOT mean the server did nothing: callers of
 * non-idempotent writes must treat it as an unknown outcome.
 */
export async function apiFetch(path, options = {}) {
    const { timeoutMs, ...fetchOptions } = options;
    const headers = new Headers(fetchOptions.headers || {});
    headers.set("Accept", "application/json");
    if (fetchOptions.body && !(fetchOptions.body instanceof FormData) && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    const token = getToken();
    if (token && !headers.has("Authorization")) headers.set("Authorization", `Token ${token}`);

    let controller = null;
    let timer = null;
    let timedOut = false;
    if (Number.isFinite(timeoutMs) && timeoutMs > 0 && typeof AbortController === "function") {
        controller = new AbortController();
        const outer = fetchOptions.signal;
        if (outer) {
            if (outer.aborted) controller.abort();
            else outer.addEventListener("abort", () => controller.abort(), { once: true });
        }
        timer = setTimeout(() => {
            timedOut = true;
            controller.abort();
        }, timeoutMs);
    }

    let response;
    try {
        response = await fetch(`${API_BASE}${path}`, {
            ...fetchOptions,
            headers,
            ...(controller ? { signal: controller.signal } : {}),
        });
    } catch (cause) {
        const error = new Error(
            timedOut
                ? "The POS server did not respond in time."
                : "Unable to reach the POS server. Check your connection and try again.",
        );
        error.cause = cause;
        error.isNetworkError = true;
        error.isTimeout = timedOut;
        error.kind = timedOut ? "timeout" : "network";
        throw error;
    } finally {
        if (timer) clearTimeout(timer);
    }

    // A failed login/OTP request is not evidence that an existing session is invalid.
    if (response.status === 401 && token && !isPublicAuthPath(path) && unauthorizedTokenHandled !== token) {
        unauthorizedTokenHandled = token;
        redirectToLogin();
    }
    return response;
}

export async function apiJson(path, options = {}) {
    const response = await apiFetch(path, options);
    const contentType = response.headers.get("content-type") || "";
    let data;
    if (contentType.includes("application/json")) data = await response.json().catch(() => ({}));
    else data = await response.text();

    if (!response.ok) {
        throw apiError(response.status, data);
    }
    return data;
}

/** Category of a failed request so callers can react differently (re-login, hide action, show fields...). */
export function errorKind(status) {
    if (status === 401) return "auth";
    if (status === 403) return "permission";
    if (status === 404) return "not_found";
    if (status === 409) return "conflict";
    if (status === 429) return "rate_limited";
    if (status >= 500) return "server";
    if (status >= 400) return "validation";
    return "unknown";
}

const GENERIC_MESSAGES = {
    auth: "Your session has expired. Please sign in again.",
    permission: "You do not have permission to perform this action.",
    not_found: "The requested record was not found.",
    rate_limited: "Too many requests. Please wait a moment and try again.",
    server: "The server could not complete the request. Please try again.",
};

/** "name: This field is required.; price: Must be positive." (bounded, plain text). */
export function fieldSummary(fields) {
    if (!fields || typeof fields !== "object") return "";
    const parts = [];
    for (const [field, value] of Object.entries(fields)) {
        const messages = (Array.isArray(value) ? value : [value]).filter((item) => typeof item === "string" && item);
        if (!messages.length) continue;
        const label = field === "non_field_errors" || field === "detail" ? "" : `${field.replace(/_/g, " ")}: `;
        parts.push(`${label}${messages.join(" ")}`);
        if (parts.length === 4) break;
    }
    const text = parts.join("; ");
    return text.length > 300 ? `${text.slice(0, 297)}...` : text;
}

/** Build an Error from a non-2xx response, keeping the backend's message, code and field errors. */
export function apiError(status, data) {
    const kind = errorKind(status);
    let message = "";
    if (data && typeof data === "object") {
        const candidate = data.detail ?? data.error?.message ?? data.error ?? data.message;
        if (typeof candidate === "string") message = candidate;
        else if (!data.error) {
            message = Object.values(data).flat().filter((value) => typeof value === "string").join(", ");
        }
    } else if (typeof data === "string" && data.trim() && !/^\s*</.test(data) && data.length <= 300) {
        // Short plain-text bodies are meaningful; HTML error pages (proxy/Django) are not.
        message = data.trim();
    }
    if (!message) message = GENERIC_MESSAGES[kind] || `Request failed (${status})`;
    const fields = data && typeof data === "object" && data.error?.fields && typeof data.error.fields === "object"
        ? data.error.fields
        : {};
    // The backend envelope says only "Request validation failed." and puts the
    // reason in `fields`; most screens show error.message, so summarise it.
    const summary = fieldSummary(fields);
    if (summary && !message.includes(summary)) message = `${message} ${summary}`;
    const error = new Error(message);
    error.status = status;
    error.kind = kind;
    error.code = data && typeof data === "object" ? data.error?.code || null : null;
    error.fields = fields;
    error.data = data;
    return error;
}

/* ---------------------------------------------------------------------------
 * Helpers shared by every feature module (added during API alignment).
 * ------------------------------------------------------------------------ */

/** Build a query string, dropping empty values. Returns "" or "?a=b". */
export function buildQuery(params = {}) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value === undefined || value === null || value === "") return;
        search.append(key, String(value));
    });
    const qs = search.toString();
    return qs ? `?${qs}` : "";
}

/**
 * The backend returns lists in two shapes: a bare array (e.g. /api/categories/)
 * or the paginated envelope { count, page, total_pages, results, next, ... }.
 * Normalise both to the paginated shape so pages have one code path.
 */
export function normalizeList(data) {
    if (Array.isArray(data)) {
        return { count: data.length, results: data, page: 1, total_pages: 1, has_next: false, has_previous: false, next: null, previous: null };
    }
    if (data && Array.isArray(data.results)) {
        return { total_pages: 1, has_next: false, has_previous: false, ...data };
    }
    return { count: 0, results: [], page: 1, total_pages: 1, has_next: false, has_previous: false, next: null, previous: null };
}

/** GET a list endpoint and return the normalised paginated shape. */
export async function apiList(path) {
    return normalizeList(await apiJson(path));
}

/**
 * Download an export (csv / excel / pdf) through the authenticated client.
 * A plain window.open() cannot send the Authorization header, so the file is
 * fetched as a blob and saved from an object URL.
 */
export async function apiDownload(path, filename) {
    const response = await apiFetch(path);
    if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        const data = contentType.includes("application/json")
            ? await response.json().catch(() => ({}))
            : await response.text().catch(() => "");
        const error = apiError(response.status, data);
        if (error.message === GENERIC_MESSAGES[error.kind] || /^Request failed/.test(error.message)) {
            error.message = `Export failed: ${error.message}`;
        }
        throw error;
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    const name = match ? match[1] : filename;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
