from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from pos.models import Warehouse, WarehouseStock
from enterprise.serializers import (
    WarehouseSerializer, WarehouseStockSerializer,
)
from saas.permissions import HasActiveTenant, TenantRBACPermission


class WarehouseListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"
    serializer_class = WarehouseSerializer

    def get_queryset(self):
        return Warehouse.objects.filter(tenant=self.request.tenant).select_related("store")


class WarehouseStockListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    serializer_class = WarehouseStockSerializer

    def get_queryset(self):
        return WarehouseStock.objects.filter(warehouse__tenant=self.request.tenant).select_related("warehouse", "product").filter(warehouse_id=self.kwargs["warehouse_id"])

