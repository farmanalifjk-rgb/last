"""Tenant-safe operational facades for existing system-control records.

The models remain system-owned. This module replaces unsafe global management
views with a single active-tenant, RBAC-gated surface and never serializes
persisted API-key or webhook secrets.
"""
import hashlib

from django.db import connection
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.recorder import record, snapshot
from saas.permissions import HasActiveTenant, TenantRBACPermission
from system.models import APIKey, ErrorLog, Webhook, WebhookDelivery, generate_api_key
from system.serializers import (
    APIKeyCreateResponseSerializer,
    APIKeySerializer,
    ErrorLogSerializer,
    WebhookDeliverySerializer,
    WebhookSerializer,
)


class TenantSystemOperationsAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"


def _new_api_secret():
    secret = generate_api_key()
    return secret, hashlib.sha256(secret.encode("utf-8")).hexdigest()


class APIKeyListView(TenantSystemOperationsAPIView):
    def get(self, request):
        return Response(APIKeySerializer(APIKey.objects.filter(tenant=request.tenant), many=True).data)

    def post(self, request):
        secret, digest = _new_api_secret()
        key = APIKey.objects.create(
            tenant=request.tenant,
            name=str(request.data.get("name") or "Untitled Key").strip(),
            key=digest,
            key_prefix=secret[:8],
            key_last4=secret[-4:],
            scopes=request.data.get("scopes") or [],
            expires_at=request.data.get("expires_at") or None,
            created_by=request.user,
        )
        record(tenant=request.tenant, actor=request.user, action="create", instance=key, request=request,
               summary=f"Created API key {key.name}", icon="key-round",
               after={"name": key.name, "scopes": key.scopes, "expires_at": key.expires_at})
        return Response(APIKeyCreateResponseSerializer(key, context={"secret": secret}).data, status=status.HTTP_201_CREATED)


class APIKeyDetailView(TenantSystemOperationsAPIView):
    def get_object(self, request, pk):
        return get_object_or_404(APIKey, tenant=request.tenant, pk=pk)

    def get(self, request, pk):
        return Response(APIKeySerializer(self.get_object(request, pk)).data)

    def put(self, request, pk):
        key = self.get_object(request, pk)
        before = {"name": key.name, "scopes": key.scopes, "is_active": key.is_active, "expires_at": key.expires_at}
        for field in ("name", "scopes", "is_active", "expires_at"):
            if field in request.data:
                setattr(key, field, request.data[field])
        key.save(update_fields=["name", "scopes", "is_active", "expires_at"])
        record(tenant=request.tenant, actor=request.user, action="update", instance=key, request=request,
               summary=f"Updated API key {key.name}", icon="key-round", before=before,
               after={"name": key.name, "scopes": key.scopes, "is_active": key.is_active, "expires_at": key.expires_at})
        return Response(APIKeySerializer(key).data)

    def delete(self, request, pk):
        key = self.get_object(request, pk)
        before = {"name": key.name, "scopes": key.scopes}
        key.delete()
        record(tenant=request.tenant, actor=request.user, action="delete", entity_type="apikey", entity_id=str(pk),
               entity_label=before["name"], request=request, summary=f"Revoked API key {before['name']}",
               icon="key-round", before=before)
        return Response(status=status.HTTP_204_NO_CONTENT)


class APIKeyRegenerateView(TenantSystemOperationsAPIView):
    def post(self, request, pk):
        key = get_object_or_404(APIKey, tenant=request.tenant, pk=pk)
        secret, digest = _new_api_secret()
        key.key, key.key_prefix, key.key_last4 = digest, secret[:8], secret[-4:]
        key.save(update_fields=["key", "key_prefix", "key_last4"])
        record(tenant=request.tenant, actor=request.user, action="update", instance=key, request=request,
               summary=f"Regenerated API key {key.name}", icon="key-round")
        return Response(APIKeyCreateResponseSerializer(key, context={"secret": secret}).data)


