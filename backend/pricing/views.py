from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import ProductVariant
from pos.models import Customer, Product
from pos.pagination import CustomPagination
from saas.permissions import HasActiveTenant, TenantRBACPermission
from system.models import CustomerGroup
from .models import BuyXGetY, CustomerGroupPrice, PriceList, PriceListItem, TimeBasedPrice, VolumeTier
from .serializers import BuyXGetYSerializer, CustomerGroupOptionSerializer, CustomerGroupPriceSerializer, PriceListItemSerializer, PriceListSerializer, TimeBasedPriceSerializer, VolumeTierSerializer
from .services import apply_buyx_gety, resolve_price
from rest_framework.permissions import IsAuthenticated


class TenantPricingAPIView:
    permission_classes = [permissions.IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "products"


class TenantPricingListCreateView(TenantPricingAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    pagination_class = CustomPagination

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class TenantPricingDetailView(TenantPricingAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    pass


class PriceListListCreateView(TenantPricingListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = PriceListSerializer

    def get_queryset(self):
        queryset = PriceList.objects.filter(tenant=self.request.tenant)
        if active := self.request.query_params.get("is_active"):
            queryset = queryset.filter(is_active=active.lower() == "true")
        return queryset.order_by("name")


class PriceListDetailView(TenantPricingDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = PriceListSerializer

    def get_queryset(self):
        return PriceList.objects.filter(tenant=self.request.tenant).prefetch_related("items")


class CustomerGroupOptionListView(TenantPricingAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = CustomerGroupOptionSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = CustomerGroup.objects.filter(tenant=self.request.tenant)
        if active := self.request.query_params.get("is_active"):
            queryset = queryset.filter(is_active=active.lower() == "true")
        return queryset.order_by("name")


class PriceListItemListCreateView(TenantPricingListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = PriceListItemSerializer

    def get_price_list(self):
        return get_object_or_404(PriceList, pk=self.kwargs["price_list_id"], tenant=self.request.tenant)

    def get_queryset(self):
        queryset = PriceListItem.objects.filter(tenant=self.request.tenant, price_list=self.get_price_list()).select_related("product", "variant", "price_list")
        if product_id := self.request.query_params.get("product_id"):
            queryset = queryset.filter(product_id=product_id)
        return queryset.order_by("product__name", "min_quantity")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant, price_list=self.get_price_list())


class PriceListItemDetailView(TenantPricingDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = PriceListItemSerializer

    def get_queryset(self):
        return PriceListItem.objects.filter(tenant=self.request.tenant, price_list_id=self.kwargs["price_list_id"]).select_related("product", "variant", "price_list")


class ProductFilteredPricingListView(TenantPricingListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    product_model = None

    def product_queryset(self):
        queryset = self.product_model.objects.filter(tenant=self.request.tenant).select_related("product")
        if product_id := self.request.query_params.get("product_id"):
            queryset = queryset.filter(product_id=product_id)
        return queryset


class CustomerGroupPriceListCreateView(ProductFilteredPricingListView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = CustomerGroupPriceSerializer
    product_model = CustomerGroupPrice

    def get_queryset(self):
        return self.product_queryset().order_by("product__name")


class CustomerGroupPriceDetailView(TenantPricingDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = CustomerGroupPriceSerializer
    def get_queryset(self): return CustomerGroupPrice.objects.filter(tenant=self.request.tenant).select_related("product")


class VolumeTierListCreateView(ProductFilteredPricingListView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = VolumeTierSerializer
    product_model = VolumeTier
    def get_queryset(self): return self.product_queryset().order_by("product__name", "min_quantity")


class VolumeTierDetailView(TenantPricingDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = VolumeTierSerializer
    def get_queryset(self): return VolumeTier.objects.filter(tenant=self.request.tenant).select_related("product")


class TimeBasedPriceListCreateView(ProductFilteredPricingListView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = TimeBasedPriceSerializer
    product_model = TimeBasedPrice
    def get_queryset(self): return self.product_queryset().order_by("product__name", "valid_from", "start_time")


class TimeBasedPriceDetailView(TenantPricingDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = TimeBasedPriceSerializer
    def get_queryset(self): return TimeBasedPrice.objects.filter(tenant=self.request.tenant).select_related("product")


class BuyXGetYListCreateView(ProductFilteredPricingListView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = BuyXGetYSerializer
    product_model = BuyXGetY
    def get_queryset(self): return self.product_queryset().order_by("product__name", "-created_at")


class BuyXGetYDetailView(TenantPricingDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    serializer_class = BuyXGetYSerializer
    def get_queryset(self): return BuyXGetY.objects.filter(tenant=self.request.tenant).select_related("product")


class ResolvePriceView(TenantPricingAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pricing"
    rbac_action = "view"
    """GET /api/pricing/resolve/?product=&quantity=&customer=&price_list=&variant="""
    def get(self, request):
        product = get_object_or_404(Product, pk=request.query_params.get("product"), tenant=request.tenant)
        customer = get_object_or_404(Customer, pk=request.query_params["customer"], tenant=request.tenant) if request.query_params.get("customer") else None
        price_list = get_object_or_404(PriceList, pk=request.query_params["price_list"], tenant=request.tenant) if request.query_params.get("price_list") else None
        variant = get_object_or_404(ProductVariant, pk=request.query_params["variant"], tenant=request.tenant, product=product) if request.query_params.get("variant") else None
        quantity = Decimal(request.query_params.get("quantity", "1"))
        price = resolve_price(product=product, customer=customer, quantity=quantity, price_list=price_list, variant=variant)
        free = apply_buyx_gety(product=product, quantity=int(quantity))
        return Response({"unit_price": str(price), "line_total": str(price * quantity), "buyx_gety": [{"product": item.id, "qty": quantity} for item, quantity in free]})
