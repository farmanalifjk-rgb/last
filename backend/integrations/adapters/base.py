import hashlib
import json


class BaseAdapter:
    """Common scaffolding: every adapter implements these methods or raises NotImplementedError."""
    def __init__(self, integration):
        self.integration = integration
        self.config = integration.config or {}

    def _hash(self, data):
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    # ---- to override ----
    def fetch_products(self):
        raise NotImplementedError

    def push_product(self, product_data):
        raise NotImplementedError

    def fetch_orders(self, since=None):
        raise NotImplementedError

    def push_invoice(self, invoice_data):
        raise NotImplementedError

    def push_payment(self, payment_data):
        raise NotImplementedError