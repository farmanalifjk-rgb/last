import requests
from .base import BaseAdapter


class ShopifyAdapter(BaseAdapter):
    """Shopify Admin REST API adapter. Requires config: {shop_url, access_token}."""
    @property
    def base_url(self):
        shop = self.config.get("shop_url", "").rstrip("/")
        return f"https://{shop}/admin/api/2024-01"

    @property
    def headers(self):
        return {"X-Shopify-Access-Token": self.config.get("access_token", ""),
                "Content-Type": "application/json"}

    def fetch_products(self):
        res = requests.get(f"{self.base_url}/products.json?limit=250", headers=self.headers, timeout=30)
        res.raise_for_status()
        products = res.json().get("products", [])
        return [{"remote_id": str(p["id"]), "name": p["title"], "sku": p.get("variants", [{}])[0].get("sku", ""),
                 "price": p.get("variants", [{}])[0].get("price", "0"),
                 "status": p.get("status", "active")} for p in products]

    def push_product(self, product_data):
        payload = {"product": {"title": product_data["name"], "variants": [{"sku": product_data.get("sku", ""),
                                                                              "price": str(product_data.get("price", 0))}]}}
        res = requests.post(f"{self.base_url}/products.json", headers=self.headers, json=payload, timeout=30)
        res.raise_for_status()
        return str(res.json()["product"]["id"])

    def fetch_orders(self, since=None):
        url = f"{self.base_url}/orders.json?limit=250&status=any"
        if since:
            url += f"&created_at_min={since.isoformat()}"
        res = requests.get(url, headers=self.headers, timeout=30)
        res.raise_for_status()
        orders = res.json().get("orders", [])
        return [{"remote_id": str(o["id"]), "number": o.get("name", ""),
                 "total": o.get("total_price", "0"),
                 "customer_name": o.get("customer", {}).get("first_name", "")} for o in orders]