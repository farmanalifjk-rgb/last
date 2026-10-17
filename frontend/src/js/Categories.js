import { createIcons, icons } from "lucide";
import { getCategories, createCategory, updateCategory, deleteCategory } from "./inventory/services/inventory-api";
import { Pagination } from "../shared/Pagination";
import { escapeHtml, loadErrorHtml } from "../shared/format.js";
import { toast, errorMessage, confirmDialog } from "../shared/ui.js";

// Rows from the last load, keyed by id, so inline handlers only carry numeric ids.
let categoriesById = new Map();

let filters = { search: "", page: 1, page_size: 20 };

const pagination = new Pagination({
    prevButtonId: "prev-page",
    nextButtonId: "next-page",
    containerId: "pagination-numbers",
    pageSize: filters.page_size,
    onPageChange: async (page) => { filters.page = page; await loadCategories(); }
});

window.initializeCategories = async function() {
    pagination.initialize();
    await loadCategories();
    initializeCategoriesEvents();
}

async function loadCategories() {
    try {
        const response = await getCategories(filters);
        document.getElementById("total-categories").innerText = response.count || 0;
        renderCategoriesTable(response.results || []);
        pagination.updateFromResponse(response);
    } catch (e) {
        console.error("Failed to load categories", e);
        const errorTarget = document.getElementById("categories-table"); if (errorTarget) errorTarget.innerHTML = loadErrorHtml(e, "categories");
    }
}

function initializeCategoriesEvents() {
    const search = document.getElementById("category-search");
    if (search) {
        search.addEventListener("input", debounce(async (e) => {
            filters.search = e.target.value; filters.page = 1; pagination.reset(); await loadCategories();
        }, 400));
    }
    
    const form = document.getElementById("category-form");
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await saveCategory();
        });
    }
}

window.refreshCategories = async function() {
    filters = { search: "", page: 1, page_size: 20 };
    document.getElementById("category-search").value = "";
    pagination.reset();
    await loadCategories();
};

function debounce(callback, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); };
}

function renderCategoriesTable(rows) {
    categoriesById = new Map(rows.map((row) => [Number(row.id), row]));
    if (rows.length === 0) {
        document.getElementById("categories-table").innerHTML = `<div class="p-8 text-center text-slate-500">No categories found.</div>`;
        return;
    }

    const tableHTML = `
        <div class="overflow-x-auto w-full rounded-2xl border border-slate-100">
            <table class="w-full text-left border-collapse bg-white">
                <thead>
                    <tr class="bg-slate-50/50 border-b border-slate-100">
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Name</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${rows.map(row => `
                        <tr class="group hover:bg-emerald-50/40 transition-colors">
                            <td class="p-4 text-sm font-semibold text-slate-800 group-hover:text-emerald-700">${escapeHtml(row.name)}</td>
                            <td class="p-4 text-right">
                                <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button onclick="window.openEditCategoryModal(${Number(row.id)})" class="w-8 h-8 rounded-lg flex items-center justify-center text-emerald-600 hover:bg-emerald-100 transition" title="Edit">
                                        <i data-lucide="edit-2" class="w-4 h-4"></i>
                                    </button>
                                    <button onclick="window.deleteCategoryHandler(${Number(row.id)})" class="w-8 h-8 rounded-lg flex items-center justify-center text-rose-600 hover:bg-rose-100 transition" title="Delete">
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
    
    document.getElementById("categories-table").innerHTML = tableHTML;
    createIcons({ icons });
}

window.openCreateCategoryModal = function() {
    document.getElementById("category-form").reset();
    document.getElementById("category-id").value = "";
    document.getElementById("form-modal-title").innerText = "Add Category";
    const modal = document.getElementById("category-form-modal");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
};

window.openEditCategoryModal = function(id) {
    const row = categoriesById.get(Number(id));
    if (!row) return;
    document.getElementById("category-id").value = row.id;
    document.getElementById("category-name").value = row.name ?? "";
    document.getElementById("form-modal-title").innerText = "Edit Category";
    const modal = document.getElementById("category-form-modal");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
};

window.closeCategoryModal = function() {
    const modal = document.getElementById("category-form-modal");
    modal.classList.add("hidden");
    modal.classList.remove("flex");
};

async function saveCategory() {
    const id = document.getElementById("category-id").value;
    const data = { name: document.getElementById("category-name").value };

    try {
        const btn = document.querySelector("#category-form button[type='submit']");
        btn.disabled = true;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Saving...`;
        createIcons({ icons });

        if (id) {
            await updateCategory(id, data);
        } else {
            await createCategory(data);
        }
        
        window.closeCategoryModal();
        await loadCategories();
        
    } catch (e) {
        console.error("Error saving category", e);
        toast(errorMessage(e, "Failed to save category."), "error");
    } finally {
        const btn = document.querySelector("#category-form button[type='submit']");
        if(btn) {
            btn.innerHTML = `Save Category`;
            btn.disabled = false;
        }
    }
}

window.deleteCategoryHandler = async function(id) {
    if (await confirmDialog({ title: "Delete category", message: "Delete this category?", confirmLabel: "Delete" })) {
        try {
            await deleteCategory(id);
            await loadCategories();
        } catch (e) {
            console.error("Error deleting category", e);
            toast(errorMessage(e, "Failed to delete category."), "error");
        }
    }
};