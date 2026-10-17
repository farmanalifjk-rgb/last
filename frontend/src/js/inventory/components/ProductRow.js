import { formatCurrency } from "../../../shared/currency.js";
import { escapeHtml, safeUrl } from "../../../shared/format.js";
import { StatusBadge } from "./StatusBadge";

export function ProductRow(product) {

    const maxStock =
        product.max_stock && product.max_stock > 0
            ? product.max_stock
            : Math.max(product.min_stock * 2, product.stock_quantity);

    const stockPercentage = Math.min(
        (product.stock_quantity / maxStock) * 100,
        100
    );

    let barColor = "bg-emerald-500";

    if (product.stock_quantity === 0) {
        barColor = "bg-red-500";
    } else if (product.stock_quantity <= product.min_stock) {
        barColor = "bg-amber-500";
    }

    return `

<tr class="group hover:bg-[#f8fffc] transition-colors duration-200">

<td class="py-4 pr-6">

<div class="flex items-center gap-3">

<div class="w-10 h-10 rounded-xl bg-gray-50 border border-gray-100 flex items-center justify-center overflow-hidden shrink-0">

${safeUrl(product.image_url)
            ? `<img src="${escapeHtml(safeUrl(product.image_url))}" class="w-full h-full object-cover">`
            : `<i data-lucide="package" class="w-5 h-5 text-gray-400"></i>`
        }

</div>

<div>

<p class="font-semibold text-gray-900 truncate max-w-[180px]">
${escapeHtml(product.name)}
</p>

<p class="text-xs text-gray-400 mt-0.5">
SKU: ${escapeHtml(product.sku || "N/A")}
</p>

</div>

</div>

</td>

<td class="px-6 py-4">
${escapeHtml(product.category || "-")}
</td>

<td class="px-6 py-4 min-w-[200px]">

<div class="flex justify-between text-xs font-semibold mb-1">

<span>
    ${escapeHtml(product.stock_quantity)} ${escapeHtml(product.unit || "Units")}
</span>

<span class="text-gray-400">
    Min ${escapeHtml(product.min_stock)}
    ${product.max_stock
            ? ` • Max ${escapeHtml(product.max_stock)}`
            : ""
        }
</span>

</div>

<div class="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">

<div
class="h-full ${barColor}"
style="width:${stockPercentage}%"
></div>

</div>

</td>

<td class="px-6 py-4">

${formatCurrency(product.sales_price)}

</td>


<td class="px-6 py-4 text-center">

${StatusBadge(
            product.stock_quantity,
            product.min_stock
        )}

</td>

<td class="py-4 pl-6 text-right">

<button
onclick="viewProductDetails(${Number(product.id)})"
class="w-8 h-8 rounded-lg hover:bg-gray-100 transition flex items-center justify-center"
>

<i data-lucide="more-horizontal"></i>

</button>

</td>

</tr>

`;

}