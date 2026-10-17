"""Fiscalize a completed POS sale through the tenant's local FBR IMS component.

FBR's retail model pushes each sale to the Software Fiscal Component "on the
event of print" and prints the fiscal number it returns. This module does that
right after checkout commits:

* the sale (order, payments, stock) is already committed and is NEVER rolled
  back or modified here; every fiscal failure becomes an honest status;
* one fiscal invoice per order (order row lock) and no automatic re-submission
  - retries/reconciliation stay explicit (``/api/fbr/submissions/<id>/...``);
* only the IMS track is fiscalized from the till. Digital Invoicing is FBR's
  invoice register for B2B sellers and is submitted from fiscal invoices.

``pos_fiscal_status`` is the single, database-derived description used by the
receipt: official FBR numbers are reserved for genuine acceptance. A simulated
number and its QR are shown only in a prominent TEST / SIMULATED block.
"""
import base64
import logging

from django.db import transaction

from .models import FiscalInvoice, InvoiceSequence

logger = logging.getLogger(__name__)

STATUS_NOT_CONFIGURED = "not_configured"   # tenant has no active FBR configuration
STATUS_NOT_FISCALIZED = "not_fiscalized"   # configured, but no fiscal invoice exists
STATUS_NOT_SUBMITTED = "not_submitted"     # fiscal invoice issued, never sent
STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_SIMULATED = "simulated"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"
STATUS_UNKNOWN = "unknown"


def _active_configuration(tenant):
    from fbr.services import FBRServiceError, get_configuration

    try:
        return get_configuration(tenant)
    except FBRServiceError:
        return None


def till_fiscalization_configured(tenant):
    """True when the tenant's till is an FBR-integrated PoS.

    That is an active configuration on the IMS track - the only track
    fiscalize_pos_order submits from the till (Digital Invoicing is not).
    """
    from fbr.constants import INTEGRATION_MODE_IMS

    config = _active_configuration(tenant)
    return config is not None and config.integration_mode == INTEGRATION_MODE_IMS


def _order_invoice(order):
    return (
        FiscalInvoice.objects.filter(tenant=order.tenant, order=order, sequence__document_type=InvoiceSequence.TYPE_INVOICE)
        .exclude(status__in=[FiscalInvoice.STATUS_CANCELLED, FiscalInvoice.STATUS_VOID])
        .order_by("id")
        .first()
    )


def _latest_submission(invoice):
    from fbr.models import FBRSubmission

    accepted = FBRSubmission.objects.filter(
        invoice=invoice, status=FBRSubmission.STATUS_ACCEPTED, is_validate=False,
    ).order_by("-id").first()
    return accepted or FBRSubmission.objects.filter(invoice=invoice, is_validate=False).order_by("-id").first()


def pos_fiscal_status(order, *, message=""):
    """Describe the order's fiscal state for the cashier and the receipt."""
    from fbr.models import FBRSubmission

    invoice = _order_invoice(order)
    if invoice is None:
        configured = _active_configuration(order.tenant) is not None
        return {
            "status": STATUS_NOT_FISCALIZED if configured else STATUS_NOT_CONFIGURED,
            "message": message,
        }
    block = {
        "status": STATUS_NOT_SUBMITTED,
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "submission_id": None,
        "fbr_invoice_number": "",
        "simulated_invoice_number": "",
        "qr_png_base64": "",
        "is_simulated": False,
        "receipt_label": "",
        "message": message,
    }
    submission = _latest_submission(invoice)
    if submission is None:
        return block
    block["submission_id"] = submission.id
    block["is_simulated"] = submission.is_simulated
    if submission.status == FBRSubmission.STATUS_ACCEPTED:
        if submission.is_simulated:
            block["status"] = STATUS_SIMULATED
            block["simulated_invoice_number"] = submission.fbr_invoice_number
            block["receipt_label"] = "TEST / SIMULATED — NOT AN FBR INVOICE"
            block["message"] = "TEST / SIMULATED invoice; not issued by FBR."
            if submission.fbr_invoice_number:
                from fbr.qr import render_qr_png

                block["qr_png_base64"] = base64.b64encode(
                    render_qr_png(submission.fbr_invoice_number, quiet_zone=0)
                ).decode("ascii")
        elif invoice.fbr_invoice_number and invoice.fbr_invoice_number == submission.fbr_invoice_number:
            from fbr.qr import render_qr_png

            block["status"] = STATUS_ACCEPTED
            block["fbr_invoice_number"] = invoice.fbr_invoice_number
            # QR of the FBR-issued fiscal number (FBR retail model).
            # Bare symbol: the receipt prints it at 7x7 mm (S.R.O. 1006) and
            # adds the quiet zone as a white margin.
            block["qr_png_base64"] = base64.b64encode(
                render_qr_png(invoice.fbr_invoice_number, quiet_zone=0)
            ).decode("ascii")
        else:
            # Accepted submission not (yet) reflected on the invoice: do not
            # print a number the invoice itself does not carry.
            block["status"] = STATUS_PENDING
    else:
        block["status"] = {
            FBRSubmission.STATUS_PENDING: STATUS_PENDING,
            FBRSubmission.STATUS_REJECTED: STATUS_REJECTED,
            FBRSubmission.STATUS_FAILED: STATUS_FAILED,
            FBRSubmission.STATUS_UNKNOWN: STATUS_UNKNOWN,
        }.get(submission.status, STATUS_PENDING)
        if not message and submission.status in (FBRSubmission.STATUS_REJECTED, FBRSubmission.STATUS_FAILED):
            block["message"] = submission.error_message[:300]
    return block


