import { formatCurrency } from "../../../shared/currency.js";
import { escapeHtml, safeUrl } from "../../../shared/format.js";
import { StatusBadge } from "./StatusBadge";


export function ProductModal(product) {

    return `

<div class="space-y-6">

    <div class="flex gap-5 items-start">

        <div class="w-24 h-24 rounded-2xl bg-gray-50 border border-gray-100 flex items-center justify-center shrink-0">

            ${
                safeUrl(product.image_url)
                    ? `<img src="${escapeHtml(safeUrl(product.image_url))}" class="w-full h-full object-cover rounded-2xl">`
                    : `<i data-lucide="image" class="w-8 h-8 text-gray-300"></i>`
            }

        </div>

        <div>

            <h3 class="text-2xl font-bold text-gray-900">
                ${escapeHtml(product.name)}
            </h3>

            <p class="text-sm text-gray-500 mt-1">
                Category:
                <span class="font-medium text-gray-700">
                    ${escapeHtml(product.category || "-")}
                </span>
            </p>

            <div class="flex gap-2 mt-3">

                ${StatusBadge(
                    product.stock,
                    product.min_stock
                )}

                <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-700">
                    SKU:
                    ${escapeHtml(product.sku || "N/A")}
                </span>

            </div>

        </div>

    </div>

    <div class="grid grid-cols-3 gap-4">

        <div class="rounded-2xl border border-slate-100 bg-slate-50 p-5">

            <p class="text-xs uppercase text-slate-400">
                Current Stock
            </p>

            <p class="mt-2 text-2xl font-bold">
                ${escapeHtml(product.stock)}
            </p>

        </div>

        <div class="rounded-2xl border border-slate-100 bg-slate-50 p-5">

            <p class="text-xs uppercase text-slate-400">
                Minimum Stock
            </p>

            <p class="mt-2 text-xl font-semibold">
                ${escapeHtml(product.min_stock)}
            </p>

        </div>

        <div class="rounded-2xl border border-slate-100 bg-slate-50 p-5">

            <p class="text-xs uppercase text-slate-400">
                Selling Price
            </p>

            <p class="mt-2 text-xl font-bold text-emerald-600">
                ${formatCurrency(product.sales_price)}
            </p>

        </div>

    </div>

    <div class="rounded-2xl border border-slate-100 p-5">

        <p class="mt-2">
            <strong>Cost Price:</strong>
            ${formatCurrency(product.cost_price)}
        </p>

    </div>

    <div class="flex justify-end gap-3 border-t border-slate-100 pt-5">

        <button
            onclick="window.location.hash='#/inventory/adjustments'"
            class="rounded-xl border px-5 py-2.5"
        >
            Adjust Stock
        </button>

        <button
            onclick="closeProductModal()"
            class="rounded-xl bg-slate-900 text-white px-5 py-2.5"
        >
            Close
        </button>

    </div>

</div>

`;

}