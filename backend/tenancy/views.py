import json
from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Tenant, Branch, UserTenantMembership, TenantSetting, BranchSetting
from .serializers import (TenantSerializer, BranchSerializer, UserTenantMembershipSerializer,
                          TenantSettingSerializer, BranchSettingSerializer)
from .context import active_tenant, active_branch
from saas.permissions import HasActiveTenant, TenantRBACPermission


class TenantListCreateView(generics.ListCreateAPIView):
    serializer_class = TenantSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Tenant.objects.all()


class TenantDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TenantSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Tenant.objects.all()


class BranchListCreateView(generics.ListCreateAPIView):
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    def get_queryset(self):
        return Branch.objects.filter(tenant=self.request.tenant).select_related("tenant")


class BranchDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    def get_queryset(self):
        return Branch.objects.filter(tenant=self.request.tenant).select_related("tenant")


class MembershipListCreateView(generics.ListCreateAPIView):
    serializer_class = UserTenantMembershipSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "rbac"
    rbac_action = "manage"

    def get_queryset(self):
        return UserTenantMembership.objects.filter(
            tenant=self.request.tenant
        ).select_related("user", "tenant", "branch")


class MembershipDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserTenantMembershipSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "rbac"
    rbac_action = "manage"

    def get_queryset(self):
        return UserTenantMembership.objects.filter(
            tenant=self.request.tenant
        ).select_related("user", "tenant", "branch")


class TenantSettingListCreateView(generics.ListCreateAPIView):
    serializer_class = TenantSettingSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    def get_queryset(self):
        return TenantSetting.objects.filter(tenant=self.request.tenant)


class BranchSettingListCreateView(generics.ListCreateAPIView):
    serializer_class = BranchSettingSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    def get_queryset(self):
        return BranchSetting.objects.filter(
            branch__tenant=self.request.tenant
        ).select_related("branch")


class MyTenantView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "rbac"
    rbac_action = "view"

    def get(self, request):
        tenant = active_tenant(request.user)
        branch = active_branch(request.user)
        if not tenant:
            return Response({"detail": "No tenant membership."}, status=404)
        data = TenantSerializer(tenant).data
        data["active_branch"] = BranchSerializer(branch).data if branch else None
        return Response(data)


class GetSettingView(APIView):
    """Read or write a single tenant/branch setting by key."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    def get(self, request):
        key = request.query_params.get("key")
        tenant = active_tenant(request.user)
        ts = TenantSetting.objects.filter(tenant=tenant, key=key).first()
        value = ts.value
        if ts and ts.is_json:
            try: value = json.loads(value)
            except Exception: pass
        return Response({"key": key, "value": value})

    def post(self, request):
        key = request.data["key"]
        value = request.data["value"]
        is_json = request.data.get("is_json", False)
        tenant = active_tenant(request.user)
        if is_json:
            value = json.dumps(value)
        obj, _ = TenantSetting.objects.update_or_create(tenant=tenant, key=key,
                                                        defaults={"value": value, "is_json": is_json})
        return Response(TenantSettingSerializer(obj).data)
