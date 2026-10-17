import { Sidebar } from "../components/Sidebar";
import { escapeHtml } from "../shared/format.js";

/**
 * Shown when a signed-in user opens a screen their role does not include.
 * This is a courtesy, not the security boundary: the backend refuses the
 * underlying API calls regardless (RBAC per endpoint).
 */
export function RestrictedPage({ title = "Not available", message = "Your role does not include this screen. Ask the business owner or an admin if you need access." } = {}) {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="mx-auto mt-16 max-w-lg rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm" role="alert">
            <h1 class="text-lg font-bold text-slate-900">${escapeHtml(title)}</h1>
            <p class="mt-2 text-sm text-slate-600">${escapeHtml(message)}</p>
            <a href="#/dashboard" class="mt-5 inline-flex rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700">Back to dashboard</a>
        </div>
    </main>
</div>`;
}
