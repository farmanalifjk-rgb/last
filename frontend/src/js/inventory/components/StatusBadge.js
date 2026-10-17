export function StatusBadge(stock, minimumStock) {

    if (stock === 0) {
        return `
            <span class="
                inline-flex items-center
                px-2.5 py-1
                rounded-full
                text-xs
                font-semibold
                bg-rose-50
                text-rose-600
                border border-rose-100
            ">
                Out of Stock
            </span>
        `;
    }

    if (stock <= minimumStock) {
        return `
            <span class="
                inline-flex items-center
                px-2.5 py-1
                rounded-full
                text-xs
                font-semibold
                bg-amber-50
                text-amber-700
                border border-amber-100
            ">
                Low Stock
            </span>
        `;
    }

    return `
        <span class="
            inline-flex items-center
            px-2.5 py-1
            rounded-full
            text-xs
            font-semibold
            bg-emerald-50
            text-emerald-700
            border border-emerald-100
        ">
            In Stock
        </span>
    `;

}