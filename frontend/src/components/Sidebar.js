import { logout, getCachedUser, getCachedTenant, hasAnyPermission, isBusinessAdmin } from "../services/auth.js";
import { loadCompany, cachedCompany } from "../services/company.js";
import { listMyTenants, cachedTenants, currentTenant, switchTenant } from "../services/tenant.js";
import { escapeHtml, safeUrl } from "../shared/format.js";
import { isDarkMode, toggleDarkMode, applyTheme } from "../shared/theme.js";
import { openModal, field, readForm, toast, errorMessage } from "../shared/ui.js";
import { createIcons, icons as lucideIcons } from "lucide";

// The company profile (logo/name) is cached in services/company.js; staff who
// may not read it (403) fall back to the session's active business name.
async function refreshCompany({ force = false } = {}) {
  try {
    await loadCompany({ force });
  } catch (error) {
    console.error("Failed to load company profile:", error?.message || error);
  }
  refreshSidebar();
}

window.addEventListener("company:updated", () => {
  refreshCompany({ force: true });
});
window.addEventListener("pos:session-updated", () => refreshSidebar());

const icons = {
  logo: `<i data-lucide="refresh-cw" width="15" height="15" class="text-sidebar-bg" stroke-width="2.5"></i>`,
  collapse: `<i data-lucide="chevrons-left" width="16" height="16"></i>`,
  home: `<i data-lucide="home" width="18" height="18" stroke-width="1.8"></i>`,
  cart: `<i data-lucide="shopping-cart" width="18" height="18" stroke-width="1.8"></i>`,
  box: `<i data-lucide="package" width="18" height="18" stroke-width="1.8"></i>`,
  chart: `<i data-lucide="bar-chart-3" width="18" height="18" stroke-width="1.8"></i>`,
  gear: `<i data-lucide="settings" width="18" height="18" stroke-width="1.8"></i>`,
  chevron: `<i data-lucide="chevron-down" width="16" height="16"></i>`,
  dots: `<i data-lucide="more-vertical" width="18" height="18"></i>`,
  sun: `<i data-lucide="sun" width="18" height="18"></i>`,
  moon: `<i data-lucide="moon" width="18" height="18"></i>`,
  pos: `<i data-lucide="monitor-dot" width="18" height="18"></i>`,
  fiscal: `<i data-lucide="receipt-text" width="18" height="18"></i>`,

  inventory: `<i data-lucide="boxes" width="18" height="18"></i>`,
  dashboard: `<i data-lucide="layout-dashboard" width="18" height="18"></i>`,
  products: `<i data-lucide="package" width="18" height="18"></i>`,
  movements: `<i data-lucide="arrow-right-left" width="18" height="18"></i>`,
  adjustments: `<i data-lucide="sliders-horizontal" width="18" height="18"></i>`,
  valuation: `<i data-lucide="wallet" width="18" height="18"></i>`,
  reports: `<i data-lucide="file-text" width="18" height="18"></i>`,
  analytics: `<i data-lucide="chart-column" width="18" height="18"></i>`,
  users: `<i data-lucide="users" width="18" height="18"></i>`,
  truck: `<i data-lucide="truck" width="18" height="18"></i>`,
  transfer: `<i data-lucide="arrow-left-right" width="18" height="18"></i>`,
};

