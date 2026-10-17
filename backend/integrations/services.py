from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from pos.models import Product, Order, Customer
from .models import Integration, SyncLog, SyncMapping
from .adapters import get_adapter


SUPPORTED_PROVIDER_KINDS = {Integration.KIND_SHOPIFY, Integration.KIND_WOOCOMMERCE}


def _require_operational_integration(integration):
    """Reject inactive and not-implemented configurations before side effects."""
    if not integration.is_active:
        raise ValueError("Integration is inactive.")
    if integration.kind not in SUPPORTED_PROVIDER_KINDS:
        raise ValueError(f"Integration kind '{integration.kind}' is not implemented.")
    return integration


@transaction.atomic

def _log(integration, direction, entity_type, local_id, remote_id, status, message="", payload=None):
    log = SyncLog(
        tenant=integration.tenant,
        integration=integration,
        direction=direction,
        entity_type=entity_type,
        entity_id=local_id or "",
        remote_id=remote_id or "",
        status=status,
        message=message,
        payload=payload or {},
    )
    log.full_clean()
    log.save()
    return log


def sync_products_inbound(integration):
    integration = _require_operational_integration(integration)
    adapter = get_adapter(integration)

    created, updated, failed = 0, 0, 0
    try:
        remote_products = adapter.fetch_products()
    except Exception as e:
        _log(integration, SyncLog.DIRECTION_INBOUND, "product", "", "", SyncLog.STATUS_FAILED, str(e))
        return {"created": 0, "updated": 0, "failed": 1, "error": str(e)}
    for rp in remote_products:
        try:
            mapping = SyncMapping.objects.filter(tenant=integration.tenant, integration=integration, entity_type="product",
                                                 remote_id=rp["remote_id"]).first()
            if mapping:
                p = Product.objects.filter(tenant=integration.tenant, id=mapping.local_id).first()
                if p:
                    p.name = rp["name"]
                    p.sku = rp.get("sku") or p.sku
                    p.sales_price = rp.get("price", p.sales_price)
                    p.save()
                    updated += 1
                else:
                    continue
            else:
                p = Product.objects.create(tenant=integration.tenant, name=rp["name"], sku=rp.get("sku") or f"EXT-{rp['remote_id']}",
                                           sales_price=rp.get("price", 0), cost_price=0)
                SyncMapping.objects.create(tenant=integration.tenant, integration=integration, entity_type="product",
                                           local_id=str(p.id), remote_id=rp["remote_id"],
                                           last_hash=adapter._hash(rp))
                created += 1
        except Exception as e:
            failed += 1
            _log(integration, SyncLog.DIRECTION_INBOUND, "product", "", rp.get("remote_id", ""),
                 SyncLog.STATUS_FAILED, str(e))
    integration.last_synced_at = timezone.now()
    integration.save(update_fields=["last_synced_at"])
    return {"created": created, "updated": updated, "failed": failed}


def sync_products_outbound(integration):
    integration = _require_operational_integration(integration)
    adapter = get_adapter(integration)

    pushed, skipped, failed = 0, 0, 0
    for p in Product.objects.filter(tenant=integration.tenant, is_active=True).iterator():
        mapping = SyncMapping.objects.filter(tenant=integration.tenant, integration=integration, entity_type="product",
                                             local_id=str(p.id)).first()
        data = {"name": p.name, "sku": p.sku, "price": str(p.sales_price)}
        new_hash = adapter._hash(data)
        if mapping and mapping.last_hash == new_hash:
            skipped += 1
            continue
        try:
            remote_id = adapter.push_product(data)
            if mapping:
                mapping.remote_id = remote_id
                mapping.last_hash = new_hash
                mapping.save()
            else:
                SyncMapping.objects.create(tenant=integration.tenant, integration=integration, entity_type="product",
                                           local_id=str(p.id), remote_id=remote_id, last_hash=new_hash)
            pushed += 1
        except Exception as e:
            failed += 1
            _log(integration, SyncLog.DIRECTION_OUTBOUND, "product", str(p.id), "",
                 SyncLog.STATUS_FAILED, str(e))
    integration.last_synced_at = timezone.now()
    integration.save(update_fields=["last_synced_at"])
    return {"pushed": pushed, "skipped": skipped, "failed": failed}


def sync_orders_inbound(integration, since=None):
    _require_operational_integration(integration)
    # Imported orders cannot safely enter a POS ledger without a canonical
    # session, tenders, tax and inventory allocations. Keep this disabled until
    # a dedicated external-order import workflow exists.
    raise ValueError("Inbound order sync is unavailable until canonical order import is implemented.")


def push_invoice(integration, invoice_data):
    integration = _require_operational_integration(integration)
    adapter = get_adapter(integration)

    try:
        remote_id = adapter.push_invoice(invoice_data)
        _log(integration, SyncLog.DIRECTION_OUTBOUND, "invoice",
             invoice_data.get("invoice_number", ""), remote_id, SyncLog.STATUS_SUCCESS)
        return remote_id
    except Exception as e:
        _log(integration, SyncLog.DIRECTION_OUTBOUND, "invoice",
             invoice_data.get("invoice_number", ""), "", SyncLog.STATUS_FAILED, str(e))
        raise


def run_sync(*, tenant, integration_id, direction="inbound", entity_type="product"):
    integration = Integration.objects.get(tenant=tenant, pk=integration_id)
    if entity_type == "product":
        return sync_products_inbound(integration) if direction == "inbound" else sync_products_outbound(integration)
    elif entity_type == "order":
        return sync_orders_inbound(integration)
    else:
        raise ValueError(f"Unknown entity_type {entity_type}")
