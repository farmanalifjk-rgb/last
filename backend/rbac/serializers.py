from rest_framework import serializers
from .models import Module, Permission, Role, UserRole, RoleTemplate, PermissionOverride


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ["id","key","label","is_active","created_at"]


class PermissionSerializer(serializers.ModelSerializer):
    module_key = serializers.CharField(source="module.key", read_only=True)
    class Meta:
        model = Permission
        fields = ["id","module","module_key","action","description","scope","risk_level","access_kind","is_sensitive","created_at"]


class RoleSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=Permission.objects.all(), source="permissions", required=False)
    class Meta:
        model = Role
        fields = ["id","key","label","description","is_system","is_active","scope","tenant","created_at","permissions","permission_ids"]


class UserRoleSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    role_label = serializers.CharField(source="role.label", read_only=True)
    class Meta:
        model = UserRole
        fields = ["id","user","user_name","role","role_label","tenant","branch","is_active","assigned_by","created_at"]


class RoleTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleTemplate
        fields = ["id","key","label","description","permission_keys","created_at"]


class PermissionOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermissionOverride
        fields = ["id", "user", "permission", "tenant", "decision", "created_at"]
        read_only_fields = ["id", "tenant", "created_at"]

    def validate(self, attrs):
        request = self.context["request"]
        tenant = getattr(request, "tenant", None)

        if tenant is None:
            raise serializers.ValidationError(
                {"tenant": "An active tenant is required."}
            )

        user = attrs.get("user")
        permission = attrs.get("permission")

        if user is None:
            raise serializers.ValidationError(
                {"user": "A target user is required."}
            )

        if permission is None:
            raise serializers.ValidationError(
                {"permission": "A permission is required."}
            )

        if permission.scope != Permission.SCOPE_TENANT:
            raise serializers.ValidationError(
                {"permission": "Platform permissions cannot be overridden from a tenant."}
            )

        from saas.models import TenantMembership

        if not TenantMembership.objects.filter(
            tenant=tenant,
            user=user,
            is_active_in_tenant=True,
        ).exists():
            raise serializers.ValidationError(
                {"user": "The target user is not an active member of this tenant."}
            )

        return attrs


class GovernanceRoleSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=Permission.objects.all(), required=False, source="permissions"
    )

    class Meta:
        model = Role
        fields = ["id", "key", "label", "description", "is_system", "is_active", "scope", "tenant", "created_at", "permissions", "permission_ids"]


class GovernanceAssignmentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    role_label = serializers.CharField(source="role.label", read_only=True)
    role_key = serializers.CharField(source="role.key", read_only=True)

    class Meta:
        model = UserRole
        fields = ["id", "user", "role", "tenant", "branch", "is_active", "assigned_by", "created_at", "user_name", "role_label", "role_key"]
        read_only_fields = ["id", "user_name", "role_label", "role_key", "created_at"]
