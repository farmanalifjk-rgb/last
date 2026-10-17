import { Sidebar } from "../components/Sidebar";
import { pageHeader, primaryButton } from "../shared/ui.js";
import { createIcons, icons } from "lucide";

/** Page shell. The controller in js/customers/customers.js renders list and detail views into #customers-root. */
export function CustomersPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div id="customers-root">
            ${pageHeader({
                title: "Customers",
                subtitle: "Customer records, credit limits, loyalty and history",
                actions: `<button type="button" data-action="groups" class="h-11 rounded-xl border border-slate-200 bg-white px-5 text-sm font-semibold text-slate-700 hover:bg-slate-50">Customer groups</button>${primaryButton("New customer", "create")}`,
            })}
            <div class="text-sm text-slate-500">Loading customers…</div>
        </div>
    </main>
</div>`;
}

export function initializeCustomersIcons() {
    createIcons({ icons });
}
