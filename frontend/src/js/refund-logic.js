/**
 * Pure refund-form helpers (no DOM), shared by order history and node tests.
 * The backend re-validates everything under a row lock; this only stops
 * obviously invalid submissions before they reach it.
 */

/**
 * @param {{orderItemId:number, name:string, quantity:string, remaining:string}[]} entries
 * @param {string} cash cash to return to the customer (blank = 0)
 * @returns {{items: {order_item_id:number, quantity:string}[], cash: string, error: string}}
 */
export function collectRefundItems(entries, cash = "0") {
    const items = [];
    for (const entry of entries || []) {
        const raw = String(entry.quantity ?? "").trim();
        if (raw === "" || Number(raw) === 0) continue;
        const quantity = Number(raw);
        if (!Number.isFinite(quantity) || quantity < 0) {
            return { items: [], cash: "0", error: `Enter a valid refund quantity for ${entry.name}.` };
        }
        if (quantity > Number(entry.remaining)) {
            return { items: [], cash: "0", error: `${entry.name}: at most ${entry.remaining} can be refunded.` };
        }
        items.push({ order_item_id: Number(entry.orderItemId), quantity: raw });
    }
    if (!items.length) return { items, cash: "0", error: "Enter a quantity for at least one item." };
    const cashText = String(cash ?? "").trim() || "0";
    const cashValue = Number(cashText);
    if (!Number.isFinite(cashValue) || cashValue < 0) {
        return { items: [], cash: "0", error: "Cash returned must be zero or a positive amount." };
    }
    return { items, cash: cashText, error: "" };
}
