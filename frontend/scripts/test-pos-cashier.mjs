// Cashier terminal regressions (audit 2026-10-13, Phase 1).
//
// Part 1 unit-tests the pure rules in src/js/pos-cart.js.
// Part 2 loads the REAL src/js/pos.js against a minimal fake DOM and a MOCKED
// server (fetch stub). It drives the cashier's actions through the same
// window.* functions and keyboard events the page uses, and asserts on the
// requests pos.js sends. No browser and no real backend are involved: this
// verifies frontend logic only.
//
// Usage: node scripts/test-pos-cashier.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { withSrcLoader } from "./lib/load-src.mjs";

let failures = 0;
async function check(name, fn) {
    try {
        await fn();
        console.log(`ok   ${name}`);
    } catch (error) {
        failures += 1;
        console.log(`FAIL ${name}\n     ${error.stack || error.message}`);
    }
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ---------------------------------------------------------------------------
// Fake browser
// ---------------------------------------------------------------------------
class FakeClassList {
    constructor(owner) { this.owner = owner; this.set = new Set(); }
    add(...names) { names.forEach((n) => this.set.add(n)); }
    remove(...names) { names.forEach((n) => this.set.delete(n)); }
    toggle(name, on) {
        const value = on === undefined ? !this.set.has(name) : Boolean(on);
        if (value) this.set.add(name); else this.set.delete(name);
        return value;
    }
    contains(name) { return this.set.has(name); }
}
class FakeElement {
    constructor(id = "") {
        this.id = id;
        this.innerHTML = "";
        this.innerText = "";
        this._text = "";
        this.value = "";
        this.disabled = false;
        this.title = "";
        this.style = {};
        this.dataset = {};
        this.classList = new FakeClassList(this);
        this.selected = false;
    }
    get className() { return [...this.classList.set].join(" "); }
    set className(value) { this.classList.set = new Set(String(value).split(/\s+/).filter(Boolean)); }
    get textContent() { return this._text; }
    set textContent(value) { this._text = String(value); }
    addEventListener() {}
    removeEventListener() {}
    querySelector() { return null; }
    querySelectorAll() { return []; }
    setAttribute() {}
    getAttribute() { return null; }
    removeAttribute() {}
    appendChild(child) { return child; }
    append() {}
    remove() {}
    focus() {}
    blur() {}
    select() { this.selected = true; }
    closest() { return null; }
    contains() { return false; }
    insertAdjacentHTML() {}
}
globalThis.HTMLElement = FakeElement;
globalThis.HTMLInputElement = class extends FakeElement {};
globalThis.HTMLTextAreaElement = class extends FakeElement {};
globalThis.HTMLSelectElement = class extends FakeElement {};
globalThis.HTMLButtonElement = class extends FakeElement {};

const MODAL_IDS = ["payment-modal", "session-modal", "customer-modal", "park-modal", "parked-modal", "cash-modal"];
const INPUT_IDS = new Set(["product-search", "discount", "amount-received", "customer-search", "park-label"]);
const elements = new Map();
const notifications = [];
function element(id) {
    if (!elements.has(id)) {
        const el = INPUT_IDS.has(id) ? new HTMLInputElement(id) : new FakeElement(id);
        if (MODAL_IDS.includes(id)) el.classList.add("hidden");
        if (id === "notification") {
            Object.defineProperty(el, "textContent", {
                get() { return this._text; },
                set(value) { this._text = String(value); notifications.push(String(value)); },
            });
        }
        elements.set(id, el);
    }
    return elements.get(id);
}
let keydownListener = null;
let messageListener = null;
const appended = [];
const body = new FakeElement("body");
body.appendChild = (child) => { appended.push(child); return child; };
globalThis.document = {
    body,
    activeElement: null,
    getElementById: (id) => element(id),
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: (tag = "") => { const el = new FakeElement(); el.tagName = String(tag).toUpperCase(); return el; },
    addEventListener: (type, fn) => { if (type === "keydown") keydownListener = fn; },
    removeEventListener() {},
};
const store = new Map();
const storage = () => ({
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
});
globalThis.localStorage = storage();
globalThis.sessionStorage = storage();
const opened = [];
globalThis.window = {
    location: { hash: "#/pos", origin: "http://pos.test", href: "http://pos.test/#/pos" },
    addEventListener(type, fn) { if (type === "message") messageListener = fn; },
    removeEventListener() {},
    dispatchEvent() { return true; },
    open: (url) => { opened.push(url); return { closed: false }; },
};
globalThis.CustomEvent = class CustomEvent { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } };
globalThis.Audio = class { play() { return Promise.resolve(); } };
// pos.js logs expected failures (CHECKOUT ERROR, BARCODE ERROR...) via
// console.error; keep the test output readable.
const consoleErrors = [];
console.error = (...args) => consoleErrors.push(args.map(String).join(" ").split("\n")[0]);

