import { formatCurrency } from "../shared/currency.js";
import { apiDownload, buildQuery } from "../services/api.js";
import { createIcons, icons } from "lucide";

import {
    getDashboard,
    getInventory,
    getSummary,
    getLowStock,
    getProduct,
    getMovements,
    getMovementSummary,
    getAdjustments,
    getAdjustment,
    getValuation,
    getReports,
    getAnalytics,
    updateProduct,
    getSlowMoving,
    getMostReturned,
} from "../js/inventory/services/inventory-api";

import { StatusBadge } from "../js/inventory/components/StatusBadge";

import { ProductRow } from "../js/inventory/components/ProductRow";

import { ProductModal } from "./inventory/components/ProductModal";

import { InventoryTable } from "./inventory/components/InventoryTable";

import { LoadingState } from "./inventory/components/LoadingState";

import { ErrorState } from "./inventory/components/ErrorState";

import { ProductDetailModal } from "./inventory/components/ProductDetailModal";

import { EditProductModal } from "./inventory/components/EditProductModal";
import { toast, errorMessage } from "../shared/ui.js";


// ============================================================================
// STATE MANAGEMENT
// ============================================================================
const state = {

    page: 1,

    totalPages: 1,

    hasNext: false,

    hasPrevious: false,

    tab: "all",

    search: "",

    searchTimer: null,

    sort: "name",

    order: "asc",

    selectedProduct: null,

};
// ============================================================================
// INITIALIZATION
// ============================================================================
window.initializeInventory = async function () {
  // 1. Setup Event Listeners
  setupEventListeners();

  // 2. Load Dashboard Stats
  await loadDashboardStats();

  // 3. Load Initial Table Data
  await loadInventory();
};

function setupEventListeners() {
  const searchInput = document.getElementById("inventory-search");
  const globalSearchInput = document.getElementById("global-search-input");
  const tabs = document.querySelectorAll("#inventory-tabs button");
  const nextPage = document.getElementById("next-page");
  const prevPage = document.getElementById("prev-page");

  // Search Debounce (Local Table Search)
  searchInput?.addEventListener("input", (e) => {
    clearTimeout(state.searchTimer);
    state.search = e.target.value.trim();
    state.searchTimer = setTimeout(() => {
      state.page = 1;
      loadInventory();
    }, 300);
  });

  // Global Search Debounce
  globalSearchInput?.addEventListener("input", (e) => {
    clearTimeout(state.searchTimer);
    state.search = e.target.value.trim();
    state.searchTimer = setTimeout(() => {
      state.page = 1;
      loadInventory();
    }, 300);
  });

  // Filter Tabs
  tabs.forEach((tab) => {
    tab.addEventListener("click", (e) => {
      // Update active tab styling
      tabs.forEach((t) => {
        t.className = "px-5 py-2.5 text-gray-500 hover:text-gray-900 hover:bg-gray-50 font-medium text-sm rounded-full transition";
      });
      
      const clickedTab = e.currentTarget;
      clickedTab.className = "px-5 py-2.5 bg-emerald-50 text-[#0aa877] font-semibold text-sm rounded-full transition";
      
      state.tab = clickedTab.dataset.tab;
      state.page = 1;
      loadInventory();
    });
  });

  // Pagination
  nextPage?.addEventListener("click", () => {
    if (!state.hasNext) return;
    state.page++;
    loadInventory();
  });

  prevPage?.addEventListener("click", () => {
    if (!state.hasPrevious) return;
    state.page--;
    loadInventory();
  });

  // Export Menu Outside Click
  document.addEventListener("click", (event) => {
    const container = document.getElementById("export-menu-container");
    if (container && !container.contains(event.target)) {
      closeExportMenu();
    }
  });
}

// ============================================================================
// DASHBOARD STATS
// ============================================================================
async function loadDashboardStats() {
  try {
    
    const data = await getDashboard();
    
    animateCounter(
      document.getElementById("total-products-stat"),
      data.total_products || 0
    );

    animateCounter(
      document.getElementById("low-stock-stat"),
      data.low_stock_products || 0
    );

    animateCounter(
      document.getElementById("out-of-stock-stat"),
      data.out_of_stock_products || 0
    );

    // The backend has no overstock count, so the card shows a dash instead of a fake zero.
    const overstockElement = document.getElementById("overstock-stat");
    if (overstockElement) {
      if (data.overstock_products === null || data.overstock_products === undefined) overstockElement.textContent = "—";
      else animateCounter(overstockElement, data.overstock_products);
    }
    
    // For top category, it might be a string or number, handle appropriately
    const topCategoryElement = document.getElementById("top-category-stat");
    if (topCategoryElement) {
        if (typeof data.top_category_count === 'number') {
            animateCounter(topCategoryElement, data.top_category_count);
        } else {
            topCategoryElement.textContent = data.top_category || "N/A";
        }
    }
  } catch (error) {
    console.error("Dashboard Load Error:", error);
  }
}

