import { formatCurrency } from "../shared/currency.js";
import { createIcons, icons } from "lucide";
import { escapeHtml, safeUrl, loadErrorHtml, formatMoney } from "../shared/format.js";
import { getProducts, createProduct, updateProduct2, deleteProduct, getCategories, getBrands } from "./inventory/services/inventory-api";
import { Pagination } from "../shared/Pagination";
import { apiDownload } from "../services/api.js";
import { toast, errorMessage, confirmDialog } from "../shared/ui.js";

let filters = { search: "", category_id: "", brand_id: "", is_active: "", page: 1, page_size: 20, ordering: "-created_at" };

const pagination = new Pagination({
    prevButtonId: "prev-page",
    nextButtonId: "next-page",
    containerId: "pagination-numbers",
    pageSize: filters.page_size,
    onPageChange: async (page) => { filters.page = page; await loadProducts(); }
});

window.initializeAllProducts = async function() {
    pagination.initialize();
    await loadFilterOptions();
    await loadProducts();
    initializeProductsEvents();
}

async function loadFilterOptions() {
    try {
        const [catResp, brandResp] = await Promise.all([
            getCategories({ page_size: 100 }),
            getBrands({ page_size: 100 })
        ]);
        
        const catSelect = document.getElementById("product-category-filter");
        const brandSelect = document.getElementById("product-brand-filter");
        const formCatSelect = document.getElementById("product-category");
        const formBrandSelect = document.getElementById("product-brand");

        let catOptions = `<option value="">All Categories</option>`;
        let formCatOptions = `<option value="">Select Category</option>`;
        (catResp.results || []).forEach(c => {
            const opt = `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`;
            catOptions += opt;
            formCatOptions += opt;
        });
        
        let brandOptions = `<option value="">All Brands</option>`;
        let formBrandOptions = `<option value="">Select Brand</option>`;
        (brandResp.results || []).forEach(b => {
            const opt = `<option value="${escapeHtml(b.id)}">${escapeHtml(b.name)}</option>`;
            brandOptions += opt;
            formBrandOptions += opt;
        });

        if (catSelect) catSelect.innerHTML = catOptions;
        if (formCatSelect) formCatSelect.innerHTML = formCatOptions;
        if (brandSelect) brandSelect.innerHTML = brandOptions;
        if (formBrandSelect) formBrandSelect.innerHTML = formBrandOptions;

    } catch (e) {
        console.error("Failed to load filter options", e);
    }
}

async function loadProducts() {
    try {
        const response = await getProducts(filters);
        
        // Update stats
        document.getElementById("total-products").innerText = response.count || 0;
        
        // Compute other stats from results (approximate if paginated, ideally comes from API)
        const active = (response.results || []).filter(p => p.is_active).length;
        const lowStock = (response.results || []).filter(p => p.stock_quantity > 0 && p.stock_quantity <= (p.min_stock || 0)).length;
        const outOfStock = (response.results || []).filter(p => p.stock_quantity <= 0).length;
        
        document.getElementById("active-products").innerText = active;
        document.getElementById("low-stock").innerText = lowStock;
        document.getElementById("out-of-stock").innerText = outOfStock;

        renderProductsTable(response.results || []);
        pagination.updateFromResponse(response);
    } catch (e) {
        console.error("Failed to load products", e);
        const errorTarget = document.getElementById("products-table"); if (errorTarget) errorTarget.innerHTML = loadErrorHtml(e, "products");
    }
}

function initializeProductsEvents() {
    const search = document.getElementById("product-search");
    if (search) {
        search.addEventListener("input", debounce(async (e) => {
            filters.search = e.target.value; filters.page = 1; pagination.reset(); await loadProducts();
        }, 400));
    }
    
    ['product-category-filter', 'product-brand-filter', 'product-status-filter'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("change", async (e) => {
                if (id === 'product-category-filter') filters.category_id = e.target.value;
                if (id === 'product-brand-filter') filters.brand_id = e.target.value;
                if (id === 'product-status-filter') filters.is_active = e.target.value;
                filters.page = 1; pagination.reset(); await loadProducts();
            });
        }
    });

    const form = document.getElementById("product-form");
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await saveProduct();
        });
    }
}

window.refreshProducts = async function() {
    filters = { search: "", category_id: "", brand_id: "", is_active: "", page: 1, page_size: 20, ordering: "-created_at" };
    document.getElementById("product-search").value = "";
    document.getElementById("product-category-filter").value = "";
    document.getElementById("product-brand-filter").value = "";
    document.getElementById("product-status-filter").value = "";
    pagination.reset();
    await loadProducts();
};

