from decimal import Decimal

from django.db import transaction
from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import ActivityFeed
from loyalty.models import LoyaltyTransaction
from pos.models import Customer, Order
from pos.pagination import CustomPagination
from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin

from .models import CustomerAddress, CustomerCreditLimit, CustomerDocument, CustomerNote
from .serializers import (
    CustomerAddressSerializer, CustomerCreditLimitSerializer, CustomerDetailSerializer,
    CustomerDocumentSerializer, CustomerListSerializer, CustomerLoyaltyTransactionSerializer,
    CustomerNoteSerializer, CustomerWriteSerializer,
)
from .services import set_credit_limit
from rest_framework.permissions import IsAuthenticated


class CustomerSecureAPIView:
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"


class CustomerViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    rbac_module = "customers"
    queryset = Customer.objects.all()
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    pagination_class = CustomPagination

    def get_permissions(self):
        if self.action in {"summary", "activity"}:
            self.rbac_action = "view"
        elif self.action == "archive":
            self.rbac_action = "update"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("group").annotate(
            order_count=Count("order", filter=Q(order__tenant=self.request.tenant)),
            total_spent=Coalesce(Sum("order__total", filter=Q(order__tenant=self.request.tenant, order__status="paid")), Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2)), output_field=DecimalField(max_digits=14, decimal_places=2)),
            last_purchase=Max("order__created_at", filter=Q(order__tenant=self.request.tenant)),
        )
        params = self.request.query_params
        if search := params.get("search", "").strip():
            queryset = queryset.filter(Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search) | Q(customer_code__icontains=search))
        if status_filter := params.get("status"):
            queryset = queryset.filter(is_active=status_filter == "active")
        if group_id := params.get("group_id"):
            queryset = queryset.filter(group_id=group_id)
        ordering = params.get("ordering", "name")
        allowed = {"name", "-name", "created_at", "-created_at", "last_purchase", "-last_purchase", "total_spent", "-total_spent", "order_count", "-order_count"}
        return queryset.order_by(ordering if ordering in allowed else "name", "id")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return CustomerWriteSerializer
        if self.action == "retrieve":
            return CustomerDetailSerializer
        return CustomerListSerializer

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)

    def destroy(self, request, *args, **kwargs):
        customer = self.get_object()
        if Order.objects.filter(tenant=request.tenant, customer=customer).exists():
            raise ValidationError({"detail": "Customers with order history cannot be deleted. Archive the customer instead."})
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        customer = self.get_object()
        customer.is_active = False
        customer.save(update_fields=["is_active", "updated_at"])
        return Response(CustomerDetailSerializer(customer, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        customer = self.get_object()
        orders = Order.objects.filter(tenant=request.tenant, customer=customer)
        paid = orders.filter(status="paid")
        totals = paid.aggregate(total_orders=Count("id"), total_spent=Coalesce(Sum("total"), Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2)), output_field=DecimalField(max_digits=14, decimal_places=2)))
        credit = CustomerCreditLimit.objects.filter(tenant=request.tenant, customer=customer).first()
        last_purchase = paid.order_by("-created_at").values("created_at", "order_number", "total").first()
        return Response({
            "customer": CustomerDetailSerializer(customer, context={"request": request}).data,
            "total_orders": totals["total_orders"],
            "total_spent": str(totals["total_spent"]),
            "average_order_value": str(totals["total_spent"] / totals["total_orders"]) if totals["total_orders"] else "0",
            "last_purchase": last_purchase,
            "credit": CustomerCreditLimitSerializer(credit).data if credit else None,
            "loyalty_points": customer.loyalty_points,
        })

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        customer = self.get_object()
        queryset = ActivityFeed.objects.filter(tenant=request.tenant, entity_type__in=["customer", "Customer"], entity_id=customer.id).order_by("-created_at")
        paginator = CustomPagination()
        page = paginator.paginate_queryset(queryset, request)
        rows = [{"id": row.id, "summary": row.summary, "link": row.link, "created_at": row.created_at} for row in page]
        return paginator.get_paginated_response(rows)


