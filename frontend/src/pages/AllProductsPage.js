import { currencyLabel } from "../shared/currency.js";
import { Sidebar } from "../components/Sidebar";
import { ProductCards } from "../js/Products/components/ProductCards";
import { ProductToolbar } from "../js/Products/components/ProductToolbar";

export function AllProductsPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold">All Products</h1>
                <p class="text-gray-500 mt-1">Manage your inventory and catalog</p>
            </div>
            <div class="flex items-center gap-3">
                <button onclick="window.exportProducts('csv')" class="h-11 px-5 rounded-xl border border-slate-200 bg-white text-slate-700 font-medium hover:bg-slate-50 transition flex items-center gap-2">
                    <i data-lucide="download" class="w-4 h-4"></i> Export CSV
                </button>
                <button onclick="openCreateProductModal()" class="h-11 px-5 rounded-xl bg-sky-600 text-white font-semibold hover:bg-sky-700 transition shadow-lg shadow-sky-600/20 flex items-center gap-2">
                    <i data-lucide="plus" class="w-4 h-4"></i> Add Product
                </button>
            </div>
        </div>

        ${ProductCards()}

        <div class="premium-surface rounded-3xl p-6 bg-white shadow-sm border border-slate-100">
            ${ProductToolbar()}
            <div id="products-table"></div>
        </div>

        <div class="flex items-center justify-between px-6 py-4 border-t mt-4 bg-white rounded-2xl shadow-sm border border-slate-100">
            <p id="pagination-info" class="text-sm text-gray-500"></p>
            <div class="flex items-center gap-2">
                <button id="prev-page" class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent transition" disabled>
                    <i data-lucide="chevron-left" class="w-4 h-4"></i>
                </button>
                <div id="pagination-numbers" class="text-sm text-gray-600 font-medium">
                    <span class="px-3 py-1 bg-gray-50 rounded-lg border border-gray-200">Page 1 of 1</span>
                </div>
                <button id="next-page" class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent transition" disabled>
                    <i data-lucide="chevron-right" class="w-4 h-4"></i>
                </button>
            </div>
        </div>

        <!-- Product Form Modal -->
        <div id="product-form-modal" class="hidden fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 items-center justify-center p-4 sm:p-8 overflow-y-auto">
            <div class="bg-white rounded-3xl w-full max-w-4xl shadow-2xl overflow-hidden my-8 relative">
                <div class="flex items-center justify-between px-8 py-6 border-b border-slate-100 sticky top-0 bg-white/80 backdrop-blur z-10">
                    <h2 id="form-modal-title" class="text-2xl font-bold text-slate-800">Add Product</h2>
                    <button onclick="closeProductModal()" class="w-10 h-10 flex items-center justify-center rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <form id="product-form" class="p-8">
                    <input type="hidden" id="product-id" />
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                        <!-- Basic Info -->
                        <div class="space-y-4">
                            <h3 class="text-lg font-semibold text-slate-800 border-b pb-2">Basic Info</h3>
                            <div>
                                <label class="block text-sm font-medium text-slate-700 mb-1">Product Name *</label>
                                <input id="product-name" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-sky-500" placeholder="e.g. Premium T-Shirt">
                            </div>
                            <div class="grid grid-cols-2 gap-4">
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">SKU *</label>
                                    <input id="product-sku" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-sky-500" placeholder="SKU-123">
                                </div>
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">Barcode</label>
                                    <input id="product-barcode" type="text" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-sky-500" placeholder="890123456789">
                                </div>
                            </div>
                            <div class="grid grid-cols-2 gap-4">
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">Category</label>
                                    <select id="product-category" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-sky-500"></select>
                                </div>
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">Brand</label>
                                    <select id="product-brand" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-sky-500"></select>
                                </div>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-slate-700 mb-1">Description</label>
                                <textarea id="product-description" rows="3" class="premium-input w-full p-4 rounded-xl border-slate-200 focus:ring-sky-500 resize-none" placeholder="Product description..."></textarea>
                            </div>
                        </div>

                        <!-- Pricing & Stock -->
                        <div class="space-y-4">
                            <h3 class="text-lg font-semibold text-slate-800 border-b pb-2">Pricing & Inventory</h3>
                            <div class="grid grid-cols-2 gap-4">
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">Cost Price *</label>
                                    <div class="relative">
                                        <span class="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" data-currency-label>${currencyLabel()}</span>
                                        <input id="product-cost-price" type="number" step="0.01" required class="premium-input w-full h-11 pl-11 pr-4 rounded-xl border-slate-200 focus:ring-sky-500" placeholder="0.00">
                                    </div>
                                </div>
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">Sales Price *</label>
                                    <div class="relative">
                                        <span class="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" data-currency-label>${currencyLabel()}</span>
                                        <input id="product-sales-price" type="number" step="0.01" required class="premium-input w-full h-11 pl-11 pr-4 rounded-xl border-slate-200 focus:ring-sky-500" placeholder="0.00">
                                    </div>
                                </div>
                            </div>
                            <div class="grid grid-cols-3 gap-4">
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">Stock Qty</label>
                                    <input id="product-stock" type="number" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-sky-500" placeholder="0">
                                </div>
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">Min Stock</label>
                                    <input id="product-min-stock" type="number" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-sky-500" placeholder="5">
                                </div>
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">Max Stock</label>
                                    <input id="product-max-stock" type="number" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-sky-500" placeholder="100">
                                </div>
                            </div>
                            <div class="grid grid-cols-2 gap-4 items-center mt-2">
                                <div>
                                    <label class="block text-sm font-medium text-slate-700 mb-1">Unit</label>
                                    <input id="product-unit" type="text" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 focus:ring-sky-500" placeholder="pcs, kg, box">
                                </div>
                                <div class="pt-6">
                                    <label class="flex items-center gap-2 cursor-pointer">
                                        <input type="checkbox" id="product-is-active" class="w-5 h-5 rounded border-slate-300 text-sky-600 focus:ring-sky-500" checked>
                                        <span class="text-sm font-medium text-slate-700">Active Product</span>
                                    </label>
                                </div>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-slate-700 mb-1">Product Image</label>
                                <input id="product-image" type="file" accept="image/*" class="w-full text-sm text-slate-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-sky-50 file:text-sky-700 hover:file:bg-sky-100 cursor-pointer">
                            </div>
                        </div>
                    </div>

                    <div class="flex justify-end gap-3 pt-6 border-t border-slate-100 mt-4">
                        <button type="button" onclick="closeProductModal()" class="h-11 px-6 rounded-xl border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition">Cancel</button>
                        <button type="submit" class="h-11 px-8 rounded-xl bg-sky-600 text-white text-sm font-semibold hover:bg-sky-700 transition shadow-lg shadow-sky-600/20">Save Product</button>
                    </div>
                </form>
            </div>
        </div>
    </main>
</div>
    `;
}