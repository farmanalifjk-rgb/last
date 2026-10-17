import { Sidebar } from "../components/Sidebar";

export function BrandsPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-8">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Brands</h1>
                <p class="text-gray-500 mt-1">Manage your product brands</p>
            </div>
            <button onclick="window.openCreateBrandModal()" class="h-11 px-5 rounded-xl bg-purple-600 text-white font-semibold hover:bg-purple-700 transition shadow-lg shadow-purple-600/20 flex items-center gap-2">
                <i data-lucide="plus" class="w-4 h-4"></i> Add Brand
            </button>
        </div>

        <div class="grid grid-cols-2 gap-6 mb-8">
            <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-purple-50 to-white border border-white/70 shadow-lg p-6">
                <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-purple-500 opacity-20 blur-3xl"></div>
                <i data-lucide="award" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-purple-600"></i>
                <div class="relative">
                    <p class="text-sm font-semibold text-slate-500">Total Brands</p>
                    <h2 id="total-brands" class="mt-3 text-4xl font-black tracking-tight text-slate-900">0</h2>
                </div>
            </div>
        </div>

        <div class="premium-surface rounded-3xl p-6 bg-white shadow-sm border border-slate-100">
            <div class="flex items-center justify-between gap-4 mb-6">
                <div class="relative">
                    <i data-lucide="search" class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"></i>
                    <input id="brand-search" type="text" placeholder="Search brands..." class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl border-slate-200 focus:ring-purple-500">
                </div>
                <button onclick="window.refreshBrands()" class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition flex items-center justify-center text-slate-600">
                    <i data-lucide="refresh-cw" class="w-5 h-5 mx-auto"></i>
                </button>
            </div>
            <div id="brands-table"></div>
        </div>

        <!-- Form Modal -->
        <div id="brand-form-modal" class="hidden fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 items-center justify-center p-4">
            <div class="bg-white rounded-3xl w-full max-w-lg shadow-2xl overflow-hidden relative">
                <div class="flex items-center justify-between px-8 py-6 border-b border-slate-100">
                    <h2 id="form-modal-title" class="text-2xl font-bold text-slate-800">Add Brand</h2>
                    <button onclick="window.closeBrandModal()" class="w-10 h-10 flex items-center justify-center rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <form id="brand-form" class="p-8">
                    <input type="hidden" id="brand-id" />
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Brand Name *</label>
                            <input id="brand-name" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-purple-500" placeholder="e.g. Nike">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Description</label>
                            <textarea id="brand-description" rows="3" class="premium-input w-full p-4 rounded-xl border-slate-200 focus:ring-purple-500 resize-none" placeholder="Brand description..."></textarea>
                        </div>
                        <div class="pt-2">
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="brand-is-active" class="w-5 h-5 rounded border-slate-300 text-purple-600 focus:ring-purple-500" checked>
                                <span class="text-sm font-medium text-slate-700">Active</span>
                            </label>
                        </div>
                    </div>
                    <div class="flex justify-end gap-3 pt-8 mt-4 border-t border-slate-100">
                        <button type="button" onclick="window.closeBrandModal()" class="h-11 px-6 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition">Cancel</button>
                        <button type="submit" class="h-11 px-8 rounded-xl bg-purple-600 text-white text-sm font-semibold hover:bg-purple-700 transition shadow-lg shadow-purple-600/20">Save Brand</button>
                    </div>
                </form>
            </div>
        </div>
    </main>
</div>
    `;
}