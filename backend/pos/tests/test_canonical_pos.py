from django.test import SimpleTestCase
from rest_framework.test import APIClient


class LegacyPOSTransactionRouteRetirementTests(SimpleTestCase):
    """Phase 6 ensures mutations cannot bypass the canonical /api/pos/ contract."""

    def setUp(self):
        self.client = APIClient()

    def test_retired_legacy_pos_transaction_routes_are_not_mounted(self):
        for path in (
            "/api/checkout/",
            "/api/session/open/",
            "/api/session/active/",
            "/api/session/close/",
            "/api/refund/process/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_retired_standalone_payment_settlement_routes_are_not_mounted(self):
        for path in (
            "/api/payments/orders/1/settle/",
            "/api/payments/tenders/",
            "/api/payments/sessions/1/reconcile/",
            "/api/payments/refunds/1/credit-note/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
