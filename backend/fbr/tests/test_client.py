"""FBR API client behaviour — DI API v1.12 (PRAL)."""
import requests

from fbr.client import FBRClient, FBRTransportError, parse_response
from fbr.constants import ENDPOINT_PRODUCTION, ENDPOINT_SANDBOX, ENDPOINT_VALIDATE_SANDBOX

from .base import FakeResponse, FakeSession, FBRTestBase

# v1.12 accepted body
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
# Legacy v1.0 accepted body kept for backward branch
ACCEPTED_LEGACY = {
    "statusCode": 200,
    "errorMessage": "",
    "result": "3310227771151DI1700000000123",
    "timestamp": "2023-12-20T10:15:00",
    "errors": [],
}


class ResponseParsingTests(FBRTestBase):
    def test_accepted_v112_response(self):
        response = parse_response(ACCEPTED_V112)
        self.assertTrue(response.accepted)
        self.assertEqual(response.invoice_number, "3310227771151DI1700000000123")
        self.assertEqual(response.dated, "2025-04-21")
        self.assertEqual(response.status_code, "00")
        self.assertEqual(response.validation_response["statusCode"], "00")

    def test_legacy_accepted_still_parses(self):
        response = parse_response(ACCEPTED_LEGACY)
        self.assertTrue(response.accepted)
        self.assertEqual(response.result, "3310227771151DI1700000000123")
        self.assertEqual(response.status_code, 200)

    def test_rejected_v112_keeps_error_code(self):
        response = parse_response({
            "invoiceNumber": "",
            "validationResponse": {
                "statusCode": "01",
                "errorCode": "0001",
                "error": "Invalid HS code",
                "invoiceStatuses": [{"itemSNo": "1", "statusCode": "01", "errorCode": "0402", "error": "Invalid hsCode"}],
            }
        })
        self.assertFalse(response.accepted)
        self.assertEqual(response.error_code, "0001")
        self.assertIn("Invalid HS code", response.errors[0])

    def test_dotnet_style_error_collection_is_flattened(self):
        response = parse_response({"statusCode": 400, "errors": {"$values": ["bad request"]}})
        self.assertEqual(response.errors, ["bad request"])

    def test_non_object_body_is_a_transport_error(self):
        with self.assertRaises(FBRTransportError):
            parse_response(["unexpected"])


class ClientTests(FBRTestBase):
    def test_posts_bearer_token_to_the_v112_sandbox_endpoint(self):
        session = FakeSession([FakeResponse(ACCEPTED_V112)])
        FBRClient(self.config_a, session=session).post_invoice({"invoiceType": "Sale Invoice"})
        call = session.calls[0]
        self.assertEqual(call["url"], ENDPOINT_SANDBOX)
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(call["json"], {"invoiceType": "Sale Invoice"})
        self.assertTrue(call["verify"])

    def test_validate_posts_to_validate_endpoint(self):
        session = FakeSession([FakeResponse(ACCEPTED_V112)])
        FBRClient(self.config_a, session=session).validate_invoice({"invoiceType": "Sale Invoice"})
        self.assertEqual(session.calls[0]["url"], ENDPOINT_VALIDATE_SANDBOX)

    def test_production_configuration_posts_to_the_production_endpoint(self):
        config = self.make_config(self.tenant_b, environment="production", scenario_id="")
        session = FakeSession([FakeResponse(ACCEPTED_V112)])
        FBRClient(config, session=session).post_invoice({})
        self.assertEqual(session.calls[0]["url"], ENDPOINT_PRODUCTION)

    def test_endpoint_override_wins(self):
        self.config_a.endpoint_url = "https://staging.example.com/postinvoicedata_sb"
        session = FakeSession([FakeResponse(ACCEPTED_V112)])
        FBRClient(self.config_a, session=session).post_invoice({})
        self.assertEqual(session.calls[0]["url"], "https://staging.example.com/postinvoicedata_sb")

    def test_fiscalization_transport_failure_is_not_retried(self):
        session = FakeSession([requests.ConnectionError("boom")])
        client = FBRClient(self.config_a, session=session, sleep=lambda _: None)
        with self.assertRaises(FBRTransportError):
            client.post_invoice({})
        self.assertEqual(len(session.calls), 1)

    def test_fiscalization_503_is_not_retried(self):
        session = FakeSession([FakeResponse("gateway", status_code=503)])
        client = FBRClient(self.config_a, session=session, sleep=lambda _: None)
        with self.assertRaises(FBRTransportError):
            client.post_invoice({})
        self.assertEqual(len(session.calls), 1)

    def test_validate_transient_failures_are_retried(self):
        session = FakeSession([
            requests.ConnectionError("boom"),
            FakeResponse("gateway", status_code=503),
            FakeResponse(ACCEPTED_V112),
        ])
        client = FBRClient(self.config_a, session=session, sleep=lambda _: None)
        response = client.validate_invoice({})
        self.assertTrue(response.accepted)
        self.assertEqual(len(session.calls), 3)

    def test_retries_are_bounded_by_the_configuration(self):
        self.config_a.max_retries = 1
        session = FakeSession([requests.ConnectionError("boom")] * 2)
        client = FBRClient(self.config_a, session=session, sleep=lambda _: None)
        with self.assertRaises(FBRTransportError):
            client.validate_invoice({})
        self.assertEqual(len(session.calls), 2)

    def test_non_success_http_status_cannot_be_accepted(self):
        body = dict(ACCEPTED_V112)
        session = FakeSession([FakeResponse(body, status_code=503)])
        client = FBRClient(self.config_a, session=session, sleep=lambda _: None)
        with self.assertRaises(FBRTransportError):
            client.post_invoice({})

    def test_business_rejections_are_not_retried(self):
        session = FakeSession([FakeResponse({"invoiceNumber": "", "validationResponse": {"statusCode": "01", "error": "Invalid"}})])
        client = FBRClient(self.config_a, session=session, sleep=lambda _: None)
        response = client.post_invoice({})
        self.assertFalse(response.accepted)
        self.assertEqual(len(session.calls), 1)
