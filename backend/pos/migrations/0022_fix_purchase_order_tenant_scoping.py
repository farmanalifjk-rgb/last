# Generated for Phase 1 critical fix: tenant-scoped PO numbers + race-free generator
from django.db import migrations, models


def backfill_purchase_order_tenant(apps, schema_editor):
    PurchaseOrder = apps.get_model("pos", "PurchaseOrder")
    Supplier = apps.get_model("pos", "Supplier")
    # Backfill any tenantless purchase orders from their supplier's tenant
    for po in PurchaseOrder.objects.filter(tenant__isnull=True).select_related("supplier"):
        if po.supplier_id and getattr(po.supplier, "tenant_id", None):
            po.tenant_id = po.supplier.tenant_id
            po.save(update_fields=["tenant"])
    # Backfill tenantless items from parent order
    PurchaseOrderItem = apps.get_model("pos", "PurchaseOrderItem")
    for item in PurchaseOrderItem.objects.filter(tenant__isnull=True).select_related("purchase_order"):
        if getattr(item.purchase_order, "tenant_id", None):
            item.tenant_id = item.purchase_order.tenant_id
            item.save(update_fields=["tenant"])


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0021_order_idempotency_request_hash"),
        ("enterprise", "0005_alter_warehouse_code_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_purchase_order_tenant, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="purchaseorder",
            name="order_number",
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddConstraint(
            model_name="purchaseorder",
            constraint=models.UniqueConstraint(fields=("tenant", "order_number"), name="unique_purchase_order_number_per_tenant"),
        ),
    ]
