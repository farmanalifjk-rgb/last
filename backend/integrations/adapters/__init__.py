from .base import BaseAdapter
from .shopify import ShopifyAdapter
from .woocommerce import WooCommerceAdapter
from .quickbooks import QuickBooksAdapter

ADAPTERS = {
    "shopify": ShopifyAdapter,
    "woocommerce": WooCommerceAdapter,
    "quickbooks": QuickBooksAdapter,
}

def get_adapter(integration):
    cls = ADAPTERS.get(integration.kind)
    if not cls:
        raise ValueError(f"No adapter for {integration.kind}")
    return cls(integration)