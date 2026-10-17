export function Toolbar() {

    return `

<div class="flex items-center justify-between gap-6">

    <div class="flex items-center gap-4">

        <div class="relative">

<i
data-lucide="search"
class="absolute left-4 top-3.5 w-4 h-4 text-slate-400">
</i>

<input
class="
premium-input
pl-11
h-11
rounded-xl
w-80">

</div>

        <button
            id="refresh-btn"
            class="h-11 px-4 rounded-xl border border-slate-200 bg-white
                   hover:bg-slate-50 transition">

            <i data-lucide="refresh-cw" class="w-5 h-5"></i>

        </button>

    </div>


</div>

`;

}