import { escapeHtml } from "../../../shared/format.js";
export function AdjustmentDetailModal(adjustment) {

    return `

<div class="bg-white rounded-3xl w-full max-w-3xl shadow-2xl overflow-hidden">

    <div class="flex items-center justify-between px-8 py-6 border-b">

        <div>

            <h2 class="text-2xl font-bold">
                Adjustment Details
            </h2>

            <p class="text-sm text-slate-500">
                Stock Adjustment #${escapeHtml(adjustment.adjustment_number)}
            </p>

        </div>

        <button
            onclick="closeAdjustmentDetailModal()"
            class="w-10 h-10 rounded-xl hover:bg-slate-100 transition">

            ✕

        </button>

    </div>

    <div class="p-8">

        <div class="grid grid-cols-2 gap-6 mb-6">

            <div>

                <p class="text-sm text-slate-500">Adjustment Number</p>

                <p class="font-semibold text-lg">
                    ${escapeHtml(adjustment.adjustment_number)}
                </p>

            </div>

            <div>

                <p class="text-sm text-slate-500">Created At</p>

                <p class="font-semibold">
                    ${escapeHtml(new Date(adjustment.created_at).toLocaleString())}
                </p>

            </div>

            <div class="col-span-2">

                <p class="text-sm text-slate-500">Note</p>

                <p class="font-medium">
                    ${escapeHtml(adjustment.note || "-")}
                </p>

            </div>

        </div>

        <!-- Items Table -->
        ${adjustment.items && adjustment.items.length ? `

        <div class="border border-slate-200 rounded-2xl overflow-hidden">

            <table class="w-full">

                <thead class="bg-slate-50 border-b border-slate-200">

                    <tr>

                        <th class="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-600">
                            Product
                        </th>

                        <th class="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-slate-600">
                            Qty Before
                        </th>

                        <th class="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-slate-600">
                            Qty After
                        </th>

                        <th class="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-slate-600">
                            Change
                        </th>

                        <th class="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-600">
                            Reason
                        </th>

                    </tr>

                </thead>

                <tbody>

                    ${adjustment.items.map(item => `

                    <tr class="border-b border-slate-100">

                        <td class="px-4 py-3 font-medium text-slate-800">
                            ${escapeHtml(item.product_name || item.product || "-")}
                        </td>

                        <td class="px-4 py-3 text-center text-slate-600">
                            ${escapeHtml(item.quantity_before ?? "-")}
                        </td>

                        <td class="px-4 py-3 text-center text-slate-600">
                            ${escapeHtml(item.quantity_after ?? "-")}
                        </td>

                        <td class="px-4 py-3 text-center">

                            <span class="${
                                (item.quantity_after - item.quantity_before) >= 0
                                    ? "text-emerald-600"
                                    : "text-red-600"
                            } font-bold">

                                ${
                                    (item.quantity_after - item.quantity_before) >= 0
                                        ? "+"
                                        : ""
                                }${escapeHtml(item.quantity_after - item.quantity_before)}

                            </span>

                        </td>

                        <td class="px-4 py-3 text-slate-600">
                            ${escapeHtml(item.reason || "-")}
                        </td>

                    </tr>

                    `).join("")}

                </tbody>

            </table>

        </div>

        ` : `

        <p class="text-slate-400 text-sm text-center py-6">
            No items found for this adjustment.
        </p>

        `}

    </div>

</div>

`;

}