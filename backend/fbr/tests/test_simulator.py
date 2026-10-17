"""Tests for the isolated Tier-1 IMS simulator; no external network is used."""
from django.test import override_settings

from .base import FBRTestBase
from fbr.simulator import validate_ims_invoice
from fbr.models import FBRSimulatorExchange, FBRSubmission
from fbr.services import retry_submission, submit_invoice


def valid_invoice():
    return {
        "InvoiceNumber": "",
        "POSID": 110014,
        "USIN": "TEST-USIN-001",
        "RefUSIN": None,
        "DateTime": "2026-10-10T10:00:00",
        "BuyerName": "Walk-in Customer",
        "BuyerNTN": "",
        "BuyerCNIC": "",
        "BuyerPhoneNumber": "",
        "TotalSaleValue": 2000.0,
        "TotalTaxCharged": 360.0,
        "TotalQuantity": 2,
        "Discount": 0.0,
        "FurtherTax": 0.0,
        "TotalBillAmount": 2360.0,
        "PaymentMode": 1,
        "InvoiceType": 1,
        "Items": [{
            "ItemCode": "SKU-1",
            "ItemName": "Test Product",
            "PCTCode": "84713010",
            "Quantity": 2,
            "TaxRate": 18.0,
            "SaleValue": 2000.0,
            "Discount": 0.0,
            "FurtherTax": 0.0,
            "TaxCharged": 360.0,
            "TotalAmount": 2360.0,
            "InvoiceType": 1,
        }],
    }


