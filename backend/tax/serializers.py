from decimal import Decimal

from rest_framework import serializers

from .models import ProductTaxAssignment, TaxBreakdown, TaxExemption, TaxRate, TaxReport


class TenantTaxRelationSerializer(serializers.ModelSerializer):
    def _tenant_record(self, value, field):
        tenant = self.context["request"].tenant
        if value is not None and getattr(value, "tenant_id", None) != tenant.id:
            raise serializers.ValidationError({field: "The selected record does not belong to the active tenant."})
        return value


class TaxRateSerializer(TenantTaxRelationSerializer):
    # Contract: API/database rates are decimal fractions (0.1700 means 17%).
    # The UI may display percentage points, but converts them to this value.
    rate = serializers.DecimalField(
        max_digits=6, decimal_places=4, min_value=Decimal("0"), max_value=Decimal("1"),
        help_text="Decimal fraction: 0.1700 means 17%. Do not send 17 for 17%.",
    )

    class Meta:
        model = TaxRate
        fields = ["id","tenant","name","code","rate","mode","compound_style","is_active","priority","applies_to_all","category","product","created_at"]
        read_only_fields = ["tenant", "created_at"]

    def validate_product(self, value):
        return self._tenant_record(value, "product")

    def validate_category(self, value):
        return self._tenant_record(value, "category")

    def validate_code(self, value):
        # The database enforces uniqueness per tenant; report it as a validation error instead of a 500.
        tenant = self.context["request"].tenant
        duplicates = TaxRate.objects.filter(tenant=tenant, code=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("A tax rate with this code already exists.")
        return value


class TaxExemptionSerializer(TenantTaxRelationSerializer):
    class Meta:
        model = TaxExemption
        fields = ["id","tenant","scope","customer","product","category","tax_rate","reason","certificate_number","is_active","created_at"]
        read_only_fields = ["tenant", "created_at"]

    def validate_customer(self, value):
        return self._tenant_record(value, "customer")

    def validate_product(self, value):
        return self._tenant_record(value, "product")

    def validate_category(self, value):
        return self._tenant_record(value, "category")

    def validate(self, attrs):
        # The chosen scope needs its own target, otherwise the exemption applies to nothing.
        scope = attrs.get("scope", getattr(self.instance, "scope", None))
        if scope in ("customer", "product", "category") and attrs.get(scope, getattr(self.instance, scope, None)) is None:
            raise serializers.ValidationError({scope: f"Choose the {scope} this exemption applies to."})
        return attrs

    def validate_tax_rate(self, value):
        return self._tenant_record(value, "tax_rate")


class ProductTaxAssignmentSerializer(TenantTaxRelationSerializer):
    tax_rate_name = serializers.CharField(source="tax_rate.name", read_only=True)
    tax_rate_code = serializers.CharField(source="tax_rate.code", read_only=True)
    rate = serializers.DecimalField(source="tax_rate.rate", max_digits=6, decimal_places=4, read_only=True)
    mode = serializers.CharField(source="tax_rate.mode", read_only=True)

    class Meta:
        model = ProductTaxAssignment
        fields = ["id", "tenant", "product", "tax_rate", "tax_rate_name", "tax_rate_code", "rate", "mode", "is_active", "created_at"]
        read_only_fields = ["id", "tenant", "product", "created_at"]

    def validate_tax_rate(self, value):
        return self._tenant_record(value, "tax_rate")


class TaxBreakdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxBreakdown
        fields = ["id","tenant","order","tax_rate","tax_rate_code","rate","taxable_amount","tax_amount","mode","created_at"]
        read_only_fields = [
            "id", "tenant", "order", "tax_rate", "tax_rate_code", "rate",
            "taxable_amount", "tax_amount", "mode", "created_at",
        ]


class TaxReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxReport
        fields = ["id","tenant","period_start","period_end","total_taxable","total_tax_collected","breakdown_json","created_at"]
        read_only_fields = [
            "id", "tenant", "period_start", "period_end", "total_taxable",
            "total_tax_collected", "breakdown_json", "created_at",
        ]
