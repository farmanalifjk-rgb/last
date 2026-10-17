from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.recorder import record, snapshot
from fiscal.models import FiscalInvoice
from fiscal.pagination import OptionalPagination
from saas.permissions import HasActiveTenant, TenantRBACPermission

from .constants import INVOICE_TYPE_STRINGS
from .models import (
    FBRBuyerProfile,
    FBRTenantEligibility,
    FBRConfiguration,
    FBRHSCode,
    FBRProductProfile,
    FBRProvince,
    FBRSROSchedule,
    FBRSubmission,
    FBRTransactionType,
    FBRUnitOfMeasure,
)
from .serializers import (
    FBRBuyerProfileSerializer,
    FBRConfigurationSerializer,
    FBRHSCodeSerializer,
    FBRProductProfileSerializer,
    FBRProvinceSerializer,
    FBRReferenceSerializer,
    FBRSubmissionSerializer,
)
from .payload import FBRValidationError
from .qr import render_qr_png
from .services import (
    FBRServiceError,
    build_ims_payload,
    build_payload,
    ims_health,
    reconcile_submission,
    retry_submission,
    submit_invoice,
    validate_invoice,
)

RBAC_MODULE = "fiscal"


def _invoice_type(value):
    """Coerce a request supplied invoice type to int 1-4 or string Sale Invoice."""
    if value in (None, ""):
        return None
    # If string that matches v1.12 string enum, return it as-is for payload mapper
    allowed_strs = set(INVOICE_TYPE_STRINGS.values())
    if isinstance(value, str) and value in allowed_strs:
        return value
    # Try int 1-4
    try:
        iv = int(value)
        if iv in [1, 2, 3, 4]:
            return iv
        raise ValueError
    except (TypeError, ValueError):
        raise FBRValidationError([f"invoice_type must be integer 1-4 or one of {sorted(allowed_strs)}"])


class _TenantScopedView:
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = RBAC_MODULE

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


# Never snapshot credentials into the audit log (security_token is encrypted
# at rest and write-only in the API; only whether one is set is recorded).
_SECRET_FIELDS = {"security_token", "api_key", "password", "secret"}


def _audit_snapshot(instance):
    data = snapshot(instance, [
        field.name for field in instance._meta.fields
        if field.name not in _SECRET_FIELDS and field.name not in {"tenant", "created_at", "updated_at"}
    ])
    if hasattr(instance, "security_token"):
        data["has_security_token"] = bool(instance.security_token)
    return data


class _AuditedTenantView(_TenantScopedView):
    """Create/update/delete with a tenant-owned audit event (fbr.<entity>.<verb>)."""

    audit_entity = "record"

    def _audit(self, verb, instance, *, before=None, after=None):
        record(
            actor=self.request.user, action=f"fbr.{self.audit_entity}.{verb}", instance=instance,
            request=self.request, tenant=self.request.tenant,
            summary=f"FBR {self.audit_entity.replace('_', ' ')} {verb}.",
            before=before, after=after,
        )

    def perform_create(self, serializer):
        instance = serializer.save(tenant=self.request.tenant)
        self._audit("created", instance, after=_audit_snapshot(instance))

    def perform_update(self, serializer):
        before = _audit_snapshot(serializer.instance)
        instance = serializer.save()
        self._audit("updated", instance, before=before, after=_audit_snapshot(instance))

    def perform_destroy(self, instance):
        before = _audit_snapshot(instance)
        self._audit("deleted", instance, before=before)
        instance.delete()


class FBRConfigurationListCreateView(_AuditedTenantView, generics.ListCreateAPIView):
    serializer_class = FBRConfigurationSerializer
    rbac_action = "manage"
    audit_entity = "configuration"

    def get_queryset(self):
        return FBRConfiguration.objects.filter(tenant=self.request.tenant).select_related("seller_province")


