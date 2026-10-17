from decimal import Decimal

from rest_framework import serializers

from loyalty.models import LoyaltyTransaction
from pos.models import Customer
from system.models import CustomerGroup

from .models import CustomerAddress, CustomerCreditLimit, CustomerDocument, CustomerNote


class TenantRelationSerializer(serializers.ModelSerializer):
    def tenant(self):
        return self.context["request"].tenant

    def require_tenant(self, value, field):
        if value is not None and getattr(value, "tenant_id", None) != self.tenant().id:
            raise serializers.ValidationError({field: "The selected record does not belong to the active tenant."})
        return value


class CustomerListSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True, default="")
    order_count = serializers.IntegerField(read_only=True)
    total_spent = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    last_purchase = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Customer
        fields = ["id", "tenant", "name", "phone", "email", "customer_code", "is_active", "created_at", "updated_at", "group", "group_name", "loyalty_points", "order_count", "total_spent", "last_purchase"]
        read_only_fields = ["id", "tenant", "customer_code", "created_at", "updated_at", "loyalty_points"]


class CustomerWriteSerializer(TenantRelationSerializer):
    group = serializers.PrimaryKeyRelatedField(queryset=CustomerGroup.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Customer
        fields = ["id", "tenant", "name", "phone", "email", "address", "customer_code", "is_active", "created_at", "updated_at", "group", "loyalty_points", "date_of_birth"]
        read_only_fields = ["id", "tenant", "customer_code", "loyalty_points", "created_at", "updated_at"]

    def validate_group(self, value):
        return self.require_tenant(value, "group")

    def validate(self, attrs):
        attrs["name"] = (attrs.get("name") or getattr(self.instance, "name", "")).strip()
        if not attrs["name"]:
            raise serializers.ValidationError({"name": "Customer name is required."})
        if "email" in attrs:
            attrs["email"] = attrs["email"].strip().lower()
        if "phone" in attrs:
            attrs["phone"] = attrs["phone"].strip()
        if "customer_code" in attrs:
            attrs["customer_code"] = attrs["customer_code"].strip().upper()
        tenant = self.tenant()
        instance_id = self.instance.id if self.instance else None
        duplicate_fields = [("email", attrs.get("email")), ("phone", attrs.get("phone")), ("customer_code", attrs.get("customer_code"))]
        errors = {}
        for field, value in duplicate_fields:
            if not value:
                continue
            queryset = Customer.objects.filter(tenant=tenant, **{field: value})
            if instance_id:
                queryset = queryset.exclude(pk=instance_id)
            if queryset.exists():
                errors[field] = f"A customer with this {field.replace('_', ' ')} already exists in the active tenant."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class CustomerDetailSerializer(CustomerListSerializer):
    address = serializers.CharField(read_only=True)
    date_of_birth = serializers.DateField(read_only=True)

    class Meta(CustomerListSerializer.Meta):
        fields = CustomerListSerializer.Meta.fields + ["address", "date_of_birth"]


class CustomerAddressSerializer(TenantRelationSerializer):
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = CustomerAddress
        fields = ["id", "tenant", "customer", "customer_name", "kind", "label", "line1", "line2", "city", "state", "postal_code", "country", "phone", "is_default", "created_at"]
        read_only_fields = ["id", "tenant", "customer", "customer_name", "created_at"]


class CustomerCreditLimitSerializer(serializers.ModelSerializer):
    available = serializers.SerializerMethodField()

    class Meta:
        model = CustomerCreditLimit
        fields = ["id", "customer", "limit", "used", "available", "terms_days", "is_active", "updated_at"]
        read_only_fields = ["id", "customer", "used", "available", "updated_at"]

    def get_available(self, obj):
        return str(max(Decimal("0"), Decimal(obj.limit) - Decimal(obj.used)))


class CustomerDocumentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, required=False)
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    uploaded_by_name = serializers.CharField(source="uploaded_by.username", read_only=True, default="")
    download_url = serializers.SerializerMethodField()
    max_upload_bytes = 10 * 1024 * 1024

    class Meta:
        model = CustomerDocument
        fields = ["id", "tenant", "customer", "kind", "file", "name", "notes", "uploaded_at", "uploaded_by", "uploaded_by_name", "download_url"]
        read_only_fields = ["id", "tenant", "customer", "kind", "file", "name", "notes", "uploaded_at", "uploaded_by"]

    def validate_file(self, value):
        if value.size > self.max_upload_bytes:
            raise serializers.ValidationError("Customer documents must not exceed 10 MB.")
        return value

    def get_download_url(self, obj):
        return f"/api/customer-documents/{obj.id}/download/"


class CustomerNoteSerializer(serializers.ModelSerializer):
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default="")

    class Meta:
        model = CustomerNote
        fields = ["id", "customer", "body", "pinned", "created_at", "created_by", "created_by_name"]
        read_only_fields = ["id", "customer", "created_at", "created_by", "created_by_name"]


class CustomerLoyaltyTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltyTransaction
        fields = ["id", "tenant", "customer", "type", "points", "reference", "reason", "created_at"]
        read_only_fields = fields
