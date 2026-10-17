from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.throttling import AnonRateThrottle
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from pos.models import Customer, Refund
from pos.pagination import CustomPagination
from saas.permissions import HasActiveTenant, TenantRBACPermission

from .models import GiftCard, PaymentReconciliation, ProviderPaymentOperation, ProviderRefundOperation, RefundSettlement, StoreCredit, TenderedPayment
from .serializers import (
    AmountSerializer,
    GiftCardIssueSerializer,
    GiftCardSerializer,
    PaymentReconciliationSerializer,
    PaymentRegisterSerializer,
    ReconciliationCreateSerializer,
    RefundCreditNoteRequestSerializer,
    RefundCreditNoteSerializer,
    RefundSettlementSerializer,
    ProviderCheckoutRequestSerializer,
    ProviderPaymentOperationSerializer,
    ProviderRefundOperationSerializer,
    StoreCreditIssueSerializer,
    StoreCreditSerializer,
)
from .services import close_reconciliation, disable_gift_card, issue_gift_card, issue_store_credit, reconcile_session, refund_as_store_credit, topup_gift_card
from .provider_services import (
    cancel_provider_payment,
    process_provider_webhook,
    start_provider_payment,
    start_provider_refund,
    verify_provider_payment,
    verify_provider_refund,
)
from .providers import get_provider, registered_providers
from .providers.base import ProviderConfigurationError, ProviderError, ProviderVerificationError


class CanonicalPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "payments"
    rbac_action = "view"


def _error(exc):
    if isinstance(exc, LookupError):
        raise NotFound(str(exc))
    raise ValidationError(str(exc))


def _provider_error(exc):
    if isinstance(exc, ProviderConfigurationError):
        raise ValidationError("The selected provider sandbox configuration is required.")
    if isinstance(exc, ProviderVerificationError):
        raise ValidationError(str(exc))
    if isinstance(exc, ProviderError):
        raise ValidationError("Provider state could not be safely verified. The payment remains pending verification.")
    _error(exc)


class PaymentRegisterView(CanonicalPaymentAPIView):
    """Read-only immutable tender register. Settlement remains owned by canonical POS checkout."""

    def get(self, request):
        query = TenderedPayment.objects.filter(tenant=request.tenant, is_settled=True).select_related("order__customer", "settlement")
        if search := request.query_params.get("search", "").strip():
            query = query.filter(Q(order__order_number__icontains=search) | Q(reference__icontains=search))
        if tender_type := request.query_params.get("tender_type"):
            query = query.filter(tender_type=tender_type)
        if customer_id := request.query_params.get("customer_id"):
            query = query.filter(order__customer_id=customer_id)
        if order_id := request.query_params.get("order_id"):
            query = query.filter(order_id=order_id)
        if date_from := request.query_params.get("date_from"):
            query = query.filter(created_at__date__gte=date_from)
        if date_to := request.query_params.get("date_to"):
            query = query.filter(created_at__date__lte=date_to)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(query.order_by("-created_at", "-id"), request)
        rows = page if page is not None else query
        data = PaymentRegisterSerializer(rows, many=True).data
        return paginator.get_paginated_response(data) if page is not None else Response(data)


class PaymentRegisterDetailView(CanonicalPaymentAPIView):
    def get(self, request, pk):
        payment = get_object_or_404(TenderedPayment.objects.select_related("order__customer", "settlement"), tenant=request.tenant, pk=pk, is_settled=True)
        return Response(PaymentRegisterSerializer(payment).data)


class GiftCardListCreateView(CanonicalPaymentAPIView):
    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "manage"
        return [permission() for permission in self.permission_classes]

    def get(self, request):
        query = GiftCard.objects.filter(tenant=request.tenant).select_related("issued_to").prefetch_related("transactions__order")
        if search := request.query_params.get("search", "").strip():
            query = query.filter(code__icontains=search[-12:])
        if active := request.query_params.get("active"):
            query = query.filter(is_active=active.lower() in {"1", "true", "yes"})
        paginator = CustomPagination()
        page = paginator.paginate_queryset(query.order_by("-issued_at", "-id"), request)
        rows = page if page is not None else query
        data = GiftCardSerializer(rows, many=True).data
        return paginator.get_paginated_response(data) if page is not None else Response(data)

    def post(self, request):
        serializer = GiftCardIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = None
        if customer_id := serializer.validated_data.get("customer_id"):
            customer = get_object_or_404(Customer, tenant=request.tenant, pk=customer_id)
        try:
            gift_card = issue_gift_card(tenant=request.tenant, initial_balance=serializer.validated_data["initial_balance"], customer=customer, expires_at=serializer.validated_data.get("expires_at"), user=request.user)
        except Exception as exc:
            _error(exc)
        data = GiftCardSerializer(gift_card).data
        # The generated identifier is returned exactly once at issuance; no PIN or card credentials exist.
        data["issued_code"] = gift_card.code
        return Response(data, status=status.HTTP_201_CREATED)


