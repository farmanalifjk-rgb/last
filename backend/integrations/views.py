from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from saas.permissions import HasActiveTenant, TenantRBACPermission

from .models import Integration, SyncLog, SyncMapping
from .serializers import IntegrationSerializer, SyncLogSerializer, SyncMappingSerializer
from .services import run_sync, sync_products_inbound, sync_products_outbound, sync_orders_inbound, push_invoice


class IntegrationListCreateView(generics.ListCreateAPIView):
    serializer_class = IntegrationSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "integrations"

    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "manage"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        return Integration.objects.filter(tenant=self.request.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class IntegrationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = IntegrationSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "integrations"

    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "manage"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        return Integration.objects.filter(tenant=self.request.tenant)


class SyncView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "integrations"
    rbac_action = "manage"
    def post(self, request, integration_id):
        direction = request.data.get("direction", "inbound")
        entity_type = request.data.get("entity_type", "product")
        try:
            result = run_sync(tenant=request.tenant, integration_id=integration_id, direction=direction, entity_type=entity_type)
        except Integration.DoesNotExist:
            return Response({"detail": "Integration not found."}, status=404)
        except ValueError as exc:
            return Response({"code": "integration_unavailable", "detail": str(exc)}, status=409)
        return Response(result)


class SyncLogListView(generics.ListAPIView):
    serializer_class = SyncLogSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "integrations"
    rbac_action = "view"
    def get_queryset(self):
        qs = SyncLog.objects.filter(tenant=self.request.tenant).select_related("integration")
        iid = self.request.query_params.get("integration_id")
        return qs.filter(integration_id=iid) if iid else qs[:200]


class SyncMappingListView(generics.ListAPIView):
    serializer_class = SyncMappingSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "integrations"
    rbac_action = "view"

    def get_queryset(self):
        return SyncMapping.objects.filter(tenant=self.request.tenant).select_related("integration")


class PushInvoiceView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "integrations"
    rbac_action = "manage"
    def post(self, request, integration_id):
        integration = get_object_or_404(Integration, tenant=request.tenant, pk=integration_id)
        try:
            remote_id = push_invoice(integration, request.data)
        except ValueError as exc:
            return Response({"code": "integration_unavailable", "detail": str(exc)}, status=409)
        return Response({"remote_id": remote_id}, status=201)
