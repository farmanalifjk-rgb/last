from .purchasing_views import *  # noqa: F401,F403
from rest_framework.permissions import IsAuthenticated
from saas.permissions import HasActiveTenant, TenantRBACPermission

