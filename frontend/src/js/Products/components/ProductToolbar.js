export function ProductToolbar() {
    return `<div class="flex items-center justify-between gap-4 mb-6">
        <div class="flex items-center gap-3">
            <div class="relative">
                <i data-lucide="search" class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"></i>
                <input id="product-search" type="text" placeholder="Search products..." class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl border-slate-200 focus:ring-sky-500">
            </div>
            <button onclick="refreshProducts()" class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition flex items-center justify-center text-slate-600">
                <i data-lucide="refresh-cw" class="w-5 h-5 mx-auto"></i>
            </button>
        </div>
        <div class="flex items-center gap-3">
            <select id="product-category-filter" class="premium-input h-11 px-4 rounded-xl border-slate-200 text-sm font-medium text-slate-600 outline-none focus:ring-2 focus:ring-sky-500">
                <option value="">All Categories</option>
            </select>
            <select id="product-brand-filter" class="premium-input h-11 px-4 rounded-xl border-slate-200 text-sm font-medium text-slate-600 outline-none focus:ring-2 focus:ring-sky-500">
                <option value="">All Brands</option>
            </select>
            <select id="product-status-filter" class="premium-input h-11 px-4 rounded-xl border-slate-200 text-sm font-medium text-slate-600 outline-none focus:ring-2 focus:ring-sky-500">
                <option value="">All Statuses</option>
                <option value="true">Active</option>
                <option value="false">Inactive</option>
            </select>
        </div>
    </div>`;
}