from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assert_receipt_lines_are_unambiguous(apps, schema_editor):
    GoodsReceiptLine = apps.get_model("suppliers", "GoodsReceiptLine")
    if GoodsReceiptLine.objects.filter(purchase_order_item__isnull=True).exists():
        raise RuntimeError("Existing receipt lines without a purchase-order line must be reconciled before canonicalization.")


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0006_alter_bundlecomponent_product_and_more"),
        ("pos", "0012_canonical_purchasing_model"),
        ("suppliers", "0003_alter_goodsreceipt_tenant_and_more"),
    ]

    operations = [
        migrations.AlterField(model_name="goodsreceipt", name="receipt_number", field=models.CharField(blank=True, max_length=30, null=True, unique=True)),
        migrations.AlterField(model_name="purchasereturn", name="return_number", field=models.CharField(blank=True, max_length=30, null=True, unique=True)),
        migrations.AddField(model_name="purchasereturn", name="processed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="purchasereturn", name="processed_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="processed_supplier_returns", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="goodsreceiptline", name="batch", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="receipt_lines", to="catalog.batch")),
        migrations.AlterField(model_name="goodsreceiptline", name="purchase_order_item", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="receipt_lines", to="pos.purchaseorderitem")),
        migrations.RunPython(assert_receipt_lines_are_unambiguous, migrations.RunPython.noop),
        migrations.AlterField(model_name="goodsreceiptline", name="purchase_order_item", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="receipt_lines", to="pos.purchaseorderitem")),
        migrations.RemoveField(model_name="goodsreceiptline", name="product"),
        migrations.RemoveField(model_name="goodsreceiptline", name="batch_number"),
        migrations.RemoveField(model_name="goodsreceiptline", name="expiry_date"),
        migrations.AddField(model_name="purchasereturnline", name="purchase_order_item", field=models.ForeignKey(default=None, on_delete=django.db.models.deletion.PROTECT, related_name="return_lines", to="pos.purchaseorderitem"), preserve_default=False),
        migrations.AddField(model_name="purchasereturnline", name="receipt_line", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="return_lines", to="suppliers.goodsreceiptline")),
        migrations.RemoveField(model_name="purchasereturnline", name="product"),
        migrations.AddConstraint(model_name="suppliercontact", constraint=models.UniqueConstraint(condition=models.Q(is_primary=True), fields=("supplier",), name="one_primary_contact_per_supplier")),
        migrations.AddConstraint(model_name="goodsreceiptline", constraint=models.CheckConstraint(condition=models.Q(quantity_received__gt=0), name="receipt_line_received_positive")),
        migrations.AddConstraint(model_name="goodsreceiptline", constraint=models.CheckConstraint(condition=models.Q(quantity_accepted__gte=0), name="receipt_line_accepted_nonnegative")),
        migrations.AddConstraint(model_name="goodsreceiptline", constraint=models.CheckConstraint(condition=models.Q(quantity_rejected__gte=0), name="receipt_line_rejected_nonnegative")),
        migrations.AddConstraint(model_name="purchasereturnline", constraint=models.CheckConstraint(condition=models.Q(quantity__gt=0), name="purchase_return_line_quantity_positive")),
    ]
