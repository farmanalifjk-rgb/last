from ..serializers import CompanySerializer
from pos.models import Company
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from saas.permissions import HasActiveTenant, TenantRBACPermission


class CompanyView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "view"

    def get(self, request):
        company = Company.objects.filter(tenant=request.tenant).first()
        serializer = CompanySerializer(company)
        return Response(serializer.data)