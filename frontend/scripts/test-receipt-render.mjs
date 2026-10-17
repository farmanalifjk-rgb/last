// Printed sale receipt layout (S.R.O. 1006(I)/2021 fields the system holds).
// Usage: node scripts/test-receipt-render.mjs
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { withSrcLoader } from "./lib/load-src.mjs";

let failures = 0;
async function check(name, fn) {
    try {
        await fn();
        console.log(`ok   ${name}`);
    } catch (error) {
        failures += 1;
        console.log(`FAIL ${name}\n     ${error.message}`);
    }
}

const PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

const company = {
    name: "Corner Mart", address: "Saddar, Hyderabad", tax_number: "", gst: "",
    ntn: "1234567-8", pos_registration_number: "110014", footer_message: "Thanks", currency: "PKR",
};

function sale(overrides = {}) {
    return {
        fiscal: {
            status: "accepted", invoice_number: "P4-000123", fbr_invoice_number: "110014-131026143000-0001",
            qr_png_base64: PNG, is_simulated: false,
        },
        order: { id: 9, number: "POS-9", created_at: "2026-10-13T09:30:00Z", customer: "Walk-in customer", cashier: "Ayesha Khan" },
        fiscal_lines: [
            { line_number: 1, description: "Tea 500g", quantity: "2", unit_price: "500.00", discount: "0.00",
              value_excl_tax: "1000.00", tax_rate: "18.00", tax: "180.00", total: "1180.00" },
            { line_number: 2, description: "Bread", quantity: "1", unit_price: "100.00", discount: "10.00",
              value_excl_tax: "90.00", tax_rate: "0.00", tax: "0.00", total: "90.00" },
        ],
        items: [{ name: "Tea 500g", quantity: "2", unit_price: "500.00", subtotal: "1000.00" }],
        tenders: [{ tender_type: "card", label: "Card", amount: "1270.00", reference: "" }],
        totals: { subtotal: "1100.00", discount: "10.00", tax: "180.00", total: "1270.00", received: "1270.00", change: "0.00", currency: "PKR" },
        ...overrides,
    };
}

