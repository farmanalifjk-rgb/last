import { createIcons, icons } from "lucide";
import { getPaymentMethods, createPaymentMethod, updatePaymentMethod, deletePaymentMethod } from "../js/inventory/services/inventory-api";
import { Pagination } from "../shared/Pagination";
import { escapeHtml, loadErrorHtml } from "../shared/format.js";
import { toast, errorMessage, confirmDialog } from "../shared/ui.js";

// Rows from the last render, keyed by id: inline handlers carry only numeric ids, never serialized API data.
let paymentMethodsById = new Map();
window.openEditPaymentMethodModalById = function(id) {
    const row = paymentMethodsById.get(Number(id));
    if (row) window.openEditPaymentMethodModal(row);
};

let filters = { search: "", page: 1, page_size: 10 };

export function PaymentMethodCard({ title, value, valueId, icon, gradient, accent, iconColor, subtitle }) {
    return `<div class="relative overflow-hidden rounded-3xl ${gradient} border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
        <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full ${accent} opacity-20 blur-3xl"></div>
        <i data-lucide="${icon}" class="absolute right-5 top-5 h-20 w-20 opacity-10 ${iconColor}"></i>
        <div class="relative">
            <p class="text-sm font-semibold text-slate-600">${title}</p>
            <h2 id="${valueId}" class="mt-3 text-4xl font-black tracking-tight text-slate-900">${value}</h2>
            <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full ${accent}"></div></div></div>
            <p class="mt-4 text-sm font-medium text-slate-600">${subtitle}</p>
        </div>
    </div>`;
}

export function PaymentMethodsCards() {
    return `<div class="grid grid-cols-3 gap-6 mb-8">
        ${PaymentMethodCard({ title: "Total Methods", value: "-", valueId: "stat-pm-total", icon: "wallet", gradient: "bg-gradient-to-br from-emerald-50 to-white", accent: "bg-emerald-500", iconColor: "text-emerald-600", subtitle: "All configured options" })}
        ${PaymentMethodCard({ title: "Active Methods", value: "-", valueId: "stat-pm-active", icon: "zap", gradient: "bg-gradient-to-br from-sky-50 to-white", accent: "bg-sky-500", iconColor: "text-sky-600", subtitle: "Available in POS" })}
        ${PaymentMethodCard({ title: "Default Method", value: "-", valueId: "stat-pm-default", icon: "star", gradient: "bg-gradient-to-br from-indigo-50 to-white", accent: "bg-indigo-500", iconColor: "text-indigo-600", subtitle: "Pre-selected standard" })}
    </div>`;
}

export function PaymentMethodsToolbar() {
    return `<div class="flex items-center justify-between gap-4 mb-6">
        <div class="flex items-center gap-3">
            <div class="relative">
                <i data-lucide="search" class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"></i>
                <input id="pm-search" type="text" placeholder="Search methods..." class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl border-slate-200">
            </div>
            <button onclick="refreshPaymentMethods()" class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition text-slate-500 flex items-center justify-center">
                <i data-lucide="refresh-cw" class="w-5 h-5"></i>
            </button>
        </div>
    </div>`;
}

const pagination = new Pagination({
    prevButtonId: "prev-page",
    nextButtonId: "next-page",
    containerId: "pagination-numbers",
    pageSize: filters.page_size,
    onPageChange: async (page) => { filters.page = page; await loadPaymentMethods(); }
});

window.initializePaymentMethods = async function() {
    pagination.initialize();
    await loadPaymentMethods();
    initializePaymentMethodsEvents();
};

async function loadPaymentMethods() {
    try {
        const response = await getPaymentMethods(filters);
        renderPaymentMethodsTable(response.results);
        updateStats(response);
        pagination.updateFromResponse(response);
        createIcons({ icons });
    } catch (e) {
        console.error("Error loading payment methods", e);
        const errorTarget = document.getElementById("payment-methods-table"); if (errorTarget) errorTarget.innerHTML = loadErrorHtml(e, "payment methods");
    }
}

function updateStats(response) {
    const total = response.count || 0;
    const results = response.results || [];
    const active = results.filter(pm => pm.is_active).length;
    const defaultPm = results.find(pm => pm.is_default);
    
    document.getElementById("stat-pm-total").textContent = total;
    document.getElementById("stat-pm-active").textContent = active;
    document.getElementById("stat-pm-default").textContent = defaultPm ? defaultPm.name : "None";
}

function initializePaymentMethodsEvents() {
    const search = document.getElementById("pm-search");
    if (search) {
        search.addEventListener("input", debounce(async (e) => {
            filters.search = e.target.value; filters.page = 1; pagination.reset(); await loadPaymentMethods();
        }, 400));
    }

    const form = document.getElementById("pm-form");
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await savePaymentMethod();
        });
    }
}

window.refreshPaymentMethods = async function() {
    filters = { search: "", page: 1, page_size: 10 };
    document.getElementById("pm-search").value = "";
    pagination.reset();
    await loadPaymentMethods();
};

function debounce(callback, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); };
}

