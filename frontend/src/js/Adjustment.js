import { downloadCsv, escapeHtml, loadErrorHtml } from "../shared/format.js";
import { apiList } from "../services/api.js";
import { openModal, field, fieldGrid, readForm, requireValue, toNumber, toast, errorMessage } from "../shared/ui.js";
import { collectAllPages } from "../shared/export-all.js";
import { createIcons, icons } from "lucide";

import { getAdjustments, getAdjustment, createAdjustment, adjustmentCsvRows } from "../js/inventory/services/inventory-api";
import { AdjustmentDetailModal } from "./Adjustments/components/AdjustmentDetailModal";
import { Pagination } from "../shared/Pagination";


let filters = {

    search: "",

    reason: "",

    date: "",

    start_date: "",

    end_date: "",

    page: 1,

    page_size: 20,

    ordering: "-created_at",

};

// ============================================================================
// PAGINATION
// ============================================================================
const pagination = new Pagination({

    prevButtonId: "prev-page",

    nextButtonId: "next-page",

    containerId: "pagination-numbers",

    pageSize: filters.page_size,

    onPageChange: async (page) => {

        filters.page = page;

        await loadAdjustments();

    }

});


window.initializeAdjustments = async function () {

    // The toolbar renders empty on every visit; keep the filters in step.
    filters = { ...filters, search: "", reason: "", date: "", page: 1 };
    pagination.initialize();

    await loadAdjustments();

    initializeAdjustmentEvents();
    document.getElementById("adjustment-new-btn")?.addEventListener("click", openNewAdjustment);
    initializeExportMenu();

}

const ADJUSTMENT_REASONS = ["Stock count", "Damaged", "Expired", "Theft or loss", "Found stock", "Correction", "Other"];

async function openNewAdjustment() {
    let products = [];
    let warehouses = [];
    try {
        [products, warehouses] = await Promise.all([
            apiList("/api/products/?page_size=200"),
            apiList("/api/inventory/warehouses/?page_size=200"),
        ]).then(([p, w]) => [p.results, w.results]);
    } catch (error) {
        return toast(errorMessage(error, "Could not load products."), "error");
    }
    if (!products.length) return toast("Add a product before recording an adjustment.", "error");
    const productOptions = [{ value: "", label: "Select product" }, ...products.map((p) => ({ value: p.id, label: p.name + (p.sku ? " · " + p.sku : "") }))];
    const warehouseOptions = [{ value: "", label: "Default warehouse" }, ...warehouses.map((w) => ({ value: w.id, label: w.name + " (" + w.code + ")" }))];
    await openModal({
        title: "New stock adjustment",
        size: "max-w-2xl",
        submitLabel: "Post adjustment",
        html: fieldGrid([
            field({ name: "product", label: "Product", type: "select", options: productOptions, required: true, full: true }),
            field({ name: "warehouse", label: "Warehouse", type: "select", options: warehouseOptions }),
            field({ name: "mode", label: "Change type", type: "select", value: "set", options: [
                { value: "set", label: "Set new quantity" },
                { value: "delta", label: "Add or remove units" },
            ] }),
            field({ name: "quantity", label: "Quantity", type: "number", step: "0.001", required: true, help: "For a new quantity enter zero or more. For a change, use a negative number to remove units." }),
            field({ name: "reason", label: "Reason", type: "select", options: ADJUSTMENT_REASONS.map((r) => ({ value: r, label: r })) , required: true }),
            field({ name: "note", label: "Note", type: "textarea", full: true }),
        ]),
        onSubmit: async (form) => {
            const d = readForm(form);
            const product = toNumber(requireValue(d.product, "Choose a product."), "Product", { min: 1 });
            const quantity = toNumber(requireValue(d.quantity, "Enter a quantity."), "Quantity");
            const payload = { product, reason: requireValue(d.reason, "Choose a reason."), note: d.note || "" };
            if (d.warehouse) payload.warehouse = Number(d.warehouse);
            if (d.mode === "set") {
                if (quantity < 0) throw new Error("The new quantity cannot be negative.");
                payload.new_quantity = quantity;
            } else {
                if (quantity === 0) throw new Error("A change must be non-zero.");
                payload.adjustment_quantity = quantity;
            }
            const created = await createAdjustment(payload);
            toast(created && created.adjustment_number ? "Adjustment " + created.adjustment_number + " posted." : "Adjustment posted.", "success");
            await loadAdjustments();
            return true;
        },
    });
}

async function loadAdjustments() {

    let response;
    try {
        response = await getAdjustments(filters);
    } catch (error) {
        const table = document.getElementById("adjustment-table");
        if (table) table.innerHTML = loadErrorHtml(error, "stock adjustments");
        return;
    }


    renderAdjustmentTable(response.results);

    pagination.updateFromResponse(response);

    updateAdjustmentCards(response);

    createIcons({ icons });

}


