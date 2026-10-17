import { Sidebar } from "../components/Sidebar";

function StockCards() {
    return `<div class="grid grid-cols-4 gap-6 mb-8">
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-amber-50 to-amber-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-amber-500 opacity-20 blur-3xl"></div>
            <i data-lucide="layers" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-amber-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Total Products</p>
                <h2 id="summary-total-products" class="mt-3 text-4xl font-black tracking-tight text-slate-900">0</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-amber-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-amber-50 to-amber-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-amber-500 opacity-20 blur-3xl"></div>
            <i data-lucide="alert-triangle" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-amber-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Low Stock Items</p>
                <h2 id="summary-low-stock" class="mt-3 text-4xl font-black tracking-tight text-slate-900">0</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-amber-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-amber-50 to-amber-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-red-500 opacity-20 blur-3xl"></div>
            <i data-lucide="x-circle" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-red-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Out of Stock</p>
                <h2 id="summary-out-of-stock" class="mt-3 text-4xl font-black tracking-tight text-slate-900">0</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-red-500"></div></div></div>
            </div>
        </div>
        <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-amber-50 to-amber-100/50 border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
            <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-amber-500 opacity-20 blur-3xl"></div>
            <i data-lucide="banknote" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-amber-600"></i>
            <div class="relative">
                <p class="text-sm font-semibold text-slate-500">Inventory Value</p>
                <h2 id="summary-inventory-value" class="mt-3 text-4xl font-black tracking-tight text-slate-900">$0.00</h2>
                <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full bg-amber-500"></div></div></div>
            </div>
        </div>
    </div>`;
}

function StockToolbar() {
    return `<div class="flex items-center justify-between gap-4 mb-6">
        <div class="flex items-center gap-3">
            <div class="relative">
                <i data-lucide="search" class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"></i>
                <input id="stock-search" type="text" placeholder="Search products..." class="premium-input pl-11 pr-4 h-10 w-64 rounded-xl border border-slate-200 text-sm">
            </div>
            <select id="stock-category" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm bg-white">
                <option value="">All Categories</option>
            </select>
            <select id="stock-status" class="premium-input h-10 px-3 rounded-xl border border-slate-200 text-sm bg-white">
                <option value="">All Statuses</option>
                <option value="in_stock">In Stock</option>
                <option value="low_stock">Low Stock</option>
                <option value="out_of_stock">Out of Stock</option>
            </select>
            <button onclick="refreshStockReport()" class="w-10 h-10 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition flex items-center justify-center">
                <i data-lucide="refresh-cw" class="w-4 h-4 text-slate-600"></i>
            </button>
        </div>
        <div class="flex gap-2">
            <button onclick="exportStockReport('csv')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="file-text" class="w-4 h-4"></i> CSV
            </button>
            <button onclick="exportStockReport('excel')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="table" class="w-4 h-4"></i> Excel
            </button>
            <button onclick="exportStockReport('pdf')" class="h-10 px-4 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 transition flex items-center gap-2">
                <i data-lucide="file" class="w-4 h-4"></i> PDF
            </button>
        </div>
    </div>`;
}

export function StockReportPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Stock & Inventory</h1>
                <p class="text-gray-500 mt-1">Monitor stock levels, inventory value, and restock alerts</p>
            </div>
        </div>
        
        ${StockCards()}
        
        <div class="premium-surface rounded-3xl p-6 bg-white border border-slate-100 shadow-sm">
            ${StockToolbar()}
            <div id="stock-table"></div>
            
            <div class="flex items-center justify-between px-6 py-4 border-t border-gray-100 mt-4">
                <p id="pagination-info" class="text-sm text-gray-500"></p>
                <div class="flex items-center gap-2">
                    <button id="prev-page" class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent transition" disabled>
                        <i data-lucide="chevron-left" class="w-4 h-4"></i>
                    </button>
                    <div id="pagination-numbers" class="text-sm text-gray-600 font-medium flex items-center gap-1">
                        <span class="px-3 py-1 bg-gray-50 rounded-lg border border-gray-200">1</span>
                    </div>
                    <button id="next-page" class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent transition" disabled>
                        <i data-lucide="chevron-right" class="w-4 h-4"></i>
                    </button>
                </div>
            </div>
        </div>
    </main>
</div>
    `;
}