function debounce(callback, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); };
}

function renderProductsTable(rows) {
    if (rows.length === 0) {
        document.getElementById("products-table").innerHTML = `
            <div class="flex flex-col items-center justify-center p-12 text-slate-500">
                <i data-lucide="package-x" class="w-16 h-16 text-slate-300 mb-4"></i>
                <h3 class="text-lg font-semibold text-slate-700">No products found</h3>
                <p class="text-sm">Try adjusting your filters or add a new product.</p>
            </div>
        `;
        createIcons({ icons });
        return;
    }

    const tableHTML = `
        <div class="overflow-x-auto w-full">
            <table class="w-full text-left border-collapse">
                <thead>
                    <tr class="bg-slate-50/50 border-b border-slate-200">
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider rounded-tl-xl">Product</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">SKU</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Category</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Brand</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Price</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Stock</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-center">Status</th>
                        <th class="p-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right rounded-tr-xl">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${rows.map(row => {
                        const imageUrl = safeUrl(row.image);
                        const imageHtml = imageUrl
                            ? `<img src="${escapeHtml(imageUrl)}" class="w-10 h-10 rounded-lg object-cover border border-slate-200" alt="${escapeHtml(row.name)}">` 
                            : `<div class="w-10 h-10 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center"><i data-lucide="package" class="w-5 h-5 text-slate-400"></i></div>`;
                        
                        const statusBadge = row.is_active
                            ? `<span class="inline-flex px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700 border border-emerald-200">Active</span>`
                            : `<span class="inline-flex px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">Inactive</span>`;
                        
                        let stockColor = "text-slate-700";
                        if (row.stock_quantity <= 0) stockColor = "text-rose-600 font-bold";
                        else if (row.stock_quantity <= (row.min_stock || 0)) stockColor = "text-amber-600 font-bold";

                        return `
                            <tr class="group hover:bg-sky-50/40 transition-colors cursor-pointer">
                                <td class="p-4">
                                    <div class="flex items-center gap-3">
                                        ${imageHtml}
                                        <div>
                                            <p class="text-sm font-semibold text-slate-800 group-hover:text-sky-700">${escapeHtml(row.name)}</p>
                                            <p class="text-xs text-slate-500">${escapeHtml(row.barcode || 'No barcode')}</p>
                                        </div>
                                    </div>
                                </td>
                                <td class="p-4 text-sm font-medium text-slate-600">${escapeHtml(row.sku)}</td>
                                <td class="p-4 text-sm text-slate-600">${escapeHtml(row.category_name || '-')}</td>
                                <td class="p-4 text-sm text-slate-600">${escapeHtml(row.brand_name || '-')}</td>
                                <td class="p-4 text-sm font-semibold text-slate-700 text-right">${formatCurrency(row.sales_price)}</td>
                                <td class="p-4 text-sm ${stockColor} text-right">${escapeHtml(row.stock_quantity)} ${escapeHtml(row.unit || '')}</td>
                                <td class="p-4 text-center">${statusBadge}</td>
                                <td class="p-4 text-right">
                                    <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button onclick="openEditProductModal(${Number(row.id)})" class="w-8 h-8 rounded-lg flex items-center justify-center text-sky-600 hover:bg-sky-100 transition" title="Edit">
                                            <i data-lucide="edit-2" class="w-4 h-4"></i>
                                        </button>
                                        <button onclick="deleteProductHandler(${Number(row.id)})" class="w-8 h-8 rounded-lg flex items-center justify-center text-rose-600 hover:bg-rose-100 transition" title="Delete">
                                            <i data-lucide="trash-2" class="w-4 h-4"></i>
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }).join("")}
                </tbody>
            </table>
        </div>
    `;
    
    document.getElementById("products-table").innerHTML = tableHTML;
    createIcons({ icons });
}

window.openCreateProductModal = function() {
    document.getElementById("product-form").reset();
    document.getElementById("product-id").value = "";
    document.getElementById("form-modal-title").innerText = "Add Product";
    document.getElementById("product-form-modal").classList.remove("hidden");
    document.getElementById("product-form-modal").classList.add("flex");
};

window.openEditProductModal = async function(id) {
    try {
        const response = await getProducts({ id });
        const product = response.results ? response.results.find(p => p.id === id) : response.find(p=>p.id===id);
        if (!product) return;

        document.getElementById("product-id").value = product.id;
        document.getElementById("product-name").value = product.name;
        document.getElementById("product-sku").value = product.sku;
        document.getElementById("product-barcode").value = product.barcode || "";
        document.getElementById("product-category").value = product.category || "";
        document.getElementById("product-brand").value = product.brand || "";
        document.getElementById("product-cost-price").value = product.cost_price;
        document.getElementById("product-sales-price").value = product.sales_price;
        document.getElementById("product-stock").value = product.stock_quantity;
        document.getElementById("product-min-stock").value = product.min_stock || "";
        document.getElementById("product-max-stock").value = product.max_stock || "";
        document.getElementById("product-unit").value = product.unit || "";
        document.getElementById("product-description").value = product.description || "";
        document.getElementById("product-is-active").checked = product.is_active;
        
        document.getElementById("form-modal-title").innerText = "Edit Product";
        document.getElementById("product-form-modal").classList.remove("hidden");
        document.getElementById("product-form-modal").classList.add("flex");
    } catch (e) {
        console.error("Error fetching product details", e);
        toast(errorMessage(e, "Failed to load product details."), "error");
    }
};

window.closeProductModal = function() {
    document.getElementById("product-form-modal").classList.add("hidden");
    document.getElementById("product-form-modal").classList.remove("flex");
};

async function saveProduct() {
    const id = document.getElementById("product-id").value;
    
    const formData = new FormData();
    formData.append("name", document.getElementById("product-name").value);
    formData.append("sku", document.getElementById("product-sku").value);
    formData.append("barcode", document.getElementById("product-barcode").value);
    
    const category = document.getElementById("product-category").value;
    if (category) formData.append("category", category);
    
    const brand = document.getElementById("product-brand").value;
    if (brand) formData.append("brand", brand);
    
    formData.append("cost_price", document.getElementById("product-cost-price").value);
    formData.append("sales_price", document.getElementById("product-sales-price").value);
    
    const stock = document.getElementById("product-stock").value;
    if (stock) formData.append("stock_quantity", stock);
    
    const minStock = document.getElementById("product-min-stock").value;
    if (minStock) formData.append("min_stock", minStock);
    
    const maxStock = document.getElementById("product-max-stock").value;
    if (maxStock) formData.append("max_stock", maxStock);
    
    formData.append("unit", document.getElementById("product-unit").value);
    formData.append("description", document.getElementById("product-description").value);
    formData.append("is_active", document.getElementById("product-is-active").checked);
    
    const imageInput = document.getElementById("product-image");
    if (imageInput.files.length > 0) {
        formData.append("image", imageInput.files[0]);
    }

    try {
        const btn = document.querySelector("#product-form button[type='submit']");
        const originalText = btn.innerHTML;
        btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Saving...`;
        btn.disabled = true;
        createIcons({ icons });

        if (id) {
            await updateProduct2(id, formData);
        } else {
            await createProduct(formData);
        }
        
        window.closeProductModal();
        await loadProducts();
        
    } catch (e) {
        console.error("Error saving product", e);
        // Show the backend reason (e.g. duplicate SKU), not a generic failure.
        toast(errorMessage(e, "Failed to save product."), "error");
    } finally {
        const btn = document.querySelector("#product-form button[type='submit']");
        if(btn) {
            btn.innerHTML = `Save Product`;
            btn.disabled = false;
        }
    }
}

window.deleteProductHandler = async function(id) {
    const ok = await confirmDialog({
        title: "Delete this product?",
        message: "This action cannot be undone.",
        confirmLabel: "Delete product",
    });
    if (!ok) return;
    try {
        await deleteProduct(id);
        toast("Product deleted.", "success");
        await loadProducts();
    } catch (e) {
        console.error("Error deleting product", e);
        toast(errorMessage(e, "Failed to delete product."), "error");
    }
};

// Real export: the canonical catalog CSV (all products of the active business;
// requires catalog.manage - the backend refuses otherwise and the reason is shown).
let exportingProducts = false;
window.exportProducts = async function(format = "csv") {
    if (format !== "csv") {
        toast("Only CSV export is available.", "info");
        return;
    }
    if (exportingProducts) return;
    exportingProducts = true;
    try {
        await apiDownload("/api/catalog/products/export/csv/", "catalog-products.csv");
        toast("Product export downloaded.", "success");
    } catch (e) {
        toast(errorMessage(e, "The products could not be exported."), "error");
    } finally {
        exportingProducts = false;
    }
};