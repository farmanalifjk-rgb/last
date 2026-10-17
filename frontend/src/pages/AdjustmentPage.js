import { Sidebar } from "../components/Sidebar";
import { AdjustmentCards } from "../js/Adjustments/components/AdjustmentCards";
import { AdjustmentToolbar } from "../js/Adjustments/components/AdjustmentToolbar";



export function AdjustmentPage() {
    return `

<div class="flex h-screen bg-[#f4f7f6]">

    ${Sidebar()}

    <main class="flex-1 p-8 overflow-y-auto">

        <div class="flex items-center justify-between">

            <div>

                <h1 class="text-3xl font-bold">
                    Stock Adjustments
                </h1>

                <p class="text-gray-500 mt-1">
                    Complete stock adjustment history
                </p>

            </div>

            <div class="flex items-center gap-3">
            <button type="button" id="adjustment-new-btn" class="h-11 rounded-xl bg-violet-600 px-5 text-sm font-semibold text-white shadow-sm hover:bg-violet-700">New adjustment</button>
            <div class="relative" id="adjustment-export-menu-container">

                <button type="button" id="adjustment-export-btn" aria-haspopup="menu" aria-expanded="false" aria-controls="adjustment-export-menu"
                    class="h-10 px-4 bg-white border border-gray-200 rounded-xl text-sm font-medium flex items-center gap-2 hover:bg-gray-50 transition">

                    <i data-lucide="download" class="w-4 h-4">
                    </i>

                    Export Adjustments

                    <i data-lucide="chevron-down" class="w-4 h-4 text-gray-400">
                    </i>

                </button>

                <div id="adjustment-export-menu" role="menu"
                    class="hidden absolute right-0 top-12 w-64 bg-white border border-gray-200 rounded-xl shadow-xl p-2 z-50">

                    <!-- CSV -->
                    <button type="button" id="adjustment-export-csv" role="menuitem"
                        class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-50 transition text-left">

                        <div class="w-9 h-9 rounded-lg bg-emerald-50 flex items-center justify-center">

                            <i data-lucide="file-spreadsheet" class="w-4 h-4 text-emerald-600">
                            </i>

                        </div>

                        <div>

                            <p class="font-medium text-gray-800">
                                Export Adjustments (CSV)
                            </p>

                            <p class="text-xs text-gray-400">
                                Current filters, all pages, one row per item (.csv)
                            </p>

                        </div>

                    </button>

                    <!-- Excel -->

                    <!-- PDF -->

                </div>

            </div>
            </div>

        </div>

        ${AdjustmentCards()}

        <div class="premium-surface rounded-3xl p-6">

            ${AdjustmentToolbar()}

            <div id="adjustment-table"></div>

        </div>

        <!-- ============================================================================
     PAGINATION
     Requires: Lucide icons (createIcons), Pagination.js module
============================================================================ -->
<div class="flex items-center justify-between px-6 py-4 border-t border-gray-100">

  <!-- Optional: results summary -->
  <p
    id="pagination-info"
    class="text-sm text-gray-500">
</p>

  <!-- Prev / Page X of Y / Next -->
  <div class="flex items-center gap-2">

    <button
      id="prev-page"
      class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent transition"
      disabled
    >
      <i data-lucide="chevron-left" class="w-4 h-4"></i>
    </button>

    <!-- Pagination.js injects "Page X of Y" here -->
    <div id="pagination-numbers" class="text-sm text-gray-600 font-medium">
      <span class="px-3 py-1 bg-gray-50 rounded-lg border border-gray-200">Page 1 of 1</span>
    </div>

    <button
      id="next-page"
      class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent transition"
      disabled
    >
      <i data-lucide="chevron-right" class="w-4 h-4"></i>
    </button>

  </div>

</div>

<div
    id="adjustment-detail-modal"
    class="hidden fixed inset-0 bg-black/50 z-50 items-center justify-center p-8">

    <div id="adjustment-detail-body"></div>

</div>

    </main>

</div>

`;
}
