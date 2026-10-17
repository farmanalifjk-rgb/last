"""Submission orchestration: persistence, idempotency, retry and tenant scope — v1.12."""
import requests

from fbr.client import FBRClient
from fbr.models import FBRSubmission
from fbr.services import FBRServiceError, retry_submission, submit_invoice, validate_invoice
from fiscal.models import FiscalDevice, FiscalInvoice, FiscalSubmission
from fiscal.services import FiscalServiceError, submit_to_device

from .base import FakeResponse, FakeSession, FBRTestBase

ACCEPTED_V112 = {
    "invoiceNumber": "3310227771151DI1700000000123",
    "dated": "2025-04-21",
    "validationResponse": {
        "statusCode": "00",
        "errorCode": "",
        "error": "Valid",
        "invoiceStatuses": [{"itemSNo": "1", "statusCode": "00", "status": "Valid", "errorCode": "", "error": ""}],
    }
}
REJECTED_V112 = {
    "invoiceNumber": "",
    "dated": "2025-04-21",
    "validationResponse": {
        "statusCode": "01",
        "errorCode": "0001",
        "error": "Invalid buyer NTN",
        "invoiceStatuses": [{"itemSNo": "1", "statusCode": "01", "errorCode": "0402", "error": "buyerNTNCNIC is invalid"}],
    }
}


class SubmissionTests(FBRTestBase):
    def _client(self, *bodies):
        session = FakeSession([
            body if isinstance(body, Exception) else FakeResponse(body) for body in bodies
        ])
        self.session = session
        return FBRClient(self.config_a, session=session, sleep=lambda _: None)

    def test_accepted_submission_stores_the_tracking_number_on_the_invoice(self):
        submission = submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=self._client(ACCEPTED_V112)
        )
        self.assertEqual(submission.status, FBRSubmission.STATUS_ACCEPTED)
        self.assertEqual(submission.fbr_invoice_number, ACCEPTED_V112["invoiceNumber"])
        self.assertEqual(submission.status_code, "00")
        self.assertEqual(submission.response_timestamp, "2025-04-21")
        self.assertEqual(submission.request_payload["sellerProvince"], "Sindh")
        self.assertEqual(submission.request_payload["sellerNTNCNIC"], "1234567")

        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, ACCEPTED_V112["invoiceNumber"])
        self.assertIn(ACCEPTED_V112["invoiceNumber"], self._decoded_qr(self.invoice_a))

    def _decoded_qr(self, invoice):
        import base64
        return base64.b64decode(invoice.qr_payload).decode()

    def test_rejected_submission_keeps_the_error_detail_and_leaves_the_invoice_untracked(self):
        submission = submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=self._client(REJECTED_V112)
        )
        self.assertEqual(submission.status, FBRSubmission.STATUS_REJECTED)
        self.assertEqual(submission.status_code, "01")
        self.assertEqual(submission.error_code, "0001")
        self.assertTrue(any("Invalid buyer NTN" in e for e in submission.errors))
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "")

    def test_validate_does_not_update_invoice_and_is_flagged(self):
        submission = validate_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=self._client(ACCEPTED_V112)
        )
        self.assertEqual(submission.status, FBRSubmission.STATUS_ACCEPTED)
        self.assertTrue(submission.is_validate)
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "")

    def test_unreachable_api_marks_the_submission_failed(self):
        submission = submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id,
            client=self._client(*[requests.ConnectionError("boom")] * 3),
        )
        self.assertEqual(submission.status, FBRSubmission.STATUS_FAILED)
        self.assertIn("Could not reach FBR", submission.error_message)

    def test_an_accepted_invoice_is_never_posted_twice(self):
        first = submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=self._client(ACCEPTED_V112)
        )
        second = submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=self._client(ACCEPTED_V112)
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.session.calls), 0)
        self.assertEqual(FBRSubmission.objects.filter(is_validate=False).count(), 1)

    def test_a_rejected_submission_can_be_retried(self):
        rejected = submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=self._client(REJECTED_V112)
        )
        retried = retry_submission(
            tenant=self.tenant_a, submission_id=rejected.id, client=self._client(ACCEPTED_V112)
        )
        self.assertEqual(retried.id, rejected.id)
        self.assertEqual(retried.status, FBRSubmission.STATUS_ACCEPTED)
        self.assertEqual(retried.attempts, 2)

    def test_accepted_submissions_cannot_be_retried(self):
        accepted = submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=self._client(ACCEPTED_V112)
        )
        with self.assertRaises(FBRServiceError):
            retry_submission(tenant=self.tenant_a, submission_id=accepted.id)

    def test_only_issued_invoices_are_posted(self):
        FiscalInvoice.objects.filter(pk=self.invoice_a.pk).update(status=FiscalInvoice.STATUS_CANCELLED)
        with self.assertRaises(FBRServiceError):
            submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id)

    def test_a_tenant_without_configuration_cannot_post(self):
        invoice_b = self.make_invoice(self.tenant_b, "b")
        with self.assertRaises(FBRServiceError):
            submit_invoice(tenant=self.tenant_b, invoice_id=invoice_b.id)


