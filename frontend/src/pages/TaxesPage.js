import { Sidebar } from "../components/Sidebar";
import { TaxesCards, TaxesToolbar } from "../js/Taxes";
import { createIcons, icons } from "lucide";

export function TaxesPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Tax Configurations</h1>
                <p class="text-gray-500 mt-1">Manage global and item-specific tax rates</p>
            </div>
            <button onclick="openCreateTaxModal()" class="h-11 px-6 rounded-xl bg-amber-500 text-white font-semibold hover:bg-amber-600 transition shadow-sm hover:shadow-md flex items-center gap-2">
                <i data-lucide="plus" class="w-4 h-4"></i>
                <span>Add Tax</span>
            </button>
        </div>
        
        ${TaxesCards()}
        
        <div class="premium-surface rounded-3xl p-6">
            ${TaxesToolbar()}
            <div id="taxes-table"></div>
        </div>
        
        <div class="flex items-center justify-between px-6 py-4 border-t border-gray-100 bg-white rounded-b-3xl mt-[-24px] relative z-0">
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
        
        <!-- Tax Modal -->
        <div id="tax-form-modal" class="hidden fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 items-center justify-center p-8">
            <div class="bg-white rounded-3xl w-full max-w-lg shadow-2xl overflow-hidden transform scale-95 transition-transform duration-200" id="tax-modal-content">
                <div class="flex items-center justify-between px-8 py-6 border-b border-slate-100">
                    <h2 id="tax-modal-title" class="text-2xl font-bold text-slate-800">Add Tax</h2>
                    <button onclick="closeTaxModal()" class="w-10 h-10 rounded-xl hover:bg-slate-100 text-slate-500 flex items-center justify-center transition">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <form id="tax-form" class="p-8 space-y-6">
                    <input type="hidden" id="tax-id">
                    
                    <div>
                        <label class="block text-sm font-medium text-slate-700 mb-1">Tax Name</label>
                        <input id="tax-name" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="e.g. State Sales Tax">
                    </div>
                    
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Tax Type</label>
                            <select id="tax-type" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 bg-white">
                                <option value="Percentage">Percentage (%)</option>
                                <option value="Fixed">Fixed Amount</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Rate</label>
                            <input id="tax-rate" type="number" step="0.01" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="0.00">
                        </div>
                    </div>
                    
                    <div class="flex flex-col gap-4 pt-2">
                        <label class="flex items-center justify-between cursor-pointer p-4 rounded-xl border border-slate-100 bg-slate-50 hover:bg-slate-100/50 transition">
                            <div>
                                <div class="font-medium text-slate-800">Active</div>
                                <div class="text-xs text-slate-500">Enable this tax rule in the system</div>
                            </div>
                            <div class="relative">
                                <input type="checkbox" id="tax-is-active" class="sr-only peer" checked>
                                <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500"></div>
                            </div>
                        </label>
                        
                        <label class="flex items-center justify-between cursor-pointer p-4 rounded-xl border border-slate-100 bg-slate-50 hover:bg-slate-100/50 transition">
                            <div>
                                <div class="font-medium text-slate-800">Default Tax</div>
                                <div class="text-xs text-slate-500">Automatically apply to all new items</div>
                            </div>
                            <div class="relative">
                                <input type="checkbox" id="tax-is-default" class="sr-only peer">
                                <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-500"></div>
                            </div>
                        </label>
                    </div>
                    
                    <div class="flex justify-end gap-3 pt-6 mt-2 border-t border-slate-100">
                        <button type="button" onclick="closeTaxModal()" class="h-11 px-6 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition">Cancel</button>
                        <button type="submit" class="h-11 px-8 rounded-xl bg-amber-500 text-white text-sm font-semibold hover:bg-amber-600 transition shadow-sm hover:shadow-md">Save Tax</button>
                    </div>
                </form>
            </div>
        </div>
    </main>
</div>
    `;
}
