from datetime import timedelta
from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from pos.models import Customer, Order, Product
from saas.permissions import HasActiveTenant, TenantRBACPermission
from .engine import compute_line_tax, compute_order_tax, tax_report
from .models import ProductTaxAssignment, TaxBreakdown, TaxExemption, TaxRate, TaxReport
from .serializers import ProductTaxAssignmentSerializer, TaxBreakdownSerializer, TaxExemptionSerializer, TaxRateSerializer, TaxReportSerializer
from rest_framework.permissions import IsAuthenticated


class TaxDomainPermission(TenantRBACPermission):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "view"
    def has_permission(self, request, view):
        view.rbac_action = "view" if request.method in permissions.SAFE_METHODS else "manage"
        return super().has_permission(request, view)


class TenantTaxAPIView:
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TaxDomainPermission]
    rbac_module = "tax"


class TaxRateListCreateView(TenantTaxAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "view"
    serializer_class = TaxRateSerializer

    def get_queryset(self):
        queryset = TaxRate.objects.filter(tenant=self.request.tenant).select_related("product", "category")
        if product_id := self.request.query_params.get("product_id"):
            queryset = queryset.filter(product_id=product_id)
        if category_id := self.request.query_params.get("category_id"):
            queryset = queryset.filter(category_id=category_id)
        if active := self.request.query_params.get("is_active"):
            queryset = queryset.filter(is_active=active.lower() == "true")
        return queryset.order_by("priority", "name")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class TaxRateDetailView(TenantTaxAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "manage"
    serializer_class = TaxRateSerializer

    def get_queryset(self):
        return TaxRate.objects.filter(tenant=self.request.tenant).select_related("product", "category")


class TaxExemptionListCreateView(TenantTaxAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "manage"
    serializer_class = TaxExemptionSerializer

    def get_queryset(self):
        return TaxExemption.objects.filter(tenant=self.request.tenant).select_related("customer")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class TaxExemptionDetailView(TenantTaxAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "manage"
    serializer_class = TaxExemptionSerializer

    def get_queryset(self):
        return TaxExemption.objects.filter(tenant=self.request.tenant).select_related("customer")


class ProductTaxAssignmentListCreateView(TenantTaxAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "manage"
    serializer_class = ProductTaxAssignmentSerializer

    def get_product(self):
        return get_object_or_404(Product, pk=self.kwargs["product_id"], tenant=self.request.tenant)

    def get_queryset(self):
        return ProductTaxAssignment.objects.filter(tenant=self.request.tenant, product=self.get_product()).select_related("tax_rate")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant, product=self.get_product())


class ProductTaxAssignmentDetailView(TenantTaxAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "manage"
    serializer_class = ProductTaxAssignmentSerializer

    def get_queryset(self):
        return ProductTaxAssignment.objects.filter(tenant=self.request.tenant, product_id=self.kwargs["product_id"]).select_related("tax_rate")


class PreviewLineTaxView(TenantTaxAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "manage"
    def post(self, request):
        product = get_object_or_404(Product, pk=request.data["product_id"], tenant=request.tenant)
        customer = get_object_or_404(Customer, pk=request.data["customer_id"], tenant=request.tenant) if request.data.get("customer_id") else None
        return Response(compute_line_tax(product, Decimal(request.data["subtotal"]), customer))


class ComputeOrderTaxView(TenantTaxAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "manage"
    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id, tenant=request.tenant)
        total = compute_order_tax(order, order.customer)
        return Response({"order": order.order_number, "tax": str(total), "total": str(order.total), "breakdown": TaxBreakdownSerializer(order.tax_breakdowns.all(), many=True).data})


class TaxBreakdownByOrderView(TenantTaxAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "view"
    serializer_class = TaxBreakdownSerializer

    def get_queryset(self):
        queryset = TaxBreakdown.objects.filter(tenant=self.request.tenant).select_related("order", "tax_rate")
        if order_id := self.request.query_params.get("order_id"):
            queryset = queryset.filter(order_id=order_id)
        return queryset.order_by("-created_at")


class TaxReportView(TenantTaxAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "tax"
    rbac_action = "view"
    rbac_action = "report"

    def get(self, request):
        end = request.query_params.get("end") or timezone.now().date()
        start = request.query_params.get("start") or (timezone.now().date() - timedelta(days=30))
        data = tax_report(start, end, tenant=request.tenant)
        report = TaxReport.objects.create(tenant=request.tenant, period_start=start, period_end=end, total_taxable=Decimal(data["total_taxable"]), total_tax_collected=Decimal(data["total_tax_collected"]), breakdown_json=str(data["by_rate"]))
        data["report_id"] = report.id
        return Response(data)
