export function ErrorState() {

    return `

<tr>

<td colspan="7" class="py-16 text-center">

    <i
        data-lucide="alert-circle"
        class="w-9 h-9 text-red-500 mx-auto">
    </i>

    <h3 class="mt-4 font-semibold">

        Failed to load inventory

    </h3>

    <button

        onclick="loadInventory()"

        class="mt-3 text-emerald-600 hover:underline"

    >

        Try Again

    </button>

</td>

</tr>

`;

}