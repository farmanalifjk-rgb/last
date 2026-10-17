// Live smoke test: calls every read-only endpoint the frontend uses against a running backend.
// Usage: API_BASE=<backend origin> SMOKE_USER=<user> SMOKE_PASSWORD=<password> SMOKE_DEVICE=<device id> node scripts/smoke-api.mjs
// Each endpoint must answer 200 with the expected envelope (a bare array, or the paginated { count, results } shape).
const RAW_BASE = process.env.API_BASE;
if (!RAW_BASE) {
    console.error("Set API_BASE to the backend origin, for example API_BASE=http://127.0.0.1:8000");
    process.exit(2);
}
const BASE = RAW_BASE.replace(/\/$/, "");
const USER = process.env.SMOKE_USER;
const PASSWORD = process.env.SMOKE_PASSWORD;
const DEVICE = process.env.SMOKE_DEVICE || "smoke-test";

if (!USER || !PASSWORD) {
  console.error("Set SMOKE_USER and SMOKE_PASSWORD.");
  process.exit(2);
}

// [path, kind]  kind: "list" = array or paginated envelope, "object" = any JSON object/array
const ENDPOINTS = [
  ["/api/auth/me/", "object"],
  ["/api/company/", "object"],
  ["/api/settings/company/", "object"],
  ["/api/categories/", "list"],
  ["/api/catalog/brands/", "list"],
  ["/api/catalog/attributes/", "list"],
  ["/api/products/", "list"],
  ["/api/products/?stock=low", "list"],
  ["/api/catalog/products/export/csv/", "text"],
  ["/api/customers/", "list"],
  ["/api/payment-methods/", "list"],
  ["/api/taxes/", "list"],
  ["/api/roles/", "list"],
  ["/api/users/", "list"],
  ["/api/inventory/overview/", "object"],
  ["/api/inventory/movements/", "list"],
  ["/api/inventory/adjustments/", "list"],
  ["/api/inventory/aging/", "list"],
  ["/api/inventory/abc/", "list"],
  ["/api/dashboard/summary/", "object"],
  ["/api/dashboard/low-stock/", "object"],
  ["/api/dashboard/order-statistics/", "object"],
  ["/api/reports/inventory-valuation/", "list"],
  ["/api/reports/sales/", "list"],
  ["/api/reports/products/", "list"],
  ["/api/reports/stock/", "list"],
  ["/api/reports/tax/", "list"],
  ["/api/reports/top-products/", "list"],
  ["/api/reports/stock/export/csv/", "text"],
  ["/api/reports/sales/export/csv/", "text"],
  ["/api/reports/products/export/csv/", "text"],
  ["/api/reports/tax/export/csv/", "text"],
  ["/api/pos/products/", "list"],
  ["/api/pos/customers/", "list"],
  ["/api/pos/orders/", "list"],
  ["/api/pos/orders/?status=draft", "list"],
  ["/api/pos/sessions/active/", "object"],
  ["/api/pos/parked-sales/", "list"],
];

async function main() {
  const login = await fetch(`${BASE}/api/auth/login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ username: USER, password: PASSWORD, device_id: DEVICE }),
  });
  const loginBody = await login.json().catch(() => ({}));
  const token = loginBody.token || loginBody.access || loginBody.key;
  if (login.status !== 200 || !token) {
    console.error(`Login failed (${login.status}).`);
    process.exit(1);
  }

  let failures = 0;
  for (const [path, kind] of ENDPOINTS) {
    const response = await fetch(`${BASE}${path}`, { headers: { Authorization: `Token ${token}`, Accept: "application/json" } });
    const text = await response.text();
    let problem = "";
    if (response.status !== 200) problem = `status ${response.status}`;
    else if (kind === "list") {
      try {
        const data = JSON.parse(text);
        const ok = Array.isArray(data) || (data && Array.isArray(data.results) && typeof data.count === "number");
        if (!ok) problem = "unexpected list envelope";
      } catch { problem = "not JSON"; }
    } else if (kind === "object") {
      try { JSON.parse(text); } catch { problem = "not JSON"; }
    }
    if (problem) failures += 1;
    console.log(`${problem ? "FAIL" : "ok  "} ${response.status} ${path}${problem ? `  (${problem})` : ""}`);
  }
  console.log(`\n${ENDPOINTS.length - failures}/${ENDPOINTS.length} passed`);
  process.exit(failures ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
