export function ProductCard({ title, value, valueId, icon, gradient, accent, iconColor, subtitle }) {
    return `<div class="relative overflow-hidden rounded-3xl ${gradient} border border-white/70 shadow-lg hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 p-6">
        <div class="absolute -right-8 -top-8 h-28 w-28 rounded-full ${accent} opacity-20 blur-3xl"></div>
        <i data-lucide="${icon}" class="absolute right-5 top-5 h-20 w-20 opacity-10 ${iconColor}"></i>
        <div class="relative">
            <p class="text-sm font-semibold text-slate-500">${title}</p>
            <h2 id="${valueId}" class="mt-3 text-4xl font-black tracking-tight text-slate-900">${value}</h2>
            <div class="mt-6"><div class="h-2 rounded-full bg-white/70 overflow-hidden"><div class="h-full w-3/4 rounded-full ${accent}"></div></div></div>
            <p class="mt-4 text-sm font-medium text-slate-600">${subtitle}</p>
        </div>
    </div>`;
}

export function ProductCards() {
    return `<div class="grid grid-cols-4 gap-6 mb-8">
        ${ProductCard({
            title: "Total Products",
            value: "0",
            valueId: "total-products",
            icon: "package",
            gradient: "bg-gradient-to-br from-sky-50 to-white",
            accent: "bg-sky-500",
            iconColor: "text-sky-600",
            subtitle: "All registered items"
        })}
        ${ProductCard({
            title: "Active Products",
            value: "0",
            valueId: "active-products",
            icon: "check-circle",
            gradient: "bg-gradient-to-br from-emerald-50 to-white",
            accent: "bg-emerald-500",
            iconColor: "text-emerald-600",
            subtitle: "Currently available"
        })}
        ${ProductCard({
            title: "Low Stock",
            value: "0",
            valueId: "low-stock",
            icon: "alert-triangle",
            gradient: "bg-gradient-to-br from-amber-50 to-white",
            accent: "bg-amber-500",
            iconColor: "text-amber-600",
            subtitle: "Below minimum stock"
        })}
        ${ProductCard({
            title: "Out of Stock",
            value: "0",
            valueId: "out-of-stock",
            icon: "x-circle",
            gradient: "bg-gradient-to-br from-rose-50 to-white",
            accent: "bg-rose-500",
            iconColor: "text-rose-600",
            subtitle: "Requires attention"
        })}
    </div>`;
}