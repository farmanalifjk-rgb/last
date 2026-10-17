from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from pos.models import Order, CashSession
from .models import (ParkedOrder, Layaway, SplitBill, ExchangeOrder, OfflineSyncQueue,
                     ReceiptTemplate, CashDrawerEvent)
from .serializers import (
    ParkedOrderSerializer, LayawaySerializer, SplitBillSerializer, ExchangeOrderSerializer,
    OfflineSyncQueueSerializer, ReceiptTemplateSerializer, CashDrawerEventSerializer,SplitBillShareSerializer,
)
from .services import (
    park_cart, resume_parked, create_layaway, add_layaway_installment,
    split_bill, mark_share_paid, log_drawer_event, enqueue_offline, sync_offline_pending,
)
from saas.permissions import HasActiveTenant, TenantRBACPermission


# -- Parked / held orders --
class ParkListCreateView(generics.ListCreateAPIView):
    serializer_class = ParkedOrderSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def get_queryset(self):
        qs = ParkedOrder.objects.filter(
            tenant=self.request.tenant, status=ParkedOrder.STATUS_PARKED
        ).select_related("customer", "session")
        sid = self.request.query_params.get("session_id")
        return qs.filter(session_id=sid) if sid else qs

    def perform_create(self, serializer):
        d = serializer.validated_data
        serializer.instance = park_cart(session=d["session"], payload=d.get("payload", {}),
                                        label=d.get("label", ""), customer=d.get("customer"),
                                        user=self.request.user)


class ResumeParkView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def post(self, request, pk):
        return Response(ParkedOrderSerializer(resume_parked(pk, tenant=request.tenant)).data)


# -- Layaway --
class LayawayCreateView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id, tenant=request.tenant)
        lw = create_layaway(order=order, deposit=request.data.get("deposit", 0),
                            due_date=request.data.get("due_date"),
                            payment_method=request.data.get("payment_method", "cash"))
        return Response(LayawaySerializer(lw).data, status=201)


class LayawayInstallmentView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def post(self, request, pk):
        lw = add_layaway_installment(pk, request.data.get("amount", 0),
                                      request.data.get("payment_method", "cash"),
                                      tenant=request.tenant)
        return Response(LayawaySerializer(lw).data)


# -- Split bill --
class SplitBillCreateView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def post(self, request, order_id):
        split = split_bill(order_id, request.data.get("share_count", 2),
                          request.data.get("amounts"),
                          tenant=request.tenant)
        return Response(SplitBillSerializer(split).data, status=201)


class SplitSharePayView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def post(self, request, share_id):
        s = mark_share_paid(share_id, request.data.get("payment_method", "cash"), tenant=request.tenant)
        return Response(SplitBillShareSerializer(s).data)


# -- Exchange --
class ExchangeListCreateView(generics.ListCreateAPIView):
    serializer_class = ExchangeOrderSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def get_queryset(self):
        return ExchangeOrder.objects.filter(
            tenant=self.request.tenant
        ).select_related("original_order")


# -- Offline sync --
class OfflineEnqueueView(generics.CreateAPIView):
    serializer_class = OfflineSyncQueueSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def perform_create(self, serializer):
        serializer.instance = enqueue_offline(device_id=serializer.validated_data["device_id"],
                                              payload=serializer.validated_data.get("payload", {}))


class OfflineSyncNowView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "manage"

    def post(self, request):
        return Response(sync_offline_pending())


# -- Receipt designer --
class ReceiptTemplateListCreateView(generics.ListCreateAPIView):
    serializer_class = ReceiptTemplateSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    def get_queryset(self):
        return ReceiptTemplate.objects.filter(tenant=self.request.tenant)


class ReceiptTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReceiptTemplateSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    def get_queryset(self):
        return ReceiptTemplate.objects.filter(tenant=self.request.tenant)


# -- Cash drawer events --
class DrawerEventListCreateView(generics.ListCreateAPIView):
    serializer_class = CashDrawerEventSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get_queryset(self):
        qs = CashDrawerEvent.objects.filter(
            tenant=self.request.tenant
        ).select_related("session")
        sid = self.request.query_params.get("session_id")
        return qs.filter(session_id=sid) if sid else qs

    def perform_create(self, serializer):
        d = serializer.validated_data
        serializer.instance = log_drawer_event(session=d["session"], kind=d["kind"],
                                               amount=d.get("amount", 0), note=d.get("note", ""),
                                               user=self.request.user)
