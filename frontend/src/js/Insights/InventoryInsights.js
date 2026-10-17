import { createIcons, icons } from "lucide";
import { getValuation, getAnalytics } from "../inventory/services/inventory-api";
import { Pagination } from "../../shared/Pagination";
import { escapeHtml, formatMoney } from "../../shared/format";

const PAGE_SIZE = 20;

function makeController(kind) {
    const filters = { page: 1, classification: "" };
    const pagination = new Pagination({
        prevButtonId: "prev-page",
        nextButtonId: "next-page",
        containerId: "pagination-numbers",
        pageSize: PAGE_SIZE,
        onPageChange: async (page) => {
            filters.page = page;
            await load();
        },
    });

    async function load() {
        const table = document.getElementById("insights-table");
        if (!table) return;
        table.innerHTML = `<p class="py-10 text-center text-sm text-gray-400">Loading…</p>`;
        try {
            const response = kind === "abc"
                ? await getAnalytics({ page: filters.page, page_size: PAGE_SIZE, classification: filters.classification })
                : await getValuation({ page: filters.page, page_size: PAGE_SIZE });
            render(response.results || [], response);
            pagination.updateFromResponse(response);
            createIcons({ icons });
        } catch (error) {
            table.innerHTML = `<p class="py-10 text-center text-sm text-red-600">Could not load data: ${escapeHtml(error.message)}</p>`;
        }
    }

    function render(rows, response) {
        const table = document.getElementById("insights-table");
        const summary = document.getElementById("insights-summary");
        if (summary) summary.textContent = `${response.count ?? rows.length} products`;
        if (!rows.length) {
            table.innerHTML = kind === "abc"
                ? `<p class="py-10 text-center text-sm text-gray-400">No ABC classes have been computed yet.</p>`
                : `<p class="py-10 text-center text-sm text-gray-400">No products with stock to value.</p>`;
            return;
        }
        if (kind === "abc") {
            table.innerHTML = `
            <table class="w-full text-sm">
                <thead class="text-gray-500 border-b">
                    <tr><th class="text-left py-3">Product</th><th class="text-left">SKU</th><th class="text-center">Class</th><th class="text-right">Annual value</th><th class="text-right">Cumulative share</th></tr>
                </thead>
                <tbody>${rows.map((row) => `
                    <tr class="border-b border-gray-100">
                        <td class="py-3 font-medium text-gray-900">${escapeHtml(row.product_name)}</td>
                        <td class="text-gray-600">${escapeHtml(row.product_sku)}</td>
                        <td class="text-center font-semibold">${escapeHtml(row.abc_class)}</td>
                        <td class="text-right">${escapeHtml(formatMoney(row.annual_value))}</td>
                        <td class="text-right">${escapeHtml(formatMoney(row.cumulative_share))}%</td>
                    </tr>`).join("")}
                </tbody>
            </table>`;
            return;
        }
        table.innerHTML = `
        <table class="w-full text-sm">
            <thead class="text-gray-500 border-b">
                <tr><th class="text-left py-3">Product</th><th class="text-left">SKU</th><th class="text-right">Quantity</th><th class="text-right">Unit cost</th><th class="text-right">Stock value</th><th class="text-left pl-4">Method</th></tr>
            </thead>
            <tbody>${rows.map((row) => `
                <tr class="border-b border-gray-100">
                    <td class="py-3 font-medium text-gray-900">${escapeHtml(row.name)}</td>
                    <td class="text-gray-600">${escapeHtml(row.sku)}</td>
                    <td class="text-right">${escapeHtml(formatMoney(row.quantity))}</td>
                    <td class="text-right">${escapeHtml(formatMoney(row.unit_cost))}</td>
                    <td class="text-right font-semibold">${escapeHtml(formatMoney(row.stock_value))}</td>
                    <td class="pl-4 text-gray-500 uppercase text-xs">${escapeHtml(row.valuation_method)}</td>
                </tr>`).join("")}
            </tbody>
        </table>`;
    }

    return function init() {
        pagination.initialize();
        document.getElementById("abc-class-filter")?.addEventListener("change", (event) => {
            filters.classification = event.target.value;
            filters.page = 1;
            pagination.reset();
            load();
        });
        return load();
    };
}

window.initializeValuation = makeController("valuation");
window.initializeAbcAnalysis = makeController("abc");
