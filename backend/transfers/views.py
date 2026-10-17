from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from enterprise.models import Warehouse
from pos.models import Product
from saas.permissions import HasActiveTenant, TenantRBACPermission

from .models import BinReplenishmentTask, PutAwayRule, PutAwayTask, StockTransfer
from .serializers import BinReplenishmentTaskSerializer, PutAwayRuleSerializer, PutAwayTaskSerializer, StockTransferSerializer, TransferCreateSerializer
from .services import create_transfer, generate_replenishment_tasks, receive_transfer, suggest_putaway
from rest_framework.permissions import IsAuthenticated


class TenantTransferAPIView:
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "inventory"


class StockTransferListCreateView(TenantTransferAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "transfers"
    rbac_action = "manage"
    def get(self, request):
        queryset = StockTransfer.objects.filter(tenant=request.tenant).select_related("source_warehouse", "destination_warehouse").prefetch_related("items__product")
        if status_filter := request.query_params.get("status"): queryset = queryset.filter(status=status_filter)
        if warehouse_id := request.query_params.get("warehouse_id"): queryset = queryset.filter(source_warehouse_id=warehouse_id) | queryset.filter(destination_warehouse_id=warehouse_id)
        return Response(StockTransferSerializer(queryset.order_by("-created_at"), many=True, context={"request": request}).data)

    def post(self, request):
        serializer = TransferCreateSerializer(data=request.data, context={"request": request}); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        transfer = create_transfer(tenant=request.tenant, source=data["source_warehouse"], destination=data["destination_warehouse"], lines=data["items"], note=data.get("note", ""), user=request.user)
        return Response(StockTransferSerializer(transfer, context={"request": request}).data, status=status.HTTP_201_CREATED)


class StockTransferDetailView(TenantTransferAPIView, generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "transfers"
    rbac_action = "manage"
    serializer_class = StockTransferSerializer
    def get_queryset(self): return StockTransfer.objects.filter(tenant=self.request.tenant).select_related("source_warehouse", "destination_warehouse").prefetch_related("items__product")


class ReceiveTransferView(TenantTransferAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "transfers"
    rbac_action = "manage"
    rbac_action = "update"
    def post(self, request, pk):
        transfer = receive_transfer(tenant=request.tenant, transfer_id=pk, received_lines=request.data.get("lines"), user=request.user)
        return Response(StockTransferSerializer(transfer, context={"request": request}).data)


class PutAwayRuleListCreateView(TenantTransferAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "transfers"
    rbac_action = "manage"
    serializer_class = PutAwayRuleSerializer
    def get_queryset(self): return PutAwayRule.objects.filter(tenant=self.request.tenant).select_related("warehouse", "target_bin")
    def perform_create(self, serializer): serializer.save(tenant=self.request.tenant)


class SuggestPutAwayView(TenantTransferAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "transfers"
    rbac_action = "manage"
    rbac_action = "create"
    def post(self, request):
        warehouse = get_object_or_404(Warehouse, tenant=request.tenant, pk=request.data["warehouse_id"])
        product = get_object_or_404(Product, tenant=request.tenant, pk=request.data["product_id"])
        task = suggest_putaway(tenant=request.tenant, warehouse=warehouse, product=product, quantity=Decimal(request.data.get("quantity", 1)), reference=request.data.get("reference", ""))
        return Response(PutAwayTaskSerializer(task, context={"request": request}).data, status=status.HTTP_201_CREATED)


class PutAwayTaskListView(TenantTransferAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "transfers"
    rbac_action = "manage"
    serializer_class = PutAwayTaskSerializer
    def get_queryset(self):
        queryset = PutAwayTask.objects.filter(tenant=self.request.tenant).select_related("warehouse", "product", "completed_by")
        if warehouse_id := self.request.query_params.get("warehouse_id"): queryset = queryset.filter(warehouse_id=warehouse_id)
        if status_filter := self.request.query_params.get("status"): queryset = queryset.filter(status=status_filter)
        return queryset.order_by("-created_at")


class CompletePutAwayView(TenantTransferAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "transfers"
    rbac_action = "manage"
    rbac_action = "update"
    def post(self, request, pk):
        task = get_object_or_404(PutAwayTask, tenant=request.tenant, pk=pk)
        if task.status != PutAwayTask.STATUS_PENDING: return Response({"detail": "Only pending tasks may be completed."}, status=status.HTTP_400_BAD_REQUEST)
        task.status = PutAwayTask.STATUS_DONE; task.completed_at = timezone.now(); task.completed_by = request.user
        task.save(update_fields=["status", "completed_at", "completed_by"])
        return Response(PutAwayTaskSerializer(task, context={"request": request}).data)


class ReplenishmentGenerateView(TenantTransferAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "transfers"
    rbac_action = "manage"
    rbac_action = "create"
    def post(self, request, pk):
        warehouse = get_object_or_404(Warehouse, tenant=request.tenant, pk=pk)
        tasks = generate_replenishment_tasks(tenant=request.tenant, warehouse=warehouse, low_threshold=Decimal(request.data.get("threshold", 5)))
        return Response({"created": [task.id for task in tasks]})


class ReplenishmentListView(TenantTransferAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "transfers"
    rbac_action = "view"
    serializer_class = BinReplenishmentTaskSerializer
    def get_queryset(self):
        queryset = BinReplenishmentTask.objects.filter(tenant=self.request.tenant).select_related("warehouse", "product", "from_bin", "to_bin")
        if warehouse_id := self.request.query_params.get("warehouse_id"): queryset = queryset.filter(warehouse_id=warehouse_id)
        if status_filter := self.request.query_params.get("status"): queryset = queryset.filter(status=status_filter)
        return queryset.order_by("-created_at")
