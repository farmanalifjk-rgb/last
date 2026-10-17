/*
 * Order history and refunds.
 *
 * Backend contract (canonical POS API):
 *   GET  /api/pos/orders/?page&search&customer_id&status&date_from&date_to
 *   GET  /api/pos/orders/<id>/                 order with items
 *   GET  /api/pos/orders/<id>/receipt/         receipt (opened in receipt.html)
 *   GET  /api/pos/refunds/order/<id>/          sold / refunded / remaining per item
 *   POST /api/pos/refunds/                     process a refund
 *   GET  /api/customers/                       customer filter
 *
 * Export is generated in the browser from the rows on the current page, because
 * the backend has no order export endpoint.
 */
import { createIcons, icons } from "lucide";
import { apiJson, buildQuery } from "../services/api.js";
import { escapeHtml, formatMoney, formatDateTime, downloadCsv } from "../shared/format.js";
import { hasPermission } from "../services/auth.js";
import { toast } from "../shared/ui.js";
import { collectRefundItems } from "./refund-logic.js";

const PAGE_SIZE = 20;

// Sidebar filter → backend order status (null = no status filter).
const STATUS_BY_FILTER = {
  all: null,
  completed: "paid",
  refunds: "refunded",
  "partial-refunds": "partially_refunded",
  draft: "draft",
};

const STATUS_BADGE = {
  paid: ["Completed", "bg-emerald-50 text-emerald-700 border-emerald-200"],
  partially_refunded: ["Partially refunded", "bg-amber-50 text-amber-700 border-amber-200"],
  refunded: ["Refunded", "bg-red-50 text-red-700 border-red-200"],
  draft: ["Draft", "bg-gray-100 text-gray-600 border-gray-200"],
  cancelled: ["Cancelled", "bg-gray-100 text-gray-500 border-gray-200"],
};

const state = {
  page: 1,
  totalPages: 1,
  hasNext: false,
  hasPrevious: false,
  status: null,
  rows: [],
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function el(id) {
  return document.getElementById(id);
}

function statusBadge(status) {
  const [label, classes] = STATUS_BADGE[status] || [status || "-", "bg-gray-100 text-gray-600 border-gray-200"];
  return `<span class="inline-flex px-2.5 py-1 rounded-full border text-xs font-semibold ${classes}">${escapeHtml(label)}</span>`;
}

function errorText(error) {
  return escapeHtml(error?.message || "Something went wrong.");
}

/** Start date for the "date" filter, in the user's local timezone. */
function dateRange(filter) {
  const today = new Date();
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  if (filter === "today") return { date_from: iso(today), date_to: iso(today) };
  if (filter === "yesterday") {
    const y = new Date(today);
    y.setDate(today.getDate() - 1);
    return { date_from: iso(y), date_to: iso(y) };
  }
  if (filter === "week") {
    const start = new Date(today);
    start.setDate(today.getDate() - ((today.getDay() + 6) % 7));
    return { date_from: iso(start), date_to: iso(today) };
  }
  if (filter === "month") {
    return { date_from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), date_to: iso(today) };
  }
  return {};
}

function statusFromHash() {
  const query = window.location.hash.split("?")[1] || "";
  const filter = new URLSearchParams(query).get("filter") || "all";
  return Object.prototype.hasOwnProperty.call(STATUS_BY_FILTER, filter) ? filter : "all";
}

// ─── Initialisation ──────────────────────────────────────────────────────────

window.initializeOrderHistory = async function () {
  bindControls();
  const filter = statusFromHash();
  state.status = STATUS_BY_FILTER[filter];
  await loadCustomerFilter();
  await loadOrders();
};

function bindControls() {
  let searchTimer = null;
  el("search-input")?.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.page = 1;
      loadOrders();
    }, 300);
  });
  el("customer-filter")?.addEventListener("change", () => { state.page = 1; loadOrders(); });
  el("date-filter")?.addEventListener("change", () => { state.page = 1; loadOrders(); });
  el("prev-page")?.addEventListener("click", () => {
    if (!state.hasPrevious) return;
    state.page -= 1;
    loadOrders();
  });
  el("next-page")?.addEventListener("click", () => {
    if (!state.hasNext) return;
    state.page += 1;
    loadOrders();
  });
}

