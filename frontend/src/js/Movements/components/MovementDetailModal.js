import { escapeHtml } from "../../../shared/format.js";
export function MovementDetailModal(movement) {

    return `

<div class="bg-white rounded-3xl w-full max-w-3xl shadow-2xl overflow-hidden">

    <div class="flex items-center justify-between px-8 py-6 border-b">

        <div>

            <h2 class="text-2xl font-bold">
                Movement Details
            </h2>

            <p class="text-sm text-slate-500">
                Stock Movement Information
            </p>

        </div>

        <button
            onclick="closeMovementDetailModal()"
            class="w-10 h-10 rounded-xl hover:bg-slate-100 transition">

            ✕

        </button>

    </div>

    <div class="p-8 grid grid-cols-2 gap-6">

        <div>

            <p class="text-sm text-slate-500">Product</p>

            <p class="font-semibold text-lg">
                ${escapeHtml(movement.product)}
            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">Movement</p>

            <p class="font-semibold">
                ${escapeHtml(movement.movement)}
            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">Quantity</p>

            <p class="${
                movement.quantity > 0
                    ? "text-emerald-600"
                    : "text-red-600"
            } font-bold text-xl">

                ${movement.quantity > 0 ? "+" : ""}${escapeHtml(movement.quantity)}

            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">Reference</p>

            <p class="font-semibold">
                ${escapeHtml(movement.reference || "-")}
            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">Previous Stock</p>

            <p class="font-semibold">
                ${escapeHtml(movement.previous_stock ?? "-")}
            </p>

        </div>

        <div>

            <p class="text-sm text-slate-500">New Stock</p>

            <p class="font-semibold">
                ${escapeHtml(movement.new_stock ?? "-")}
            </p>

        </div>

        <div class="col-span-2">

            <p class="text-sm text-slate-500">Note</p>

            <p class="font-medium">
                ${escapeHtml(movement.note || "-")}
            </p>

        </div>

        <div class="col-span-2">

            <p class="text-sm text-slate-500">Created At</p>

            <p class="font-semibold">
                ${escapeHtml(new Date(movement.created_at).toLocaleString())}
            </p>

        </div>

    </div>

</div>

`;

}