class CustomerChildAPIView(CustomerSecureAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "manage"
    def get_customer(self):
        return get_object_or_404(Customer, tenant=self.request.tenant, pk=self.kwargs["customer_id"])


class CustomerAddressListCreateView(CustomerChildAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "manage"
    serializer_class = CustomerAddressSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        return CustomerAddress.objects.filter(tenant=self.request.tenant, customer=self.get_customer())

    @transaction.atomic
    def perform_create(self, serializer):
        customer = self.get_customer()
        if serializer.validated_data.get("is_default"):
            CustomerAddress.objects.filter(tenant=self.request.tenant, customer=customer, kind=serializer.validated_data.get("kind"), is_default=True).update(is_default=False)
        serializer.save(tenant=self.request.tenant, customer=customer)


class CustomerAddressDetailView(CustomerSecureAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "manage"
    serializer_class = CustomerAddressSerializer

    def get_queryset(self):
        return CustomerAddress.objects.filter(tenant=self.request.tenant).select_related("customer")

    @transaction.atomic
    def perform_update(self, serializer):
        address = self.get_object()
        if serializer.validated_data.get("is_default"):
            CustomerAddress.objects.filter(tenant=self.request.tenant, customer=address.customer, kind=serializer.validated_data.get("kind", address.kind), is_default=True).exclude(pk=address.pk).update(is_default=False)
        serializer.save()


class CustomerCreditLimitView(CustomerChildAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "manage"
    def get_permissions(self):
        self.rbac_action = "update" if self.request.method in {"POST", "PUT", "PATCH"} else "view"
        return [permission() for permission in self.permission_classes]

    def get(self, request, customer_id):
        customer = self.get_customer()
        credit, _ = CustomerCreditLimit.objects.get_or_create(tenant=request.tenant, customer=customer)
        return Response(CustomerCreditLimitSerializer(credit).data)

    def post(self, request, customer_id):
        customer = self.get_customer()
        try:
            credit = set_credit_limit(tenant=request.tenant, customer=customer, amount=request.data.get("limit", 0), terms_days=request.data.get("terms_days", 0))
        except ValueError as error:
            raise ValidationError({"detail": str(error)})
        return Response(CustomerCreditLimitSerializer(credit).data)


class CustomerDocumentListCreateView(CustomerChildAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "view"
    serializer_class = CustomerDocumentSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        return CustomerDocument.objects.filter(tenant=self.request.tenant, customer=self.get_customer()).select_related("uploaded_by")

    def perform_create(self, serializer):
        customer = self.get_customer()
        document = serializer.save(tenant=self.request.tenant, customer=customer, uploaded_by=self.request.user)
        if not document.name:
            document.name = document.file.name.rsplit("/", 1)[-1]
            document.save(update_fields=["name"])


class CustomerDocumentDetailView(CustomerSecureAPIView, generics.RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "view"
    serializer_class = CustomerDocumentSerializer

    def get_queryset(self):
        return CustomerDocument.objects.filter(tenant=self.request.tenant).select_related("uploaded_by")


class CustomerDocumentDownloadView(CustomerSecureAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "view"
    def get(self, request, pk):
        document = get_object_or_404(CustomerDocument, tenant=request.tenant, pk=pk)
        if not document.file:
            raise Http404
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.name or document.file.name.rsplit("/", 1)[-1])


class CustomerNoteListCreateView(CustomerChildAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "view"
    serializer_class = CustomerNoteSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        return CustomerNote.objects.filter(tenant=self.request.tenant, customer=self.get_customer()).select_related("created_by")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant, customer=self.get_customer(), created_by=self.request.user)


class CustomerNoteDetailView(CustomerSecureAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "view"
    serializer_class = CustomerNoteSerializer

    def get_queryset(self):
        return CustomerNote.objects.filter(tenant=self.request.tenant).select_related("created_by")


class CustomerLoyaltyHistoryView(CustomerChildAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "view"
    serializer_class = CustomerLoyaltyTransactionSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        return LoyaltyTransaction.objects.filter(tenant=self.request.tenant, customer=self.get_customer()).order_by("-created_at")
