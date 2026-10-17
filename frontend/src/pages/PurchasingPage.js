import { Sidebar } from "../components/Sidebar";
import { pageHeader } from "../shared/ui.js";
import { createIcons, icons } from "lucide";

/** Page shell. The controller in js/purchasing/purchasing.js renders into #purchasing-root. */
export function PurchasingPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div id="purchasing-root">
            ${pageHeader({ title: "Purchasing", subtitle: "Suppliers, purchase orders, goods receipts and returns" })}
            <div class="text-sm text-slate-500">Loading…</div>
        </div>
    </main>
</div>`;
}

export function initializePurchasingIcons() {
    createIcons({ icons });
}
