from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from saas.permissions import HasActiveTenant, TenantRBACPermission
from pos.models import (Product, PurchaseReturnItem, Supplier,PurchaseOrder,PurchaseOrderItem,PurchaseReturn,)
from ..serializers import PurchaseOrderCreateSerializer, PurchaseOrderDetailSerializer, PurchaseOrderListSerializer, ReceivePurchaseSerializer
from ..serializers import PurchaseReturnSerializer, PurchaseReturnListSerializer, PurchaseReturnDetailSerializer
from ..filters import get_filtered_purchase_returns, get_purchase_return_summary
from ..services.inventory import update_stock
from rest_framework.response import Response
# pdf_helpers: no symbols used
from ..helpers import build_export_filename
from ..Order_no_generator import generate_purchase_order_number



class SupplierListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "manage"

    def get(self, request):

        suppliers = Supplier.objects.filter(tenant=request.tenant, is_active=True)

        serializer = SupplierSerializer(
            suppliers,
            many=True
        )

        return Response(serializer.data)

    def post(self, request):

        serializer = SupplierSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        serializer.save(tenant=request.tenant)

        return Response(
            serializer.data,
            status=201
        )
    

class SupplierDetailView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "manage"

    def get_object(self, pk):

        return get_object_or_404(
            Supplier,
            pk=pk,
            tenant=request.tenant,
        )

    def get(self, request, pk):

        serializer = SupplierSerializer(
            self.get_object(pk)
        )

        return Response(serializer.data)

    def put(self, request, pk):

        supplier = self.get_object(pk)

        serializer = SupplierSerializer(
            supplier,
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        serializer.save()

        return Response(serializer.data)

    def delete(self, request, pk):

        supplier = self.get_object(pk)

        supplier.is_active = False
        supplier.save()

        return Response(status=204) 


class PurchaseOrderCreateView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    @transaction.atomic
    def post(self, request):

        serializer = PurchaseOrderCreateSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        data = serializer.validated_data
        
        supplier = Supplier.objects.get(
            pk=data["supplier"],
            tenant=request.tenant,
        )

        # Tenant-scoped atomic PO creation; warehouse required.
        from enterprise.models import Warehouse
        warehouse = Warehouse.objects.filter(tenant=request.tenant, is_active=True).first()
        if not warehouse:
            # Fallback to any warehouse for this tenant to satisfy PROTECT constraint
            warehouse = get_object_or_404(Warehouse, tenant=request.tenant)

        purchase = PurchaseOrder.objects.create(
            tenant=request.tenant,
            supplier=supplier,
            warehouse=warehouse,
            order_number=generate_purchase_order_number(tenant=request.tenant),
            note=data.get("note", "")
        )

        subtotal = Decimal("0.00")

        for item in data["items"]:

            product = Product.objects.get(
                pk=item["product"],
                tenant=request.tenant,
            )

            qty = item["quantity"]

            cost = item["unit_cost"]

            line_total = qty * cost

            subtotal += line_total

            PurchaseOrderItem.objects.create(
                tenant=request.tenant,
                purchase_order=purchase,
                product=product,
                quantity=qty,
                unit_cost=cost,
                subtotal=line_total,
            )

        purchase.subtotal = subtotal

        purchase.tax = Decimal("0.00")

        purchase.total = subtotal

        purchase.save()

        return Response({
        
            "success": True,

            "purchase_order": purchase.order_number,

            "status": purchase.status,

        })
    

class PurchaseOrderListView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request):

        purchases = PurchaseOrder.objects.filter(tenant=request.tenant).select_related(
            "supplier"
        ).prefetch_related(
            "items"
        ).order_by("-id")

        serializer = PurchaseOrderListSerializer(
            purchases,
            many=True
        )

        return Response(serializer.data)  


class PurchaseOrderDetailView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request, order_number):

        purchase = get_object_or_404(PurchaseOrder, order_number=order_number, tenant=request.tenant)

        serializer = PurchaseOrderDetailSerializer(
            purchase
        )

        return Response(serializer.data)


class CancelPurchaseOrderView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "update"

    @transaction.atomic
    def post(self, request, order_number):

        purchase = get_object_or_404(PurchaseOrder, order_number=order_number, tenant=request.tenant)

        if purchase.status == "received":
            raise serializers.ValidationError(
                "Received purchase orders cannot be cancelled."
            )

        if purchase.status == "cancelled":
            raise serializers.ValidationError(
                "Purchase order is already cancelled."
            )

        purchase.status = "cancelled"

        purchase.save(update_fields=["status"])

        return Response({
            "success": True,
            "status": purchase.status
        })
