import { createIcons, icons } from "lucide";
import { escapeHtml, loadErrorHtml } from "../shared/format.js";
import { getVariants, createVariant, updateVariant, deleteVariant, addVariantValue, deleteVariantValue } from "./inventory/services/inventory-api";
import { toast, errorMessage, confirmDialog } from "../shared/ui.js";

let filters = { search: "" };

window.initializeVariants = async function() {
    await loadVariants();
    initializeVariantsEvents();
}

async function loadVariants() {
    try {
        const response = await getVariants(filters);
        const data = response.results || response;
        const count = response.count || data.length;
        
        document.getElementById("total-variants").innerText = count;
        renderVariantsTable(data);
    } catch (e) {
        console.error("Failed to load variants", e);
        const errorTarget = document.getElementById("variants-table"); if (errorTarget) errorTarget.innerHTML = loadErrorHtml(e, "variants");
    }
}

function initializeVariantsEvents() {
    const search = document.getElementById("variant-search");
    if (search) {
        search.addEventListener("input", debounce(async (e) => {
            filters.search = e.target.value; await loadVariants();
        }, 400));
    }
    
    const form = document.getElementById("variant-form");
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await saveVariant();
        });
    }
}

window.refreshVariants = async function() {
    filters = { search: "" };
    document.getElementById("variant-search").value = "";
    await loadVariants();
};

function debounce(callback, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); };
}

function renderVariantsTable(rows) {
    if (rows.length === 0) {
        document.getElementById("variants-table").innerHTML = `<div class="p-8 text-center text-slate-500">No variants found.</div>`;
        return;
    }

    const tableHTML = `
        <div class="overflow-x-auto w-full rounded-2xl border border-slate-100">
            <table class="w-full text-left border-collapse bg-white">
                <thead>
                    <tr class="bg-slate-50/50 border-b border-slate-100">
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Variant Name</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Values</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${rows.map(row => {
                        const values = row.values || [];
                        const valuesHtml = values.map(v => `<span class="inline-flex px-2 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200 mb-1 mr-1">${escapeHtml(v.value)}</span>`).join("");
                        
                        return `
                        <tr class="group hover:bg-orange-50/40 transition-colors">
                            <td class="p-4 text-sm font-semibold text-slate-800 group-hover:text-orange-700">${escapeHtml(row.name)}</td>
                            <td class="p-4">
                                <div class="flex flex-wrap max-w-md">${valuesHtml || '<span class="text-xs text-slate-400">No values</span>'}</div>
                            </td>
                            <td class="p-4 text-right">
                                <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button onclick="window.openEditVariantModal(${Number(row.id)})" class="w-8 h-8 rounded-lg flex items-center justify-center text-orange-600 hover:bg-orange-100 transition" title="Edit">
                                        <i data-lucide="edit-2" class="w-4 h-4"></i>
                                    </button>
                                    <button onclick="window.deleteVariantHandler(${Number(row.id)})" class="w-8 h-8 rounded-lg flex items-center justify-center text-rose-600 hover:bg-rose-100 transition" title="Delete">
                                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `}).join("")}
                </tbody>
            </table>
        </div>
    `;
    
    document.getElementById("variants-table").innerHTML = tableHTML;
    createIcons({ icons });
}

window.openCreateVariantModal = function() {
    document.getElementById("variant-form").reset();
    document.getElementById("variant-id").value = "";
    document.getElementById("form-modal-title").innerText = "Add Variant";
    document.getElementById("variant-values-container").classList.add("hidden");
    const modal = document.getElementById("variant-form-modal");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
};

let currentVariantValues = [];

window.openEditVariantModal = async function(id) {
    try {
        const response = await getVariants({ id });
        const variants = response.results || response;
        const variant = Array.isArray(variants) ? variants.find(v => v.id === id) : variants;
        if(!variant) return;

        document.getElementById("variant-id").value = variant.id;
        document.getElementById("variant-name").value = variant.name;
        
        currentVariantValues = variant.values || [];
        renderVariantValuesList(variant.id);

        document.getElementById("variant-values-container").classList.remove("hidden");
        document.getElementById("form-modal-title").innerText = "Edit Variant";
        const modal = document.getElementById("variant-form-modal");
        modal.classList.remove("hidden");
        modal.classList.add("flex");
    } catch (e) {
        console.error("Error loading variant details", e);
    }
};

function renderVariantValuesList(variantId) {
    const list = document.getElementById("variant-values-list");
    list.innerHTML = currentVariantValues.map(v => `
        <span class="inline-flex items-center gap-1 px-2 py-1 rounded-md text-sm font-medium bg-slate-100 text-slate-700 border border-slate-200">
            ${escapeHtml(v.value)}
            <button type="button" onclick="window.removeVariantValueHandler(${Number(variantId)}, ${Number(v.id)})" class="text-slate-400 hover:text-rose-500">
                <i data-lucide="x" class="w-3 h-3"></i>
            </button>
        </span>
    `).join("");
    createIcons({ icons });
}

window.addVariantValueHandler = async function() {
    const variantId = document.getElementById("variant-id").value;
    const input = document.getElementById("new-variant-value");
    const value = input.value.trim();
    if (!value || !variantId) return;

    try {
        const res = await addVariantValue(variantId, { value });
        currentVariantValues.push(res);
        input.value = "";
        renderVariantValuesList(variantId);
        await loadVariants();
    } catch (e) {
        console.error("Error adding variant value", e);
        toast(errorMessage(e, "Failed to add value."), "error");
    }
};

window.removeVariantValueHandler = async function(variantId, valueId) {
    try {
        await deleteVariantValue(variantId, valueId);
        currentVariantValues = currentVariantValues.filter(v => v.id !== valueId);
        renderVariantValuesList(variantId);
        await loadVariants();
    } catch (e) {
        console.error("Error removing variant value", e);
        toast(errorMessage(e, "Failed to remove value."), "error");
    }
};

window.closeVariantModal = function() {
    const modal = document.getElementById("variant-form-modal");
    modal.classList.add("hidden");
    modal.classList.remove("flex");
};

async function saveVariant() {
    const id = document.getElementById("variant-id").value;
    const data = { name: document.getElementById("variant-name").value };

    try {
        const btn = document.querySelector("#variant-form button[type='submit']");
        btn.disabled = true;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Saving...`;
        createIcons({ icons });

        if (id) {
            await updateVariant(id, data);
        } else {
            await createVariant(data);
        }
        
        window.closeVariantModal();
        await loadVariants();
        
    } catch (e) {
        console.error("Error saving variant", e);
        toast(errorMessage(e, "Failed to save variant."), "error");
    } finally {
        const btn = document.querySelector("#variant-form button[type='submit']");
        if(btn) {
            btn.innerHTML = `Save Variant`;
            btn.disabled = false;
        }
    }
}

window.deleteVariantHandler = async function(id) {
    if (await confirmDialog({ title: "Delete variant", message: "Delete this variant and all its values?", confirmLabel: "Delete" })) {
        try {
            await deleteVariant(id);
            await loadVariants();
        } catch (e) {
            console.error("Error deleting variant", e);
            toast(errorMessage(e, "Failed to delete variant."), "error");
        }
    }
};