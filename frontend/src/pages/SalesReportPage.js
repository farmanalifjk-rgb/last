import { Sidebar } from "../components/Sidebar";

function SalesCards() {
    return `<div class="grid grid-cols-4 gap-6 mb-8">
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-blue-50 to-blue-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-blue-500 opacity-20 blur-3xl"></div>
            <i data-lucide="shopping-cart" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-blue-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Total Sales</p>
                <h2 id="summary-total-sales" class="mt-3 text-4xl font-black tracking-tight text-slate-900">0</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-blue-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-blue-50 to-blue-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-blue-500 opacity-20 blur-3xl"></div>
            <i data-lucide="dollar-sign" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-blue-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Total Revenue</p>
                <h2 id="summary-total-revenue" class="mt-3 text-4xl font-black tracking-tight text-slate-900">$0.00</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-blue-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-blue-50 to-blue-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-blue-500 opacity-20 blur-3xl"></div>
            <i data-lucide="trending-up" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-blue-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Avg Order Value</p>
                <h2 id="summary-avg-order" class="mt-3 text-4xl font-black tracking-tight text-slate-900">$0.00</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-blue-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-blue-50 to-blue-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-blue-500 opacity-20 blur-3xl"></div>
            <i data-lucide="corner-up-left" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-blue-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Total Refunds</p>
                <h2 id="summary-total-refunds" class="mt-3 text-4xl font-black tracking-tight text-slate-900">$0.00</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-blue-500"></div></div></div>
            </div>
        </div>
    </div>`;
}

function SalesToolbar() {
    return `<div class="flex items-center justify-between gap-4 mb-6">
        <div class="flex items-center gap-3">
            <div class="flex items-center bg-white border border-slate-200 rounded-xl p-1 shadow-sm">
                <button onclick="applySalesDateRange('today')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-blue-50 focus:text-blue-600 transition">Today</button>
                <button onclick="applySalesDateRange('week')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-blue-50 focus:text-blue-600 transition">Week</button>
                <button onclick="applySalesDateRange('month')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-blue-50 focus:text-blue-600 transition">Month</button>
                <button onclick="applySalesDateRange('year')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-blue-50 focus:text-blue-600 transition">Year</button>
            </div>
            <div class="flex items-center gap-2">
                <input id="sales-start-date" type="date" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm">
                <span class="text-slate-400">-</span>
                <input id="sales-end-date" type="date" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm">
            </div>
            <select id="sales-payment-method" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm bg-white">
                <option value="">All Payments</option>
                <option value="cash">Cash</option>
                <option value="card">Card</option>
                <option value="transfer">Transfer</option>
            </select>
            <button onclick="refreshSalesReport()" class="w-10 h-10 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition flex items-center justify-center">
                <i data-lucide="refresh-cw" class="w-4 h-4 text-slate-600"></i>
            </button>
        </div>
        <div class="flex gap-2">
            <button onclick="exportSalesReport('csv')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="file-text" class="w-4 h-4"></i> CSV
            </button>
            <button onclick="exportSalesReport('excel')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="table" class="w-4 h-4"></i> Excel
            </button>
            <button onclick="exportSalesReport('pdf')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="file" class="w-4 h-4"></i> PDF
            </button>
        </div>
    </div>`;
}

export function SalesReportPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Sales Report</h1>
                <p class="text-gray-500 mt-1">Analyze revenue, average order value, and daily trends</p>
            </div>
        </div>
        
        ${SalesCards()}
        
        <div class="premium-surface rounded-3xl p-6 mb-8 bg-white border border-slate-100 shadow-sm">
            <h3 class="text-lg font-bold mb-4 text-slate-800">Revenue Trends</h3>
            <div id="sales-chart" class="w-full h-64 flex items-end gap-2 p-4 border border-slate-100 rounded-2xl bg-slate-50/50">
                <!-- Pure CSS Chart injected here -->
            </div>
        </div>

        <div class="premium-surface rounded-3xl p-6 bg-white border border-slate-100 shadow-sm">
            ${SalesToolbar()}
            <div id="sales-table"></div>
        </div>
    </main>
</div>
    `;
}
