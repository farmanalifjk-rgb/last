/*
 * Rendering of the printed sale receipt (receipt.html).
 *
 * Input is the backend receipt payload (GET /api/pos/orders/<id>/receipt/):
 *   { fiscal, business, order, fiscal_lines, items, tenders, totals }
 * Layout follows S.R.O. 1006(I)/2021 where the data exists: business NTN and
 * PoS registration number, sequential invoice number, cashier, mode of
 * payment, and per item: price excl. tax, GST rate, quantity, GST and total.
 * STRN and tax office are not printed yet (not captured by the system).
 */
import { escapeHtml, safeUrl } from "./format.js";
import { renderFiscalReceipt } from "./fiscal-receipt.js";

export const PAPER_SIZES = ["58mm", "80mm", "A5", "A4"];

export function money(value) {
    const number = Number.parseFloat(value);
    return Number.isFinite(number)
        ? number.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        : "0.00";
}

function dateTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString("en-PK");
}

function rate(value) {
    if (value === null || value === undefined || value === "") return "-";
    const number = Number.parseFloat(value);
    return Number.isFinite(number) ? `${number.toFixed(number % 1 ? 2 : 0)}%` : "-";
}

export function normalizePaper(value) {
    return PAPER_SIZES.includes(value) ? value : "80mm";
}

/** @page rule for the configured paper (thermal rolls: driver sets the roll, no margins). */
export function pageCss(paper) {
    const size = normalizePaper(paper);
    if (size === "A4" || size === "A5") return `@page { size: ${size} portrait; margin: 10mm; }`;
    return "@page { margin: 0; }";
}

export function renderReceiptHeader(company) {
    const logoUrl = safeUrl(company.logo);
    const logo = logoUrl
        ? `<div class="flex justify-center mb-3"><img src="${escapeHtml(logoUrl)}" class="receipt-logo h-24 object-contain" alt=""></div>`
        : "";
    const taxNumber = company.tax_number || company.gst || "";
    const ntn = company.ntn || "";
    return `${logo}
      <div class="text-center">
        <h1 class="text-3xl font-bold">${escapeHtml(company.name)}</h1>
        ${company.tagline ? `<p class="text-gray-600">${escapeHtml(company.tagline)}</p>` : ""}
        ${company.address ? `<p class="text-sm">${escapeHtml(company.address)}</p>` : ""}
        ${company.phone ? `<p class="text-sm">Tel: ${escapeHtml(company.phone)}</p>` : ""}
        ${company.email ? `<p class="text-sm">${escapeHtml(company.email)}</p>` : ""}
        ${company.website ? `<p class="text-sm">${escapeHtml(company.website)}</p>` : ""}
        ${ntn ? `<p class="text-sm">NTN: ${escapeHtml(ntn)}</p>` : ""}
        ${!ntn || (taxNumber && taxNumber !== ntn) ? `<p class="text-sm">Tax no: ${escapeHtml(taxNumber || "-")}</p>` : ""}
        ${company.pos_registration_number ? `<p class="text-sm">POS ID: ${escapeHtml(company.pos_registration_number)}</p>` : ""}
      </div>
      <hr class="my-4">`;
}

function fiscalItemRows(lines) {
    return lines.map((line) => {
        const discount = Number.parseFloat(line.discount);
        return `
      <tr class="receipt-line-head"><td class="pt-1 align-top">${escapeHtml(line.line_number)}</td><td class="pt-1" colspan="5">${escapeHtml(line.description)}</td></tr>
      <tr class="receipt-line-figures">
        <td></td>
        <td class="text-right">${money(line.unit_price)}</td>
        <td class="text-right">${escapeHtml(rate(line.tax_rate))}</td>
        <td class="text-right">${escapeHtml(line.quantity)}</td>
        <td class="text-right">${money(line.tax)}</td>
        <td class="text-right">${money(line.total)}</td>
      </tr>${Number.isFinite(discount) && discount > 0 ? `
      <tr class="receipt-line-discount"><td></td><td colspan="4">Discount</td><td class="text-right">-${money(line.discount)}</td></tr>` : ""}`;
    }).join("");
}

