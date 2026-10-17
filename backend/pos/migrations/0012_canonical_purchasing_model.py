from django.db import migrations, models
import django.db.models.deletion


def assert_purchase_orders_have_no_warehouse_gaps(apps, schema_editor):
    PurchaseOrder = apps.get_model("pos", "PurchaseOrder")
    if PurchaseOrder.objects.filter(warehouse__isnull=True).exists():
        raise RuntimeError("Existing purchase orders require an explicit warehouse before the canonical purchasing migration can complete.")


class Migration(migrations.Migration):
    dependencies = [
        ("enterprise", "0005_alter_warehouse_code_and_more"),
        ("pos", "0011_alter_customer_options_customer_created_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="warehouse",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_orders", to="enterprise.warehouse"),
        ),
        migrations.AddField(model_name="purchaseorder", name="expected_date", field=models.DateField(blank=True, null=True)),
        migrations.AlterField(model_name="purchaseorder", name="order_number", field=models.CharField(blank=True, max_length=30, null=True, unique=True)),
        migrations.AlterField(model_name="purchaseorderitem", name="quantity", field=models.DecimalField(decimal_places=2, max_digits=14)),
        migrations.AlterField(model_name="purchaseorderitem", name="received_quantity", field=models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.AlterField(model_name="purchaseorderitem", name="returned_quantity", field=models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.RunPython(assert_purchase_orders_have_no_warehouse_gaps, migrations.RunPython.noop),
        migrations.AlterField(model_name="purchaseorder", name="warehouse", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_orders", to="enterprise.warehouse")),
        migrations.DeleteModel(name="PurchaseReturnItem"),
        migrations.DeleteModel(name="PurchaseReturn"),
    ]
