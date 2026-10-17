from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from .models import InvoiceSequence, FiscalInvoice, FiscalDevice, FiscalSubmission
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery

from audit.recorder import record, snapshot

from .pagination import OptionalPagination
from .serializers import (InvoiceSequenceSerializer, FiscalInvoiceSerializer,
                          FiscalInvoiceHistorySerializer,
                          FiscalDeviceSerializer, FiscalSubmissionSerializer)
from .services import issue_invoice, cancel_invoice, submit_to_device, FiscalServiceError
from saas.permissions import HasActiveTenant, TenantRBACPermission


class InvoiceSequenceListCreateView(generics.ListCreateAPIView):
    serializer_class = InvoiceSequenceSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "create"

    def get_queryset(self):
        return InvoiceSequence.objects.filter(tenant=self.request.tenant).annotate(
            invoice_count=Count("invoices")
        ).order_by("id")

    def perform_create(self, serializer):
        sequence = serializer.save(tenant=self.request.tenant)
        record(actor=self.request.user, action="fiscal.sequence.created", instance=sequence,
               request=self.request, summary=f"Created invoice sequence {sequence.name}.",
               after=snapshot(sequence, SEQUENCE_AUDIT_FIELDS))


SEQUENCE_AUDIT_FIELDS = ["name", "prefix", "next_number", "padding", "document_type", "is_active"]


class InvoiceSequenceDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH one sequence (no DELETE: issued invoices PROTECT it; deactivate instead).

    Numbering fields are locked once invoices exist (see the serializer). The
    POS checkout uses the oldest active "invoice" sequence of the tenant.
    """

    serializer_class = InvoiceSequenceSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "manage"
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return InvoiceSequence.objects.filter(tenant=self.request.tenant).annotate(invoice_count=Count("invoices"))

    def perform_update(self, serializer):
        before = snapshot(serializer.instance, SEQUENCE_AUDIT_FIELDS)
        sequence = serializer.save()
        record(actor=self.request.user, action="fiscal.sequence.updated", instance=sequence,
               request=self.request, summary=f"Updated invoice sequence {sequence.name}.",
               before=before, after=snapshot(sequence, SEQUENCE_AUDIT_FIELDS))


FBR_STATUS_FILTERS = {"pending", "accepted", "rejected", "failed", "unknown", "simulated", "not_submitted"}


class FiscalInvoiceListView(generics.ListAPIView):
    """Fiscal invoices of the active tenant.

    Without ?page= the response is the historical full array with the full
    serializer. With ?page= (FBR history screen) it is paginated and uses the
    compact history serializer. Filters (both modes): ?search= (invoice no.,
    FBR no., order no.), ?status= (draft/issued/cancelled/void), ?fbr_status=
    (pending/accepted/rejected/failed/unknown/simulated/not_submitted; the
    latest live submission decides).
    """

    serializer_class = FiscalInvoiceSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "view"
    pagination_class = OptionalPagination

    def get_serializer_class(self):
        if "page" in self.request.query_params or "page_size" in self.request.query_params:
            return FiscalInvoiceHistorySerializer
        return FiscalInvoiceSerializer

    def get_queryset(self):
        from fbr.models import FBRSubmission

        params = self.request.query_params
        live = FBRSubmission.objects.filter(invoice=OuterRef("pk"), is_validate=False).order_by("-id")
        queryset = FiscalInvoice.objects.filter(
            tenant=self.request.tenant
        ).select_related("order", "customer", "sequence").annotate(
            latest_fbr_status=Subquery(live.values("status")[:1]),
            latest_fbr_simulated=Subquery(live.values("is_simulated")[:1]),
        ).prefetch_related(
            Prefetch(
                "fbr_submissions",
                queryset=FBRSubmission.objects.filter(is_validate=False).order_by("-id"),
                to_attr="live_fbr_submissions",
            )
        ).order_by("-created_at", "-id")
        search = (params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search)
                | Q(fbr_invoice_number__icontains=search)
                | Q(order__order_number__icontains=search)
            )
        status_filter = (params.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        fbr_status = (params.get("fbr_status") or "").strip().lower()
        if fbr_status in FBR_STATUS_FILTERS:
            if fbr_status == "not_submitted":
                queryset = queryset.filter(latest_fbr_status__isnull=True)
            elif fbr_status == "simulated":
                queryset = queryset.filter(latest_fbr_status="accepted", latest_fbr_simulated=True)
            elif fbr_status == "accepted":
                queryset = queryset.filter(latest_fbr_status="accepted", latest_fbr_simulated=False)
            else:
                queryset = queryset.filter(latest_fbr_status=fbr_status)
        return queryset


class FiscalInvoiceDetailView(generics.RetrieveAPIView):
    serializer_class = FiscalInvoiceSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "view"

    def get_queryset(self):
        return FiscalInvoice.objects.filter(
            tenant=self.request.tenant
        ).select_related("order", "customer", "sequence")


class IssueInvoiceView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "create"

    def post(self, request):
        try:
            inv = issue_invoice(
                tenant=request.tenant,
                order_id=request.data.get("order_id"),
                sequence_id=request.data["sequence_id"],
                customer_id=request.data.get("customer_id"),
                user=request.user)
        except FiscalServiceError as e:
            return Response({"error": str(e)}, status=400)
        return Response(FiscalInvoiceSerializer(inv).data, status=201)


class CancelInvoiceView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "manage"

    def post(self, request, pk):
        try:
            inv = cancel_invoice(tenant=request.tenant, invoice_id=pk, user=request.user)
        except FiscalServiceError as e:
            return Response({"error": str(e)}, status=400)
        return Response(FiscalInvoiceSerializer(inv).data)


class FiscalDeviceListCreateView(generics.ListCreateAPIView):
    serializer_class = FiscalDeviceSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "manage"

    def get_queryset(self):
        return FiscalDevice.objects.filter(tenant=self.request.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class SubmitToDeviceView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "create"

    def post(self, request, invoice_id):
        device_id = request.data["device_id"]
        try:
            sub = submit_to_device(
                tenant=request.tenant, invoice_id=invoice_id,
                device_id=device_id, user=request.user)
        except FiscalServiceError as e:
            return Response({"error": str(e)}, status=400)
        return Response(FiscalSubmissionSerializer(sub).data)


class InvoiceXMLView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "view"

    def get(self, request, pk):
        inv = get_object_or_404(FiscalInvoice, pk=pk, tenant=request.tenant)
        return HttpResponse(inv.xml_content, content_type="application/xml",
                            headers={"Content-Disposition": f'attachment; filename="{inv.invoice_number}.xml"'})


class SubmissionListView(generics.ListAPIView):
    serializer_class = FiscalSubmissionSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "view"

    def get_queryset(self):
        qs = FiscalSubmission.objects.filter(
            tenant=self.request.tenant
        ).select_related("invoice", "device")
        inv = self.request.query_params.get("invoice_id")
        return qs.filter(invoice_id=inv) if inv else qs
