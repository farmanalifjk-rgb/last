import { createIcons, icons } from "lucide";
import { getUsers, createUser, updateUser, deleteUser2, getRoles } from "../js/inventory/services/inventory-api";
import { Pagination } from "../shared/Pagination";
import { escapeHtml, loadErrorHtml } from "../shared/format.js";
import { toast, errorMessage, confirmDialog } from "../shared/ui.js";

// Rows from the last render, keyed by id: inline handlers carry only numeric ids, never serialized API data.
let usersById = new Map();
window.openEditUserModalById = function(id) {
    const row = usersById.get(Number(id));
    if (row) window.openEditUserModal(row);
};

let filters = { search: "", page: 1, page_size: 10 };
let currentRoles = [];

export function UsersCard({ title, value, valueId, icon, gradient, accent, iconColor, subtitle }) {
    return `<div class="relative overflow-hidden rounded-3xl ${gradient} border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
        <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full ${accent} opacity-20 blur-3xl"></div>
        <i data-lucide="${icon}" class="absolute right-5 top-5 h-20 w-20 opacity-10 ${iconColor}"></i>
        <div class="relative">
            <p class="text-sm font-semibold text-slate-600">${title}</p>
            <h2 id="${valueId}" class="mt-3 text-4xl font-black tracking-tight text-slate-900">${value}</h2>
            <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full ${accent}"></div></div></div>
            <p class="mt-4 text-sm font-medium text-slate-600">${subtitle}</p>
        </div>
    </div>`;
}

export function UsersCards() {
    return `<div class="grid grid-cols-4 gap-6 mb-8">
        ${UsersCard({ title: "Total Users", value: "-", valueId: "stat-users-total", icon: "users", gradient: "bg-gradient-to-br from-sky-50 to-white", accent: "bg-sky-500", iconColor: "text-sky-600", subtitle: "All registered accounts" })}
        ${UsersCard({ title: "Active Users", value: "-", valueId: "stat-users-active", icon: "user-check", gradient: "bg-gradient-to-br from-emerald-50 to-white", accent: "bg-emerald-500", iconColor: "text-emerald-600", subtitle: "Currently active" })}
        ${UsersCard({ title: "Admins", value: "-", valueId: "stat-users-admins", icon: "shield", gradient: "bg-gradient-to-br from-indigo-50 to-white", accent: "bg-indigo-500", iconColor: "text-indigo-600", subtitle: "System administrators" })}
        ${UsersCard({ title: "Inactive", value: "-", valueId: "stat-users-inactive", icon: "user-x", gradient: "bg-gradient-to-br from-rose-50 to-white", accent: "bg-rose-500", iconColor: "text-rose-600", subtitle: "Disabled accounts" })}
    </div>`;
}

export function UsersToolbar() {
    return `<div class="flex items-center justify-between gap-4 mb-6">
        <div class="flex items-center gap-3">
            <div class="relative">
                <i data-lucide="search" class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"></i>
                <input id="users-search" type="text" placeholder="Search users..." class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl border-slate-200">
            </div>
            <button onclick="refreshUsers()" class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition text-slate-500 flex items-center justify-center">
                <i data-lucide="refresh-cw" class="w-5 h-5"></i>
            </button>
        </div>
    </div>`;
}

const pagination = new Pagination({
    prevButtonId: "prev-page",
    nextButtonId: "next-page",
    containerId: "pagination-numbers",
    pageSize: filters.page_size,
    onPageChange: async (page) => { filters.page = page; await loadUsers(); }
});

window.initializeUsers = async function() {
    pagination.initialize();
    await loadRolesDropdown();
    await loadUsers();
    initializeUsersEvents();
};

async function loadRolesDropdown() {
    try {
        const response = await getRoles({ page_size: 100 });
        currentRoles = response.results || [];
        const select = document.getElementById("user-role");
        if (select) {
            select.innerHTML = `<option value="">Select Role</option>` + 
                currentRoles.map(r => `<option value="${escapeHtml(r.id)}">${escapeHtml(r.name)}</option>`).join("");
        }
    } catch (e) { console.error("Error loading roles", e); }
}

async function loadUsers() {
    try {
        const response = await getUsers(filters);
        renderUsersTable(response.results);
        updateStats(response);
        pagination.updateFromResponse(response);
        createIcons({ icons });
    } catch (e) {
        console.error("Error loading users", e);
        const container = document.getElementById("users-table");
        if (container) container.innerHTML = loadErrorHtml(e, "users");
    }
}

function updateStats(response) {
    const total = response.count || 0;
    const active = response.results?.filter(u => u.is_active).length || 0;
    const admins = response.results?.filter(u => u.is_staff || (u.role && u.role.name === 'Admin')).length || 0;
    
    document.getElementById("stat-users-total").textContent = total;
    document.getElementById("stat-users-active").textContent = active; 
    document.getElementById("stat-users-admins").textContent = admins;
    document.getElementById("stat-users-inactive").textContent = total - active;
}

function initializeUsersEvents() {
    const search = document.getElementById("users-search");
    if (search) {
        search.addEventListener("input", debounce(async (e) => {
            filters.search = e.target.value; filters.page = 1; pagination.reset(); await loadUsers();
        }, 400));
    }

    const form = document.getElementById("user-form");
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await saveUser();
        });
    }
}

window.refreshUsers = async function() {
    filters = { search: "", page: 1, page_size: 10 };
    document.getElementById("users-search").value = "";
    pagination.reset();
    await loadUsers();
};

function debounce(callback, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); };
}

