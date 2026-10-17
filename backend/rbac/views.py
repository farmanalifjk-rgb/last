from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from saas.permissions import HasActiveTenant, PlatformRBACPermission, TenantRBACPermission
from saas.services import get_active_tenant_for_user
from saas.models import TenantMembership

from .models import Module, Permission, Role, UserRole, RoleTemplate, PermissionOverride
from .serializers import (ModuleSerializer, PermissionSerializer, RoleSerializer,
                          UserRoleSerializer, RoleTemplateSerializer, PermissionOverrideSerializer,
                          GovernanceRoleSerializer, GovernanceAssignmentSerializer)
from .checker import user_permissions, apply_template_to_role, seed_modules_and_permissions
from .governance import (
    require_tenant_governance, tenant_roles, tenant_permissions,
    create_tenant_role, update_tenant_role, deactivate_tenant_role,
    assign_tenant_role, remove_tenant_role_assignment, effective_permissions,
)


class ModuleListView(generics.ListAPIView):
    serializer_class = ModuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Module.objects.filter(is_active=True)


class PermissionListView(generics.ListAPIView):
    serializer_class = PermissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Permission.objects.select_related("module").all()


class RoleListCreateView(generics.ListCreateAPIView):
    serializer_class = RoleSerializer
    permission_classes = [permissions.IsAuthenticated, PlatformRBACPermission]
    rbac_module = "rbac"
    rbac_action = "manage"
    queryset = Role.objects.prefetch_related("permissions__module").all()


class RoleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoleSerializer
    permission_classes = [permissions.IsAuthenticated, PlatformRBACPermission]
    rbac_module = "rbac"
    rbac_action = "manage"
    queryset = Role.objects.prefetch_related("permissions__module").all()

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.is_system:
            return Response({"detail": "System roles cannot be deleted."}, status=400)
        return super().destroy(request, *args, **kwargs)


class UserRoleListCreateView(generics.ListCreateAPIView):
    serializer_class = UserRoleSerializer
    permission_classes = [permissions.IsAuthenticated, PlatformRBACPermission]
    rbac_module = "rbac"
    rbac_action = "manage"
    queryset = UserRole.objects.select_related("user", "role", "assigned_by").all()


class UserRoleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserRoleSerializer
    permission_classes = [permissions.IsAuthenticated, PlatformRBACPermission]
    rbac_module = "rbac"
    rbac_action = "manage"
    queryset = UserRole.objects.select_related("user", "role", "assigned_by").all()


class RoleTemplateListCreateView(generics.ListCreateAPIView):
    serializer_class = RoleTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, PlatformRBACPermission]
    rbac_module = "rbac"
    rbac_action = "manage"
    queryset = RoleTemplate.objects.all()


class ApplyTemplateView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "rbac"
    rbac_action = "manage"
    def post(self, request, role_id):
        role = get_object_or_404(Role, pk=role_id, tenant=request.tenant)
        template = get_object_or_404(RoleTemplate, pk=request.data["template_id"])
        added = apply_template_to_role(role, template)
        return Response({"added": added}, status=200)


class PermissionOverrideListCreateView(generics.ListCreateAPIView):
    serializer_class = PermissionOverrideSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        HasActiveTenant,
        TenantRBACPermission,
    ]
    rbac_module = "rbac"
    rbac_action = "manage"

    def get_queryset(self):
        return PermissionOverride.objects.filter(
            tenant=self.request.tenant
        ).select_related(
            "permission",
            "permission__module",
        )

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class MyPermissionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        # Permission visibility is a token-authentication UX hint, but it must
        # use the same principal-derived tenant resolution as protected SaaS
        # views. A stale Django session can otherwise suppress an owner/admin's
        # effective permissions after a token-authenticated login.
        tenant = get_active_tenant_for_user(request.user)
        membership = TenantMembership.objects.filter(
            tenant=tenant,
            user=request.user,
            is_active_in_tenant=True,
        ).first() if tenant else None
        if request.user.is_superuser or membership and membership.role in {
            TenantMembership.ROLE_OWNER,
            TenantMembership.ROLE_ADMIN,
        }:
            permissions = {"*.*"}
        else:
            permissions = user_permissions(request.user, tenant=tenant)
        return Response({"permissions": sorted(permissions)})


class CheckPermissionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        from .checker import has_permission
        tenant = get_active_tenant_for_user(request.user)
        module = request.query_params.get("module")
        action = request.query_params.get("action")
        return Response({"allowed": has_permission(request.user, module, action, tenant=tenant)})


