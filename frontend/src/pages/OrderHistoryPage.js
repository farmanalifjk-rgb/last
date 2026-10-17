import { Sidebar } from "../components/Sidebar.js";

export function OrderHistoryPage() {
  return `
    <div class="flex h-screen bg-[#f1f2f0] overflow-hidden">

      ${Sidebar()}
  <main class="flex-1 h-screen min-h-0 overflow-hidden p-6">

    <div class="premium-surface h-full min-h-0 rounded-[24px] flex flex-col overflow-hidden">

        <!-- TITLE -->

        <div class="shrink-0 px-6 pt-3 flex items-center justify-between">

                <div class="relative w-[420px]">

                    <i data-lucide="search" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"></i>

                    <input id="search-input" type="text" placeholder="Search for order..."
                        class="w-full h-11 pl-10 pr-4 border border-gray-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-lime-400">

                </div>


            <div class="flex items-center gap-3">

                <div class="relative" id="export-menu-container">

                  <button
                    onclick="toggleExportMenu(event)"
                    class="h-10 px-4 bg-white border border-gray-200 rounded-xl text-sm font-medium flex items-center gap-2 hover:bg-gray-50 transition"
                  >
                    <i data-lucide="download" class="w-4 h-4"></i>

                    Export

                    <i data-lucide="chevron-down" class="w-4 h-4 text-gray-400"></i>
                  </button>


                  <div
                    id="export-menu"
                    class="hidden absolute right-0 top-12 w-52 bg-white border border-gray-200 rounded-xl shadow-xl p-2 z-50"
                  >

                    <button
                      onclick="exportCSV(); closeExportMenu()"
                      class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-50 text-sm text-left transition"
                    >
                      <div class="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center">
                        <i data-lucide="file-spreadsheet" class="w-4 h-4 text-emerald-600"></i>
                      </div>

                      <div>
                        <p class="font-medium text-gray-800">Export CSV</p>
                        <p class="text-xs text-gray-400">Comma-separated file</p>
                      </div>
                    </button>

                  </div>

                </div>


                <button class="h-10 px-4 border border-gray-200 rounded-xl text-sm flex items-center gap-2">
                    More actions

                    <i data-lucide="chevron-down" class="w-4 h-4"></i>
                </button>


                <button onclick="window.location.hash='#/pos'"
                    class="premium-mint-button h-10 px-5 rounded-xl text-sm font-semibold transition hover:-translate-y-0.5">
                    Create order
                </button>

            </div>

        </div>


        <!-- STAT CARDS -->

        <div class="shrink-0 grid grid-cols-4 gap-4 px-6 pt-5">

  ${StatCard(
    "Total Orders",
    "total-orders-stat",
    "shopping-cart",
    "25.2% last period",
    "dark"
  )}

  ${StatCard(
    "Order items",
    "total-items-stat",
    "package",
    "18.2% last period",
    ""
  )}

  ${StatCard(
    "Refund Orders",
    "refund-orders-stat",
    "rotate-ccw",
    "1.2% last period",
    "rose"
  )}

  ${StatCard(
    "Completed Orders",
    "completed-orders-stat",
    "circle-check",
    "12.2% last period",
    "diamond"
  )}

</div>


        <!-- TABLE TOOLBAR -->

        <div class="shrink-0 px-6 pt-5">

            <div class="flex items-center justify-between">


                <div class="flex items-center gap-2">

    <!-- CUSTOMER -->
    <div class="relative group">
        <i
            data-lucide="users"
            class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-sky-500 pointer-events-none"
        ></i>

        <select
            id="customer-filter"
            class="h-10 min-w-[150px] pl-10 pr-9
                   bg-gradient-to-r from-sky-50/80 to-white
                   border border-sky-100
                   rounded-xl text-sm font-medium text-gray-700
                   shadow-sm outline-none appearance-none
                   hover:border-sky-300 hover:shadow-md
                   focus:ring-4 focus:ring-sky-100
                   transition-all duration-200 cursor-pointer"
        >
            <option value="">All Customers</option>
        </select>

        <i
            data-lucide="chevron-down"
            class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
        ></i>
    </div>


    <!-- DATE -->
    <div class="relative group">
        <i
            data-lucide="calendar-days"
            class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-amber-500 pointer-events-none"
        ></i>

        <select
            id="date-filter"
            class="h-10 min-w-[135px] pl-10 pr-9
                   bg-gradient-to-r from-amber-50/80 to-white
                   border border-amber-100
                   rounded-xl text-sm font-medium text-gray-700
                   shadow-sm outline-none appearance-none
                   hover:border-amber-300 hover:shadow-md
                   focus:ring-4 focus:ring-amber-100
                   transition-all duration-200 cursor-pointer"
        >
            <option value="">All Dates</option>
            <option value="today">Today</option>
            <option value="yesterday">Yesterday</option>
            <option value="week">This Week</option>
            <option value="month">This Month</option>
        </select>

        <i
            data-lucide="chevron-down"
            class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
        ></i>
    </div>


    <!-- SORT -->
    <button
        class="group w-10 h-10
               bg-gradient-to-br from-white to-indigo-50
               border border-indigo-100 rounded-xl
               shadow-sm flex items-center justify-center
               hover:border-indigo-300 hover:shadow-md hover:-translate-y-0.5
               active:translate-y-0
               transition-all duration-200"
        title="Sort orders"
    >
        <i
            data-lucide="arrow-up-down"
            class="w-4 h-4 text-indigo-500 group-hover:text-indigo-700 transition"
        ></i>
    </button>


    <!-- MORE -->
    <button
        class="group w-10 h-10
               bg-gradient-to-br from-white to-gray-50
               border border-gray-200 rounded-xl
               shadow-sm flex items-center justify-center
               hover:border-gray-300 hover:shadow-md hover:-translate-y-0.5
               active:translate-y-0
               transition-all duration-200"
        title="More actions"
    >
        <i
            data-lucide="ellipsis"
            class="w-4 h-4 text-gray-500 group-hover:text-gray-900 transition"
        ></i>
    </button>

</div>

            </div>

        </div>


        <!-- TABLE -->



        <div class="flex-1 min-h-0 px-6 pt-4 pb-4 flex flex-col">

            <div class="flex-1 min-h-0 border border-gray-200 rounded-xl overflow-hidden flex flex-col">

                <div id="orders-scroll-container" class="flex-1 min-h-0 overflow-y-scroll overscroll-contain">

                    <table class="w-full text-sm">

                        <thead id="history-header" class="sticky top-0 z-10 bg-[#fafafa] text-gray-500">

                            <tr>

                                <th class="p-4 text-left w-12">
                                    <input type="checkbox">
                                </th>

                                <th class="p-4 text-left font-medium">
                                    Order
                                </th>

                                <th class="p-4 text-left font-medium">
                                    Date
                                </th>

                                <th class="p-4 text-left font-medium">
                                    Customer
                                </th>

                                <th class="p-4 text-left font-medium">
                                    Payment
                                </th>

                                <th class="p-4 text-left font-medium">
                                    Action
                                </th>

                            </tr>

                        </thead>


                        <tbody id="orders-table" class="divide-y divide-gray-100"></tbody>

                    </table>

                </div>

                <!-- PAGINATION -->
                <div id="pagination" class="shrink-0 h-16 px-5 border-t bg-white flex items-center justify-between">

                    <button id="prev-page" class="px-4 py-2 border border-gray-200 rounded-lg text-sm">
                        ← Previous
                    </button>


                    <span id="page-info" class="text-sm text-gray-500"></span>


                    <button id="next-page" class="px-4 py-2 border border-gray-200 rounded-lg text-sm">
                        Next →
                    </button>

                </div>

                
                </div>
                </div>
                </div>
                
  </main>

</div>


<!-- ORDER MODAL -->

<div
  id="order-modal"
  class="fixed inset-0 z-50 hidden items-center justify-center bg-black/40 p-6 backdrop-blur-sm"
>
  <div
    class="w-full max-w-4xl overflow-hidden rounded-[28px]
           border border-white/60
           bg-white/95
           shadow-[0_30px_80px_rgba(15,23,42,0.22)]"
  >
    <!-- HEADER -->

    <div
      class="flex items-center justify-between
             border-b border-gray-100
             bg-gradient-to-r from-white via-emerald-50/40 to-white
             px-7 py-5"
    >
      <div class="flex items-center gap-4">
        <div
          class="flex h-11 w-11 items-center justify-center
                 rounded-2xl bg-[#0c1511] text-emerald-400"
        >
          <i data-lucide="receipt-text" class="h-5 w-5"></i>
        </div>

        <div>
          <h2 class="text-lg font-bold text-gray-950">
            Order Details
          </h2>

          <p class="mt-0.5 text-sm text-gray-400">
            View complete order information
          </p>
        </div>
      </div>

      <button
        onclick="closeModal()"
        class="flex h-10 w-10 items-center justify-center
               rounded-xl border border-gray-200
               bg-white text-gray-500
               transition
               hover:bg-gray-100 hover:text-gray-900"
      >
        <i data-lucide="x" class="h-5 w-5"></i>
      </button>
    </div>

    <!-- BODY -->

    <div
      id="modal-body"
      class="max-h-[72vh] overflow-y-auto p-7"
    ></div>
  </div>
</div>


<!-- REFUND MODAL -->

<div
  id="refund-modal"
  class="fixed inset-0 z-50 hidden items-center justify-center bg-black/40 p-6 backdrop-blur-sm"
>
  <div
    class="w-full max-w-5xl overflow-hidden rounded-[28px]
           border border-white/60
           bg-white/95
           shadow-[0_30px_80px_rgba(15,23,42,0.22)]"
  >
    <!-- HEADER -->

    <div
      class="flex items-center justify-between
             border-b border-gray-100
             bg-gradient-to-r from-white via-emerald-50/50 to-white
             px-7 py-5"
    >
      <div class="flex items-center gap-4">
        <div
          class="flex h-11 w-11 items-center justify-center
                 rounded-2xl bg-[#0c1511] text-emerald-400"
        >
          <i data-lucide="rotate-ccw" class="h-5 w-5"></i>
        </div>

        <div>
          <h2 class="text-lg font-bold text-gray-950">
            Refund Order
          </h2>

          <p class="mt-0.5 text-sm text-gray-400">
            Select products and quantities to refund
          </p>
        </div>
      </div>

      <button
        onclick="closeRefundModal()"
        class="flex h-10 w-10 items-center justify-center
               rounded-xl border border-gray-200
               bg-white text-gray-500
               transition
               hover:bg-gray-100 hover:text-gray-900"
      >
        <i data-lucide="x" class="h-5 w-5"></i>
      </button>
    </div>

    <!-- BODY -->

    <div
      id="refund-body"
      class="max-h-[72vh] overflow-y-auto p-7"
    ></div>
  </div>
</div>
  `;
}


