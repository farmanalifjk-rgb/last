import { Sidebar } from "../components/Sidebar.js";
import { apiJson } from "../services/api.js";
import { esc, formatMoney, formatDateTime, table, badge, pageHeader, emptyStateCard, errorMessage } from "../shared/ui.js";
import { createIcons, icons } from "lucide";

/** Dashboard shell. Data is loaded by initializeDashboard() after render. */
export function Dashboard() {
    return `
<div class="flex h-screen bg-[#f4f7f6]">
    ${Sidebar()}
    <main class="flex-1 p-8 overflow-y-auto">
        ${pageHeader({ title: "Dashboard", subtitle: "Today at a glance" })}
        <div id="dashboard-kpis" class="mb-8 grid grid-cols-4 gap-4"></div>
        <div class="mb-8 grid grid-cols-3 gap-4">
            <a href="#/pos" class="rounded-2xl border border-slate-200 bg-white p-5 hover:border-violet-300"><p class="font-semibold text-slate-900">Point of Sale</p><p class="mt-1 text-sm text-slate-500">Open the register and take payments</p></a>
            <a href="#/customers" class="rounded-2xl border border-slate-200 bg-white p-5 hover:border-violet-300"><p class="font-semibold text-slate-900">Customers</p><p class="mt-1 text-sm text-slate-500">Records, credit limits and loyalty</p></a>
            <a href="#/purchasing?tab=orders" class="rounded-2xl border border-slate-200 bg-white p-5 hover:border-violet-300"><p class="font-semibold text-slate-900">Purchasing</p><p class="mt-1 text-sm text-slate-500">Purchase orders, receipts and returns</p></a>
        </div>
        <div class="grid grid-cols-2 gap-6">
            <section>
                <h2 class="mb-3 text-base font-bold text-slate-900">Low stock</h2>
                <div id="dashboard-low-stock"></div>
            </section>
            <section>
                <h2 class="mb-3 text-base font-bold text-slate-900">Recent orders</h2>
                <div id="dashboard-recent-orders"></div>
            </section>
        </div>
    </main>
</div>`;
}

const KPI_LABELS = [
    ["today_sales", "Today's sales", true],
    ["today_orders", "Orders today", false],
    ["total_customers", "Customers", false],
    ["total_products", "Products", false],
    ["low_stock_count", "Low stock items", false],
    ["out_of_stock_count", "Out of stock", false],
    ["open_sessions", "Open POS sessions", false],
    ["pending_orders", "Pending orders", false],
];

window.initializeDashboard = async function () {
    await Promise.all([loadKpis(), loadLowStock(), loadRecentOrders()]);
    createIcons({ icons });
};

async function loadKpis() {
    const target = document.getElementById("dashboard-kpis");
    if (!target) return;
    try {
        const s = await apiJson("/api/dashboard/summary/");
        target.innerHTML = KPI_LABELS.map(([key, label, money]) => `
            <div class="rounded-2xl border border-slate-200 bg-white p-5">
                <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">${esc(label)}</p>
                <p class="mt-2 text-2xl font-bold text-slate-900 tabular-nums">${esc(money ? formatMoney(s[key]) : (s[key] ?? 0))}</p>
            </div>`).join("");
    } catch (error) {
        target.innerHTML = `<div class="col-span-4">${emptyStateCard("Could not load the summary", errorMessage(error))}</div>`;
    }
}

async function loadLowStock() {
    const target = document.getElementById("dashboard-low-stock");
    if (!target) return;
    try {
        const rows = await apiJson("/api/dashboard/low-stock/");
        target.innerHTML = table({
            columns: [
                { label: "Product", cell: (r) => `<span class="font-semibold">${esc(r.name)}</span> <span class="text-xs text-slate-500">${esc(r.sku || "")}</span>` },
                { label: "Stock", align: "right", cell: (r) => esc(r.stock) },
                { label: "Minimum", align: "right", cell: (r) => esc(r.minimum_stock) },
                { label: "Status", cell: (r) => badge(r.status || "Low", Number(r.stock) <= 0 ? "red" : "amber") },
            ],
            rows: Array.isArray(rows) ? rows : [],
            empty: "Nothing is below its minimum stock level.",
        });
    } catch (error) {
        target.innerHTML = emptyStateCard("Could not load low stock", errorMessage(error));
    }
}

async function loadRecentOrders() {
    const target = document.getElementById("dashboard-recent-orders");
    if (!target) return;
    try {
        const rows = await apiJson("/api/dashboard/recent-orders/");
        target.innerHTML = table({
            columns: [
                { label: "Order", cell: (o) => `<span class="font-mono text-xs">${esc(o.order_number || o.number || o.id || "-")}</span>` },
                { label: "Date", cell: (o) => esc(formatDateTime(o.created_at || o.date)) },
                { label: "Total", align: "right", cell: (o) => esc(formatMoney(o.total ?? o.total_amount)) },
                { label: "Status", cell: (o) => esc(o.status || "-") },
            ],
            rows: Array.isArray(rows) ? rows : [],
            empty: "No orders yet today.",
        });
    } catch (error) {
        target.innerHTML = emptyStateCard("Could not load recent orders", errorMessage(error));
    }
}
