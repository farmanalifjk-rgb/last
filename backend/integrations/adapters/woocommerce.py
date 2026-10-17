import requests
from .base import BaseAdapter


class WooCommerceAdapter(BaseAdapter):
    """WooCommerce REST adapter. config: {store_url, consumer_key, consumer_secret}."""
    @property
    def base_url(self):
        return f"{self.config.get('store_url', '').rstrip('/')}/wp-json/wc/v3"

    @property
    def auth(self):
        return (self.config.get("consumer_key", ""), self.config.get("consumer_secret", ""))

    def fetch_products(self):
        res = requests.get(f"{self.base_url}/products?per_page=100", auth=self.auth, timeout=30)
        res.raise_for_status()
        products = res.json()
        return [{"remote_id": str(p["id"]), "name": p["name"], "sku": p.get("sku", ""),
                 "price": p.get("price", "0"), "status": p.get("status", "publish")} for p in products]

    def push_product(self, product_data):
        payload = {"name": product_data["name"], "sku": product_data.get("sku", ""),
                   "regular_price": str(product_data.get("price", 0))}
        res = requests.post(f"{self.base_url}/products", auth=self.auth, json=payload, timeout=30)
        res.raise_for_status()
        return str(res.json()["id"])

    def fetch_orders(self, since=None):
        url = f"{self.base_url}/orders?per_page=100"
        res = requests.get(url, auth=self.auth, timeout=30)
        res.raise_for_status()
        orders = res.json()
        return [{"remote_id": str(o["id"]), "number": str(o.get("number", "")),
                 "total": o.get("total", "0"),
                 "customer_name": f"{o.get('billing', {}).get('first_name', '')}"} for o in orders]