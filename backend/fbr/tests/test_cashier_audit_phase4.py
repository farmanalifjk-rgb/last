"""Cashier audit phase 4: fiscal robustness (E1, E2, background processing).

docs/pos-cashier-terminal-audit-2026-10-13.md, findings E1/E2/F6:
* checkout makes ONE bounded fiscalization attempt while the cashier waits;
* an HTTP 500/502/504 from the fiscal endpoint is UNKNOWN (possibly recorded),
  never re-posted in-call and never auto-retried; 429/503 stay FAILED;
* ``fbr_process_pending`` finishes what checkout could not: stale pending ->
  unknown, never-dispatched POS invoices -> submitted, failed -> retried with
  backoff. It never resends an unknown or rejected submission.
All transport is faked: nothing leaves the process.
"""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import requests
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from audit.models import AuditEvent
from fbr.client import FBRClient, FBRTransportError
from fbr.ims_client import IMSFiscalClient, IMSTransportError, interactive_budget
from fbr.models import FBRSubmission
from fbr.pending import longest_call, process_pending, retry_backoff
from fbr.services import FBRServiceError, reconcile_submission, retry_submission, submit_invoice
from fbr.transport import OUTCOME_FAILED, OUTCOME_UNKNOWN, classify_transport_outcome
from fiscal.models import FiscalInvoice
from payments.models import TenderedPayment
from pos.models import Order

from .base import FakeResponse, FakeSession, FBRTestBase
from .test_phase4_checkout_fiscalization import LOCAL_OK, LOCAL_REJECTED, CheckoutFixture


def _no_sleep(*_args):
    return None


class IMSClientTransportTests(FBRTestBase):
    def setUp(self):
        super().setUp()
        self.config = self.make_ims_config(self.tenant_b)

    def _client(self, responses):
        session = FakeSession(responses)
        return IMSFiscalClient(self.config, session=session, sleep=_no_sleep), session

    def test_server_errors_are_not_reposted_and_are_unknown(self):
        for status in (500, 502, 504):
            with self.subTest(status=status):
                client, session = self._client([FakeResponse({}, status), FakeResponse(LOCAL_OK, 200)])
                with self.assertRaises(IMSTransportError) as caught:
                    client.fiscalize({})
                self.assertEqual(len(session.calls), 1, "a possibly-recorded invoice was posted again")
                self.assertEqual(classify_transport_outcome(caught.exception), OUTCOME_UNKNOWN)

    def test_unavailable_is_retried_outside_checkout_and_failed_when_exhausted(self):
        client, session = self._client([FakeResponse({}, 503), FakeResponse(LOCAL_OK, 200)])
        self.assertTrue(client.fiscalize({}).accepted)
        self.assertEqual(len(session.calls), 2)

        client, session = self._client([FakeResponse({}, 429)] * (self.config.max_retries + 1))
        with self.assertRaises(IMSTransportError) as caught:
            client.fiscalize({})
        self.assertEqual(len(session.calls), self.config.max_retries + 1)
        self.assertEqual(classify_transport_outcome(caught.exception), OUTCOME_FAILED)

    def test_interactive_budget_is_one_bounded_attempt_and_is_scoped(self):
        self.config.timeout_seconds = 30
        self.config.max_retries = 3
        client, session = self._client([requests.exceptions.ConnectionError("refused")] * 5)
        with interactive_budget(10), self.assertRaises(IMSTransportError):
            client.fiscalize({})
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["timeout"], (5, 10))

        client, session = self._client([requests.exceptions.ConnectionError("refused")] * 5)
        with interactive_budget(3), self.assertRaises(IMSTransportError):
            client.fiscalize({})
        self.assertEqual(session.calls[0]["timeout"], (3, 3))

        # Outside the block the configured timeout and retries apply again.
        client, session = self._client([requests.exceptions.ConnectionError("refused")] * 5)
        with self.assertRaises(IMSTransportError):
            client.fiscalize({})
        self.assertEqual(len(session.calls), 4)
        self.assertEqual(session.calls[0]["timeout"], 30)


