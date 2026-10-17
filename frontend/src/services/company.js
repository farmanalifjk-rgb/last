/**
 * Company profile cache (GET /api/company/).
 *
 * Owners/admins can read the profile; staff without the settings permission
 * receive 403. A refusal is remembered for the session so the sidebar does not
 * re-request (and burn the 120/min rate limit) on every route change; the
 * business name and currency then come from the session payload instead.
 */
import { apiJson, getToken } from "./api.js";

const CACHE_MS = 5 * 60 * 1000;
let state = { token: null, company: null, loadedAt: 0, denied: false, request: null };

globalThis.window?.addEventListener?.("pos:auth-cleared", () => {
    state = { token: null, company: null, loadedAt: 0, denied: false, request: null };
});
globalThis.window?.addEventListener?.("company:updated", () => {
    state.loadedAt = 0;
    state.denied = false;
});

export function cachedCompany() {
    return state.token === getToken() ? state.company : null;
}

export async function loadCompany({ force = false } = {}) {
    const token = getToken();
    if (!token) return null;
    if (state.token !== token) state = { token, company: null, loadedAt: 0, denied: false, request: null };
    if (!force && state.denied) return null;
    if (!force && state.company && Date.now() - state.loadedAt < CACHE_MS) return state.company;
    if (!state.request) {
        state.request = apiJson("/api/company/")
            .then((data) => {
                if (state.token === token) {
                    state.company = data;
                    state.loadedAt = Date.now();
                }
                return data;
            })
            .catch((error) => {
                if (state.token === token && (error?.status === 403 || error?.status === 404)) {
                    state.denied = true;
                    return null;
                }
                throw error;
            })
            .finally(() => {
                state.request = null;
            });
    }
    return state.request;
}