function getTypeIcon(type) {
    const map = {
        'Cash': 'banknote',
        'Card': 'credit-card',
        'Bank': 'landmark',
        'Mobile': 'smartphone',
        'Other': 'circle-dollar-sign'
    };
    return map[type] || 'circle-dollar-sign';
}

function renderPaymentMethodsTable(rows) {
    paymentMethodsById = new Map(rows.map((row) => [Number(row.id), row]));
    if (!rows || rows.length === 0) {
        document.getElementById("payment-methods-table").innerHTML = `<div class="text-center py-12 text-slate-500">No payment methods found.</div>`;
        return;
    }

    const html = `
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <table class="w-full text-left text-sm whitespace-nowrap">
                <thead class="bg-slate-50 text-slate-600 font-medium border-b border-slate-200">
                    <tr>
                        <th class="px-6 py-4">Method Name</th>
                        <th class="px-6 py-4">Type</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4 text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${rows.map(pm => `
                        <tr class="group hover:bg-emerald-50/40 transition-colors">
                            <td class="px-6 py-4">
                                <div class="font-bold text-slate-900 flex items-center gap-2">
                                    ${escapeHtml(pm.name)}
                                    ${pm.is_default ? `<span class="inline-flex px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-100 text-indigo-700 uppercase tracking-wider">Default</span>` : ''}
                                </div>
                                ${pm.instructions ? `<div class="text-xs text-slate-500 mt-1 truncate max-w-xs">${escapeHtml(pm.instructions)}</div>` : ''}
                            </td>
                            <td class="px-6 py-4">
                                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-50 text-slate-700 border border-slate-200">
                                    <i data-lucide="${getTypeIcon(pm.method_type)}" class="w-3 h-3"></i> ${escapeHtml(pm.method_type)}
                                </span>
                            </td>
                            <td class="px-6 py-4">
                                ${pm.is_active 
                                    ? `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">Active</span>` 
                                    : `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">Inactive</span>`}
                            </td>
                            <td class="px-6 py-4 text-right">
                                <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button onclick="openEditPaymentMethodModalById(${Number(pm.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 flex items-center justify-center transition">
                                        <i data-lucide="edit-2" class="w-4 h-4"></i>
                                    </button>
                                    <button onclick="deletePaymentMethod(${Number(pm.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center transition">
                                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
    
    document.getElementById("payment-methods-table").innerHTML = html;
}

window.openCreatePaymentMethodModal = function() {
    document.getElementById("pm-id").value = "";
    document.getElementById("pm-form").reset();
    document.getElementById("pm-is-active").checked = true;
    document.getElementById("pm-is-default").checked = false;
    document.getElementById("pm-modal-title").textContent = "Add Payment Method";
    
    const modal = document.getElementById("pm-form-modal");
    const content = document.getElementById("pm-modal-content");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    setTimeout(() => content.classList.remove("scale-95"), 10);
};

window.openEditPaymentMethodModal = function(pm) {
    document.getElementById("pm-id").value = pm.id;
    document.getElementById("pm-name").value = pm.name || "";
    document.getElementById("pm-type").value = pm.method_type || "Cash";
    document.getElementById("pm-instructions").value = pm.instructions || "";
    document.getElementById("pm-is-active").checked = pm.is_active;
    document.getElementById("pm-is-default").checked = pm.is_default;
    
    document.getElementById("pm-modal-title").textContent = "Edit Payment Method";
    
    const modal = document.getElementById("pm-form-modal");
    const content = document.getElementById("pm-modal-content");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    setTimeout(() => content.classList.remove("scale-95"), 10);
};

window.closePaymentMethodModal = function() {
    const modal = document.getElementById("pm-form-modal");
    const content = document.getElementById("pm-modal-content");
    content.classList.add("scale-95");
    setTimeout(() => {
        modal.classList.add("hidden");
        modal.classList.remove("flex");
    }, 200);
};

async function savePaymentMethod() {
    const id = document.getElementById("pm-id").value;
    const data = {
        name: document.getElementById("pm-name").value,
        method_type: document.getElementById("pm-type").value,
        instructions: document.getElementById("pm-instructions").value,
        is_active: document.getElementById("pm-is-active").checked,
        is_default: document.getElementById("pm-is-default").checked,
    };

    try {
        if (id) {
            await updatePaymentMethod(id, data);
        } else {
            await createPaymentMethod(data);
        }
        closePaymentMethodModal();
        await loadPaymentMethods();
    } catch (error) {
        console.error("Error saving payment method", error);
        toast(errorMessage(error, "Failed to save payment method."), "error");
    }
}

window.deletePaymentMethod = async function(id) {
    if (await confirmDialog({ title: "Delete payment method", message: "Are you sure you want to delete this payment method?", confirmLabel: "Delete" })) {
        try {
            await deletePaymentMethod(id);
            await loadPaymentMethods();
        } catch (error) {
            console.error("Error deleting payment method", error);
            toast(errorMessage(error, "Failed to delete payment method."), "error");
        }
    }
};
