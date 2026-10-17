import { Sidebar } from "../components/Sidebar";

function ProductCards() {
    return `<div class="grid grid-cols-4 gap-6 mb-8">
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-50 to-emerald-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-emerald-500 opacity-20 blur-3xl"></div>
            <i data-lucide="package" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-emerald-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Products Sold</p>
                <h2 id="summary-products-sold" class="mt-3 text-4xl font-black tracking-tight text-slate-900">0</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-emerald-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-50 to-emerald-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-emerald-500 opacity-20 blur-3xl"></div>
            <i data-lucide="award" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-emerald-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Top Product</p>
                <h2 id="summary-top-product" class="mt-3 text-2xl font-black tracking-tight text-slate-900 truncate">-</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-emerald-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-50 to-emerald-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-emerald-500 opacity-20 blur-3xl"></div>
            <i data-lucide="dollar-sign" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-emerald-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Total Revenue</p>
                <h2 id="summary-total-revenue" class="mt-3 text-4xl font-black tracking-tight text-slate-900">$0.00</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-emerald-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-50 to-emerald-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-emerald-500 opacity-20 blur-3xl"></div>
            <i data-lucide="rotate-ccw" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-emerald-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Returns</p>
                <h2 id="summary-returns" class="mt-3 text-4xl font-black tracking-tight text-slate-900">0</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-emerald-500"></div></div></div>
            </div>
        </div>
    </div>`;
}

function ProductToolbar() {
    return `<div class="flex items-center justify-between gap-4 mb-6">
        <div class="flex items-center gap-3">
            <div class="flex items-center bg-white border border-slate-200 rounded-xl p-1 shadow-sm">
                <button onclick="applyProductDateRange('today')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-emerald-50 focus:text-emerald-600 transition">Today</button>
                <button onclick="applyProductDateRange('week')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-emerald-50 focus:text-emerald-600 transition">Week</button>
                <button onclick="applyProductDateRange('month')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-emerald-50 focus:text-emerald-600 transition">Month</button>
                <button onclick="applyProductDateRange('year')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-emerald-50 focus:text-emerald-600 transition">Year</button>
            </div>
            <div class="flex items-center gap-2">
                <input id="product-start-date" type="date" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm">
                <span class="text-slate-400">-</span>
                <input id="product-end-date" type="date" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm">
            </div>
            <select id="product-category" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm bg-white">
                <option value="">All Categories</option>
            </select>
            <button onclick="refreshProductReport()" class="w-10 h-10 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition flex items-center justify-center">
                <i data-lucide="refresh-cw" class="w-4 h-4 text-slate-600"></i>
            </button>
        </div>
        <div class="flex gap-2">
            <button onclick="exportProductReport('csv')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="file-text" class="w-4 h-4"></i> CSV
            </button>
            <button onclick="exportProductReport('excel')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="table" class="w-4 h-4"></i> Excel
            </button>
            <button onclick="exportProductReport('pdf')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="file" class="w-4 h-4"></i> PDF
            </button>
        </div>
    </div>`;
}

export function ProductReportPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Product Performance</h1>
                <p class="text-gray-500 mt-1">Track which items are driving your revenue</p>
            </div>
        </div>
        
        ${ProductCards()}
        
        <div class="premium-surface rounded-3xl p-6 bg-white border border-slate-100 shadow-sm">
            ${ProductToolbar()}
            <div id="product-table"></div>
        </div>
    </main>
</div>
    `;
}
