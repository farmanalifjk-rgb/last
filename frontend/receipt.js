/*
 * Standalone receipt page (receipt.html?type=sale&id=<orderId>).
 *
 * Data comes from the backend (same-origin relative URLs unless VITE_API_BASE_URL is set):
 *   GET  /api/pos/orders/<id>/receipt/          -> { fiscal, business, order, fiscal_lines, items, tenders, totals }
 *   POST /api/pos/orders/<id>/receipt/printed/  -> { copy, reprint }  (audited; copy > 1 prints as a reprint)
 *   GET  /api/company/                          -> fallback header for older backends
 * Refund receipts have no backend endpoint yet, so that type is reported as unavailable.
 *
 * FBR PoS invoicing-system logo (S.R.O. 1006): /fbr/fbr-pos-logo.png
 * (frontend/public/fbr/, the business-supplied official file). Override with
 * VITE_FBR_POS_LOGO_URL; set it to an empty value to print no logo.
 */
import {
  normalizePaper, pageCss, removeBrokenImages, renderReceiptBody, renderReceiptHeader, waitForImages,
} from "./src/shared/receipt-render.js";
import { DEFAULT_FBR_LOGO_URL } from "./src/shared/fiscal-receipt.js";

(function () {
  "use strict";

  const TOKEN_KEY = "pos_auth_token";
  const ENV = import.meta.env || {};
  // Same contract as src/services/api.js: empty means same-origin relative /api URLs.
  const API_BASE = String(ENV.VITE_API_BASE_URL || "").replace(/\/$/, "");
  const FBR_LOGO_URL = ENV.VITE_FBR_POS_LOGO_URL === undefined
    ? DEFAULT_FBR_LOGO_URL
    : String(ENV.VITE_FBR_POS_LOGO_URL);

  // When printed from the till's hidden frame, report the outcome so a failure
  // is shown to the cashier instead of dying silently in an invisible frame.
  function notifyParent(status, message = "") {
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: "pos-receipt", status, message }, window.location.origin);
      }
    } catch (_) { /* no parent to tell */ }
  }

  function showMessage(text) {
    const root = document.getElementById("receipt");
    root.textContent = text;
  }

  function showScreenWarning(text) {
    // Visible on screen, never printed on the customer's receipt.
    const banner = document.createElement("p");
    banner.className = "screen-only receipt-warning";
    banner.textContent = text;
    document.body.insertBefore(banner, document.body.firstChild);
  }

  function sessionBusinessName() {
    try {
      return JSON.parse(localStorage.getItem("pos_user") || "{}")?.tenant?.name || "";
    } catch (_) {
      return "";
    }
  }

  async function requestJson(path, { method = "GET" } = {}) {
    const headers = { Accept: "application/json" };
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers.Authorization = `Token ${token}`;
    if (method !== "GET") headers["Content-Type"] = "application/json";
    const response = await fetch(`${API_BASE}${path}`, { method, headers, body: method === "GET" ? undefined : "{}" });
    let data = {};
    try { data = await response.json(); } catch (_) { /* not JSON */ }
    if (!response.ok) {
      throw new Error(data?.error?.message || data?.detail || `Request failed (${response.status})`);
    }
    return data;
  }

  function applyPaper(receipt, paper) {
    receipt.classList.remove("paper-58mm", "paper-80mm", "paper-A5", "paper-A4");
    receipt.classList.add(`paper-${paper}`);
    const style = document.createElement("style");
    style.id = "receipt-page-size";
    style.textContent = pageCss(paper);
    document.getElementById("receipt-page-size")?.remove();
    document.head.appendChild(style);
  }

  async function loadReceipt() {
    const params = new URLSearchParams(window.location.search);
    const type = params.get("type");
    const id = params.get("id");

    if (type === "refund") {
      showMessage("Refund receipts are not available yet.");
      notifyParent("error", "Refund receipts are not available yet.");
      return;
    }
    if (type !== "sale" || !/^\d+$/.test(id || "")) {
      showMessage("Unknown receipt.");
      notifyParent("error", "Unknown receipt.");
      return;
    }

    try {
      const orderPath = `/api/pos/orders/${encodeURIComponent(id)}`;
      const data = await requestJson(`${orderPath}/receipt/`);
      // The receipt carries its business header, so cashiers (no access to
      // /api/company/) can print. Older backends: fall back, never fail on it.
      const company = data.business
        || await requestJson("/api/company/").catch(() => ({ name: sessionBusinessName() }));
      // Every print is audited; copies after the first are marked as reprints.
      // If recording fails the customer still gets a receipt, but the cashier
      // sees on screen that this print is not in the audit trail.
      let copy = null;
      try {
        copy = (await requestJson(`${orderPath}/receipt/printed/`, { method: "POST" })).copy ?? null;
      } catch (error) {
        showScreenWarning(`This print was not recorded in the audit log: ${error.message}`);
      }
      const receipt = document.getElementById("receipt");
      applyPaper(receipt, normalizePaper(company.receipt_paper));
      receipt.innerHTML = renderReceiptHeader(company) + renderReceiptBody(data, company, { copy, fbrLogoUrl: FBR_LOGO_URL });
      await waitForImages(receipt);
      // A missing logo file must not print as a broken image.
      if (removeBrokenImages(receipt, "img.fbr-logo, img.receipt-logo")) {
        showScreenWarning("A receipt logo could not be loaded and was left off this print.");
      }
      window.print();
      notifyParent("printed");
    } catch (error) {
      showMessage(`Could not load receipt: ${error.message}`);
      notifyParent("error", error.message);
    }
  }

  loadReceipt();
})();
