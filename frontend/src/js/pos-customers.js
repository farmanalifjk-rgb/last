/*
 * Pure helpers for the POS customer picker (no DOM; tested in
 * scripts/test-phase5-frontend.mjs). Search itself is server-side:
 * GET /api/pos/customers/?search= (name, phone, email, code; max 50 rows).
 */
export const CUSTOMER_RESULT_LIMIT = 50;

/** "Ali Khan · 0300-1234567" (plain text; escape before inserting as HTML). */
export function customerLabel(customer) {
    if (!customer) return "Walk-in customer";
    const name = String(customer.name || "").trim() || `Customer #${customer.id}`;
    return customer.phone ? `${name} · ${customer.phone}` : name;
}

/** Label for the active cart's customer, from the directory or the cart itself. */
export function cartCustomerLabel(cart, directory) {
    const id = cart?.customer_id || cart?.customer || null;
    if (!id) return "Walk-in customer";
    const known = directory?.get?.(String(id));
    if (known) return customerLabel(known);
    return cart.customer_name ? String(cart.customer_name) : `Customer #${id}`;
}

/** Keyboard navigation over `count` options (wraps; -1 = nothing active). */
export function moveActive(current, count, key) {
    if (!count) return -1;
    if (key === "ArrowDown") return current < count - 1 ? current + 1 : 0;
    if (key === "ArrowUp") return current > 0 ? current - 1 : count - 1;
    if (key === "Home") return 0;
    if (key === "End") return count - 1;
    return current;
}

/** Prefill for "Add customer" from what the cashier typed: digits → phone. */
export function newCustomerPrefill(term) {
    const value = String(term || "").trim();
    if (!value) return { name: "", phone: "" };
    return /^[+\d][\d\s-]{3,}$/.test(value) ? { name: "", phone: value } : { name: value, phone: "" };
}
