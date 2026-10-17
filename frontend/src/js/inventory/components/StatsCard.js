export function StatsCard({
    icon,
    iconBg,
    iconColor,
    glow,
    title,
    value,
    valueId,
    change,
    changeColor,
}) {

return `

<div
    class="relative overflow-hidden rounded-3xl border border-slate-200 bg-white p-6 shadow-sm hover:-translate-y-1 hover:shadow-xl transition-all duration-300">

    <!-- Glow -->
    <div
        class="absolute -top-12 -right-12 h-40 w-40 rounded-full blur-3xl ${glow}">
    </div>

    <div class="relative flex items-start justify-between">

        <!-- Left Content -->
        <div>

            <p class="text-sm font-medium text-slate-500">
                ${title}
            </p>

            <h2
                id="${valueId}"
                class="mt-3 text-3xl font-black tracking-tight text-slate-800">

                ${value}

            </h2>

            <p
                class="mt-4 flex items-center gap-2 text-sm font-medium ${changeColor}">

                <span class="w-2 h-2 rounded-full bg-current"></span>

                ${change}

            </p>

        </div>

        <!-- Right Icon -->
        <div
            class="flex h-16 w-16 items-center justify-center rounded-2xl ${iconBg} shadow-lg ring-1 ring-white/70">

            <i
                data-lucide="${icon}"
                class="h-7 w-7 ${iconColor}">
            </i>

        </div>

    </div>

</div>

`;

}