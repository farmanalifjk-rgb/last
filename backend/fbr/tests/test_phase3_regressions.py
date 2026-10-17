"""Phase-3 audit regressions: fiscal transport safety, simulator isolation and
POS-charge / fiscal-document consistency.

Every test here reproduces a defect observed at runtime against the real
clients and the real checkout (not hand-built fakes):

* R1  a read timeout from the real IMS/DI client was classified "failed" (the
      requests cause was dropped) and the IMS client silently re-POSTed it;
* R2  deployment simulator flags silently routed every sandbox configuration
      (including the official PRAL cloud sandbox) to the simulator;
* R3  a simulated acceptance was written to the fiscal invoice (SIM number,
      QR payload) and the FBR QR endpoint rendered it;
* R4  a fiscal document could report a bill different from what was charged;
* R5  price-inclusive tax was added on top of the price at checkout.
"""
from decimal import Decimal
from unittest.mock import patch

import requests
from django.test import override_settings

from fbr.client import FBRClient
from fbr.ims_client import IMSFiscalClient, IMSTransportError
from fbr.ims_payload import build_ims_invoice_payload
from fbr.models import FBRConfiguration, FBRHSCode, FBRProductProfile, FBRSubmission, FBRUnitOfMeasure
from fbr.payload import FBRValidationError
from fbr.services import (
    FBRServiceError,
    _ims_client_for_configuration,
    ims_health,
    retry_submission,
    submit_invoice,
)
from fbr.simulator import IMSSimulatorClient
from fbr.transport import OUTCOME_FAILED, OUTCOME_UNKNOWN, classify_transport_outcome
from fiscal.models import FiscalDevice, FiscalInvoice, FiscalSubmission, InvoiceSequence
from fiscal.services import issue_invoice, submit_to_device
from pos.models import CashSession, Category, Company, Order, Product
from pricing.models import PriceList, PriceListItem
from tax.models import TaxRate

from .base import FakeResponse, FakeSession, FBRTestBase

LOCAL_OK = {"InvoiceNumber": "9000052011142444901", "Code": "100", "Response": "Fiscal Invoice Number generated successfully.", "Errors": None}


def _no_sleep(*_args):
    return None


class FiscalTransportClassificationTests(FBRTestBase):
    """R1 — the real clients must preserve 'may have been fiscalized'."""

    def setUp(self):
        super().setUp()
        self.ims_config = self.make_ims_config(self.tenant_a, max_retries=2)

    def _ims_client(self, *responses):
        session = FakeSession(list(responses))
        return IMSFiscalClient(self.ims_config, session=session, sleep=_no_sleep), session

    def test_ims_read_timeout_is_unknown_and_never_reposted(self):
        client, session = self._ims_client(requests.exceptions.ReadTimeout("read timed out"), FakeResponse(LOCAL_OK, 200))
        with self.assertRaises(IMSTransportError) as ctx:
            client.fiscalize({"USIN": "U1"})
        self.assertEqual(len(session.calls), 1, "a possibly-delivered invoice must not be re-POSTed")
        self.assertIsInstance(ctx.exception.__cause__, requests.exceptions.ReadTimeout)
        self.assertEqual(classify_transport_outcome(ctx.exception), OUTCOME_UNKNOWN)

    def test_ims_ambiguous_transport_error_is_not_reposted(self):
        client, session = self._ims_client(requests.RequestException("stream died"), FakeResponse(LOCAL_OK, 200))
        with self.assertRaises(IMSTransportError) as ctx:
            client.fiscalize({"USIN": "U1"})
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(classify_transport_outcome(ctx.exception), OUTCOME_UNKNOWN)

    def test_ims_connect_failures_are_retried_and_classified_failed(self):
        client, session = self._ims_client(
            requests.exceptions.ConnectTimeout("connect timed out"),
            requests.ConnectionError("refused"),
            requests.ConnectionError("refused"),
        )
        with self.assertRaises(IMSTransportError) as ctx:
            client.fiscalize({"USIN": "U1"})
        self.assertEqual(len(session.calls), 3)  # max_retries=2 -> 3 attempts, none delivered
        self.assertEqual(classify_transport_outcome(ctx.exception), OUTCOME_FAILED)

    def test_submit_with_real_ims_client_read_timeout_parks_unknown_and_blocks_retry(self):
        client, session = self._ims_client(requests.exceptions.ReadTimeout("read timed out"))
        submission = submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=client)
        self.assertEqual(submission.status, FBRSubmission.STATUS_UNKNOWN)
        self.assertEqual(len(session.calls), 1)
        with self.assertRaises(FBRServiceError):
            retry_submission(tenant=self.tenant_a, submission_id=submission.pk, client=self._ims_client(FakeResponse(LOCAL_OK))[0])
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "")

    def test_di_read_timeout_keeps_its_cause_and_parks_unknown(self):
        di_config = FBRConfiguration.objects.get(pk=self.config_a.pk)
        di_config.integration_mode = "di"
        di_config.save()
        session = FakeSession([requests.exceptions.ReadTimeout("read timed out")])
        submission = submit_invoice(
            tenant=self.tenant_a, invoice_id=self.invoice_a.id,
            client=FBRClient(di_config, session=session, sleep=_no_sleep),
        )
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(submission.status, FBRSubmission.STATUS_UNKNOWN)


