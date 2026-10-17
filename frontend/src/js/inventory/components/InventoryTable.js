import { ProductRow } from "./ProductRow";

export function InventoryTable(products) {

    if (!products.length) {

        return `

<tr>

    <td colspan="7" class="py-16 text-center">

        <div class="w-16 h-16 mx-auto rounded-2xl bg-gray-50 border flex items-center justify-center">

            <i data-lucide="package-search"
               class="w-8 h-8 text-gray-400">
            </i>

        </div>

        <h3 class="mt-5 text-lg font-semibold text-slate-900">
            No products found
        </h3>

        <p class="mt-1 text-sm text-slate-500">
            Try changing your filters.
        </p>

    </td>

</tr>

`;
    }

    return products.map(ProductRow).join("");

}