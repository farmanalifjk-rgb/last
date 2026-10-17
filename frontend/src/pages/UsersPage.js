import { Sidebar } from "../components/Sidebar";
import { UsersCards, UsersToolbar } from "../js/Users";
import { createIcons, icons } from "lucide";

export function UsersPage() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Users</h1>
                <p class="text-gray-500 mt-1">Manage system access and roles</p>
            </div>
            <button onclick="openCreateUserModal()" class="h-11 px-6 rounded-xl bg-sky-600 text-white font-semibold hover:bg-sky-700 transition shadow-sm hover:shadow-md flex items-center gap-2">
                <i data-lucide="plus" class="w-4 h-4"></i>
                <span>Add User</span>
            </button>
        </div>
        
        ${UsersCards()}
        
        <div class="premium-surface rounded-3xl p-6">
            ${UsersToolbar()}
            <div id="users-table"></div>
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
        
        <!-- User Modal -->
        <div id="user-form-modal" class="hidden fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 items-center justify-center p-8">
            <div class="bg-white rounded-3xl w-full max-w-2xl shadow-2xl overflow-hidden transform scale-95 transition-transform duration-200" id="user-modal-content">
                <div class="flex items-center justify-between px-8 py-6 border-b border-slate-100">
                    <h2 id="user-modal-title" class="text-2xl font-bold text-slate-800">Add User</h2>
                    <button onclick="closeUserModal()" class="w-10 h-10 rounded-xl hover:bg-slate-100 text-slate-500 flex items-center justify-center transition">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <form id="user-form" class="p-8 space-y-5">
                    <input type="hidden" id="user-id">
                    
                    <div class="grid grid-cols-2 gap-6">
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">First Name</label>
                            <input id="user-first-name" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="John">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Last Name</label>
                            <input id="user-last-name" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="Doe">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Username</label>
                            <input id="user-username" type="text" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="johndoe">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Email</label>
                            <input id="user-email" type="email" required class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="john@example.com">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Password</label>
                            <input id="user-password" type="password" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="Leave blank to keep current">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-700 mb-1">Phone</label>
                            <input id="user-phone" type="text" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200" placeholder="+123456789">
                        </div>
                        <div class="col-span-2">
                            <label class="block text-sm font-medium text-slate-700 mb-1">Role</label>
                            <select id="user-role" class="premium-input w-full h-11 px-4 rounded-xl border-slate-200 bg-white">
                                <!-- Roles populated dynamically -->
                            </select>
                        </div>
                        
                        <div class="col-span-2 flex gap-8 pt-2">
                            <label class="flex items-center gap-3 cursor-pointer">
                                <div class="relative">
                                    <input type="checkbox" id="user-is-active" class="sr-only peer" checked>
                                    <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-sky-500"></div>
                                </div>
                                <span class="text-sm font-medium text-slate-700">Active Account</span>
                            </label>
                            <label class="flex items-center gap-3 cursor-pointer">
                                <div class="relative">
                                    <input type="checkbox" id="user-is-staff" class="sr-only peer">
                                    <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-500"></div>
                                </div>
                                <span class="text-sm font-medium text-slate-700">Staff Status</span>
                            </label>
                        </div>
                    </div>
                    
                    <div class="flex justify-end gap-3 pt-6 mt-6 border-t border-slate-100">
                        <button type="button" onclick="closeUserModal()" class="h-11 px-6 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition">Cancel</button>
                        <button type="submit" class="h-11 px-8 rounded-xl bg-sky-600 text-white text-sm font-semibold hover:bg-sky-700 transition shadow-sm hover:shadow-md">Save User</button>
                    </div>
                </form>
            </div>
        </div>
    </main>
</div>
    `;
}
