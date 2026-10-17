"""Service/API tests for the Tier-1 IMS fiscalization track."""
from unittest.mock import patch

from django.test import override_settings

import base64

from fbr.ims_client import IMSResponse, IMSTransportError
from fbr.models import FBRConfiguration, FBRSubmission, FBRTenantEligibility
from fbr.services import submit_invoice

from .base import FBRTestBase

FISCAL_OK = IMSResponse(
    invoice_number="9000052011142444901", code="100",
    message="Fiscal Invoice Number generated successfully.", raw={"Code": "100"},
)


class FakeIMSClient:
    def __init__(self, response=None):
        self.response = response or FISCAL_OK

    def fiscalize(self, payload):
        return self.response


@override_settings(ROOT_URLCONF="backend.urls")
class IMSSubmitTests(FBRTestBase):
    def setUp(self):
        super().setUp()
        self.config = self.make_ims_config(self.tenant_a)

    def _submit(self, client):
        return submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=client)

    def test_submit_routes_to_ims_and_fiscalizes(self):
        submission = self._submit(FakeIMSClient())
        self.assertEqual(submission.status, FBRSubmission.STATUS_ACCEPTED)
        self.assertEqual(submission.ims_code, "100")
        self.assertEqual(submission.fbr_invoice_number, "9000052011142444901")
        self.assertEqual(submission.usin, submission.request_payload["USIN"])
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "9000052011142444901")
        self.assertTrue(self.invoice_a.qr_payload)  # printed on the receipt with the QR

    def test_submit_is_idempotent(self):
        first = self._submit(FakeIMSClient())

        class _Exploding(FakeIMSClient):
            def fiscalize(self, payload):
                raise AssertionError("a fiscalized invoice must never be posted twice")

        second = self._submit(_Exploding())
        self.assertEqual(first.pk, second.pk)

    def test_rejection_records_code_and_errors(self):
        rejected = IMSResponse(
            invoice_number="", code="101", message="Invalid POSID",
            errors=["POSID not registered"], raw={"Code": "101"},
        )
        submission = self._submit(FakeIMSClient(rejected))
        self.assertEqual(submission.status, FBRSubmission.STATUS_REJECTED)
        self.assertEqual(submission.ims_code, "101")
        self.assertIn("POSID not registered", submission.error_message)
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "")

    def test_transport_failure_marks_failed(self):
        class _Down:
            def fiscalize(self, payload):
                from fbr.ims_client import IMSTransportError

                raise IMSTransportError("Could not reach the IMS endpoint")

        submission = self._submit(_Down())
        self.assertEqual(submission.status, FBRSubmission.STATUS_FAILED)
        self.assertIn("Could not reach", submission.error_message)

    def test_credit_note_without_ref_usin_is_rejected_locally(self):
        from fbr.payload import FBRValidationError

        with self.assertRaises(FBRValidationError):
            submit_invoice(
                tenant=self.tenant_a, invoice_id=self.invoice_a.id,
                invoice_type=4, client=FakeIMSClient(),
            )

    def test_di_configuration_untouched_by_ims_defaults(self):
        config = self.make_config(self.tenant_b)
        self.assertEqual(config.integration_mode, "di")
        self.assertIsNone(config.pos_registration_number)
        self.assertFalse(config.ims_use_cloud)


