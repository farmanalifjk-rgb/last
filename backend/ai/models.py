from django.conf import settings
from django.db import models


class AIQuery(models.Model):
    """Audit log of natural-language questions + AI answers + data returned."""
    # Historical rows predate tenant attribution. They remain inaccessible until
    # explicitly remediated; all new rows are tenant-bound by the service layer.
    tenant = models.ForeignKey("saas.Tenant", null=True, blank=True, on_delete=models.CASCADE, related_name="ai_queries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    question = models.TextField()
    answer = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    model = models.CharField(max_length=60, blank=True)
    tokens_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ReorderSuggestion(models.Model):
    """AI-generated smart reorder suggestion."""
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_ORDERED = "ordered"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_APPROVED, "Approved"),
                      (STATUS_REJECTED, "Rejected"), (STATUS_ORDERED, "Ordered")]
    tenant = models.ForeignKey("saas.Tenant", null=True, blank=True, on_delete=models.CASCADE, related_name="ai_reorder_suggestions")
    product = models.ForeignKey("pos.Product", on_delete=models.CASCADE, related_name="reorder_suggestions")
    suggested_qty = models.PositiveIntegerField()
    current_stock = models.IntegerField(default=0)
    avg_daily_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    days_of_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lead_time_days = models.PositiveIntegerField(default=7)
    confidence = models.DecimalField(max_digits=4, decimal_places=2, default=0)  # 0.00–1.00
    rationale = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PromptTemplate(models.Model):
    """Reusable LLM prompt templates (sales query, reorder, summary)."""
    KIND_SALES_QUERY = "sales_query"
    KIND_REORDER = "reorder"
    KIND_SUMMARY = "summary"
    KIND_CHOICES = [(KIND_SALES_QUERY, "Sales query"), (KIND_REORDER, "Reorder"),
                    (KIND_SUMMARY, "Summary")]
    tenant = models.ForeignKey("saas.Tenant", null=True, blank=True, on_delete=models.CASCADE, related_name="ai_prompt_templates")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    template = models.TextField(help_text="Use {question} / {context} placeholders")
    response_json_schema = models.JSONField(default=dict, blank=True)
    model = models.CharField(max_length=60, blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "kind"], name="ai_unique_template_kind_per_tenant"),
        ]