function initializeAdjustmentEvents() {

    const search = document.getElementById("adjustment-search");

    if (search) {

        search.addEventListener("input", debounce(async (e) => {

            filters.search = e.target.value;

            filters.page = 1;

            pagination.reset();

            await loadAdjustments();

        }, 400));

    }

    const reasonFilter = document.getElementById("adjustment-reason-filter");

    if (reasonFilter) {

        reasonFilter.addEventListener("change", async (e) => {

            filters.reason = e.target.value;

            filters.page = 1;

            pagination.reset();

            await loadAdjustments();

        });

    }

    const dateFilter = document.getElementById("adjustment-date-filter");

    if (dateFilter) {

        dateFilter.addEventListener("change", async (e) => {

            filters.date = e.target.value;

            filters.page = 1;

            pagination.reset();

            await loadAdjustments();

        });

    }

}

window.refreshAdjustments = async function () {

    filters = {

        search: "",

        reason: "",

        date: "",

        start_date: "",

        end_date: "",

        page: 1,

        page_size: 20,

        ordering: "-created_at",

    };

    for (const id of ["adjustment-search", "adjustment-reason-filter", "adjustment-date-filter"]) {
        const control = document.getElementById(id);
        if (control) control.value = "";
    }

    pagination.reset();

    await loadAdjustments();

};


function debounce(callback, delay = 300) {

    let timer;

    return (...args) => {

        clearTimeout(timer);

        timer = setTimeout(() => {

            callback(...args);

        }, delay);

    };

}


function renderAdjustmentTable(rows) {

document.getElementById("adjustment-table").innerHTML = `

<div class="overflow-hidden rounded-2xl border border-slate-200 bg-white">

<table class="w-full">

<thead class="bg-slate-50 border-b border-slate-200">

<tr>

<th class="px-6 py-4 text-left">

<div class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-600">

<i data-lucide="hash" class="w-4 h-4 text-slate-400"></i>

<span>Adjustment #</span>

</div>

</th>

<th class="px-4 py-4 text-center">

<div class="flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-600">

<i data-lucide="layers" class="w-4 h-4 text-slate-400"></i>

<span>Items</span>

</div>

</th>

<th class="px-4 py-4 text-center">

<div class="flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-600">

<i data-lucide="activity" class="w-4 h-4 text-slate-400"></i>

Net Change

</div>

</th>

<th class="px-4 py-4 text-left">

<div class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-600">

<i data-lucide="file-text" class="w-4 h-4 text-slate-400"></i>

Note

</div>

</th>

<th class="px-6 py-4 text-left">

<div class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-600">

<i data-lucide="calendar-days" class="w-4 h-4 text-slate-400"></i>

Date

</div>

</th>

<th class="w-12"></th>

</tr>

</thead>

<tbody>

${rows.map(row => `

<tr

data-adjustment-number="${escapeHtml(row.adjustment_number)}"

onclick="viewAdjustmentDetail(this.dataset.adjustmentNumber)"

class="group border-b border-slate-100 hover:bg-violet-50/40 transition-all cursor-pointer">

<td class="px-6 py-5">

<span class="font-semibold text-slate-800">
    ${escapeHtml(row.adjustment_number)}
</span>

</td>

<td class="px-4 py-5 text-center">

<span class="inline-flex px-3 py-1 rounded-lg bg-slate-100 text-slate-700 text-sm font-semibold">

${escapeHtml(row.items_count ?? (row.items ? row.items.length : "-"))}

</span>

</td>

<td class="px-4 py-5 text-center">

${netChangeBadge(row)}

</td>

<td class="px-4 py-5">

<span class="text-slate-600 text-sm line-clamp-2 max-w-xs">

${escapeHtml(row.note || "-")}

</span>

</td>

<td class="px-6 py-5">

<div class="flex items-center gap-2 text-slate-600">

<i data-lucide="clock-3"

class="w-4 h-4 text-slate-400">

</i>

${escapeHtml(new Date(row.created_at).toLocaleString())}

</div>

</td>

<td>

<i

data-lucide="chevron-right"

class="w-5 h-5 text-slate-300 group-hover:text-violet-500 transition">

</i>

</td>

</tr>

`).join("")}

</tbody>

</table>

</div>

`;

createIcons({ icons });

}


function netChangeBadge(row) {

    const net = row.net_change ?? 0;

    if (net > 0) {

        return `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">+${escapeHtml(net)}</span>`;

    }

    if (net < 0) {

        return `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700">${escapeHtml(net)}</span>`;

    }

    return `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">0</span>`;

}


function updateAdjustmentCards(response) {

    animateCounter("total-adjustments", response.count ?? 0);

    const results = response.results ?? [];

    const totalItems = results.reduce((sum, r) => {
        return sum + (r.items_count ?? (r.items ? r.items.length : 0));
    }, 0);

    animateCounter("items-adjusted", totalItems);

    const increased = results.filter(r => (r.net_change ?? 0) > 0).length;
    const decreased = results.filter(r => (r.net_change ?? 0) < 0).length;

    animateCounter("stock-increased", increased);
    animateCounter("stock-decreased", decreased);

}


