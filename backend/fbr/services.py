"""Tenant-scoped orchestration of FBR fiscal submissions (DI v1.12 + Tier-1 IMS).

Every function takes an explicit tenant and re-reads the objects it is given by
ID under that tenant, so a client-supplied ID can never reach another tenant's
data.

Submission invariants (production-hardening audit H1/H2/H5/H9/H10):

* At most one PENDING fiscalization per invoice exists at any time — enforced
  by a partial unique constraint and checked under a row lock, so concurrent
  callers can never trigger two external fiscalization calls.
* Each submission FREEZES its fiscalization track (``integration_mode``) at
  creation; retries reuse the frozen track even if the tenant's configuration
  changes afterwards.
* Purchase invoices are never fiscalized.
* A transport timeout moves the submission to ``unknown`` — it must be
  reconciled by an operator before another external attempt is allowed.
* Acceptance of a fiscal number and the receipt update on ``FiscalInvoice``
  are applied transactionally, and any accepted submission self-heals a
  missing receipt number on the idempotent early-return path.
"""
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from fiscal.models import FiscalInvoice

from .client import FBRClient, FBRTransportError
from .constants import (
    INTEGRATION_MODE_DI,
    INTEGRATION_MODE_IMS,
    INVOICE_TYPE_CREDIT_NOTE,
    INVOICE_TYPE_PURCHASE,
    INVOICE_TYPE_SALE,
)
from .ims_client import IMSFiscalClient, IMSTransportError
from .ims_payload import build_ims_invoice_payload
from .models import FBRConfiguration, FBRSubmission
from .payload import FBRValidationError, build_invoice_payload
from .transport import OUTCOME_UNKNOWN, classify_transport_outcome


class FBRServiceError(Exception):
    """A submission could not be started for a business reason."""


def get_configuration(tenant, environment=None):
    queryset = FBRConfiguration.objects.filter(tenant=tenant, is_active=True)
    if environment:
        queryset = queryset.filter(environment=environment)
    config = queryset.select_related("default_transaction_type", "seller_province").order_by("environment").first()
    if config is None:
        raise FBRServiceError("No active FBR configuration exists for this tenant.")
    return config


def get_invoice(tenant, invoice_id):
    invoice = (
        FiscalInvoice.objects.filter(tenant=tenant, pk=invoice_id)
        .select_related("order", "customer", "customer__fbr_profile", "customer__fbr_profile__buyer_province", "sequence")
        .first()
    )
    if invoice is None:
        raise FBRServiceError("Fiscal invoice not found for the active tenant.")
    return invoice


def default_invoice_type(invoice):
    if invoice.sequence and invoice.sequence.document_type == invoice.sequence.TYPE_CREDIT_NOTE:
        return INVOICE_TYPE_CREDIT_NOTE
    return INVOICE_TYPE_SALE


def build_payload(*, tenant, invoice_id, invoice_type=None, environment=None, invoice_ref_no="", scenario_id=None):
    """Validate an invoice and return the DI document that would be posted (v1.12)."""
    invoice = get_invoice(tenant, invoice_id)
    config = get_configuration(tenant, environment)
    if config.integration_mode == INTEGRATION_MODE_IMS:
        raise FBRServiceError(
            "The active FBR configuration is in IMS mode — use preview?mode=ims for the IMS document."
        )
    return build_invoice_payload(
        invoice, config=config, invoice_type=invoice_type or default_invoice_type(invoice),
        invoice_ref_no=invoice_ref_no, scenario_id=scenario_id,
    )


def build_ims_payload(*, tenant, invoice_id, invoice_type=None, environment=None, ref_usin=""):
    """Validate an invoice and return the Tier-1 IMS document that would be posted."""
    invoice = get_invoice(tenant, invoice_id)
    config = get_configuration(tenant, environment)
    if config.integration_mode != INTEGRATION_MODE_IMS:
        raise FBRServiceError(
            "The active FBR configuration is not in IMS mode — set integration_mode='ims' first."
        )
    return build_ims_invoice_payload(
        invoice, config=config, di_invoice_type=invoice_type or default_invoice_type(invoice),
        ref_usin=ref_usin,
    )