// ============================================================================
// INVENTORY TABLE RENDERING
// ============================================================================
async function loadInventory() {
  const tableBody = document.getElementById("inventory-table-body");
  
  // Loading State
  tableBody.innerHTML = LoadingState();

  createIcons({ icons });

  try {
    const params = new URLSearchParams({ page: state.page });
    
    if (state.search) params.append("search", state.search);
    
    // Map tabs to backend parameters if needed
    if (state.tab !== "all") {
        params.append("status", state.tab);
    }

    const data = await getInventory(`?${params.toString()}`);

    const products = data.results || [];

    state.totalPages = Math.ceil(data.count / 20) || 1;
    state.hasNext = data.next !== null;
    state.hasPrevious = data.previous !== null;

    tableBody.innerHTML = InventoryTable(products);
    
    createIcons({ icons });
    updatePagination();
    
  } catch (error) {
    console.error("Inventory Load Error:", error);
    tableBody.innerHTML = ErrorState();
    createIcons({ icons });
  }
}

// ============================================================================
// HELPERS & UI COMPONENTS
// ============================================================================


function animateCounter(element, target, duration = 900) {
  if (!element) return;
  target = Number(target) || 0;
  const startTime = performance.now();

  function update(currentTime) {
    const progress = Math.min((currentTime - startTime) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = Math.floor(target * eased).toLocaleString();
    if (progress < 1) {
      requestAnimationFrame(update);
    } else {
      element.textContent = target.toLocaleString();
    }
  }
  requestAnimationFrame(update);
}

function updatePagination() {
  const prevBtn = document.getElementById("prev-page");
  const nextBtn = document.getElementById("next-page");
  const pageContainer = document.getElementById("pagination-numbers");

  if (prevBtn) prevBtn.disabled = !state.hasPrevious;
  if (nextBtn) nextBtn.disabled = !state.hasNext;
  
  if (pageContainer) {
    pageContainer.innerHTML = `<span class="px-3 py-1 bg-gray-50 rounded-lg border border-gray-200">Page ${state.page} of ${state.totalPages}</span>`;
  }
}

// ============================================================================
// EXPORT FUNCTIONS
// ============================================================================
function toggleExportMenu(event) {
  event.stopPropagation();
  const menu = document.getElementById("export-menu");
  menu?.classList.toggle("hidden");
}

function closeExportMenu() {
  document.getElementById("export-menu")?.classList.add("hidden");
}

function buildExportUrl(format) {
  const params = new URLSearchParams();
  if (state.search) params.append("search", state.search);
  if (state.tab !== "all") params.append("status", state.tab);
  
  // Aligning with standard Django structure and movement history endpoints provided[cite: 4]
  return `/api/reports/stock/export/${format}/${buildQuery({ search: state.search, status: state.tab !== "all" ? state.tab : undefined })}`;
}


// ============================================================================
// MODALS & ACTIONS
// ============================================================================
async function viewProductDetails(productId) {



    try {

        const data = await getProduct(productId);

        document.getElementById(
            "product-detail-body"
        ).innerHTML = ProductDetailModal(data);

        createIcons({ icons });

        openProductDetailModal();

    }

    catch (error) {

        console.error(error);

        toast(errorMessage(error, "Unable to load product."), "error");

    }

}

function openProductDetailModal() {

    const modal = document.getElementById(
        "product-detail-modal"
    );

    modal.classList.remove("hidden");

    modal.classList.add("flex");

}

function closeProductDetailModal() {

    const modal = document.getElementById(
        "product-detail-modal"
    );

    modal.classList.remove("flex");

    modal.classList.add("hidden");

}


window.openProductModal = function () {
    const modal = document.getElementById("product-modal");

    modal.classList.remove("hidden");
    modal.classList.add("flex");
};

window.closeProductModal = function () {
    const modal = document.getElementById("product-modal");

    modal.classList.remove("flex");
    modal.classList.add("hidden");
};

window.closeProductDetailModal = function () {

    const modal = document.getElementById("product-detail-modal");

    modal.classList.remove("flex");
    modal.classList.add("hidden");

}


function exportProductCSV() {

    apiDownload(buildExportUrl("csv"), "stock-report.csv");

}


function exportProductExcel() {

    apiDownload(buildExportUrl("excel"), "stock-report.xlsx");

}


function exportProductPdf() {

    apiDownload(buildExportUrl("pdf"), "stock-report.pdf");

}


window.openEditProduct = async function(id) {



    const response = await getProduct(id);

    const product = response.product;

    document.getElementById("product-detail-body").innerHTML =
        EditProductModal(product);

    createIcons({ icons });
    EditProductModal(product);

}


window.saveProduct = async function(id) {

    const data = {

        name: document.getElementById("edit-name").value,

        sales_price: document.getElementById("edit-sale-price").value,

        cost_price: document.getElementById("edit-cost-price").value,

    };

    await updateProduct(id, data);

    closeProductDetailModal();

    loadInventory();
}


// ============================================================================
// WINDOW BINDINGS
// ============================================================================
window.toggleExportMenu = toggleExportMenu;
window.closeExportMenu = closeExportMenu;
// InventoryPage's export menu calls these names. (The previous bindings pointed
// at exportCSV/exportExcel/exportPdf, which do not exist in this module; the
// ReferenceError aborted main.js and left the whole app blank.)
// window.exportCSV belongs to order-history.js and is not overridden here.
window.exportProductCSV = exportProductCSV;
window.exportProductExcel = exportProductExcel;
window.exportProductPdf = exportProductPdf;
window.loadInventory = loadInventory;
window.viewProductDetails = viewProductDetails;
window.openProductDetailModal = openProductDetailModal;
window.closeProductDetailModal = closeProductDetailModal;
window.exportProductCSV = exportProductCSV;
window.exportProductExcel = exportProductExcel;
window.exportProductPdf = exportProductPdf;
