from django.urls import path

from enterprise.views import (
    WarehouseListCreateView, WarehouseStockListView,
)

urlpatterns = [
    path("enterprise/warehouses/", WarehouseListCreateView.as_view()),
    path("enterprise/warehouses/<int:warehouse_id>/stock/", WarehouseStockListView.as_view()),
]
