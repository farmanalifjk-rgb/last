import { apiJson, apiFetch, getToken, clearAuthentication } from "./api.js";

const DEVICE_KEY = "pos_device_id";
let validatedToken = null;
let validationPromise = null;

export function getDeviceId() {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
        id = globalThis.crypto?.randomUUID?.() || `pos-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
        localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
}

export function saveAuthenticatedSession(data) {
    if (!data?.token) throw new Error("The server did not return an authentication token.");
    localStorage.setItem("pos_auth_token", data.token);
    cacheSessionUser(data);
    validatedToken = data.token;
    window.dispatchEvent(new CustomEvent("pos:authenticated", { detail: data.user || null }));
    return data;
}

/**
 * The active business ({id, name, slug, currency}) travels with the session
 * payload and is cached on the user so logout/clearAuthentication drop it.
 */
function cacheSessionUser(data) {
    if (!data?.user) return;
    const user = { ...data.user, tenant: data.tenant ?? null };
    localStorage.setItem("pos_user", JSON.stringify(user));
    window.dispatchEvent(new CustomEvent("pos:session-updated", { detail: user }));
}

export function getCachedTenant(user = getCachedUser()) {
    return user?.tenant || null;
}

export function getCachedUser() {
    try { return JSON.parse(localStorage.getItem("pos_user") || "null"); }
    catch { return null; }
}

/*
 * Permission checks for *navigation and button visibility only*. The backend
 * enforces RBAC on every endpoint; hiding a control is never the security
 * boundary. /api/auth/me/ returns ["*.*"] for tenant owners, admins and
 * superusers, otherwise the explicit "module.action" keys of the active tenant.
 */
export function userPermissions(user = getCachedUser()) {
    return Array.isArray(user?.permissions) ? user.permissions : [];
}

export function hasPermission(key, user = getCachedUser()) {
    const permissions = userPermissions(user);
    return permissions.includes("*.*") || permissions.includes(key);
}

export function hasAnyPermission(keys, user = getCachedUser()) {
    return (keys || []).some((key) => hasPermission(key, user));
}

/** Owner, admin or superuser of the active business. */
export function isBusinessAdmin(user = getCachedUser()) {
    return userPermissions(user).includes("*.*");
}

export async function login({ username, password }) {
    return apiJson("/api/auth/login/", {
        method: "POST",
        body: JSON.stringify({ username, password, device_name: "POS Terminal", device_id: getDeviceId() }),
    });
}

/**
 * Account to continue a login challenge (OTP, device authorization, expired
 * password) with. People may sign in with their email, but verify-otp,
 * resend-otp and expired-password-change look the account up by username, so
 * use the canonical username the server returned with the challenge.
 */
export function challengeAccount(data, typed) {
    const canonical = typeof data?.username === "string" ? data.username.trim() : "";
    return canonical || String(typed ?? "").trim();
}

export async function verifyOTP({ username, code, deviceId }) {
    return apiJson("/api/auth/verify-otp/", {
        method: "POST",
        body: JSON.stringify({ username, code, device_id: deviceId || getDeviceId() }),
    });
}

export async function resendOTP({ username, deviceId }) {
    return apiJson("/api/auth/resend-otp/", {
        method: "POST",
        body: JSON.stringify({ username, device_id: deviceId || getDeviceId() }),
    });
}


export async function changeExpiredPassword({ username, oldPassword, newPassword }) {
    return apiJson("/api/auth/expired-password-change/", {
        method: "POST",
        body: JSON.stringify({ username, old_password: oldPassword, new_password: newPassword }),
    });
}

export async function requestPasswordReset(email) {
    return apiJson("/api/auth/password-reset/request/", {
        method: "POST",
        body: JSON.stringify({ email }),
    });
}

export async function confirmPasswordReset({ email, code, newPassword }) {
    return apiJson("/api/auth/password-reset/confirm/", {
        method: "POST",
        body: JSON.stringify({ email, code, new_password: newPassword }),
    });
}

export async function validateSession({ force = false } = {}) {
    const token = getToken();
    if (!token) { validatedToken = null; return false; }
    if (!force && validatedToken === token) return true;
    if (validationPromise) return validationPromise;

    validationPromise = (async () => {
        try {
            const data = await apiJson("/api/auth/me/");
            if (data?.token && data.token !== token) {
                // The backend may return the token model key; never silently rotate local credentials here.
                throw new Error("Session response did not match the active credential.");
            }
            cacheSessionUser(data);
            validatedToken = token;
            return true;
        } catch (error) {
            if (error.status === 401) {
                clearAuthentication();
                validatedToken = null;
                return false;
            }
            throw error;
        } finally {
            validationPromise = null;
        }
    })();
    return validationPromise;
}

export async function logout() {
    try {
        if (getToken()) await apiFetch("/api/auth/logout/", { method: "POST" });
    } finally {
        clearAuthentication();
        validatedToken = null;
        if (window.location.hash !== "#/login") window.location.hash = "#/login";
    }
}

globalThis.window?.addEventListener?.("storage", (event) => {
    if (event.key === "pos_auth_token" && !event.newValue) {
        validatedToken = null;
        if (window.location.hash !== "#/login") window.location.hash = "#/login";
    }
});
