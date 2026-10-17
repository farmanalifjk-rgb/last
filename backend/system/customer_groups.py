from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin

from .models import CustomerGroup


class CustomerGroupTenantSerializer(serializers.ModelSerializer):
    customers_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomerGroup
        fields = ["id", "tenant", "name", "description", "discount_percent", "is_active", "created_at", "customers_count"]
        read_only_fields = ["id", "tenant", "created_at", "customers_count"]

    def get_customers_count(self, obj):
        return obj.customers.count()

    def validate_name(self, value):
        # The database enforces uniqueness per tenant; report it as a validation error instead of a 500.
        tenant = self.context["request"].tenant
        duplicates = CustomerGroup.objects.filter(tenant=tenant, name=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("A customer group with this name already exists.")
        return value


class CustomerGroupViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """System-owned group records exposed through the Customer workflow safely."""
    rbac_module = "customers"
    queryset = CustomerGroup.objects.all()
    serializer_class = CustomerGroupTenantSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        if search := self.request.query_params.get("search", "").strip():
            from django.db.models import Q
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if active := self.request.query_params.get("is_active"):
            queryset = queryset.filter(is_active=active.lower() == "true")
        return queryset