def _simulator_available_for(config):
    from .simulator import simulator_is_available

    return simulator_is_available(config.environment)


def _ims_client_for_configuration(config):
    """Return the IMS client for *config* — never a silent substitution.

    * A configuration that has not opted in (``use_simulator=False``) always
      talks to its real target (local component or official PRAL endpoint),
      whatever the deployment's simulator flags say.
    * An opted-in configuration gets the isolated simulator only when the
      deployment enables it for that environment (FBR_SIMULATOR_ENABLED and a
      matching FBR_SIMULATOR_MODE; production settings can never enable it).
      Otherwise it fails closed: nothing is sent to FBR or a component.
    """
    if not getattr(config, "use_simulator", False):
        return IMSFiscalClient(config)
    if not _simulator_available_for(config):
        raise FBRServiceError(
            "This FBR configuration is set to use the IMS simulator, but the simulator is not enabled "
            f"for the '{config.environment}' environment on this deployment. Nothing was sent to FBR. "
            "Turn off use_simulator to fiscalize through the real IMS component."
        )
    from .simulator import IMSSimulatorClient
    return IMSSimulatorClient(config)


def _is_simulator_client(client):
    return bool(getattr(client, "is_simulator", False))


def ims_health(*, tenant, environment=None):
    """Probe the locally installed IMS fiscal component (GET /api/IMSFiscal/get).

    The response is deliberately minimal: it never echoes the component URL or
    any remote response content back to the API caller (SSRF-hardening).
    """
    config = get_configuration(tenant, environment)
    if config.integration_mode != INTEGRATION_MODE_IMS:
        raise FBRServiceError("The active FBR configuration is not in IMS mode.")
    client = _ims_client_for_configuration(config)
    try:
        client.health_check()
    except IMSTransportError:
        return {"status": "unreachable", "error": "The IMS fiscal component did not respond or is not installed."}
    if _is_simulator_client(client):
        # Never let the simulator pass for a reachable real component.
        return {"status": "responding", "simulated": True}
    return {"status": "responding"}


def _accepted_submission(invoice):
    return FBRSubmission.objects.filter(invoice=invoice, status=FBRSubmission.STATUS_ACCEPTED, is_validate=False).first()


def _pending_submission(invoice):
    return FBRSubmission.objects.filter(invoice=invoice, status=FBRSubmission.STATUS_PENDING, is_validate=False).first()


def _ensure_acceptance_applied(submission):
    """Self-heal (audit H10): an accepted submission must always be reflected
    on the receipt. Re-applies the fiscal number + QR payload when the invoice
    row is missing them (e.g. a historical partial failure)."""
    invoice = submission.invoice
    if invoice.fbr_invoice_number != submission.fbr_invoice_number:
        _apply_acceptance(invoice, submission)


def _apply_acceptance(invoice, submission):
    """Store the tracking number FBR requires on the printed invoice.

    A simulated acceptance is test evidence only: it is never written to the
    fiscal invoice, so no SIM number or QR can reach a receipt.
    """
    from fiscal.services import build_qr_payload

    if getattr(submission, "is_simulated", False):
        return

    invoice.fbr_invoice_number = submission.fbr_invoice_number
    invoice.qr_payload = build_qr_payload(invoice)
    invoice.save(update_fields=["fbr_invoice_number", "qr_payload"])


def _save_submission_safely(submission):
    """Persist a response outcome, resolving the accepted-constraint race.

    Returns ``None`` when *submission* itself was saved, or the earlier
    accepted submission that won the race (audit H1) — in which case the lost
    row is parked as rejected so it cannot block future work.
    """
    try:
        submission.save()
        return None
    except IntegrityError:
        accepted = _accepted_submission(submission.invoice)
        if accepted is not None and accepted.pk != submission.pk:
            if submission.status == FBRSubmission.STATUS_PENDING:
                submission.status = FBRSubmission.STATUS_REJECTED
                submission.error_message = f"Superseded by accepted submission {accepted.pk}."
                try:
                    submission.save(update_fields=["status", "error_message"])
                except IntegrityError:
                    pass
            return accepted
        raise


