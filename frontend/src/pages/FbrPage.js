import { Sidebar } from "../components/Sidebar";
import { pageHeader } from "../shared/ui.js";

/** Page shell. The controller in js/fbr/fbr.js renders into #fbr-root. */
export function FbrPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div id="fbr-root">
            ${pageHeader({ title: "FBR / Fiscal", subtitle: "Retail fiscalization setup, invoice history and FBR submissions" })}
            <div class="text-sm text-slate-500">Loading…</div>
        </div>
    </main>
</div>`;
}
