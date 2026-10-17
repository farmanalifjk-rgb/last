"""
settings_core.py
GET/PUT endpoints for every "single row" settings group (the tabs that hold
one set of options rather than a list of records).
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from saas.permissions import HasActiveTenant, PlatformRBACPermission, TenantRBACPermission
from system.platform_audit import record_platform_action

from pos.models import Company

from system.models import (
    POSSettings, InventorySettings, TaxSettings, ReceiptSettings,
    NotificationSettings, BarcodeSettings, CustomerSettings, ProductSettings,
    SecuritySettings, BackupSettings, DataManagementSettings, ReportSettings,
    AppearanceSettings, FeatureFlags, AboutInfo,
)
from system.serializers import (
    CompanyFullSerializer, POSSettingsSerializer, InventorySettingsSerializer,
    TaxSettingsSerializer, ReceiptSettingsSerializer, NotificationSettingsSerializer,
    BarcodeSettingsSerializer, CustomerSettingsSerializer, ProductSettingsSerializer,
    SecuritySettingsSerializer, BackupSettingsSerializer, DataManagementSettingsSerializer,
    ReportSettingsSerializer, AppearanceSettingsSerializer, FeatureFlagsSerializer,
    AboutInfoSerializer,
)


class SingletonSettingsView(APIView):
    """Tenant-isolated singleton settings — one row per tenant."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    """
    Base class: GET returns the single settings row (auto-created on first
    access), PUT partially updates it. Subclasses only set `model` and
    `serializer_class`.
    """
    model = None
    serializer_class = None

    def get(self, request):
        obj = self.model.load(tenant=getattr(request, 'tenant', None))
        return Response(self.serializer_class(obj).data)

    def put(self, request):
        obj = self.model.load(tenant=getattr(request, 'tenant', None))
        serializer = self.serializer_class(obj, data=request.data, partial=True)
        if serializer.is_valid():
            before = self.serializer_class(obj).data
            serializer.save()
            record_platform_action(
                request=request,
                action="update",
                entity=self.model.__name__,
                entity_id=obj.pk,
                description=f"Updated platform-global {self.model.__name__} settings.",
                metadata={"before": before, "after": serializer.data},
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # PATCH behaves the same as PUT (all fields already optional / partial)
    def patch(self, request):
        return self.put(request)


class PlatformSystemAPIView(APIView):
    """Platform-global operational controls with explicit RBAC, never is_staff."""
    permission_classes = [PlatformRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"


class TenantSystemAPIView(APIView):
    """Tenant-owned system resources isolated by canonical active-tenant context."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"


