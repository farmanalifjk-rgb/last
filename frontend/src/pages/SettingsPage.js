import { Sidebar } from "../components/Sidebar";

export function SettingsPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Settings</h1>
                <p class="text-slate-500 mt-1">Configure company, fiscal, and system settings</p>
            </div>
            <button onclick="saveSettings()" class="h-11 px-6 rounded-xl bg-indigo-600 text-white font-semibold hover:bg-indigo-700 transition shadow-sm hover:shadow-md flex items-center gap-2">
                <i data-lucide="save" class="w-4 h-4"></i>
                <span>Save Settings</span>
            </button>
        </div>
        
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="lg:col-span-2 space-y-6">
                <!-- General Settings -->
                <div class="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 premium-surface">
                    <h2 class="text-xl font-semibold mb-6 flex items-center gap-2 text-indigo-900">
                        <i data-lucide="building" class="w-5 h-5 text-indigo-500"></i>
                        General Settings
                    </h2>
                    <form id="settings-general-form" class="grid grid-cols-2 gap-6">
                        <div class="col-span-2">
                            <label class="block text-sm font-medium text-slate-700 mb-1">Company Name</label>
                            <input id="setting-company_name" type="text" class="premium-input w-full h-11 px-4 rounded-xl border border-gray-200" placeholder="e.g. Acme Corp">
                        </div>
                        <div class="col-span-2">
                            <label class="block text-sm font-medium text-slate-700 mb-1">Tagline</label>
                            <input id="setting-tagline" type="text" class="premium-input w-full h-11 px-4 rounded-xl border border-gray-200" placeholder="Your business tagline">
                        </div>
                        <div class="col-span-2">
                            <label class="block text-sm font-medium text-slate-700 mb-1">Address</label>
                            <textarea id="setting-address" rows="3" class="premium-input w-full p-4 rounded-xl border border-gray-200" placeholder="Full business address"></textarea>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Phone</label>
                            <input id="setting-phone" type="text" class="premium-input w-full h-11 px-4 rounded-xl border border-gray-200" placeholder="+1 234 567 8900">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Email</label>
                            <input id="setting-email" type="email" class="premium-input w-full h-11 px-4 rounded-xl border border-gray-200" placeholder="contact@example.com">
                        </div>
                        <div class="col-span-2">
                            <label class="block text-sm font-medium text-slate-700 mb-1">Website</label>
                            <input id="setting-website" type="url" class="premium-input w-full h-11 px-4 rounded-xl border border-gray-200" placeholder="https://example.com">
                        </div>
                    </form>
                </div>
                
                <!-- Fiscal Settings -->
                <div class="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 premium-surface">
                    <h2 class="text-xl font-semibold mb-6 flex items-center gap-2 text-indigo-900">
                        <i data-lucide="file-text" class="w-5 h-5 text-indigo-500"></i>
                        Fiscal Settings
                    </h2>
                    <div class="grid grid-cols-2 gap-6">
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Tax Number</label>
                            <input id="setting-tax_number" type="text" class="premium-input w-full h-11 px-4 rounded-xl border border-gray-200" placeholder="e.g. TAX-123456">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">GST / VAT</label>
                            <input id="setting-gst_number" type="text" class="premium-input w-full h-11 px-4 rounded-xl border border-gray-200" placeholder="GST Number">
                        </div>
                        <div class="col-span-2">
                            <label class="block text-sm font-medium text-slate-700 mb-1">Currency</label>
                            <input id="setting-currency" type="text" class="premium-input w-full h-11 px-4 rounded-xl border border-gray-200" placeholder="e.g. USD, EUR, GBP">
                        </div>
                    </div>
                </div>
                
                <!-- Receipt Settings -->
                <div class="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 premium-surface">
                    <h2 class="text-xl font-semibold mb-6 flex items-center gap-2 text-indigo-900">
                        <i data-lucide="receipt" class="w-5 h-5 text-indigo-500"></i>
                        Receipt Settings
                    </h2>
                    <div class="grid grid-cols-2 gap-6">
                        <div class="col-span-2">
                            <label class="block text-sm font-medium text-slate-700 mb-1">Receipt Paper Size</label>
                            <select id="setting-receipt_paper_size" class="premium-input w-full h-11 px-4 rounded-xl border border-gray-200 bg-white">
                                <option value="58mm">58mm (Compact Receipt)</option>
                                <option value="80mm">80mm (Standard Receipt)</option>
                                <option value="A5">A5 (Half Letter)</option>
                                <option value="A4">A4 (Standard Letter)</option>
                            </select>
                        </div>
                        <div class="col-span-2">
                            <label class="block text-sm font-medium text-slate-700 mb-1">Receipt Footer Message</label>
                            <textarea id="setting-receipt_footer" rows="2" class="premium-input w-full p-4 rounded-xl border border-gray-200" placeholder="Thank you for your business!"></textarea>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="space-y-6">
                <!-- Logo Upload -->
                <div class="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 premium-surface">
                    <h2 class="text-xl font-semibold mb-6 flex items-center gap-2 text-indigo-900">
                        <i data-lucide="image" class="w-5 h-5 text-indigo-500"></i>
                        Company Logo
                    </h2>
                    <div class="flex flex-col items-center">
                        <div class="w-48 h-48 rounded-2xl border-2 border-dashed border-gray-300 flex items-center justify-center bg-gray-50 mb-6 overflow-hidden relative group">
                            <img id="setting-logo-preview" src="" alt="Logo Preview" class="w-full h-full object-contain hidden" />
                            <div id="setting-logo-placeholder" class="text-center text-gray-400">
                                <i data-lucide="upload-cloud" class="w-10 h-10 mx-auto mb-2 opacity-50"></i>
                                <span class="text-sm font-medium">No logo selected</span>
                            </div>
                            <div class="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition cursor-pointer" onclick="document.getElementById('setting-logo').click()">
                                <span class="text-white font-medium flex items-center gap-2"><i data-lucide="edit-2" class="w-4 h-4"></i> Change</span>
                            </div>
                        </div>
                        <input type="file" id="setting-logo" class="hidden" accept="image/*" onchange="window.previewLogo(event)">
                        <button type="button" onclick="document.getElementById('setting-logo').click()" class="w-full h-11 rounded-xl border border-gray-200 font-medium hover:bg-gray-50 transition text-slate-700 flex items-center justify-center gap-2">
                            <i data-lucide="image-plus" class="w-4 h-4"></i>
                            Select New Logo
                        </button>
                    </div>
                </div>
                
                <!-- Quick Info -->
                <div class="bg-indigo-50 rounded-3xl border border-indigo-100 p-8">
                    <h3 class="text-indigo-900 font-bold mb-2">Did you know?</h3>
                    <p class="text-sm text-indigo-700 leading-relaxed mb-4">Your company details appear on all printed receipts, customer invoices, and email communications.</p>
                    <p class="text-sm text-indigo-700 leading-relaxed">Ensure your tax number and address are accurate to comply with local regulations.</p>
                </div>
            </div>
        </div>
    </main>
</div>
    `;
}
