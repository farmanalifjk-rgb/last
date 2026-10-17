from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone

from .models import AlertRule, Notification, NotificationDigest
from .serializers import AlertRuleSerializer, NotificationSerializer, NotificationDigestSerializer
from .services import run_all_scans, mark_read
from saas.permissions import HasActiveTenant, TenantRBACPermission


class TenantNotificationView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "operations"
    rbac_action = "view"


class AlertRuleListCreateView(generics.ListCreateAPIView):
    serializer_class = AlertRuleSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "operations"
    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "manage"
        return [permission() for permission in self.permission_classes]
    def get_queryset(self):
        return AlertRule.objects.filter(tenant=self.request.tenant)
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class AlertRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AlertRuleSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "operations"
    rbac_action = "manage"
    def get_queryset(self):
        return AlertRule.objects.filter(tenant=self.request.tenant)


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "operations"
    rbac_action = "view"

    def get_queryset(self):
        qs = Notification.objects.filter(tenant=self.request.tenant).select_related("target_user")
        unread = self.request.query_params.get("unread")
        if unread == "1":
            qs = qs.filter(is_read=False)
        mine = self.request.query_params.get("mine")
        if mine == "1":
            qs = qs.filter(target_user=self.request.user)
        return qs[:100]


class NotificationDetailView(generics.RetrieveAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "operations"
    rbac_action = "view"
    def get_queryset(self):
        return Notification.objects.filter(tenant=self.request.tenant).select_related("target_user")


class MarkReadView(TenantNotificationView):
    def post(self, request, pk):
        n = mark_read(tenant=request.tenant, notification_id=pk, user=request.user)
        return Response(NotificationSerializer(n).data)


class MarkAllReadView(TenantNotificationView):
    def post(self, request):
        Notification.objects.filter(tenant=request.tenant, target_user=request.user, is_read=False).update(is_read=True)
        return Response({"ok": True})


class RunScansView(TenantNotificationView):
    rbac_action = "manage"
    def post(self, request):
        result = run_all_scans(tenant=request.tenant)
        NotificationDigest.objects.create(tenant=request.tenant, day=timezone.now().date(), fired_count=result["fired"], email_count=Notification.objects.filter(tenant=request.tenant, is_sent_email=True,created_at__date=timezone.now().date()).count(), summary=str(result))
        return Response(result)


class NotificationDigestListView(generics.ListAPIView):
    serializer_class = NotificationDigestSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "operations"
    rbac_action = "view"
    def get_queryset(self):
        return NotificationDigest.objects.filter(tenant=self.request.tenant)
