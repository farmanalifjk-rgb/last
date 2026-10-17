import csv
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from pos.models import Brand, Category, Order, Product, Variant
from pos.pagination import CustomPagination
from saas.permissions import HasActiveTenant, TenantRBACPermission
from .models import Batch, BatchMovement, ProductBundle, ProductMedia, ProductVariant, SerialNumber
from .serializers import (
    BatchMovementSerializer,
    BatchSerializer,
    BrandSerializer,
    ProductBundleSerializer,
    ProductMediaSerializer,
    ProductVariantSerializer,
    SerialNumberSerializer,
    VariantDefinitionSerializer,
)
from .services import allocate_batch_fefo, recall_batch, validate_serial


class TenantCatalogAPIView:
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "products"


class TenantCatalogListCreateView(TenantCatalogAPIView, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    pagination_class = CustomPagination

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class TenantCatalogDetailView(TenantCatalogAPIView, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    pass


def tenant_product_or_404(request, product_id):
    return get_object_or_404(Product, pk=product_id, tenant=request.tenant)


class ProductVariantListCreateView(TenantCatalogListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = ProductVariantSerializer

    def get_queryset(self):
        return ProductVariant.objects.filter(tenant=self.request.tenant, product_id=self.kwargs["product_id"]).prefetch_related("attributes")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant, product=tenant_product_or_404(self.request, self.kwargs["product_id"]))


class ProductVariantDetailView(TenantCatalogDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = ProductVariantSerializer

    def get_queryset(self):
        return ProductVariant.objects.filter(tenant=self.request.tenant).prefetch_related("attributes")


class ProductVariantGlobalListView(TenantCatalogListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = ProductVariantSerializer

    def get_queryset(self):
        queryset = ProductVariant.objects.filter(tenant=self.request.tenant).select_related("product").prefetch_related("attributes")
        if search := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(Q(sku__icontains=search) | Q(barcode__icontains=search) | Q(product__name__icontains=search) | Q(product__sku__icontains=search))
        return queryset.order_by("product__name", "sku")


class ProductBundleListCreateView(TenantCatalogListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = ProductBundleSerializer

    def get_queryset(self):
        return ProductBundle.objects.filter(tenant=self.request.tenant).prefetch_related("components__product", "components__variant")


class ProductBundleDetailView(TenantCatalogDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = ProductBundleSerializer

    def get_queryset(self):
        return ProductBundle.objects.filter(tenant=self.request.tenant).prefetch_related("components__product", "components__variant")


class SerialListCreateView(TenantCatalogListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = SerialNumberSerializer

    def get_queryset(self):
        queryset = SerialNumber.objects.filter(tenant=self.request.tenant).select_related("product", "variant", "sold_in_order")
        if product_id := self.request.query_params.get("product_id"):
            queryset = queryset.filter(product_id=product_id)
        if status := self.request.query_params.get("status"):
            queryset = queryset.filter(status=status)
        if search := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(Q(serial_number__icontains=search) | Q(product__name__icontains=search) | Q(product__sku__icontains=search))
        return queryset.order_by("-created_at")


class SerialDetailView(TenantCatalogDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = SerialNumberSerializer

    def get_queryset(self):
        return SerialNumber.objects.filter(tenant=self.request.tenant).select_related("product", "variant", "sold_in_order")


class ValidateSerialView(TenantCatalogAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    def post(self, request):
        product = tenant_product_or_404(request, request.data.get("product_id"))
        try:
            serial = validate_serial(product, request.data.get("serial_number"))
        except ValueError as error:
            return Response({"detail": str(error)}, status=400)
        return Response(SerialNumberSerializer(serial, context={"request": request}).data)


class BatchListCreateView(TenantCatalogListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = BatchSerializer

    def get_queryset(self):
        queryset = Batch.objects.filter(tenant=self.request.tenant).select_related("product", "supplier")
        if product_id := self.request.query_params.get("product_id"):
            queryset = queryset.filter(product_id=product_id)
        if status := self.request.query_params.get("status"):
            if status == "recalled":
                queryset = queryset.filter(is_recalled=True)
            elif status == "expired":
                queryset = queryset.filter(expiry_date__lt=__import__("django.utils.timezone", fromlist=["now"]).now().date())
        if search := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(Q(batch_number__icontains=search) | Q(product__name__icontains=search) | Q(product__sku__icontains=search))
        return queryset.order_by("expiry_date", "-created_at")


class BatchDetailView(TenantCatalogDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = BatchSerializer

    def get_queryset(self):
        return Batch.objects.filter(tenant=self.request.tenant).select_related("product", "supplier")


class BatchMovementListView(TenantCatalogAPIView, generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = BatchMovementSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = BatchMovement.objects.filter(tenant=self.request.tenant, batch_id=self.kwargs["pk"]).select_related("batch", "order", "created_by")
        if kind := self.request.query_params.get("kind"):
            queryset = queryset.filter(kind=kind)
        return queryset.order_by("-created_at")


class BatchRecallView(TenantCatalogAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    def post(self, request, pk):
        batch = get_object_or_404(Batch, pk=pk, tenant=request.tenant)
        recall_batch(batch, request.data.get("reason", ""))
        return Response(BatchSerializer(batch, context={"request": request}).data)


class FefoAllocateView(TenantCatalogAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    def post(self, request):
        product = tenant_product_or_404(request, request.data.get("product_id"))
        order = None
        if order_id := request.data.get("order"):
            order = get_object_or_404(Order, pk=order_id, tenant=request.tenant)
        try:
            allocations = allocate_batch_fefo(product=product, quantity=request.data.get("quantity"), kind=request.data.get("kind", "sale"), order=order, reference=request.data.get("reference", ""), user=request.user)
        except ValueError as error:
            return Response({"detail": str(error)}, status=400)
        return Response([{"batch_id": batch.id, "taken": str(quantity)} for batch, quantity in allocations])


class ProductMediaListCreateView(TenantCatalogListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = ProductMediaSerializer

    def get_queryset(self):
        return ProductMedia.objects.filter(tenant=self.request.tenant, product_id=self.kwargs["product_id"]).select_related("product")

    def perform_create(self, serializer):
        product = tenant_product_or_404(self.request, self.kwargs["product_id"])
        with transaction.atomic():
            if serializer.validated_data.get("is_primary"):
                ProductMedia.objects.filter(tenant=self.request.tenant, product=product, is_primary=True).update(is_primary=False)
            elif not ProductMedia.objects.filter(tenant=self.request.tenant, product=product).exists():
                serializer.validated_data["is_primary"] = True
            serializer.save(tenant=self.request.tenant, product=product)


class ProductMediaDetailView(TenantCatalogDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = ProductMediaSerializer

    def get_queryset(self):
        return ProductMedia.objects.filter(tenant=self.request.tenant).select_related("product")

    def perform_update(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_primary"):
                ProductMedia.objects.filter(tenant=self.request.tenant, product=serializer.instance.product, is_primary=True).exclude(pk=serializer.instance.pk).update(is_primary=False)
            serializer.save()

    def perform_destroy(self, instance):
        with transaction.atomic():
            was_primary = instance.is_primary
            product_id = instance.product_id
            instance.delete()
            if was_primary:
                replacement = ProductMedia.objects.filter(tenant=self.request.tenant, product_id=product_id).order_by("sort_order", "created_at").first()
                if replacement:
                    replacement.is_primary = True
                    replacement.save(update_fields=["is_primary"])


class ProductMediaReorderView(TenantCatalogAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    def post(self, request, product_id):
        product = tenant_product_or_404(request, product_id)
        items = request.data.get("items", [])
        if not isinstance(items, list) or not items:
            return Response({"items": ["Provide at least one media ID and sort order."]}, status=400)
        media_ids = [item.get("id") for item in items if item.get("id")]
        media = list(ProductMedia.objects.filter(tenant=request.tenant, product=product, id__in=media_ids))
        if len(media) != len(set(media_ids)):
            return Response({"items": ["One or more media records are unavailable in this tenant product."]}, status=404)
        primary_ids = [item.get("id") for item in items if item.get("is_primary")]
        if len(primary_ids) > 1:
            return Response({"items": ["Only one primary image may be selected."]}, status=400)
        by_id = {record.id: record for record in media}
        with transaction.atomic():
            ProductMedia.objects.filter(tenant=request.tenant, product=product, is_primary=True).update(is_primary=False)
            for item in items:
                record = by_id[item["id"]]
                record.sort_order = int(item.get("sort_order", record.sort_order))
                record.is_primary = record.id == (primary_ids[0] if primary_ids else None)
                record.save(update_fields=["sort_order", "is_primary"])
        return Response(ProductMediaSerializer(ProductMedia.objects.filter(tenant=request.tenant, product=product), many=True, context={"request": request}).data)


class BrandListCreateView(TenantCatalogListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = BrandSerializer

    def get_queryset(self):
        queryset = Brand.objects.filter(tenant=self.request.tenant)
        if search := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if active := self.request.query_params.get("is_active"):
            queryset = queryset.filter(is_active=active.lower() == "true")
        return queryset.order_by("name")


class BrandDetailView(TenantCatalogDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = BrandSerializer

    def get_queryset(self):
        return Brand.objects.filter(tenant=self.request.tenant)


class VariantDefinitionListCreateView(TenantCatalogListCreateView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = VariantDefinitionSerializer

    def get_queryset(self):
        queryset = Variant.objects.filter(tenant=self.request.tenant).prefetch_related("values")
        if search := self.request.query_params.get("search", "").strip():
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("name")


class VariantDefinitionDetailView(TenantCatalogDetailView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    serializer_class = VariantDefinitionSerializer

    def get_queryset(self):
        return Variant.objects.filter(tenant=self.request.tenant).prefetch_related("values")


class ProductExportCsvView(TenantCatalogAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    def get(self, request):
        products = Product.objects.filter(tenant=request.tenant).select_related("category", "brand").order_by("name")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="catalog-products.csv"'
        writer = csv.writer(response)
        writer.writerow(["name", "sku", "barcode", "description", "category", "brand", "sales_price", "cost_price", "stock_quantity", "min_stock", "max_stock", "unit", "is_active"])
        from pos.helpers import sanitize_csv_cell  # CSV/Excel formula injection guard

        for product in products:
            writer.writerow([
                sanitize_csv_cell(product.name), sanitize_csv_cell(product.sku),
                sanitize_csv_cell(product.barcode or ""), sanitize_csv_cell(product.description or ""),
                sanitize_csv_cell(product.category.name if product.category else ""),
                sanitize_csv_cell(product.brand.name if product.brand else ""),
                product.sales_price, product.cost_price, product.stock_quantity, product.min_stock,
                product.max_stock if product.max_stock is not None else "", sanitize_csv_cell(product.unit), product.is_active,
            ])
        return response


class ProductImportCsvView(TenantCatalogAPIView, APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "catalog"
    rbac_action = "manage"
    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"file": ["Select a CSV file to import."]}, status=400)
        try:
            rows = csv.DictReader(uploaded_file.read().decode("utf-8-sig").splitlines())
        except UnicodeDecodeError:
            return Response({"file": ["The file must be UTF-8 encoded CSV."]}, status=400)

        created = updated = 0
        errors = []
        for line_number, row in enumerate(rows, start=2):
            name = (row.get("name") or "").strip()
            sku = (row.get("sku") or "").strip()
            if not name or not sku:
                errors.append({"line": line_number, "message": "name and sku are required."})
                continue
            try:
                sales_price = Decimal(str(row.get("sales_price") or "0"))
                cost_price = Decimal(str(row.get("cost_price") or "0"))
                stock_quantity = Decimal(str(row.get("stock_quantity") or "0"))
                min_stock = int(row.get("min_stock") or 0)
                max_stock = int(row["max_stock"]) if row.get("max_stock") else None
            except (InvalidOperation, ValueError):
                errors.append({"line": line_number, "message": "Pricing and stock values must be numeric."})
                continue
            category = None
            if category_name := (row.get("category") or "").strip():
                category, _ = Category.objects.get_or_create(tenant=request.tenant, name=category_name)
            brand = None
            if brand_name := (row.get("brand") or "").strip():
                brand, _ = Brand.objects.get_or_create(tenant=request.tenant, name=brand_name)
            try:
                product, was_created = Product.objects.update_or_create(
                    tenant=request.tenant,
                    sku=sku,
                    defaults={
                        "name": name, "barcode": (row.get("barcode") or "").strip() or None,
                        "description": (row.get("description") or "").strip() or None,
                        "category": category, "brand": brand, "sales_price": sales_price,
                        "cost_price": cost_price, "stock_quantity": stock_quantity,
                        "min_stock": min_stock, "max_stock": max_stock,
                        "unit": (row.get("unit") or "Piece").strip() or "Piece",
                        "is_active": str(row.get("is_active", "true")).lower() not in {"false", "0", "no"},
                    },
                )
            except IntegrityError:
                errors.append({"line": line_number, "message": "SKU or barcode conflicts with another product in this tenant."})
                continue
            created += int(was_created)
            updated += int(not was_created)
        return Response({"created": created, "updated": updated, "errors": errors, "processed": created + updated})