function login(permissions) {
    store.set("pos_auth_token", "tok-test");
    store.set("pos_user", JSON.stringify({ username: "cashier", permissions }));
}

// ---------------------------------------------------------------------------
// Mocked server
// ---------------------------------------------------------------------------
const PRODUCTS = [
    { id: 1, name: "Tea", sales_price: "100.00", available_quantity: "50", barcode: "8961000000011", category_id: 3, category_name: "Drinks" },
    { id: 2, name: "Sugar", sales_price: "200.00", available_quantity: "50", barcode: "8961000000028", category_id: 4, category_name: "Grocery" },
];
const server = {
    calls: [],
    taxRate: 0.17,          // deliberately NOT 18%: the UI must show the server's figure
    priceBump: 0,           // added to the preview total to simulate a price change
    buyerThreshold: null,   // FBR buyer rule (backend flag) when set
    checkout: null,         // (call) => Response | throws
};
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
function previewFor(body) {
    const subtotal = body.items.reduce((sum, line) => {
        const product = PRODUCTS.find((p) => p.id === Number(line.product_id));
        return sum + Number(product.sales_price) * Number(line.quantity);
    }, 0);
    const discount = Number(body.discount || 0);
    const net = Math.max(0, subtotal - discount);
    const tax = Math.round(net * server.taxRate * 100) / 100;
    const total = net + tax + server.priceBump;
    const buyerRequired = server.buyerThreshold !== null && total > server.buyerThreshold;
    return {
        subtotal: subtotal.toFixed(2), discount: discount.toFixed(2), tax: tax.toFixed(2), total: total.toFixed(2), items: [],
        buyer_identification_required: buyerRequired,
        buyer_identification_threshold: server.buyerThreshold === null ? null : String(server.buyerThreshold),
    };
}
let orderSeq = 100;
globalThis.fetch = async (url, init = {}) => {
    const path = String(url);
    const headers = new Headers(init.headers || {});
    const call = { path, method: init.method || "GET", body: init.body ? JSON.parse(init.body) : null, rawBody: init.body, key: headers.get("Idempotency-Key"), hasSignal: Boolean(init.signal) };
    server.calls.push(call);
    if (path.startsWith("/api/pos/sessions/active/")) return json(200, { session: { id: 7, opening_balance: "1000.00", employee_name: "Test" } });
    if (path.startsWith("/api/pos/parked-sales/")) return json(200, []);
    // A POS-only cashier may not read the catalog categories (permission-gated).
    if (path.startsWith("/api/categories/")) return json(403, { success: false, error: { code: "permission_denied", message: "Not allowed.", fields: {} } });
    if (path.startsWith("/api/pos/customers/")) return json(200, []);
    if (path.startsWith("/api/pos/products/")) {
        const barcode = new URL(path, "http://x").searchParams.get("barcode");
        if (barcode !== null) return json(200, PRODUCTS.filter((p) => p.barcode === barcode));
        return json(200, { results: PRODUCTS, count: PRODUCTS.length, has_next: false });
    }
    if (path.startsWith("/api/pos/preview/")) return json(200, previewFor(call.body));
    if (path.startsWith("/api/pos/checkout/")) {
        if (server.checkout) return server.checkout(call);
        orderSeq += 1;
        return json(201, { order: { id: orderSeq, order_number: `POS-${orderSeq}` }, fiscal: { status: "not_configured" }, idempotent_replay: false });
    }
    return json(404, { detail: "not mocked" });
};
const callsTo = (prefix) => server.calls.filter((c) => c.path.startsWith(prefix));
const lastCall = (prefix) => callsTo(prefix).at(-1);
async function settlePreview() { await sleep(380); }

