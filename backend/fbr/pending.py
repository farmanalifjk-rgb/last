"""Background processing of FBR fiscalization (cashier audit E1/E2).

Checkout makes ONE short fiscalization attempt while the cashier waits
(``fiscal.pos_fiscalization.fiscalize_pos_order``). Whatever that attempt did
not finish is handled here, by ``manage.py fbr_process_pending`` run on a
schedule (cron / systemd timer / Task Scheduler, e.g. every minute).

One run does three things, in this order, each tenant-scoped through the row's
own tenant (``tenant=`` narrows the run to one tenant):

1. **Stale pending -> unknown.** A non-validate submission still ``pending``
   ``stale_minutes`` after it was dispatched never recorded a response (the
   worker died mid-call). The request may have been delivered, so it becomes
   ``unknown`` and must be reconciled by a person. It is never resent.
2. **Never-dispatched POS invoices -> submit.** An issued POS sale invoice on
   a tenant with an active IMS (FBR PoS) configuration that has **no**
   submission at all was never sent (a submission row is committed before any
   network call). These are submitted once, normally.
3. **Failed -> retry with backoff.** The latest submission of an invoice that
   is ``failed`` (provably not delivered, or the endpoint said 429/503, or a
   person reconciled it as not fiscalized) is retried through
   ``retry_submission`` up to ``max_attempts`` attempts in total, waiting
   ``min(2**(attempts-1), 60)`` minutes after the last response.

Never touched: ``accepted``, ``rejected`` (FBR answered no: the data needs a
person), ``unknown`` (reconcile first), validate dry-runs, DI-track failures
(retried manually from the Fiscal screens), inactive configurations, and any
invoice with an accepted/pending/unknown submission.
"""
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from .constants import INTEGRATION_MODE_IMS
from .models import FBRSubmission

logger = logging.getLogger(__name__)

AUTO_RETRY_MAX_ATTEMPTS_DEFAULT = 5
PENDING_STALE_MINUTES_DEFAULT = 10
PENDING_STALE_MINUTES_MINIMUM = 2
# An invoice issued by a checkout is submitted by that checkout a moment
# later; leave it alone for this long so the till and the processor do not race.
FRESH_INVOICE_GRACE = timedelta(minutes=2)
UNSUBMITTED_MAX_AGE_HOURS_DEFAULT = 72
STALE_PENDING_MESSAGE = (
    "No response was recorded for this fiscalization; the request may have been delivered. "
    "Reconcile it (fiscalized / not fiscalized) before any retry."
)


@dataclass
class PendingRunReport:
    dry_run: bool = False
    marked_unknown: list = field(default_factory=list)   # submission ids
    submitted: list = field(default_factory=list)        # (invoice id, resulting status)
    retried: list = field(default_factory=list)          # (submission id, resulting status)
    skipped: list = field(default_factory=list)          # (kind, id, reason)
    errors: list = field(default_factory=list)           # (kind, id, message)


def _audit(action, submission, summary):
    """Audit an automatic action (no human actor) on the submission's tenant."""
    from audit.recorder import record

    try:
        record(
            action=action, instance=submission, tenant=submission.tenant,
            summary=f"{summary} (automatic: fbr_process_pending)",
            after={"status": submission.status, "attempts": submission.attempts, "is_simulated": submission.is_simulated},
        )
    except Exception:  # noqa: BLE001 - the fiscal outcome is already stored on the row
        logger.exception("Could not audit %s for FBR submission %s", action, submission.pk)


def _setting(name, default):
    value = getattr(settings, name, default)
    return default if value in (None, "") else int(value)


def retry_backoff(attempts):
    """Minutes to wait after the last response before automatic attempt N+1."""
    return timedelta(minutes=min(2 ** max(attempts - 1, 0), 60))


def _blocking_sibling(invoice_id):
    """Submissions that rule out any automatic action on the invoice."""
    return FBRSubmission.objects.filter(
        invoice_id=invoice_id,
        is_validate=False,
        status__in=[FBRSubmission.STATUS_ACCEPTED, FBRSubmission.STATUS_PENDING, FBRSubmission.STATUS_UNKNOWN],
    )


def longest_call(configuration):
    """Upper bound of one non-interactive client call for *configuration*.

    Each attempt may spend the timeout on connect and again on read, plus the
    capped backoff sleeps between attempts. A pending submission younger than
    this may still be in flight.
    """
    if configuration is None:
        return timedelta(0)
    attempts = max(1, (configuration.max_retries or 0) + 1)
    per_attempt = 2 * (configuration.timeout_seconds or 0)
    sleeps = sum(min(2 ** (n - 1), 8) for n in range(1, attempts))
    return timedelta(seconds=attempts * per_attempt + sleeps)


def mark_stale_pending(*, tenant=None, stale_minutes, limit, dry_run, now, report):
    stale = timedelta(minutes=stale_minutes)
    cutoff = now - stale
    qs = FBRSubmission.objects.filter(status=FBRSubmission.STATUS_PENDING, is_validate=False).filter(
        Q(dispatched_at__lt=cutoff) | Q(dispatched_at__isnull=True, created_at__lt=cutoff)
    ).select_related("configuration")
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    for submission in qs.order_by("id")[:limit]:
        since = submission.dispatched_at or submission.created_at
        if now - since < max(stale, longest_call(submission.configuration)):
            report.skipped.append(("submission", submission.pk, "may still be in flight"))
            continue
        if dry_run:
            report.marked_unknown.append(submission.pk)
            continue
        # Conditional update: a response that arrived meanwhile wins.
        changed = FBRSubmission.objects.filter(pk=submission.pk, status=FBRSubmission.STATUS_PENDING).update(
            status=FBRSubmission.STATUS_UNKNOWN, error_message=STALE_PENDING_MESSAGE,
        )
        if changed:
            logger.warning(
                "FBR submission %s (tenant %s) had no response after %s min; marked unknown.",
                submission.pk, submission.tenant_id, stale_minutes,
            )
            report.marked_unknown.append(submission.pk)
            submission.refresh_from_db()
            _audit("fbr.submission.marked_unknown", submission,
                   f"FBR submission {submission.pk} had no response; marked unknown, reconcile before any retry.")