def _record_response(submission, response):
    """Persist a DI-track response (v1.12 or legacy v1.0)."""
    submission.status_code = str(response.status_code) if response.status_code is not None else ""
    submission.status_code_legacy = response.http_status
    submission.error_message = response.error_message
    submission.error_code = getattr(response, "error_code", "") or ""
    submission.errors = response.errors
    submission.response_payload = response.raw
    submission.validation_response = getattr(response, "validation_response", {}) or {}
    ts = getattr(response, "dated", "") or getattr(response, "timestamp", "") or ""
    submission.response_timestamp = str(ts)
    submission.responded_at = timezone.now()
    if response.accepted:
        submission.status = FBRSubmission.STATUS_ACCEPTED
        inv_no = getattr(response, "invoice_number", "") or getattr(response, "result", "")
        submission.fbr_invoice_number = inv_no
    else:
        submission.status = FBRSubmission.STATUS_REJECTED
    if getattr(response, "invoice_number", ""):
        submission.fbr_invoice_number = response.invoice_number
    saved = _save_submission_safely(submission)
    return saved if saved is not None else submission


def _record_ims_response(submission, response):
    """Persist the IMS component's fiscal response (Code "100" = fiscalized)."""
    submission.ims_code = response.code
    submission.status_code = response.code  # reuse the generic status column
    submission.error_message = response.message if not response.accepted else ""
    submission.errors = response.errors
    submission.response_payload = response.raw
    submission.responded_at = timezone.now()
    if response.accepted:
        submission.status = FBRSubmission.STATUS_ACCEPTED
        submission.fbr_invoice_number = response.invoice_number
    else:
        submission.status = FBRSubmission.STATUS_REJECTED
        if response.errors:
            submission.error_message = "; ".join(response.errors)
    saved = _save_submission_safely(submission)
    return saved if saved is not None else submission


def _record_transport_failure(submission, exc):
    """Persist a transport failure, distinguishing failed from unknown (H9)."""
    if classify_transport_outcome(exc) == OUTCOME_UNKNOWN:
        submission.status = FBRSubmission.STATUS_UNKNOWN
        submission.error_message = str(exc)
    else:
        submission.status = FBRSubmission.STATUS_FAILED
        submission.error_message = str(exc)
    update_fields = ["status", "error_message", "responded_at"]
    simulator_response = getattr(exc, "simulator_response", None)
    if simulator_response is not None:
        submission.response_payload = simulator_response
        submission.ims_code = str(simulator_response.get("Code", ""))
        submission.status_code = submission.ims_code
        submission.errors = simulator_response.get("Errors") or []
        update_fields.extend(["response_payload", "ims_code", "status_code", "errors"])
    submission.responded_at = timezone.now()
    submission.save(update_fields=update_fields)
    return submission


def _dispatch(submission, config, *, client=None):
    """Run the external call for *submission* on its frozen track (H2)."""
    if submission.integration_mode == INTEGRATION_MODE_IMS:
        client = client or _ims_client_for_configuration(config)
        try:
            response = client.fiscalize(submission.request_payload)
        except IMSTransportError as exc:
            return _record_transport_failure(submission, exc)
        with transaction.atomic():
            recorded = _record_ims_response(submission, response)
            if recorded.pk == submission.pk and recorded.status == FBRSubmission.STATUS_ACCEPTED:
                _apply_acceptance(recorded.invoice, recorded)
            return recorded
    client = client or FBRClient(config)
    try:
        response = client.post_invoice(submission.request_payload)
    except FBRTransportError as exc:
        return _record_transport_failure(submission, exc)
    with transaction.atomic():
        recorded = _record_response(submission, response)
        if recorded.pk == submission.pk and recorded.status == FBRSubmission.STATUS_ACCEPTED:
            _apply_acceptance(recorded.invoice, recorded)
        return recorded


