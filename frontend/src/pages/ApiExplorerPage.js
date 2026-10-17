import { Sidebar } from "../components/Sidebar";
import { pageHeader } from "../shared/ui.js";
import { createIcons, icons } from "lucide";

/** Page shell. The explorer in js/api-map/explorer.js renders into #api-explorer-root. */
export function ApiExplorerPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        ${pageHeader({ title: "API explorer", subtitle: "Every backend operation, grouped by domain. Use a section to call it with a form generated from the API schema." })}
        <div id="api-explorer-root" class="mt-6">
            <div class="text-sm text-slate-500">Loading…</div>
        </div>
    </main>
</div>`;
}

export function initializeApiExplorerIcons() {
    createIcons({ icons });
}