@override_settings(ROOT_URLCONF="backend.urls")
class IMSAPITests(FBRTestBase):
    def setUp(self):
        super().setUp()
        self.config = self.make_ims_config(self.tenant_a)

    def test_preview_mode_ims_returns_document(self):
        client = self.api_client(self.user_a)
        response = client.get(f"/api/fbr/invoices/{self.invoice_a.id}/preview/?mode=ims")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["POSID"], 110014)
        self.assertEqual(body["InvoiceNumber"], "")
        self.assertIn("TotalBillAmount", body)

    def test_preview_rejects_other_tenants_invoice(self):
        client = self.api_client(self.user_b)
        response = client.get(f"/api/fbr/invoices/{self.invoice_a.id}/preview/?mode=ims")
        self.assertIn(response.status_code, (400, 403, 404))

    def test_configuration_serializer_accepts_ims_fields(self):
        from fbr.models import FBRTenantEligibility

        FBRTenantEligibility.objects.create(tenant=self.tenant_b, allowed_modes="di,ims")
        client = self.api_client(self.user_b)  # tenant B has no configuration yet
        payload = {
            "environment": "sandbox",
            "integration_mode": "ims",
            "pos_registration_number": 110099,
            "ims_local_base_url": "http://localhost:8524",
            "seller_ntn_cnic": "1234567",
            "seller_business_name": "IMS Seller",
            "seller_address": "Karachi",
        }
        response = client.post("/api/fbr/configurations/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["integration_mode"], "ims")
        self.assertEqual(response.json()["pos_registration_number"], 110099)

    def test_duplicate_configuration_environment_returns_400_not_500(self):
        client = self.api_client(self.user_a)  # config_a already covers sandbox
        payload = {
            "environment": "sandbox",
            "integration_mode": "di",
            "security_token": "another-token",
            "seller_ntn_cnic": "1234567",
            "seller_business_name": "Dup",
            "seller_address": "Karachi",
        }
        response = client.post("/api/fbr/configurations/", payload, format="json")
        self.assertEqual(response.status_code, 400, response.content)

    def test_configuration_requires_posid_for_ims(self):
        client = self.api_client(self.user_a)
        payload = {
            "environment": "sandbox",
            "integration_mode": "ims",
            "seller_ntn_cnic": "1234567",
            "seller_business_name": "IMS Seller",
            "seller_address": "Karachi",
        }
        response = client.post("/api/fbr/configurations/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("pos_registration_number", str(response.content))

    def test_ims_health_endpoint(self):
        client = self.api_client(self.user_a)
        with patch("fbr.views.ims_health") as probe:
            probe.return_value = {"status": "responding", "url": "http://localhost:8524/api/IMSFiscal/get"}
            response = client.get("/api/fbr/ims/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "responding")

def _transport_error(cause):
    """An IMSTransportError carrying a real requests cause for classification."""
    exc = IMSTransportError("transport down")
    exc.__cause__ = cause
    return exc


class HardeningRegressionTests(FBRTestBase):
    """Regression tests for the production-hardening audit fixes H1/H2/H5/H9/H10."""

    def setUp(self):
        super().setUp()
        self.config = self.make_ims_config(self.tenant_a)

    def _submit(self, client):
        return submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=client)

    # -- H1: concurrent duplicate fiscalization ---------------------------
    def test_pending_submission_blocks_a_second_external_call(self):
        FBRSubmission.objects.create(
            tenant=self.tenant_a, invoice=self.invoice_a, configuration=self.config,
            environment="sandbox", integration_mode="ims", status=FBRSubmission.STATUS_PENDING,
            request_payload={}, attempts=1,
        )

        class _Exploding(FakeIMSClient):
            def fiscalize(self, payload):
                raise AssertionError("must not post while another submission is in flight")

        from fbr.services import FBRServiceError

        with self.assertRaises(FBRServiceError) as ctx:
            self._submit(_Exploding())
        self.assertIn("already in progress", str(ctx.exception))

    def test_two_pending_submissions_are_impossible_at_the_db_level(self):
        from django.db import IntegrityError

        FBRSubmission.objects.create(
            tenant=self.tenant_a, invoice=self.invoice_a, configuration=self.config,
            environment="sandbox", integration_mode="ims", status=FBRSubmission.STATUS_PENDING,
            request_payload={}, attempts=1,
        )
        with self.assertRaises(IntegrityError):
            FBRSubmission.objects.create(
                tenant=self.tenant_a, invoice=self.invoice_a, configuration=self.config,
                environment="sandbox", integration_mode="ims", status=FBRSubmission.STATUS_PENDING,
                request_payload={}, attempts=1,
            )

    # -- H9: timeout -> unknown -> reconcile -------------------------------
    def test_read_timeout_marks_unknown_and_blocks_retry(self):
        import requests

        submission = self._submit(FakeTimeoutClient())
        self.assertEqual(submission.status, FBRSubmission.STATUS_UNKNOWN)
        from fbr.services import FBRServiceError, retry_submission

        with self.assertRaises(FBRServiceError) as ctx:
            retry_submission(tenant=self.tenant_a, submission_id=submission.pk, client=FakeIMSClient())
        self.assertIn("reconcile", str(ctx.exception))
        self.assertIn(submission.usin, str(ctx.exception))

    def test_reconcile_not_fiscalized_then_retry_succeeds(self):
        import requests

        submission = self._submit(FakeTimeoutClient())
        from fbr.services import retry_submission, reconcile_submission

        reconciled = reconcile_submission(
            tenant=self.tenant_a, submission_id=submission.pk, outcome="not_fiscalized",
        )
        self.assertEqual(reconciled.status, FBRSubmission.STATUS_FAILED)
        retried = retry_submission(tenant=self.tenant_a, submission_id=submission.pk, client=FakeIMSClient())
        self.assertEqual(retried.status, FBRSubmission.STATUS_ACCEPTED)

    def test_reconcile_fiscalized_requires_the_fiscal_number_and_updates_receipt(self):
        import requests

        submission = self._submit(FakeTimeoutClient())
        from fbr.services import FBRServiceError, reconcile_submission

        with self.assertRaises(FBRServiceError):
            reconcile_submission(
                tenant=self.tenant_a, submission_id=submission.pk, outcome="fiscalized",
            )
        reconciled = reconcile_submission(
            tenant=self.tenant_a, submission_id=submission.pk, outcome="fiscalized",
            fiscal_invoice_number="9000052011142444901",
        )
        self.assertEqual(reconciled.status, FBRSubmission.STATUS_ACCEPTED)
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "9000052011142444901")
        self.assertTrue(self.invoice_a.qr_payload)

    def test_connect_timeout_marks_failed_and_allows_direct_retry(self):
        import requests

        submission = self._submit(FakeConnectTimeoutClient())
        self.assertEqual(submission.status, FBRSubmission.STATUS_FAILED)
        from fbr.services import retry_submission

        retried = retry_submission(tenant=self.tenant_a, submission_id=submission.pk, client=FakeIMSClient())
        self.assertEqual(retried.status, FBRSubmission.STATUS_ACCEPTED)

    # -- H2: frozen integration mode ---------------------------------------
    def test_retry_uses_frozen_mode_even_after_configuration_flip(self):
        from fbr.client import FBRResponse
        from fbr.services import retry_submission

        class FakeDIClient:
            """Replies with the queued FBR responses and records the payloads."""

            def __init__(self, *responses):
                self.responses = list(responses)
                self.payloads = []

            def post_invoice(self, payload):
                self.payloads.append(payload)
                return self.responses.pop(0)

        # A tenant on the DI track (tenant_b default config) submits a sale
        # that PRAL rejects — a retryable attempt.
        invoice_b = self.make_invoice(self.tenant_b, "b")
        di_config = self.make_config(self.tenant_b)  # tenant B defaults to the DI track
        self.assertEqual(di_config.integration_mode, "di")
        submission = submit_invoice(
            tenant=self.tenant_b, invoice_id=invoice_b.id,
            client=FakeDIClient(FBRResponse(invoice_number="", status_code="01", error_message="Invalid")),
        )
        self.assertEqual(submission.integration_mode, "di")
        self.assertEqual(submission.status, FBRSubmission.STATUS_REJECTED)
        # The tenant (and its config) flip to IMS after the DI attempt.
        FBRTenantEligibility.objects.create(tenant=self.tenant_b, allowed_modes="di,ims")
        di_config.integration_mode = "ims"
        di_config.pos_registration_number = 110014
        di_config.save()

        retry_client = FakeDIClient(FBRResponse(invoice_number="7000001", status_code="00", dated="2026-09-05"))
        retried = retry_submission(
            tenant=self.tenant_b, submission_id=submission.pk,
            client=retry_client,  # a DI submission retries over the DI transport
        )
        self.assertEqual(retried.integration_mode, "di")
        # The rebuilt payload is still a DI document, not an IMS one.
        self.assertIn("sellerNTNCNIC", retried.request_payload)
        self.assertNotIn("POSID", retried.request_payload)

    def test_validate_is_blocked_for_ims_tenants(self):
        from fbr.services import FBRServiceError, validate_invoice

        with self.assertRaises(FBRServiceError) as ctx:
            validate_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id)
        self.assertIn("DI", str(ctx.exception))

    def test_di_preview_is_blocked_for_ims_mode(self):
        client = self.api_client(self.user_a)
        response = client.get(f"/api/fbr/invoices/{self.invoice_a.id}/preview/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("IMS", str(response.content))

    # -- H5: purchases are never fiscalized --------------------------------
    def test_purchase_invoice_rejected_without_external_call(self):
        from fbr.services import FBRServiceError

        class _Exploding(FakeIMSClient):
            def fiscalize(self, payload):
                raise AssertionError("purchases must never be fiscalized")

        with self.assertRaises(FBRServiceError) as ctx:
            submit_invoice(
                tenant=self.tenant_a, invoice_id=self.invoice_a.id,
                invoice_type=1, client=_Exploding(),
            )
        self.assertIn("not fiscalized", str(ctx.exception))
        self.assertFalse(FBRSubmission.objects.filter(invoice=self.invoice_a, is_validate=False).exists())

    # -- H10: acceptance is always reflected on the receipt ----------------
    def test_early_return_self_heals_missing_receipt_number(self):
        submission = self._submit(FakeIMSClient())
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "9000052011142444901")
        # Simulate a historical partial failure: invoice row lost the number.
        self.invoice_a.fbr_invoice_number = ""
        self.invoice_a.save(update_fields=["fbr_invoice_number"])

        class _Exploding(FakeIMSClient):
            def fiscalize(self, payload):
                raise AssertionError("accepted invoices are never posted twice")

        again = self._submit(_Exploding())
        self.assertEqual(again.pk, submission.pk)
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "9000052011142444901")
        self.assertIn("F:9000052011142444901", base64.b64decode(self.invoice_a.qr_payload).decode())

    # -- H4 / sanity gates via the API --------------------------------------
    def test_public_component_url_rejected(self):
        client = self.api_client(self.user_b)
        payload = {
            "environment": "sandbox", "integration_mode": "ims",
            "pos_registration_number": 110099,
            "ims_local_base_url": "https://internal.example.com",
            "seller_ntn_cnic": "1234567", "seller_business_name": "S", "seller_address": "A",
        }
        response = client.post("/api/fbr/configurations/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("ims_local_base_url", str(response.content))

    def test_cloud_ims_requires_token_in_every_environment(self):
        client = self.api_client(self.user_b)
        payload = {
            "environment": "sandbox", "integration_mode": "ims",
            "pos_registration_number": 110099, "ims_use_cloud": True,
            "seller_ntn_cnic": "1234567", "seller_business_name": "S", "seller_address": "A",
        }
        response = client.post("/api/fbr/configurations/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("security_token", str(response.content))

    def test_production_local_mode_requires_component_confirmation(self):
        client = self.api_client(self.user_b)
        payload = {
            "environment": "production", "integration_mode": "ims",
            "pos_registration_number": 110099, "ims_local_confirmed": False,
            "security_token": "tok", "seller_ntn_cnic": "1234567",
            "seller_business_name": "S", "seller_address": "A",
        }
        response = client.post("/api/fbr/configurations/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("ims_local_confirmed", str(response.content))

    def test_health_endpoint_does_not_leak_urls_or_remote_bodies(self):
        client = self.api_client(self.user_a)
        with patch("fbr.services.IMSFiscalClient") as client_cls:
            client_cls.return_value.health_check.side_effect = IMSTransportError("internal detail http://10.0.0.1")
            response = client.get("/api/fbr/ims/health/")
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertNotIn("10.0.0.1", str(body))
        self.assertNotIn("url", body)

    def test_submission_http_status_mapping(self):
        from fbr.views import _submission_http_status

        class _S:
            def __init__(self, status):
                self.status = status

        self.assertEqual(_submission_http_status(_S(FBRSubmission.STATUS_ACCEPTED), created=201), 201)
        self.assertEqual(_submission_http_status(_S(FBRSubmission.STATUS_REJECTED), created=201), 422)
        self.assertEqual(_submission_http_status(_S(FBRSubmission.STATUS_FAILED), created=201), 502)
        self.assertEqual(_submission_http_status(_S(FBRSubmission.STATUS_UNKNOWN), created=201), 502)


class FakeTimeoutClient(FakeIMSClient):
    def fiscalize(self, payload):
        import requests

        raise _transport_error(requests.exceptions.ReadTimeout("read timed out"))


class FakeConnectTimeoutClient(FakeIMSClient):
    def fiscalize(self, payload):
        import requests

        raise _transport_error(requests.exceptions.ConnectTimeout("connect timed out"))
