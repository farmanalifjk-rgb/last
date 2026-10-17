import { Sidebar } from "../components/Sidebar";
import { pageHeader } from "../shared/ui.js";
import { createIcons, icons } from "lucide";

/** Page shell. The controller in js/transfers/transfers.js renders into #transfers-root. */
export function TransfersPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div id="transfers-root">
            ${pageHeader({ title: "Transfers & warehouses", subtitle: "Move stock between warehouses, replenish bins and manage locations" })}
            <div class="text-sm text-slate-500">Loading…</div>
        </div>
    </main>
</div>`;
}

export function initializeTransfersIcons() {
    createIcons({ icons });
}