function renderUsersTable(rows) {
    usersById = new Map(rows.map((row) => [Number(row.id), row]));
    if (!rows || rows.length === 0) {
        document.getElementById("users-table").innerHTML = `<div class="text-center py-12 text-slate-500">No users found.</div>`;
        return;
    }

    const html = `
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <table class="w-full text-left text-sm whitespace-nowrap">
                <thead class="bg-slate-50 text-slate-600 font-medium border-b border-slate-200">
                    <tr>
                        <th class="px-6 py-4">User</th>
                        <th class="px-6 py-4">Role</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4">Created</th>
                        <th class="px-6 py-4 text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${rows.map(user => `
                        <tr class="group hover:bg-sky-50/40 transition-colors">
                            <td class="px-6 py-4">
                                <div class="flex items-center gap-3">
                                    <div class="w-10 h-10 rounded-full bg-sky-100 text-sky-700 flex items-center justify-center font-bold">
                                        ${escapeHtml(user.first_name?.[0] || user.username?.[0] || '?')}
                                    </div>
                                    <div>
                                        <div class="font-medium text-slate-900">${escapeHtml(user.first_name)} ${escapeHtml(user.last_name)}</div>
                                        <div class="text-slate-500 text-xs">${escapeHtml(user.email || user.username)}</div>
                                    </div>
                                </div>
                            </td>
                            <td class="px-6 py-4">
                                <span class="text-slate-700 font-medium">${escapeHtml(user.role?.name || 'No Role')}</span>
                                ${user.is_staff ? `<span class="ml-2 inline-flex px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-100 text-indigo-700 uppercase tracking-wider">Staff</span>` : ''}
                            </td>
                            <td class="px-6 py-4">
                                ${user.is_active 
                                    ? `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">Active</span>` 
                                    : `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">Inactive</span>`}
                            </td>
                            <td class="px-6 py-4 text-slate-500">
                                ${escapeHtml(new Date(user.created_at || Date.now()).toLocaleDateString())}
                            </td>
                            <td class="px-6 py-4 text-right">
                                <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button onclick="openEditUserModalById(${Number(user.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-sky-600 hover:bg-sky-50 flex items-center justify-center transition">
                                        <i data-lucide="edit-2" class="w-4 h-4"></i>
                                    </button>
                                    <button onclick="deleteUser(${Number(user.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center transition">
                                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                                        </button>
                                </div>
                            </td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
    
    document.getElementById("users-table").innerHTML = html;
}

window.openCreateUserModal = function() {
    document.getElementById("user-id").value = "";
    document.getElementById("user-form").reset();
    document.getElementById("user-is-active").checked = true;
    document.getElementById("user-password").required = true;
    document.getElementById("user-modal-title").textContent = "Add User";
    
    const modal = document.getElementById("user-form-modal");
    const content = document.getElementById("user-modal-content");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    setTimeout(() => content.classList.remove("scale-95"), 10);
};

window.openEditUserModal = function(user) {
    document.getElementById("user-id").value = user.id;
    document.getElementById("user-first-name").value = user.first_name || "";
    document.getElementById("user-last-name").value = user.last_name || "";
    document.getElementById("user-username").value = user.username || "";
    document.getElementById("user-email").value = user.email || "";
    document.getElementById("user-phone").value = user.phone || "";
    
    if (user.role) {
        const roleId = typeof user.role === 'object' ? user.role.id : user.role;
        document.getElementById("user-role").value = roleId || "";
    } else {
        document.getElementById("user-role").value = "";
    }
    
    document.getElementById("user-is-active").checked = user.is_active;
    document.getElementById("user-is-staff").checked = user.is_staff;
    
    document.getElementById("user-password").value = "";
    document.getElementById("user-password").required = false;
    document.getElementById("user-modal-title").textContent = "Edit User";
    
    const modal = document.getElementById("user-form-modal");
    const content = document.getElementById("user-modal-content");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    setTimeout(() => content.classList.remove("scale-95"), 10);
};

window.closeUserModal = function() {
    const modal = document.getElementById("user-form-modal");
    const content = document.getElementById("user-modal-content");
    content.classList.add("scale-95");
    setTimeout(() => {
        modal.classList.add("hidden");
        modal.classList.remove("flex");
    }, 200);
};

async function saveUser() {
    const id = document.getElementById("user-id").value;
    const data = {
        first_name: document.getElementById("user-first-name").value,
        last_name: document.getElementById("user-last-name").value,
        username: document.getElementById("user-username").value,
        email: document.getElementById("user-email").value,
        phone: document.getElementById("user-phone").value,
        role_id: document.getElementById("user-role").value || null,
        is_active: document.getElementById("user-is-active").checked,
        is_staff: document.getElementById("user-is-staff").checked,
    };
    
    const pwd = document.getElementById("user-password").value;
    if (pwd) data.password = pwd;

    try {
        if (id) {
            await updateUser(id, data);
        } else {
            await createUser(data);
        }
        closeUserModal();
        await loadUsers();
    } catch (error) {
        console.error("Error saving user", error);
        toast(errorMessage(error, "Failed to save user."), "error");
    }
}

window.deleteUser = async function(id) {
    if (await confirmDialog({ title: "Delete user", message: "Are you sure you want to delete this user? This action cannot be undone.", confirmLabel: "Delete" })) {
        try {
            await deleteUser2(id);
            await loadUsers();
        } catch (error) {
            console.error("Error deleting user", error);
            toast(errorMessage(error, "Failed to delete user."), "error");
        }
    }
};