const navSections = [
{
  id: "orders",
  label: "Orders",
  icon: icons.cart,
  items: [
    {
      id: "orders-all",
      label: "All Orders",
      route: "#/orders?filter=all",
      icon: "list",
    },
    {
      id: "orders-completed",
      label: "Completed Orders",
      route: "#/orders?filter=completed",
      icon: "badge-check",
    },
    {
      id: "orders-refunds",
      label: "Refunds",
      route: "#/orders?filter=refunds",
      icon: "rotate-ccw",
    },
    {
      id: "orders-partial",
      label: "Partial Refunds",
      route: "#/orders?filter=partial-refunds",
      icon: "undo-2",
    },
    {
      id: "orders-draft",
      label: "Draft",
      route: "#/orders?filter=draft",
      icon: "file-text",
    },
  ],
},
{
  id: "inventory",
  label: "Inventory",
  icon: icons.inventory,

  items: [
    {
      id: "inventory-dashboard",
      label: "Dashboard",
      route: "#/inventory/dashboard",
      icon: "layout-dashboard",
    },
    {
      id: "inventory-products",
      label: "Products",
      route: "#/inventory/products",
      icon: "package",
    },
    {
      id: "inventory-movements",
      label: "Movements",
      route: "#/inventory/movements",
      icon: "arrow-right-left",
    },
    {
      id: "inventory-adjustments",
      label: "Adjustments",
      route: "#/inventory/adjustments",
      icon: "sliders-horizontal",
    },
    {
      id: "inventory-valuation",
      label: "Valuation",
      route: "#/inventory/valuation",
      icon: "wallet",
    },
    {
      id: "inventory-reports",
      label: "Reports",
      route: "#/inventory/reports",
      icon: "file-text",
    },
    {
      id: "inventory-analytics",
      label: "Analytics",
      route: "#/inventory/analytics",
      icon: "chart-column",
    },
  ],
},
{
  id: "products",
  label: "Products",
  icon: icons.box,

  items: [
    {
      label: "All Products",
      route: "#/products",
    },
    {
      label: "Categories",
      route: "#/categories",
    },
    {
      label: "Brands",
      route: "#/brands",
    },
    {
      label: "Variants",
      route: "#/variants",
    },
  ],
},
{
  id: "business",
  label: "Customers & Purchasing",
  icon: icons.users,
  items: [
    { label: "Customers", route: "#/customers" },
    { label: "Purchase Orders", route: "#/purchasing?tab=orders" },
    { label: "Goods Receipts", route: "#/purchasing?tab=receipts" },
    { label: "Returns to Supplier", route: "#/purchasing?tab=returns" },
    { label: "Suppliers", route: "#/purchasing?tab=suppliers" },
    { label: "Transfers", route: "#/transfers?tab=transfers" },
    { label: "Replenishment", route: "#/transfers?tab=replenishment" },
    { label: "Warehouses", route: "#/transfers?tab=warehouses" },
    { label: "Stock levels", route: "#/stock-control?tab=stock" },
    { label: "Reorder rules", route: "#/stock-control?tab=reorder" },
    { label: "Bin locations", route: "#/stock-control?tab=bins" },
    { label: "Cycle counts", route: "#/stock-control?tab=cycle-counts" },
    { label: "Reservations", route: "#/stock-control?tab=reservations" },
    { label: "Gift cards", route: "#/payments?tab=gift-cards" },
    { label: "Store credit", route: "#/payments?tab=store-credit" },
    { label: "Cash reconciliation", route: "#/payments?tab=reconciliations" },
    { label: "Price lists", route: "#/pricing?tab=price-lists" },
    { label: "Tax rates", route: "#/pricing?tab=tax-rates" },
  ],
},
  {
    id: "reporting",
    activeItem: "",
    label: "Reporting",
    icon: icons.chart,
    items: [
  {
    label: "Sales Report",
    route: "#/reports/sales",
  },
  {
    label: "Products Report",
    route: "#/reports/products",
  },
  {
    label: "Stock Report",
    route: "#/reports/stock",
  },
  {
    label: "Tax Report",
    route: "#/reports/tax",
  },
]
  },
  {
    id: "fbr",
    activeItem: "",
    label: "FBR / Fiscal",
    icon: icons.fiscal,
    // Shown to owners/admins (*.*) and roles with a fiscal permission; the
    // FBR endpoints enforce fiscal.view / fiscal.create / fiscal.manage.
    visible: () => hasAnyPermission(["fiscal.view", "fiscal.manage"]),
    items: [
      { id: "fbr-configuration", label: "Configuration", route: "#/fbr?tab=configuration" },
      { id: "fbr-profiles", label: "Product fiscal profiles", route: "#/fbr?tab=profiles" },
      { id: "fbr-sequences", label: "Invoice sequences", route: "#/fbr?tab=sequences" },
      { id: "fbr-invoices", label: "Fiscal invoices", route: "#/fbr?tab=invoices" },
      { id: "fbr-submissions", label: "Submissions", route: "#/fbr?tab=submissions" },
    ],
  },
  {
    id: "configuration",
    activeItem: "",
    label: "Configuration",
    icon: icons.gear,
    items: [
  {
    label: "Settings",
    route: "#/settings",
  },
  {
    id: "api-explorer",
    label: "API explorer",
    route: "#/api-explorer",
    // Developer tool: hidden from cashiers/shop staff. Every call it makes is
    // still authorised by the backend (RBAC per endpoint).
    visible: () => isBusinessAdmin(),
  },
  {
    label: "Users",
    route: "#/users",
  },
  {
    label: "Roles & Permissions",
    route: "#/roles",
  },
  {
    label: "Taxes",
    route: "#/taxes",
  },
  {
    label: "Payment Methods",
    route: "#/payment-methods",
  },
]
  },
];

const state = {
  collapsed: false,
  activeItem: "",
  openSections: {
    orders: true,
    inventory: true,
    products: true,
    reporting: true,
    configuration: true,
    business: true,
    fbr: true,
  },
};