def _check_purchase_type(invoice_type):
    """Purchases are never fiscalized as FBR sales (audit H5)."""
    if isinstance(invoice_type, int) and invoice_type == INVOICE_TYPE_PURCHASE:
        raise FBRServiceError(
            "Purchase invoices are not fiscalized: FBR fiscalization applies to sales "
            "(and their debit/credit notes) only."
        )


def submit_invoice(*, tenant, invoice_id, invoice_type=None, environment=None, invoice_ref_no="", scenario_id=None, user=None, client=None):
    """Fiscalize an issued invoice on the tenant's configured track.

    Idempotent per invoice: an accepted invoice is never posted twice, and a
    concurrent caller while a submission is in flight gets an explicit error
    instead of a second external call (audit H1). The submission freezes the
    configuration's fiscalization track (audit H2).
    """
    invoice = get_invoice(tenant, invoice_id)
    if invoice.status != FiscalInvoice.STATUS_ISSUED:
        raise FBRServiceError(f"Only issued invoices can be posted to FBR; this one is '{invoice.status}'.")

    invoice_type = invoice_type or default_invoice_type(invoice)
    _check_purchase_type(invoice_type)

    existing = _accepted_submission(invoice)
    if existing is not None:
        _ensure_acceptance_applied(existing)
        return existing

    config = get_configuration(tenant, environment)
    mode = config.integration_mode
    if mode == INTEGRATION_MODE_IMS and client is None:
        # Resolve the target before any submission row exists so a fail-closed
        # simulator configuration never leaves a stranded pending submission.
        client = _ims_client_for_configuration(config)
    if mode == INTEGRATION_MODE_IMS:
        payload = build_ims_invoice_payload(
            invoice, config=config, di_invoice_type=invoice_type, ref_usin=invoice_ref_no,
        )
    else:
        payload = build_invoice_payload(
            invoice, config=config, invoice_type=invoice_type,
            invoice_ref_no=invoice_ref_no, scenario_id=scenario_id,
        )

    with transaction.atomic():
        locked = FiscalInvoice.objects.select_for_update().get(pk=invoice.pk, tenant=tenant)
        existing = _accepted_submission(locked)
        if existing is not None:
            return existing
        in_progress = _pending_submission(locked)
        if in_progress is not None:
            raise FBRServiceError(
                f"A fiscalization for this invoice is already in progress (submission {in_progress.pk}); "
                "check its outcome before submitting again."
            )
        unresolved = FBRSubmission.objects.filter(
            invoice=locked, status=FBRSubmission.STATUS_UNKNOWN, is_validate=False,
        ).order_by("-id").first()
        if unresolved is not None:
            # Same rule as retry_submission: a previous attempt may already
            # have been recorded by FBR. Posting a new submission would risk
            # a second fiscal invoice for the same sale.
            raise FBRServiceError(
                f"A previous fiscalization of this invoice has an unknown outcome (submission {unresolved.pk}, "
                f"USIN {unresolved.usin or 'n/a'}). Reconcile it first via "
                f"POST /api/fbr/submissions/{unresolved.pk}/reconcile/."
            )
        submission = FBRSubmission(
            tenant=tenant,
            invoice=invoice,
            configuration=config,
            environment=config.environment,
            integration_mode=mode,
            invoice_type=invoice_type if isinstance(invoice_type, int) else 2,
            status=FBRSubmission.STATUS_PENDING,
            request_payload=payload,
            attempts=1,
            dispatched_at=timezone.now(),
            created_by=user,
            invoice_ref_no=invoice_ref_no or "",
            usin=payload.get("USIN", "") if mode == INTEGRATION_MODE_IMS else "",
            is_validate=False,
            is_simulated=_is_simulator_client(client),
        )
        submission.full_clean(exclude=["errors", "request_payload", "response_payload", "validation_response"])
        submission.save()

    return _dispatch(submission, config, client=client)


