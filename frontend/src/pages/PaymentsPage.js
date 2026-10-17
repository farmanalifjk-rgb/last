import { Sidebar } from "../components/Sidebar";
import { pageHeader } from "../shared/ui.js";
import { createIcons, icons } from "lucide";

/** Page shell. The controller in js/payments/payments.js renders into #payments-root. */
export function PaymentsPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div id="payments-root">
            ${pageHeader({ title: "Payments & credit", subtitle: "Gift cards, store credit, tender register, cash reconciliation and refund credit" })}
            <div class="text-sm text-slate-500">Loading…</div>
        </div>
    </main>
</div>`;
}

export function initializePaymentsIcons() {
    createIcons({ icons });
}
