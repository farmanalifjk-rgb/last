from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        (
            "tax",
            "0004_producttaxassignment_alter_taxrate_code_and_more",
        ),
        (
            "pos",
            "0024_remove_cashsession_pos_cashsession_tenant_open_user_idx_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="taxbreakdown",
            name="order_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tax_breakdowns",
                to="pos.orderitem",
            ),
        ),
    ]