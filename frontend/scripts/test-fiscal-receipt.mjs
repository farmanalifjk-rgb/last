// The receipt's FBR block must never make a non-fiscalized sale look fiscalized.
// Usage: node scripts/test-fiscal-receipt.mjs
import assert from "node:assert/strict";
import { withSrcLoader } from "./lib/load-src.mjs";

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

const PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

await withSrcLoader(async (load) => {
    const { renderFiscalReceipt, FISCAL_NOTICES, TAX_ASAAN_STATEMENT } = await load("/src/shared/fiscal-receipt.js");

    check("genuine acceptance prints the FBR number and the QR", () => {
        const html = renderFiscalReceipt({ status: "accepted", fbr_invoice_number: "123456ABCD", qr_png_base64: PNG });
        assert.match(html, /FBR POS Invoice No\./);
        assert.match(html, /123456ABCD/);
        assert.match(html, /<img src="data:image\/png;base64,iVBOR/);
    });

    check("non-accepted states never print an FBR number or QR, even if one leaks in", () => {
        for (const status of ["simulated", "pending", "unknown", "failed", "rejected", "not_submitted", "not_fiscalized", "bogus"]) {
            const html = renderFiscalReceipt({ status, fbr_invoice_number: "SIM-123", qr_png_base64: PNG });
            assert.doesNotMatch(html, /SIM-123|<img|FBR POS Invoice No/, status);
            assert.match(html, /not (yet )?fiscalized/i, status);
        }
        assert.match(renderFiscalReceipt({ status: "simulated" }), /SIMULATED - NOT AN FBR INVOICE/);
    });

    check("accepted without an FBR number is not shown as fiscalized", () => {
        const html = renderFiscalReceipt({ status: "accepted", fbr_invoice_number: "", qr_png_base64: PNG });
        assert.doesNotMatch(html, /<img|FBR POS Invoice No/);
        assert.match(html, new RegExp(FISCAL_NOTICES.not_fiscalized.replace(/[.()]/g, "\\$&")));
    });

    check("tenants without FBR get an explicit not-an-FBR-invoice line", () => {
        // Phase 5 requirement: "not configured" is distinguished on the receipt.
        const notConfigured = renderFiscalReceipt({ status: "not_configured", fbr_invoice_number: "X-1", qr_png_base64: "iVBORw0KGgo=" });
        assert.match(notConfigured, /Not an FBR fiscal invoice\./);
        assert.doesNotMatch(notConfigured, /X-1|<img|FBR POS Invoice No/);
        assert.equal(renderFiscalReceipt(undefined), "");
    });

    // ---- S.R.O. 1006(I)/2021 part (D): logo, 7x7 mm QR, Tax Asaan statement ----
    const accepted = { status: "accepted", fbr_invoice_number: "123456ABCD", qr_png_base64: PNG, is_simulated: false };

    check("accepted sale prints the verbatim Tax Asaan / 9966 statement", () => {
        assert.equal(TAX_ASAAN_STATEMENT,
            "Verify this invoice through FBR Tax Asaan Mobile App or SMS at 9966 and win exciting prizes in draw.");
        assert.ok(renderFiscalReceipt(accepted).includes(TAX_ASAAN_STATEMENT));
    });

    check("QR is printed at 7x7 mm with a white quiet zone and no smoothing", () => {
        const html = renderFiscalReceipt(accepted);
        assert.match(html, /class="fbr-qr" style="width:7mm;height:7mm;padding:1\.2mm;box-sizing:content-box;background:#fff;image-rendering:pixelated;/);
        assert.doesNotMatch(html, /h-32|w-32/, "old 32-unit (about 34 mm) size is gone");
    });

    check("FBR logo only when the operator supplied one; never a made-up default", () => {
        assert.doesNotMatch(renderFiscalReceipt(accepted), /fbr-logo/);
        const html = renderFiscalReceipt(accepted, { logoUrl: "/branding/fbr-pos-logo.png" });
        assert.match(html, /<img src="\/branding\/fbr-pos-logo\.png" class="fbr-logo"/);
        assert.doesNotMatch(renderFiscalReceipt(accepted, { logoUrl: "javascript:alert(1)" }), /fbr-logo|javascript/);
    });

    check("logo, QR and statement never appear on a sale that is not genuinely accepted", () => {
        const options = { logoUrl: "/branding/fbr-pos-logo.png" };
        for (const status of ["simulated", "pending", "unknown", "failed", "rejected", "not_submitted", "not_fiscalized", "not_configured"]) {
            const html = renderFiscalReceipt({ ...accepted, status }, options);
            assert.doesNotMatch(html, /fbr-logo|fbr-qr|9966|Tax Asaan/, status);
        }
        // Belt and braces: "accepted" flagged simulated is still not fiscal.
        const flagged = renderFiscalReceipt({ ...accepted, is_simulated: true }, options);
        assert.doesNotMatch(flagged, /fbr-logo|fbr-qr|9966|123456ABCD/);
        assert.match(flagged, /not fiscalized/i);
    });

    check("hostile number is escaped and a hostile QR payload is not rendered", () => {
        const html = renderFiscalReceipt({
            status: "accepted",
            fbr_invoice_number: `<img src=x onerror=alert(1)>`,
            qr_png_base64: `x" onerror="alert(1)`,
        });
        assert.doesNotMatch(html, /<img/);
        assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
    });
});

console.log(failures ? `\n${failures} check(s) failed` : "\nall fiscal receipt checks passed");
process.exit(failures ? 1 : 0);
