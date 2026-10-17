from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0002_initial"),
        ("saas", "0004_manual_billing"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiquery",
            name="tenant",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="ai_queries", to="saas.tenant"),
        ),
        migrations.AddField(
            model_name="reordersuggestion",
            name="tenant",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="ai_reorder_suggestions", to="saas.tenant"),
        ),
        migrations.AddField(
            model_name="prompttemplate",
            name="tenant",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="ai_prompt_templates", to="saas.tenant"),
        ),
        migrations.AlterField(
            model_name="prompttemplate",
            name="kind",
            field=models.CharField(choices=[("sales_query", "Sales query"), ("reorder", "Reorder"), ("summary", "Summary")], max_length=20),
        ),
        migrations.AddConstraint(
            model_name="prompttemplate",
            constraint=models.UniqueConstraint(fields=("tenant", "kind"), name="ai_unique_template_kind_per_tenant"),
        ),
    ]
