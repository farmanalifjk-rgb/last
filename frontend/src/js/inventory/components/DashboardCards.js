import { StatsCard } from "./StatsCard";

export function DashboardCards() {

    return `

<div
class="grid grid-cols-4 gap-6">

${StatsCard({

    title: "Total Products",

    value: "0",

    valueId: "total-products-stat",

    icon: "package",

    iconBg: "bg-emerald-100",

    iconColor: "text-emerald-600",

    glow: "bg-emerald-200/60",

    change: "+12% this month",

    changeColor: "text-emerald-600",

})}

${StatsCard({

    title: "Low Stock",

    value: "0",

    valueId: "low-stock-stat",

    icon: "triangle-alert",

    iconBg: "bg-amber-100",

    iconColor: "text-amber-600",

    glow: "bg-amber-200/60",

    change: "Needs attention",

    changeColor: "text-amber-600",

})}

${StatsCard({

    title: "Out of Stock",

    value: "0",

    valueId: "out-of-stock-stat",

    icon: "circle-off",

    iconBg: "bg-red-100",

    iconColor: "text-red-600",

    glow: "bg-red-200/60",

    change: "Critical",

    changeColor: "text-red-600",

})}

${StatsCard({

    title: "Top Category",

    value: "-",

    valueId: "top-category-stat",

    icon: "layers-3",

    iconBg: "bg-indigo-100",

    iconColor: "text-indigo-600",

    glow: "bg-indigo-200/60",

    change: "Best performing",

    changeColor: "text-indigo-600",

})}

</div>

`;

}