def submit_never_dispatched(*, tenant=None, max_age_hours, limit, dry_run, now, report):
    from fiscal.models import FiscalInvoice, InvoiceSequence
    from fiscal.pos_fiscalization import till_fiscalization_configured

    from .services import submit_invoice

    qs = (
        FiscalInvoice.objects.filter(
            status=FiscalInvoice.STATUS_ISSUED,
            order__isnull=False,
            sequence__document_type=InvoiceSequence.TYPE_INVOICE,
            created_at__lt=now - FRESH_INVOICE_GRACE,
            created_at__gte=now - timedelta(hours=max_age_hours),
        )
        .annotate(has_submission=Exists(
            FBRSubmission.objects.filter(invoice=OuterRef("pk"), is_validate=False)
        ))
        .filter(has_submission=False)
        .select_related("tenant")
    )
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    configured = {}
    for invoice in qs.order_by("id")[:limit]:
        if invoice.tenant_id not in configured:
            configured[invoice.tenant_id] = till_fiscalization_configured(invoice.tenant)
        if not configured[invoice.tenant_id]:
            report.skipped.append(("invoice", invoice.pk, "tenant has no active FBR PoS (IMS) configuration"))
            continue
        if dry_run:
            report.submitted.append((invoice.pk, "would submit"))
            continue
        try:
            submission = submit_invoice(tenant=invoice.tenant, invoice_id=invoice.pk)
        except Exception as exc:  # noqa: BLE001 - one bad invoice must not stop the run
            logger.warning("FBR processor could not submit invoice %s: %s", invoice.pk, exc)
            report.errors.append(("invoice", invoice.pk, str(exc)[:300]))
            continue
        report.submitted.append((invoice.pk, submission.status))
        _audit("fbr.invoice.submitted", submission,
               f"Submitted invoice {invoice.invoice_number} to FBR: {submission.status}.")


def retry_failed(*, tenant=None, max_attempts, limit, dry_run, now, report):
    from fiscal.models import FiscalInvoice

    from .services import retry_submission

    latest_id = (
        FBRSubmission.objects.filter(invoice=OuterRef("invoice"), is_validate=False)
        .order_by("-id").values("id")[:1]
    )
    qs = (
        FBRSubmission.objects.filter(
            status=FBRSubmission.STATUS_FAILED,
            is_validate=False,
            integration_mode=INTEGRATION_MODE_IMS,
            attempts__lt=max_attempts,
            invoice__status=FiscalInvoice.STATUS_ISSUED,
            configuration__is_active=True,
        )
        .filter(id=Subquery(latest_id))
        .select_related("tenant")
    )
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    for submission in qs.order_by("id")[:limit]:
        last = submission.responded_at or submission.dispatched_at or submission.created_at
        if last and now - last < retry_backoff(submission.attempts):
            report.skipped.append(("submission", submission.pk, "waiting for backoff"))
            continue
        if _blocking_sibling(submission.invoice_id).exists():
            report.skipped.append(("submission", submission.pk, "invoice has an accepted, pending or unknown submission"))
            continue
        if dry_run:
            report.retried.append((submission.pk, "would retry"))
            continue
        try:
            result = retry_submission(tenant=submission.tenant, submission_id=submission.pk)
        except Exception as exc:  # noqa: BLE001 - one bad submission must not stop the run
            logger.warning("FBR processor could not retry submission %s: %s", submission.pk, exc)
            report.errors.append(("submission", submission.pk, str(exc)[:300]))
            continue
        report.retried.append((submission.pk, result.status))
        _audit("fbr.submission.retried", result, f"Retried FBR submission {submission.pk}: {result.status}.")


def process_pending(*, tenant=None, limit=50, max_attempts=None, stale_minutes=None,
                    max_age_hours=UNSUBMITTED_MAX_AGE_HOURS_DEFAULT, dry_run=False, now=None):
    """Run the three steps once; returns a :class:`PendingRunReport`."""
    now = now or timezone.now()
    if max_attempts is None:
        max_attempts = _setting("FBR_AUTO_RETRY_MAX_ATTEMPTS", AUTO_RETRY_MAX_ATTEMPTS_DEFAULT)
    if stale_minutes is None:
        stale_minutes = _setting("FBR_PENDING_STALE_MINUTES", PENDING_STALE_MINUTES_DEFAULT)
    if stale_minutes < PENDING_STALE_MINUTES_MINIMUM:
        raise ValueError(
            f"stale_minutes must be at least {PENDING_STALE_MINUTES_MINIMUM}: a shorter window "
            "could mark an in-flight request as unknown."
        )
    report = PendingRunReport(dry_run=dry_run)
    common = {"tenant": tenant, "limit": limit, "dry_run": dry_run, "now": now, "report": report}
    mark_stale_pending(stale_minutes=stale_minutes, **common)
    submit_never_dispatched(max_age_hours=max_age_hours, **common)
    retry_failed(max_attempts=max_attempts, **common)
    return report


__all__ = ["PendingRunReport", "longest_call", "process_pending", "retry_backoff"]
