from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import F, Q

from ..models import Product
from ..pagination import CustomPagination
from ..serializers import ProductSerializer
from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin


class ProductViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    rbac_module = "products"
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = super().get_queryset().select_related("category", "brand")
        query = self.request.query_params
        if search := query.get("search", "").strip():
            queryset = queryset.filter(Q(name__icontains=search) | Q(sku__icontains=search) | Q(barcode__icontains=search))
        if category := query.get("category"):
            queryset = queryset.filter(category_id=category)
        if brand := query.get("brand"):
            queryset = queryset.filter(brand_id=brand)
        if status := query.get("status"):
            if status == "active":
                queryset = queryset.filter(is_active=True)
            elif status == "inactive":
                queryset = queryset.filter(is_active=False)
        if stock := query.get("stock"):
            if stock == "low":
                queryset = queryset.filter(stock_quantity__gt=0, stock_quantity__lte=F("min_stock"))
            elif stock == "out":
                queryset = queryset.filter(stock_quantity__lte=0)
            elif stock == "in":
                queryset = queryset.filter(stock_quantity__gt=F("min_stock"))
        ordering = query.get("ordering", "name")
        allowed_ordering = {"name", "-name", "sku", "-sku", "sales_price", "-sales_price", "stock_quantity", "-stock_quantity"}
        return queryset.order_by(ordering if ordering in allowed_ordering else "name")

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        product = self.get_object()
        product.is_active = False
        product.save(update_fields=["is_active"])
        return Response(self.get_serializer(product).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, HasActiveTenant])
def product_by_barcode(request, barcode):
    product = Product.objects.filter(tenant=request.tenant, barcode=barcode).first()
    if product is None:
        return Response({"error": "Not found"}, status=404)
    return Response(ProductSerializer(product).data)
