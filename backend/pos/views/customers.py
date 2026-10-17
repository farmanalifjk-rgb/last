from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, ValidationError

from ..models import Customer, DraftOrder
from ..serializers import CustomerSerializer
from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin


class CustomerViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    rbac_module = "customers"
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]


class CustomerListView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "view"

    def get(self, request):
        customers = Customer.objects.filter(tenant=request.tenant)
        return Response([{"id": c.id, "name": c.name, "phone": c.phone} for c in customers])


class CustomerCreateView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "create"

    def post(self, request):
        customer = Customer.objects.create(
            tenant=request.tenant,
            name=request.data.get("name"),
            phone=request.data.get("phone", ""),
        )
        return Response({"id": customer.id, "name": customer.name})


class AssignCustomerView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "customers"
    rbac_action = "update"

    def post(self, request):
        draft = DraftOrder.objects.filter(id=request.data.get("draft_id"), tenant=request.tenant).first()
        if draft is None:
            raise NotFound("Draft order was not found.")
        customer = Customer.objects.filter(id=request.data.get("customer_id"), tenant=request.tenant).first()
        if customer is None:
            raise ValidationError("Customer is not in the active tenant.")
        draft.customer = customer
        draft.save(update_fields=["customer"])
        return Response({"success": True})