function renderItems(data) {
    const lines = Array.isArray(data.fiscal_lines) ? data.fiscal_lines : [];
    if (lines.length) {
        return `
      <table class="receipt-items w-full text-sm mb-4">
        <thead>
          <tr><th class="text-left">#</th><th class="text-left" colspan="5">Description</th></tr>
          <tr class="border-b"><th></th><th class="text-right">Price</th><th class="text-right">GST Rate</th><th class="text-right">Qty</th><th class="text-right">GST</th><th class="text-right">Total</th></tr>
        </thead>
        <tbody>${fiscalItemRows(lines)}</tbody>
      </table>`;
    }
    // No fiscal invoice (FBR not configured): plain order lines.
    const rows = (data.items || []).map((item) => `
      <tr>
        <td class="py-1">${escapeHtml(item.name)}</td>
        <td class="py-1 text-right">${escapeHtml(item.quantity)}</td>
        <td class="py-1 text-right">${money(item.unit_price)}</td>
        <td class="py-1 text-right">${money(item.subtotal)}</td>
      </tr>`).join("");
    return `
      <table class="receipt-items w-full text-sm mb-4">
        <thead>
          <tr class="border-b"><th class="text-left">Item</th><th class="text-right">Qty</th><th class="text-right">Price</th><th class="text-right">Amount</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
}

/**
 * @param options.copy copy number from POST .../receipt/printed/ (null = unknown)
 * @param options.fbrLogoUrl operator-provided official FBR PoS logo URL
 */
export function renderReceiptBody(data, company, { copy = null, fbrLogoUrl = "" } = {}) {
    const order = data.order || {};
    const fiscal = data.fiscal || {};
    const t = data.totals || {};
    const tenders = Array.isArray(data.tenders) ? data.tenders : [];
    const currency = t.currency || company.currency || "";
    const reprint = Number.isInteger(copy) && copy > 1
        ? `<p class="receipt-reprint text-center font-bold mb-2">DUPLICATE - REPRINT (copy ${copy})</p>`
        : "";
    const tenderRows = tenders.map((tender) => `
      <tr>
        <td>${escapeHtml(tender.label || tender.tender_type)}${tender.reference ? ` (${escapeHtml(tender.reference)})` : ""}</td>
        <td class="text-right">${money(tender.amount)}</td>
      </tr>`).join("");
    const subtotal = Number.parseFloat(t.subtotal);
    const discount = Number.parseFloat(t.discount);
    const saleValue = Number.isFinite(subtotal) ? subtotal - (Number.isFinite(discount) ? discount : 0) : NaN;
    return `${reprint}
      <table class="w-full text-sm mb-4">
        <tr><td><b>SALES RECEIPT</b></td><td class="text-right">${escapeHtml(order.number)}</td></tr>
        ${fiscal.invoice_number ? `<tr><td><b>Invoice No.</b></td><td class="text-right">${escapeHtml(fiscal.invoice_number)}</td></tr>` : ""}
        <tr><td><b>Date</b></td><td class="text-right">${escapeHtml(dateTime(order.created_at))}</td></tr>
        ${order.cashier ? `<tr><td><b>Cashier</b></td><td class="text-right">${escapeHtml(order.cashier)}</td></tr>` : ""}
        <tr><td><b>Customer</b></td><td class="text-right">${escapeHtml(order.customer || "Walk-in customer")}</td></tr>
      </table>
      ${renderItems(data)}
      <hr class="my-4">
      <table class="w-full text-sm">
        <tr><td>Subtotal</td><td class="text-right">${money(t.subtotal)}</td></tr>
        <tr><td>Discount</td><td class="text-right">${money(t.discount)}</td></tr>
        ${Number.isFinite(saleValue) ? `<tr><td>Sale value (excl. tax)</td><td class="text-right">${money(saleValue)}</td></tr>` : ""}
        <tr><td>Sales tax (GST)</td><td class="text-right">${money(t.tax)}</td></tr>
        <tr class="font-bold"><td>Total payable (${escapeHtml(currency)})</td><td class="text-right">${money(t.total)}</td></tr>
      </table>
      ${tenders.length ? `<hr class="my-4"><p class="text-sm"><b>Payment</b></p><table class="w-full text-sm">${tenderRows}</table>` : ""}
      <table class="w-full text-sm mt-2">
        <tr><td>Received</td><td class="text-right">${money(t.received)}</td></tr>
        <tr><td>Change</td><td class="text-right">${money(t.change)}</td></tr>
      </table>
      ${renderFiscalReceipt(data.fiscal, { logoUrl: fbrLogoUrl })}
      <hr class="my-4">
      <p class="text-center text-sm">${escapeHtml(company.footer_message || "")}</p>`;
}

/**
 * Resolve once every <img> under root has loaded or failed (or after timeoutMs),
 * so the print dialog never captures a receipt without its QR or logo.
 */
export function waitForImages(root, timeoutMs = 3000) {
    const images = Array.from(root?.querySelectorAll?.("img") || []);
    const pending = images
        .filter((img) => !img.complete)
        .map((img) => new Promise((resolve) => {
            img.addEventListener("load", resolve, { once: true });
            img.addEventListener("error", resolve, { once: true });
        }));
    if (!pending.length) return Promise.resolve();
    return Promise.race([
        Promise.all(pending),
        new Promise((resolve) => setTimeout(resolve, timeoutMs)),
    ]);
}

/**
 * Drop images matching selector that failed to load (missing file, 404), so
 * the printout never shows a broken-image icon. Call after waitForImages.
 */
export function removeBrokenImages(root, selector) {
    const images = Array.from(root?.querySelectorAll?.(selector) || []);
    let removed = 0;
    for (const img of images) {
        if (img.complete && !img.naturalWidth) {
            (img.closest?.("div") || img).remove();
            removed += 1;
        }
    }
    return removed;
}