const isVisible = (entry) => typeof entry.visible !== "function" || entry.visible();

function renderSection(section, collapsed) {
  const isOpen = state.openSections[section.id];

  const itemsHtml = section.items
  .filter(isVisible)
  .map((item) => {
    const isActive = state.activeItem === item.id;

    return `
      <button
        data-nav-item="${item.id}"
        data-route="${item.route}"
        class="w-full text-left px-3 py-2 text-sm rounded-lg transition-colors
        ${
          isActive
            ? "text-accent bg-accent/10"
            : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
        }">

        ${item.label}

      </button>
    `;
  })
  .join("");

  return `
    <div class="mb-1">

    <button
  data-section-toggle="${section.id}"
  ${collapsed ? `data-sidebar-open` : ""}
  class="relative group w-full flex items-center ${
    collapsed ? "justify-center" : "justify-between"
  } px-3 py-2.5 rounded-lg text-gray-200 hover:bg-white/5 transition-colors"
>

  <span class="flex items-center ${collapsed ? "" : "gap-3"}">

    <span class="text-gray-400 shrink-0">
      ${section.icon}
    </span>

    ${
      collapsed
        ? ""
        : `
          <span class="text-sm font-semibold">
            ${section.label}
          </span>
        `
    }

  </span>

  ${
    collapsed
      ? `
        <span
          class="absolute left-full ml-3 top-1/2 -translate-y-1/2 bg-white text-slate-900 text-sm font-medium px-3 py-2 rounded-lg shadow-lg whitespace-nowrap opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50 pointer-events-none"
        >
          ${section.label}
        </span>
      `
      : `
        <span class="text-gray-500 ${isOpen ? "" : "-rotate-90"}">
          ${icons.chevron}
        </span>
      `
  }

</button>

      ${!collapsed && isOpen
      ? `
            <div class="relative mt-1 ml-[20px] pl-[26px] space-y-0.5">

  <!-- Vertical line -->
  <span
    class="absolute left-0 top-1 bottom-1 w-px bg-gray-600"
  ></span>

  ${itemsHtml}

</div>
          `
      : ""
    }

    </div>
  `;
}

const ROLE_LABELS = { owner: "Owner", admin: "Admin", manager: "Manager", staff: "Staff" };

function displayName(user) {
  const full = [user?.first_name, user?.last_name].filter(Boolean).join(" ").trim();
  return full || user?.username || "Signed in";
}

function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] || "?").slice(0, 2);
  return letters.toUpperCase();
}

/** Signed-in user, role and active business (no third-party avatar requests). */
function userCard(collapsed) {
  const user = getCachedUser();
  const name = displayName(user);
  const role = ROLE_LABELS[user?.role] || (user?.permissions?.includes("*.*") ? "Administrator" : "Member");
  const tenants = cachedTenants() || [];
  const business = currentTenant(tenants)?.name || getCachedTenant()?.name || "";
  const canSwitch = tenants.length > 1;
  const avatar = `<span class="flex w-9 h-9 shrink-0 items-center justify-center rounded-full bg-accent/20 text-xs font-bold text-accent" aria-hidden="true">${escapeHtml(initials(name))}</span>`;
  const logoutButton = (extra = "") => `<button id="sidebar-logout-btn" type="button" title="Sign out" aria-label="Sign out" class="${extra} flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 transition hover:bg-rose-500/10 hover:text-rose-300 shrink-0"><i data-lucide="log-out" width="17" height="17"></i></button>`;
  if (collapsed) {
    return `<div class="flex flex-col items-center gap-2 px-2 py-2 rounded-xl bg-sidebar-card" title="${escapeHtml(`${name} · ${role}${business ? ` · ${business}` : ""}`)}">${avatar}${logoutButton("mx-auto")}</div>`;
  }
  return `
    <div class="px-2 py-2 rounded-xl bg-sidebar-card">
      <div class="flex items-center gap-3">
        ${avatar}
        <div class="flex-1 min-w-0">
          <p class="text-sm font-semibold text-white truncate" id="sidebar-user-name">${escapeHtml(name)}</p>
          <p class="text-xs text-gray-400 truncate" id="sidebar-user-role">${escapeHtml(role)}</p>
        </div>
        ${logoutButton()}
      </div>
      ${business ? `
      <div class="mt-2 flex items-center gap-2 border-t border-sidebar-border pt-2">
        <i data-lucide="store" width="14" height="14" class="text-gray-400 shrink-0"></i>
        <span class="flex-1 min-w-0 truncate text-xs text-gray-300" id="sidebar-business" title="Active business">${escapeHtml(business)}</span>
        ${canSwitch ? `<button id="sidebar-switch-business" type="button" class="shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold text-accent hover:bg-white/5">Switch</button>` : ""}
      </div>` : ""}
    </div>`;
}