await withSrcLoader(async (load) => {
    const { renderReceiptHeader, renderReceiptBody, pageCss, normalizePaper, waitForImages, removeBrokenImages } =
        await load("/src/shared/receipt-render.js");
    const { DEFAULT_FBR_LOGO_URL } = await load("/src/shared/fiscal-receipt.js");

    await check("header prints the seller NTN and the PoS registration number (POS ID)", () => {
        const html = renderReceiptHeader(company);
        assert.match(html, /NTN: 1234567-8/);
        assert.match(html, /POS ID: 110014/);
        assert.doesNotMatch(html, /Tax no:/, "NTN replaces the generic tax line when no other number is set");
    });

    await check("header without FBR keeps the old tax line and prints no POS ID", () => {
        const html = renderReceiptHeader({ name: "Shop", tax_number: "TX-9", ntn: "", pos_registration_number: "" });
        assert.match(html, /Tax no: TX-9/);
        assert.doesNotMatch(html, /POS ID|NTN:/);
        assert.match(renderReceiptHeader({ name: "Shop" }), /Tax no: -/);
    });

    await check("item lines use the S.R.O. columns: #, Description, Price, GST Rate, Qty, GST, Total", () => {
        const html = renderReceiptBody(sale(), company);
        for (const heading of [">#<", ">Description<", ">Price<", ">GST Rate<", ">Qty<", ">GST<", ">Total<"]) {
            assert.ok(html.includes(heading), heading);
        }
        assert.match(html, /Tea 500g[\s\S]*500\.00[\s\S]*18%[\s\S]*>2<[\s\S]*180\.00[\s\S]*1,180\.00/);
        assert.match(html, /Bread[\s\S]*0%/, "exempt or zero-rated items print 0%");
        assert.match(html, /Discount<\/td><td class="text-right">-10\.00/, "line discount shown");
    });

    await check("invoice number, cashier, readable payment mode and totals are printed", () => {
        const html = renderReceiptBody(sale(), company);
        assert.match(html, /Invoice No\.<\/b><\/td><td class="text-right">P4-000123/);
        assert.match(html, /Cashier<\/b><\/td><td class="text-right">Ayesha Khan/);
        assert.match(html, /<td>Card<\/td>/);
        assert.match(html, /Sale value \(excl\. tax\)<\/td><td class="text-right">1,090\.00/);
        assert.match(html, /Sales tax \(GST\)<\/td><td class="text-right">180\.00/);
        assert.match(html, /Total payable \(PKR\)<\/td><td class="text-right">1,270\.00/);
        assert.match(html, /9966/, "accepted sale carries the FBR statement");
    });

    await check("without a fiscal invoice the plain item table is used and nothing FBR is invented", () => {
        const html = renderReceiptBody(sale({ fiscal: { status: "not_configured" }, fiscal_lines: [] }), { name: "Shop" });
        assert.match(html, />Item<\/th>/);
        assert.doesNotMatch(html, /GST Rate|Invoice No\.|9966|fbr-qr/);
        assert.match(html, /Not an FBR fiscal invoice\./);
    });

    await check("reprints are marked; the original copy is not", () => {
        assert.doesNotMatch(renderReceiptBody(sale(), company, { copy: 1 }), /REPRINT/);
        assert.doesNotMatch(renderReceiptBody(sale(), company, { copy: null }), /REPRINT/);
        assert.match(renderReceiptBody(sale(), company, { copy: 3 }), /DUPLICATE - REPRINT \(copy 3\)/);
    });

    await check("operator-supplied FBR logo reaches the fiscal block", () => {
        assert.match(renderReceiptBody(sale(), company, { fbrLogoUrl: "/fbr-pos-logo.png" }), /class="fbr-logo"/);
        assert.doesNotMatch(renderReceiptBody(sale(), company), /fbr-logo/);
    });

    await check("hostile text from the server is escaped", () => {
        const evil = "<img src=x onerror=alert(1)>";
        const html = renderReceiptHeader({ ...company, name: evil, ntn: evil })
            + renderReceiptBody(sale({
                order: { number: evil, cashier: evil, customer: evil, created_at: "" },
                fiscal_lines: [{ line_number: evil, description: evil, quantity: evil, unit_price: "1", discount: "0", tax_rate: evil, tax: "0", total: "1" }],
                tenders: [{ label: evil, amount: "1", reference: evil }],
            }), company);
        assert.doesNotMatch(html, /<img src=x/);
    });

    await check("@page: thermal rolls get zero margins, sheets get their size", () => {
        assert.equal(pageCss("80mm"), "@page { margin: 0; }");
        assert.equal(pageCss("58mm"), "@page { margin: 0; }");
        assert.equal(pageCss("A4"), "@page { size: A4 portrait; margin: 10mm; }");
        assert.equal(pageCss("A5"), "@page { size: A5 portrait; margin: 10mm; }");
        assert.equal(normalizePaper("letter; } body { display:none"), "80mm", "unknown values cannot inject CSS");
    });

    await check("printing waits for the QR/logo images to load or fail", async () => {
        const listeners = [];
        const img = (complete) => ({ complete, addEventListener: (type, fn) => listeners.push({ type, fn }) });
        let done = false;
        const wait = waitForImages({ querySelectorAll: () => [img(true), img(false), img(false)] }, 5000).then(() => { done = true; });
        await new Promise((resolve) => setTimeout(resolve, 20));
        assert.equal(done, false, "still waiting for two images");
        listeners.filter((l) => l.type === "load")[0].fn();
        listeners.filter((l) => l.type === "error")[1].fn();
        await wait;
        assert.equal(done, true);
    });

    await check("the FBR logo is used by default from public/fbr/, overridable by env", () => {
        assert.equal(DEFAULT_FBR_LOGO_URL, "/fbr/fbr-pos-logo.png");
        const page = readFileSync(new URL("../receipt.js", import.meta.url), "utf8");
        assert.match(page, /VITE_FBR_POS_LOGO_URL === undefined\s*\?\s*DEFAULT_FBR_LOGO_URL/);
        assert.match(renderReceiptBody(sale(), company, { fbrLogoUrl: DEFAULT_FBR_LOGO_URL }),
            /<img src="\/fbr\/fbr-pos-logo\.png" class="fbr-logo"/);
    });

    await check("the logo file, when present, is a real PNG", () => {
        const file = new URL("../public/fbr/fbr-pos-logo.png", import.meta.url);
        if (!existsSync(file)) {
            console.log("     note: public/fbr/fbr-pos-logo.png not added yet; receipts print without the logo");
            return;
        }
        const bytes = readFileSync(file);
        assert.deepEqual([...bytes.subarray(0, 8)], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    });

    await check("a logo that fails to load is removed before printing (no broken-image icon)", () => {
        const removed = [];
        const img = (complete, naturalWidth) => {
            const wrapper = { remove: () => removed.push(wrapper) };
            return { complete, naturalWidth, closest: () => wrapper, wrapper };
        };
        const ok = img(true, 400);
        const broken = img(true, 0);
        const loading = img(false, 0);
        assert.equal(removeBrokenImages({ querySelectorAll: () => [ok, broken, loading] }, "img.fbr-logo"), 1);
        assert.deepEqual(removed, [broken.wrapper]);
        assert.equal(removeBrokenImages(null, "img"), 0);
    });

    await check("a stuck image cannot block printing forever", async () => {
        const started = Date.now();
        await waitForImages({ querySelectorAll: () => [{ complete: false, addEventListener() {} }] }, 50);
        assert.ok(Date.now() - started < 1000);
        await waitForImages(null);
    });
});

console.log(failures ? `\n${failures} receipt render check(s) failed` : "\nall receipt render checks passed");
process.exit(failures ? 1 : 0);