def retry_submission(*, tenant, submission_id, user=None, client=None):
    """Re-post a rejected/failed submission using its frozen fiscal track.

    The database lock protects the state transition, but the external FBR call
    happens after the transaction commits so a slow network call never holds a
    row lock unnecessarily.
    """
    with transaction.atomic():
        # Lock only the FBRSubmission row.  Do not combine FOR UPDATE with
        # select_related() here because invoice/configuration are nullable
        # relations; PostgreSQL rejects FOR UPDATE on the nullable side of
        # an outer join.  Relations are loaded after the lock is acquired.
        submission = FBRSubmission.objects.select_for_update().filter(
            tenant=tenant, pk=submission_id
        ).first()
        if submission is None:
            raise FBRServiceError("FBR submission not found for the active tenant.")
        submission = FBRSubmission.objects.select_related(
            "invoice", "configuration"
        ).get(pk=submission.pk)
        if submission.status == FBRSubmission.STATUS_UNKNOWN:
            raise FBRServiceError(
                "The previous fiscalization attempt timed out and its outcome is unknown "
                f"(USIN {submission.usin or 'n/a'}). Reconcile it first via "
                f"POST /api/fbr/submissions/{submission.pk}/reconcile/ before retrying."
            )
        if submission.status == FBRSubmission.STATUS_PENDING:
            # In flight (or interrupted mid-call): re-posting it could record
            # the invoice twice. fbr_process_pending moves a stale pending
            # submission to UNKNOWN, which then needs reconciliation.
            raise FBRServiceError(
                "This fiscalization is still in progress; wait for its outcome "
                "(a submission with no response is later marked unknown and must be reconciled)."
            )
        if submission.status == FBRSubmission.STATUS_ACCEPTED and not submission.is_validate:
            raise FBRServiceError("This submission was already accepted by FBR.")
        if _accepted_submission(submission.invoice) is not None:
            raise FBRServiceError("This invoice was already accepted by FBR.")
        other_pending = FBRSubmission.objects.filter(
            invoice=submission.invoice,
            status=FBRSubmission.STATUS_PENDING,
            is_validate=False,
        ).exclude(pk=submission.pk).first()
        if other_pending is not None:
            raise FBRServiceError(
                f"Another fiscalization for this invoice is in progress (submission {other_pending.pk})."
            )

        mode = submission.integration_mode or INTEGRATION_MODE_DI
        config = submission.configuration or get_configuration(tenant, submission.environment)
        inv_ref = submission.invoice_ref_no or ""
        scenario = (
            submission.request_payload.get("scenarioId")
            if isinstance(submission.request_payload, dict)
            else None
        )
        invoice = get_invoice(tenant, submission.invoice_id)
        if mode == INTEGRATION_MODE_IMS and client is None:
            # The simulated/real target is frozen with the submission, exactly
            # like the track (H2): a retry never moves a real attempt onto the
            # simulator, nor a simulated one onto the real component.
            client = _ims_client_for_configuration(config)
            if _is_simulator_client(client) != submission.is_simulated:
                raise FBRServiceError(
                    "This submission was made against the "
                    f"{'simulator' if submission.is_simulated else 'real IMS component'}, but the configuration "
                    "now targets the "
                    f"{'simulator' if _is_simulator_client(client) else 'real IMS component'}. "
                    "It cannot be retried on a different target."
                )
        if mode == INTEGRATION_MODE_IMS:
            submission.request_payload = build_ims_invoice_payload(
                invoice, config=config,
                di_invoice_type=submission.invoice_type,
                ref_usin=inv_ref,
            )
        else:
            submission.request_payload = build_invoice_payload(
                invoice, config=config,
                invoice_type=submission.invoice_type,
                invoice_ref_no=inv_ref,
                scenario_id=scenario,
            )
        submission.integration_mode = mode
        submission.status = FBRSubmission.STATUS_PENDING
        submission.attempts += 1
        submission.dispatched_at = timezone.now()
        submission.save(update_fields=["request_payload", "integration_mode", "status", "attempts", "dispatched_at"])

    return _dispatch(submission, config, client=client)