async function openBusinessSwitcher() {
  let tenants;
  try {
    tenants = await listMyTenants({ force: true });
  } catch (error) {
    toast(errorMessage(error, "Could not load your businesses."), "error");
    return;
  }
  const current = currentTenant(tenants);
  const others = tenants.filter((tenant) => !tenant.isCurrent);
  if (!others.length) {
    toast("You belong to only one active business.", "info");
    refreshSidebar();
    return;
  }
  const openCarts = typeof window.posOpenCartCount === "function" ? window.posOpenCartCount() : 0;
  await openModal({
    title: "Switch business",
    submitLabel: "Switch",
    html: `
      <p class="mb-3 text-sm text-slate-600">Current: <strong>${escapeHtml(current?.name || "—")}</strong>. Switching reloads the app with the selected business's data and permissions.</p>
      ${openCarts ? `<p class="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">${openCarts} POS cart(s) with items will be discarded. Park the sale first to keep it.</p>` : ""}
      ${field({ name: "tenant_id", label: "Business", type: "select", required: true, options: others.map((tenant) => ({ value: tenant.id, label: tenant.name })) })}`,
    onSubmit: async (form) => {
      const { tenant_id: tenantId } = readForm(form);
      if (!tenantId) throw new Error("Choose a business.");
      await switchTenant(tenantId);
      return true;
    },
  });
}

export function Sidebar() {
  const collapsed = state.collapsed;
  const company = cachedCompany();
  const darkMode = isDarkMode();

  return `

  <aside
  id="pos-sidebar"
  class="${
    collapsed ? "w-[72px]" : "w-[260px]"
  } h-screen bg-sidebar-bg border-r border-sidebar-border flex flex-col
  transition-all duration-200 ease-out rounded-r-3xl shrink-0"
>

<!-- Header: logo + collapse toggle -->

<div class="flex items-center ${
  collapsed ? "justify-center px-0" : "justify-between px-5"
} pt-6 pb-6">

  <button
  id="sidebar-logo-btn"
  class="flex items-center ${
    collapsed ? "justify-center w-full" : "gap-2.5 min-w-0"
  }"
>

    <div class="w-8 h-8 shrink-0 rounded-full overflow-hidden flex items-center justify-center">

      ${
        safeUrl(company?.logo)
          ? `
            <img
              src="${escapeHtml(safeUrl(company.logo))}"
              alt="${escapeHtml(company.name || "Company")}"
              class="w-full h-full object-cover"
            >
          `
          : icons.logo
      }

    </div>

    ${
      collapsed
        ? ""
        : `
          <span class="text-white font-bold text-[14px] tracking-tight ">
            ${escapeHtml(company?.name || getCachedTenant()?.name || "POS SYSTEM")}
          </span>
        `
    }

  </button>


  ${
    collapsed
      ? ""
      : `
        <button
          id="collapse-btn"
          class="shrink-0 w-8 h-8 rounded-lg bg-sidebar-card border border-sidebar-border flex items-center justify-center text-gray-400 hover:text-white transition-colors">
          <span class="transition-transform duration-200 inline-flex">
            ${icons.collapse}
          </span>
        </button>  `
  }

</div>


  <!-- Nav: scrollable -->

  <nav id="sidebar-nav" class="flex-1 overflow-y-auto px-3 space-y-5">

    <!-- Dashboard -->

    <div>


    <button
  data-nav-item="Dashboard"
  data-route="#/dashboard"
  data-sidebar-open
  class="relative group w-full flex items-center ${
    collapsed ? "justify-center" : "gap-3"
  } px-3 py-2.5 rounded-lg transition-colors
  ${
    state.activeItem === "Dashboard"
      ? "bg-accent/10 text-accent"
      : "text-gray-200 hover:bg-white/5"
  }"
>

  <span class="shrink-0">
    ${icons.home}
  </span>

  ${
    collapsed
      ? `
        <span
          class="absolute left-full ml-3 top-1/2 -translate-y-1/2
          bg-white text-slate-900 text-sm font-medium
          px-3 py-2 rounded-lg shadow-lg whitespace-nowrap
          opacity-0 invisible group-hover:opacity-100 group-hover:visible
          transition-all duration-200 z-50 pointer-events-none"
        >
          Dashboard
        </span>
      `
      : `
        <span class="text-sm font-semibold">
          Dashboard
        </span>
      `
  }

</button>

    </div>

    <div>

  <button data-nav-item="POS" data-route="#/pos" class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors
    ${state.activeItem === "POS"? "bg-accent/10 text-accent": "text-gray-200 hover:bg-white/5"}">

    <span>
      ${icons.pos}
    </span>

    ${collapsed? "": `<span class="text-sm font-semibold">Point of Sale</span>`}

  </button>

</div>



    <!-- Grouped sections -->

    <div class="space-y-4">

      ${navSections
      .filter((section) => isVisible(section) && section.items.some(isVisible))
      .map((section) => renderSection(section, collapsed))
      .join("")}

    </div>

  </nav>


    <div class="px-3 pb-3">

  <button
    id="theme-toggle"
    class="relative group w-full flex items-center ${
      collapsed ? "justify-center" : "gap-3"
    } px-3 py-2.5 rounded-lg text-gray-300 hover:bg-white/5 transition-colors"
  >

    <span class="shrink-0">
      ${darkMode ? icons.sun : icons.moon}
    </span>

    ${
      collapsed
        ? `
          <span class="absolute left-full ml-3 top-1/2 -translate-y-1/2
            bg-white text-slate-900 text-sm font-medium
            px-3 py-2 rounded-lg shadow-lg whitespace-nowrap
            opacity-0 invisible group-hover:opacity-100 group-hover:visible
            transition-all duration-200 z-50 pointer-events-none">
            ${darkMode ? "Light Mode" : "Dark Mode"}
          </span>
        `
        : `
          <span class="text-sm font-semibold">
            ${darkMode ? "Light Mode" : "Dark Mode"}
          </span>
        `
    }

  </button>

</div>

  <!-- Footer: user card -->

  <div class="p-3 border-t border-sidebar-border">

    ${userCard(collapsed)}

  </div>

</aside>


  `;
}