@override_settings(FBR_SIMULATOR_ENABLED=True, FBR_SIMULATOR_MODE="sandbox")
class SimulatorIsolationTests(FBRTestBase):
    """R2/R3 — the simulator never intercepts and never looks fiscalized."""

    def setUp(self):
        super().setUp()
        self.api_a = self.api_client(self.user_a)

    def test_deployment_flags_alone_never_route_to_the_simulator(self):
        local = self.make_ims_config(self.tenant_a)
        self.assertIsInstance(_ims_client_for_configuration(local), IMSFiscalClient)
        local.ims_use_cloud = True  # official PRAL sandbox endpoint
        self.assertIsInstance(_ims_client_for_configuration(local), IMSFiscalClient)

    def test_opted_in_configuration_uses_the_simulator(self):
        config = self.make_ims_config(self.tenant_a, use_simulator=True)
        self.assertIsInstance(_ims_client_for_configuration(config), IMSSimulatorClient)

    @override_settings(FBR_SIMULATOR_ENABLED=False)
    def test_opted_in_configuration_fails_closed_when_simulator_disabled(self):
        self.make_ims_config(self.tenant_a, use_simulator=True)
        with patch("fbr.services.IMSFiscalClient") as real_client:
            with self.assertRaises(FBRServiceError):
                submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id)
            real_client.assert_not_called()
        self.assertFalse(FBRSubmission.objects.filter(invoice=self.invoice_a).exists())

    def test_opted_in_configuration_fails_closed_on_environment_mismatch(self):
        config = self.make_ims_config(self.tenant_a, use_simulator=True)
        config.environment = "production"
        with self.assertRaises(FBRServiceError):
            _ims_client_for_configuration(config)

    def test_simulated_acceptance_is_never_applied_to_the_fiscal_invoice(self):
        self.make_ims_config(self.tenant_a, use_simulator=True)
        submission = submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id, user=self.user_a)
        self.assertEqual(submission.status, FBRSubmission.STATUS_ACCEPTED)
        self.assertTrue(submission.is_simulated)
        self.assertTrue(submission.fbr_invoice_number.startswith("SIM-"))
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "")
        self.assertNotIn("SIM-", self.invoice_a.qr_payload)
        # The FBR QR endpoint refuses; the APIs say "simulated" explicitly.
        self.assertEqual(self.api_a.get(f"/api/fbr/invoices/{self.invoice_a.id}/qr.png").status_code, 400)
        detail = self.api_a.get(f"/api/fbr/submissions/{submission.id}/").json()
        self.assertIs(detail["is_simulated"], True)
        fiscal = self.api_a.get(f"/api/fiscal/invoices/{self.invoice_a.id}/").json()
        self.assertEqual(fiscal["fbr_invoice_number"], "")
        # Idempotent: the same invoice is never re-sent (simulated or real).
        again = submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id, user=self.user_a)
        self.assertEqual(again.pk, submission.pk)
        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.fbr_invoice_number, "")

    def test_legacy_simulated_acceptance_on_invoice_never_renders_a_qr(self):
        self.make_ims_config(self.tenant_a, use_simulator=True)
        submission = submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id, user=self.user_a)
        # Data written before this fix: SIM number on the invoice, no flag.
        FiscalInvoice.objects.filter(pk=self.invoice_a.pk).update(fbr_invoice_number=submission.fbr_invoice_number)
        FBRSubmission.objects.filter(pk=submission.pk).update(is_simulated=False)
        self.assertEqual(self.api_a.get(f"/api/fbr/invoices/{self.invoice_a.id}/qr.png").status_code, 400)

    def test_retry_never_switches_between_real_and_simulated_targets(self):
        config = self.make_ims_config(self.tenant_a)
        failing = IMSFiscalClient(config, session=FakeSession([requests.ConnectionError("refused")]), sleep=_no_sleep)
        config.max_retries = 0
        submission = submit_invoice(tenant=self.tenant_a, invoice_id=self.invoice_a.id, client=failing)
        self.assertEqual(submission.status, FBRSubmission.STATUS_FAILED)
        self.assertFalse(submission.is_simulated)
        FBRConfiguration.objects.filter(pk=config.pk).update(use_simulator=True)
        with self.assertRaises(FBRServiceError):
            retry_submission(tenant=self.tenant_a, submission_id=submission.pk)
        submission.refresh_from_db()
        self.assertEqual(submission.status, FBRSubmission.STATUS_FAILED)
        self.assertEqual(submission.attempts, 1)

    def test_health_is_labelled_simulated_and_real_probe_is_not_intercepted(self):
        config = self.make_ims_config(self.tenant_a)
        with patch("fbr.services.IMSFiscalClient") as real_client:
            real_client.return_value.health_check.side_effect = IMSTransportError("down")
            self.assertEqual(ims_health(tenant=self.tenant_a)["status"], "unreachable")
        FBRConfiguration.objects.filter(pk=config.pk).update(use_simulator=True)
        self.assertEqual(ims_health(tenant=self.tenant_a), {"status": "responding", "simulated": True})

    @override_settings(FBR_SIMULATOR_ENABLED=False)
    def test_configuration_api_refuses_use_simulator_when_disabled(self):
        config = self.make_ims_config(self.tenant_a)
        response = self.api_a.patch(f"/api/fbr/configurations/{config.id}/", {"use_simulator": True}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        config.refresh_from_db()
        self.assertFalse(config.use_simulator)

    def test_fiscal_device_mirrors_simulated_and_unknown_outcomes_as_requires_review(self):
        device = FiscalDevice.objects.create(
            tenant=self.tenant_a, name="FBR", kind=FiscalDevice.KIND_API, provider=FiscalDevice.PROVIDER_FBR,
        )
        self.make_ims_config(self.tenant_a, use_simulator=True)
        mirrored = submit_to_device(tenant=self.tenant_a, invoice_id=self.invoice_a.id, device_id=device.id, user=self.user_a)
        self.assertEqual(mirrored.status, FiscalSubmission.STATUS_REQUIRES_REVIEW)

        invoice_b = self.make_invoice(self.tenant_a, "unk")
        config = self.make_ims_config(self.tenant_a, use_simulator=False)
        timeout = IMSFiscalClient(config, session=FakeSession([requests.exceptions.ReadTimeout("t")]), sleep=_no_sleep)
        submit_invoice(tenant=self.tenant_a, invoice_id=invoice_b.id, client=timeout)
        unknown = FBRSubmission.objects.get(invoice=invoice_b)
        self.assertEqual(unknown.status, FBRSubmission.STATUS_UNKNOWN)
        # The device mirror reports the pending (unknown) submission for review
        # instead of calling it a rejection.
        with patch("fbr.services.submit_invoice", return_value=unknown):
            mirrored_b = submit_to_device(tenant=self.tenant_a, invoice_id=invoice_b.id, device_id=device.id, user=self.user_a)
        self.assertEqual(mirrored_b.status, FiscalSubmission.STATUS_REQUIRES_REVIEW)
        # A simulator rejection is not an FBR rejection either.
        unknown.status, unknown.is_simulated = FBRSubmission.STATUS_REJECTED, True
        with patch("fbr.services.submit_invoice", return_value=unknown):
            mirrored_c = submit_to_device(tenant=self.tenant_a, invoice_id=invoice_b.id, device_id=device.id, user=self.user_a)
        self.assertEqual(mirrored_c.status, FiscalSubmission.STATUS_REQUIRES_REVIEW)


class CheckoutFiscalConsistencyTests(FBRTestBase):
    """R4/R5 — through the real POS checkout endpoint."""

    def setUp(self):
        super().setUp()
        self.client_pos = self.api_client(self.user_b)
        tenant = self.tenant_b
        category = Category.objects.create(tenant=tenant, name="Consistency")
        price_list = PriceList.objects.create(tenant=tenant, name="POS default", is_default=True, is_active=True)
        self.product = Product.objects.create(
            tenant=tenant, category=category, name="Taxed Widget", sku="TW-1",
            sales_price=Decimal("100.00"), cost_price=Decimal("40.00"),
            stock_quantity=Decimal("20.000"), is_active=True,
        )
        PriceListItem.objects.create(tenant=tenant, price_list=price_list, product=self.product,
                                     price=Decimal("100.00"), min_quantity=Decimal("1"))
        CashSession.objects.create(tenant=tenant, opened_by=self.user_b, employee_name="B",
                                   opening_balance=Decimal("0.00"), is_open=True)
        Company.objects.create(tenant=tenant, name="Consistency", address="Karachi", currency="PKR")
        self.rate = TaxRate.objects.create(tenant=tenant, name="GST", code="GST18", rate=Decimal("0.1800"),
                                           is_active=True, applies_to_all=True)
        self.profile = FBRProductProfile.objects.create(
            tenant=tenant, product=self.product,
            hs_code=FBRHSCode.objects.get_or_create(code="84713010", defaults={"description": "x"})[0],
            uom=FBRUnitOfMeasure.objects.get_or_create(code="U1000012", defaults={"description": "u"})[0],
            pct_code="84713010", sales_tax_rate=Decimal("18.000"),
        )
        self.config = self.make_ims_config(tenant)
        self.sequence = InvoiceSequence.objects.create(tenant=tenant, name="C", prefix="CON", document_type="invoice")
        # Checkout now fiscalizes automatically (phase 4): fake the local IMS
        # component so these tests never open a socket.
        session = FakeSession([FakeResponse(LOCAL_OK, 200) for _ in range(4)])
        patcher = patch("fbr.services._ims_client_for_configuration",
                        side_effect=lambda cfg: IMSFiscalClient(cfg, session=session, sleep=_no_sleep))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _checkout(self, amount, key):
        response = self.client_pos.post(
            "/api/pos/checkout/",
            {"items": [{"product_id": self.product.id, "quantity": "1"}],
             "tenders": [{"tender_type": "cash", "amount": amount}]},
            format="json", HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Order.objects.get(tenant=self.tenant_b, pk=response.json()["order"]["id"])

    def _issue(self, order):
        # The invoice checkout issued; one sale never gets a second invoice.
        existing = FiscalInvoice.objects.filter(tenant=self.tenant_b, order=order).first()
        return existing or issue_invoice(tenant=self.tenant_b, order_id=order.id, sequence_id=self.sequence.id, user=self.user_b)

    def test_consistent_sale_reports_exactly_what_was_charged(self):
        order = self._checkout("118.00", "consistent-1")
        payload = build_ims_invoice_payload(self._issue(order), config=self.config)
        self.assertEqual(Decimal(str(payload["TotalBillAmount"])), order.total)
        self.assertEqual(Decimal(str(payload["TotalTaxCharged"])), order.tax)

    def test_profile_rate_mismatch_is_refused_before_any_submission(self):
        self.profile.sales_tax_rate = Decimal("17.000")
        self.profile.save()
        order = self._checkout("118.00", "mismatch-1")
        invoice = self._issue(order)
        with self.assertRaises(FBRValidationError):
            build_ims_invoice_payload(invoice, config=self.config)
        with self.assertRaises(FBRValidationError):
            submit_invoice(tenant=self.tenant_b, invoice_id=invoice.id)
        self.assertFalse(FBRSubmission.objects.filter(invoice=invoice).exists())

    def test_inclusive_tax_is_not_charged_on_top_of_the_price(self):
        self.rate.mode = TaxRate.MODE_INCLUSIVE
        self.rate.save()
        preview = self.client_pos.post(
            "/api/pos/preview/", {"items": [{"product_id": self.product.id, "quantity": "1"}]}, format="json",
        ).json()
        self.assertEqual(preview["total"], "100.00")
        self.assertEqual(preview["tax"], "15.25")  # reported, already inside the price
        order = self._checkout("100.00", "inclusive-1")
        self.assertEqual(order.total, Decimal("100.00"))
        self.assertEqual(order.tax, Decimal("15.25"))
        self.assertEqual(sum(t.amount for t in order.tenders.all()), Decimal("100.00"))
        # The fiscal layer does not model inclusive pricing yet: it refuses to
        # report 118.00 for a sale that collected 100.00.
        with self.assertRaises(FBRValidationError):
            build_ims_invoice_payload(self._issue(order), config=self.config)

    def test_exclusive_tax_is_still_added(self):
        order = self._checkout("118.00", "exclusive-1")
        self.assertEqual(order.total, Decimal("118.00"))


class SimulatorProductionSettingsTests(FBRTestBase):
    """Production settings can never enable the simulator (fresh interpreter)."""

    def _load_settings(self, **env_overrides):
        import os
        import subprocess
        import sys
        from pathlib import Path

        from cryptography.fernet import Fernet

        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "DJANGO_SECRET_KEY": "settings-test-only-not-a-real-secret-0123456789abcdef",
            "DJANGO_ALLOWED_HOSTS": "pos.example.test",
            "FBR_CREDENTIAL_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            **env_overrides,
        }
        return subprocess.run(
            [sys.executable, "-c",
             "import backend.settings as s; print(s.FBR_SIMULATOR_ENABLED, s.FBR_SIMULATOR_MODE)"],
            cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, timeout=60,
        )

    def test_production_defaults_disable_the_simulator(self):
        result = self._load_settings(DJANGO_ENV="production")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "False disabled")

    def test_production_refuses_to_start_with_the_simulator_enabled(self):
        result = self._load_settings(DJANGO_ENV="production", FBR_SIMULATOR_ENABLED="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FBR_SIMULATOR_ENABLED may only be true", result.stderr)