/** Sidebar filter links change the hash; the router re-renders the page and calls initializeOrderHistory again. */
function applySidebarFilterFromHash() {
  if (!el("orders-table")) return;
  const filter = statusFromHash();
  state.status = STATUS_BY_FILTER[filter];
  state.page = 1;
  loadOrders();
}

async function loadCustomerFilter() {
  const select = el("customer-filter");
  if (!select) return;
  try {
    const data = await apiJson("/api/customers/?page_size=100");
    const customers = data.results || data;
    const current = select.value;
    select.innerHTML = `<option value="">All Customers</option>${customers
      .map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`)
      .join("")}`;
    select.value = current;
  } catch (error) {
    console.error("Failed to load customers", error);
  }
}

// ─── List ─────────────────────────────────────────────────────────────────────

async function loadOrders() {
  const table = el("orders-table");
  if (!table) return;

  const params = {
    page: state.page,
    search: el("search-input")?.value.trim() || "",
    customer_id: el("customer-filter")?.value || "",
    status: state.status || "",
    ...dateRange(el("date-filter")?.value || ""),
  };

  table.innerHTML = `<tr><td colspan="6" class="px-6 py-10 text-center text-gray-400 text-sm">Loading orders…</td></tr>`;
  try {
    const data = await apiJson(`/api/pos/orders/${buildQuery(params)}`);
    state.rows = data.results || [];
    state.totalPages = data.total_pages || 1;
    state.hasNext = Boolean(data.has_next);
    state.hasPrevious = Boolean(data.has_previous);
    renderRows(state.rows);
    const info = el("page-info");
    if (info) info.textContent = `Page ${data.page || state.page} of ${state.totalPages} · ${data.count ?? state.rows.length} orders`;
    const prev = el("prev-page");
    const next = el("next-page");
    if (prev) prev.disabled = !state.hasPrevious;
    if (next) next.disabled = !state.hasNext;
    createIcons({ icons });
  } catch (error) {
    table.innerHTML = `<tr><td colspan="6" class="px-6 py-10 text-center text-red-600 text-sm">Could not load orders: ${errorText(error)}</td></tr>`;
  }
}

function renderRows(rows) {
  const table = el("orders-table");
  if (!rows.length) {
    table.innerHTML = `<tr><td colspan="6" class="px-6 py-10 text-center text-gray-400 text-sm">No orders match these filters.</td></tr>`;
    return;
  }
  table.innerHTML = rows
    .map((order) => {
      // UI hint only; POST /api/pos/refunds/ enforces pos.refund server-side.
      const canRefund = (order.status === "paid" || order.status === "partially_refunded") && hasPermission("pos.refund");
      return `
      <tr class="hover:bg-gray-50">
        <td class="px-6 py-4 font-medium text-gray-900">${escapeHtml(order.order_number)}</td>
        <td class="px-6 py-4 text-gray-700">${escapeHtml(order.customer_name)}</td>
        <td class="px-6 py-4 text-right font-semibold text-gray-900">${escapeHtml(formatMoney(order.total))}</td>
        <td class="px-6 py-4 text-gray-600">${escapeHtml(order.payment_method || "-")}</td>
        <td class="px-6 py-4 text-gray-600">${escapeHtml(formatDateTime(order.created_at))}</td>
        <td class="px-6 py-4">
          <div class="flex items-center gap-2">
            ${statusBadge(order.status)}
            <button onclick="viewOrder(${Number(order.id)})" class="px-2.5 py-1 text-xs border border-gray-200 rounded-lg hover:bg-gray-50">View</button>
            ${canRefund ? `<button onclick="openRefund(${Number(order.id)})" class="px-2.5 py-1 text-xs border border-red-200 text-red-600 rounded-lg hover:bg-red-50">Refund</button>` : ""}
            ${order.status !== "draft" ? `<button onclick="reprintReceipt(${Number(order.id)})" class="px-2.5 py-1 text-xs border border-gray-200 rounded-lg hover:bg-gray-50">Receipt</button>` : ""}
          </div>
        </td>
      </tr>`;
    })
    .join("");
}

// ─── Order detail ─────────────────────────────────────────────────────────────

window.viewOrder = async function (orderId) {
  const body = el("modal-body");
  body.innerHTML = `<p class="text-sm text-gray-400">Loading order…</p>`;
  openModal("order-modal");
  try {
    const order = await apiJson(`/api/pos/orders/${Number(orderId)}/`);
    const items = (order.items || [])
      .map((item) => `
        <tr class="border-b border-gray-100">
          <td class="py-2">${escapeHtml(item.name)}</td>
          <td class="py-2 text-right">${escapeHtml(item.quantity)}</td>
          <td class="py-2 text-right">${escapeHtml(formatMoney(item.unit_price))}</td>
          <td class="py-2 text-right">${escapeHtml(formatMoney(item.subtotal))}</td>
        </tr>`)
      .join("");
    body.innerHTML = `
      <div class="flex items-start justify-between mb-5">
        <div>
          <p class="text-xs uppercase tracking-wide text-gray-400">Order</p>
          <h3 class="text-xl font-bold text-gray-950">${escapeHtml(order.order_number)}</h3>
          <p class="text-sm text-gray-500">${escapeHtml(formatDateTime(order.created_at))} · ${escapeHtml(order.customer_name)}</p>
        </div>
        ${statusBadge(order.status)}
      </div>
      <table class="w-full text-sm mb-4">
        <thead><tr class="text-gray-500 border-b"><th class="text-left py-2">Item</th><th class="text-right">Qty</th><th class="text-right">Price</th><th class="text-right">Amount</th></tr></thead>
        <tbody>${items || `<tr><td colspan="4" class="py-4 text-center text-gray-400">No items</td></tr>`}</tbody>
      </table>
      <div class="ml-auto w-64 text-sm space-y-1">
        <div class="flex justify-between"><span>Subtotal</span><span>${escapeHtml(formatMoney(order.subtotal))}</span></div>
        <div class="flex justify-between"><span>Discount</span><span>${escapeHtml(formatMoney(order.discount))}</span></div>
        <div class="flex justify-between"><span>Tax</span><span>${escapeHtml(formatMoney(order.tax))}</span></div>
        <div class="flex justify-between font-bold text-base border-t pt-2"><span>Total</span><span>${escapeHtml(formatMoney(order.total))}</span></div>
        <div class="flex justify-between text-gray-500"><span>Paid (${escapeHtml(order.payment_method || "-")})</span><span>${escapeHtml(formatMoney(order.amount_received))}</span></div>
        <div class="flex justify-between text-gray-500"><span>Change</span><span>${escapeHtml(formatMoney(order.change_amount))}</span></div>
      </div>`;
  } catch (error) {
    body.innerHTML = `<p class="text-sm text-red-600">Could not load order: ${errorText(error)}</p>`;
  }
};

window.reprintReceipt = function (orderId) {
  window.open(`/receipt.html?type=sale&id=${encodeURIComponent(orderId)}`, "_blank");
};

// ─── Refunds ──────────────────────────────────────────────────────────────────

window.openRefund = async function (orderId) {
  const body = el("refund-body");
  body.innerHTML = `<p class="text-sm text-gray-400">Loading refundable items…</p>`;
  openModal("refund-modal");
  try {
    const data = await apiJson(`/api/pos/refunds/order/${Number(orderId)}/`);
    const rows = data.items || [];
    const refundable = rows.filter((row) => Number(row.remaining_quantity) > 0);
    if (!refundable.length) {
      body.innerHTML = `<p class="text-sm text-gray-500">Every item on this order has already been refunded.</p>`;
      return;
    }
    body.innerHTML = `
      <div class="space-y-4" data-refund-order="${Number(orderId)}">
        <table class="w-full text-sm">
          <thead><tr class="text-gray-500 border-b"><th class="text-left py-2">Item</th><th class="text-right">Sold</th><th class="text-right">Refunded</th><th class="text-right">Remaining</th><th class="text-right">Refund qty</th></tr></thead>
          <tbody>
            ${rows.map((row) => `
              <tr class="border-b border-gray-100">
                <td class="py-2">${escapeHtml(row.name)}</td>
                <td class="py-2 text-right">${escapeHtml(row.sold_quantity)}</td>
                <td class="py-2 text-right">${escapeHtml(row.refunded_quantity)}</td>
                <td class="py-2 text-right">${escapeHtml(row.remaining_quantity)}</td>
                <td class="py-2 text-right">
                  <input type="number" min="0" step="0.001" max="${escapeHtml(row.remaining_quantity)}" value="0"
                    data-order-item-id="${Number(row.order_item_id)}" data-remaining="${escapeHtml(row.remaining_quantity)}" data-name="${escapeHtml(row.name)}" ${Number(row.remaining_quantity) > 0 ? "" : "disabled"}
                    class="w-24 h-9 px-2 border border-gray-200 rounded-lg text-right">
                </td>
              </tr>`).join("")}
          </tbody>
        </table>
        <div class="grid grid-cols-2 gap-4">
          <label class="text-sm text-gray-600">Reason
            <input id="refund-reason" type="text" maxlength="255" class="mt-1 w-full h-10 px-3 border border-gray-200 rounded-lg">
          </label>
          <label class="text-sm text-gray-600">Cash returned to customer
            <input id="refund-cash" type="number" min="0" step="0.01" value="0" class="mt-1 w-full h-10 px-3 border border-gray-200 rounded-lg">
          </label>
        </div>
        <p id="refund-error" class="text-sm text-red-600 hidden"></p>
        <div class="flex justify-end gap-3">
          <button onclick="closeRefundModal()" class="px-4 py-2 border border-gray-200 rounded-lg text-sm">Cancel</button>
          <button id="refund-submit" type="button" onclick="processRefund(${Number(orderId)})" class="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-semibold hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60">Process refund</button>
        </div>
      </div>`;
  } catch (error) {
    body.innerHTML = `<p class="text-sm text-red-600">Could not load refund details: ${errorText(error)}</p>`;
  }
};

let refundInFlight = false;

window.processRefund = async function (orderId) {
  // One request at a time: a double click must never post a second refund.
  if (refundInFlight) return;
  const errorBox = el("refund-error");
  const showError = (message) => {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  };
  errorBox.classList.add("hidden");

  const entries = [...document.querySelectorAll("[data-order-item-id]")].map((input) => ({
    orderItemId: input.dataset.orderItemId,
    name: input.dataset.name || "this item",
    remaining: input.dataset.remaining,
    quantity: input.value,
  }));
  const { items, cash, error } = collectRefundItems(entries, el("refund-cash")?.value);
  if (error) return showError(error);

  const button = el("refund-submit");
  refundInFlight = true;
  if (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "Processing…";
  }
  try {
    const result = await apiJson("/api/pos/refunds/", {
      method: "POST",
      body: JSON.stringify({
        order_id: Number(orderId),
        items,
        reason: el("refund-reason")?.value.trim() || "",
        cash_refund_amount: cash,
      }),
    });
    closeRefundModal();
    toast(`Refund #${result.id} processed for ${formatMoney(result.total_amount)}.`, "success");
    await loadOrders();
  } catch (error) {
    // Nothing was refunded on an error response; the cashier may correct and retry.
    showError(`Refund failed: ${error.message}`);
  } finally {
    refundInFlight = false;
    if (button?.isConnected) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = "Process refund";
    }
  }
};

