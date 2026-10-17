import { formatCurrency } from "../shared/currency.js";
import { escapeHtml, loadErrorHtml, formatMoney } from "../shared/format.js";
import { apiDownload } from "../services/api.js";
import { createIcons, icons } from "lucide";
import { getStockReport } from "../js/inventory/services/inventory-api";
import { Pagination } from "../shared/Pagination";

let stockFilters = { search: "", category: "", status: "", page: 1, page_size: 20 };

const pagination = new Pagination({
    prevButtonId: "prev-page",
    nextButtonId: "next-page",
    containerId: "pagination-numbers",
    pageSize: stockFilters.page_size,
    onPageChange: async (page) => { 
        stockFilters.page = page; 
        await loadStockReport(); 
    }
});

window.initializeStockReport = async function() {
    pagination.initialize();
    initializeStockEvents();
    await loadStockReport();
}

async function loadStockReport() {
    try {
        const response = await getStockReport(stockFilters);
        if (response.summary) {
            renderStockSummary(response.summary);
        }
        
        renderStockTable(response.results || response.products || []);
        pagination.updateFromResponse(response);
        createIcons({ icons });
    } catch (e) {
        console.error("Failed to load stock report", e);
        const errorTarget = document.getElementById("stock-table"); if (errorTarget) errorTarget.innerHTML = loadErrorHtml(e, "the stock report");
    }
}

function initializeStockEvents() {
    const search = document.getElementById("stock-search");
    const category = document.getElementById("stock-category");
    const status = document.getElementById("stock-status");
    
    if (search) {
        search.addEventListener("input", debounce(async (e) => {
            stockFilters.search = e.target.value; 
            stockFilters.page = 1; 
            pagination.reset(); 
            await loadStockReport();
        }, 400));
    }
    if (category) {
        category.addEventListener("change", (e) => {
            stockFilters.category = e.target.value;
            stockFilters.page = 1;
            pagination.reset();
            loadStockReport();
        });
    }
    if (status) {
        status.addEventListener("change", (e) => {
            stockFilters.status = e.target.value;
            stockFilters.page = 1;
            pagination.reset();
            loadStockReport();
        });
    }
}

window.refreshStockReport = async function() {
    stockFilters = { search: "", category: "", status: "", page: 1, page_size: 20 };
    
    const search = document.getElementById("stock-search");
    const category = document.getElementById("stock-category");
    const status = document.getElementById("stock-status");
    
    if(search) search.value = "";
    if(category) category.value = "";
    if(status) status.value = "";
    
    pagination.reset();
    await loadStockReport();
};

window.exportStockReport = function(format) {
    const qs = new URLSearchParams(stockFilters).toString();
    apiDownload(`/api/reports/stock/export/${format}/?${qs}`, `stock-report.${format === 'excel' ? 'xlsx' : format}`);
};

function renderStockSummary(summary) {
    document.getElementById("summary-total-products").textContent = summary.total_products || 0;
    document.getElementById("summary-low-stock").textContent = summary.low_stock || 0;
    document.getElementById("summary-out-of-stock").textContent = summary.out_of_stock || 0;
    document.getElementById("summary-inventory-value").textContent = `${formatCurrency(summary.inventory_value || 0)}`;
}

function renderStockTable(products) {
    if (!products || products.length === 0) {
        document.getElementById("stock-table").innerHTML = `<div class="text-center py-10 text-slate-500">No stock records found.</div>`;
        return;
    }

    const rows = products.map(p => {
        let statusBadge = '';
        if (p.stock_qty <= 0) {
            statusBadge = `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700">Out of Stock</span>`;
        } else if (p.stock_qty <= (p.min_stock || 5)) {
            statusBadge = `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">Low Stock</span>`;
        } else {
            statusBadge = `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">In Stock</span>`;
        }

        return `
        <tr class="group border-b border-slate-100 hover:bg-amber-50/40 transition-all cursor-pointer">
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-slate-900">${escapeHtml(p.product_name || p.name)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">${escapeHtml(p.sku || '-')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">${escapeHtml(p.category || 'General')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">${escapeHtml(p.brand || '-')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-bold text-slate-900">${escapeHtml(p.stock_qty || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">${escapeHtml(p.min_stock || 0)} / ${escapeHtml(p.max_stock || '-')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">${formatCurrency(p.cost_price || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">${formatCurrency(p.sales_price || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-bold text-slate-900">${formatCurrency(p.inventory_value || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap">${statusBadge}</td>
        </tr>
    `}).join("");

    document.getElementById("stock-table").innerHTML = `
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <table class="min-w-full divide-y divide-slate-200">
                <thead class="bg-slate-50">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Product</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">SKU</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Category</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Brand</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Stock Qty</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Min/Max</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Cost Price</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Sales Price</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Inv. Value</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-slate-200">
                    ${rows}
                </tbody>
            </table>
        </div>
    `;
}

function debounce(callback, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); };
}