@override_settings(FBR_SIMULATOR_ENABLED=True, FBR_SIMULATOR_MODE="sandbox", ROOT_URLCONF="backend.urls")
class IMSSimulatorAPITests(FBRTestBase):
    def setUp(self):
        super().setUp()
        self.client_a = self.api_client(self.user_a)
        self.sandbox_url = "/api/fbr-simulator/sandbox/api/IMSFiscal/GetInvoiceNumberByModel"
        self.production_url = "/api/fbr-simulator/production/api/IMSFiscal/GetInvoiceNumberByModel"

    def test_sandbox_success_uses_documented_response_keys(self):
        response = self.client_a.post(self.sandbox_url, valid_invoice(), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"InvoiceNumber", "Code", "Response", "Errors"})
        self.assertEqual(response.data["Code"], "100")
        self.assertTrue(response.data["InvoiceNumber"].startswith("SIM-SBX-"))
        self.assertIn("NOT ISSUED BY FBR", response.data["Response"])

    def test_production_like_route_is_disabled_even_when_development_simulator_is_enabled(self):
        response = self.client_a.post(self.production_url, valid_invoice(), format="json")
        self.assertEqual(response.status_code, 404)

    def test_same_usin_is_idempotent_per_tenant_and_environment(self):
        first = self.client_a.post(self.sandbox_url, valid_invoice(), format="json")
        second = self.client_a.post(self.sandbox_url, valid_invoice(), format="json")
        self.assertEqual(first.data["InvoiceNumber"], second.data["InvoiceNumber"])

    def test_totals_mismatch_is_rejected(self):
        payload = valid_invoice()
        payload["TotalBillAmount"] = 99
        response = self.client_a.post(self.sandbox_url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["Code"], "101")
        self.assertEqual(response.data["InvoiceNumber"], "")
        self.assertTrue(response.data["Errors"])

    def test_tax_and_line_arithmetic_mismatches_are_rejected(self):
        payload = valid_invoice()
        payload["Items"][0]["TaxCharged"] = 350
        payload["TotalTaxCharged"] = 350
        payload["Items"][0]["TotalAmount"] = 2350
        payload["TotalBillAmount"] = 2350
        response = self.client_a.post(self.sandbox_url, payload, format="json")
        self.assertEqual(response.data["Code"], "101")
        self.assertTrue(any("TaxCharged does not match" in error for error in response.data["Errors"]))

    def test_configured_rejected_and_failed_outcomes_are_persisted(self):
        with self.settings(FBR_SIMULATOR_OUTCOME="rejected"):
            rejected = self.client_a.post(self.sandbox_url, valid_invoice(), format="json")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data["Code"], "101")
        exchange = FBRSimulatorExchange.objects.get(tenant=self.tenant_a, usin="TEST-USIN-001")
        self.assertEqual(exchange.status, FBRSimulatorExchange.STATUS_REJECTED)
        self.assertEqual(exchange.request_payload["USIN"], "TEST-USIN-001")
        self.assertEqual(exchange.response_payload["Code"], "101")
        self.assertEqual(exchange.attempts, 1)

        payload = valid_invoice()
        payload["USIN"] = "TEST-USIN-FAILED"
        with self.settings(FBR_SIMULATOR_OUTCOME="failed"):
            failed = self.client_a.post(self.sandbox_url, payload, format="json")
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(failed.data["Code"], "500")
        failed_exchange = FBRSimulatorExchange.objects.get(tenant=self.tenant_a, usin="TEST-USIN-FAILED")
        self.assertEqual(failed_exchange.status, FBRSimulatorExchange.STATUS_FAILED)
        self.assertEqual(failed_exchange.attempt_history[0]["response"]["Code"], "500")

    def test_retry_after_failure_can_accept_once_and_preserves_attempt_history(self):
        payload = valid_invoice()
        with self.settings(FBR_SIMULATOR_OUTCOME="rejected"):
            rejected = self.client_a.post(self.sandbox_url, payload, format="json")
        self.assertEqual(rejected.data["Code"], "101")
        with self.settings(FBR_SIMULATOR_OUTCOME="accepted"):
            accepted = self.client_a.post(self.sandbox_url, payload, format="json")
            replay = self.client_a.post(self.sandbox_url, payload, format="json")
        self.assertEqual(accepted.data["Code"], "100")
        self.assertEqual(accepted.data["InvoiceNumber"], replay.data["InvoiceNumber"])
        exchange = FBRSimulatorExchange.objects.get(tenant=self.tenant_a, usin="TEST-USIN-001")
        self.assertEqual(exchange.status, FBRSimulatorExchange.STATUS_ACCEPTED)
        self.assertEqual(exchange.attempts, 3)
        self.assertEqual(len(exchange.attempt_history), 3)
        self.assertEqual(len(set([accepted.data["InvoiceNumber"], replay.data["InvoiceNumber"]])), 1)

    def test_reusing_usin_with_different_payload_is_rejected_and_does_not_change_number(self):
        first = self.client_a.post(self.sandbox_url, valid_invoice(), format="json")
        changed = valid_invoice()
        changed["TotalSaleValue"] = 1000
        response = self.client_a.post(self.sandbox_url, changed, format="json")
        self.assertEqual(response.data["Code"], "101")
        self.assertIn("different invoice payload", response.data["Response"])
        exchange = FBRSimulatorExchange.objects.get(tenant=self.tenant_a, usin="TEST-USIN-001")
        self.assertEqual(exchange.simulated_invoice_number, first.data["InvoiceNumber"])
        self.assertEqual(exchange.attempts, 2)
        self.assertEqual(len(exchange.attempt_history), 2)

    def test_simulated_invoice_number_is_database_unique(self):
        self.client_a.post(self.sandbox_url, valid_invoice(), format="json")
        exchange = FBRSimulatorExchange.objects.get(tenant=self.tenant_a)
        duplicate = FBRSimulatorExchange(
            tenant=self.tenant_b,
            environment=exchange.environment,
            usin="ANOTHER-USIN",
            idempotency_key="ANOTHER-USIN",
            request_fingerprint="0" * 64,
            simulated_invoice_number=exchange.simulated_invoice_number,
        )
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()

    def test_simulator_is_not_exposed_outside_development(self):
        with self.settings(DJANGO_ENV="staging"):
            response = self.client_a.post(self.sandbox_url, valid_invoice(), format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(FBRSimulatorExchange.objects.exists())

    def test_health_response_matches_local_component_contract(self):
        response = self.client_a.get("/api/fbr-simulator/sandbox/api/IMSFiscal/get")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, ["Service is responding"])

    def test_simulator_disabled_returns_404(self):
        with self.settings(FBR_SIMULATOR_ENABLED=False):
            response = self.client_a.post(self.sandbox_url, valid_invoice(), format="json")
        self.assertEqual(response.status_code, 404)

    def test_validator_rejects_missing_items(self):
        payload = valid_invoice()
        payload["Items"] = []
        self.assertTrue(validate_ims_invoice(payload))

    def test_other_tenant_gets_different_simulated_invoice_number(self):
        client_b = self.api_client(self.user_b)
        response_a = self.client_a.post(self.sandbox_url, valid_invoice(), format="json")
        response_b = client_b.post(self.sandbox_url, valid_invoice(), format="json")
        self.assertNotEqual(response_a.data["InvoiceNumber"], response_b.data["InvoiceNumber"])

    def test_simulator_submission_and_retry_never_use_external_transports(self):
        from unittest.mock import patch

        self.make_ims_config(self.tenant_a, use_simulator=True)
        with patch("fbr.ims_client.IMSFiscalClient.fiscalize", side_effect=AssertionError("external IMS transport")), \
             patch("fbr.client.FBRClient.post_invoice", side_effect=AssertionError("external FBR transport")):
            with self.settings(FBR_SIMULATOR_OUTCOME="rejected"):
                submission = submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id, user=self.user_a)
            with self.settings(FBR_SIMULATOR_OUTCOME="accepted"):
                retried = retry_submission(tenant=self.tenant_a, submission_id=submission.id, user=self.user_a)
        self.assertEqual(retried.pk, submission.pk)
        self.assertEqual(retried.status, FBRSubmission.STATUS_ACCEPTED)
        self.assertTrue(retried.is_simulated)
        exchange = FBRSimulatorExchange.objects.get(tenant=self.tenant_a, usin=submission.usin)
        self.assertEqual(exchange.attempts, 2)
        self.assertEqual([entry["status"] for entry in exchange.attempt_history], ["rejected", "accepted"])
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "")

    def test_existing_submission_service_can_fiscalize_without_network(self):
        # The simulator only answers for a configuration that opts in.
        self.make_ims_config(self.tenant_a, use_simulator=True)
        submission = submit_invoice(
            tenant=self.tenant_a,
            invoice_id=self.invoice_a.id,
            user=self.user_a,
        )
        self.assertEqual(submission.status, FBRSubmission.STATUS_ACCEPTED)
        self.assertTrue(submission.is_simulated)
        self.assertTrue(submission.fbr_invoice_number.startswith("SIM-SBX-"))
        self.assertIn("NOT ISSUED BY FBR", submission.response_payload["Response"])
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            FBRSubmission.objects.create(
                tenant=self.tenant_a, invoice=self.invoice_a,
                status=FBRSubmission.STATUS_REJECTED, is_simulated=True,
                fbr_invoice_number=submission.fbr_invoice_number,
            )
        # A simulated acceptance is never applied to the fiscal invoice/receipt.
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "")