# ─── 1 & 2. General / Company ───────────────────────────────────────────────
class CompanySettingsView(APIView):
    """Tenant-owned company profile, isolated by canonical context and RBAC."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    """Full company/business profile — General + Company tabs combined."""

    def get(self, request):
        company = Company.objects.filter(tenant=request.tenant).first()
        if not company:
            company = Company.objects.create(tenant=request.tenant, name="My Store", address="")
        return Response(CompanyFullSerializer(company).data)

    def put(self, request):
        company = Company.objects.filter(tenant=request.tenant).first()
        if not company:
            company = Company(tenant=request.tenant, name=request.data.get("name", "My Store"), address=request.data.get("address", ""))
            company.save()
        serializer = CompanyFullSerializer(company, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        return self.put(request)


# ─── 3. POS Settings ─────────────────────────────────────────────────────────
class POSSettingsView(SingletonSettingsView):
    model = POSSettings
    serializer_class = POSSettingsSerializer


# ─── 4. Inventory Settings ───────────────────────────────────────────────────
class InventorySettingsView(SingletonSettingsView):
    model = InventorySettings
    serializer_class = InventorySettingsSerializer


# ─── 5. Tax Settings (global config) ─────────────────────────────────────────
class TaxSettingsView(SingletonSettingsView):
    model = TaxSettings
    serializer_class = TaxSettingsSerializer


# ─── 7. Receipt Settings ─────────────────────────────────────────────────────
class ReceiptSettingsView(SingletonSettingsView):
    model = ReceiptSettings
    serializer_class = ReceiptSettingsSerializer


# ─── 9. Notification Settings ────────────────────────────────────────────────
class NotificationSettingsView(SingletonSettingsView):
    model = NotificationSettings
    serializer_class = NotificationSettingsSerializer


# ─── 11. Barcode Settings ────────────────────────────────────────────────────
class BarcodeSettingsView(SingletonSettingsView):
    model = BarcodeSettings
    serializer_class = BarcodeSettingsSerializer


# ─── 12. Customer Settings ───────────────────────────────────────────────────
class CustomerSettingsView(SingletonSettingsView):
    model = CustomerSettings
    serializer_class = CustomerSettingsSerializer


# ─── 13. Product Settings ────────────────────────────────────────────────────
class ProductSettingsView(SingletonSettingsView):
    model = ProductSettings
    serializer_class = ProductSettingsSerializer


# ─── 14. Security Settings ───────────────────────────────────────────────────
class SecuritySettingsView(SingletonSettingsView):
    model = SecuritySettings
    serializer_class = SecuritySettingsSerializer


# ─── 15. Backup Settings ─────────────────────────────────────────────────────
class BackupSettingsView(SingletonSettingsView):
    model = BackupSettings
    serializer_class = BackupSettingsSerializer


# ─── 16. Data Management Settings ────────────────────────────────────────────
class DataManagementSettingsView(SingletonSettingsView):
    model = DataManagementSettings
    serializer_class = DataManagementSettingsSerializer


# ─── 17. Report Settings ─────────────────────────────────────────────────────
class ReportSettingsView(SingletonSettingsView):
    model = ReportSettings
    serializer_class = ReportSettingsSerializer


# ─── 18. Appearance Settings ─────────────────────────────────────────────────
class AppearanceSettingsView(SingletonSettingsView):
    model = AppearanceSettings
    serializer_class = AppearanceSettingsSerializer


# ─── Feature Flags (platform-wide switches) ──────────────────────────────────
class FeatureFlagsView(SingletonSettingsView):
    model = FeatureFlags
    serializer_class = FeatureFlagsSerializer


# ─── 20. About ────────────────────────────────────────────────────────────────
class AboutInfoView(SingletonSettingsView):
    model = AboutInfo
    serializer_class = AboutInfoSerializer


class CheckUpdatesView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    """Stub 'check for updates' endpoint — swap the hard-coded version for a
    real update-server call when one exists."""

    def post(self, request):
        from django.utils import timezone
        about = AboutInfo.load(tenant=getattr(request, "tenant", None))
        about.last_update_check_at = timezone.now()
        about.save()
        record_platform_action(
            request=request,
            action="update",
            entity="AboutInfo",
            entity_id=about.pk,
            description="Checked platform update metadata.",
        )
        return Response({
            "current_version": about.pos_version,
            "latest_version": about.pos_version,
            "update_available": False,
            "checked_at": about.last_update_check_at,
        })


# ─── All-in-one settings bundle (handy for a single frontend load) ──────────
class SettingsBundleView(APIView):
    permission_classes = [PlatformRBACPermission]
    rbac_module = "settings"
    rbac_action = "view"

    """Returns every settings group in one call, keyed by tab name."""

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        company = Company.objects.filter(tenant=tenant).first() if tenant else Company.objects.first()
        return Response({
            "company": CompanyFullSerializer(company).data if company else {},
            "pos": POSSettingsSerializer(POSSettings.load(tenant=tenant)).data,
            "inventory": InventorySettingsSerializer(InventorySettings.load(tenant=tenant)).data,
            "tax": TaxSettingsSerializer(TaxSettings.load(tenant=tenant)).data,
            "receipt": ReceiptSettingsSerializer(ReceiptSettings.load(tenant=tenant)).data,
            "notifications": NotificationSettingsSerializer(NotificationSettings.load(tenant=tenant)).data,
            "barcode": BarcodeSettingsSerializer(BarcodeSettings.load(tenant=tenant)).data,
            "customer": CustomerSettingsSerializer(CustomerSettings.load(tenant=tenant)).data,
            "product": ProductSettingsSerializer(ProductSettings.load(tenant=tenant)).data,
            "security": SecuritySettingsSerializer(SecuritySettings.load(tenant=tenant)).data,
            "backup": BackupSettingsSerializer(BackupSettings.load(tenant=tenant)).data,
            "data_management": DataManagementSettingsSerializer(DataManagementSettings.load(tenant=tenant)).data,
            "reports": ReportSettingsSerializer(ReportSettings.load(tenant=tenant)).data,
            "appearance": AppearanceSettingsSerializer(AppearanceSettings.load(tenant=tenant)).data,
            "feature_flags": FeatureFlagsSerializer(FeatureFlags.load(tenant=tenant)).data,
            "about": AboutInfoSerializer(AboutInfo.load(tenant=tenant)).data,
        })


"""
settings_backup.py
Backup & Restore + Data Management tabs.

Backups use Django's own `dumpdata` / `loaddata` machinery (via `call_command`)
so they work against whatever database engine is configured (Postgres in
production) without shelling out to `pg_dump`. Each backup is a JSON fixture
of every `pos` app model, stored as a FileField (so it lands wherever
MEDIA_ROOT / your storage backend points) and tracked in `BackupRecord`.

