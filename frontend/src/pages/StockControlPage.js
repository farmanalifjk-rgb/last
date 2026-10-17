import { Sidebar } from "../components/Sidebar";
import { pageHeader } from "../shared/ui.js";
import { createIcons, icons } from "lucide";

/** Page shell. The controller in js/stock/stock-control.js renders into #stock-control-root. */
export function StockControlPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div id="stock-control-root">
            ${pageHeader({ title: "Stock control", subtitle: "Stock levels, reorder rules, bin locations, cycle counts and reservations" })}
            <div class="text-sm text-slate-500">Loading…</div>
        </div>
    </main>
</div>`;
}

export function initializeStockControlIcons() {
    createIcons({ icons });
}