class DigitalInvoicingClientTransportTests(FBRTestBase):
    def test_invoice_post_server_error_is_unknown_and_unavailable_is_failed(self):
        for status, outcome in ((502, OUTCOME_UNKNOWN), (500, OUTCOME_UNKNOWN), (503, OUTCOME_FAILED)):
            with self.subTest(status=status):
                session = FakeSession([FakeResponse("gateway", status_code=status)])
                client = FBRClient(self.config_a, session=session, sleep=_no_sleep)
                with self.assertRaises(FBRTransportError) as caught:
                    client.post_invoice({})
                self.assertEqual(len(session.calls), 1)
                self.assertEqual(classify_transport_outcome(caught.exception), outcome)


class Phase4Fixture(CheckoutFixture):
    def _order(self, data):
        return Order.objects.get(tenant=self.tenant_b, pk=data["order"]["id"])

    def assertSaleCommitted(self, data):
        order = self._order(data)
        self.assertEqual(order.status, "paid")
        self.assertEqual(TenderedPayment.objects.filter(tenant=self.tenant_b, order=order).count(), 1)

    def _submission(self, data):
        return FBRSubmission.objects.get(tenant=self.tenant_b, invoice__order_id=data["order"]["id"], is_validate=False)


class CheckoutBudgetTests(Phase4Fixture):
    def test_component_down_is_one_short_attempt_and_the_sale_is_kept(self):
        self.ims_session.responses = [requests.exceptions.ConnectionError("refused")] * 3
        data = self.checkout(amount="118.00", key="p4-down").json()
        self.assertEqual(data["fiscal"]["status"], "failed")
        self.assertEqual(len(self.ims_session.calls), 1, "checkout must not retry while the cashier waits")
        self.assertEqual(self.ims_session.calls[0]["timeout"], (5, 10))
        self.assertSaleCommitted(data)
        self.assertIsNotNone(self._submission(data).dispatched_at)

    def test_gateway_error_at_checkout_is_unknown_and_sent_once(self):
        self.ims_session.responses = [FakeResponse({}, 502), FakeResponse(LOCAL_OK, 200)]
        data = self.checkout(amount="118.00", key="p4-502").json()
        self.assertEqual(data["fiscal"]["status"], "unknown")
        self.assertEqual(data["fiscal"]["fbr_invoice_number"], "")
        self.assertEqual(len(self.ims_session.calls), 1)
        self.assertSaleCommitted(data)

    @override_settings(FBR_POS_CHECKOUT_TIMEOUT_SECONDS=4)
    def test_budget_follows_the_setting(self):
        self.ims_session.responses = [requests.exceptions.ConnectionError("refused")] * 3
        self.checkout(amount="118.00", key="p4-budget")
        self.assertEqual(self.ims_session.calls[0]["timeout"], (4, 4))

    @override_settings(FBR_POS_CHECKOUT_TIMEOUT_SECONDS=0)
    def test_zero_restores_the_configured_attempts(self):
        attempts = self.config.max_retries + 1
        self.ims_session.responses = [requests.exceptions.ConnectionError("refused")] * attempts
        self.checkout(amount="118.00", key="p4-nobudget")
        self.assertEqual(len(self.ims_session.calls), attempts)


class ResendGuardTests(Phase4Fixture):
    def test_a_pending_submission_cannot_be_retried(self):
        self.ims_session.responses = [requests.exceptions.ConnectionError("refused")]
        submission = self._submission(self.checkout(amount="118.00", key="p4-pend").json())
        FBRSubmission.objects.filter(pk=submission.pk).update(status=FBRSubmission.STATUS_PENDING)
        with self.assertRaisesMessage(FBRServiceError, "still in progress"):
            retry_submission(tenant=self.tenant_b, submission_id=submission.pk)
        self.assertEqual(len(self.ims_session.calls), 1)

    def test_a_new_submission_after_an_unknown_outcome_needs_reconciliation(self):
        self.ims_session.responses = [requests.exceptions.ReadTimeout("slow"), FakeResponse(LOCAL_OK, 200)]
        submission = self._submission(self.checkout(amount="118.00", key="p4-unk").json())
        self.assertEqual(submission.status, FBRSubmission.STATUS_UNKNOWN)
        with self.assertRaisesMessage(FBRServiceError, "Reconcile it first"):
            submit_invoice(tenant=self.tenant_b, invoice_id=submission.invoice_id)
        self.assertEqual(len(self.ims_session.calls), 1)
        self.assertEqual(FBRSubmission.objects.filter(invoice_id=submission.invoice_id).count(), 1)


