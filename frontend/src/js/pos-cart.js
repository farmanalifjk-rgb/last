/*
 * Pure cashier-cart rules (no DOM, no network) so they can be unit-tested in
 * Node and reused by pos.js.
 *
 * - The discount belongs to ONE cart. It is never shared through a global input,
 *   so a completed or switched sale cannot leak its discount into the next one.
 * - A cart whose checkout is in flight, or whose outcome is unknown (timeout,
 *   network loss, 5xx), is LOCKED. Editing it would change the request
 *   fingerprint and a new Idempotency-Key could ring the same sale twice. The
 *   only safe actions are "retry the exact same request" (the server replays
 *   the committed sale or creates it once) or "discard the local cart".
 * - Totals shown to the customer come from the server preview. The cart never
 *   invents a tax rate locally.
 */

const MONEY_PATTERN = /^\d+(\.\d{1,2})?$/;

/** A new local cart. `discount` is a 2-dp string, `pendingCheckout` null. */
export function newCart({ id, name }) {
    return {
        id,
        name,
        customer: null,
        customer_id: null,
        items: [],
        note: "",
        discount: "0.00",
        checkoutIdempotencyKey: null,
        pendingCheckout: null,
    };
}

/**
 * Parse what the cashier typed into the discount box.
 * Returns { ok: true, value: "12.50" } or { ok: false, value: "0.00", message }.
 * Empty input means no discount.
 */
export function parseDiscount(raw) {
    const text = String(raw ?? "").trim().replace(/,/g, "");
    if (!text) return { ok: true, value: "0.00" };
    if (!MONEY_PATTERN.test(text)) {
        return { ok: false, value: "0.00", message: "Discount must be a non-negative amount with up to 2 decimals." };
    }
    return { ok: true, value: Number.parseFloat(text).toFixed(2) };
}

/** The discount actually sent to the server: always "0.00" without permission. */
export function effectiveDiscount(cart, canDiscount) {
    if (!canDiscount || !cart) return "0.00";
    const parsed = parseDiscount(cart.discount);
    return parsed.ok ? parsed.value : "0.00";
}

/** True while the cart has a checkout in flight or an unresolved outcome. */
export function isCartLocked(cart) {
    return Boolean(cart && cart.pendingCheckout);
}

/**
 * Stable fingerprint of what the preview depends on (items, customer, discount).
 * Used to drop stale preview responses after the cart changed.
 */
export function cartFingerprint(cart, discount) {
    if (!cart) return "";
    const items = (cart.items || [])
        .map((item) => `${Number(item.id)}x${String(item.qty)}`)
        .sort()
        .join(",");
    const customer = cart.customer_id || cart.customer || "";
    return `${cart.id}|${customer}|${discount}|${items}`;
}

/** Amount in integer paisa/cents. Non-numbers become 0. */
export function toCents(value) {
    const number = Number.parseFloat(value);
    return Number.isFinite(number) ? Math.round(number * 100) : 0;
}

/** True when two money amounts differ by at least one cent. */
export function totalsDiffer(a, b) {
    return toCents(a) !== toCents(b);
}

/** Change due in cents-safe arithmetic (negative means still owed). */
export function computeChange(total, received) {
    return (toCents(received) - toCents(total)) / 100;
}

/**
 * Classify a failed checkout request.
 *
 * - "ambiguous": the server may have committed the sale. This covers network
 *   loss, client timeout, 5xx (the response can fail after the transaction
 *   committed), and an idempotency conflict (the key already belongs to a
 *   committed checkout). Keep the cart locked; only an identical retry is safe.
 * - "rejected": the server answered with a definitive refusal (validation,
 *   permission, stock, rate limit). Nothing was committed, so the cart can be
 *   edited again.
 */
export function classifyCheckoutFailure(error) {
    if (!error) return "ambiguous";
    if (error.isNetworkError || error.isTimeout || error.kind === "network" || error.kind === "timeout") {
        return "ambiguous";
    }
    const status = Number(error.status);
    if (!Number.isFinite(status) || status <= 0) return "ambiguous";
    if (status >= 500) return "ambiguous";
    if (status === 409 && error.code === "idempotency_key_reused") return "ambiguous";
    return "rejected";
}

/**
 * The input field value to restore after a barcode scan that was typed into
 * the search box. `before` is the field value when the scan started; when it
 * is unknown, strip the scanned code from the end of the current value.
 */
export function searchValueAfterScan({ before, current, code }) {
    if (typeof before === "string") return before;
    const value = String(current ?? "");
    const scanned = String(code ?? "");
    return scanned && value.endsWith(scanned) ? value.slice(0, value.length - scanned.length) : value;
}
