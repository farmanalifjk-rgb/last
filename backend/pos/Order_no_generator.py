from django.db import transaction

from .models import PurchaseOrder
from saas.models import Tenant


def generate_purchase_order_number(*, tenant):
    """
    Tenant-scoped, race-free PO number generator.
    Must be called inside an outer transaction.atomic block by the caller.
    Uses Tenant row as serialization point to avoid cross-tenant contention.
    """
    if tenant is None or not getattr(tenant, "pk", None):
        raise ValueError("Tenant is required to generate a purchase order number.")
    # Lock the tenant row to serialize number generation for this tenant.
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    last = PurchaseOrder.objects.select_for_update().filter(tenant=tenant, order_number__startswith="PO-").order_by("-id").first()
    if not last or not last.order_number:
        return "PO-000001"
    try:
        number = int(last.order_number.replace("PO-", "")) + 1
    except (ValueError, AttributeError):
        number = PurchaseOrder.objects.filter(tenant=tenant).count() + 1
    return f"PO-{number:06d}"


# Backward-compatible alias for callers that already hold a transaction
def generate_purchase_order_number_legacy():
    # Legacy global fallback - deprecated, do not use in new code
    last = PurchaseOrder.objects.order_by("-id").first()
    if not last:
        return "PO-000001"
    number = int(last.order_number.replace("PO-", "")) + 1
    return f"PO-{number:06d}"
