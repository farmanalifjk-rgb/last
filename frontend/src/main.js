import "./style.css";
import "./styles/dark-theme.css";
import { applyTheme } from "./shared/theme.js";

// Apply the stored theme before anything renders (no light flash, login included).
applyTheme();

import { createIcons, icons } from "lucide";

import {
  LoginPage,
  initializeLogin,
} from "./pages/LoginPage.js";
import { ForgotPasswordPage, initializeForgotPassword } from "./pages/ForgotPasswordPage.js";

import { Dashboard } from "./pages/Dashboard.js";
import { POSPage } from "./pages/POSPage.js";
import { OrderHistoryPage } from "./pages/OrderHistoryPage.js";
import { InventoryPage } from "./pages/InventoryPage.js";
import { MovementHistoryPage } from "./pages/MovementHistoryPage";
import { AdjustmentPage } from "./pages/AdjustmentPage.js";

// ── Catalog pages ─────────────────────────────────────────────────────────────
import { AllProductsPage } from "./pages/AllProductsPage.js";
import { CategoriesPage } from "./pages/CategoriesPage.js";
import { BrandsPage } from "./pages/BrandsPage.js";
import { VariantsPage } from "./pages/VariantsPage.js";

// ── Report pages ──────────────────────────────────────────────────────────────
import { SalesReportPage } from "./pages/SalesReportPage.js";
import { ProductReportPage } from "./pages/ProductReportPage.js";
import { StockReportPage } from "./pages/StockReportPage.js";
import { TaxReportPage } from "./pages/TaxReportPage.js";

// ── Configuration pages ───────────────────────────────────────────────────────
import { SettingsPage } from "./pages/SettingsPage.js";
import { UsersPage } from "./pages/UsersPage.js";
import { RolesPage } from "./pages/RolesPage.js";
import { TaxesPage } from "./pages/TaxesPage.js";
import { PaymentMethodsPage } from "./pages/PaymentMethodsPage.js";
import { InventoryInsightsPage } from "./pages/InventoryInsightsPage.js";
import { CustomersPage } from "./pages/CustomersPage.js";
import { PurchasingPage } from "./pages/PurchasingPage.js";
import { TransfersPage } from "./pages/TransfersPage.js";
import { StockControlPage } from "./pages/StockControlPage.js";
import { PaymentsPage } from "./pages/PaymentsPage.js";
import { PricingPage } from "./pages/PricingPage.js";

import { initializeSidebar } from "./components/Sidebar.js";
import { validateSession, isBusinessAdmin, hasAnyPermission } from "./services/auth.js";
import { RestrictedPage } from "./pages/RestrictedPage.js";

// ── Existing controllers ──────────────────────────────────────────────────────
import "./js/pos.js";
import "./js/order-history.js";
import "./js/Inventory.js";
import "./js/Movements.js";
import "./js/Adjustment.js";

// ── Catalog controllers ───────────────────────────────────────────────────────
import "./js/AllProducts.js";
import "./js/Categories.js";
import "./js/Brands.js";
import "./js/Variants.js";

// ── Report controllers ────────────────────────────────────────────────────────
import "./js/SalesReport.js";
import "./js/ProductReport.js";
import "./js/StockReport.js";
import "./js/TaxReport.js";

// ── Configuration controllers ─────────────────────────────────────────────────
import "./js/Settings.js";
import "./js/Users.js";
import "./js/Roles.js";
import "./js/Taxes.js";
import "./js/PaymentMethods.js";
import "./js/Insights/InventoryInsights.js";
import "./js/customers/customers.js";
import "./js/purchasing/purchasing.js";
import "./js/transfers/transfers.js";
import "./js/stock/stock-control.js";
import "./js/payments/payments.js";
import "./js/pricing/pricing.js";


// ============================================================================
// AUTHENTICATION / ROUTE GUARD
// ============================================================================

let routeRenderId = 0;
function getToken() {
  return localStorage.getItem("pos_auth_token");
}

function redirectToLogin() {
  if (window.location.hash !== "#/login") window.location.hash = "#/login";
}

// ============================================================================
// ROUTER
// ============================================================================

