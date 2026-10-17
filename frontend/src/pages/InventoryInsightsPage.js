import { Sidebar } from "../components/Sidebar";

/**
 * Shared scaffold for inventory valuation and ABC analysis.
 * kind: "valuation" | "abc"
 */
const COPY = {
    valuation: {
        title: "Inventory Valuation",
        subtitle: "Stock on hand valued at unit cost, per product",
        filterLabel: "All classes",
    },
    abc: {
        title: "ABC Analysis",
        subtitle: "Products ranked by annual value: A (top 80%), B (next 15%), C (last 5%)",
        filterLabel: "All classes",
    },
};

export function InventoryInsightsPage(kind = "valuation") {
    const copy = COPY[kind] || COPY.valuation;
    const filterControl = kind === "abc"
        ? `<select id="abc-class-filter" class="h-10 px-3 rounded-xl border border-slate-200 bg-white text-sm">
                <option value="">${copy.filterLabel}</option>
                <option value="A">Class A</option>
                <option value="B">Class B</option>
                <option value="C">Class C</option>
           </select>`
        : "";
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">${copy.title}</h1>
                <p class="text-gray-500 mt-1">${copy.subtitle}</p>
            </div>
        </div>

        <div class="premium-surface rounded-3xl p-6 bg-white border border-slate-100 shadow-sm">
            <div class="flex items-center justify-between gap-4 mb-6">
                <div class="flex items-center gap-3">${filterControl}</div>
                <p id="insights-summary" class="text-sm text-slate-500"></p>
            </div>
            <div id="insights-table" class="overflow-x-auto"></div>
            <div class="flex items-center justify-between px-6 py-4 border-t border-gray-100 mt-4">
                <p id="pagination-info" class="text-sm text-gray-500"></p>
                <div class="flex items-center gap-2">
                    <button id="prev-page" class="h-9 px-3 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40">Previous</button>
                    <div id="pagination-numbers" class="text-sm text-gray-600 font-medium"></div>
                    <button id="next-page" class="h-9 px-3 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40">Next</button>
                </div>
            </div>
        </div>
    </main>
</div>`;
}
