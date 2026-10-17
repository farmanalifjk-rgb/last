import { createIcons, icons } from "lucide";
import { escapeHtml, loadErrorHtml } from "../shared/format.js";
import { getBrands, createBrand, updateBrand, deleteBrand } from "./inventory/services/inventory-api";
import { Pagination } from "../shared/Pagination";
import { toast, errorMessage, confirmDialog } from "../shared/ui.js";

let filters = { search: "", page: 1, page_size: 20 };

// Note: Ensure Brands endpoint is paginated or adapt appropriately.
window.initializeBrands = async function() {
    await loadBrands();
    initializeBrandsEvents();
}

async function loadBrands() {
    try {
        const response = await getBrands(filters);
        // If paginated, response has results, else response is array
        const data = response.results || response;
        const count = response.count || data.length;
        
        document.getElementById("total-brands").innerText = count;
        renderBrandsTable(data);
    } catch (e) {
        console.error("Failed to load brands", e);
        const errorTarget = document.getElementById("brands-table"); if (errorTarget) errorTarget.innerHTML = loadErrorHtml(e, "brands");
    }
}

function initializeBrandsEvents() {
    const search = document.getElementById("brand-search");
    if (search) {
        search.addEventListener("input", debounce(async (e) => {
            filters.search = e.target.value; await loadBrands();
        }, 400));
    }
    
    const form = document.getElementById("brand-form");
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await saveBrand();
        });
    }
}

window.refreshBrands = async function() {
    filters = { search: "", page: 1, page_size: 20 };
    document.getElementById("brand-search").value = "";
    await loadBrands();
};

function debounce(callback, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); };
}

function renderBrandsTable(rows) {
    if (rows.length === 0) {
        document.getElementById("brands-table").innerHTML = `<div class="p-8 text-center text-slate-500">No brands found.</div>`;
        return;
    }

    const tableHTML = `
        <div class="overflow-x-auto w-full rounded-2xl border border-slate-100">
            <table class="w-full text-left border-collapse bg-white">
                <thead>
                    <tr class="bg-slate-50/50 border-b border-slate-100">
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Brand Name</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Description</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-center">Status</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${rows.map(row => {
                        const statusBadge = row.is_active !== false 
                            ? `<span class="inline-flex px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-100 text-purple-700 border border-purple-200">Active</span>`
                            : `<span class="inline-flex px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">Inactive</span>`;
                            
                        return `
                        <tr class="group hover:bg-purple-50/40 transition-colors">
                            <td class="p-4 text-sm font-semibold text-slate-800 group-hover:text-purple-700">${escapeHtml(row.name)}</td>
                            <td class="p-4 text-sm text-slate-500 max-w-xs truncate">${escapeHtml(row.description || '-')}</td>
                            <td class="p-4 text-center">${statusBadge}</td>
                            <td class="p-4 text-right">
                                <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button onclick="window.openEditBrandModal(${Number(row.id)})" class="w-8 h-8 rounded-lg flex items-center justify-center text-purple-600 hover:bg-purple-100 transition" title="Edit">
                                        <i data-lucide="edit-2" class="w-4 h-4"></i>
                                    </button>
                                    <button onclick="window.deleteBrandHandler(${Number(row.id)})" class="w-8 h-8 rounded-lg flex items-center justify-center text-rose-600 hover:bg-rose-100 transition" title="Delete">
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
    
    document.getElementById("brands-table").innerHTML = tableHTML;
    createIcons({ icons });
}

window.openCreateBrandModal = function() {
    document.getElementById("brand-form").reset();
    document.getElementById("brand-id").value = "";
    document.getElementById("brand-is-active").checked = true;
    document.getElementById("form-modal-title").innerText = "Add Brand";
    const modal = document.getElementById("brand-form-modal");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
};

window.openEditBrandModal = async function(id) {
    try {
        const response = await getBrands({ id });
        const brands = response.results || response;
        const brand = Array.isArray(brands) ? brands.find(b => b.id === id) : brands;
        if(!brand) return;

        document.getElementById("brand-id").value = brand.id;
        document.getElementById("brand-name").value = brand.name;
        document.getElementById("brand-description").value = brand.description || "";
        document.getElementById("brand-is-active").checked = brand.is_active !== false;
        
        document.getElementById("form-modal-title").innerText = "Edit Brand";
        const modal = document.getElementById("brand-form-modal");
        modal.classList.remove("hidden");
        modal.classList.add("flex");
    } catch (e) {
        console.error("Error loading brand details", e);
    }
};

window.closeBrandModal = function() {
    const modal = document.getElementById("brand-form-modal");
    modal.classList.add("hidden");
    modal.classList.remove("flex");
};

async function saveBrand() {
    const id = document.getElementById("brand-id").value;
    const data = { 
        name: document.getElementById("brand-name").value,
        description: document.getElementById("brand-description").value,
        is_active: document.getElementById("brand-is-active").checked
    };

    try {
        const btn = document.querySelector("#brand-form button[type='submit']");
        btn.disabled = true;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Saving...`;
        createIcons({ icons });

        if (id) {
            await updateBrand(id, data);
        } else {
            await createBrand(data);
        }
        
        window.closeBrandModal();
        await loadBrands();
        
    } catch (e) {
        console.error("Error saving brand", e);
        toast(errorMessage(e, "Failed to save brand."), "error");
    } finally {
        const btn = document.querySelector("#brand-form button[type='submit']");
        if(btn) {
            btn.innerHTML = `Save Brand`;
            btn.disabled = false;
        }
    }
}

window.deleteBrandHandler = async function(id) {
    if (await confirmDialog({ title: "Delete brand", message: "Delete this brand?", confirmLabel: "Delete" })) {
        try {
            await deleteBrand(id);
            await loadBrands();
        } catch (e) {
            console.error("Error deleting brand", e);
            toast(errorMessage(e, "Failed to delete brand."), "error");
        }
    }
};