function animateCounter(id, endValue, duration = 800) {

    const element = document.getElementById(id);

    if (!element) return;

    const startValue = parseInt(element.textContent.replace(/,/g, "")) || 0;

    const startTime = performance.now();

    function update(currentTime) {

        const progress = Math.min(
            (currentTime - startTime) / duration,
            1
        );

        const value = Math.floor(
            startValue + (endValue - startValue) * progress
        );

        element.textContent = value.toLocaleString();

        if (progress < 1) {
            requestAnimationFrame(update);
        }

    }

    requestAnimationFrame(update);

}


window.viewAdjustmentDetail = async function (adjustmentNumber) {

    const adjustment = await getAdjustment(adjustmentNumber);

    document.getElementById("adjustment-detail-body").innerHTML =
        AdjustmentDetailModal(adjustment);

    createIcons({ icons });

    openAdjustmentDetailModal();

};

window.openAdjustmentDetailModal = function () {

    const modal = document.getElementById("adjustment-detail-modal");

    modal.classList.remove("hidden");
    modal.classList.add("flex");

};

window.closeAdjustmentDetailModal = function () {

    const modal = document.getElementById("adjustment-detail-modal");

    modal.classList.add("hidden");
    modal.classList.remove("flex");

};


// ============================================================================
// EXPORT FUNCTIONS
// ============================================================================
// The menu used inline onclick handlers for functions that were never bound
// to window, so the button threw a ReferenceError and nothing opened.
function setExportMenu(open) {
    const menu = document.getElementById("adjustment-export-menu");
    const button = document.getElementById("adjustment-export-btn");
    if (!menu) return;
    menu.classList.toggle("hidden", !open);
    button?.setAttribute("aria-expanded", String(open));
}

function initializeExportMenu() {
    const button = document.getElementById("adjustment-export-btn");
    const container = document.getElementById("adjustment-export-menu-container");
    if (!button || !container) return;
    button.addEventListener("click", (event) => {
        event.stopPropagation();
        setExportMenu(document.getElementById("adjustment-export-menu")?.classList.contains("hidden"));
    });
    document.getElementById("adjustment-export-csv")?.addEventListener("click", async (event) => {
        setExportMenu(false);
        await exportAdjustmentCSV(button);
        event.preventDefault();
    });
    // Close on outside click / Escape. Registered once per page render; the
    // handlers drop out when the page (and its container) is replaced.
    const onDocumentClick = (event) => {
        if (!document.body.contains(container)) return document.removeEventListener("click", onDocumentClick);
        if (!container.contains(event.target)) setExportMenu(false);
    };
    const onKey = (event) => {
        if (!document.body.contains(container)) return document.removeEventListener("keydown", onKey);
        if (event.key === "Escape") setExportMenu(false);
    };
    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onKey);
}

const EXPORT_MAX_ROWS = 5000;

async function exportAdjustmentCSV(button) {
    if (button?.disabled) return;
    // Not setBusy(): it replaces textContent and would drop the button icons.
    if (button) {
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
    }
    try {
        const { rows, count, truncated } = await collectAllPages(
            // Same filters as the table (search, reason, period), all pages.
            (page, pageSize) => getAdjustments({ ...filters, page, page_size: pageSize }),
            { pageSize: 100, maxRows: EXPORT_MAX_ROWS },
        );
        if (!rows.length) {
            toast("There are no adjustments to export.", "info");
            return;
        }
        downloadCsv("stock-adjustments.csv", [
            { label: "Adjustment", value: (r) => r.adjustment.adjustment_number },
            { label: "Date", value: (r) => r.adjustment.created_at },
            { label: "Type", value: (r) => r.adjustment.adjustment_type },
            { label: "Reason", value: (r) => r.adjustment.reason },
            { label: "Product", value: (r) => r.item?.product_name ?? "" },
            { label: "Before", value: (r) => r.item?.quantity_before ?? "" },
            { label: "After", value: (r) => r.item?.quantity_after ?? "" },
            { label: "Change", value: (r) => r.item?.change ?? "" },
            { label: "Note", value: (r) => r.adjustment.note },
        ], adjustmentCsvRows(rows));
        toast(truncated
            ? `Exported the newest ${rows.length} of ${count} adjustments (export limit ${EXPORT_MAX_ROWS}).`
            : `Exported ${rows.length} adjustment${rows.length === 1 ? "" : "s"}.`, truncated ? "info" : "success");
    } catch (error) {
        toast(errorMessage(error, "The adjustments could not be exported."), "error");
    } finally {
        if (button) {
            button.disabled = false;
            button.removeAttribute("aria-busy");
        }
    }
}
// Excel/PDF bindings removed: those functions were never implemented and the
// ReferenceError at import time aborted main.js (blank application).