from .base import BaseAdapter


class QuickBooksAdapter(BaseAdapter):
    """QuickBooks Online adapter. Stub: real impl requires OAuth2 + refresh token flow.
    config: {realm_id, access_token (short-lived), refresh_token}.
    Replace _request with signed OAuth2 calls in production.
    """
    BASE = "https://quickbooks.api.intuit.com"

    def push_invoice(self, invoice_data):
        # Stub: build QBO Invoice object
        payload = {"Line": [{"Amount": float(invoice_data.get("total", 0)),
                             "DetailType": "SalesItemLineDetail",
                             "SalesItemLineDetail": {"ItemRef": {"value": "1"}}}],
                   "CustomerRef": {"value": str(invoice_data.get("customer_id", "1"))},
                   "TotalAmt": float(invoice_data.get("total", 0))}
        # res = requests.post(f"{self.BASE}/v3/company/{self.config['realm_id']}/invoice",
        #                      headers=self._headers(), json=payload, timeout=30)
        # res.raise_for_status(); return res.json()["Invoice"]["Id"]
        return f"QB-STUB-{invoice_data.get('invoice_number', '')}"

    def push_payment(self, payment_data):
        return f"QB-PAY-STUB-{payment_data.get('amount', 0)}"