async function router() {
  const renderId = ++routeRenderId;
  const app = document.getElementById("app");

  if (!app) {
    console.error("Application root #app was not found.");
    return;
  }

  const requestedRoute =
    window.location.hash
      .slice(1)
      .split("?")[0] || "/";

  // Legacy sidebar hashes that map onto existing pages.
  const ROUTE_ALIASES = {
    "/inventory/products": "/products",
    "/inventory/reports": "/reports/stock",
    "/dashboard": "/",
  };
  const route = ROUTE_ALIASES[requestedRoute] || requestedRoute;


  // ==========================================================================
  // LOGIN
  // ==========================================================================

  if (route === "/login") {
    app.innerHTML = LoginPage();

    createIcons({ icons });

    initializeLogin();

    return;
  }

  if (route === "/forgot-password") {
    app.innerHTML = ForgotPasswordPage();
    createIcons({ icons });
    initializeForgotPassword();
    return;
  }


  // ==========================================================================
  // PROTECTED ROUTES
  // ==========================================================================

  const token = getToken();

  if (!token) {
    redirectToLogin();
    return;
  }

  // A cached token is not proof of a valid session. Validate it once per app
  // startup/token, then rely on the API client to catch subsequent revocation.
  app.innerHTML = `
    <div class="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div class="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <div class="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-violet-100 border-t-violet-600"></div>
        <h1 class="text-lg font-bold text-slate-900">Securing your session</h1>
        <p class="mt-2 text-sm text-slate-500">Verifying your access with the POS server…</p>
      </div>
    </div>`;
  try {
    const valid = await validateSession();
    if (renderId !== routeRenderId) return;
    if (!valid) {
      redirectToLogin();
      return;
    }
  } catch (error) {
    if (renderId !== routeRenderId) return;
    app.innerHTML = `
      <div class="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div class="w-full max-w-md rounded-2xl border border-amber-200 bg-white p-8 text-center shadow-sm">
          <h1 class="text-lg font-bold text-slate-900">Could not verify your session</h1>
          <p class="mt-2 text-sm text-slate-600">${String(error?.message || "The POS server could not be reached.").replace(/[&<>\"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[ch]))}</p>
          <button id="retry-session-validation" class="mt-5 rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-violet-700">Try again</button>
          <button id="return-to-login" class="ml-2 mt-5 rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700">Back to login</button>
        </div>
      </div>`;
    document.getElementById("retry-session-validation")?.addEventListener("click", () => {
      import("./services/auth.js").then(({ validateSession: validate }) => validate({ force: true })).then((valid) => {
        if (valid) router(); else redirectToLogin();
      }).catch(() => router());
    });
    document.getElementById("return-to-login")?.addEventListener("click", redirectToLogin);
    return;
  }


  // ==========================================================================
  // POS
  // ==========================================================================

  if (route === "/pos") {
    app.innerHTML = POSPage();

    createIcons({ icons });

    window.initializePOS?.();

    return;
  }


  // ==========================================================================
  // ORDERS
  // ==========================================================================

  if (route === "/orders") {
    app.innerHTML = OrderHistoryPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeOrderHistory?.();

    return;
  }


  // ==========================================================================
  // INVENTORY DASHBOARD
  // ==========================================================================

  if (route === "/inventory/dashboard") {
    app.innerHTML = InventoryPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeInventory?.();

    return;
  }


  // ==========================================================================
  // STOCK MOVEMENTS
  // ==========================================================================

  if (route === "/inventory/movements") {
    app.innerHTML = MovementHistoryPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeMovements?.();

    return;
  }


  // ==========================================================================
  // STOCK ADJUSTMENTS
  // ==========================================================================

  if (route === "/inventory/adjustments") {
    app.innerHTML = AdjustmentPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeAdjustments?.();

    return;
  }


  // ==========================================================================
  // PRODUCTS
  // ==========================================================================

  if (route === "/products") {
    app.innerHTML = AllProductsPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeAllProducts?.();

    return;
  }


  // ==========================================================================
  // CATEGORIES
  // ==========================================================================

  if (route === "/categories") {
    app.innerHTML = CategoriesPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeCategories?.();

    return;
  }


  // ==========================================================================
  // BRANDS
  // ==========================================================================

  if (route === "/brands") {
    app.innerHTML = BrandsPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeBrands?.();

    return;
  }


  // ==========================================================================
  // VARIANTS
  // ==========================================================================

  if (route === "/variants") {
    app.innerHTML = VariantsPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeVariants?.();

    return;
  }


  // ==========================================================================
  // SALES REPORT
  // ==========================================================================

  if (route === "/reports/sales") {
    app.innerHTML = SalesReportPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeSalesReport?.();

    return;
  }


  // ==========================================================================
  // PRODUCT REPORT
  // ==========================================================================

  if (route === "/reports/products") {
    app.innerHTML = ProductReportPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeProductReport?.();

    return;
  }


  // ==========================================================================
  // STOCK REPORT
  // ==========================================================================

  if (route === "/reports/stock") {
    app.innerHTML = StockReportPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeStockReport?.();

    return;
  }


  // ==========================================================================
  // TAX REPORT
  // ==========================================================================

  if (route === "/reports/tax") {
    app.innerHTML = TaxReportPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeTaxReport?.();

    return;
  }


  // ==========================================================================
  // SETTINGS
  // ==========================================================================

  if (route === "/settings") {
    app.innerHTML = SettingsPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeSettings?.();

    return;
  }


  // ==========================================================================
  // USERS
  // ==========================================================================

  if (route === "/users") {
    app.innerHTML = UsersPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeUsers?.();

    return;
  }


  // ==========================================================================
  // ROLES
  // ==========================================================================

  if (route === "/roles") {
    app.innerHTML = RolesPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeRoles?.();

    return;
  }


  // ==========================================================================
  // TAXES
  // ==========================================================================

  if (route === "/taxes") {
    app.innerHTML = TaxesPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializeTaxes?.();

    return;
  }


  // CUSTOMERS
  if (route === "/customers") {
    app.innerHTML = CustomersPage();
    createIcons({ icons });
    initializeSidebar();
    window.initializeCustomers?.();
    return;
  }

  // PURCHASING
  if (route === "/purchasing" || route === "/suppliers") {
    app.innerHTML = PurchasingPage();
    createIcons({ icons });
    initializeSidebar();
    window.initializePurchasing?.();
    return;
  }

  // TRANSFERS & WAREHOUSES
  if (route === "/transfers" || route === "/warehouses") {
    app.innerHTML = TransfersPage();
    createIcons({ icons });
    initializeSidebar();
    window.initializeTransfers?.();
    return;
  }

  // STOCK CONTROL
  if (route === "/stock-control") {
    app.innerHTML = StockControlPage();
    createIcons({ icons });
    initializeSidebar();
    window.initializeStockControl?.();
    return;
  }

  // PAYMENTS & CREDIT
  if (route === "/payments") {
    app.innerHTML = PaymentsPage();
    createIcons({ icons });
    initializeSidebar();
    window.initializePayments?.();
    return;
  }

  // PRICING & TAX
  if (route === "/pricing") {
    app.innerHTML = PricingPage();
    createIcons({ icons });
    initializeSidebar();
    window.initializePricing?.();
    return;
  }

  // FBR / FISCAL (owners, admins, roles with a fiscal permission)
  if (route === "/fbr") {
    if (!hasAnyPermission(["fiscal.view", "fiscal.manage"])) {
      app.innerHTML = RestrictedPage({ title: "FBR / Fiscal is not available", message: "Your role does not include fiscal permissions. Ask the business owner or an admin." });
      createIcons({ icons });
      initializeSidebar();
      return;
    }
    const { FbrPage } = await import("./pages/FbrPage.js");
    await import("./js/fbr/fbr.js");
    if (renderId !== routeRenderId) return;
    app.innerHTML = FbrPage();
    createIcons({ icons });
    initializeSidebar();
    window.initializeFbr?.();
    return;
  }

  // API EXPLORER
  if (route === "/api-explorer") {
    // Developer tool for owners/admins only (navigation hides it too). The
    // backend authorises every request the explorer sends regardless.
    if (!isBusinessAdmin()) {
      app.innerHTML = RestrictedPage({ title: "API explorer is not available", message: "The API explorer is a developer tool for business owners and admins." });
      createIcons({ icons });
      initializeSidebar();
      return;
    }
    const { ApiExplorerPage, initializeApiExplorerIcons } = await import("./pages/ApiExplorerPage.js");
    app.innerHTML = ApiExplorerPage();
    initializeApiExplorerIcons();
    initializeSidebar();
    const { mountApiExplorer } = await import("./js/api-map/explorer.js");
    if (renderId !== routeRenderId) return;
    mountApiExplorer(document.getElementById("api-explorer-root"));
    return;
  }

  // ==========================================================================
  // PAYMENT METHODS
  // ==========================================================================

  if (route === "/payment-methods") {
    app.innerHTML = PaymentMethodsPage();

    createIcons({ icons });

    initializeSidebar();

    window.initializePaymentMethods?.();

    return;
  }


  // ==========================================================================
  // INVENTORY VALUATION AND ABC ANALYSIS
  // ==========================================================================

  if (route === "/inventory/valuation" || route === "/inventory/analytics") {
    const kind = route === "/inventory/valuation" ? "valuation" : "abc";
    app.innerHTML = InventoryInsightsPage(kind);

    createIcons({ icons });

    initializeSidebar();

    if (kind === "valuation") window.initializeValuation?.();
    else window.initializeAbcAnalysis?.();

    return;
  }


  // ==========================================================================
  // DEFAULT
  // ==========================================================================

  // Unknown route → Dashboard
  app.innerHTML = Dashboard();

  createIcons({ icons });

  initializeSidebar();
  window.initializeDashboard?.();
}


// ============================================================================
// START APPLICATION
// ============================================================================

window.addEventListener("hashchange", router);

router();