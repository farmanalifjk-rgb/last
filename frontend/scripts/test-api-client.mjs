// MOCKED tests for src/services/api.js (no backend involved).
// fetch, localStorage and window are stubbed; the real module is loaded through
// Vite's SSR loader so import.meta.env and the exact shipped code are exercised.
// Real-backend verification of the same paths is done separately (curl / browser).
import assert from "node:assert/strict";
import { withSrcLoader } from "./lib/load-src.mjs";

// ---- browser stubs --------------------------------------------------------
const store = new Map();
globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
};
const win = new EventTarget();
win.location = { hash: "#/pos" };
globalThis.window = win;
if (typeof globalThis.CustomEvent === "undefined") {
    globalThis.CustomEvent = class extends Event {
        constructor(type, init = {}) { super(type); this.detail = init.detail; }
    };
}

let nextResponse = null;
const calls = [];
globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    if (nextResponse instanceof Error) throw nextResponse;
    return nextResponse;
};
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const text = (status, body, type = "text/html") => new Response(body, { status, headers: { "content-type": type } });
const envelope = (code, message, fields = {}) => ({ success: false, error: { code, message, fields } });

let passed = 0;
async function check(name, fn) {
    try {
        await fn();
        passed += 1;
    } catch (error) {
        console.error(`FAIL: ${name}`);
        throw error;
    }
}