Data Management exports use CSV via the stdlib `csv` module — no serializer
plumbing required, and it can be opened directly in Excel/Sheets.
"""
import csv
import io
import json
import os
import tempfile
from django.core import management
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from pos.models import Product, Customer, Category, Brand
from system.models import BackupRecord, BackupSettings, DataManagementSettings
from pos.pagination import CustomPagination
from system.serializers import BackupRecordSerializer, BackupSettingsSerializer, DataManagementSettingsSerializer

APP_LABEL = "pos"
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000


def _validated_import_upload(request, *, extensions, content_types):
    upload = request.FILES.get("file")
    if not upload:
        raise ValidationError({"file": ["No file uploaded."]})
    if upload.size <= 0 or upload.size > MAX_IMPORT_BYTES:
        raise ValidationError({"file": ["The import file must be between 1 byte and 2 MiB."]})
    name = str(upload.name or "")
    if os.path.basename(name) != name or not any(name.lower().endswith(extension) for extension in extensions):
        raise ValidationError({"file": ["Unexpected import file extension."]})
    content_type = (getattr(upload, "content_type", "") or "").lower()
    if content_type and content_type not in content_types:
        raise ValidationError({"file": ["Unexpected import content type."]})
    return upload


def _read_csv_import(upload):
    try:
        text = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError({"file": ["CSV imports must be UTF-8 encoded."]}) from exc
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValidationError({"file": ["CSV import exceeds the 10,000-row limit."]})
    return rows


def _load_fixture_bytes(data_bytes):
    """
    Django's `loaddata` management command only accepts a fixture path/name,
    not stdin — so we write the payload to a temp .json file and point
    loaddata at that.
    """
    json.loads(data_bytes)  # validate it's well-formed JSON before touching the DB
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data_bytes)
        management.call_command("loaddata", path, format="json")
    finally:
        os.remove(path)


# ═══════════════════════════════════════════════════════════════════════════
# Backup & Restore
# ═══════════════════════════════════════════════════════════════════════════
class BackupListView(PlatformSystemAPIView):

    def get(self, request):
        qs = BackupRecord.objects.all()
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = BackupRecordSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data)
        tenant = getattr(request, "tenant", None)
        paged.data["stats"] = {
            "total": BackupRecord.objects.count(),
            "last_backup_at": BackupSettings.load(tenant=tenant).last_backup_at,
            "automatic_backup": BackupSettings.load(tenant=tenant).automatic_backup,
        }
        return paged


class BackupCreateView(PlatformSystemAPIView):

    """Trigger a manual (or automatic-scheduler-invoked) backup right now."""

    def post(self, request):
        backup_type = request.data.get("backup_type", "manual")
        record = BackupRecord.objects.create(
            backup_type=backup_type,
            status="pending",
            notes=request.data.get("notes", ""),
            created_by=request.user if getattr(request.user, "is_authenticated", False) else None,
        )

        try:
            buffer = io.StringIO()
            management.call_command(
                "dumpdata", APP_LABEL,
                indent=2, natural_foreign=True, natural_primary=True, stdout=buffer,
            )
            content = buffer.getvalue().encode("utf-8")

            filename = f"backup_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
            record.file.save(filename, ContentFile(content), save=False)
            record.file_size_bytes = len(content)
            record.status = "success"
            record.save()

            settings_obj = BackupSettings.load(tenant=getattr(request, "tenant", None))
            settings_obj.last_backup_at = timezone.now()
            settings_obj.save()

            # Trim old backups beyond retention count
            keep_n = settings_obj.keep_last_n_backups
            if keep_n > 0:
                stale = BackupRecord.objects.filter(status="success").order_by("-created_at")[keep_n:]
                for old in stale:
                    if old.file:
                        old.file.delete(save=False)
                    old.delete()

        except Exception as e:
            record.status = "failed"
            record.notes = (record.notes + f" | error: {e}").strip(" |")
            record.save()
            return Response(BackupRecordSerializer(record).data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(BackupRecordSerializer(record).data, status=status.HTTP_201_CREATED)


class BackupDownloadView(PlatformSystemAPIView):

    def get(self, request, pk):
        record = BackupRecord.objects.filter(pk=pk).first()
        if not record or not record.file:
            return Response({"error": "Backup file not found"}, status=status.HTTP_404_NOT_FOUND)
        response = HttpResponse(record.file.read(), content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="{record.file.name.split("/")[-1]}"'
        return response


class BackupRestoreView(PlatformSystemAPIView):

    """
    Restore from a previously created backup (by id) OR from an uploaded
    JSON fixture file. THIS OVERWRITES CURRENT DATA for the pos app models —
    callers should confirm with the user before calling this.
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @transaction.atomic
    def post(self, request):
        upload = request.FILES.get("file")
        backup_id = request.data.get("backup_id")

        if upload:
            data = upload.read()
        elif backup_id:
            record = BackupRecord.objects.filter(pk=backup_id).first()
            if not record or not record.file:
                return Response({"error": "Backup not found"}, status=status.HTTP_404_NOT_FOUND)
            data = record.file.read()
        else:
            return Response({"error": "Provide either 'file' or 'backup_id'"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            _load_fixture_bytes(data)
        except Exception as e:
            return Response({"error": f"Restore failed: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Restore completed successfully."})


class ExportDatabaseView(PlatformSystemAPIView):

    """Full JSON export of every pos-app model, streamed as a download."""

    def get(self, request):
        buffer = io.StringIO()
        management.call_command(
            "dumpdata", APP_LABEL, indent=2, natural_foreign=True, natural_primary=True, stdout=buffer,
        )
        content = buffer.getvalue()
        response = HttpResponse(content, content_type="application/json")
        filename = f"pos_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class ImportDatabaseView(PlatformSystemAPIView):

    """Import/merge a JSON fixture without wiping existing rows first."""
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = _validated_import_upload(
            request,
            extensions=(".json",),
            content_types={"application/json", "text/json"},
        )
        try:
            data = upload.read()
            _load_fixture_bytes(data)
        except Exception:
            return Response({"error": "Import failed validation."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Import completed successfully."})


# ═══════════════════════════════════════════════════════════════════════════
# Data Management
# ═══════════════════════════════════════════════════════════════════════════
def _csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return response


class ExportProductsView(PlatformSystemAPIView):

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        rows = Product.objects.select_related("category", "brand").all() if not tenant else Product.objects.filter(tenant=tenant).select_related("category", "brand").all()
        return _csv_response(
            "products.csv",
            ["ID", "Name", "SKU", "Barcode", "Category", "Brand", "Sales Price", "Cost Price",
             "Stock Quantity", "Min Stock", "Max Stock", "Unit", "Active"],
            [[p.id, p.name, p.sku, p.barcode or "", p.category.name if p.category else "",
              p.brand.name if p.brand else "", p.sales_price, p.cost_price, p.stock_quantity,
              p.min_stock, p.max_stock or "", p.unit, p.is_active] for p in rows],
        )


class ImportProductsView(PlatformSystemAPIView):

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = _validated_import_upload(
            request,
            extensions=(".csv",),
            content_types={"text/csv", "application/csv", "application/vnd.ms-excel"},
        )
        rows = _read_csv_import(upload)
        created, updated, errors = 0, 0, []
        tenant = getattr(request, 'tenant', None)

        for i, row in enumerate(rows, start=2):
            try:
                sku = row.get("SKU") or row.get("sku")
                if not sku:
                    errors.append(f"Row {i}: missing SKU")
                    continue
                category = None
                if row.get("Category"):
                    if tenant:
                        category, _ = Category.objects.get_or_create(tenant=tenant, name=row["Category"])
                    else:
                        category, _ = Category.objects.get_or_create(name=row["Category"])
                brand = None
                if row.get("Brand"):
                    if tenant:
                        brand, _ = Brand.objects.get_or_create(tenant=tenant, name=row["Brand"])
                    else:
                        brand, _ = Brand.objects.get_or_create(name=row["Brand"])

                lookup = {"sku": sku}
                defaults = {
                    "name": row.get("Name", sku),
                    "barcode": row.get("Barcode") or None,
                    "category": category,
                    "brand": brand,
                    "sales_price": row.get("Sales Price") or 0,
                    "cost_price": row.get("Cost Price") or 0,
                    "stock_quantity": row.get("Stock Quantity") or 0,
                    "min_stock": row.get("Min Stock") or 0,
                    "unit": row.get("Unit") or "Piece",
                    "is_active": str(row.get("Active", "True")).lower() in ("true", "1", "yes"),
                }
                if tenant:
                    lookup["tenant"] = tenant
                    defaults["tenant"] = tenant
                obj, was_created = Product.objects.update_or_create(
                    **lookup,
                    defaults=defaults,
                )
                created += 1 if was_created else 0
                updated += 0 if was_created else 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")

        return Response({"created": created, "updated": updated, "errors": errors})


class ExportCustomersView(PlatformSystemAPIView):

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        rows = Customer.objects.select_related("group").all() if not tenant else Customer.objects.filter(tenant=tenant).select_related("group").all()
        return _csv_response(
            "customers.csv",
            ["ID", "Name", "Phone", "Email", "Address", "Group", "Loyalty Points"],
            [[c.id, c.name, c.phone, c.email, c.address, c.group.name if c.group else "", c.loyalty_points]
             for c in rows],
        )


class ImportCustomersView(PlatformSystemAPIView):

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        from ..models_settings import CustomerGroup
        upload = _validated_import_upload(
            request,
            extensions=(".csv",),
            content_types={"text/csv", "application/csv", "application/vnd.ms-excel"},
        )
        rows = _read_csv_import(upload)
        created, updated, errors = 0, 0, []

        tenant = getattr(request, 'tenant', None)

        for i, row in enumerate(rows, start=2):
            try:
                name = row.get("Name")
                if not name:
                    errors.append(f"Row {i}: missing Name")
                    continue
                group = None
                if row.get("Group"):
                    if tenant:
                        group, _ = CustomerGroup.objects.get_or_create(tenant=tenant, name=row["Group"])
                    else:
                        group, _ = CustomerGroup.objects.get_or_create(name=row["Group"])

                lookup = {"email": row["Email"]} if row.get("Email") else {"phone": row.get("Phone", ""), "name": name}
                defaults = {
                    "name": name,
                    "phone": row.get("Phone", ""),
                    "email": row.get("Email", ""),
                    "address": row.get("Address", ""),
                    "group": group,
                }
                if tenant:
                    lookup["tenant"] = tenant
                    defaults["tenant"] = tenant
                obj, was_created = Customer.objects.update_or_create(
                    **lookup,
                    defaults=defaults,
                )
                created += 1 if was_created else 0
                updated += 0 if was_created else 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")

        return Response({"created": created, "updated": updated, "errors": errors})


class ExportInventoryView(PlatformSystemAPIView):

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        rows = Product.objects.all() if not tenant else Product.objects.filter(tenant=tenant).all()
        return _csv_response(
            "inventory.csv",
            ["ID", "Name", "SKU", "Stock Quantity", "Min Stock", "Max Stock", "Unit"],
            [[p.id, p.name, p.sku, p.stock_quantity, p.min_stock, p.max_stock or "", p.unit] for p in rows],
        )


class ExportSalesView(PlatformSystemAPIView):

    def get(self, request):
        from ..models import Order
        tenant = getattr(request, 'tenant', None)
        qs = Order.objects.select_related("customer").prefetch_related("items").all() if not tenant else Order.objects.filter(tenant=tenant).select_related("customer").prefetch_related("items").all()
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        return _csv_response(
            "sales.csv",
            ["Order Number", "Date", "Customer", "Payment Method", "Subtotal", "Tax", "Discount", "Total", "Status"],
            [[o.order_number, o.created_at.strftime("%Y-%m-%d %H:%M"), o.customer.name if o.customer else "Walk-in",
              o.payment_method, o.subtotal, o.tax, o.discount, o.total, o.status] for o in qs],
        )


class ClearCacheView(PlatformSystemAPIView):

    def post(self, request):
        from django.core.cache import cache
        cache.clear()
        settings_obj = DataManagementSettings.load(tenant=getattr(request, "tenant", None))
        settings_obj.last_cache_clear_at = timezone.now()
        settings_obj.save()
        return Response({"message": "Cache cleared successfully.", "cleared_at": settings_obj.last_cache_clear_at})


class RebuildSearchIndexView(PlatformSystemAPIView):

    """
    Placeholder hook — wire this to your actual search backend (Postgres
    full-text index refresh, Elasticsearch reindex, etc). Currently just
    records that a rebuild was requested so the UI can show progress/history.
    """

    def post(self, request):
        settings_obj = DataManagementSettings.load(tenant=getattr(request, "tenant", None))
        settings_obj.last_index_rebuild_at = timezone.now()
        settings_obj.save()
        return Response({
            "message": "Search index rebuild triggered.",
            "rebuilt_at": settings_obj.last_index_rebuild_at,
        })


class OptimizeDatabaseView(PlatformSystemAPIView):

    """Runs Django's `optimize`-equivalent maintenance where supported (VACUUM ANALYZE on Postgres)."""

    def post(self, request):
        from django.db import connection
        ran_vacuum = False
        try:
            if connection.vendor == "postgresql":
                autocommit = connection.get_autocommit()
                connection.set_autocommit(True)
                with connection.cursor() as cursor:
                    cursor.execute("VACUUM ANALYZE;")
                connection.set_autocommit(autocommit)
                ran_vacuum = True
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        settings_obj = DataManagementSettings.load(tenant=getattr(request, "tenant", None))
        settings_obj.last_optimization_at = timezone.now()
        settings_obj.save()
        return Response({
            "message": "Database optimization complete." if ran_vacuum else "Optimization skipped (unsupported DB engine).",
            "optimized_at": settings_obj.last_optimization_at,
        })


"""
settings_dev.py
Developer / integrations tooling: API keys, webhooks (+ delivery log & test
trigger), email/SMS templates, and error/crash logging (system health).
"""
import json
import hmac
import hashlib
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from system.models import (
    APIKey, Webhook, WebhookDelivery, EmailTemplate, SMSTemplate, ErrorLog,
)
from pos.pagination import CustomPagination
from system.serializers import (
    APIKeySerializer, APIKeyCreateResponseSerializer, WebhookSerializer,
    WebhookDeliverySerializer, EmailTemplateSerializer, SMSTemplateSerializer,
    ErrorLogSerializer,
)


# ═══════════════════════════════════════════════════════════════════════════
# API Keys
# ═══════════════════════════════════════════════════════════════════════════
class APIKeyListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = APIKey.objects.all()
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = APIKeySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Returns the raw key ONCE — store it now, it can't be retrieved again."""
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        data["created_by"] = request.user.id if getattr(request.user, "is_authenticated", False) else None
        key = APIKey.objects.create(
            name=data.get("name", "Untitled Key"),
            scopes=data.get("scopes", []),
            expires_at=data.get("expires_at") or None,
            created_by_id=data.get("created_by"),
        )
        return Response(APIKeyCreateResponseSerializer(key).data, status=status.HTTP_201_CREATED)


class APIKeyDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        key = get_object_or_404(APIKey, pk=pk)
        return Response(APIKeySerializer(key).data)

    def put(self, request, pk):
        key = get_object_or_404(APIKey, pk=pk)
        if "is_active" in request.data:
            key.is_active = request.data["is_active"]
        if "name" in request.data:
            key.name = request.data["name"]
        if "scopes" in request.data:
            key.scopes = request.data["scopes"]
        key.save()
        return Response(APIKeySerializer(key).data)

    def delete(self, request, pk):
        get_object_or_404(APIKey, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class APIKeyRegenerateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        from ..models_settings import generate_api_key
        key = get_object_or_404(APIKey, pk=pk)
        key.key = generate_api_key()
        key.save()
        return Response(APIKeyCreateResponseSerializer(key).data)


# ═══════════════════════════════════════════════════════════════════════════
# Webhooks
# ═══════════════════════════════════════════════════════════════════════════
class WebhookListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = Webhook.objects.all()
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = WebhookSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = WebhookSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WebhookDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        return Response(WebhookSerializer(get_object_or_404(Webhook, pk=pk)).data)

    def put(self, request, pk):
        webhook = get_object_or_404(Webhook, pk=pk)
        serializer = WebhookSerializer(webhook, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        get_object_or_404(Webhook, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def sign_payload(secret, payload_bytes):
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


class WebhookTestView(APIView):
    permission_classes = [IsAdminUser]

    """Sends a synthetic test event to the webhook's target URL right now."""

    def post(self, request, pk):
        import requests as _requests  # local import: keep this optional dependency scoped

        webhook = get_object_or_404(Webhook, pk=pk)
        test_payload = {
            "event": "webhook.test",
            "sent_at": timezone.now().isoformat(),
            "data": {"message": "This is a test event from your POS system."},
        }
        payload_bytes = json.dumps(test_payload).encode()
        signature = sign_payload(webhook.secret, payload_bytes)

        status_code, success, body = None, False, ""
        try:
            resp = _requests.post(
                webhook.target_url,
                data=payload_bytes,
                headers={"Content-Type": "application/json", "X-POS-Signature": signature},
                timeout=8,
            )
            status_code, success, body = resp.status_code, resp.ok, resp.text[:2000]
        except Exception as e:
            body = str(e)

        WebhookDelivery.objects.create(
            webhook=webhook, event="webhook.test", payload=test_payload,
            status_code=status_code, success=success, response_body=body,
        )
        webhook.last_triggered_at = timezone.now()
        webhook.last_status_code = status_code
        webhook.save()

        return Response({"success": success, "status_code": status_code, "response": body})


class WebhookDeliveryListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        webhook = get_object_or_404(Webhook, pk=pk)
        qs = webhook.deliveries.all()
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = WebhookDeliverySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


def trigger_webhooks(event_key, payload):
    """
    Call this from anywhere in the app (e.g. after an order is paid) to fan
    the event out to every active, subscribed webhook.
    Example: trigger_webhooks("order.paid", {"order_id": order.id, "total": str(order.total)})
    """
    import requests as _requests

    webhooks = Webhook.objects.filter(is_active=True)
    for webhook in webhooks:
        if event_key not in (webhook.events or []):
            continue
        body = {"event": event_key, "sent_at": timezone.now().isoformat(), "data": payload}
        payload_bytes = json.dumps(body).encode()
        signature = sign_payload(webhook.secret, payload_bytes)
        status_code, success, resp_body = None, False, ""
        try:
            resp = _requests.post(
                webhook.target_url, data=payload_bytes,
                headers={"Content-Type": "application/json", "X-POS-Signature": signature}, timeout=8,
            )
            status_code, success, resp_body = resp.status_code, resp.ok, resp.text[:2000]
        except Exception as e:
            resp_body = str(e)

        WebhookDelivery.objects.create(
            webhook=webhook, event=event_key, payload=body,
            status_code=status_code, success=success, response_body=resp_body,
        )
        webhook.last_triggered_at = timezone.now()
        webhook.last_status_code = status_code
        webhook.save()


# ═══════════════════════════════════════════════════════════════════════════
# Email / SMS Templates
# ═══════════════════════════════════════════════════════════════════════════
class EmailTemplateListView(TenantSystemAPIView):
    def get(self, request):
        return Response(EmailTemplateSerializer(EmailTemplate.objects.filter(tenant=request.tenant), many=True).data)

    def post(self, request):
        serializer = EmailTemplateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(tenant=request.tenant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EmailTemplateDetailView(TenantSystemAPIView):
    def get(self, request, pk):
        return Response(EmailTemplateSerializer(get_object_or_404(EmailTemplate, tenant=request.tenant, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(EmailTemplate, tenant=request.tenant, pk=pk)

        serializer = EmailTemplateSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        get_object_or_404(EmailTemplate, tenant=request.tenant, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SMSTemplateListView(TenantSystemAPIView):
    def get(self, request):
        return Response(SMSTemplateSerializer(SMSTemplate.objects.filter(tenant=request.tenant), many=True).data)

    def post(self, request):
        serializer = SMSTemplateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(tenant=request.tenant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SMSTemplateDetailView(TenantSystemAPIView):
    def get(self, request, pk):
        return Response(SMSTemplateSerializer(get_object_or_404(SMSTemplate, tenant=request.tenant, pk=pk)).data)

    def put(self, request, pk):
        obj = get_object_or_404(SMSTemplate, tenant=request.tenant, pk=pk)

        serializer = SMSTemplateSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        get_object_or_404(SMSTemplate, tenant=request.tenant, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ═══════════════════════════════════════════════════════════════════════════
# Error / Crash Logs (system health & monitoring)
# ═══════════════════════════════════════════════════════════════════════════
class ErrorLogListView(TenantSystemAPIView):
    def get(self, request):
        qs = ErrorLog.objects.filter(tenant=request.tenant)

        log_type = request.GET.get("log_type")
        if log_type:
            qs = qs.filter(log_type=log_type)
        severity = request.GET.get("severity")
        if severity:
            qs = qs.filter(severity=severity)
        resolved = request.GET.get("is_resolved")
        if resolved is not None:
            qs = qs.filter(is_resolved=resolved in ("1", "true", "True"))

        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ErrorLogSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data)
        paged.data["stats"] = {
            "total": qs.count(),
            "unresolved": qs.filter(is_resolved=False).count(),
            "critical": qs.filter(severity="critical", is_resolved=False).count(),
        }

        return paged

    def post(self, request):
        """Frontend/agent crash & error reporter posts here."""
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        data["user"] = request.user.id if getattr(request.user, "is_authenticated", False) else None
        serializer = ErrorLogSerializer(data=data)
        if serializer.is_valid():
            serializer.save(tenant=request.tenant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ErrorLogResolveView(TenantSystemAPIView):
    def post(self, request, pk):
        log = get_object_or_404(ErrorLog, tenant=request.tenant, pk=pk)

        log.is_resolved = True
        log.save()
        return Response(ErrorLogSerializer(log).data)


class SystemHealthView(TenantSystemAPIView):

    """Lightweight system-health snapshot for a dashboard widget."""

    def get(self, request):
        from django.db import connection
        from django.utils import timezone as tz
        from datetime import timedelta

        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            db_ok = False

        last_24h = tz.now() - timedelta(hours=24)
        return Response({
            "database_connected": db_ok,
            "errors_last_24h": ErrorLog.objects.filter(tenant=request.tenant, log_type="error", created_at__gte=last_24h).count(),
            "crashes_last_24h": ErrorLog.objects.filter(tenant=request.tenant, log_type="crash", created_at__gte=last_24h).count(),
            "unresolved_issues": ErrorLog.objects.filter(tenant=request.tenant, is_resolved=False).count(),
            "checked_at": tz.now(),
        })


class ReadinessHealthView(APIView):
    """Non-sensitive liveness/readiness endpoint for load balancers and smoke tests."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            return Response(
                {"status": "unavailable", "database": "unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", "database": "ok"})


"""
settings_security.py
Views backing the Security settings tab: login-attempt tracking (with
lockout), trusted-device authorization, audit log, and a password-policy
validator that reads live from SecuritySettings so the frontend and backend
enforce the exact same rule.
"""
import re
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from system.models import SecuritySettings, LoginAttempt, TrustedDevice, AuditLog
from pos.pagination import CustomPagination
from system.serializers import (
    LoginAttemptSerializer, TrustedDeviceSerializer, AuditLogSerializer,
)

User = get_user_model()


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def validate_password_against_policy(password, tenant=None):
    """Returns (is_valid, list_of_errors) checked against live SecuritySettings."""
    settings_obj = SecuritySettings.load(tenant=tenant)
    errors = []

    if len(password) < settings_obj.password_min_length:
        errors.append(f"Password must be at least {settings_obj.password_min_length} characters long.")

    if settings_obj.password_policy == "standard":
        if not re.search(r"[A-Za-z]", password):
            errors.append("Password must contain at least one letter.")
        if not re.search(r"[0-9]", password):
            errors.append("Password must contain at least one number.")
    elif settings_obj.password_policy == "strong":
        if not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter.")
        if not re.search(r"[0-9]", password):
            errors.append("Password must contain at least one number.")
        if not re.search(r"[^A-Za-z0-9]", password):
            errors.append("Password must contain at least one symbol.")

    return (len(errors) == 0, errors)


class PasswordPolicyCheckView(APIView):
    """Frontend can call this live while the user types a new password."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        password = request.data.get("password", "")
        tenant = getattr(request, "tenant", None)
        is_valid, errors = validate_password_against_policy(password, tenant=tenant)
        return Response({"is_valid": is_valid, "errors": errors})



class LoginAttemptListView(APIView):
    """Record a login attempt (call from the actual login view) and list history."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = LoginAttempt.objects.all()
        username = request.GET.get("username")
        if username:
            qs = qs.filter(username__icontains=username)
        status_filter = request.GET.get("status")
        if status_filter == "success":
            qs = qs.filter(was_successful=True)
        elif status_filter == "failed":
            qs = qs.filter(was_successful=False)

        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = LoginAttemptSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data)
        paged.data["stats"] = {
            "total": LoginAttempt.objects.count(),
            "failed_last_24h": LoginAttempt.objects.filter(
                was_successful=False, created_at__gte=timezone.now() - timedelta(hours=24)
            ).count(),
        }
        return paged

    def post(self, request):
        username = request.data.get("username", "")
        was_successful = bool(request.data.get("was_successful", False))
        reason = request.data.get("reason", "")

        attempt = LoginAttempt.objects.create(
            username=username,
            was_successful=was_successful,
            reason=reason,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        )

        settings_obj = SecuritySettings.load(tenant=getattr(request, "tenant", None))
        locked_out = False
        if not was_successful:
            window_start = timezone.now() - timedelta(minutes=settings_obj.lockout_duration_minutes)
            recent_failures = LoginAttempt.objects.filter(
                username=username, was_successful=False, created_at__gte=window_start
            ).count()
            locked_out = recent_failures >= settings_obj.max_login_attempts
            # A NotificationSettings.failed_login_alerts check + dispatch would hook in here.

        return Response({
            **LoginAttemptSerializer(attempt).data,
            "locked_out": locked_out,
        }, status=status.HTTP_201_CREATED)


# ─── Trusted Devices ──────────────────────────────────────────────────────────
class TrustedDeviceListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = TrustedDevice.objects.all()
        user_id = request.GET.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = TrustedDeviceSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        user_id = request.data.get("user")
        user = get_object_or_404(User, pk=user_id)
        device, created = TrustedDevice.objects.get_or_create(
            user=user,
            device_id=request.data.get("device_id"),
            defaults={
                "device_name": request.data.get("device_name", ""),
                "ip_address": _client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
                "is_authorized": not SecuritySettings.load(tenant=getattr(request, "tenant", None)).require_device_authorization,
            },
        )
        return Response(TrustedDeviceSerializer(device).data,
                         status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class TrustedDeviceAuthorizeView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        device = get_object_or_404(TrustedDevice, pk=pk)
        device.is_authorized = True
        device.save()
        return Response(TrustedDeviceSerializer(device).data)


class TrustedDeviceRevokeView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        device = get_object_or_404(TrustedDevice, pk=pk)
        device.is_authorized = False
        device.save()
        # Immediately kill any active sessions issued to this device.
        from ..models_auth import AuthToken
        revoked_sessions = AuthToken.objects.filter(device=device, is_revoked=False).update(is_revoked=True)
        data = TrustedDeviceSerializer(device).data
        data["revoked_sessions"] = revoked_sessions
        return Response(data)


class TrustedDeviceDeleteView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        get_object_or_404(TrustedDevice, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Audit Log ────────────────────────────────────────────────────────────────
class AuditLogListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = AuditLog.objects.all()
        user_id = request.GET.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)
        action = request.GET.get("action")
        if action:
            qs = qs.filter(action=action)
        entity = request.GET.get("entity")
        if entity:
            qs = qs.filter(entity__icontains=entity)
        date_from = request.GET.get("date_from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = request.GET.get("date_to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Allows the frontend (or other views) to push an audit entry directly."""
        serializer = AuditLogSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(ip_address=_client_ip(request))
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def write_audit_log(user, action, entity="", entity_id="", description="", request=None, **metadata):
    """Convenience helper other views can import to log an action in one line."""
    AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        description=description,
        ip_address=_client_ip(request) if request else None,
        metadata=metadata,
    )


"""
settings_lists.py
List/detail (CRUD) views for settings resources that hold multiple records:
Stores, Hardware devices, Customer groups, Custom fields, Scheduled reports,
Notifications, Receipt templates.
Follows the same plain-APIView list+detail pattern already used in
views/configuration.py so the codebase stays consistent.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.shortcuts import get_object_or_404

from system.models import (
    Store, HardwareDevice, CustomerGroup, CustomField, ScheduledReport,
    Notification, ReceiptTemplate,
)
from pos.pagination import CustomPagination
from system.serializers import (
    StoreSerializer, HardwareDeviceSerializer, CustomerGroupSerializer,
    CustomFieldSerializer, ScheduledReportSerializer, NotificationSerializer,
    ReceiptTemplateSerializer,
)


class _BaseListView(APIView):
    """Tenant-owned CRUD base used only by records with a canonical tenant FK."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    model = None
    serializer_class = None
    search_fields = []

    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "manage"
        return [permission() for permission in self.permission_classes]

    def get_queryset(self, request):
        qs = self.model.objects.filter(tenant=request.tenant)
        search = request.GET.get("search", "").strip()
        if search and self.search_fields:
            q = Q()
            for f in self.search_fields:
                q |= Q(**{f"{f}__icontains": search})
            qs = qs.filter(q)
        return qs

    def get(self, request):
        qs = self.get_queryset(request)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = self.serializer_class(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save(tenant=request.tenant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class _BaseDetailView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    model = None
    serializer_class = None

    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "manage"
        return [permission() for permission in self.permission_classes]

    def get_object(self, request, pk):
        return get_object_or_404(self.model, tenant=request.tenant, pk=pk)

    def get(self, request, pk):
        return Response(self.serializer_class(self.get_object(request, pk)).data)

    def put(self, request, pk):
        obj = self.get_object(request, pk)
        serializer = self.serializer_class(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Stores (multi-store) ────────────────────────────────────────────────────
class StoreListView(_BaseListView):
    model = Store
    serializer_class = StoreSerializer
    search_fields = ["name", "code"]


class StoreDetailView(_BaseDetailView):
    model = Store
    serializer_class = StoreSerializer


# ─── Hardware Devices ─────────────────────────────────────────────────────────
class HardwareDeviceListView(_BaseListView):
    model = HardwareDevice
    serializer_class = HardwareDeviceSerializer
    search_fields = ["name", "address"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        device_type = request.GET.get("device_type")
        if device_type:
            qs = qs.filter(device_type=device_type)
        return qs


class HardwareDeviceDetailView(_BaseDetailView):
    model = HardwareDevice
    serializer_class = HardwareDeviceSerializer


class HardwareDeviceTestView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    """Fire a lightweight test action (e.g. open cash drawer / test print)."""

    def post(self, request, pk):
        device = get_object_or_404(HardwareDevice, tenant=request.tenant, pk=pk)
        if not device.is_active:
            return Response({"error": "Device is not active"}, status=status.HTTP_400_BAD_REQUEST)
        # Actual hardware I/O happens client-side (WebUSB/WebSerial/agent);
        # this endpoint just confirms the device is configured and logs the test.
        return Response({
            "message": f"Test signal queued for {device.name}",
            "device_type": device.device_type,
            "connection_type": device.connection_type,
        })


# ─── Customer Groups ──────────────────────────────────────────────────────────
class CustomerGroupListView(_BaseListView):
    model = CustomerGroup
    serializer_class = CustomerGroupSerializer
    search_fields = ["name", "description"]


class CustomerGroupDetailView(_BaseDetailView):
    model = CustomerGroup
    serializer_class = CustomerGroupSerializer


# ─── Custom Fields ─────────────────────────────────────────────────────────────
class CustomFieldListView(_BaseListView):
    model = CustomField
    serializer_class = CustomFieldSerializer
    search_fields = ["name"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        entity = request.GET.get("entity")
        if entity:
            qs = qs.filter(entity=entity)
        return qs


class CustomFieldDetailView(_BaseDetailView):
    model = CustomField
    serializer_class = CustomFieldSerializer


# ─── Scheduled Reports ─────────────────────────────────────────────────────────
class ScheduledReportListView(_BaseListView):
    model = ScheduledReport
    serializer_class = ScheduledReportSerializer
    search_fields = ["name"]


class ScheduledReportDetailView(_BaseDetailView):
    model = ScheduledReport
    serializer_class = ScheduledReportSerializer


# ─── Receipt Templates ─────────────────────────────────────────────────────────
class ReceiptTemplateListView(_BaseListView):
    model = ReceiptTemplate
    serializer_class = ReceiptTemplateSerializer
    search_fields = ["name"]


class ReceiptTemplateDetailView(_BaseDetailView):
    model = ReceiptTemplate
    serializer_class = ReceiptTemplateSerializer


# ─── Notifications (bell/inbox) ─────────────────────────────────────────────────
class NotificationListView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "view"

    def get(self, request):
        qs = Notification.objects.filter(tenant=request.tenant)
        unread_only = request.GET.get("unread_only")
        if unread_only in ("1", "true", "True"):
            qs = qs.filter(is_read=False)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = NotificationSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data)
        paged.data["unread_count"] = Notification.objects.filter(is_read=False, tenant=request.tenant).count()
        return paged

    def post(self, request):
        serializer = NotificationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(tenant=request.tenant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "update"

    def post(self, request, pk):
        notif = get_object_or_404(Notification, pk=pk, tenant=request.tenant)
        notif.is_read = True
        notif.save()
        return Response(NotificationSerializer(notif).data)


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "update"

    def post(self, request):
        updated = Notification.objects.filter(
            is_read=False, tenant=request.tenant
        ).update(is_read=True)
        return Response({"marked_read": updated})


class NotificationDeleteView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "settings"
    rbac_action = "manage"

    def delete(self, request, pk):
        get_object_or_404(Notification, pk=pk, tenant=request.tenant).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


