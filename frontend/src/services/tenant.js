/**
 * Active business (tenant) context.
 *
 *   GET  /api/saas/tenants/          the signed-in user's own active memberships
 *                                    (is_active_in_tenant marks the current one)
 *   POST /api/saas/tenants/switch/   {tenant_id}; membership-checked server-side,
 *                                    403 when the user is not a member
 *
 * /api/saas/tenant/ is deliberately NOT used here: it records a usage snapshot
 * on every call.
 */
import { apiJson, getToken } from "./api.js";
import { validateSession } from "./auth.js";

let cache = { token: null, tenants: null, promise: null };

globalThis.window?.addEventListener?.("pos:auth-cleared", () => {
    cache = { token: null, tenants: null, promise: null };
});

export function normalizeTenants(data) {
    const rows = Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : [];
    return rows
        .filter((row) => row && row.id != null)
        .map((row) => ({
            id: Number(row.id),
            name: String(row.name || row.slug || `Business ${row.id}`),
            slug: row.slug || "",
            isCurrent: Boolean(row.is_active_in_tenant),
        }));
}

export function currentTenant(tenants) {
    return (tenants || []).find((tenant) => tenant.isCurrent) || null;
}

/** Cached per token; the switcher and the sidebar badge share one request. */
export async function listMyTenants({ force = false } = {}) {
    const token = getToken();
    if (!token) return [];
    if (!force && cache.token === token && cache.tenants) return cache.tenants;
    if (!force && cache.token === token && cache.promise) return cache.promise;
    cache.token = token;
    cache.promise = apiJson("/api/saas/tenants/")
        .then((data) => {
            if (cache.token === token) cache.tenants = normalizeTenants(data);
            return normalizeTenants(data);
        })
        .finally(() => {
            if (cache.token === token) cache.promise = null;
        });
    return cache.promise;
}

export function cachedTenants() {
    return cache.token === getToken() ? cache.tenants : null;
}

/**
 * Switch the active business. Afterwards the session (permissions are
 * per-tenant) is re-validated and the page is reloaded so no data, cart or
 * cache from the previous business survives in memory.
 */
export async function switchTenant(tenantId, { reload = () => window.location.reload() } = {}) {
    const id = Number(tenantId);
    if (!Number.isInteger(id) || id <= 0) throw new Error("Choose a business to switch to.");
    const result = await apiJson("/api/saas/tenants/switch/", {
        method: "POST",
        body: JSON.stringify({ tenant_id: id }),
    });
    cache = { token: null, tenants: null, promise: null };
    await validateSession({ force: true });
    if (window.location.hash !== "#/dashboard") window.location.hash = "#/dashboard";
    reload();
    return result;
}
