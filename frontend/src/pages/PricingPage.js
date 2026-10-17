import { Sidebar } from "../components/Sidebar";
import { pageHeader } from "../shared/ui.js";
import { createIcons, icons } from "lucide";

/** Page shell. The controller in js/pricing/pricing.js renders into #pricing-root. */
export function PricingPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div id="pricing-root">
            ${pageHeader({ title: "Pricing & tax", subtitle: "Price lists, customer-group prices, volume tiers, tax rates and tax exemptions" })}
            <div class="text-sm text-slate-500">Loading…</div>
        </div>
    </main>
</div>`;
}

export function initializePricingIcons() {
    createIcons({ icons });
}
