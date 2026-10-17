import { Sidebar } from "../components/Sidebar";

function TaxCards() {
    return `<div class="grid grid-cols-4 gap-6 mb-8">
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-violet-50 to-violet-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-violet-500 opacity-20 blur-3xl"></div>
            <i data-lucide="calculator" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-violet-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Total Tax Collected</p>
                <h2 id="summary-total-tax" class="mt-3 text-4xl font-black tracking-tight text-slate-900">$0.00</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-violet-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-violet-50 to-violet-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-violet-500 opacity-20 blur-3xl"></div>
            <i data-lucide="calendar-days" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-violet-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Tax This Month</p>
                <h2 id="summary-month-tax" class="mt-3 text-4xl font-black tracking-tight text-slate-900">$0.00</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-violet-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-violet-50 to-violet-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-violet-500 opacity-20 blur-3xl"></div>
            <i data-lucide="calendar" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-violet-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Tax This Week</p>
                <h2 id="summary-week-tax" class="mt-3 text-4xl font-black tracking-tight text-slate-900">$0.00</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-violet-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-violet-50 to-violet-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-violet-500 opacity-20 blur-3xl"></div>
            <i data-lucide="pie-chart" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-violet-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Avg Tax / Order</p>
                <h2 id="summary-avg-tax" class="mt-3 text-4xl font-black tracking-tight text-slate-900">$0.00</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-violet-500"></div></div></div>
            </div>
        </div>
    </div>`;
}

function TaxToolbar() {
    return `<div class="flex items-center justify-between gap-4 mb-6">
        <div class="flex items-center gap-3">
            <div class="flex items-center bg-white border border-slate-200 rounded-xl p-1 shadow-sm">
                <button onclick="applyTaxDateRange('today')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-violet-50 focus:text-violet-600 transition">Today</button>
                <button onclick="applyTaxDateRange('week')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-violet-50 focus:text-violet-600 transition">Week</button>
                <button onclick="applyTaxDateRange('month')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-violet-50 focus:text-violet-600 transition">Month</button>
                <button onclick="applyTaxDateRange('year')" class="px-4 py-1.5 text-sm font-medium rounded-lg hover:bg-slate-50 text-slate-600 focus:bg-violet-50 focus:text-violet-600 transition">Year</button>
            </div>
            <div class="flex items-center gap-2">
                <input id="tax-start-date" type="date" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm">
                <span class="text-slate-400">-</span>
                <input id="tax-end-date" type="date" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm">
            </div>
            <select id="tax-payment-method" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm bg-white">
                <option value="">All Payments</option>
                <option value="cash">Cash</option>
                <option value="card">Card</option>
                <option value="transfer">Transfer</option>
            </select>
            <button onclick="refreshTaxReport()" class="w-10 h-10 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition flex items-center justify-center">
                <i data-lucide="refresh-cw" class="w-4 h-4 text-slate-600"></i>
            </button>
        </div>
        <div class="flex gap-2">
            <button onclick="exportTaxReport('csv')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="file-text" class="w-4 h-4"></i> CSV
            </button>
            <button onclick="exportTaxReport('excel')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="table" class="w-4 h-4"></i> Excel
            </button>
            <button onclick="exportTaxReport('pdf')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="file" class="w-4 h-4"></i> PDF
            </button>
        </div>
    </div>`;
}

export function TaxReportPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Tax Report</h1>
                <p class="text-gray-500 mt-1">Review collected taxes and compliance obligations</p>
            </div>
        </div>
        
        ${TaxCards()}
        
        <div class="premium-surface rounded-3xl p-6 bg-white border border-slate-100 shadow-sm">
            ${TaxToolbar()}
            <div id="tax-table"></div>
        </div>
    </main>
</div>
    `;
}
