import { escapeHtml, safeUrl } from "../../../shared/format.js";
export function EditProductModal(product) {

return `

<div class="space-y-5">

    <input
        id="edit-name"
        value="${escapeHtml(product.name)}"
        class="w-full border rounded-xl p-3"
    >

    <input
        id="edit-sale-price"
        type="number"
        value="${escapeHtml(product.sales_price)}"
        class="w-full border rounded-xl p-3"
    >

    <input
        id="edit-cost-price"
        type="number"
        value="${escapeHtml(product.cost_price)}"
        class="w-full border rounded-xl p-3"
    >

    <button
        onclick="saveProduct(${Number(product.id)})"
        class="bg-emerald-600 text-white px-5 py-3 rounded-xl"
    >
        Save Changes
    </button>

</div>

`;

}