class TenantIsolationTests(FBRTestBase):
    def test_cannot_submit_another_tenants_invoice(self):
        with self.assertRaises(FBRServiceError):
            submit_invoice(tenant=self.tenant_b, invoice_id=self.invoice_a.id)

    def test_cannot_retry_another_tenants_submission(self):
        submission = submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id,
            client=FBRClient(self.config_a, session=FakeSession([FakeResponse(REJECTED_V112)])),
        )
        with self.assertRaises(FBRServiceError):
            retry_submission(tenant=self.tenant_b, submission_id=submission.id)


class FiscalDeviceRoutingTests(FBRTestBase):
    def test_fbr_device_routes_the_submission_to_fbr(self):
        device = FiscalDevice.objects.create(
            tenant=self.tenant_a, name="FBR", kind=FiscalDevice.KIND_API,
            provider=FiscalDevice.PROVIDER_FBR,
        )
        client = FBRClient(self.config_a, session=FakeSession([FakeResponse(ACCEPTED_V112)]))
        submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=client)
        submission = submit_to_device(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, device_id=device.id, user=self.user_a
        )
        self.assertEqual(submission.status, FiscalSubmission.STATUS_ACCEPTED)
        self.assertEqual(submission.reference, ACCEPTED_V112["invoiceNumber"])

    def test_fbr_device_does_not_mirror_an_accepted_invoice_twice(self):
        device = FiscalDevice.objects.create(
            tenant=self.tenant_a, name="FBR", kind=FiscalDevice.KIND_API,
            provider=FiscalDevice.PROVIDER_FBR,
        )
        submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id,
            client=FBRClient(self.config_a, session=FakeSession([FakeResponse(ACCEPTED_V112)])),
        )
        first = submit_to_device(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, device_id=device.id, user=self.user_a
        )
        second = submit_to_device(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, device_id=device.id, user=self.user_a
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(FiscalSubmission.objects.filter(invoice=self.invoice_a).count(), 1)

    def test_stub_device_still_uses_the_local_stub(self):
        device = FiscalDevice.objects.create(tenant=self.tenant_a, name="Legacy", kind=FiscalDevice.KIND_API)
        submission = submit_to_device(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id, device_id=device.id, user=self.user_a
        )
        self.assertTrue(submission.reference.startswith("STUB-"))

    def test_fbr_device_without_configuration_reports_a_fiscal_error(self):
        invoice_b = self.make_invoice(self.tenant_b, "b")
        device = FiscalDevice.objects.create(
            tenant=self.tenant_b, name="FBR", kind=FiscalDevice.KIND_API,
            provider=FiscalDevice.PROVIDER_FBR,
        )
        with self.assertRaises(FiscalServiceError):
            submit_to_device(
                tenant=self.tenant_b, invoice_id=invoice_b.id, device_id=device.id, user=self.user_b
            )
