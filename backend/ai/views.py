from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from saas.permissions import HasActiveTenant, TenantRBACPermission

from .models import AIQuery, ReorderSuggestion, PromptTemplate
from .serializers import AIQuerySerializer, ReorderSuggestionSerializer, PromptTemplateSerializer
from .services import AIServiceUnavailable, ask, daily_summary, generate_reorder_suggestions


class TenantAIView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "ai"
    rbac_action = "view"


class AskView(TenantAIView):
    rbac_action = "create"
    def post(self, request):
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"detail": "question is required"}, status=400)
        model = request.data.get("model", "automatic")
        try:
            result = ask(tenant=request.tenant, question=question, user=request.user, model=model)
        except AIServiceUnavailable as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=503)
        return Response(result)


class DailySummaryView(TenantAIView):
    def get(self, request):
        try:
            result = daily_summary(tenant=request.tenant, user=request.user)
        except AIServiceUnavailable as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=503)
        return Response(result)


class AIQueryHistoryView(generics.ListAPIView):
    serializer_class = AIQuerySerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "ai"
    rbac_action = "view"
    def get_queryset(self):
        return AIQuery.objects.filter(tenant=self.request.tenant, user=self.request.user).select_related("user")[:50]


class GenerateReorderSuggestionsView(TenantAIView):
    rbac_action = "create"
    def post(self, request):
        return Response(generate_reorder_suggestions(tenant=request.tenant))


class ReorderSuggestionListView(generics.ListAPIView):
    serializer_class = ReorderSuggestionSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "ai"
    rbac_action = "view"
    def get_queryset(self):
        qs = ReorderSuggestion.objects.filter(tenant=self.request.tenant).select_related("product")
        status = self.request.query_params.get("status")
        return qs.filter(status=status) if status else qs[:100]


class ReorderSuggestionDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ReorderSuggestionSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "ai"
    rbac_action = "update"

    def get_queryset(self):
        return ReorderSuggestion.objects.filter(tenant=self.request.tenant).select_related("product")


class PromptTemplateListCreateView(generics.ListCreateAPIView):
    serializer_class = PromptTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "ai"

    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "manage"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        return PromptTemplate.objects.filter(tenant=self.request.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)
