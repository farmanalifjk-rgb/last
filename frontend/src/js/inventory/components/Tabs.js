const tabs = [

    {
        id: "all",
        label: "All Products"
    },

    {
        id: "low",
        label: "Low Stock"
    },

    {
        id: "out",
        label: "Out Of Stock"
    },

    {
        id: "inactive",
        label: "Inactive"
    },

];

export function Tabs() {

    return `

<div
    id="inventory-tabs"
    class="flex gap-2">

${tabs.map(tab => `

<button

    data-tab="${tab.id}"

    class="
        px-5 py-2.5 rounded-full
        text-sm font-medium
        text-slate-500
        hover:bg-slate-100
        transition">

    ${tab.label}

</button>

`).join("")}

</div>

`;

}