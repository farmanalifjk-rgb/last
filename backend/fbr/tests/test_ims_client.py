"""Client tests for the Tier-1 IMS Software Fiscal Component (local + cloud)."""
import requests

from fbr.constants import (
    IMS_CLOUD_ENDPOINT_PRODUCTION,
    IMS_CLOUD_ENDPOINT_SANDBOX,
    IMS_LOCAL_BASE_URL_DEFAULT,
)
from fbr.ims_client import IMSFiscalClient, IMSTransportError, parse_ims_response

from .base import FBRTestBase, FakeResponse, FakeSession

LOCAL_OK = {
    "InvoiceNumber": "9000052011142444901",
    "Code": "100",
    "Response": "Fiscal Invoice Number generated successfully.",
    "Errors": None,
}
CLOUD_OK = {
    "FBRInvoiceNumber": 11000120181112000369,
    "Response": "Invoice received successfully",
    "Code": "100",
}


class ParseTests(FBRTestBase):
    def test_local_shape(self):
        response = parse_ims_response(LOCAL_OK, http_status=200)
        self.assertTrue(response.accepted)
        self.assertEqual(response.invoice_number, "9000052011142444901")
        self.assertEqual(response.code, "100")

    def test_cloud_shape(self):
        response = parse_ims_response(CLOUD_OK)
        self.assertTrue(response.accepted)
        self.assertEqual(response.invoice_number, "11000120181112000369")

    def test_rejection_shape(self):
        body = {"InvoiceNumber": "", "Code": "101", "Response": "Invalid POSID", "Errors": ["POSID not registered"]}
        response = parse_ims_response(body)
        self.assertFalse(response.accepted)
        self.assertEqual(response.errors, ["POSID not registered"])

    def test_non_object_body_raises(self):
        with self.assertRaises(IMSTransportError):
            parse_ims_response(["Service is responding"])


class LocalClientTests(FBRTestBase):
    def setUp(self):
        super().setUp()
        self.config = self.make_ims_config(self.tenant_a)

    def test_health_check_ok(self):
        session = FakeSession([FakeResponse(["Service is responding"], 200)])
        client = IMSFiscalClient(self.config, session=session)
        self.assertTrue(client.health_check())
        self.assertEqual(session.calls[0]["url"], f"{IMS_LOCAL_BASE_URL_DEFAULT}/api/IMSFiscal/get")

    def test_health_check_bad_body(self):
        session = FakeSession([FakeResponse({"error": "no"}, 200)])
        with self.assertRaises(IMSTransportError):
            IMSFiscalClient(self.config, session=session).health_check()

    def test_health_check_requires_local_mode(self):
        self.config.ims_use_cloud = True
        with self.assertRaises(IMSTransportError):
            IMSFiscalClient(self.config, session=FakeSession([])).health_check()

    def test_fiscalize_posts_to_local_component(self):
        session = FakeSession([FakeResponse(LOCAL_OK, 200)])
        response = IMSFiscalClient(self.config, session=session).fiscalize({"USIN": "U1"})
        self.assertTrue(response.accepted)
        call = session.calls[0]
        self.assertEqual(call["url"], f"{IMS_LOCAL_BASE_URL_DEFAULT}/api/IMSFiscal/GetInvoiceNumberByModel")
        self.assertNotIn("Authorization", call["headers"])  # local binding, no bearer

    def test_fiscalize_retries_transport_failures(self):
        # Only a provably undelivered request (connection refused) is retried;
        # ambiguous errors are covered by the no-re-POST tests below.
        session = FakeSession([requests.ConnectionError("refused"), FakeResponse(LOCAL_OK, 200)])
        config = self.make_ims_config(self.tenant_b)
        response = IMSFiscalClient(config, session=session).fiscalize({"USIN": "U1"})
        self.assertTrue(response.accepted)
        self.assertEqual(len(session.calls), 2)

    def test_fiscalize_non_json_body(self):
        response = FakeResponse(LOCAL_OK, 200)
        response.json = lambda: (_ for _ in ()).throw(ValueError("nope"))
        with self.assertRaises(IMSTransportError):
            IMSFiscalClient(self.config, session=FakeSession([response])).fiscalize({})


class CloudClientTests(FBRTestBase):
    def test_sandbox_cloud_endpoint(self):
        config = self.make_ims_config(self.tenant_a, ims_use_cloud=True, environment="sandbox")
        session = FakeSession([FakeResponse(CLOUD_OK, 200)])
        response = IMSFiscalClient(config, session=session).fiscalize({"USIN": "U1"})
        self.assertTrue(response.accepted)
        call = session.calls[0]
        self.assertEqual(call["url"], IMS_CLOUD_ENDPOINT_SANDBOX)
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-token")

    def test_production_cloud_endpoint(self):
        config = self.make_ims_config(
            self.tenant_a, ims_use_cloud=True, environment="production", verify_tls=True
        )
        session = FakeSession([FakeResponse(CLOUD_OK, 200)])
        response = IMSFiscalClient(config, session=session).fiscalize({"USIN": "U1"})
        self.assertTrue(response.accepted)
        self.assertEqual(session.calls[0]["url"], IMS_CLOUD_ENDPOINT_PRODUCTION)

    def test_local_base_url_override(self):
        config = self.make_ims_config(self.tenant_a, ims_local_base_url="http://192.168.1.10:8524/")
        session = FakeSession([FakeResponse(LOCAL_OK, 200)])
        IMSFiscalClient(config, session=session).fiscalize({})
        self.assertTrue(session.calls[0]["url"].startswith("http://192.168.1.10:8524/api/IMSFiscal/"))
