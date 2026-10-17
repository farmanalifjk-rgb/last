export function MovementCard({
    title,
    value,
    valueId,
    icon,
    gradient,
    accent,
    iconColor,
    subtitle,
}) {

    return `

<div
    class="relative overflow-hidden rounded-3xl ${gradient}
    border border-white/70 shadow-lg hover:shadow-2xl
    hover:-translate-y-1 transition-all duration-300 p-6">

    <!-- Glow -->
    <div
        class="absolute -right-8 -top-8 h-28 w-28 rounded-full ${accent} opacity-20 blur-3xl">
    </div>

    <!-- Background Icon -->
    <i
        data-lucide="${icon}"
        class="absolute right-5 top-5 h-20 w-20 opacity-10 ${iconColor}">
    </i>

    <div class="relative">

        <p class="text-sm font-semibold text-slate-500">
            ${title}
        </p>

        <h2
            id="${valueId}"
            class="mt-3 text-4xl font-black tracking-tight text-slate-900">

            ${value}

        </h2>

        <div class="mt-6">

            <div class="h-2 rounded-full bg-white/70 overflow-hidden">

                <div
                    class="h-full w-3/4 rounded-full ${accent}">
                </div>

            </div>

        </div>

        <p class="mt-4 text-sm font-medium text-slate-600">

            ${subtitle}

        </p>

    </div>

</div>

`;
}

export function MovementCards() {

    return `

<div class="grid grid-cols-4 gap-6 mb-8">

${MovementCard({

title:"Today's Movements",

value:"0",

valueId:"today-movements",

icon:"activity",

gradient:"bg-gradient-to-br from-sky-50 to-cyan-100",

accent:"bg-sky-500",

iconColor:"text-sky-600",

subtitle:"Inventory activity"

})}

${MovementCard({

title:"Stock In",

value:"0",

valueId:"stock-in",

icon:"arrow-down-circle",

gradient:"bg-gradient-to-br from-emerald-50 to-green-100",

accent:"bg-emerald-500",

iconColor:"text-emerald-600",

subtitle:"Products received"

})}

${MovementCard({

title:"Stock Out",

value:"0",

valueId:"stock-out",

icon:"arrow-up-circle",

gradient:"bg-gradient-to-br from-orange-50 to-red-100",

accent:"bg-red-500",

iconColor:"text-red-600",

subtitle:"Products issued"

})}

${MovementCard({

title:"Adjustments",

value:"0",

valueId:"adjustments",

icon:"sliders-horizontal",

gradient:"bg-gradient-to-br from-violet-50 to-fuchsia-100",

accent:"bg-violet-500",

iconColor:"text-violet-600",

subtitle:"Manual corrections"

})}

</div>

`;

}