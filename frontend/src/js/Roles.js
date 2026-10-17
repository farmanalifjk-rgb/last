import { createIcons, icons } from "lucide";
import { getRoles, createRole, updateRole, deleteRole } from "../js/inventory/services/inventory-api";
import { Pagination } from "../shared/Pagination";
import { escapeHtml, loadErrorHtml } from "../shared/format.js";
import { toast, errorMessage, confirmDialog } from "../shared/ui.js";

// Rows from the last render, keyed by id: inline handlers carry only numeric ids, never serialized API data.
let rolesById = new Map();
window.openEditRoleModalById = function(id) {
    const row = rolesById.get(Number(id));
    if (row) window.openEditRoleModal(row);
};

let filters = { search: "", page: 1, page_size: 10 };

const PERMISSION_MODULES = {
    products: { label: "Products Catalog", actions: ["view", "create", "edit", "delete"] },
    orders: { label: "Sales & Orders", actions: ["view", "create", "edit"] },
    inventory: { label: "Inventory Management", actions: ["view", "edit"] },
    reports: { label: "Analytics & Reports", actions: ["view"] },
    configuration: { label: "System Configuration", actions: ["view", "edit"] }
};

export function RolesCard({ title, value, valueId, icon, gradient, accent, iconColor, subtitle }) {
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

export function RolesCards() {
    return `<div class="grid grid-cols-2 gap-6 mb-8">
        ${RolesCard({ title: "Total Roles", value: "-", valueId: "stat-roles-total", icon: "shield", gradient: "bg-gradient-to-br from-purple-50 to-white", accent: "bg-purple-500", iconColor: "text-purple-600", subtitle: "Defined security roles" })}
        ${RolesCard({ title: "Active Roles", value: "-", valueId: "stat-roles-active", icon: "shield-check", gradient: "bg-gradient-to-br from-indigo-50 to-white", accent: "bg-indigo-500", iconColor: "text-indigo-600", subtitle: "Currently in use" })}
    </div>`;
}

export function RolesToolbar() {
    return `<div class="flex items-center justify-between gap-4 mb-6">
        <div class="flex items-center gap-3">
            <div class="relative">
                <i data-lucide="search" class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"></i>
                <input id="roles-search" type="text" placeholder="Search roles..." class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl border-slate-200">
            </div>
            <button onclick="refreshRoles()" class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition text-slate-500 flex items-center justify-center">
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
    onPageChange: async (page) => { filters.page = page; await loadRoles(); }
});

window.initializeRoles = async function() {
    pagination.initialize();
    renderPermissionsChecklist();
    await loadRoles();
    initializeRolesEvents();
};

function renderPermissionsChecklist() {
    const container = document.getElementById("permissions-container");
    if (!container) return;
    
    let html = "";
    Object.entries(PERMISSION_MODULES).forEach(([key, mod]) => {
        html += `
        <div class="bg-slate-50/50 rounded-2xl p-5 border border-slate-100">
            <h4 class="font-semibold text-slate-800 mb-3">${escapeHtml(mod.label)}</h4>
            <div class="flex flex-wrap gap-6">
                ${mod.actions.map(action => `
                    <label class="flex items-center gap-2 cursor-pointer group">
                        <input type="checkbox" id="perm-${key}-${action}" class="w-4 h-4 rounded text-purple-600 focus:ring-purple-500 border-gray-300">
                        <span class="text-sm font-medium text-slate-600 group-hover:text-slate-900 capitalize">${action}</span>
                    </label>
                `).join('')}
            </div>
        </div>`;
    });
    container.innerHTML = html;
}

async function loadRoles() {
    try {
        const response = await getRoles(filters);
        renderRolesTable(response.results);
        updateStats(response);
        pagination.updateFromResponse(response);
        createIcons({ icons });
    } catch (e) {
        console.error("Error loading roles", e);
        const container = document.getElementById("roles-table");
        if (container) container.innerHTML = loadErrorHtml(e, "roles");
    }
}

function updateStats(response) {
    const total = response.count || 0;
    const active = response.results?.filter(r => r.is_active).length || 0;
    
    document.getElementById("stat-roles-total").textContent = total;
    document.getElementById("stat-roles-active").textContent = active;
}

function initializeRolesEvents() {
    const search = document.getElementById("roles-search");
    if (search) {
        search.addEventListener("input", debounce(async (e) => {
            filters.search = e.target.value; filters.page = 1; pagination.reset(); await loadRoles();
        }, 400));
    }

    const form = document.getElementById("role-form");
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await saveRole();
        });
    }
}

window.refreshRoles = async function() {
    filters = { search: "", page: 1, page_size: 10 };
    document.getElementById("roles-search").value = "";
    pagination.reset();
    await loadRoles();
};

function debounce(callback, delay = 300) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); };
}

function renderRolesTable(rows) {
    rolesById = new Map(rows.map((row) => [Number(row.id), row]));
    if (!rows || rows.length === 0) {
        document.getElementById("roles-table").innerHTML = `<div class="text-center py-12 text-slate-500">No roles found.</div>`;
        return;
    }

    const html = `
        <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <table class="w-full text-left text-sm whitespace-nowrap">
                <thead class="bg-slate-50 text-slate-600 font-medium border-b border-slate-200">
                    <tr>
                        <th class="px-6 py-4">Role Name</th>
                        <th class="px-6 py-4">Description</th>
                        <th class="px-6 py-4">Permissions</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4 text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    ${rows.map(role => {
                        const permCount = role.permissions ? countPermissions(role.permissions) : 0;
                        return `
                        <tr class="group hover:bg-purple-50/40 transition-colors cursor-pointer" onclick="openEditRoleModalById(${Number(role.id)})">
                            <td class="px-6 py-4">
                                <div class="font-bold text-slate-900">${escapeHtml(role.name)}</div>
                                <div class="text-slate-400 text-xs mt-1">${escapeHtml(role.users_count || 0)} users assigned</div>
                            </td>
                            <td class="px-6 py-4 text-slate-500 truncate max-w-xs">
                                ${escapeHtml(role.description || '-')}
                            </td>
                            <td class="px-6 py-4">
                                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-purple-50 text-purple-700 border border-purple-100">
                                    <i data-lucide="key" class="w-3 h-3"></i> ${permCount} Rules
                                </span>
                            </td>
                            <td class="px-6 py-4">
                                ${role.is_active 
                                    ? `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">Active</span>` 
                                    : `<span class="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">Inactive</span>`}
                            </td>
                            <td class="px-6 py-4 text-right" onclick="event.stopPropagation()">
                                <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button onclick="openEditRoleModalById(${Number(role.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-purple-600 hover:bg-purple-50 flex items-center justify-center transition">
                                        <i data-lucide="edit-2" class="w-4 h-4"></i>
                                    </button>
                                    <button onclick="deleteRole(${Number(role.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center transition">
                                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `}).join("")}
                </tbody>
            </table>
        </div>
    `;
    
    document.getElementById("roles-table").innerHTML = html;
}

function countPermissions(permsObj) {
    let count = 0;
    try {
        const p = typeof permsObj === 'string' ? JSON.parse(permsObj) : permsObj;
        Object.values(p).forEach(module => {
            if(module && typeof module === 'object') {
                Object.values(module).forEach(val => { if(val) count++; });
            }
        });
    } catch(e){}
    return count;
}

window.openCreateRoleModal = function() {
    document.getElementById("role-id").value = "";
    document.getElementById("role-form").reset();
    document.getElementById("role-is-active").checked = true;
    document.getElementById("role-modal-title").textContent = "Add Role";
    
    document.querySelectorAll("input[type='checkbox'][id^='perm-']").forEach(cb => cb.checked = false);
    
    const modal = document.getElementById("role-form-modal");
    const content = document.getElementById("role-modal-content");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    setTimeout(() => content.classList.remove("scale-95"), 10);
};

window.openEditRoleModal = function(role) {
    document.getElementById("role-id").value = role.id;
    document.getElementById("role-name").value = role.name || "";
    document.getElementById("role-description").value = role.description || "";
    document.getElementById("role-is-active").checked = role.is_active;
    
    document.getElementById("role-modal-title").textContent = "Edit Role";
    
    document.querySelectorAll("input[type='checkbox'][id^='perm-']").forEach(cb => cb.checked = false);
    if (role.permissions) {
        try {
            const p = typeof role.permissions === 'string' ? JSON.parse(role.permissions) : role.permissions;
            Object.keys(p).forEach(moduleKey => {
                const actions = p[moduleKey];
                if (actions && typeof actions === 'object') {
                    Object.keys(actions).forEach(actionKey => {
                        if (actions[actionKey]) {
                            const cb = document.getElementById(`perm-${moduleKey}-${actionKey}`);
                            if (cb) cb.checked = true;
                        }
                    });
                }
            });
        } catch(e) {}
    }
    
    const modal = document.getElementById("role-form-modal");
    const content = document.getElementById("role-modal-content");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    setTimeout(() => content.classList.remove("scale-95"), 10);
};

window.closeRoleModal = function() {
    const modal = document.getElementById("role-form-modal");
    const content = document.getElementById("role-modal-content");
    content.classList.add("scale-95");
    setTimeout(() => {
        modal.classList.add("hidden");
        modal.classList.remove("flex");
    }, 200);
};

async function saveRole() {
    const id = document.getElementById("role-id").value;
    
    const permissions = {};
    Object.keys(PERMISSION_MODULES).forEach(key => {
        permissions[key] = {};
        PERMISSION_MODULES[key].actions.forEach(action => {
            const cb = document.getElementById(`perm-${key}-${action}`);
            if(cb) permissions[key][action] = cb.checked;
        });
    });

    const data = {
        name: document.getElementById("role-name").value,
        description: document.getElementById("role-description").value,
        is_active: document.getElementById("role-is-active").checked,
        permissions: JSON.stringify(permissions)
    };

    try {
        if (id) {
            await updateRole(id, data);
        } else {
            await createRole(data);
        }
        closeRoleModal();
        await loadRoles();
    } catch (error) {
        console.error("Error saving role", error);
        toast(errorMessage(error, "Failed to save role."), "error");
    }
}

window.deleteRole = async function(id) {
    if (await confirmDialog({ title: "Delete role", message: "Are you sure you want to delete this role?", confirmLabel: "Delete" })) {
        try {
            await deleteRole(id);
            await loadRoles();
        } catch (error) {
            console.error("Error deleting role", error);
            toast(errorMessage(error, "Failed to delete role."), "error");
        }
    }
};
