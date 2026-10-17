from rest_framework import serializers

from .models import AIQuery, PromptTemplate, ReorderSuggestion


class AIQuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = AIQuery
        fields = ("id", "question", "answer", "data", "model", "tokens_used", "created_at")
        read_only_fields = fields


class ReorderSuggestionSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = ReorderSuggestion
        fields = (
            "id", "product", "product_name", "product_sku", "suggested_qty",
            "current_stock", "avg_daily_sales", "days_of_stock", "lead_time_days",
            "confidence", "rationale", "status", "created_at",
        )
        read_only_fields = (
            "id", "product", "product_name", "product_sku", "suggested_qty",
            "current_stock", "avg_daily_sales", "days_of_stock", "lead_time_days",
            "confidence", "rationale", "created_at",
        )


class PromptTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptTemplate
        fields = ("id", "kind", "template", "response_json_schema", "model", "is_active", "updated_at")
        read_only_fields = ("id", "updated_at")