@override_settings(FBR_AUTO_RETRY_MAX_ATTEMPTS=5, FBR_PENDING_STALE_MINUTES=10)
class ProcessPendingTests(Phase4Fixture):
    def _failed_sale(self, key):
        self.ims_session.responses = [requests.exceptions.ConnectionError("refused")]
        data = self.checkout(amount="118.00", key=key).json()
        self.assertEqual(data["fiscal"]["status"], "failed")
        return self._submission(data)

    def test_failed_sale_is_retried_after_backoff_and_becomes_accepted(self):
        submission = self._failed_sale("pp-retry")
        self.ims_session.responses = [FakeResponse(LOCAL_OK, 200)]
        now = timezone.now()

        report = process_pending(now=now)
        self.assertEqual(report.retried, [])
        self.assertIn(("submission", submission.pk, "waiting for backoff"), report.skipped)
        self.assertEqual(len(self.ims_session.calls), 1)

        report = process_pending(now=now + retry_backoff(1) + timedelta(seconds=1))
        self.assertEqual(report.retried, [(submission.pk, FBRSubmission.STATUS_ACCEPTED)])
        submission.refresh_from_db()
        self.assertEqual((submission.status, submission.attempts), (FBRSubmission.STATUS_ACCEPTED, 2))
        self.assertEqual(submission.invoice.fbr_invoice_number, LOCAL_OK["InvoiceNumber"])
        self.assertEqual(FBRSubmission.objects.filter(invoice_id=submission.invoice_id).count(), 1)
        event = AuditEvent.objects.get(action="fbr.submission.retried", entity_id=str(submission.pk))
        self.assertEqual((event.tenant_id, event.actor_id), (self.tenant_b.id, None))
        self.assertEqual(event.after["status"], FBRSubmission.STATUS_ACCEPTED)

        # Nothing left to do: accepted is never touched again.
        later = process_pending(now=now + timedelta(hours=2))
        self.assertEqual((later.retried, later.submitted), ([], []))
        self.assertEqual(len(self.ims_session.calls), 2)

    def test_unknown_and_rejected_are_never_resent(self):
        self.ims_session.responses = [requests.exceptions.ReadTimeout("slow")]
        unknown = self._submission(self.checkout(amount="118.00", key="pp-unk").json())
        self.ims_session.responses = [FakeResponse(LOCAL_REJECTED, 200)]
        rejected = self._submission(self.checkout(amount="118.00", key="pp-rej").json())
        self.ims_session.responses = [FakeResponse(LOCAL_OK, 200)] * 4
        calls = len(self.ims_session.calls)

        report = process_pending(now=timezone.now() + timedelta(days=1))
        self.assertEqual((report.retried, report.submitted), ([], []))
        self.assertEqual(len(self.ims_session.calls), calls)
        unknown.refresh_from_db()
        rejected.refresh_from_db()
        self.assertEqual(unknown.status, FBRSubmission.STATUS_UNKNOWN)
        self.assertEqual(rejected.status, FBRSubmission.STATUS_REJECTED)

    def test_reconciled_as_not_fiscalized_is_then_retried(self):
        self.ims_session.responses = [requests.exceptions.ReadTimeout("slow")]
        submission = self._submission(self.checkout(amount="118.00", key="pp-rec").json())
        reconcile_submission(tenant=self.tenant_b, submission_id=submission.pk, outcome="not_fiscalized")
        self.ims_session.responses = [FakeResponse(LOCAL_OK, 200)]
        report = process_pending(now=timezone.now() + timedelta(hours=1))
        self.assertEqual(report.retried, [(submission.pk, FBRSubmission.STATUS_ACCEPTED)])

    def test_attempt_limit_and_inactive_configuration_stop_automatic_retries(self):
        submission = self._failed_sale("pp-limit")
        later = timezone.now() + timedelta(days=1)
        FBRSubmission.objects.filter(pk=submission.pk).update(attempts=5)
        self.assertEqual(process_pending(now=later).retried, [])

        FBRSubmission.objects.filter(pk=submission.pk).update(attempts=1)
        self.config.is_active = False
        self.config.save(update_fields=["is_active"])
        self.assertEqual(process_pending(now=later).retried, [])
        self.assertEqual(len(self.ims_session.calls), 1)

    def test_stale_pending_becomes_unknown_and_is_never_resent(self):
        submission = self._failed_sale("pp-stale")
        now = timezone.now()
        FBRSubmission.objects.filter(pk=submission.pk).update(
            status=FBRSubmission.STATUS_PENDING, dispatched_at=now - timedelta(minutes=3),
        )
        report = process_pending(now=now)
        self.assertEqual(report.marked_unknown, [])  # may still be in flight

        report = process_pending(now=now + timedelta(minutes=8))
        self.assertEqual(report.marked_unknown, [submission.pk])
        submission.refresh_from_db()
        self.assertEqual(submission.status, FBRSubmission.STATUS_UNKNOWN)
        self.assertIn("Reconcile", submission.error_message)
        self.assertTrue(AuditEvent.objects.filter(
            tenant=self.tenant_b, action="fbr.submission.marked_unknown", entity_id=str(submission.pk)).exists())
        self.assertEqual(process_pending(now=now + timedelta(days=1)).retried, [])
        self.assertEqual(len(self.ims_session.calls), 1)

    def test_stale_window_never_shorter_than_the_longest_configured_call(self):
        self.config.timeout_seconds = 300
        self.config.max_retries = 2
        self.config.save(update_fields=["timeout_seconds", "max_retries"])
        self.assertGreater(longest_call(self.config), timedelta(minutes=10))
        submission = self._failed_sale("pp-long")
        now = timezone.now()
        FBRSubmission.objects.filter(pk=submission.pk).update(
            status=FBRSubmission.STATUS_PENDING, dispatched_at=now - timedelta(minutes=15),
        )
        report = process_pending(now=now)
        self.assertEqual(report.marked_unknown, [])
        self.assertIn(("submission", submission.pk, "may still be in flight"), report.skipped)

    def test_never_dispatched_pos_invoice_is_submitted_once_after_the_grace_period(self):
        with patch("fbr.services.submit_invoice", side_effect=RuntimeError("worker died")):
            data = self.checkout(amount="118.00", key="pp-never").json()
        invoice = FiscalInvoice.objects.get(tenant=self.tenant_b, order_id=data["order"]["id"])
        self.assertFalse(invoice.fbr_submissions.exists())
        self.assertEqual(self.ims_session.calls, [])

        self.assertEqual(process_pending().submitted, [])  # the till may still be submitting it

        report = process_pending(now=timezone.now() + timedelta(minutes=5))
        self.assertEqual(report.submitted, [(invoice.pk, FBRSubmission.STATUS_ACCEPTED)])
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant_b, action="fbr.invoice.submitted").exists())
        self.assertEqual(process_pending(now=timezone.now() + timedelta(minutes=10)).submitted, [])
        self.assertEqual(len(self.ims_session.calls), 1)

    def test_runs_are_tenant_scoped_and_dry_run_changes_nothing(self):
        submission = self._failed_sale("pp-scope")
        self.ims_session.responses = [FakeResponse(LOCAL_OK, 200)]
        later = timezone.now() + timedelta(hours=1)

        self.assertEqual(process_pending(tenant=self.tenant_a, now=later).retried, [])
        dry = process_pending(now=later, dry_run=True)
        self.assertEqual(dry.retried, [(submission.pk, "would retry")])
        self.assertFalse(AuditEvent.objects.filter(action="fbr.submission.retried").exists())
        submission.refresh_from_db()
        self.assertEqual((submission.status, submission.attempts), (FBRSubmission.STATUS_FAILED, 1))
        self.assertEqual(len(self.ims_session.calls), 1)

        self.assertEqual(process_pending(tenant=self.tenant_b, now=later).retried,
                         [(submission.pk, FBRSubmission.STATUS_ACCEPTED)])

    def test_command_reports_and_validates_options(self):
        submission = self._failed_sale("pp-cmd")
        out = StringIO()
        call_command("fbr_process_pending", "--dry-run", "--tenant", self.tenant_b.slug, stdout=out)
        self.assertIn("[dry run]", out.getvalue())
        self.assertIn("errors=0", out.getvalue())
        submission.refresh_from_db()
        self.assertEqual(submission.status, FBRSubmission.STATUS_FAILED)
        self.assertNotIn("test-token", out.getvalue())
        with self.assertRaises(CommandError):
            call_command("fbr_process_pending", "--tenant", "no-such-shop", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("fbr_process_pending", "--stale-minutes", "1", stdout=StringIO())
