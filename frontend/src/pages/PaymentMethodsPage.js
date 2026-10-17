import { Sidebar } from "../components/Sidebar";
import { PaymentMethodsCards, PaymentMethodsToolbar } from "../js/PaymentMethods";
import { createIcons, icons } from "lucide";

export function PaymentMethodsPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Payment Methods</h1>
                <p class="text-gray-500 mt-1">Configure accepted payment options</p>
            </div>
            <button onclick="openCreatePaymentMethodModal()" class="h-11 px-6 rounded-xl bg-emerald-600 text-white font-semibold hover:bg-emerald-700 transition shadow-sm hover:shadow-md flex items-center gap-2">
                <i data-lucide="credit-card" class="w-4 h-4"></i>
                <span>Add Method</span>
            </button>
        </div>
        
        ${PaymentMethodsCards()}
        
        <div class="premium-surface rounded-3xl p-6">
            ${PaymentMethodsToolbar()}
            <div id="payment-methods-table"></div>
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
        
        <!-- Payment Method Modal -->
        <div id="pm-form-modal" class="hidden fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 items-center justify-center p-8">
            <div class="bg-white rounded-3xl w-full max-w-lg shadow-2xl overflow-hidden transform scale-95 transition-transform duration-200" id="pm-modal-content">
                <div class="flex items-center justify-between px-8 py-6 border-b border-slate-100">
                    <h2 id="pm-modal-title" class="text-2xl font-bold text-slate-800">Add Payment Method</h2>
                    <button onclick="closePaymentMethodModal()" class="w-10 h-10 rounded-xl hover:bg-slate-100 text-slate-500 flex items-center justify-center transition">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <form id="pm-form" class="p-8 space-y-6">
                    <input type="hidden" id="pm-id">
                    
                    <div>
                        <label class="block text-sm font-medium text-slate-700 mb-1">Display Name</label>
                        <input id="pm-name" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="e.g. Visa / Mastercard">
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-slate-700 mb-1">Method Type</label>
                        <select id="pm-type" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 bg-white">
                            <option value="Cash">Cash</option>
                            <option value="Card">Credit / Debit Card</option>
                            <option value="Bank">Bank Transfer</option>
                            <option value="Mobile">Mobile Payment (NFC/QR)</option>
                            <option value="Other">Other</option>
                        </select>
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-slate-700 mb-1">Cashier Instructions (Optional)</label>
                        <textarea id="pm-instructions" rows="3" class="premium-input w-full p-4 rounded-xl border-slate-200" placeholder="e.g. Please check ID for purchases over $500"></textarea>
                    </div>
                    
                    <div class="flex flex-col gap-4 pt-2">
                        <label class="flex items-center justify-between cursor-pointer p-4 rounded-xl border border-slate-100 bg-slate-50 hover:bg-slate-100/50 transition">
                            <div>
                                <div class="font-medium text-slate-800">Active</div>
                                <div class="text-xs text-slate-500">Enable this method at checkout</div>
                            </div>
                            <div class="relative">
                                <input type="checkbox" id="pm-is-active" class="sr-only peer" checked>
                                <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
                            </div>
                        </label>
                        
                        <label class="flex items-center justify-between cursor-pointer p-4 rounded-xl border border-slate-100 bg-slate-50 hover:bg-slate-100/50 transition">
                            <div>
                                <div class="font-medium text-slate-800">Default Method</div>
                                <div class="text-xs text-slate-500">Pre-selected for fast checkout</div>
                            </div>
                            <div class="relative">
                                <input type="checkbox" id="pm-is-default" class="sr-only peer">
                                <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-500"></div>
                            </div>
                        </label>
                    </div>
                    
                    <div class="flex justify-end gap-3 pt-6 mt-2 border-t border-slate-100">
                        <button type="button" onclick="closePaymentMethodModal()" class="h-11 px-6 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition">Cancel</button>
                        <button type="submit" class="h-11 px-8 rounded-xl bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 transition shadow-sm hover:shadow-md">Save Method</button>
                    </div>
                </form>
            </div>
        </div>
    </main>
</div>
    `;
}