// ─── Modals ───────────────────────────────────────────────────────────────────

function openModal(id) {
  const modal = el(id);
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

function closeModalById(id) {
  const modal = el(id);
  modal.classList.remove("flex");
  modal.classList.add("hidden");
}

window.closeModal = () => closeModalById("order-modal");
window.closeRefundModal = () => closeModalById("refund-modal");

// ─── Export ───────────────────────────────────────────────────────────────────

window.toggleExportMenu = function (event) {
  event?.stopPropagation();
  el("export-menu")?.classList.toggle("hidden");
};

window.closeExportMenu = function () {
  el("export-menu")?.classList.add("hidden");
};

window.exportCSV = function () {
  downloadCsv("orders.csv", [
    { label: "Order", value: (r) => r.order_number },
    { label: "Customer", value: (r) => r.customer_name },
    { label: "Status", value: (r) => r.status },
    { label: "Subtotal", value: (r) => r.subtotal },
    { label: "Discount", value: (r) => r.discount },
    { label: "Tax", value: (r) => r.tax },
    { label: "Total", value: (r) => r.total },
    { label: "Payment", value: (r) => r.payment_method },
    { label: "Date", value: (r) => r.created_at },
  ], state.rows);
};

window.applySidebarOrderFilter = applySidebarFilterFromHash;
window.filterStatus = () => applySidebarFilterFromHash();
window.performSearch = () => { state.page = 1; loadOrders(); };
