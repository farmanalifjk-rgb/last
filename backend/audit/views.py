from django.db.models import Count, Q
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from saas.permissions import HasActiveTenant, TenantRBACPermission

from .models import ActivityFeed, AuditEvent
from .serializers import ActivityFeedSerializer, AuditEventSerializer


class AuditSecureAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "audit"
    rbac_action = "view"


class AuditEventListView(AuditSecureAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "audit"
    rbac_action = "view"
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        qs = AuditEvent.objects.filter(tenant=self.request.tenant).select_related("actor")
        params = self.request.query_params
        if value := params.get("entity_type"):
            qs = qs.filter(entity_type__iexact=value)
        if value := params.get("action"):
            qs = qs.filter(action=value)
        if value := params.get("actor"):
            qs = qs.filter(Q(actor_id=value) | Q(actor_name__icontains=value))
        if value := params.get("date_from"):
            qs = qs.filter(created_at__date__gte=value)
        if value := params.get("date_to"):
            qs = qs.filter(created_at__date__lte=value)
        if value := params.get("search"):
            qs = qs.filter(Q(entity_label__icontains=value) | Q(actor_name__icontains=value) | Q(entity_type__icontains=value))
        return qs[:500]


class AuditEventDetailView(AuditSecureAPIView, generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "audit"
    rbac_action = "view"
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        return AuditEvent.objects.filter(tenant=self.request.tenant).select_related("actor")


class ActivityFeedListView(AuditSecureAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "audit"
    rbac_action = "view"
    serializer_class = ActivityFeedSerializer

    def get_queryset(self):
        qs = ActivityFeed.objects.filter(tenant=self.request.tenant)  # denormalised: actor_name, no FK
        params = self.request.query_params
        if value := params.get("entity_type"):
            qs = qs.filter(entity_type__iexact=value)
        if value := params.get("actor"):
            qs = qs.filter(actor_name__icontains=value)
        if value := params.get("search"):
            qs = qs.filter(Q(summary__icontains=value) | Q(entity_type__icontains=value))
        return qs[:100]


class AuditStatsView(AuditSecureAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "audit"
    rbac_action = "view"
    def get(self, request):
        rows = AuditEvent.objects.filter(tenant=request.tenant).values("action").annotate(count=Count("id"))
        return Response({"actions": {row["action"]: row["count"] for row in rows}, "total": sum(row["count"] for row in rows)})
