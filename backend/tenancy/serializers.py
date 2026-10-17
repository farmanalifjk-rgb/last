from rest_framework import serializers
from .models import Tenant, Branch, UserTenantMembership, TenantSetting, BranchSetting


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id","name","code","contact_email","contact_phone","address","logo_url","is_active","created_at"]


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "tenant", "name", "code", "address", "phone", "is_active", "created_at"]


class UserTenantMembershipSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    class Meta:
        model = UserTenantMembership
        fields = ["id","user","user_name","tenant","tenant_name","branch","branch_name","role","is_active","created_at"]


class TenantSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSetting
        fields = ["id","tenant","key","value","is_json","updated_at"]


class BranchSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BranchSetting
        fields = ["id","branch","key","value","is_json","updated_at"]