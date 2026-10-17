import { Sidebar } from "../components/Sidebar";
import { RolesCards, RolesToolbar } from "../js/Roles";
import { createIcons, icons } from "lucide";

export function RolesPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Roles & Permissions</h1>
                <p class="text-gray-500 mt-1">Define access levels and system permissions</p>
            </div>
            <button onclick="openCreateRoleModal()" class="h-11 px-6 rounded-xl bg-purple-600 text-white font-semibold hover:bg-purple-700 transition shadow-sm hover:shadow-md flex items-center gap-2">
                <i data-lucide="shield-plus" class="w-4 h-4"></i>
                <span>Add Role</span>
            </button>
        </div>
        
        ${RolesCards()}
        
        <div class="premium-surface rounded-3xl p-6">
            ${RolesToolbar()}
            <div id="roles-table"></div>
        </div>
        
        <div class="flex items-center justify-between px-6 py-4 border-t border-gray-100 bg-white rounded-b-3xl mt-[-24px] relative z-0">
            <p id="pagination-info" class="text-sm text-gray-500"></p>
            <div class="flex items-center gap-2">
                <button id="prev-page" class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent transition" disabled>
                    <i data-lucide="chevron-left" class="w-4 h-4"></i>
                </button>
                <div id="pagination-numbers" class="text-sm text-gray-600 font-medium">
                    <span class="px-3 py-1 bg-gray-50 rounded-lg border border-gray-200">Page 1 of 1</span>
                </div>
                <button id="next-page" class="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-900 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent transition" disabled>
                    <i data-lucide="chevron-right" class="w-4 h-4"></i>
                </button>
            </div>
        </div>
        
        <!-- Role Modal -->
        <div id="role-form-modal" class="hidden fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 items-center justify-center p-8">
            <div class="bg-white rounded-3xl w-full max-w-4xl shadow-2xl overflow-hidden transform scale-95 transition-transform duration-200 flex flex-col max-h-[90vh]" id="role-modal-content">
                <div class="flex items-center justify-between px-8 py-6 border-b border-slate-100 flex-shrink-0">
                    <h2 id="role-modal-title" class="text-2xl font-bold text-slate-800">Add Role</h2>
                    <button onclick="closeRoleModal()" class="w-10 h-10 rounded-xl hover:bg-slate-100 text-slate-500 flex items-center justify-center transition">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <form id="role-form" class="flex flex-col flex-1 overflow-hidden">
                    <div class="p-8 overflow-y-auto space-y-8 flex-1">
                        <input type="hidden" id="role-id">
                        
                        <div class="grid grid-cols-2 gap-6">
                            <div class="col-span-2 md:col-span-1">
                                <label class="block text-sm font-medium text-slate-700 mb-1">Role Name</label>
                                <input id="role-name" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="e.g. Store Manager">
                            </div>
                            <div class="col-span-2 md:col-span-1 flex items-center mt-6">
                                <label class="flex items-center gap-3 cursor-pointer">
                                    <div class="relative">
                                        <input type="checkbox" id="role-is-active" class="sr-only peer" checked>
                                        <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-500"></div>
                                    </div>
                                    <span class="text-sm font-medium text-slate-700">Active Role</span>
                                </label>
                            </div>
                            <div class="col-span-2">
                                <label class="block text-sm font-medium text-slate-700 mb-1">Description</label>
                                <textarea id="role-description" rows="2" class="premium-input w-full p-4 rounded-xl border-slate-200" placeholder="Briefly describe what this role can do..."></textarea>
                            </div>
                        </div>
                        
                        <div>
                            <h3 class="text-lg font-semibold text-slate-800 mb-4 pb-2 border-b border-slate-100">Permissions Checklist</h3>
                            <div class="space-y-6" id="permissions-container">
                                <!-- Permissions generated via JS -->
                            </div>
                        </div>
                    </div>
                    
                    <div class="flex justify-end gap-3 px-8 py-5 border-t border-slate-100 bg-slate-50 flex-shrink-0">
                        <button type="button" onclick="closeRoleModal()" class="h-11 px-6 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-100 bg-white transition">Cancel</button>
                        <button type="submit" class="h-11 px-8 rounded-xl bg-purple-600 text-white text-sm font-semibold hover:bg-purple-700 transition shadow-sm hover:shadow-md">Save Role</button>
                    </div>
                </form>
            </div>
        </div>
    </main>
</div>
    `;
}
