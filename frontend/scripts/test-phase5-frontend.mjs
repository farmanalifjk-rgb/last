// Phase 5 frontend regressions: currency label, permission gating helpers,
// theme switching, tenant list normalisation and the FBR screen logic.
// Usage: node scripts/test-phase5-frontend.mjs
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { withSrcLoader } from "./lib/load-src.mjs";

const store = new Map();
globalThis.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
};
globalThis.window = { addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; }, location: { hash: "" } };
globalThis.CustomEvent = class CustomEvent { constructor(type) { this.type = type; } };

let failures = 0;
function check(name, fn) {
    try {
        fn();
        console.log(`ok   ${name}`);
    } catch (error) {
        failures += 1;
        console.log(`FAIL ${name}\n     ${error.message}`);
    }
}

function fakeRoot() {
    const classes = new Set();
    return { classList: { toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)), contains: (name) => classes.has(name) }, style: {} };
}

await withSrcLoader(async (load) => {
    const currency = await load("/src/shared/currency.js");
    const auth = await load("/src/services/auth.js");
    const theme = await load("/src/shared/theme.js");
    const tenant = await load("/src/services/tenant.js");
    const fbr = await load("/src/js/fbr/fbr-logic.js");
    const exportAll = await load("/src/shared/export-all.js");
    const inventoryApi = await load("/src/js/inventory/services/inventory-api.js");

    check("currency: ISO codes, free text, hostile text and fallback", () => {
        assert.equal(currency.currencyLabel("PKR"), "Rs");
        assert.equal(currency.currencyLabel("usd"), "$");
        assert.equal(currency.currencyLabel("Rs."), "Rs.");
        assert.equal(currency.currencyLabel("<img src=x>"), "img srcx"); // markup characters stripped
        assert.equal(currency.currencyLabel(""), "Rs");
        assert.equal(currency.currencyLabel("<>"), "Rs");
        assert.equal(currency.formatCurrency(1250, "PKR"), "Rs 1,250.00");
    });

    check("currency: session tenant currency is used when no company profile is cached", () => {
        store.set("pos_user", JSON.stringify({ username: "c", permissions: ["pos.view"], tenant: { id: 1, name: "Shop", currency: "AED" } }));
        assert.equal(currency.configuredCurrency(), "AED");
        assert.equal(currency.currencyLabel(), "AED");
        store.set("pos_user", JSON.stringify({ username: "c", permissions: [], tenant: { id: 1, name: "Shop", currency: null } }));
        assert.equal(currency.currencyLabel(), "Rs");
    });

    check("permissions: cashier is not an admin and has no fiscal access", () => {
        const cashier = { permissions: ["pos.view", "pos.create", "customers.view", "customers.create", "products.view"] };
        assert.equal(auth.isBusinessAdmin(cashier), false);
        assert.equal(auth.hasAnyPermission(["fiscal.view", "fiscal.manage"], cashier), false);
        assert.deepEqual(fbr.allowedTabs((key) => auth.hasPermission(key, cashier)), []);
    });

    check("permissions: owner wildcard sees every FBR tab; a viewer sees history only", () => {
        const owner = { permissions: ["*.*"] };
        assert.equal(auth.isBusinessAdmin(owner), true);
        assert.deepEqual(fbr.allowedTabs((key) => auth.hasPermission(key, owner)).map((t) => t.id),
            ["configuration", "profiles", "sequences", "invoices", "submissions"]);
        const viewer = { permissions: ["fiscal.view"] };
        assert.deepEqual(fbr.allowedTabs((key) => auth.hasPermission(key, viewer)).map((t) => t.id), ["invoices", "submissions"]);
        assert.equal(auth.hasPermission("fiscal.view", null), false);
    });

    check("theme: toggling persists and sets html.dark", () => {
        store.delete("pos-theme");
        assert.equal(theme.isDarkMode(), false);
        const root = fakeRoot();
        assert.equal(theme.applyTheme(true, root), true);
        assert.equal(root.classList.contains("dark"), true);
        assert.equal(root.style.colorScheme, "dark");
        theme.applyTheme(false, root);
        assert.equal(root.classList.contains("dark"), false);
        globalThis.document = { documentElement: fakeRoot() };
        assert.equal(theme.toggleDarkMode(), true);
        assert.equal(store.get("pos-theme"), "dark");
        assert.equal(document.documentElement.classList.contains("dark"), true);
        assert.equal(theme.toggleDarkMode(), false);
        assert.equal(store.get("pos-theme"), "light");
    });

    check("tenants: membership list is normalised and the active one found", () => {
        const rows = tenant.normalizeTenants([
            { id: "3", name: "Main shop", slug: "main", is_active_in_tenant: true },
            { id: 4, slug: "branch", is_active_in_tenant: false },
            { name: "no id" },
        ]);
        assert.deepEqual(rows.map((r) => [r.id, r.name, r.isCurrent]), [[3, "Main shop", true], [4, "branch", false]]);
        assert.equal(tenant.currentTenant(rows).id, 3);
        assert.equal(tenant.normalizeTenants({ results: [{ id: 1, name: "A" }] }).length, 1);
        assert.deepEqual(tenant.normalizeTenants(null), []);
    });

    check("fbr: simulated acceptance is never shown as accepted or with an FBR number", () => {
        const simulated = { status: "accepted", is_simulated: true, fbr_invoice_number: "SIM-1" };
        assert.equal(fbr.submissionStatus(simulated), "simulated");
        assert.equal(fbr.officialFbrNumber(simulated), "");
        assert.match(fbr.statusInfo("simulated").label, /not official/i);
        assert.equal(fbr.officialFbrNumber({ status: "accepted", is_simulated: false, fbr_invoice_number: "F-9" }), "F-9");
        assert.equal(fbr.officialFbrNumber({ fbr: { status: "simulated", fbr_invoice_number: "SIM-2" } }), "");
        assert.equal(fbr.officialFbrNumber({ fbr: { status: "accepted", fbr_invoice_number: "F-1" } }), "F-1");
        assert.equal(fbr.officialFbrNumber({ fbr: { status: "pending", fbr_invoice_number: "F-1" } }), "");
        assert.equal(fbr.submissionStatus({ status: "weird" }), "unknown");
        assert.equal(fbr.submissionStatus(null), "not_submitted");
    });

    check("fbr: retry outcome reads 502/422 submission bodies as outcomes", () => {
        const failed = { status: 502, message: "x", data: { id: 7, status: "failed", is_simulated: false, error_message: "IMS not responding" } };
        const outcome = fbr.retryOutcome(null, failed);
        assert.equal(outcome.tone, "error");
        assert.match(outcome.message, /Failed — not fiscalized\. IMS not responding/);
        assert.match(fbr.retryOutcome(null, { status: 422, data: { id: 7, status: "rejected" } }).message, /Rejected by FBR/);
        assert.equal(fbr.retryOutcome({ id: 7, status: "accepted", is_simulated: false, fbr_invoice_number: "F-2" }, null).tone, "success");
        assert.match(fbr.retryOutcome({ id: 7, status: "accepted", is_simulated: true }, null).message, /NOT an official/);
        const refused = fbr.retryOutcome(null, { status: 400, message: "Reconcile it first", data: { error: "Reconcile it first" } });
        assert.deepEqual([refused.ok, refused.message], [false, "Reconcile it first"]);
    });

    check("fbr: configuration payload keeps the stored token and nulls blank links", () => {
        const body = fbr.configurationPayload({
            environment: "production", security_token: "  ", pos_registration_number: "", timeout_seconds: "30",
            max_retries: "", seller_province: "", default_transaction_type: "4", is_active: true,
        });
        assert.equal("security_token" in body, false);
        assert.equal("environment" in body, false); // environment is fixed after creation
        assert.equal(body.pos_registration_number, null);
        assert.equal(body.timeout_seconds, 30);
        assert.equal("max_retries" in body, false);
        assert.equal(body.seller_province, null);
        assert.equal(body.default_transaction_type, "4");
        const created = fbr.configurationPayload({ environment: "sandbox", security_token: "tok", pos_registration_number: "110014" }, { creating: true });
        assert.deepEqual([created.environment, created.security_token, created.pos_registration_number], ["sandbox", "tok", 110014]);
    });

    check("fbr: profile and sequence payloads respect backend rules", () => {
        const profile = fbr.profilePayload({ product: "5", hs_code: "2", uom: "1", sales_tax_rate: "", transaction_type: "", sro_schedule: "", extra_tax_rate: "" });
        assert.deepEqual([profile.product, profile.sales_tax_rate, profile.transaction_type, profile.sro_schedule, profile.extra_tax_rate], [undefined, "0", null, null, "0"]);
        assert.equal(fbr.profilePayload({ product: "5" }, { creating: true }).product, "5");
        const locked = fbr.sequencePayload({ name: "Till", prefix: "X", padding: "4", next_number: "1", is_active: false }, { invoices_issued: 3 });
        assert.deepEqual(locked, { name: "Till", is_active: false });
        const open = fbr.sequencePayload({ name: "Till", prefix: "T-", padding: "4", next_number: "9", document_type: "", is_active: true }, null);
        assert.deepEqual(open, { name: "Till", is_active: true, prefix: "T-", document_type: "invoice", padding: 4, next_number: 9 });
        assert.equal(fbr.nextInvoiceNumber({ prefix: "INV-", next_number: 42, padding: 6 }), "INV-000042");
        assert.equal(fbr.nextInvoiceNumber({ prefix: "A", next_number: 1, padding: 99 }), "A000000000001");
    });

    await (async () => {
        const pages = { 1: [1, 2], 2: [3, 4], 3: [5] };
        const calls = [];
        const loadPage = async (page, size) => { calls.push([page, size]); return { results: pages[page] || [], count: 5, total_pages: 3 }; };
        const all = await exportAll.collectAllPages(loadPage, { pageSize: 2, maxRows: 100 });
        const capped = await exportAll.collectAllPages(loadPage, { pageSize: 2, maxRows: 3 });
        const exact = await exportAll.collectAllPages(async () => ({ results: [1, 2], count: 2, total_pages: 1 }), { maxRows: 2 });
        check("adjustments export: every page is collected; the cap is reported", () => {
            assert.deepEqual(all, { rows: [1, 2, 3, 4, 5], count: 5, truncated: false });
            assert.deepEqual(calls.slice(0, 3), [[1, 2], [2, 2], [3, 2]]);
            assert.deepEqual(capped, { rows: [1, 2, 3], count: 5, truncated: true });
            assert.equal(exact.truncated, false);
        });
    })();

    check("adjustments export: one row per item; filters map to a date range", () => {
        const rows = inventoryApi.adjustmentCsvRows([{ adjustment_number: "A1", items: [{ product_name: "x" }, { product_name: "y" }] }, { adjustment_number: "A2", items: [] }]);
        assert.deepEqual(rows.map((r) => [r.adjustment.adjustment_number, r.item?.product_name ?? null]), [["A1", "x"], ["A1", "y"], ["A2", null]]);
        const today = inventoryApi.adjustmentDateRange("today");
        assert.match(today.date_from, /^\d{4}-\d{2}-\d{2}$/);
        assert.equal(today.date_from, today.date_to);
        const yesterday = inventoryApi.adjustmentDateRange("yesterday");
        assert.ok(yesterday.date_from < today.date_from);
        assert.ok(inventoryApi.adjustmentDateRange("month").date_from <= today.date_from);
        assert.ok(inventoryApi.adjustmentDateRange("week").date_from <= today.date_from);
        assert.deepEqual(inventoryApi.adjustmentDateRange(""), {});
    });

    const format = await load("/src/shared/format.js");
    check("csv: spreadsheet formulas in user text are neutralised, numbers kept", () => {
        assert.equal(format.csvCell('=HYPERLINK("http://evil","x")'), `"'=HYPERLINK(""http://evil"",""x"")"`);
        assert.equal(format.csvCell("@SUM(A1)"), "'@SUM(A1)");
        assert.equal(format.csvCell("+92 300"), "'+92 300");
        assert.equal(format.csvCell("-cmd"), "'-cmd");
        assert.equal(format.csvCell(-5), "-5");
        assert.equal(format.csvCell("-12.50"), "-12.50");
        assert.equal(format.csvCell("Plain, text"), '"Plain, text"');
        assert.equal(format.csvCell(null), "");
    });

    const picker = await load("/src/js/pos-customers.js");
    check("pos customers: labels, keyboard navigation and add-customer prefill", () => {
        assert.equal(picker.customerLabel({ id: 4, name: "Ali", phone: "0300" }), "Ali · 0300");
        assert.equal(picker.customerLabel({ id: 4, name: " " }), "Customer #4");
        assert.equal(picker.customerLabel(null), "Walk-in customer");
        const directory = new Map([["4", { id: 4, name: "Ali" }]]);
        assert.equal(picker.cartCustomerLabel({ customer_id: "4" }, directory), "Ali");
        assert.equal(picker.cartCustomerLabel({ customer_id: "9", customer_name: "Parked Bilal" }, directory), "Parked Bilal");
        assert.equal(picker.cartCustomerLabel({ customer_id: "9" }, directory), "Customer #9");
        assert.equal(picker.cartCustomerLabel({ customer_id: null }, directory), "Walk-in customer");
        assert.deepEqual([picker.moveActive(-1, 3, "ArrowDown"), picker.moveActive(2, 3, "ArrowDown"), picker.moveActive(0, 3, "ArrowUp"), picker.moveActive(1, 0, "ArrowDown")], [0, 0, 2, -1]);
        assert.deepEqual(picker.newCustomerPrefill("0300 1234567"), { name: "", phone: "0300 1234567" });
        assert.deepEqual(picker.newCustomerPrefill("+92-300-1234567"), { name: "", phone: "+92-300-1234567" });
        assert.deepEqual(picker.newCustomerPrefill("Sara"), { name: "Sara", phone: "" });
        assert.deepEqual(picker.newCustomerPrefill(""), { name: "", phone: "" });
    });

    check("login challenges continue with the server's canonical username", () => {
        assert.equal(auth.challengeAccount({ username: "sara.k" }, "sara@example.test"), "sara.k");
        assert.equal(auth.challengeAccount({ username: "  " }, " sara.k "), "sara.k");
        assert.equal(auth.challengeAccount(null, "sara.k"), "sara.k");
        const page = readFileSync(new URL("../src/pages/LoginPage.js", import.meta.url), "utf8");
        assert.match(page, /verifyOTP\(\{ username: auth\.challengeAccount\(challenge, username\)/);
        assert.match(page, /resendOTP\(\{ username: challengeAccount\(data, usernameInput\.value\)/);
        assert.match(page, /changeExpiredPassword\(\{ username: expiredAccount \|\| username/);
    });

    const refunds = await load("/src/js/refund-logic.js");
    check("refunds: quantities are bounded by what remains; cash must be non-negative", () => {
        const rows = [
            { orderItemId: "7", name: "Tea", remaining: "2.000", quantity: "1" },
            { orderItemId: "8", name: "Milk", remaining: "1.000", quantity: "" },
        ];
        assert.deepEqual(refunds.collectRefundItems(rows, ""), { items: [{ order_item_id: 7, quantity: "1" }], cash: "0", error: "" });
        assert.match(refunds.collectRefundItems([{ ...rows[0], quantity: "3" }]).error, /Tea: at most 2\.000/);
        assert.match(refunds.collectRefundItems([{ ...rows[0], quantity: "-1" }]).error, /valid refund quantity/);
        assert.match(refunds.collectRefundItems([{ ...rows[0], quantity: "abc" }]).error, /valid refund quantity/);
        assert.match(refunds.collectRefundItems([{ ...rows[0], quantity: "0" }]).error, /at least one item/);
        assert.match(refunds.collectRefundItems(rows, "-5").error, /zero or a positive/);
        const history = readFileSync(new URL("../src/js/order-history.js", import.meta.url), "utf8");
        assert.match(history, /if \(refundInFlight\) return;/);
        assert.doesNotMatch(history, /window\.alert\(|\balert\(/);
    });

    check("no native alert/confirm/prompt dialogs remain in the app source", () => {
        const offenders = [];
        const walk = (dir) => {
            for (const name of readdirSync(dir)) {
                const path = new URL(name, dir);
                if (statSync(path).isDirectory()) { walk(new URL(`${name}/`, dir)); continue; }
                if (!name.endsWith(".js")) continue;
                readFileSync(path, "utf8").split("\n").forEach((line, index) => {
                    if (/(^|[^.\w])(window\.)?(alert|confirm|prompt)\s*\(/.test(line)) offenders.push(`${path.pathname.split("/src/")[1]}:${index + 1}`);
                });
            }
        };
        walk(new URL("../src/", import.meta.url));
        assert.deepEqual(offenders, []);
    });

    check("receipt: popup-safe opening, last receipt, and cashier-printable header", () => {
        const pos = readFileSync(new URL("../src/js/pos.js", import.meta.url), "utf8");
        const page = readFileSync(new URL("../src/pages/POSPage.js", import.meta.url), "utf8");
        const receipt = readFileSync(new URL("../receipt.js", import.meta.url), "utf8");
        // Cashier audit G9 (Phase 3): receipts print in a hidden frame, so no
        // popup can be blocked and no tab steals the scanner's focus. A frame
        // that reports an error falls back to the open/print dialog.
        assert.equal((pos.match(/window\.open\(/g) || []).length, 0);
        assert.match(pos, /printReceipt\(order\.id,/);
        assert.match(pos, /data\.status !== "error"\) return;[\s\S]{0,200}showReceiptFallback\(lastReceipt/);
        assert.match(page, /id="pos-last-receipt"[\s\S]{0,80}onclick="reopenLastReceipt\(\)"/);
        // Cashiers cannot read /api/company/: the receipt must not depend on it.
        assert.doesNotMatch(receipt, /Promise\.all\(\[[\s\S]{0,120}\/api\/company\//);
        assert.match(receipt, /data\.business\s*\n?\s*\|\| await requestJson\("\/api\/company\/"\)\.catch/);
    });

    check("fbr: validation envelope fields become readable lines", () => {
        const lines = fbr.fieldErrorLines({ fields: { pos_registration_number: ["Required for IMS."], next_number: "Locked" } });
        assert.deepEqual(lines, ["pos registration number: Required for IMS.", "next number: Locked"]);
        assert.deepEqual(fbr.fieldErrorLines(new Error("x")), []);
    });
});

if (failures) {
    console.log(`\n${failures} check(s) failed`);
    process.exit(1);
}
console.log("\nAll phase 5 frontend checks passed.");