class FBRConfigurationDetailView(_AuditedTenantView, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FBRConfigurationSerializer
    rbac_action = "manage"
    audit_entity = "configuration"

    def get_queryset(self):
        return FBRConfiguration.objects.filter(tenant=self.request.tenant)


class FBRBuyerProfileListCreateView(_TenantScopedView, generics.ListCreateAPIView):
    serializer_class = FBRBuyerProfileSerializer
    rbac_action = "manage"

    def get_queryset(self):
        return FBRBuyerProfile.objects.filter(tenant=self.request.tenant).select_related("customer", "buyer_province")


class FBRBuyerProfileDetailView(_TenantScopedView, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FBRBuyerProfileSerializer
    rbac_action = "manage"

    def get_queryset(self):
        return FBRBuyerProfile.objects.filter(tenant=self.request.tenant)


class FBRProductProfileListCreateView(_AuditedTenantView, generics.ListCreateAPIView):
    """Product fiscal profiles. ?search= (product name/SKU, HS code, product
    code) and opt-in pagination (?page=); without ?page= the full array."""

    serializer_class = FBRProductProfileSerializer
    rbac_action = "manage"
    audit_entity = "product_profile"
    pagination_class = OptionalPagination

    def get_queryset(self):
        queryset = FBRProductProfile.objects.filter(tenant=self.request.tenant).select_related(
            "product", "hs_code", "uom", "transaction_type", "sro_schedule"
        ).order_by("product__name", "id")
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(product__name__icontains=search) | Q(product__sku__icontains=search)
                | Q(hs_code__code__icontains=search) | Q(product_code__icontains=search)
            )
        return queryset


class FBRProductProfileDetailView(_AuditedTenantView, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FBRProductProfileSerializer
    rbac_action = "manage"
    audit_entity = "product_profile"

    def get_queryset(self):
        return FBRProductProfile.objects.filter(tenant=self.request.tenant)


class _ReferenceListView(_TenantScopedView, generics.ListAPIView):
    """Read-only lookups over the FBR published code lists."""

    serializer_class = FBRReferenceSerializer
    rbac_action = "view"
    model = None

    def get_queryset(self):
        queryset = self.model.objects.filter(is_active=True)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(description__icontains=search)
        return queryset


class FBRProvinceListView(_TenantScopedView, generics.ListAPIView):
    serializer_class = FBRProvinceSerializer
    rbac_action = "view"
    queryset = FBRProvince.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(code__icontains=search) | qs.filter(description__icontains=search)
        return qs


class FBRTransactionTypeListView(_ReferenceListView):
    model = FBRTransactionType


class FBRSROScheduleListView(_ReferenceListView):
    model = FBRSROSchedule


class FBRUnitOfMeasureListView(_ReferenceListView):
    model = FBRUnitOfMeasure


class FBRHSCodeListView(_TenantScopedView, generics.ListAPIView):
    serializer_class = FBRHSCodeSerializer
    rbac_action = "view"

    def get_queryset(self):
        queryset = FBRHSCode.objects.filter(is_active=True)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(code__startswith=search) | queryset.filter(
                description__icontains=search
            )
        return queryset


SUBMISSION_STATUS_FILTERS = {choice for choice, _label in FBRSubmission.STATUS_CHOICES} | {"simulated"}


def _with_action_flags(queryset):
    """Annotate the invoice-level facts allowed_actions needs (no N+1)."""
    live = FBRSubmission.objects.filter(invoice_id=OuterRef("invoice_id"), is_validate=False)
    return queryset.annotate(
        invoice_has_accepted=Exists(live.filter(status=FBRSubmission.STATUS_ACCEPTED)),
        invoice_has_other_pending=Exists(
            live.filter(status=FBRSubmission.STATUS_PENDING).exclude(pk=OuterRef("pk"))
        ),
    )


class FBRSubmissionListView(_TenantScopedView, generics.ListAPIView):
    """FBR submissions of the active tenant, newest first.

    Filters: ?invoice_id=, ?status= (pending/accepted/rejected/failed/unknown,
    or "simulated" = accepted by the simulator only; "accepted" then means
    genuinely accepted), ?search= (USIN, FBR invoice no., invoice no., order
    no.). Opt-in pagination with ?page=. Each row carries allowed_actions.
    """

    serializer_class = FBRSubmissionSerializer
    rbac_action = "view"
    pagination_class = OptionalPagination

    def get_queryset(self):
        params = self.request.query_params
        queryset = _with_action_flags(
            FBRSubmission.objects.filter(tenant=self.request.tenant).select_related("invoice", "invoice__order")
        ).order_by("-created_at", "-id")
        invoice_id = params.get("invoice_id")
        if invoice_id:
            queryset = queryset.filter(invoice_id=invoice_id)
        status_filter = (params.get("status") or "").strip().lower()
        if status_filter in SUBMISSION_STATUS_FILTERS:
            if status_filter == "simulated":
                queryset = queryset.filter(status=FBRSubmission.STATUS_ACCEPTED, is_simulated=True)
            elif status_filter == FBRSubmission.STATUS_ACCEPTED:
                queryset = queryset.filter(status=status_filter, is_simulated=False)
            else:
                queryset = queryset.filter(status=status_filter)
        search = (params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(usin__icontains=search) | Q(fbr_invoice_number__icontains=search)
                | Q(invoice__invoice_number__icontains=search) | Q(invoice__order__order_number__icontains=search)
            )
        return queryset


class FBRSubmissionDetailView(_TenantScopedView, generics.RetrieveAPIView):
    serializer_class = FBRSubmissionSerializer
    rbac_action = "view"

    def get_queryset(self):
        return _with_action_flags(
            FBRSubmission.objects.filter(tenant=self.request.tenant).select_related("invoice", "invoice__order")
        )


class FBRInvoicePreviewView(_TenantScopedView, APIView):
    """Return the exact document that would be posted, without sending it.

    ``?mode=di`` (default) returns the PRAL DI API v1.12 document;
    ``?mode=ims`` returns the Tier-1 IMS fiscal component document.
    """

    rbac_action = "view"

    def get(self, request, invoice_id):
        mode = (request.query_params.get("mode") or "di").lower()
        try:
            if mode == "ims":
                payload = build_ims_payload(
                    tenant=request.tenant,
                    invoice_id=invoice_id,
                    invoice_type=_invoice_type(request.query_params.get("invoice_type")),
                    environment=request.query_params.get("environment"),
                    ref_usin=request.query_params.get("ref_usin") or request.query_params.get("invoice_ref_no") or "",
                )
            else:
                payload = build_payload(
                    tenant=request.tenant,
                    invoice_id=invoice_id,
                    invoice_type=_invoice_type(request.query_params.get("invoice_type")),
                    environment=request.query_params.get("environment"),
                    invoice_ref_no=request.query_params.get("invoice_ref_no") or request.query_params.get("invoiceRefNo") or "",
                    scenario_id=request.query_params.get("scenario_id") or request.query_params.get("scenarioId"),
                )
        except FBRValidationError as exc:
            return Response({"errors": exc.errors}, status=400)
        except FBRServiceError as exc:
            return Response({"error": str(exc)}, status=400)
        return Response(payload)


class FBRIMSHealthView(_TenantScopedView, APIView):
    """Probe the locally installed IMS fiscal component (GET /api/IMSFiscal/get)."""

    rbac_action = "view"

    def get(self, request):
        try:
            result = ims_health(tenant=request.tenant, environment=request.query_params.get("environment"))
        except FBRServiceError as exc:
            return Response({"error": str(exc)}, status=400)
        status = 200 if result["status"] == "responding" else 502
        return Response(result, status=status)


class FBRSubmitInvoiceView(_TenantScopedView, APIView):
    rbac_action = "create"

    def post(self, request, invoice_id):
        try:
            submission = submit_invoice(
                tenant=request.tenant,
                invoice_id=invoice_id,
                invoice_type=_invoice_type(request.data.get("invoice_type")),
                environment=request.data.get("environment"),
                invoice_ref_no=request.data.get("invoice_ref_no") or request.data.get("invoiceRefNo") or "",
                scenario_id=request.data.get("scenario_id") or request.data.get("scenarioId"),
                user=request.user,
            )
        except FBRValidationError as exc:
            return Response({"errors": exc.errors}, status=400)
        except FBRServiceError as exc:
            return Response({"error": str(exc)}, status=400)
        return Response(
            FBRSubmissionSerializer(submission).data,
            status=_submission_http_status(submission, created=201),
        )


class FBRValidateInvoiceView(_TenantScopedView, APIView):
    """Dry-run validate via PRAL validateinvoicedata (v1.12 §4.2) — does not book."""

    rbac_action = "create"

    def post(self, request, invoice_id):
        try:
            submission = validate_invoice(
                tenant=request.tenant,
                invoice_id=invoice_id,
                invoice_type=_invoice_type(request.data.get("invoice_type")),
                environment=request.data.get("environment"),
                invoice_ref_no=request.data.get("invoice_ref_no") or request.data.get("invoiceRefNo") or "",
                scenario_id=request.data.get("scenario_id") or request.data.get("scenarioId"),
                user=request.user,
            )
        except FBRValidationError as exc:
            return Response({"errors": exc.errors}, status=400)
        except FBRServiceError as exc:
            return Response({"error": str(exc)}, status=400)
        # Validate always returns 200 with validation payload even if FBR says Invalid — front-end should inspect statusCode
        return Response(FBRSubmissionSerializer(submission).data, status=200)


class FBRRetrySubmissionView(_TenantScopedView, APIView):
    rbac_action = "create"

    def post(self, request, pk):
        try:
            submission = retry_submission(tenant=request.tenant, submission_id=pk, user=request.user)
        except FBRValidationError as exc:
            return Response({"errors": exc.errors}, status=400)
        except FBRServiceError as exc:
            return Response({"error": str(exc)}, status=400)
        record(
            actor=request.user, action="fbr.submission.retried", instance=submission, request=request,
            tenant=request.tenant, summary=f"Retried FBR submission {pk}: {submission.status}.",
            after={"status": submission.status, "attempts": submission.attempts, "is_simulated": submission.is_simulated},
        )
        return Response(
            FBRSubmissionSerializer(submission, context={"request": request}).data,
            status=_submission_http_status(submission, created=200),
        )


def _submission_http_status(submission, *, created):
    """Map a submission outcome to an honest HTTP status (audit fix).

    2xx — accepted (or dry-run/unknown handled by their endpoints);
    422 — FBR rejected the document (client-fixable data);
    502 — upstream unavailable/failed; 200-family for reconcile endpoint.
    """
    if submission.status == FBRSubmission.STATUS_ACCEPTED:
        return created
    if submission.status == FBRSubmission.STATUS_REJECTED:
        return 422
    return 502


class FBRReconcileSubmissionView(_TenantScopedView, APIView):
    """Resolve a submission with an unknown outcome (timeout) after an
    operator has verified the truth in the component / FBR portal."""

    rbac_action = "manage"

    def post(self, request, pk):
        try:
            submission = reconcile_submission(
                tenant=request.tenant,
                submission_id=pk,
                outcome=request.data.get("outcome"),
                fiscal_invoice_number=request.data.get("fiscal_invoice_number")
                or request.data.get("fbr_invoice_number") or "",
                user=request.user,
            )
        except FBRServiceError as exc:
            return Response({"error": str(exc)}, status=400)
        # The operator asserts the fiscal outcome: always audited.
        record(
            actor=request.user, action="fbr.submission.reconciled", instance=submission, request=request,
            tenant=request.tenant,
            summary=f"Reconciled FBR submission {pk} as {request.data.get('outcome')}.",
            after={"status": submission.status, "fbr_invoice_number": submission.fbr_invoice_number,
                   "outcome": request.data.get("outcome")},
        )
        return Response(FBRSubmissionSerializer(submission, context={"request": request}).data, status=200)


class FBREligibilityView(_TenantScopedView, APIView):
    """The fiscalization tracks the active tenant is eligible to configure."""

    rbac_action = "view"

    def get(self, request):
        row = FBRTenantEligibility.objects.filter(tenant=request.tenant, is_active=True).first()
        return Response({
            "allowed_modes": sorted(row.allowed_mode_set()) if row else ["di"],
            "verified": row is not None,
            "reference": row.reference if row else "",
        })


class FBRInvoiceQRView(_TenantScopedView, APIView):
    """PNG QR code carrying the FBR tracking number of an accepted invoice."""

    rbac_action = "view"

    def get(self, request, invoice_id):
        invoice = get_object_or_404(FiscalInvoice, pk=invoice_id, tenant=request.tenant)
        if not invoice.fbr_invoice_number:
            return Response({"error": "This invoice has not been accepted by FBR yet."}, status=400)
        if invoice.fbr_invoice_number.upper().startswith("SIM-") or FBRSubmission.objects.filter(
            invoice=invoice, status=FBRSubmission.STATUS_ACCEPTED, is_validate=False, is_simulated=True,
        ).exists():
            # Never render a fiscal QR for a simulator outcome (the SIM- prefix
            # also covers rows written before is_simulated existed).
            return Response({"error": "This invoice was only accepted by the FBR simulator, not by FBR."}, status=400)
        return HttpResponse(render_qr_png(invoice.fbr_invoice_number), content_type="image/png")
