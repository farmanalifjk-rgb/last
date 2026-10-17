from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from rbac.models import Role
from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin

from .models import ApprovalRequest, ApprovalRule, EmailQueue, InAppNotification, SMSQueue
from .services import decide_approval


class ApprovalRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalRule
        fields = ["id", "tenant", "module", "action", "min_amount", "requires_approval", "approver_role", "is_active"]

    def validate_approver_role(self, value):
        if value and not Role.objects.filter(key=value).exists():
            raise serializers.ValidationError("Use an existing role key.")
        return value


class ApprovalRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = [
            "id", "module", "action", "reference_id", "reference_str", "amount",
            "requested_by", "requested_by_name", "status", "reviewed_by",
            "reviewed_by_name", "reviewed_at", "note", "created_at",
        ]
        read_only_fields = fields

    def get_requested_by_name(self, obj):
        return obj.requested_by.get_full_name() or obj.requested_by.username

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username


class OperationNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InAppNotification
        fields = ["id", "tenant", "user", "type", "title", "message", "link", "event_key", "is_read", "created_at"]
        read_only_fields = fields
        ref_name = "OperationNotification"


class DeliveryQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailQueue
        fields = ["id", "tenant", "to", "subject", "body", "status", "attempts", "sent_at", "error", "created_at"]
        read_only_fields = fields


class SMSQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSQueue
        fields = ["id", "tenant", "to", "message", "status", "attempts", "sent_at", "error", "created_at"]
        read_only_fields = fields


class OperationsSecureViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "operations"


class ApprovalRuleViewSet(OperationsSecureViewSet):
    queryset = ApprovalRule.objects.all()
    serializer_class = ApprovalRuleSerializer

    def get_permissions(self):
        self.rbac_action = "view" if self.action in {"list", "retrieve"} else "manage"
        return [permission() for permission in self.permission_classes]


class ApprovalRequestViewSet(OperationsSecureViewSet):
    queryset = ApprovalRequest.objects.select_related("requested_by", "reviewed_by")
    serializer_class = ApprovalRequestSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        self.rbac_action = "approve" if self.action in {"approve", "reject"} else "view"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        qs = super().get_queryset()
        for query_key, field in (("module", "module"), ("status", "status"), ("action", "action")):
            if value := self.request.query_params.get(query_key):
                qs = qs.filter(**{field: value})
        return qs

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST", detail="Approval requests are created only by supported source actions.")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        approval, source = decide_approval(
            tenant=request.tenant,
            approval_id=pk,
            actor=request.user,
            decision=ApprovalRequest.STATUS_APPROVED,
            note=str(request.data.get("note", "")),
            request=request,
        )
        payload = ApprovalRequestSerializer(approval).data
        if source is not None:
            payload["source_status"] = getattr(source, "status", None)
        return Response(payload)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        approval, _ = decide_approval(
            tenant=request.tenant,
            approval_id=pk,
            actor=request.user,
            decision=ApprovalRequest.STATUS_REJECTED,
            note=str(request.data.get("note", "")),
            request=request,
        )
        return Response(ApprovalRequestSerializer(approval).data)

    @action(detail=False, methods=["get"])
    def pending_count(self, request):
        return Response({"count": self.get_queryset().filter(status=ApprovalRequest.STATUS_PENDING).count()})


class NotificationViewSet(OperationsSecureViewSet):
    queryset = InAppNotification.objects.all()
    serializer_class = OperationNotificationSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        self.rbac_action = "view"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        qs = super().get_queryset().filter(user=self.request.user)
        if value := self.request.query_params.get("type"):
            qs = qs.filter(type=value)
        if (is_read := self.request.query_params.get("is_read")) is not None:
            qs = qs.filter(is_read=is_read.lower() == "true")
        return qs

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST", detail="Notifications are emitted by trusted backend events.")

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(OperationNotificationSerializer(notification).data)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"marked": count})

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(is_read=False).count()})


class EmailQueueViewSet(OperationsSecureViewSet):
    queryset = EmailQueue.objects.all()
    serializer_class = DeliveryQueueSerializer
    http_method_names = ["get", "head", "options"]

    def get_permissions(self):
        self.rbac_action = "manage"
        return [permission() for permission in self.permission_classes]


class SMSQueueViewSet(OperationsSecureViewSet):
    queryset = SMSQueue.objects.all()
    serializer_class = SMSQueueSerializer
    http_method_names = ["get", "head", "options"]

    def get_permissions(self):
        self.rbac_action = "manage"
        return [permission() for permission in self.permission_classes]
