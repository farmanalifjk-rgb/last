from django.urls import path

from .views import (
    ABCView, AdjustmentListCreateView, AgingView, AvailableStockView, BinLocationDetailView,
    BinLocationListCreateView, CycleCountDetailView, CycleCountListCreateView, InventoryOverviewView,
    MovementListView, ReorderAlertsView, ReorderRuleDetailView, ReorderRuleListCreateView,
    ReleaseReservationView, RunCycleCountView, StockListView, StockReservationListCreateView,
    WarehouseArchiveView, WarehouseDetailView, WarehouseListCreateView,
)

urlpatterns = [
    path("overview/", InventoryOverviewView.as_view()),
    path("stock/", StockListView.as_view()),
    path("movements/", MovementListView.as_view()),
    path("warehouses/", WarehouseListCreateView.as_view()),
    path("warehouses/<int:pk>/", WarehouseDetailView.as_view()),
    path("warehouses/<int:pk>/archive/", WarehouseArchiveView.as_view()),
    path("bins/", BinLocationListCreateView.as_view()),
    path("bins/<int:pk>/", BinLocationDetailView.as_view()),
    path("reservations/", StockReservationListCreateView.as_view()),
    path("reservations/<int:pk>/release/", ReleaseReservationView.as_view()),
    path("available/", AvailableStockView.as_view()),
    path("adjustments/", AdjustmentListCreateView.as_view()),
    path("cycle-counts/", CycleCountListCreateView.as_view()),
    path("cycle-counts/<int:pk>/", CycleCountDetailView.as_view()),
    path("cycle-counts/<int:pk>/run/", RunCycleCountView.as_view()),
    path("reorder-rules/", ReorderRuleListCreateView.as_view()),
    path("reorder-rules/<int:pk>/", ReorderRuleDetailView.as_view()),
    path("reorder-alerts/", ReorderAlertsView.as_view()),
    path("abc/", ABCView.as_view()),
    path("aging/", AgingView.as_view()),
]
