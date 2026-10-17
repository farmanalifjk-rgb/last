/*
 * FBR block of the printed sale receipt.
 *
 * Input is the backend `fiscal` object (fiscal.pos_fiscalization.pos_fiscal_status).
 * The FBR number and QR are printed ONLY for a genuine acceptance; simulated,
 * pending, failed or rejected sales must never look fiscalized.
 */
import { escapeHtml, safeUrl } from "./format.js";

export const FISCAL_NOTICES = {
    pending: "FBR: pending - this sale is not yet fiscalized.",
    unknown: "FBR: outcome being verified - not yet fiscalized.",
    failed: "FBR: not fiscalized (submission failed).",
    rejected: "FBR: not fiscalized (rejected by FBR).",
    not_submitted: "FBR: not fiscalized (not submitted).",
    not_fiscalized: "FBR: not fiscalized.",
    simulated: "SIMULATED - NOT AN FBR INVOICE. Not fiscalized.",
};

export const NOT_CONFIGURED_NOTICE = "Not an FBR fiscal invoice.";

// S.R.O. 1006(I)/2021 (D): statement printed on every FBR PoS invoice.
export const TAX_ASAAN_STATEMENT =
    "Verify this invoice through FBR Tax Asaan Mobile App or SMS at 9966 and win exciting prizes in draw.";

// S.R.O. 1006(I)/2021 (D)(ii): logo of FBR's PoS invoicing system. The file is
// the business-supplied official artwork served from frontend/public/fbr/.
export const DEFAULT_FBR_LOGO_URL = "/fbr/fbr-pos-logo.png";

// S.R.O. 1006(I)/2021 (D) and Sales Tax Rules 150R(13): verifiable QR code of
// 7x7 mm. The backend sends the bare symbol; the white padding below is the
// quiet zone (about 4 modules at this size) that scanners need around it.
export const FBR_QR_SIZE_MM = 7;
const QR_STYLE = `width:${FBR_QR_SIZE_MM}mm;height:${FBR_QR_SIZE_MM}mm;padding:1.2mm;`
    + "box-sizing:content-box;background:#fff;image-rendering:pixelated;image-rendering:crisp-edges;";

const BASE64_PNG = /^[A-Za-z0-9+/]+={0,2}$/;

/**
 * @param fiscal backend `fiscal` block
 * @param options.logoUrl URL of the official FBR PoS invoicing-system logo, set
 *   by the operator (VITE_FBR_POS_LOGO_URL). Never bundled or guessed here:
 *   without it no logo is printed.
 */
export function renderFiscalReceipt(fiscal, { logoUrl = "" } = {}) {
    if (!fiscal || !fiscal.status) return "";
    if (fiscal.status === "not_configured") {
        // Phase 5: say so explicitly (small, neutral) instead of printing
        // nothing, so a non-FBR receipt is never mistaken for a fiscal one.
        return `
      <p class="mt-3 text-center text-xs text-gray-500">${escapeHtml(NOT_CONFIGURED_NOTICE)}</p>`;
    }
    // Genuine acceptance only: the backend never reports a simulated sale as
    // "accepted", and is_simulated is checked again here as a second guard.
    if (fiscal.status === "accepted" && fiscal.fbr_invoice_number && !fiscal.is_simulated) {
        const png = String(fiscal.qr_png_base64 || "");
        const qr = BASE64_PNG.test(png)
            ? `<div class="flex justify-center mt-2"><img src="data:image/png;base64,${png}" class="fbr-qr" style="${QR_STYLE}" alt="FBR invoice QR code"></div>`
            : "";
        const logoSrc = safeUrl(logoUrl);
        const logo = logoSrc
            ? `<div class="flex justify-center mb-1"><img src="${escapeHtml(logoSrc)}" class="fbr-logo" style="height:12mm;width:auto;" alt="FBR POS invoicing system"></div>`
            : "";
        return `
      <hr class="my-4">
      <div class="fbr-block text-center text-sm">
        ${logo}
        <p><b>FBR POS Invoice No.</b></p>
        <p class="font-mono">${escapeHtml(fiscal.fbr_invoice_number)}</p>
        ${qr}
        <p class="fbr-statement text-xs mt-2">${escapeHtml(TAX_ASAAN_STATEMENT)}</p>
      </div>`;
    }
    const notice = FISCAL_NOTICES[fiscal.status] || FISCAL_NOTICES.not_fiscalized;
    return `
      <hr class="my-4">
      <p class="text-center text-sm font-bold">${escapeHtml(notice)}</p>`;
}
