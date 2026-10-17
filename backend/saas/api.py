from rest_framework import permissions
from rest_framework.views import APIView

from .permissions import HasActiveTenant, TenantRBACPermission


class TenantAPIView(APIView):
    """
    Base class for every tenant-owned API endpoint.

    Guarantees:
    - The user is authenticated.
    - The user has an active tenant.
    - Tenant RBAC is checked.
    - request.tenant is available to the view.
    """

    permission_classes = [
        permissions.IsAuthenticated,
        HasActiveTenant,
        TenantRBACPermission,
    ]

    rbac_module = None
    rbac_action = None