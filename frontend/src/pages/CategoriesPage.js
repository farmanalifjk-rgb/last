import { Sidebar } from "../components/Sidebar";

export function CategoriesPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-8">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Categories</h1>
                <p class="text-gray-500 mt-1">Organize your products into categories</p>
            </div>
            <button onclick="window.openCreateCategoryModal()" class="h-11 px-5 rounded-xl bg-emerald-600 text-white font-semibold hover:bg-emerald-700 transition shadow-lg shadow-emerald-600/20 flex items-center gap-2">
                <i data-lucide="plus" class="w-4 h-4"></i> Add Category
            </button>
        </div>

        <div class="grid grid-cols-2 gap-6 mb-8">
            <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-50 to-white border border-white/70 shadow-lg p-6">
                <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-emerald-500 opacity-20 blur-3xl"></div>
                <i data-lucide="layers" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-emerald-600"></i>
                <div class="relative">
                    <p class="text-sm font-semibold text-slate-500">Total Categories</p>
                    <h2 id="total-categories" class="mt-3 text-4xl font-black tracking-tight text-slate-900">0</h2>
                </div>
            </div>
        </div>

        <div class="premium-surface rounded-3xl p-6 bg-white shadow-sm border border-slate-100">
            <div class="flex items-center justify-between gap-4 mb-6">
                <div class="relative">
                    <i data-lucide="search" class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"></i>
                    <input id="category-search" type="text" placeholder="Search categories..." class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl border-slate-200 focus:ring-emerald-500">
                </div>
                <button onclick="window.refreshCategories()" class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition flex items-center justify-center text-slate-600">
                    <i data-lucide="refresh-cw" class="w-5 h-5 mx-auto"></i>
                </button>
            </div>
            <div id="categories-table"></div>
        </div>

        <div class="flex items-center justify-between px-6 py-4 border-t mt-4 bg-white rounded-2xl shadow-sm border border-slate-100">
            <p id="pagination-info" class="text-sm text-gray-500"></p>
            <div class="flex items-center gap-2">
                <button id="prev-page" class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed transition" disabled>
                    <i data-lucide="chevron-left" class="w-4 h-4"></i>
                </button>
                <div id="pagination-numbers" class="text-sm text-gray-600 font-medium">
                    <span class="px-3 py-1 bg-gray-50 rounded-lg border border-gray-200">Page 1 of 1</span>
                </div>
                <button id="next-page" class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed transition" disabled>
                    <i data-lucide="chevron-right" class="w-4 h-4"></i>
                </button>
            </div>
        </div>

        <!-- Form Modal -->
        <div id="category-form-modal" class="hidden fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 items-center justify-center p-4">
            <div class="bg-white rounded-3xl w-full max-w-lg shadow-2xl overflow-hidden relative">
                <div class="flex items-center justify-between px-8 py-6 border-b border-slate-100">
                    <h2 id="form-modal-title" class="text-2xl font-bold text-slate-800">Add Category</h2>
                    <button onclick="window.closeCategoryModal()" class="w-10 h-10 flex items-center justify-center rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <form id="category-form" class="p-8">
                    <input type="hidden" id="category-id" />
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Category Name *</label>
                            <input id="category-name" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-emerald-500" placeholder="e.g. Electronics">
                        </div>
                    </div>
                    <div class="flex justify-end gap-3 pt-8 mt-4 border-t border-slate-100">
                        <button type="button" onclick="window.closeCategoryModal()" class="h-11 px-6 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition">Cancel</button>
                        <button type="submit" class="h-11 px-8 rounded-xl bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 transition shadow-lg shadow-emerald-600/20">Save Category</button>
                    </div>
                </form>
            </div>
        </div>
    </main>
</div>
    `;
}