class GiftCardDetailView(CanonicalPaymentAPIView):
    def get(self, request, pk):
        gift_card = get_object_or_404(GiftCard.objects.select_related("issued_to").prefetch_related("transactions__order"), tenant=request.tenant, pk=pk)
        return Response(GiftCardSerializer(gift_card).data)


class GiftCardTopupView(CanonicalPaymentAPIView):
    rbac_action = "manage"

    def post(self, request, pk):
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            gift_card = topup_gift_card(tenant=request.tenant, gift_card_id=pk, amount=serializer.validated_data["amount"], user=request.user)
        except Exception as exc:
            _error(exc)
        return Response(GiftCardSerializer(gift_card).data)


class GiftCardDisableView(CanonicalPaymentAPIView):
    rbac_action = "manage"

    def post(self, request, pk):
        try:
            gift_card = disable_gift_card(tenant=request.tenant, gift_card_id=pk, user=request.user)
        except Exception as exc:
            _error(exc)
        return Response(GiftCardSerializer(gift_card).data)


class StoreCreditDetailView(CanonicalPaymentAPIView):
    def get(self, request, customer_id):
        customer = get_object_or_404(Customer, tenant=request.tenant, pk=customer_id)
        wallet = StoreCredit.objects.filter(tenant=request.tenant, customer=customer).prefetch_related("transactions__order").first()
        if wallet is None:
            return Response({"customer_id": customer.id, "balance": "0.00", "currency": "USD", "transactions": []})
        return Response(StoreCreditSerializer(wallet).data)


class StoreCreditIssueView(CanonicalPaymentAPIView):
    rbac_action = "manage"

    def post(self, request, customer_id):
        serializer = StoreCreditIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = get_object_or_404(Customer, tenant=request.tenant, pk=customer_id)
        try:
            issue_store_credit(tenant=request.tenant, customer=customer, amount=serializer.validated_data["amount"], note=serializer.validated_data.get("note", ""), user=request.user)
        except Exception as exc:
            _error(exc)
        wallet = StoreCredit.objects.prefetch_related("transactions__order").get(tenant=request.tenant, customer=customer)
        return Response(StoreCreditSerializer(wallet).data, status=status.HTTP_201_CREATED)


class RefundSettlementListView(CanonicalPaymentAPIView):
    rbac_action = "refund"

    def get(self, request):
        query = RefundSettlement.objects.filter(tenant=request.tenant).select_related("refund__order")
        return Response(RefundSettlementSerializer(query.order_by("-created_at", "-id"), many=True).data)


class RefundCreditNoteCreateView(CanonicalPaymentAPIView):
    rbac_action = "refund"

    def post(self, request, refund_id):
        serializer = RefundCreditNoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refund = get_object_or_404(Refund, tenant=request.tenant, pk=refund_id)
        customer = get_object_or_404(Customer, tenant=request.tenant, pk=serializer.validated_data["customer_id"])
        try:
            credit_note = refund_as_store_credit(tenant=request.tenant, refund=refund, customer=customer, user=request.user)
        except Exception as exc:
            _error(exc)
        return Response(RefundCreditNoteSerializer(credit_note).data, status=status.HTTP_201_CREATED)


class ReconciliationListCreateView(CanonicalPaymentAPIView):
    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "manage"
        return [permission() for permission in self.permission_classes]

    def get(self, request):
        query = PaymentReconciliation.objects.filter(tenant=request.tenant).select_related("session").prefetch_related("lines")
        if status_value := request.query_params.get("status"):
            query = query.filter(status=status_value)
        return Response(PaymentReconciliationSerializer(query.order_by("-created_at", "-id"), many=True).data)

    def post(self, request):
        serializer = ReconciliationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reconciliation = reconcile_session(tenant=request.tenant, session_id=serializer.validated_data["session_id"], counted_lines=serializer.validated_data["lines"], note=serializer.validated_data.get("note", ""), user=request.user)
        except Exception as exc:
            _error(exc)
        return Response(PaymentReconciliationSerializer(reconciliation).data, status=status.HTTP_201_CREATED)


class ReconciliationDetailView(CanonicalPaymentAPIView):
    def get(self, request, pk):
        reconciliation = get_object_or_404(PaymentReconciliation.objects.prefetch_related("lines"), tenant=request.tenant, pk=pk)
        return Response(PaymentReconciliationSerializer(reconciliation).data)


class ReconciliationCloseView(CanonicalPaymentAPIView):
    rbac_action = "manage"

    def post(self, request, pk):
        try:
            reconciliation = close_reconciliation(tenant=request.tenant, reconciliation_id=pk, user=request.user)
        except Exception as exc:
            _error(exc)
        return Response(PaymentReconciliationSerializer(reconciliation).data)


class ProviderConfigView(CanonicalPaymentAPIView):
    """Safe provider capability projection; never returns secret or webhook values."""

    def get(self, request, provider):
        try:
            return Response(get_provider(provider).public_configuration())
        except ValueError:
            raise NotFound("The requested payment provider is not registered.")


