# Generated for the development-only IMS simulator ledger.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("fbr", "0007_submission_dispatched_at"),
        ("saas", "0006_phase19_bridge_legacy_tenancy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fbrconfiguration",
            name="use_simulator",
            field=models.BooleanField(default=False, help_text="Development/test only: use the isolated IMS simulator instead of a real component. The simulated number never becomes an official fiscal invoice number and receipts label it TEST / SIMULATED."),
        ),
        migrations.AddConstraint(
            model_name="fbrsubmission",
            constraint=models.UniqueConstraint(condition=models.Q(is_simulated=True) & ~models.Q(fbr_invoice_number=""), fields=("fbr_invoice_number",), name="unique_simulated_submission_number"),
        ),
        migrations.CreateModel(
            name="FBRSimulatorExchange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("environment", models.CharField(choices=[("sandbox", "Sandbox"), ("production", "Production")], default="sandbox", max_length=12)),
                ("usin", models.CharField(blank=True, max_length=64)),
                ("idempotency_key", models.CharField(max_length=80)),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("request_payload", models.JSONField(blank=True, default=dict)),
                ("response_payload", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("accepted", "Accepted (simulated)"), ("rejected", "Rejected (simulated)"), ("failed", "Failed (simulated)")], default="pending", max_length=12)),
                ("configured_outcome", models.CharField(blank=True, max_length=12)),
                ("simulated_invoice_number", models.CharField(blank=True, max_length=64)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("attempt_history", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fbr_simulator_exchanges", to="saas.tenant")),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["tenant", "created_at"], name="fbrsimex_tenant_created_idx")],
            },
        ),
        migrations.AddConstraint(
            model_name="fbrsimulatorexchange",
            constraint=models.UniqueConstraint(fields=("tenant", "environment", "idempotency_key"), name="unique_fbr_sim_exchange_usin"),
        ),
        migrations.AddConstraint(
            model_name="fbrsimulatorexchange",
            constraint=models.UniqueConstraint(condition=~models.Q(simulated_invoice_number=""), fields=("simulated_invoice_number",), name="unique_fbr_sim_invoice_number"),
        ),
    ]
