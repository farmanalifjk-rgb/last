import { formatCurrency } from "../shared/currency.js";
import { createIcons, icons } from "lucide";
import { getTaxes, createTax, updateTax, deleteTax } from "../js/inventory/services/inventory-api";
import { Pagination } from "../shared/Pagination";
import { escapeHtml, loadErrorHtml, formatMoney } from "../shared/format.js";
import { toast, errorMessage, confirmDialog } from "../shared/ui.js";

// Rows from the last render, keyed by id: inline handlers carry only numeric ids, never serialized API data.
let taxesById = new Map();
window.openEditTaxModalById = function(id) {
    const row = taxesById.get(Number(id));
    if (row) window.openEditTaxModal(row);
};

let filters = { search: "", page: 1, page_size: 10 };

export function TaxesCard({ title, value, valueId, icon, gradient, accent, iconColor, subtitle }) {
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

export function TaxesCards() {
    return `<div class="grid grid-cols-3 gap-6 mb-8">
        ${TaxesCard({ title: "Total Taxes", value: "-", valueId: "stat-taxes-total", icon: "receipt", gradient: "bg-gradient-to-br from-amber-50 to-white", accent: "bg-amber-500", iconColor: "text-amber-600", subtitle: "Configured tax rules" })}
        ${TaxesCard({ title: "Active Taxes", value: "-", valueId: "stat-taxes-active", icon: "check-circle", gradient: "bg-gradient-to-br from-emerald-50 to-white", accent: "bg-emerald-500", iconColor: "text-emerald-600", subtitle: "Applied in checkout" })}
        ${TaxesCard({ title: "Default Rate", value: "-", valueId: "stat-taxes-default", icon: "star", gradient: "bg-gradient-to-br from-blue-50 to-white", accent: "bg-blue-500", iconColor: "text-blue-600", subtitle: "Standard application" })}
    </div>`;
}

export function TaxesToolbar() {
    return `<div class="flex items-center justify-between gap-4 mb-6">
        <div class="flex items-center gap-3">
            <div class="relative">
                <i data-lucide="search" class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"></i>
                <input id="taxes-search" type="text" placeholder="Search taxes..." class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl border-slate-200">
            </div>
            <button onclick="refreshTaxes()" class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition text-slate-500 flex items-center justify-center">
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
    onPageChange: async (page) => { filters.page = page; await loadTaxes(); }
});

window.initializeTaxes = async function() {
    pagination.initialize();
    await loadTaxes();
    initializeTaxesEvents();
};

async function loadTaxes() {
    try {
        const response = await getTaxes(filters);
        renderTaxesTable(response.results);
        updateStats(response);
        pagination.updateFromResponse(response);
        createIcons({ icons });
    } catch (e) {
        console.error("Error loading taxes", e);
        const errorTarget = document.getElementById("taxes-table"); if (errorTarget) errorTarget.innerHTML = loadErrorHtml(e, "tax configurations");
    }
}

function updateStats(response) {
    const total = response.count || 0;
    const results = response.results || [];
    const active = results.filter(t => t.is_active).length;
    const defaultTax = results.find(t => t.is_default);
    
    document.getElementById("stat-taxes-total").textContent = total;
    document.getElementById("stat-taxes-active").textContent = active;
    
    if (defaultTax) {
        document.getElementById("stat-taxes-default").textContent = defaultTax.tax_type === 'Percentage' ? `${defaultTax.rate}%` : `${formatCurrency(defaultTax.rate)}`;
    } else {
        document.getElementById("stat-taxes-default").textContent = "None";
    }
}

function initializeTaxesEvents() {
    const search = document.getElementById("taxes-search");
    if (search) {
        search.addEventListener("input", debounce(async (e) => {
            filters.search = e.target.value; filters.page = 1; pagination.reset(); await loadTaxes();
        }, 400));
    }

    const form = document.getElementById("tax-form");
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await saveTax();
        });
    }
}

window.refreshTaxes = async function() {
    filters = { search: "", page: 1, page_size: 10 };
    document.getElementById("taxes-search").value = "";
    pagination.reset();
    await loadTaxes();
};

function debounce(callback, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); };
}

function renderTaxesTable(rows) {
    taxesById = new Map(rows.map((row) => [Number(row.id), row]));
    if (!rows || rows.length === 0) {
        document.getElementById("taxes-table").innerHTML = `<div class="text-center py-12 text-slate-500">No taxes found.</div>`;
        return;
    }

    const html = `
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <table class="w-full text-left text-sm whitespace-nowrap">
                <thead class="bg-slate-50 text-slate-600 font-medium border-b border-slate-200">
                    <tr>
                        <th class="px-6 py-4">Tax Name</th>
                        <th class="px-6 py-4">Rate</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4 text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${rows.map(tax => `
                        <tr class="group hover:bg-amber-50/40 transition-colors">
                            <td class="px-6 py-4">
                                <div class="font-bold text-slate-900 flex items-center gap-2">
                                    ${escapeHtml(tax.name)}
                                    ${tax.is_default ? `<span class="inline-flex px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-700 uppercase tracking-wider">Default</span>` : ''}
                                </div>
                            </td>
                            <td class="px-6 py-4">
                                <span class="font-mono bg-slate-50 px-2 py-1 rounded text-slate-700">
                                    ${tax.tax_type === 'Percentage' ? `${escapeHtml(tax.rate)}%` : `${escapeHtml(formatCurrency(tax.rate))}`}
                                </span>
                            </td>
                            <td class="px-6 py-4">
                                ${tax.is_active 
                                    ? `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">Active</span>` 
                                    : `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">Inactive</span>`}
                            </td>
                            <td class="px-6 py-4 text-right">
                                <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button onclick="openEditTaxModalById(${Number(tax.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-amber-600 hover:bg-amber-50 flex items-center justify-center transition">
                                        <i data-lucide="edit-2" class="w-4 h-4"></i>
                                    </button>
                                    <button onclick="deleteTax(${Number(tax.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center transition">
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
    
    document.getElementById("taxes-table").innerHTML = html;
}

window.openCreateTaxModal = function() {
    document.getElementById("tax-id").value = "";
    document.getElementById("tax-form").reset();
    document.getElementById("tax-is-active").checked = true;
    document.getElementById("tax-is-default").checked = false;
    document.getElementById("tax-modal-title").textContent = "Add Tax";
    
    const modal = document.getElementById("tax-form-modal");
    const content = document.getElementById("tax-modal-content");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    setTimeout(() => content.classList.remove("scale-95"), 10);
};

window.openEditTaxModal = function(tax) {
    document.getElementById("tax-id").value = tax.id;
    document.getElementById("tax-name").value = tax.name || "";
    document.getElementById("tax-type").value = tax.tax_type || "Percentage";
    document.getElementById("tax-rate").value = tax.rate || "";
    document.getElementById("tax-is-active").checked = tax.is_active;
    document.getElementById("tax-is-default").checked = tax.is_default;
    
    document.getElementById("tax-modal-title").textContent = "Edit Tax";
    
    const modal = document.getElementById("tax-form-modal");
    const content = document.getElementById("tax-modal-content");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    setTimeout(() => content.classList.remove("scale-95"), 10);
};

window.closeTaxModal = function() {
    const modal = document.getElementById("tax-form-modal");
    const content = document.getElementById("tax-modal-content");
    content.classList.add("scale-95");
    setTimeout(() => {
        modal.classList.add("hidden");
        modal.classList.remove("flex");
    }, 200);
};

async function saveTax() {
    const id = document.getElementById("tax-id").value;
    const data = {
        name: document.getElementById("tax-name").value,
        tax_type: document.getElementById("tax-type").value,
        rate: parseFloat(document.getElementById("tax-rate").value),
        is_active: document.getElementById("tax-is-active").checked,
        is_default: document.getElementById("tax-is-default").checked,
    };

    try {
        if (id) {
            await updateTax(id, data);
        } else {
            await createTax(data);
        }
        closeTaxModal();
        await loadTaxes();
    } catch (error) {
        console.error("Error saving tax", error);
        toast(errorMessage(error, "Failed to save tax."), "error");
    }
}

window.deleteTax = async function(id) {
    if (await confirmDialog({ title: "Delete tax", message: "Are you sure you want to delete this tax?", confirmLabel: "Delete" })) {
        try {
            await deleteTax(id);
            await loadTaxes();
        } catch (error) {
            console.error("Error deleting tax",  error);
            toast(errorMessage(error, "Failed to delete tax."), "error");
        }
    }
};
