import { Sidebar } from "../components/Sidebar";

export function VariantsPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-8">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Variants</h1>
                <p class="text-gray-500 mt-1">Manage product variants (e.g. Size, Color)</p>
            </div>
            <button onclick="window.openCreateVariantModal()" class="h-11 px-5 rounded-xl bg-orange-600 text-white font-semibold hover:bg-orange-700 transition shadow-lg shadow-orange-600/20 flex items-center gap-2">
                <i data-lucide="plus" class="w-4 h-4"></i> Add Variant
            </button>
        </div>

        <div class="grid grid-cols-2 gap-6 mb-8">
            <div class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-orange-50 to-white border border-white/70 shadow-lg p-6">
                <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-orange-500 opacity-20 blur-3xl"></div>
                <i data-lucide="sliders" class="absolute right-5 top-5 h-20 w-20 opacity-10 text-orange-600"></i>
                <div class="relative">
                    <p class="text-sm font-semibold text-slate-500">Total Variants</p>
                    <h2 id="total-variants" class="mt-3 text-4xl font-black tracking-tight text-slate-900">0</h2>
                </div>
            </div>
        </div>

        <div class="premium-surface rounded-3xl p-6 bg-white shadow-sm border border-slate-100">
            <div class="flex items-center justify-between gap-4 mb-6">
                <div class="relative">
                    <i data-lucide="search" class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"></i>
                    <input id="variant-search" type="text" placeholder="Search variants..." class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl border-slate-200 focus:ring-orange-500">
                </div>
                <button onclick="window.refreshVariants()" class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition flex items-center justify-center text-slate-600">
                    <i data-lucide="refresh-cw" class="w-5 h-5 mx-auto"></i>
                </button>
            </div>
            <div id="variants-table"></div>
        </div>

        <!-- Form Modal -->
        <div id="variant-form-modal" class="hidden fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 items-center justify-center p-4">
            <div class="bg-white rounded-3xl w-full max-w-lg shadow-2xl overflow-hidden relative">
                <div class="flex items-center justify-between px-8 py-6 border-b border-slate-100">
                    <h2 id="form-modal-title" class="text-2xl font-bold text-slate-800">Add Variant</h2>
                    <button onclick="window.closeVariantModal()" class="w-10 h-10 flex items-center justify-center rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <form id="variant-form" class="p-8">
                    <input type="hidden" id="variant-id" />
                    <div class="space-y-6">
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Variant Name *</label>
                            <input id="variant-name" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-orange-500" placeholder="e.g. Size, Color">
                        </div>
                        
                        <div id="variant-values-container" class="hidden">
                            <label class="block text-sm font-medium text-slate-700 mb-2">Variant Values</label>
                            <div class="flex gap-2 mb-3">
                                <input id="new-variant-value" type="text" class="premium-input flex-1 h-11 px-4 rounded-xl border-slate-200 focus:ring-orange-500" placeholder="New value (e.g. XL)">
                                <button type="button" onclick="window.addVariantValueHandler()" class="h-11 px-4 rounded-xl bg-slate-100 text-slate-700 font-medium hover:bg-slate-200 transition">Add</button>
                            </div>
                            <div id="variant-values-list" class="flex flex-wrap gap-2">
                                <!-- Value chips go here -->
                            </div>
                        </div>
                    </div>
                    <div class="flex justify-end gap-3 pt-8 mt-6 border-t border-slate-100">
                        <button type="button" onclick="window.closeVariantModal()" class="h-11 px-6 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition">Cancel</button>
                        <button type="submit" class="h-11 px-8 rounded-xl bg-orange-600 text-white text-sm font-semibold hover:bg-orange-700 transition shadow-lg shadow-orange-600/20">Save Variant</button>
                    </div>
                </form>
            </div>
        </div>
    </main>
</div>
    `;
}