class ProviderCatalogView(CanonicalPaymentAPIView):
    """Discover optional adapters without making a production-provider selection."""

    def get(self, request):
        return Response({"results": [adapter.public_configuration() for adapter in registered_providers()]})


class ProviderInitiateView(CanonicalPaymentAPIView):
    rbac_module = "pos"
    rbac_action = "create"

    def post(self, request, provider):
        serializer = ProviderCheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from saas.permissions import tenant_member_has_permission

        discount = serializer.validated_data["discount"]
        if discount and not tenant_member_has_permission(request.user, request.tenant, "pos", "discount"):
            raise PermissionDenied("The active tenant role does not permit discounts.")
        try:
            operation, client_secret, replayed = start_provider_payment(
                tenant=request.tenant,
                user=request.user,
                items=serializer.validated_data["items"],
                customer_id=serializer.validated_data.get("customer_id"),
                discount=discount,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                provider_code=provider,
            )
        except Exception as exc:
            _provider_error(exc)
        data = ProviderPaymentOperationSerializer(operation).data
        # Any provider client token is scoped to one operation, is never
        # persisted locally, and is returned only to the initiating token holder.
        data["client_secret"] = client_secret
        data["idempotent_replay"] = replayed
        return Response(data, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED)


class ProviderOperationListView(CanonicalPaymentAPIView):
    def get(self, request, provider):
        rows = ProviderPaymentOperation.objects.filter(tenant=request.tenant, provider=provider).select_related("order").order_by("-created_at", "-id")
        return Response(ProviderPaymentOperationSerializer(rows, many=True).data)


class ProviderOperationDetailView(CanonicalPaymentAPIView):
    def get(self, request, provider, pk):
        operation = get_object_or_404(ProviderPaymentOperation.objects.select_related("order"), tenant=request.tenant, provider=provider, pk=pk)
        return Response(ProviderPaymentOperationSerializer(operation).data)


class ProviderOperationVerifyView(CanonicalPaymentAPIView):
    rbac_action = "manage"

    def post(self, request, provider, pk):
        get_object_or_404(ProviderPaymentOperation, tenant=request.tenant, provider=provider, pk=pk)
        try:
            operation = verify_provider_payment(tenant=request.tenant, operation_id=pk, user=request.user)
        except Exception as exc:
            _provider_error(exc)
        return Response(ProviderPaymentOperationSerializer(operation).data)


class ProviderOperationCancelView(CanonicalPaymentAPIView):
    rbac_action = "manage"

    def post(self, request, provider, pk):
        get_object_or_404(ProviderPaymentOperation, tenant=request.tenant, provider=provider, pk=pk)
        try:
            operation = cancel_provider_payment(tenant=request.tenant, operation_id=pk, user=request.user)
        except Exception as exc:
            _provider_error(exc)
        return Response(ProviderPaymentOperationSerializer(operation).data)


class ProviderRefundInitiateView(CanonicalPaymentAPIView):
    rbac_module = "pos"
    rbac_action = "refund"

    def post(self, request, provider, refund_id):
        refund = get_object_or_404(Refund, tenant=request.tenant, pk=refund_id)
        if not ProviderPaymentOperation.objects.filter(tenant=request.tenant, order=refund.order, provider=provider).exists():
            raise NotFound("No matching provider operation exists for this refund.")
        try:
            operation = start_provider_refund(tenant=request.tenant, refund=refund, user=request.user)
        except Exception as exc:
            _provider_error(exc)
        return Response(ProviderRefundOperationSerializer(operation).data, status=status.HTTP_201_CREATED)


class ProviderRefundDetailView(CanonicalPaymentAPIView):
    rbac_action = "refund"

    def get(self, request, provider, pk):
        operation = get_object_or_404(ProviderRefundOperation, tenant=request.tenant, provider=provider, pk=pk)
        return Response(ProviderRefundOperationSerializer(operation).data)


class ProviderRefundVerifyView(CanonicalPaymentAPIView):
    rbac_action = "refund"

    def post(self, request, provider, pk):
        get_object_or_404(ProviderRefundOperation, tenant=request.tenant, provider=provider, pk=pk)
        try:
            operation = verify_provider_refund(tenant=request.tenant, refund_operation_id=pk, user=request.user)
        except Exception as exc:
            _provider_error(exc)
        return Response(ProviderRefundOperationSerializer(operation).data)


class ProviderWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request, provider):
        try:
            adapter = get_provider(provider)
            event, replayed = process_provider_webhook(
                provider_code=provider,
                raw_body=request.body,
                signature=request.headers.get(adapter.webhook_signature_header, ""),
            )
        except ValueError:
            return Response({"detail": "Webhook provider is not registered."}, status=status.HTTP_404_NOT_FOUND)
        except ProviderConfigurationError:
            return Response({"detail": "Webhook provider configuration is unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ProviderVerificationError:
            return Response({"detail": "Webhook signature verification failed."}, status=status.HTTP_400_BAD_REQUEST)
        except ProviderError:
            return Response({"detail": "Webhook processing could not be completed safely."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"received": True, "replayed": replayed, "state": event.processing_state})