await withSrcLoader(async (load) => {
    const api = await load("/src/services/api.js");

    const fail = async (response, path = "/api/pos/products/") => {
        nextResponse = response;
        try {
            await api.apiJson(path);
        } catch (error) {
            return error;
        }
        throw new Error("expected apiJson to throw");
    };
    const login = (token = "tok-1") => { store.set("pos_auth_token", token); store.set("pos_user", "{}"); win.location.hash = "#/pos"; };

    await check("errorKind mapping", () => {
        assert.equal(api.errorKind(400), "validation");
        assert.equal(api.errorKind(401), "auth");
        assert.equal(api.errorKind(403), "permission");
        assert.equal(api.errorKind(404), "not_found");
        assert.equal(api.errorKind(409), "conflict");
        assert.equal(api.errorKind(422), "validation");
        assert.equal(api.errorKind(429), "rate_limited");
        assert.equal(api.errorKind(500), "server");
        assert.equal(api.errorKind(503), "server");
    });

    await check("token header is sent and JSON success is returned", async () => {
        login("abc");
        nextResponse = json(200, { ok: true });
        const data = await api.apiJson("/api/pos/products/");
        assert.deepEqual(data, { ok: true });
        assert.equal(calls.at(-1).init.headers.get("Authorization"), "Token abc");
        assert.equal(calls.at(-1).url, "/api/pos/products/", "relative URL, no hardcoded host");
    });

    await check("400 with fields keeps code/fields and names the field in the message", async () => {
        login();
        const error = await fail(json(400, envelope("VALIDATION_ERROR", "Request validation failed.", {
            name: ["This field is required."], unit_price: ["Ensure this value is greater than 0."],
        })));
        assert.equal(error.status, 400);
        assert.equal(error.kind, "validation");
        assert.equal(error.code, "VALIDATION_ERROR");
        assert.deepEqual(error.fields.name, ["This field is required."]);
        assert.match(error.message, /^Request validation failed\. name: This field is required\.; unit price: Ensure/);
        assert.ok(!error.message.includes("[object Object]"));
        assert.equal(store.get("pos_auth_token"), "tok-1", "400 must not log the user out");
    });

    await check("non_field_errors are summarised without a label", async () => {
        const error = await fail(json(400, envelope("VALIDATION_ERROR", "Request validation failed.", {
            non_field_errors: ["Session is already closed."],
        })));
        assert.equal(error.message, "Request validation failed. Session is already closed.");
    });

    await check("401 on a protected path clears auth and redirects once", async () => {
        login("expired");
        let cleared = 0;
        const onClear = () => { cleared += 1; };
        win.addEventListener("pos:auth-cleared", onClear);
        const error = await fail(json(401, envelope("NOT_AUTHENTICATED", "Invalid token.")));
        assert.equal(error.kind, "auth");
        assert.equal(store.get("pos_auth_token"), undefined);
        assert.equal(win.location.hash, "#/login");
        assert.equal(cleared, 1);
        win.removeEventListener("pos:auth-cleared", onClear);
    });

    await check("401 from login/OTP endpoints does not clear an existing session", async () => {
        login("still-valid");
        const error = await fail(json(401, envelope("AUTH_FAILED", "Invalid credentials.")), "/api/auth/login/");
        assert.equal(error.message, "Invalid credentials.");
        assert.equal(store.get("pos_auth_token"), "still-valid");
        assert.equal(win.location.hash, "#/pos");
        await fail(json(401, envelope("OTP", "Invalid code.")), "/api/auth/verify-otp/?x=1");
        assert.equal(store.get("pos_auth_token"), "still-valid");
    });

    await check("403 is a permission error and keeps the session", async () => {
        login();
        const error = await fail(json(403, envelope("PERMISSION_DENIED", "A platform-level permission is required for this action.")));
        assert.equal(error.kind, "permission");
        assert.equal(error.message, "A platform-level permission is required for this action.");
        assert.equal(store.get("pos_auth_token"), "tok-1");
    });

    await check("404 / 409 / 429 kinds and messages", async () => {
        assert.equal((await fail(json(404, envelope("NOT_FOUND", "Not found.")))).kind, "not_found");
        const conflict = await fail(json(409, envelope("IDEMPOTENCY_CONFLICT", "This checkout is already being processed.")));
        assert.equal(conflict.kind, "conflict");
        assert.equal(conflict.code, "IDEMPOTENCY_CONFLICT");
        assert.equal(conflict.message, "This checkout is already being processed.");
        const throttled = await fail(json(429, { detail: "Request was throttled. Expected available in 12 seconds." }));
        assert.equal(throttled.kind, "rate_limited");
        assert.match(throttled.message, /throttled/);
    });

    await check("500 with an HTML body shows a generic message, never markup", async () => {
        const error = await fail(text(500, "<!doctype html><html><body><h1>Server Error (500)</h1><script>x()</script></body></html>"));
        assert.equal(error.kind, "server");
        assert.equal(error.message, "The server could not complete the request. Please try again.");
        assert.ok(!/</.test(error.message));
    });

    await check("502 with a long plain-text proxy body falls back to a generic message", async () => {
        const error = await fail(text(502, "upstream connect error ".repeat(40), "text/plain"));
        assert.equal(error.kind, "server");
        assert.equal(error.message, "The server could not complete the request. Please try again.");
    });

    await check("short plain-text bodies are kept", async () => {
        const error = await fail(text(400, "Bad barcode", "text/plain"));
        assert.equal(error.message, "Bad barcode");
    });

    await check("legacy DRF shapes ({detail}, {field:[...]}) are readable", async () => {
        assert.equal((await fail(json(400, { detail: "Nope." }))).message, "Nope.");
        assert.equal((await fail(json(400, { name: ["Required."], sku: ["Taken."] }))).message, "Required., Taken.");
    });

    await check("network failure has kind=network and a readable message", async () => {
        login();
        nextResponse = new TypeError("Failed to fetch");
        await assert.rejects(api.apiJson("/api/pos/products/"), (error) => {
            assert.equal(error.kind, "network");
            assert.equal(error.isNetworkError, true);
            assert.match(error.message, /Unable to reach the POS server/);
            return true;
        });
        assert.equal(store.get("pos_auth_token"), "tok-1", "network errors must not log out");
    });

    await check("fieldSummary is bounded and ignores non-strings", () => {
        assert.equal(api.fieldSummary(null), "");
        assert.equal(api.fieldSummary({ a: [{ nested: 1 }] }), "");
        const many = Object.fromEntries(Array.from({ length: 10 }, (_, i) => [`f${i}`, ["x".repeat(120)]]));
        const summary = api.fieldSummary(many);
        assert.ok(summary.length <= 300);
        assert.ok(summary.endsWith("..."));
    });

    await check("normalizeList handles array, envelope, and junk", () => {
        assert.deepEqual(api.normalizeList([1, 2]).results, [1, 2]);
        assert.equal(api.normalizeList([1, 2]).count, 2);
        const page = api.normalizeList({ count: 30, results: [1], has_next: true, total_pages: 3 });
        assert.equal(page.total_pages, 3);
        assert.equal(page.has_next, true);
        assert.deepEqual(api.normalizeList(null).results, []);
        assert.deepEqual(api.normalizeList({ error: "x" }).results, []);
        assert.deepEqual(api.normalizeList("<html>").results, []);
    });

    await check("timeoutMs aborts a hung request with kind=timeout (unknown outcome)", async () => {
        const realFetch = globalThis.fetch;
        let sawSignal = false;
        // A server that never answers: only the abort signal can end the request.
        globalThis.fetch = (url, init) => new Promise((resolve, reject) => {
            sawSignal = Boolean(init.signal);
            init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        });
        try {
            const started = Date.now();
            await assert.rejects(api.apiJson("/api/pos/checkout/", { method: "POST", body: "{}", timeoutMs: 40 }), (error) => {
                assert.equal(error.kind, "timeout");
                assert.equal(error.isTimeout, true);
                assert.equal(error.isNetworkError, true);
                assert.match(error.message, /did not respond in time/);
                return true;
            });
            assert.ok(sawSignal, "an AbortSignal must be passed to fetch");
            assert.ok(Date.now() - started < 2000, "the timeout must fire promptly");
        } finally {
            globalThis.fetch = realFetch;
        }
    });

    await check("without timeoutMs no signal is added and timeoutMs is not forwarded to fetch", async () => {
        login();
        nextResponse = json(200, { ok: true });
        calls.length = 0;
        await api.apiJson("/api/pos/products/");
        assert.equal(calls[0].init.signal, undefined);
        nextResponse = json(200, { ok: true });
        await api.apiJson("/api/pos/products/", { timeoutMs: 5000 });
        assert.equal("timeoutMs" in calls[1].init, false);
        assert.ok(calls[1].init.signal, "timeoutMs adds an abort signal");
    });

    await check("a plain network failure is still kind=network, not timeout", async () => {
        nextResponse = new TypeError("Failed to fetch");
        const direct = await api.apiJson("/api/pos/products/", { timeoutMs: 5000 }).catch((e) => e);
        assert.ok(direct instanceof Error);
        assert.equal(direct.kind, "network");
        assert.equal(direct.isTimeout, false);
        assert.match(direct.message, /Unable to reach the POS server/);
    });

    await check("buildQuery drops empty values and encodes", () => {
        assert.equal(api.buildQuery({ a: "", b: null, c: undefined }), "");
        assert.equal(api.buildQuery({ search: "a&b=<x>", page: 2, active: false }), "?search=a%26b%3D%3Cx%3E&page=2&active=false");
    });
});

console.log(`all api client checks passed (${passed}, mocked fetch)`);
