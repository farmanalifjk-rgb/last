import datetime
from decimal import Decimal

from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from enterprise.models import Warehouse, WarehouseStock
from pos.models import Product, StockAdjustment, StockMovement
from pos.pagination import CustomPagination
from saas.permissions import HasActiveTenant, TenantRBACPermission

from .models import ABCAnalysis, BinLocation, CycleCount, InventoryAgingSnapshot, ReorderRule, StockReservation
from .serializers import (
    ABCAnalysisSerializer, AdjustmentRequestSerializer, BinLocationSerializer, CycleCountSerializer,
    InventoryAgingSerializer, ReorderRuleSerializer, StockMovementSerializer, StockReservationSerializer,
    WarehouseSerializer, WarehouseStockSerializer,
)
from .services import available_stock, compute_abc, compute_aging, create_adjustment, products_below_reorder, release_reservation, reserve_stock, run_cycle_count
from rest_framework.permissions import IsAuthenticated


class TenantInventoryAPIView:
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"


class TenantInventoryListCreateView(TenantInventoryAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    pagination_class = CustomPagination

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class TenantInventoryDetailView(TenantInventoryAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    pass


class InventoryOverviewView(TenantInventoryAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    def get(self, request):
        tenant = request.tenant
        stocks = WarehouseStock.objects.filter(tenant=tenant).select_related("product")
        total_units = stocks.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        total_value = sum((stock.quantity * stock.product.cost_price for stock in stocks), Decimal("0"))
        alerts = products_below_reorder(tenant)
        active_reservations = StockReservation.objects.filter(tenant=tenant, status=StockReservation.STATUS_ACTIVE).count()
        return Response({
            "total_units": str(total_units), "total_stock_value": str(total_value),
            "warehouse_count": Warehouse.objects.filter(tenant=tenant, is_active=True).count(),
            "low_stock_count": len(alerts), "out_of_stock_count": stocks.filter(quantity__lte=0).count(),
            "active_reservation_count": active_reservations,
            "recent_movements": StockMovementSerializer(StockMovement.objects.filter(tenant=tenant).select_related("product", "warehouse")[:8], many=True).data,
            "reorder_alerts": alerts[:8],
        })


class WarehouseListCreateView(TenantInventoryListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = WarehouseSerializer

    def get_queryset(self):
        queryset = Warehouse.objects.filter(tenant=self.request.tenant).select_related("store")
        if active := self.request.query_params.get("is_active"):
            queryset = queryset.filter(is_active=active.lower() == "true")
        if search := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(name__icontains=search) | queryset.filter(code__icontains=search)
        return queryset.order_by("name")


class WarehouseDetailView(TenantInventoryDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = WarehouseSerializer

    def get_queryset(self):
        return Warehouse.objects.filter(tenant=self.request.tenant).select_related("store")


class WarehouseArchiveView(TenantInventoryAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    rbac_action = "manage"

    def post(self, request, pk):
        warehouse = get_object_or_404(Warehouse, tenant=request.tenant, pk=pk)
        if warehouse.stock_levels.filter(quantity__gt=0).exists():
            return Response({"detail": "A warehouse with on-hand stock cannot be archived."}, status=status.HTTP_400_BAD_REQUEST)
        warehouse.is_active = False
        warehouse.save(update_fields=["is_active"])
        return Response(WarehouseSerializer(warehouse, context={"request": request}).data)


class StockListView(TenantInventoryAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "view"
    serializer_class = WarehouseStockSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = WarehouseStock.objects.filter(tenant=self.request.tenant).select_related("warehouse", "product", "product__category")
        filters = self.request.query_params
        if filters.get("warehouse_id"):
            queryset = queryset.filter(warehouse_id=filters["warehouse_id"])
        if filters.get("product_id"):
            queryset = queryset.filter(product_id=filters["product_id"])
        if filters.get("category_id"):
            queryset = queryset.filter(product__category_id=filters["category_id"])
        if filters.get("status") == "out":
            queryset = queryset.filter(quantity__lte=0)
        elif filters.get("status") == "low":
            queryset = queryset.filter(quantity__gt=0, quantity__lte=F("reorder_point"))
        if search := filters.get("search", "").strip():
            from django.db.models import Q
            queryset = queryset.filter(Q(product__name__icontains=search) | Q(product__sku__icontains=search) | Q(warehouse__name__icontains=search) | Q(bin_location__icontains=search))
        ordering = filters.get("ordering", "product__name")
        return queryset.order_by(ordering if ordering.lstrip("-") in {"quantity", "reorder_point", "updated_at", "product__name", "warehouse__name"} else "product__name")


class MovementListView(TenantInventoryAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = StockMovementSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = StockMovement.objects.filter(tenant=self.request.tenant).select_related("product", "warehouse")
        params = self.request.query_params
        for key, field in {"product_id": "product_id", "warehouse_id": "warehouse_id", "movement_type": "movement_type"}.items():
            if params.get(key):
                queryset = queryset.filter(**{field: params[key]})
        if params.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=params["date_to"])
        return queryset.order_by("-created_at")


class BinLocationListCreateView(TenantInventoryListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = BinLocationSerializer

    def get_queryset(self):
        queryset = BinLocation.objects.filter(tenant=self.request.tenant).select_related("warehouse")
        if warehouse_id := self.request.query_params.get("warehouse_id"):
            queryset = queryset.filter(warehouse_id=warehouse_id)
        if search := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(code__icontains=search)
        return queryset.order_by("code")


class BinLocationDetailView(TenantInventoryDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = BinLocationSerializer
    def get_queryset(self): return BinLocation.objects.filter(tenant=self.request.tenant)


class StockReservationListCreateView(TenantInventoryListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = StockReservationSerializer

    def get_queryset(self):
        queryset = StockReservation.objects.filter(tenant=self.request.tenant).select_related("product", "warehouse", "reserved_by")
        for key, field in {"product_id": "product_id", "warehouse_id": "warehouse_id", "status": "status"}.items():
            if self.request.query_params.get(key): queryset = queryset.filter(**{field: self.request.query_params[key]})
        return queryset.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reservation = reserve_stock(tenant=request.tenant, product_id=serializer.validated_data["product"].id, warehouse_id=serializer.validated_data.get("warehouse").id if serializer.validated_data.get("warehouse") else None, quantity=serializer.validated_data["quantity"], reference=serializer.validated_data.get("reference", ""), reserved_by=request.user)
        return Response(self.get_serializer(reservation).data, status=status.HTTP_201_CREATED)


class ReleaseReservationView(TenantInventoryAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "update"
    def post(self, request, pk):
        reservation = release_reservation(tenant=request.tenant, reservation_id=pk, user=request.user)
        return Response(StockReservationSerializer(reservation, context={"request": request}).data)


class AvailableStockView(TenantInventoryAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    def get(self, request):
        product = get_object_or_404(Product, tenant=request.tenant, pk=request.query_params.get("product"))
        warehouse = get_object_or_404(Warehouse, tenant=request.tenant, pk=request.query_params["warehouse_id"]) if request.query_params.get("warehouse_id") else None
        return Response({"product": product.id, "warehouse": warehouse.id if warehouse else None, "available": str(available_stock(request.tenant, product, warehouse))})


class AdjustmentListCreateView(TenantInventoryAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    def get_permissions(self):
        # DRF evaluates permissions before dispatching to get()/post().  Choose
        # the verb-specific action here so an inventory viewer cannot create a
        # correction simply because rbac_action was changed too late in post().
        self.rbac_action = "manage" if self.request.method == "POST" else "view"
        return [permission() for permission in self.permission_classes]

    def get(self, request):
        """Adjustments of the active tenant, newest first.

        Filters: ?search= (adjustment no., reason, note, product name/SKU),
        ?reason= (exact, case-insensitive), ?date_from= / ?date_to=
        (YYYY-MM-DD, inclusive, server time zone).
        """
        queryset = StockAdjustment.objects.filter(tenant=request.tenant).prefetch_related("items__product")
        params = request.query_params
        if search := params.get("search", "").strip():
            matching = StockAdjustment.objects.filter(tenant=request.tenant).filter(
                Q(adjustment_number__icontains=search) | Q(reason__icontains=search) | Q(note__icontains=search)
                | Q(items__product__name__icontains=search) | Q(items__product__sku__icontains=search)
            ).values("pk")
            queryset = queryset.filter(pk__in=matching)
        if reason := params.get("reason", "").strip():
            queryset = queryset.filter(reason__iexact=reason)
        for key, lookup in (("date_from", "created_at__date__gte"), ("date_to", "created_at__date__lte")):
            if raw := params.get(key, "").strip():
                try:
                    value = datetime.date.fromisoformat(raw)
                except ValueError:
                    return Response({key: ["Use the YYYY-MM-DD format."]}, status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(**{lookup: value})
        paginator = CustomPagination(); page = paginator.paginate_queryset(queryset.order_by("-created_at", "-id"), request)
        rows = [{"id": row.id, "adjustment_number": row.adjustment_number, "adjustment_type": row.adjustment_type, "reason": row.reason, "note": row.note, "created_at": row.created_at, "items": [{"product": item.product_id, "product_name": item.product.name, "quantity": item.quantity, "previous_stock": item.previous_stock, "new_stock": item.new_stock} for item in row.items.all()]} for row in page]
        return paginator.get_paginated_response(rows)

    def post(self, request):
        serializer = AdjustmentRequestSerializer(data=request.data, context={"request": request}); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        adjustment, movement = create_adjustment(tenant=request.tenant, product_id=data["product"].id, warehouse_id=data.get("warehouse").id if data.get("warehouse") else None, new_quantity=data.get("new_quantity"), adjustment_quantity=data.get("adjustment_quantity"), reason=data["reason"], note=data.get("note", ""), user=request.user)
        return Response({"adjustment_number": adjustment.adjustment_number, "movement": StockMovementSerializer(movement, context={"request": request}).data}, status=status.HTTP_201_CREATED)


class CycleCountListCreateView(TenantInventoryListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = CycleCountSerializer
    def get_queryset(self): return CycleCount.objects.filter(tenant=self.request.tenant).select_related("warehouse", "started_by").prefetch_related("lines__product").order_by("-created_at")
    def perform_create(self, serializer): serializer.save(tenant=self.request.tenant, started_by=self.request.user)


class CycleCountDetailView(TenantInventoryDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = CycleCountSerializer
    def get_queryset(self): return CycleCount.objects.filter(tenant=self.request.tenant).select_related("warehouse").prefetch_related("lines__product")


class RunCycleCountView(TenantInventoryAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    rbac_action = "manage"
    def post(self, request, pk):
        count, movements = run_cycle_count(tenant=request.tenant, count_id=pk, counted_lines=request.data.get("lines", []), user=request.user)
        return Response({"count": CycleCountSerializer(count, context={"request": request}).data, "movements": StockMovementSerializer(movements, many=True, context={"request": request}).data})


class ReorderRuleListCreateView(TenantInventoryListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = ReorderRuleSerializer
    def get_queryset(self):
        queryset = ReorderRule.objects.filter(tenant=self.request.tenant).select_related("product", "warehouse", "supplier")
        if search := self.request.query_params.get("search", "").strip(): queryset = queryset.filter(product__name__icontains=search)
        return queryset.order_by("product__name")


class ReorderRuleDetailView(TenantInventoryDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "manage"
    serializer_class = ReorderRuleSerializer
    def get_queryset(self): return ReorderRule.objects.filter(tenant=self.request.tenant).select_related("product", "warehouse", "supplier")


class ReorderAlertsView(TenantInventoryAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "view"
    def get(self, request): return Response(products_below_reorder(request.tenant))


class ABCView(TenantInventoryAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "view"
    serializer_class = ABCAnalysisSerializer; pagination_class = CustomPagination
    def get_queryset(self):
        compute_abc(self.request.tenant)
        queryset = ABCAnalysis.objects.filter(tenant=self.request.tenant).select_related("product")
        if classification := self.request.query_params.get("classification"): queryset = queryset.filter(abc_class=classification)
        return queryset.order_by("-annual_value")


class AgingView(TenantInventoryAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"
    rbac_action = "view"
    serializer_class = InventoryAgingSerializer; pagination_class = CustomPagination
    def get_queryset(self):
        compute_aging(self.request.tenant)
        queryset = InventoryAgingSnapshot.objects.filter(tenant=self.request.tenant).select_related("product")
        if bucket := self.request.query_params.get("bucket"): queryset = queryset.filter(bucket=bucket)
        return queryset.order_by("bucket", "product__name")