def _invoice_sequence(tenant):
    """The tenant's oldest active invoice sequence (sequences are tenant data)."""
    return (
        InvoiceSequence.objects.filter(tenant=tenant, is_active=True, document_type=InvoiceSequence.TYPE_INVOICE)
        .order_by("id")
        .first()
    )


CHECKOUT_FISCALIZATION_BUDGET_DEFAULT = 10


def checkout_fiscalization_budget_seconds():
    """Seconds a checkout may wait for the fiscal component (one attempt).

    Setting ``FBR_POS_CHECKOUT_TIMEOUT_SECONDS`` (default 10). ``0`` restores
    the configuration's own timeout and retry count (not recommended at a till).
    """
    from django.conf import settings

    value = getattr(settings, "FBR_POS_CHECKOUT_TIMEOUT_SECONDS", CHECKOUT_FISCALIZATION_BUDGET_DEFAULT)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return CHECKOUT_FISCALIZATION_BUDGET_DEFAULT
    return value if value > 0 else None


def fiscalize_pos_order(*, tenant, order, user=None):
    """Issue and submit the fiscal invoice for a completed sale. Never raises."""
    from fbr.constants import INTEGRATION_MODE_IMS
    from fbr.payload import FBRValidationError
    from fbr.ims_client import interactive_budget
    from fbr.services import FBRServiceError, submit_invoice
    from pos.models import Order

    from .services import FiscalServiceError, issue_invoice

    try:
        config = _active_configuration(tenant)
        if config is None:
            return pos_fiscal_status(order)
        if config.integration_mode != INTEGRATION_MODE_IMS:
            return pos_fiscal_status(order, message=(
                "This tenant uses FBR Digital Invoicing; submit the sale from Fiscal invoices."
            ))

        with transaction.atomic():
            # Serialize concurrent checkouts/replays of the same order so it
            # can never receive two fiscal invoices.
            locked = Order.objects.select_for_update().get(pk=order.pk, tenant=tenant)
            invoice = _order_invoice(locked)
            if invoice is None:
                sequence = _invoice_sequence(tenant)
                if sequence is None:
                    return pos_fiscal_status(order, message=(
                        "No active invoice sequence is configured, so the sale was not sent to FBR."
                    ))
                invoice = issue_invoice(tenant=tenant, order_id=locked.id, sequence_id=sequence.id, user=user)

        if _latest_submission(invoice) is not None:
            # Already attempted (e.g. a replayed checkout): report, never resend.
            return pos_fiscal_status(order)
        # The cashier is waiting: one bounded attempt (cashier audit E1).
        # Anything unfinished is left FAILED (fbr_process_pending retries it)
        # or UNKNOWN (reconcile first); the sale itself is already saved.
        with interactive_budget(checkout_fiscalization_budget_seconds()):
            submit_invoice(tenant=tenant, invoice_id=invoice.id, user=user)
        return pos_fiscal_status(order)
    except (FiscalServiceError, FBRValidationError, FBRServiceError) as exc:
        return pos_fiscal_status(order, message=f"Not sent to FBR: {exc}"[:500])
    except Exception:  # noqa: BLE001 - the completed sale must never fail here
        logger.exception("POS fiscalization failed for order %s", order.pk)
        return pos_fiscal_status(order, message="Fiscalization could not be completed; the sale is saved.")


__all__ = ["fiscalize_pos_order", "pos_fiscal_status"]
