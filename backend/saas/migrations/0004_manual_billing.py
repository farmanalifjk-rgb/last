from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_manual_payment_methods(apps, schema_editor):
    ManualPaymentMethod = apps.get_model("saas", "ManualPaymentMethod")
    for code, label, reference_required, sort_order in (
        ("cash", "Cash", False, 10),
        ("bank-transfer", "Bank transfer", True, 20),
        ("direct-deposit", "Direct deposit", True, 30),
    ):
        ManualPaymentMethod.objects.get_or_create(
            code=code,
            defaults={
                "label": label,
                "reference_required": reference_required,
                "is_active": True,
                "sort_order": sort_order,
            },
        )


def unseed_manual_payment_methods(apps, schema_editor):
    ManualPaymentMethod = apps.get_model("saas", "ManualPaymentMethod")
    ManualPaymentMethod.objects.filter(code__in=["cash", "bank-transfer", "direct-deposit"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("saas", "0003_phase11_plan_entitlements"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ManualPaymentMethod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=40, unique=True)),
                ("label", models.CharField(max_length=100)),
                ("reference_required", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["sort_order", "label"]},
        ),
        migrations.CreateModel(
            name="SubscriptionRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("expected_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("expected_currency", models.CharField(max_length=10)),
                ("period_start", models.DateTimeField()),
                ("period_end", models.DateTimeField()),
                ("status", models.CharField(choices=[("awaiting_payment", "Awaiting payment"), ("payment_submitted", "Payment submitted"), ("activated", "Activated"), ("rejected", "Rejected"), ("cancelled", "Cancelled")], default="awaiting_payment", max_length=24)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("activated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="activated_subscription_requests", to=settings.AUTH_USER_MODEL)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscription_requests", to="saas.subscriptionplan")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscription_requests", to=settings.AUTH_USER_MODEL)),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requests", to="saas.subscription")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subscription_requests", to="saas.tenant")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ManualSubscriptionPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("paid_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("paid_currency", models.CharField(max_length=10)),
                ("payment_reference", models.CharField(blank=True, max_length=160)),
                ("payment_date", models.DateField()),
                ("proof_reference", models.CharField(blank=True, max_length=240)),
                ("notes", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("submitted", "Submitted"), ("verified", "Verified"), ("rejected", "Rejected"), ("cancelled", "Cancelled")], default="submitted", max_length=20)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True)),
                ("review_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("payment_method", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="manual_subscription_payments", to="saas.manualpaymentmethod")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="manual_subscription_payments", to="saas.subscriptionplan")),
                ("submitted_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="submitted_manual_subscription_payments", to=settings.AUTH_USER_MODEL)),
                ("subscription_request", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="manual_payment", to="saas.subscriptionrequest")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="manual_subscription_payments", to="saas.tenant")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="verified_manual_subscription_payments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-submitted_at"]},
        ),
        migrations.AddField(
            model_name="invoice",
            name="finalized_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="invoice",
            name="period_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="invoice",
            name="period_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="invoice",
            name="manual_payment",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoice", to="saas.manualsubscriptionpayment"),
        ),
        migrations.AddField(
            model_name="invoice",
            name="subscription_request",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoice", to="saas.subscriptionrequest"),
        ),
        migrations.AddConstraint(
            model_name="subscriptionrequest",
            constraint=models.UniqueConstraint(condition=models.Q(("status__in", ["awaiting_payment", "payment_submitted"])), fields=("tenant",), name="saas_one_open_subscription_request_per_tenant"),
        ),
        migrations.AddConstraint(
            model_name="manualsubscriptionpayment",
            constraint=models.UniqueConstraint(condition=~models.Q(("payment_reference", "")), fields=("payment_method", "payment_reference"), name="saas_unique_manual_payment_reference_by_method"),
        ),
        migrations.RunPython(seed_manual_payment_methods, unseed_manual_payment_methods),
    ]
