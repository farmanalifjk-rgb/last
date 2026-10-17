import { createIcons, icons } from "lucide";
import { getRoles, getGovernancePermissions, createRole, updateRole, deleteRole } from "../js/inventory/services/inventory-api";
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

let availablePermissions = [];

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
    try {
        await loadPermissions();
        await loadRoles();
    } catch (error) {
        console.error("Error initializing tenant role governance", error);
        const container = document.getElementById("roles-table");
        if (container) container.innerHTML = loadErrorHtml(error, "role permissions");
    }
    initializeRolesEvents();
};

async function loadPermissions() {
    const response = await getGovernancePermissions();
    availablePermissions = Array.isArray(response) ? response : (response.results || []);
    renderPermissionsChecklist();
}

function renderPermissionsChecklist() {
    const container = document.getElementById("permissions-container");
    if (!container) return;

    const modules = new Map();
    availablePermissions.forEach((permission) => {
        const key = permission.module_key || `module-${permission.module}`;
        if (!modules.has(key)) modules.set(key, []);
        modules.get(key).push(permission);
    });

    container.innerHTML = Array.from(modules.entries()).map(([key, permissions]) => {
        const label = key.replace(/[-_]/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
        return `
        <div class="bg-slate-50/50 rounded-2xl p-5 border border-slate-100">
            <h4 class="font-semibold text-slate-800 mb-3">${escapeHtml(label)}</h4>
            <div class="flex flex-wrap gap-6">
                ${permissions.map((permission) => `
                    <label class="flex items-center gap-2 cursor-pointer group">
                        <input type="checkbox" id="perm-${Number(permission.id)}" data-permission-id="${Number(permission.id)}" data-sensitive="${Boolean(permission.is_sensitive)}" class="w-4 h-4 rounded text-purple-600 focus:ring-purple-500 border-gray-300">
                        <span class="text-sm font-medium text-slate-600 group-hover:text-slate-900">${escapeHtml(permission.action)}${permission.is_sensitive ? " · sensitive" : ""}</span>
                    </label>
                `).join("")}
            </div>
        </div>`;
    }).join("");
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
                        const permCount = Array.isArray(role.permissions) ? role.permissions.length : 0;
                        return `
                        <tr class="group hover:bg-purple-50/40 transition-colors ${role.is_system ? "" : "cursor-pointer"}" onclick="${role.is_system ? "" : `openEditRoleModalById(${Number(role.id)})`}">
                            <td class="px-6 py-4">
                                <div class="font-bold text-slate-900">${escapeHtml(role.label || role.name || role.key)}</div>
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
                                    ${role.is_system ? "" : `
                                    <button onclick="openEditRoleModalById(${Number(role.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-purple-600 hover:bg-purple-50 flex items-center justify-center transition" aria-label="Edit role">
                                        <i data-lucide="edit-2" class="w-4 h-4"></i>
                                    </button>
                                    <button onclick="deleteRole(${Number(role.id)})" class="w-8 h-8 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center transition" aria-label="Deactivate role">
                                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                                    </button>`}
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

window.openCreateRoleModal = function() {
    document.getElementById("role-id").value = "";
    document.getElementById("role-form").reset();
    document.getElementById("role-modal-title").textContent = "Add Role";
    
    document.querySelectorAll("input[data-permission-id]").forEach(cb => cb.checked = false);
    
    const modal = document.getElementById("role-form-modal");
    const content = document.getElementById("role-modal-content");
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    setTimeout(() => content.classList.remove("scale-95"), 10);
};

window.openEditRoleModal = function(role) {
    document.getElementById("role-id").value = role.id;
    document.getElementById("role-name").value = role.label || role.name || "";
    document.getElementById("role-description").value = role.description || "";
    
    document.getElementById("role-modal-title").textContent = "Edit Role";
    
    document.querySelectorAll("input[data-permission-id]").forEach(cb => cb.checked = false);
    if (Array.isArray(role.permissions)) {
        role.permissions.forEach((permission) => {
            const cb = document.getElementById(`perm-${Number(permission.id)}`);
            if (cb) cb.checked = true;
        });
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
    const label = document.getElementById("role-name").value.trim();
    const description = document.getElementById("role-description").value.trim();
    const checked = Array.from(document.querySelectorAll("input[data-permission-id]:checked"));
    const permissionIds = checked
        .map((checkbox) => Number(checkbox.dataset.permissionId))
        .filter((permissionId) => Number.isInteger(permissionId) && permissionId > 0);
    const hasSensitive = checked.some((checkbox) => checkbox.dataset.sensitive === "true");

    if (!label) {
        toast("Role name is required.", "error");
        return;
    }
    if (hasSensitive && !window.confirm("This role includes sensitive permissions. Confirm that these permissions are required.")) {
        return;
    }

    const data = {
        label,
        description,
        permission_ids: permissionIds,
        confirm_sensitive: hasSensitive
    };
    if (!id) {
        data.key = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    }

    try {
        if (id) await updateRole(id, data);
        else await createRole(data);
        closeRoleModal();
        await loadRoles();
    } catch (error) {
        console.error("Error saving role", error);
        toast(errorMessage(error, "Failed to save role."), "error");
    }
}

window.deleteRole = async function(id) {
    if (await confirmDialog({ title: "Deactivate role", message: "This role will be deactivated for this tenant. Continue?", confirmLabel: "Deactivate" })) {
        try {
            await deleteRole(id);
            await loadRoles();
        } catch (error) {
            console.error("Error deleting role", error);
            toast(errorMessage(error, "Failed to delete role."), "error");
        }
    }
};
