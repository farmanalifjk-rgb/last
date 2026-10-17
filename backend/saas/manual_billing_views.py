from rest_framework.response import Response
from rest_framework.views import APIView

from .manual_billing_serializers import (
    ManualPaymentDecisionSerializer,
    ManualPaymentMethodSerializer,
    ManualPaymentSubmissionSerializer,
    ManualSubscriptionPaymentSerializer,
    SubscriptionRequestCreateSerializer,
    SubscriptionRequestSerializer,
)
from .manual_billing_services import create_subscription_request, reject_manual_payment, submit_manual_payment, verify_manual_payment
from .models import ManualPaymentMethod, ManualSubscriptionPayment, SubscriptionRequest
from .permissions import HasActiveTenant, PlatformBillingPermission, TenantRBACPermission
from .services import get_active_tenant_for_user


class TenantBillingPermissionView(APIView):
    permission_classes = [HasActiveTenant, TenantRBACPermission]
    rbac_module = "billing"
    rbac_action = "view"

    def get_tenant(self, request):
        return get_active_tenant_for_user(request.user)


class ManualPaymentMethodsView(TenantBillingPermissionView):
    def get(self, request):
        methods = ManualPaymentMethod.objects.filter(is_active=True)
        return Response({"results": ManualPaymentMethodSerializer(methods, many=True).data})


class SubscriptionRequestListCreateView(TenantBillingPermissionView):
    def get_permissions(self):
        self.rbac_action = "request" if self.request.method == "POST" else "view"
        return super().get_permissions()

    def get(self, request):
        records = SubscriptionRequest.objects.filter(tenant=self.get_tenant(request)).select_related("plan", "invoice", "manual_payment")
        return Response({"results": SubscriptionRequestSerializer(records, many=True).data})

    def post(self, request):
        serializer = SubscriptionRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        billing_request, invoice = create_subscription_request(
            tenant=self.get_tenant(request), plan_id=serializer.validated_data["plan_id"], actor=request.user, request=request,
        )
        data = SubscriptionRequestSerializer(billing_request).data
        data["invoice_id"] = invoice.id
        return Response(data, status=201)


class ManualPaymentSubmissionView(TenantBillingPermissionView):
    rbac_action = "request"

    def post(self, request, request_id):
        serializer = ManualPaymentSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = submit_manual_payment(
            tenant=self.get_tenant(request),
            subscription_request_id=request_id,
            actor=request.user,
            request=request,
            **serializer.validated_data,
        )
        return Response(ManualSubscriptionPaymentSerializer(payment).data, status=201)


class TenantManualPaymentListView(TenantBillingPermissionView):
    def get(self, request):
        payments = ManualSubscriptionPayment.objects.filter(tenant=self.get_tenant(request)).select_related(
            "subscription_request", "plan", "payment_method", "submitted_by", "verified_by", "tenant",
        )
        return Response({"results": ManualSubscriptionPaymentSerializer(payments, many=True).data})


class PlatformManualPaymentListView(APIView):
    permission_classes = [PlatformBillingPermission]

    def get(self, request):
        status_value = request.query_params.get("status")
        payments = ManualSubscriptionPayment.objects.select_related(
            "subscription_request", "plan", "payment_method", "submitted_by", "verified_by", "tenant",
        )
        if status_value:
            payments = payments.filter(status=status_value)
        return Response({"results": ManualSubscriptionPaymentSerializer(payments, many=True).data})


class PlatformManualPaymentVerifyView(APIView):
    permission_classes = [PlatformBillingPermission]

    def post(self, request, payment_id):
        serializer = ManualPaymentDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = verify_manual_payment(payment_id=payment_id, actor=request.user, request=request, review_note=serializer.validated_data.get("review_note", ""))
        return Response(ManualSubscriptionPaymentSerializer(payment).data)


class PlatformManualPaymentRejectView(APIView):
    permission_classes = [PlatformBillingPermission]

    def post(self, request, payment_id):
        serializer = ManualPaymentDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = reject_manual_payment(
            payment_id=payment_id,
            actor=request.user,
            request=request,
            rejection_reason=serializer.validated_data.get("rejection_reason", ""),
            review_note=serializer.validated_data.get("review_note", ""),
        )
        return Response(ManualSubscriptionPaymentSerializer(payment).data)