function StatCard(title, valueId, icon, comparison, variant = "mint") {
  const variants = {
    dark: {
      card: "bg-gradient-to-br from-[#111714] to-[#0b0f0d] text-white border-[#1c2923]",
      title: "text-gray-300",
      value: "text-white",
      comparison: "text-gray-400",
      iconBox: "bg-[#7cf5cb]",
      icon: "text-[#063d2e]",
      bars: "bg-[#72efc4]",
    },

    mint: {
      card: "bg-gradient-to-br from-white via-[#f7fffc] to-[#e8fff7] border-emerald-100",
      title: "text-gray-600",
      value: "text-gray-950",
      comparison: "text-gray-500",
      iconBox: "bg-[#d8fff2]",
      icon: "text-[#08745a]",
      bars: "bg-[#08745a]",
    },

    rose: {
      card: "bg-gradient-to-br from-white via-[#fffafa] to-[#fff0f1] border-rose-100",
      title: "text-gray-600",
      value: "text-gray-950",
      comparison: "text-gray-500",
      iconBox: "bg-[#ffe4e6]",
      icon: "text-[#be3b4b]",
      bars: "bg-[#be3b4b]",
    },

    diamond: {
      card: "bg-gradient-to-br from-white via-[#f7fcff] to-[#e2f5ff] border-[#c7e9f8]",
      title: "text-gray-600",
      value: "text-gray-950",
      comparison: "text-gray-500",
      iconBox: "bg-[#dff4ff]",
      icon: "text-[#2589b8]",
      bars: "bg-[#2589b8]",
    },
  };

  const style = variants[variant] || variants.mint;

  return `
    <div
      class="${style.card}
             relative overflow-hidden border rounded-2xl p-5
             min-h-[195px]
             transition-all duration-300
             hover:-translate-y-1 hover:shadow-xl"
    >

      <div class="absolute -right-10 -top-10 w-32 h-32 rounded-full bg-white/10 blur-2xl"></div>

      <div class="relative flex items-center justify-between">

        <p class="text-base font-medium ${style.title}">
          ${title}
        </p>

        <div
          class="${style.iconBox}
                 w-10 h-10 rounded-xl
                 flex items-center justify-center"
        >
          <i
            data-lucide="${icon}"
            class="w-5 h-5 ${style.icon}"
          ></i>
        </div>

      </div>

      <h2
        id="${valueId}"
        class="relative text-4xl font-semibold tracking-tight mt-6 ${style.value}"
      >
        0
      </h2>

      <div class="relative flex items-end justify-between mt-6">

        <p class="text-sm ${style.comparison}">
          ↑ ${comparison}
        </p>

        <div class="flex items-end gap-[3px] h-7">
          ${[8, 14, 10, 20, 15, 25, 19, 28]
            .map(
              (height) => `
                <span
                  class="w-[3px] rounded-full ${style.bars}"
                  style="height:${height}px"
                ></span>
              `,
            )
            .join("")}
        </div>

      </div>

    </div>
  `;
}