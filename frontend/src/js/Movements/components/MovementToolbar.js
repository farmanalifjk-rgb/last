export function MovementToolbar() {

    return `

<div class="flex items-center justify-between gap-4 mb-6">

    <div class="flex items-center gap-3">

        <!-- Search -->
        <div class="relative">

            <i
                data-lucide="search"
                class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400">
            </i>

            <input
                id="movement-search"
                type="text"
                placeholder="Search movements..."
                class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl">

        </div>

        <!-- Refresh -->
        <button
            onclick="refreshMovements()"
            class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition">

            <i data-lucide="refresh-cw" class="w-5 h-5 mx-auto"></i>

        </button>

    </div>

    <div class="flex items-center gap-3">

        <!-- Movement Type -->
        <select
            id="movement-filter"
            class="premium-input h-11 px-4 rounded-xl">

            <option value="">All Types</option>
            <option value="purchase">Purchase</option>
            <option value="sale">Sale</option>
            <option value="refund">Refund</option>
            <option value="adjustment">Adjustment</option>
            <option value="damage">Damage</option>
            <option value="purchase_return">Purchase Return</option>

        </select>

        <!-- Date -->
        <select
            id="date-filter"
            class="premium-input h-11 px-4 rounded-xl">

            <option value="">All Time</option>
            <option value="today">Today</option>
            <option value="yesterday">Yesterday</option>
            <option value="week">This Week</option>
            <option value="month">This Month</option>

        </select>

    </div>

</div>

`;

}