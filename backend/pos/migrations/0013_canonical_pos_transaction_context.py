from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("enterprise", "0005_alter_warehouse_code_and_more"),
        ("pos", "0012_canonical_purchasing_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="cashsession",
            name="warehouse",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="pos_cash_sessions", to="enterprise.warehouse"),
        ),
        migrations.AddField(
            model_name="cashtransaction",
            name="created_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="cash_transactions", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="order",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="warehouse",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="pos_orders", to="enterprise.warehouse"),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(condition=models.Q(("idempotency_key__isnull", False), ("idempotency_key", ""), _connector="AND", _negated=True), fields=("tenant", "idempotency_key"), name="unique_pos_checkout_idempotency_per_tenant"),
        ),
    ]
