from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from pos.models import PurchaseOrder, Supplier
from pos.pagination import CustomPagination
from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin
from operations.services import request_approval

from .models import GoodsReceipt, PurchaseReturn, SupplierContact
from .purchasing_serializers import (
    GoodsReceiptSerializer, PurchaseOrderDetailSerializer, PurchaseOrderListSerializer,
    PurchaseOrderWriteSerializer, PurchaseReturnSerializer, PurchaseReturnWriteSerializer,
    ReceiptWriteSerializer, SupplierContactSerializer, SupplierDetailSerializer,
    SupplierListSerializer, SupplierPortalTokenSerializer, SupplierWriteSerializer,
)
from .purchasing_services import (
    cancel_purchase_order, cancel_purchase_return, confirm_purchase_order, create_purchase_order,
    create_purchase_return, create_receipt, issue_supplier_portal_token, process_purchase_return,
    save_supplier_contact, update_draft_purchase_order,
)


class SupplierSecureAPIView:
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "suppliers"


class PurchasingSecureAPIView:
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "purchasing"


class SupplierViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "suppliers"
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related("contacts")
        params = self.request.query_params
        if search := params.get("search", "").strip():
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(company__icontains=search) | Q(contact_person__icontains=search)
                | Q(email__icontains=search) | Q(phone__icontains=search) | Q(tax_number__icontains=search)
            )
        if supplier_status := params.get("status"):
            queryset = queryset.filter(is_active=supplier_status == "active")
        ordering = params.get("ordering", "name")
        allowed = {"name", "-name", "company", "-company", "created_at", "-created_at", "updated_at", "-updated_at"}
        return queryset.order_by(ordering if ordering in allowed else "name", "id")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return SupplierWriteSerializer
        return SupplierDetailSerializer if self.action == "retrieve" else SupplierListSerializer

    def get_permissions(self):
        if self.action == "archive":
            self.rbac_action = "update"
        elif self.action == "summary":
            self.rbac_action = "view"
        elif self.action == "portal_token":
            self.rbac_action = "update"
        return [permission() for permission in self.permission_classes]

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        supplier = self.get_object()
        supplier.is_active = False
        supplier.save(update_fields=["is_active", "updated_at"])
        return Response(SupplierDetailSerializer(supplier, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        supplier = self.get_object()
        orders = PurchaseOrder.objects.filter(tenant=request.tenant, supplier=supplier)
        stats = orders.aggregate(
            total_purchase_value=Coalesce(Sum("total"), Value(Decimal("0"))),
            purchase_order_count=Count("id"),
            open_purchase_orders=Count("id", filter=Q(status="ordered")),
            received_purchase_orders=Count("id", filter=Q(status="received")),
        )
        returns = PurchaseReturn.objects.filter(tenant=request.tenant, purchase_order__supplier=supplier, status=PurchaseReturn.STATUS_RETURNED)
        return Response({
            "supplier": SupplierDetailSerializer(supplier, context={"request": request}).data,
            "total_purchase_value": str(stats["total_purchase_value"]),
            "purchase_order_count": stats["purchase_order_count"],
            "open_purchase_orders": stats["open_purchase_orders"],
            "received_purchase_orders": stats["received_purchase_orders"],
            "return_total": str(returns.aggregate(total=Coalesce(Sum("total_amount"), Value(Decimal("0"))))["total"]),
            "last_purchase": orders.order_by("-created_at").values("id", "order_number", "status", "total", "created_at").first(),
        })

    @action(detail=True, methods=["post"], url_path="portal-token")
    def portal_token(self, request, pk=None):
        token = issue_supplier_portal_token(tenant=request.tenant, supplier=self.get_object())
        return Response(SupplierPortalTokenSerializer(token).data, status=status.HTTP_201_CREATED)


class SupplierChildAPIView(SupplierSecureAPIView):
    def get_supplier(self):
        return get_object_or_404(Supplier, tenant=self.request.tenant, pk=self.kwargs["supplier_id"])


class SupplierContactListCreateView(SupplierChildAPIView, generics.ListCreateAPIView):
    serializer_class = SupplierContactSerializer
    pagination_class = CustomPagination

    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "update"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        return SupplierContact.objects.filter(tenant=self.request.tenant, supplier=self.get_supplier()).select_related("supplier")

    def perform_create(self, serializer):
        save_supplier_contact(tenant=self.request.tenant, supplier=self.get_supplier(), serializer=serializer)


class SupplierContactDetailView(SupplierSecureAPIView, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SupplierContactSerializer

    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "update"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        return SupplierContact.objects.filter(tenant=self.request.tenant).select_related("supplier")

    @transaction.atomic
    def perform_update(self, serializer):
        contact = self.get_object()
        if serializer.validated_data.get("is_primary"):
            SupplierContact.objects.filter(tenant=self.request.tenant, supplier=contact.supplier, is_primary=True).exclude(pk=contact.pk).update(is_primary=False)
        serializer.save()


class PurchaseOrderViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.all()
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "purchasing"
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    def get_permissions(self):
        if self.action == "confirm":
            self.rbac_action = "approve"
        elif self.action == "cancel":
            self.rbac_action = "update"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("supplier", "warehouse").prefetch_related("items", "items__product")
        params = self.request.query_params
        if search := params.get("search", "").strip():
            queryset = queryset.filter(Q(order_number__icontains=search) | Q(supplier__name__icontains=search))
        for query_key, field in (("supplier_id", "supplier_id"), ("warehouse_id", "warehouse_id"), ("status", "status"), ("product_id", "items__product_id")):
            if value := params.get(query_key):
                queryset = queryset.filter(**{field: value})
        if date_from := params.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to := params.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=date_to)
        ordering = params.get("ordering", "-created_at")
        allowed = {"created_at", "-created_at", "expected_date", "-expected_date", "total", "-total", "order_number", "-order_number"}
        return queryset.order_by(ordering if ordering in allowed else "-created_at", "-id").distinct()

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return PurchaseOrderWriteSerializer
        return PurchaseOrderDetailSerializer if self.action == "retrieve" else PurchaseOrderListSerializer

    def create(self, request, *args, **kwargs):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        order = create_purchase_order(tenant=request.tenant, payload=payload.validated_data)
        return Response(PurchaseOrderDetailSerializer(order, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        order = update_draft_purchase_order(tenant=request.tenant, order=self.get_object(), payload=payload.validated_data)
        return Response(PurchaseOrderDetailSerializer(order, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        order = self.get_object()
        approval, _ = request_approval(
            tenant=request.tenant,
            module="purchase_order",
            action="confirm",
            source=order,
            requested_by=request.user,
            amount=order.total,
            reference_str=order.order_number,
            request=request,
        )
        if approval is not None:
            return Response(
                {
                    "detail": "Purchase order confirmation requires approval.",
                    "approval_request_id": approval.id,
                    "approval_status": approval.status,
                    "order": PurchaseOrderDetailSerializer(order, context={"request": request}).data,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        return Response(PurchaseOrderDetailSerializer(confirm_purchase_order(tenant=request.tenant, order=order), context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(PurchaseOrderDetailSerializer(cancel_purchase_order(tenant=request.tenant, order=self.get_object()), context={"request": request}).data)


class ReceiptListCreateView(PurchasingSecureAPIView, generics.ListCreateAPIView):
    serializer_class = GoodsReceiptSerializer
    pagination_class = CustomPagination

    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "receive"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        query = GoodsReceipt.objects.filter(tenant=self.request.tenant).select_related("purchase_order", "purchase_order__supplier", "purchase_order__warehouse", "received_by").prefetch_related("lines", "lines__purchase_order_item", "lines__purchase_order_item__product", "lines__batch")
        if order_id := self.request.query_params.get("purchase_order_id"):
            query = query.filter(purchase_order_id=order_id)
        if supplier_id := self.request.query_params.get("supplier_id"):
            query = query.filter(purchase_order__supplier_id=supplier_id)
        return query

    def create(self, request, *args, **kwargs):
        payload = ReceiptWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        if not (order_id := request.data.get("purchase_order_id")):
            raise ValidationError({"purchase_order_id": "A purchase_order_id is required."})
        order = get_object_or_404(PurchaseOrder, tenant=request.tenant, pk=order_id)
        receipt = create_receipt(tenant=request.tenant, purchase_order=order, payload=payload.validated_data, user=request.user)
        return Response(GoodsReceiptSerializer(receipt, context={"request": request}).data, status=status.HTTP_201_CREATED)


class ReceiptDetailView(PurchasingSecureAPIView, generics.RetrieveAPIView):
    serializer_class = GoodsReceiptSerializer

    def get_queryset(self):
        return GoodsReceipt.objects.filter(tenant=self.request.tenant).select_related("purchase_order", "purchase_order__supplier", "purchase_order__warehouse", "received_by").prefetch_related("lines", "lines__purchase_order_item", "lines__purchase_order_item__product", "lines__batch")


class PurchaseReturnViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PurchaseReturn.objects.all()
    serializer_class = PurchaseReturnSerializer
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "purchasing"
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if self.action in {"create", "process", "cancel"}:
            self.rbac_action = "return"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        query = super().get_queryset().select_related("purchase_order", "purchase_order__supplier", "purchase_order__warehouse").prefetch_related("lines", "lines__purchase_order_item", "lines__purchase_order_item__product", "lines__receipt_line")
        params = self.request.query_params
        if order_id := params.get("purchase_order_id"):
            query = query.filter(purchase_order_id=order_id)
        if supplier_id := params.get("supplier_id"):
            query = query.filter(purchase_order__supplier_id=supplier_id)
        if return_status := params.get("status"):
            query = query.filter(status=return_status)
        return query

    def create(self, request, *args, **kwargs):
        payload = PurchaseReturnWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        if not (order_id := request.data.get("purchase_order_id")):
            raise ValidationError({"purchase_order_id": "A purchase_order_id is required."})
        order = get_object_or_404(PurchaseOrder, tenant=request.tenant, pk=order_id)
        purchase_return = create_purchase_return(tenant=request.tenant, purchase_order=order, payload=payload.validated_data, user=request.user)
        return Response(PurchaseReturnSerializer(purchase_return, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        return Response(PurchaseReturnSerializer(process_purchase_return(tenant=request.tenant, purchase_return=self.get_object(), user=request.user), context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(PurchaseReturnSerializer(cancel_purchase_return(tenant=request.tenant, purchase_return=self.get_object()), context={"request": request}).data)