class WebhookListView(TenantSystemOperationsAPIView):
    def get(self, request):
        return Response(WebhookSerializer(Webhook.objects.filter(tenant=request.tenant), many=True).data)

    def post(self, request):
        serializer = WebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        webhook = serializer.save(tenant=request.tenant)
        record(tenant=request.tenant, actor=request.user, action="create", instance=webhook, request=request,
               summary=f"Created webhook {webhook.name}", icon="webhook", after=snapshot(webhook, fields=["name", "target_url", "events", "is_active"]))
        return Response(WebhookSerializer(webhook).data, status=status.HTTP_201_CREATED)


class WebhookDetailView(TenantSystemOperationsAPIView):
    def get_object(self, request, pk):
        return get_object_or_404(Webhook, tenant=request.tenant, pk=pk)

    def get(self, request, pk):
        return Response(WebhookSerializer(self.get_object(request, pk)).data)

    def put(self, request, pk):
        webhook = self.get_object(request, pk)
        before = snapshot(webhook, fields=["name", "target_url", "events", "is_active"])
        serializer = WebhookSerializer(webhook, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        webhook = serializer.save()
        record(tenant=request.tenant, actor=request.user, action="update", instance=webhook, request=request,
               summary=f"Updated webhook {webhook.name}", icon="webhook", before=before,
               after=snapshot(webhook, fields=["name", "target_url", "events", "is_active"]))
        return Response(WebhookSerializer(webhook).data)

    def delete(self, request, pk):
        webhook = self.get_object(request, pk)
        before = snapshot(webhook, fields=["name", "target_url", "events"])
        webhook.delete()
        record(tenant=request.tenant, actor=request.user, action="delete", entity_type="webhook", entity_id=str(pk),
               entity_label=before["name"], request=request, summary=f"Deleted webhook {before['name']}", icon="webhook", before=before)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebhookTestView(TenantSystemOperationsAPIView):
    def post(self, request, pk):
        raise MethodNotAllowed("POST", detail="Webhook test delivery is not enabled in the Phase 10 operational surface.")


class WebhookDeliveryListView(TenantSystemOperationsAPIView):
    def get(self, request, pk):
        webhook = get_object_or_404(Webhook, tenant=request.tenant, pk=pk)
        return Response(WebhookDeliverySerializer(webhook.deliveries.filter(tenant=request.tenant), many=True).data)


class ErrorLogListView(TenantSystemOperationsAPIView):
    def get(self, request):
        qs = ErrorLog.objects.filter(tenant=request.tenant)
        for query_key in ("log_type", "severity"):
            if value := request.query_params.get(query_key):
                qs = qs.filter(**{query_key: value})
        if (resolved := request.query_params.get("is_resolved")) is not None:
            qs = qs.filter(is_resolved=resolved.lower() == "true")
        data = ErrorLogSerializer(qs, many=True).data
        return Response({"results": data, "stats": {
            "total": qs.count(),
            "unresolved": qs.filter(is_resolved=False).count(),
            "critical": qs.filter(severity="critical", is_resolved=False).count(),
        }})

    def post(self, request):
        serializer = ErrorLogSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        error_log = serializer.save(tenant=request.tenant, user=request.user)
        return Response(ErrorLogSerializer(error_log).data, status=status.HTTP_201_CREATED)


class ErrorLogResolveView(TenantSystemOperationsAPIView):
    def post(self, request, pk):
        error_log = get_object_or_404(ErrorLog, tenant=request.tenant, pk=pk)
        if not error_log.is_resolved:
            error_log.is_resolved = True
            error_log.save(update_fields=["is_resolved"])
            record(tenant=request.tenant, actor=request.user, action="update", instance=error_log, request=request,
                   summary=f"Resolved {error_log.log_type} log", icon="circle-check", after={"is_resolved": True})
        return Response(ErrorLogSerializer(error_log).data)


class SystemHealthView(TenantSystemOperationsAPIView):
    def get(self, request):
        database_connected = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            database_connected = False
        return Response({
            "application_status": "available",
            "database_connected": database_connected,
            "unresolved_issues": ErrorLog.objects.filter(tenant=request.tenant, is_resolved=False).count(),
            "checked_at": timezone.now(),
        })