function refreshSidebar() {
  const oldSidebar = document.getElementById("pos-sidebar");

  if (!oldSidebar) return;

  // Save current scroll position
  const nav = oldSidebar.querySelector("#sidebar-nav");
  const scrollTop = nav ? nav.scrollTop : 0;

  oldSidebar.outerHTML = Sidebar();

  createIcons({
    icons: lucideIcons,
  });

  // Restore scroll position
  const newNav = document.querySelector("#sidebar-nav");

  if (newNav) {
    newNav.scrollTop = scrollTop;
  }

  wireSidebarEvents();
}

function wireSidebarEvents() {
  const collapseBtn = document.getElementById("collapse-btn");
  const logoBtn = document.getElementById("sidebar-logo-btn");

  if (collapseBtn) {
    collapseBtn.addEventListener("click", () => {
      state.collapsed = true;

      refreshSidebar();
    });
  }

  if (logoBtn) {
    logoBtn.addEventListener("click", () => {
      if (state.collapsed) {
        state.collapsed = false;

        refreshSidebar();
      }
    });
  }

  const logoutButton = document.getElementById("sidebar-logout-btn");
  logoutButton?.addEventListener("click", async () => {
    logoutButton.disabled = true;
    logoutButton.setAttribute("aria-label", "Signing out");
    try {
      await logout();
    } catch (error) {
      console.error("Logout request failed; local credentials were cleared.", error);
    }
  });

  document.getElementById("sidebar-switch-business")?.addEventListener("click", () => {
    openBusinessSwitcher();
  });

  const themeToggle = document.getElementById("theme-toggle");

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    toggleDarkMode();
    refreshSidebar();
  });
}

  document
  .querySelectorAll("[data-sidebar-open]")
  .forEach((button) => {
    button.addEventListener("click", () => {
      if (state.collapsed) {
        state.collapsed = false;

        refreshSidebar();
      }
    });
  });

  document
    .querySelectorAll("[data-section-toggle]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.getAttribute("data-section-toggle");

        state.openSections[id] = !state.openSections[id];

        refreshSidebar();
      });
    });

document
  .querySelectorAll("[data-nav-item]")
  .forEach((button) => {

    button.addEventListener("click", () => {

      state.activeItem = button.dataset.navItem;

      if (button.dataset.route) {
        window.location.hash = button.dataset.route;
      }

      refreshSidebar();

    });

  });
    
}

export async function initializeSidebar() {
  createIcons({
    icons: lucideIcons,
  });

  wireSidebarEvents();

  applyTheme();
  await refreshCompany();
  // Business list for the switcher (own memberships only); failure is non-fatal.
  if (!cachedTenants()) {
    listMyTenants().then(() => refreshSidebar()).catch(() => {});
  }
}


















