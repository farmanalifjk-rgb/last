from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import Category
from ..serializers import CategorySerializer
from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin


class CategoryViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    rbac_module = "products"
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("parent").annotate(product_count=Count("product", distinct=True), child_count=Count("children", distinct=True))
        if search := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(name__icontains=search)
        if active := self.request.query_params.get("is_active"):
            queryset = queryset.filter(is_active=active.lower() == "true")
        return queryset.order_by("parent_id", "name")

    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        categories = list(super().get_queryset().select_related("parent").annotate(product_count=Count("product", distinct=True), child_count=Count("children", distinct=True)).order_by("parent_id", "name"))
        search = request.query_params.get("search", "").strip().lower()
        if search:
            matched_ids = {category.id for category in categories if search in category.name.lower()}
            by_id = {category.id: category for category in categories}
            for category_id in list(matched_ids):
                parent = by_id[category_id].parent
                while parent is not None:
                    matched_ids.add(parent.id)
                    parent = parent.parent
            categories = [category for category in categories if category.id in matched_ids]
        children = {}
        for category in categories:
            children.setdefault(category.parent_id, []).append(category)

        def node(category):
            data = self.get_serializer(category).data
            data["children"] = [node(child) for child in children.get(category.id, [])]
            return data

        return Response([node(category) for category in children.get(None, [])])

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        category = self.get_object()
        category.is_active = False
        category.save(update_fields=["is_active"])
        return Response(self.get_serializer(category).data)

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.children.exists():
            raise ValidationError({"detail": "This category has child categories. Move or archive them before deletion."})
        if category.product_set.exists():
            raise ValidationError({"detail": "This category is assigned to products. Reassign or archive those products before deletion."})
        self.perform_destroy(category)
        return Response(status=status.HTTP_204_NO_CONTENT)