function pressKeys(text, target) {
    for (const key of text) {
        const event = { key, target, ctrlKey: false, altKey: false, metaKey: false, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
        keydownListener(event);
        if (target instanceof HTMLInputElement) target.value += key; // what the browser would type
    }
}
async function pressEnter(target) {
    const event = { key: "Enter", target, ctrlKey: false, altKey: false, metaKey: false, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
    await keydownListener(event);
    return event;
}

// ---------------------------------------------------------------------------
await withSrcLoader(async (load) => {
    const cartRules = await load("/src/js/pos-cart.js");

    // ------------------------------ Part 1 --------------------------------
    await check("pos-cart: a new cart starts with no discount and no pending checkout", () => {
        const cart = cartRules.newCart({ id: 1, name: "Order 1" });
        assert.equal(cart.discount, "0.00");
        assert.equal(cart.pendingCheckout, null);
        assert.equal(cartRules.isCartLocked(cart), false);
    });

    await check("pos-cart: discount parsing accepts money, rejects junk and negatives", () => {
        assert.deepEqual(cartRules.parseDiscount(""), { ok: true, value: "0.00" });
        assert.deepEqual(cartRules.parseDiscount(" 12.5 "), { ok: true, value: "12.50" });
        assert.deepEqual(cartRules.parseDiscount("1,250"), { ok: true, value: "1250.00" });
        for (const bad of ["-5", "abc", "1.234", "1e3", "5-"]) {
            const result = cartRules.parseDiscount(bad);
            assert.equal(result.ok, false, bad);
            assert.equal(result.value, "0.00", bad);
        }
    });

    await check("pos-cart: no discount is sent without permission or when invalid", () => {
        const cart = { ...cartRules.newCart({ id: 1, name: "x" }), discount: "40" };
        assert.equal(cartRules.effectiveDiscount(cart, true), "40.00");
        assert.equal(cartRules.effectiveDiscount(cart, false), "0.00");
        assert.equal(cartRules.effectiveDiscount({ ...cart, discount: "-1" }, true), "0.00");
    });

    await check("pos-cart: fingerprint follows items, customer and discount (order-insensitive)", () => {
        const base = { id: 9, customer_id: null, items: [{ id: 1, qty: 2 }, { id: 2, qty: 1 }] };
        const swapped = { ...base, items: [{ id: 2, qty: 1 }, { id: 1, qty: 2 }] };
        assert.equal(cartRules.cartFingerprint(base, "0.00"), cartRules.cartFingerprint(swapped, "0.00"));
        assert.notEqual(cartRules.cartFingerprint(base, "0.00"), cartRules.cartFingerprint(base, "5.00"));
        assert.notEqual(cartRules.cartFingerprint(base, "0.00"), cartRules.cartFingerprint({ ...base, customer_id: "4" }, "0.00"));
        assert.notEqual(cartRules.cartFingerprint(base, "0.00"), cartRules.cartFingerprint({ ...base, items: [{ id: 1, qty: 3 }, { id: 2, qty: 1 }] }, "0.00"));
    });

    await check("pos-cart: money comparisons are cent-exact", () => {
        assert.equal(cartRules.totalsDiffer("117.00", 117), false);
        assert.equal(cartRules.totalsDiffer("117.00", "117.01"), true);
        assert.equal(cartRules.computeChange("117.00", "200"), 83);
        assert.equal(cartRules.computeChange(0.3, 0.1 + 0.2), 0);
        assert.equal(cartRules.computeChange("117.00", "100") < 0, true);
    });

    await check("pos-cart: checkout failures that may have committed are 'ambiguous'", () => {
        const c = cartRules.classifyCheckoutFailure;
        assert.equal(c({ isNetworkError: true, kind: "network" }), "ambiguous");
        assert.equal(c({ isTimeout: true, isNetworkError: true, kind: "timeout" }), "ambiguous");
        assert.equal(c({ status: 500, kind: "server" }), "ambiguous");
        assert.equal(c({ status: 502, kind: "server" }), "ambiguous");
        assert.equal(c({ status: 504, kind: "server" }), "ambiguous");
        assert.equal(c({ status: 409, code: "idempotency_key_reused" }), "ambiguous");
        assert.equal(c(null), "ambiguous");
        assert.equal(c(new Error("no status")), "ambiguous");
        assert.equal(c({ status: 400, kind: "validation" }), "rejected");
        assert.equal(c({ status: 403, kind: "permission" }), "rejected");
        assert.equal(c({ status: 409, code: "insufficient_stock" }), "rejected");
        assert.equal(c({ status: 429, kind: "rate_limited" }), "rejected");
    });

    await check("pos-cart: the search box is restored after a scan", () => {
        const f = cartRules.searchValueAfterScan;
        assert.equal(f({ before: "", current: "8961000000011", code: "8961000000011" }), "");
        assert.equal(f({ before: "te", current: "te8961000000011", code: "8961000000011" }), "te");
        assert.equal(f({ before: null, current: "te8961000000011", code: "8961000000011" }), "te");
        assert.equal(f({ before: undefined, current: "tea", code: "999" }), "tea");
    });

    // --------------------------- static guards ----------------------------
    const posSource = readFileSync(new URL("../src/js/pos.js", import.meta.url), "utf8");
    const pageSource = readFileSync(new URL("../src/pages/POSPage.js", import.meta.url), "utf8");

    await check("pos.js imports lucide and has no dead typeof-createIcons guards", () => {
        assert.match(posSource, /import\s*\{\s*createIcons,\s*icons\s*\}\s*from\s*"lucide"/);
        assert.doesNotMatch(posSource, /typeof createIcons/);
    });

    await check("pos.js never invents a tax rate locally", () => {
        assert.doesNotMatch(posSource, /\*\s*0\.1[0-9]\b/);
        assert.doesNotMatch(posSource, /localTax/);
    });

    await check("discount box is per cart (setCartDiscount), not a re-render of a global input", () => {
        assert.match(pageSource, /id="discount"[\s\S]{0,400}oninput="setCartDiscount\(this\.value\)"/);
        assert.doesNotMatch(pageSource, /id="discount"[\s\S]{0,400}oninput="renderCart\(\)"/);
        assert.match(pageSource, /id="pos-totals-error"/);
    });

    await check("icon-only cart buttons have accessible names", () => {
        assert.match(posSource, /aria-label="Remove \$\{escapeHtml\(item\.name\)\}"/);
        assert.match(posSource, /aria-label="Increase quantity of/);
        assert.match(posSource, /aria-label="Decrease quantity of/);
    });

    // ------------------------------ Part 2 --------------------------------
    login(["*.*"]);
    await load("/src/js/pos.js");
    const w = globalThis.window;
    assert.equal(typeof w.initializePOS, "function", "pos.js must expose initializePOS");
    assert.equal(typeof keydownListener, "function", "pos.js must register the scanner listener");
    await w.initializePOS();

    await check("categories fall back to the product rows when the catalog endpoint is refused", () => {
        const bar = element("category-bar").innerHTML;
        assert.match(bar, /Drinks/);
        assert.match(bar, /Grocery/);
        assert.ok(bar.indexOf("Drinks") < bar.indexOf("Grocery"), "sorted by name");
    });

    const discountInput = element("discount");
    const total = () => element("total").innerText;
    const tax = () => element("tax").innerText;

    await check("totals show '…' until the server preview answers, then the server's tax (not 18%)", async () => {
        server.calls.length = 0;
        assert.equal(w.addToCart(1), true);
        assert.equal(tax(), "…");
        assert.equal(total(), "…");
        await settlePreview();
        assert.equal(callsTo("/api/pos/preview/").length, 1, "one debounced preview");
        assert.equal(tax(), "17.00");      // server: 17% of 100
        assert.equal(total(), "117.00");
        assert.ok(lastCall("/api/pos/preview/").hasSignal, "preview requests carry a timeout signal");
    });

    await check("rapid cart edits are debounced into a single preview", async () => {
        server.calls.length = 0;
        w.increaseQty(1);
        w.increaseQty(1);
        w.addToCart(2);
        await settlePreview();
        const previews = callsTo("/api/pos/preview/");
        assert.equal(previews.length, 1);
        assert.deepEqual(previews[0].body.items.map((i) => [i.product_id, i.quantity]).sort(), [[1, "3"], [2, "1"]]);
    });

    await check("discount is sent with this sale only and reset for the next sale", async () => {
        server.calls.length = 0;
        w.setCartDiscount("50");
        await settlePreview();
        assert.equal(lastCall("/api/pos/preview/").body.discount, "50.00");

        await w.openPaymentModal();
        element("amount-received").value = "1000";
        await w.confirmPayment({});
        const sale = lastCall("/api/pos/checkout/");
        assert.ok(sale, "checkout was sent");
        assert.equal(sale.body.discount, "50.00");
        assert.ok(sale.hasSignal, "checkout carries a timeout signal");

        // The completed cart is gone; the fresh cart must not inherit 50.
        assert.equal(discountInput.value, "0.00", "discount box shows the new cart's 0.00");
        server.calls.length = 0;
        w.addToCart(1);
        await settlePreview();
        assert.equal(lastCall("/api/pos/preview/").body.discount, "0.00");
    });

    await check("switching carts keeps each cart's own discount", async () => {
        w.setCartDiscount("10");
        await settlePreview();
        w.createOrder();                         // second tab, empty
        assert.equal(discountInput.value, "0.00");
        w.addToCart(2);
        await settlePreview();
        assert.equal(lastCall("/api/pos/preview/").body.discount, "0.00");
        // Back to the first tab: its 10 must come back, not leak into tab 2.
        const firstTabId = Number(/switchOrder\((\d+)\)/.exec(element("order-tabs").innerHTML)[1]);
        w.switchOrder(firstTabId);
        assert.equal(discountInput.value, "10");
    });

    await check("invalid discount is reported inline and blocks payment", async () => {
        server.calls.length = 0;
        w.setCartDiscount("-5");
        await settlePreview();
        assert.match(element("pos-totals-error").textContent, /non-negative/);
        assert.equal(lastCall("/api/pos/preview/").body.discount, "0.00", "invalid input is never sent");
        await w.openPaymentModal();
        assert.ok(element("payment-modal").classList.contains("hidden"), "payment does not open");
        w.setCartDiscount("0");
        await settlePreview();
    });

    await check("payment total change is shown, not silently charged", async () => {
        await w.openPaymentModal();
        assert.equal(element("payment-modal").classList.contains("hidden"), false);
        const shown = element("payment-total").innerText;
        server.priceBump = 25;                  // prices changed on the server
        server.calls.length = 0;
        element("amount-received").value = "5000";
        await w.confirmPayment({});
        server.priceBump = 0;
        assert.equal(callsTo("/api/pos/checkout/").length, 0, "no checkout with an unseen total");
        assert.match(notifications.at(-1), /total changed/i);
        assert.notEqual(element("payment-total").innerText, shown, "modal shows the new total");
        w.closePaymentModal();
    });

    await check("change is computed from the quoted total, not the totals panel text", async () => {
        await w.openPaymentModal();
        element("total").innerText = "999999.00";      // tampered/stale panel text
        element("amount-received").value = String(Number(element("amount-received").value) + 10);
        w.calculateChange();
        assert.match(element("change-amount").innerText, /10\.00$/);
        w.closePaymentModal();
    });

    await check("timeout/network failure locks the cart; retry resends the identical request", async () => {
        const tabsBefore = element("order-tabs").innerHTML;
        server.checkout = () => { throw new TypeError("Failed to fetch"); };
        await w.openPaymentModal();
        element("amount-received").value = "5000";
        server.calls.length = 0;
        await w.confirmPayment({});
        const first = lastCall("/api/pos/checkout/");
        assert.ok(first, "first attempt sent");
        assert.match(element("cart").innerHTML, /Checkout result unknown/);
        assert.match(element("cart").innerHTML, /retryPendingCheckout\(\)/);
        assert.ok(element("payment-modal").classList.contains("hidden"), "payment closes; banner takes over");

        // Locked: no edits, no new key, no re-priced attempt.
        assert.equal(w.addToCart(1), false);
        w.setCartDiscount("99");
        assert.equal(discountInput.disabled, true);
        await w.openPaymentModal();
        assert.ok(element("payment-modal").classList.contains("hidden"));

        server.checkout = null;                  // connection is back
        server.calls.length = 0;
        await w.retryPendingCheckout();
        const retry = lastCall("/api/pos/checkout/");
        assert.ok(retry, "retry sent");
        assert.equal(retry.key, first.key, "same Idempotency-Key");
        assert.equal(retry.rawBody, first.rawBody, "byte-identical body");
        assert.equal(callsTo("/api/pos/preview/").length, 0, "retry is not re-priced");
        assert.doesNotMatch(element("cart").innerHTML, /Checkout result unknown/);
        assert.notEqual(element("order-tabs").innerHTML, tabsBefore);
    });

    await check("a 5xx answer is also treated as unknown (the sale may have committed)", async () => {
        w.addToCart(1);
        await settlePreview();
        server.checkout = () => json(502, "<html>Bad gateway</html>");
        await w.openPaymentModal();
        element("amount-received").value = "5000";
        await w.confirmPayment({});
        assert.match(element("cart").innerHTML, /Checkout result unknown/);
        server.checkout = null;
        await w.retryPendingCheckout();
        assert.doesNotMatch(element("cart").innerHTML, /Checkout result unknown/);
    });

    await check("a definitive 4xx refusal unlocks the cart for correction", async () => {
        w.addToCart(1);
        await settlePreview();
        server.checkout = () => json(400, { success: false, error: { code: "validation_error", message: "Insufficient stock for Tea.", fields: {} } });
        await w.openPaymentModal();
        element("amount-received").value = "5000";
        await w.confirmPayment({});
        server.checkout = null;
        assert.doesNotMatch(element("cart").innerHTML, /Checkout result unknown/);
        assert.match(notifications.at(-1), /Insufficient stock/);
        assert.equal(element("payment-modal").classList.contains("hidden"), false, "cashier stays in the payment window to correct");
        w.closePaymentModal();
        assert.equal(w.addToCart(2), true, "cart is editable again");
        await settlePreview();
    });

    const search = element("product-search");

    await check("scan into the focused search box adds the item and restores the box", async () => {
        search.value = "";
        server.calls.length = 0;
        pressKeys("8961000000028", search);
        assert.equal(search.value, "8961000000028");      // what the browser typed
        await pressEnter(search);
        assert.ok(lastCall("/api/pos/products/?barcode=8961000000028"), "barcode lookup sent");
        assert.equal(search.value, "", "scanned digits removed from the search box");
    });

    await check("unknown barcode leaves the digits selected so the next scan replaces them", async () => {
        search.value = "";
        search.selected = false;
        pressKeys("0000000", search);
        await pressEnter(search);
        assert.equal(search.selected, true);
        assert.match(notifications.at(-1), /No product with barcode 0000000/);
    });

    await check("scans are ignored while the payment window is open", async () => {
        await w.openPaymentModal();
        assert.equal(element("payment-modal").classList.contains("hidden"), false);
        server.calls.length = 0;
        const button = new HTMLButtonElement("confirm");
        pressKeys("8961000000011", button);
        const event = await pressEnter(button);
        assert.equal(callsTo("/api/pos/products/").length, 0, "no lookup while a dialog is open");
        assert.equal(event.defaultPrevented, true, "Enter must not press the focused dialog button");
        assert.match(notifications.at(-1), /Close the open window/);
        w.closePaymentModal();
    });

    await check("FBR buyer rule: payment does not open for a walk-in sale above the threshold", async () => {
        w.createOrder();
        w.addToCart(1);
        await settlePreview();
        server.buyerThreshold = 100;           // 117.00 > 100
        await w.openPaymentModal();
        assert.ok(element("payment-modal").classList.contains("hidden"), "payment must not open");
        assert.match(notifications.at(-1), /need the buyer's name/);
        server.buyerThreshold = 1000;          // 117.00 <= 1000
        await w.openPaymentModal();
        assert.equal(element("payment-modal").classList.contains("hidden"), false);
        w.closePaymentModal();
        server.buyerThreshold = null;
    });

    // ------------------------- Receipt printing (Phase 3) -------------------
    const receiptFrames = () => appended.filter((el) => el.tagName === "IFRAME" && el.id === "pos-receipt-frame");
    async function completeSale() {
        w.createOrder();
        w.addToCart(1);
        await settlePreview();
        await w.openPaymentModal();
        element("amount-received").value = "1000";
        await w.confirmPayment({});
    }

    await check("a completed sale prints its receipt in a hidden frame, never a new tab (G9)", async () => {
        const tabsBefore = opened.length;
        appended.length = 0;
        await completeSale();
        const frames = receiptFrames();
        assert.equal(frames.length, 1, "one receipt frame");
        const sale = lastCall("/api/pos/checkout/");
        assert.ok(sale, "sale completed");
        assert.match(frames[0].src, /^\/receipt\.html\?type=sale&id=\d+$/);
        assert.match(frames[0].style.cssText, /visibility:hidden/);
        assert.equal(opened.length, tabsBefore, "no window.open: the scanner keeps focus");
    });

    await check("'Last receipt' reprints the same receipt in the frame", () => {
        const first = receiptFrames().at(-1).src;
        appended.length = 0;
        w.reopenLastReceipt();
        assert.equal(receiptFrames().length, 1);
        assert.equal(receiptFrames()[0].src, first);
        assert.match(notifications.at(-1), /Reprinting the last receipt/);
    });

    await check("receipt frame errors reach the cashier; foreign or spoofed messages are ignored", () => {
        assert.equal(typeof messageListener, "function", "pos.js listens for receipt frame messages");
        const frameWindow = {};
        element("pos-receipt-frame").contentWindow = frameWindow;
        const count = notifications.length;
        const payload = { type: "pos-receipt", status: "error", message: "Request failed (500)" };
        messageListener({ origin: "http://evil.test", source: frameWindow, data: payload });
        messageListener({ origin: "http://pos.test", source: {}, data: payload });
        messageListener({ origin: "http://pos.test", source: frameWindow, data: { ...payload, status: "printed" } });
        assert.equal(notifications.length, count, "nothing shown for foreign, spoofed or success messages");
        const modalRoot = element("ui-modal-root");
        modalRoot.querySelector = () => new FakeElement();
        modalRoot.querySelectorAll = () => [];
        messageListener({ origin: "http://pos.test", source: frameWindow, data: payload });
        assert.match(notifications.at(-1), /Receipt could not be printed: Request failed \(500\)/);
        assert.match(modalRoot.innerHTML, /Receipt could not be printed/, "open/print fallback offered");
        assert.match(modalRoot.innerHTML, /data-receipt-print/);
    });

    // Permission-less cashier: the discount box is disabled and nothing is sent.
    await check("without pos.discount the box is disabled and the discount is never sent", async () => {
        login(["pos.view", "pos.create"]);
        w.createOrder();
        assert.equal(discountInput.disabled, true);
        w.setCartDiscount("30");
        w.addToCart(1);
        await settlePreview();
        assert.equal(lastCall("/api/pos/preview/").body.discount, "0.00");
        assert.equal(discountInput.value, "0.00");
        login(["*.*"]);
    });
});

if (failures) {
    console.log(`\n${failures} cashier check(s) FAILED.`);
    process.exit(1);
}
console.log("\nAll cashier terminal checks passed (mocked server, fake DOM).");
// Exit now: pos.js leaves a 120 s cleanup timer for the receipt print frame.
process.exit(0);
