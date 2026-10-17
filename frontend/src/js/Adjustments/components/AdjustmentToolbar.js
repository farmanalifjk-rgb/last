export function AdjustmentToolbar() {

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
                id="adjustment-search"
                type="text"
                placeholder="Search adjustments..."
                class="premium-input pl-11 pr-4 h-11 w-80 rounded-xl">

        </div>

        <!-- Refresh -->
        <button
            onclick="refreshAdjustments()"
            class="w-11 h-11 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition">

            <i data-lucide="refresh-cw" class="w-5 h-5 mx-auto"></i>

        </button>

    </div>

    <div class="flex items-center gap-3">

        <!-- Reason / Type -->
        <select
            id="adjustment-reason-filter"
            class="premium-input h-11 px-4 rounded-xl">

            <option value="">All Reasons</option>
            <option value="Stock count">Stock count</option>
            <option value="Damaged">Damaged</option>
            <option value="Expired">Expired</option>
            <option value="Theft or loss">Theft or loss</option>
            <option value="Found stock">Found stock</option>
            <option value="Correction">Correction</option>
            <option value="Other">Other</option>

        </select>

        <!-- Date -->
        <select
            id="adjustment-date-filter"
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