class TenantGovernanceBase(APIView):
    permission_classes = [
    permissions.IsAuthenticated,
    HasActiveTenant,
    TenantRBACPermission,
]

    @property
    def tenant(self):
        return self.request.tenant

    def require_governance(self):
        return require_tenant_governance(actor=self.request.user, tenant=self.tenant)


class TenantGovernanceRoleListView(TenantGovernanceBase):
    def get(self, request):
        self.require_governance()
        return Response(GovernanceRoleSerializer(tenant_roles(tenant=self.tenant), many=True).data)

    def post(self, request):
        self.require_governance()
        role = create_tenant_role(
            actor=request.user, tenant=self.tenant,
            key=request.data.get("key"), label=request.data.get("label"),
            description=request.data.get("description", ""),
            permission_ids=request.data.get("permission_ids", []),
            confirm_sensitive=bool(request.data.get("confirm_sensitive")), request=request,
        )
        return Response(GovernanceRoleSerializer(role).data, status=status.HTTP_201_CREATED)


class TenantGovernanceRoleDetailView(TenantGovernanceBase):
    def _role(self, pk):
        return get_object_or_404(Role.objects.prefetch_related("permissions__module"), pk=pk)

    def get(self, request, pk):
        self.require_governance()
        role = self._role(pk)
        if role.scope != Permission.SCOPE_TENANT or role.tenant_id not in {None, self.tenant.id}:
            raise PermissionDenied("The role does not belong to the active tenant.")
        return Response(GovernanceRoleSerializer(role).data)

    def patch(self, request, pk):
        self.require_governance()
        role = update_tenant_role(
            actor=request.user, tenant=self.tenant, role=self._role(pk),
            label=request.data.get("label"), description=request.data.get("description", ""),
            permission_ids=request.data.get("permission_ids", []),
            confirm_sensitive=bool(request.data.get("confirm_sensitive")), request=request,
        )
        return Response(GovernanceRoleSerializer(role).data)

    def delete(self, request, pk):
        self.require_governance()
        deactivate_tenant_role(actor=request.user, tenant=self.tenant, role=self._role(pk), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TenantGovernancePermissionListView(TenantGovernanceBase):
    def get(self, request):
        self.require_governance()
        return Response(PermissionSerializer(tenant_permissions(), many=True).data)


class TenantGovernanceMemberListView(TenantGovernanceBase):
    def get(self, request):
        self.require_governance()
        memberships = TenantMembership.objects.filter(tenant=self.tenant).select_related("user").order_by("user__username")
        return Response([
            {"id": row.id, "user_id": row.user_id, "username": row.user.username, "email": row.user.email,
             "membership_role": row.role, "is_active": row.is_active_in_tenant}
            for row in memberships
        ])


class TenantGovernanceAssignmentListView(TenantGovernanceBase):
    def get(self, request):
        self.require_governance()
        assignments = UserRole.objects.filter(tenant=self.tenant).select_related("user", "role", "assigned_by").order_by("user__username", "role__label")
        return Response(GovernanceAssignmentSerializer(assignments, many=True).data)

    def post(self, request):
        self.require_governance()
        target = get_object_or_404(TenantMembership.objects.select_related("user"), tenant=self.tenant, user_id=request.data.get("user")).user
        role = get_object_or_404(Role, pk=request.data.get("role"))
        assignment = assign_tenant_role(actor=request.user, tenant=self.tenant, target_user=target, role=role, branch=None, request=request)
        return Response(GovernanceAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class TenantGovernanceAssignmentDetailView(TenantGovernanceBase):
    def delete(self, request, pk):
        self.require_governance()
        assignment = get_object_or_404(UserRole.objects.select_related("user", "role"), pk=pk)
        remove_tenant_role_assignment(actor=request.user, tenant=self.tenant, assignment=assignment, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TenantGovernanceEffectivePermissionView(TenantGovernanceBase):
    def get(self, request, user_id):
        self.require_governance()
        user = get_object_or_404(TenantMembership.objects.select_related("user"), tenant=self.tenant, user_id=user_id).user
        return Response(effective_permissions(user=user, tenant=self.tenant))


class SeedView(APIView):
    permission_classes = [permissions.IsAdminUser]
    def post(self, request):
        seed_modules_and_permissions()
        return Response({"modules": Module.objects.count(),
                         "permissions": Permission.objects.count(),
                         "templates": RoleTemplate.objects.count()})
