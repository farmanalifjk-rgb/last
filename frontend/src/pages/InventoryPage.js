import { Sidebar } from "../components/Sidebar";
import { DashboardCards } from "../js/inventory/components/DashboardCards";
import { Toolbar } from "../js/inventory/components/Toolbar";
import { Tabs } from "../js/inventory/components/Tabs";

export function InventoryPage() {
  return `<div class="flex h-screen bg-[#f4f7f6] overflow-hidden font-sans">

    ${Sidebar()}

    <main class="flex-1 h-screen min-h-0 overflow-y-auto p-8 flex flex-col gap-8">

        <!-- HEADER SECTION -->
        <header class="flex items-center justify-between shrink-0">
            <div>
                <h1 class="text-[28px] font-bold text-gray-900 tracking-tight">Inventory Management</h1>
                <p class="text-sm text-gray-500 mt-1">Monitor stock levels and manage product inventory.</p>
            </div>

            <div class="flex items-center gap-5">
                <div class="flex items-center gap-3">

                    <div class="flex items-center gap-3">

                        <!-- Export -->
                        <div class="relative" id="export-menu-container">

                            <button onclick="toggleExportMenu(event)"
                                class="h-10 px-4 bg-white border border-gray-200 rounded-xl text-sm font-medium flex items-center gap-2 hover:bg-gray-50 transition">

                                <i data-lucide="download" class="w-4 h-4">
                                </i>

                                Export Inventory

                                <i data-lucide="chevron-down" class="w-4 h-4 text-gray-400">
                                </i>

                            </button>

                            <div id="export-menu"
                                class="hidden absolute right-0 top-12 w-60 bg-white border border-gray-200 rounded-xl shadow-xl p-2 z-50">

                                <!-- CSV -->
                                <button onclick="exportProductCSV(); closeExportMenu()"
                                    class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-50 transition text-left">

                                    <div class="w-9 h-9 rounded-lg bg-emerald-50 flex items-center justify-center">

                                        <i data-lucide="file-spreadsheet" class="w-4 h-4 text-emerald-600">
                                        </i>

                                    </div>

                                    <div>

                                        <p class="font-medium text-gray-800">
                                            Export Inventory (CSV)
                                        </p>

                                        <p class="text-xs text-gray-400">
                                            Filtered inventory data (.csv)
                                        </p>

                                    </div>

                                </button>

                                <!-- Excel -->
                                <button onclick="exportProductExcel(); closeExportMenu()"
                                    class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-50 transition text-left">

                                    <div class="w-9 h-9 rounded-lg bg-green-50 flex items-center justify-center">

                                        <i data-lucide="sheet" class="w-4 h-4 text-green-600">
                                        </i>

                                    </div>

                                    <div>

                                        <p class="font-medium text-gray-800">
                                            Export Inventory (Excel)
                                        </p>

                                        <p class="text-xs text-gray-400">
                                            Microsoft Excel (.xlsx)
                                        </p>

                                    </div>

                                </button>

                                <!-- PDF -->
                                <button onclick="exportProductPdf(); closeExportMenu()"
                                    class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-50 transition text-left">

                                    <div class="w-9 h-9 rounded-lg bg-red-50 flex items-center justify-center">

                                        <i data-lucide="file-text" class="w-4 h-4 text-red-600">
                                        </i>

                                    </div>

                                    <div>

                                        <p class="font-medium text-gray-800">
                                            Export Inventory (PDF)
                                        </p>

                                        <p class="text-xs text-gray-400">
                                            Printable filtered inventory report
                                        </p>

                                    </div>

                                </button>

                            </div>

                        </div>

                        <!-- More Actions -->
                        <button
                            class="h-10 px-4 border border-gray-200 rounded-xl text-sm font-medium flex items-center gap-2 hover:bg-gray-50 transition">

                            More Actions

                            <i data-lucide="chevron-down" class="w-4 h-4">
                            </i>

                        </button>

                        <!-- Add Product -->
                        <button onclick="openCreateProductModal()"
                            class="premium-mint-button h-10 px-5 rounded-xl text-sm font-semibold transition hover:-translate-y-0.5 flex items-center gap-2">

                            <i data-lucide="plus" class="w-4 h-4">
                            </i>

                            Add Product

                        </button>

                    </div>


                </div>
                <!-- Notification -->
                <button
                    class="w-12 h-12 bg-white rounded-2xl flex items-center justify-center shadow-sm relative hover:bg-gray-50 transition">
                    <i data-lucide="bell" class="w-5 h-5 text-gray-600"></i>
                    <span
                        class="absolute top-3.5 right-3.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
                </button>


            </div>
        </header>

        <!-- DASHBOARD CARDS -->
        ${DashboardCards()}

        <!-- MAIN TABLE SURFACE -->
        <div class="premium-surface rounded-[30px] flex flex-col flex-1 min-h-0 overflow-hidden">

            <!-- Inventory Header & Export -->


            <!-- Tabs & Filters -->
            <div class="flex px-8 py-5">

                ${Toolbar()}

                <div>

                    ${Tabs()}

                </div>

            </div>

            <!-- Search & Actions -->


            <!-- Table Container -->
            <div class="flex-1 min-h-0 overflow-y-auto px-8 pb-4">
                <table class="w-full text-sm text-left">
                    <thead
                        class=" sticky top-0 z-20 bg-gradient-to-r from-white via-emerald-50/60 to-white border-b border-emerald-100 backdrop-blur-xl">
                        <tr>
                            <th class="">

                                <div class="flex items-center gap-2">

                                    <i data-lucide="package" class="w-4 h-4 text-blue-600"></i>

                                    <span>Product</span>

                                </div>

                            </th>
                            <th class="px-6 py-4 font-medium">
                                <div class="flex items-center gap-2">

                                    <i data-lucide="layers-3" class="w-4 h-4 text-emerald-600"></i>

                                    <span>Category</span>

                                </div>
                            </th>
                            <th class="px-6 py-4 font-medium min-w-[200px]">
                                <div class="flex items-center gap-2">

                                    <i data-lucide="boxes">
                                        class="w-4 h-4 text-emerald-600"></i>

                                    <span>Stock</span>

                                </div>
                            </th>
                            <th class="px-6 py-4 font-medium">
                                <div class="flex items-center gap-2">
                                    <i data-lucide="badge-dollar-sign" class="w-4 h-4 text-emerald-600"></i>

                                    <span>Price</span>

                                </div>
                            </th>
                            <th class="px-6 py-4 font-medium text-center">
                                <div class="flex items-center gap-2">

                                    <i data-lucide="activity" class="w-4 h-4 text-emerald-600"></i>

                                    <span>Status</span>

                                </div>
                            </th>
                            <th class="py-4 pl-6 font-medium text-right">
                                <div class="flex items-center gap-2">

                                    <i data-lucide="settings-2" class="w-4 h-4 text-emerald-600"></i>

                                    <span>Action</span>

                                </div>
                            </th>
                        </tr>
                    </thead>
                    <tbody id="inventory-table-body" class="divide-y divide-gray-50">
                        <!-- Data populated by inventory.js -->
                    </tbody>
                </table>
            </div>

            <!-- Pagination -->
            <div class="px-8 py-5 border-t border-gray-100 bg-white shrink-0 flex items-center justify-between">
                <button id="prev-page"
                    class="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i> Previous
                </button>

                <div id="pagination-numbers" class="flex items-center gap-1.5 text-sm font-medium text-gray-600">
                    <!-- Rendered by JS logic -->
                </div>

                <button id="next-page"
                    class="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed">
                    Next <i data-lucide="arrow-right" class="w-4 h-4"></i>
                </button>
            </div>
        </div>

    </main>
</div>

<!-- PRODUCT DETAILS MODAL (Hidden by default) -->
<div id="product-detail-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50 p-8">

    <div id="product-detail-body"></div>

</div>

<!-- Product Modal -->
<div id="product-modal" class="hidden fixed inset-0 bg-black/40 z-50 items-center justify-center">
    <div class="bg-white rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">

        <div class="flex items-center justify-between p-6 border-b">
            <h2 class="text-xl font-semibold">
                Product Details
            </h2>

            <button onclick="closeProductModal()" class="text-gray-500 hover:text-black">
                ✕
            </button>
        </div>

        <div id="product-modal-body" class="p-6">

        </div>

    </div>
</div>
  `;
}