@transaction.atomic
def reconcile_submission(*, tenant, submission_id, outcome, fiscal_invoice_number="", user=None):
    """Resolve a submission whose external outcome is unknown (audit H9).

    The operator verifies the truth in the component / FBR portal (or at the
    counter) and records it:
      * ``fiscalized``      — the sale WAS fiscalized; requires the fiscal
                              invoice number, marks the submission accepted
                              and updates the receipt.
      * ``not_fiscalized``  — it was not; the submission is marked failed and
                              may be retried (posting the same USIN).
    """
    submission = FBRSubmission.objects.select_for_update().filter(tenant=tenant, pk=submission_id).select_related("invoice").first()
    if submission is None:
        raise FBRServiceError("FBR submission not found for the active tenant.")
    if submission.status != FBRSubmission.STATUS_UNKNOWN:
        raise FBRServiceError("Only submissions with an unknown outcome can be reconciled.")
    if _accepted_submission(submission.invoice) is not None:
        raise FBRServiceError("This invoice was already accepted by FBR.")
    outcome = (outcome or "").strip().lower()
    if outcome == "fiscalized":
        fiscal_invoice_number = (fiscal_invoice_number or "").strip()
        if not fiscal_invoice_number:
            raise FBRServiceError(
                "Reconciling as fiscalized requires the fiscal invoice number assigned by the component/FBR."
            )
        submission.status = FBRSubmission.STATUS_ACCEPTED
        submission.fbr_invoice_number = fiscal_invoice_number
        submission.error_message = "Reconciled by operator: fiscalized."
        submission.save(update_fields=["status", "fbr_invoice_number", "error_message"])
        _apply_acceptance(submission.invoice, submission)
    elif outcome == "not_fiscalized":
        submission.status = FBRSubmission.STATUS_FAILED
        submission.error_message = "Reconciled by operator: not fiscalized — safe to retry."
        submission.save(update_fields=["status", "error_message"])
    else:
        raise FBRServiceError("outcome must be 'fiscalized' or 'not_fiscalized'.")
    return submission


def validate_invoice(*, tenant, invoice_id, invoice_type=None, environment=None, invoice_ref_no="", scenario_id=None, user=None, client=None):
    """Dry-run validate via PRAL validateinvoicedata (DI track only, does not book)."""
    invoice = get_invoice(tenant, invoice_id)
    config = get_configuration(tenant, environment)
    if config.integration_mode == INTEGRATION_MODE_IMS:
        raise FBRServiceError(
            "validateinvoicedata is a PRAL DI operation. The Tier-1 IMS track has no server-side "
            "validation — use GET preview?mode=ims to inspect the exact fiscal document."
        )
    invoice_type = invoice_type or default_invoice_type(invoice)
    _check_purchase_type(invoice_type)
    payload = build_invoice_payload(invoice, config=config, invoice_type=invoice_type, invoice_ref_no=invoice_ref_no, scenario_id=scenario_id)
    # Record as is_validate submission so it does not count toward unique accepted constraint
    with transaction.atomic():
        submission = FBRSubmission(
            tenant=tenant,
            invoice=invoice,
            configuration=config,
            environment=config.environment,
            integration_mode=INTEGRATION_MODE_DI,
            invoice_type=invoice_type if isinstance(invoice_type, int) else 2,
            status=FBRSubmission.STATUS_PENDING,
            request_payload=payload,
            attempts=1,
            dispatched_at=timezone.now(),
            created_by=user,
            invoice_ref_no=invoice_ref_no or "",
            is_validate=True,
        )
        submission.full_clean(exclude=["errors", "request_payload", "response_payload", "validation_response"])
        submission.save()
    # Post to validate endpoint
    client = client or FBRClient(config)
    try:
        response = client.validate_invoice(submission.request_payload)
    except FBRTransportError as exc:
        submission.status = FBRSubmission.STATUS_FAILED
        submission.error_message = str(exc)
        submission.responded_at = timezone.now()
        submission.save(update_fields=["status", "error_message", "responded_at"])
        return submission
    return _record_response(submission, response)


__all__ = [
    "FBRServiceError",
    "FBRValidationError",
    "build_ims_payload",
    "build_payload",
    "get_configuration",
    "ims_health",
    "reconcile_submission",
    "retry_submission",
    "submit_invoice",
    "validate_invoice",
]
