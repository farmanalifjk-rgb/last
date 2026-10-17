import { formatCurrency } from "../../../shared/currency.js";
import { escapeHtml, safeUrl } from "../../../shared/format.js";
export function ProductDetailModal(data) {

    const product = data.product;

    return `

<div class="bg-white rounded-2xl w-full max-w-5xl max-h-[90vh] overflow-y-auto shadow-2xl">

    <div class="flex items-center justify-between px-8 py-6 border-b">

        <h2 class="text-2xl font-bold">
            Product Details
        </h2>

        <button
            onclick="closeProductDetailModal()"
            class="w-10 h-10 rounded-lg hover:bg-gray-100">

            ✕

        </button>

    </div>

    <div class="p-8 grid grid-cols-3 gap-8">

        <div>

            ${
                safeUrl(product.image_url)
                ? `
                <img
                    src="${escapeHtml(safeUrl(product.image_url))}"
                    class="w-full rounded-xl border">
                `
                : `
                <div class="h-64 rounded-xl border flex items-center justify-center">

                    No Image

                </div>
                `
            }

        </div>

        <div class="col-span-2 space-y-5">

            <div>

                <h3 class="text-3xl font-bold">

                    ${escapeHtml(product.name)}

                </h3>

                <p class="text-gray-500">

                    ${escapeHtml(product.category || "-")}

                </p>

            </div>

            <div class="grid grid-cols-2 gap-6">

                <div>

                    <p class="text-sm text-gray-500">
                        SKU
                    </p>

                    <p class="font-semibold">
                        ${escapeHtml(product.sku)}
                    </p>

                </div>

                <div>

                    <p class="text-sm text-gray-500">
                        Barcode
                    </p>

                    <p class="font-semibold">
                        ${escapeHtml(product.barcode || "-")}
                    </p>

                </div>

                <div>

                    <p class="text-sm text-gray-500">
                        Cost Price
                    </p>

                    <p class="font-semibold">

                        ${escapeHtml(formatCurrency(product.cost_price))}

                    </p>

                </div>

                <div>

                    <p class="text-sm text-gray-500">
                        Sale Price
                    </p>

                    <p class="font-semibold">

                        ${escapeHtml(formatCurrency(product.sales_price))}

                    </p>

                </div>

                <div>

                    <p class="text-sm text-gray-500">
                        Current Stock
                    </p>

                    <p class="font-semibold">

                        ${escapeHtml(product.stock_quantity)}

                    </p>

                </div>

                <div>

                    <p class="text-sm text-gray-500">
                        Status
                    </p>

                    <p class="font-semibold">

                        ${escapeHtml(product.stock_status)}

                    </p>

                </div>

            </div>

        </div>

    </div>

    <div class="border-t p-6 flex justify-end gap-3">

        <button onclick="openEditProduct(${Number(product.id)})">
            Edit Product
        </button>

        <button
            class="px-5 py-2 rounded-xl bg-red-600 text-white">

            Delete Product

        </button>

    </div>

    <div class="border-t px-8 py-6">

    <h3 class="text-lg font-semibold mb-4">

        Recent Stock Movements

    </h3>

    <div class="space-y-3">

        ${
            data.recent_movements.length
            ?

            data.recent_movements.map(m => `

                <div class="flex items-center justify-between border rounded-xl px-4 py-3">

                    <div>

                        <p class="font-medium">

                            ${escapeHtml(m.movement_type)}

                        </p>

                        <p class="text-xs text-gray-400">

                            ${escapeHtml(m.reference || "-")}

                        </p>

                    </div>

                    <div class="text-right">

                        <p class="${
                            m.quantity > 0
                            ? "text-emerald-600"
                            : "text-red-600"
                        } font-semibold">

                            ${m.quantity > 0 ? "+" : ""}${escapeHtml(m.quantity)}

                        </p>

                    </div>

                </div>

            `).join("")

            :

            `<p class="text-gray-400">
                No stock movement found.
            </p>`

        }

    </div>

</div>

</div>



`;

}