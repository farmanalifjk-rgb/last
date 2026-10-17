import { formatCurrency } from "../shared/currency.js";
import { escapeHtml, loadErrorHtml, formatMoney } from "../shared/format.js";
import { apiDownload } from "../services/api.js";
import { createIcons, icons } from "lucide";
import { getSalesReport } from "../js/inventory/services/inventory-api";

let salesFilters = { start_date: "", end_date: "", payment: "", date: "" };

window.initializeSalesReport = async function() {
    initializeSalesEvents();
    await loadSalesReport();
}

async function loadSalesReport() {
    try {
        const response = await getSalesReport(salesFilters);
        renderSalesSummary(response?.summary || {});
        renderSalesChart(response?.chart_data || []);
        renderSalesTable(response?.orders || []);
        createIcons({ icons });
    } catch (e) {
        console.error("Failed to load sales report", e);
        const errorTarget = document.getElementById("sales-table"); if (errorTarget) errorTarget.innerHTML = loadErrorHtml(e, "the sales report");
    }
}

function initializeSalesEvents() {
    const start = document.getElementById("sales-start-date");
    const end = document.getElementById("sales-end-date");
    const payment = document.getElementById("sales-payment-method");
    
    if (start) {
        start.addEventListener("change", (e) => {
            salesFilters.start_date = e.target.value;
            salesFilters.date = ""; // clear quick filter
            loadSalesReport();
        });
    }
    if (end) {
        end.addEventListener("change", (e) => {
            salesFilters.end_date = e.target.value;
            salesFilters.date = ""; 
            loadSalesReport();
        });
    }
    if (payment) {
        payment.addEventListener("change", (e) => {
            salesFilters.payment = e.target.value;
            loadSalesReport();
        });
    }
}

window.applySalesDateRange = function(rangeType) {
    salesFilters.date = rangeType;
    salesFilters.start_date = "";
    salesFilters.end_date = "";
    
    const start = document.getElementById("sales-start-date");
    const end = document.getElementById("sales-end-date");
    if(start) start.value = "";
    if(end) end.value = "";
    
    loadSalesReport();
};

window.refreshSalesReport = async function() {
    salesFilters = { start_date: "", end_date: "", payment: "", date: "" };
    
    const start = document.getElementById("sales-start-date");
    const end = document.getElementById("sales-end-date");
    const payment = document.getElementById("sales-payment-method");
    
    if(start) start.value = "";
    if(end) end.value = "";
    if(payment) payment.value = "";
    
    await loadSalesReport();
};

window.exportSalesReport = function(format) {
    const qs = new URLSearchParams(salesFilters).toString();
    apiDownload(`/api/reports/sales/export/${format}/?${qs}`, `sales-report.${format === 'excel' ? 'xlsx' : format}`);
};

function renderSalesSummary(summary) {
    document.getElementById("summary-total-sales").textContent = summary.total_orders || 0;
    document.getElementById("summary-total-revenue").textContent = `${formatCurrency(summary.total_revenue || 0)}`;
    document.getElementById("summary-avg-order").textContent = `${formatCurrency(summary.avg_order_value || 0)}`;
    document.getElementById("summary-total-refunds").textContent = `${formatCurrency(summary.total_refunds || 0)}`;
}

function renderSalesChart(data) {
    const chartContainer = document.getElementById("sales-chart");
    if (!chartContainer) return;
    
    if (!data || data.length === 0) {
        chartContainer.innerHTML = `<div class="w-full h-full flex items-center justify-center text-slate-400">No chart data available</div>`;
        return;
    }
    
    const maxVal = Math.max(...data.map(d => parseFloat(d.revenue) || 0));
    
    const barsHTML = data.map(d => {
        const heightPct = maxVal > 0 ? ((parseFloat(d.revenue) || 0) / maxVal) * 100 : 0;
        return `
            <div class="flex-1 flex flex-col items-center justify-end h-full group relative">
                <div class="absolute bottom-full mb-2 bg-slate-800 text-white text-xs py-1 px-2 rounded opacity-0 group-hover:opacity-100 transition whitespace-nowrap z-10 pointer-events-none">
                    ${escapeHtml(d.date)}: ${formatCurrency(d.revenue)}
                </div>
                <div class="w-full max-w-[40px] bg-blue-500 rounded-t-md transition-all duration-500 hover:bg-blue-600" style="height: ${heightPct}%"></div>
                <div class="text-[10px] text-slate-500 mt-2 truncate w-full text-center">${escapeHtml(String(d.date).split("-").slice(1).join("/"))}</div>
            </div>
        `;
    }).join("");
    
    chartContainer.innerHTML = barsHTML;
}

function renderSalesTable(orders) {
    if (!orders || orders.length === 0) {
        document.getElementById("sales-table").innerHTML = `<div class="text-center py-10 text-slate-500">No sales records found.</div>`;
        return;
    }

    const rows = orders.map(order => `
        <tr class="group border-b border-slate-100 hover:bg-blue-50/40 transition-all cursor-pointer">
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-slate-900">#${escapeHtml(order.order_number || order.id)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">${escapeHtml(order.customer || 'Walk-in')}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">
                <span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
                    ${escapeHtml(order.payment_method || 'Unknown')}
                </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">${formatCurrency(order.subtotal || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">${formatCurrency(order.discount || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">${formatCurrency(order.tax || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-bold text-slate-900">${formatCurrency(order.total || 0)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">${escapeHtml(order.date || order.created_at || '-')}</td>
        </tr>
    `).join("");

    document.getElementById("sales-table").innerHTML = `
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <table class="min-w-full divide-y divide-slate-200">
                <thead class="bg-slate-50">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Order #</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Customer</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Payment</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Subtotal</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Discount</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Tax</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Total</th>
                        <th class="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Date</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-slate-200">
                    ${rows}
                </tbody>
            </table>
        </div>
    `;
}
