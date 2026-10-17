import { formatCurrency } from "../shared/currency.js";
import { escapeHtml, loadErrorHtml, formatMoney } from "../shared/format.js";
import { apiDownload } from "../services/api.js";
import { createIcons, icons } from "lucide";
import { getProductReport } from "../js/inventory/services/inventory-api";

let productFilters = { start_date: "", end_date: "", category: "", date: "" };

window.initializeProductReport = async function() {
    initializeProductEvents();
    await loadProductReport();
}

async function loadProductReport() {
    try {
        const response = await getProductReport(productFilters);
        renderProductSummary(response?.summary || {});
        renderProductTable(response?.products || []);
        createIcons({ icons });
    } catch (e) {
        console.error("Failed to load product report", e);
        const errorTarget = document.getElementById("product-table"); if (errorTarget) errorTarget.innerHTML = loadErrorHtml(e, "the product report");
    }
}

function initializeProductEvents() {
    const start = document.getElementById("product-start-date");
    const end = document.getElementById("product-end-date");
    const category = document.getElementById("product-category");
    
    if (start) {
        start.addEventListener("change", (e) => {
            productFilters.start_date = e.target.value;
            productFilters.date = "";
            loadProductReport();
        });
    }
    if (end) {
        end.addEventListener("change", (e) => {
            productFilters.end_date = e.target.value;
            productFilters.date = "";
            loadProductReport();
        });
    }
    if (category) {
        category.addEventListener("change", (e) => {
            productFilters.category = e.target.value;
            loadProductReport();
        });
    }
}

window.applyProductDateRange = function(rangeType) {
    productFilters.date = rangeType;
    productFilters.start_date = "";
    productFilters.end_date = "";
    
    const start = document.getElementById("product-start-date");
    const end = document.getElementById("product-end-date");
    if(start) start.value = "";
    if(end) end.value = "";
    
    loadProductReport();
};

window.refreshProductReport = async function() {
    productFilters = { start_date: "", end_date: "", category: "", date: "" };
    
    const start = document.getElementById("product-start-date");
    const end = document.getElementById("product-end-date");
    const category = document.getElementById("product-category");
    
    if(start) start.value = "";
    if(end) end.value = "";
    if(category) category.value = "";
    
    await loadProductReport();
};

window.exportProductReport = function(format) {
    const qs = new URLSearchParams(productFilters).toString();
    apiDownload(`/api/reports/products/export/${format}/?${qs}`, `products-report.${format === 'excel' ? 'xlsx' : format}`);
};

function renderProductSummary(summary) {
    document.getElementById("summary-products-sold").textContent = summary.total_sold || 0;
    document.getElementById("summary-top-product").textContent = summary.top_product || "-";
    document.getElementById("summary-total-revenue").textContent = `${formatCurrency(summary.total_revenue || 0)}`;
    document.getElementById("summary-returns").textContent = summary.total_returns || 0;
}

function renderProductTable(products) {
    if (!products || products.length === 0) {
        document.getElementById("product-table").innerHTML = `<div class="text-center py-10 text-slate-500">No product records found.</div>`;
        return;
    }

    const rows = products.map(p => `
        <tr class="group border-b border-slate-100 hover:bg-emerald-50/40 transition-all cursor-pointer">
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-slate-900">${escapeHtml(p.product_name || p.name)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">${escapeHtml(p.sku || '-')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                <span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
                    ${escapeHtml(p.category || 'General')}
                </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-bold text-slate-900">${escapeHtml(p.qty_sold || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-emerald-600 font-medium">${formatCurrency(p.revenue || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">${formatCurrency(p.avg_price || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">${escapeHtml(p.return_count || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-bold text-slate-900">${formatCurrency(p.profit || 0)}</td>
        </tr>
    `).join("");

    document.getElementById("product-table").innerHTML = `
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <table class="min-w-full divide-y divide-slate-200">
                <thead class="bg-slate-50">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Product Name</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">SKU</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Category</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Qty Sold</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Revenue</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Avg Price</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Returns</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Profit</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-slate-200">
                    ${rows}
                </tbody>
            </table>
        </div>
    `;
}
