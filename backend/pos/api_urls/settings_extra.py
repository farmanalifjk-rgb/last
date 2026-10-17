from django.urls import path
from system.views import (
    CompanySettingsView, POSSettingsView, InventorySettingsView, TaxSettingsView,
    ReceiptSettingsView, NotificationSettingsView, BarcodeSettingsView,
    CustomerSettingsView, ProductSettingsView, SecuritySettingsView,
    BackupSettingsView, DataManagementSettingsView, ReportSettingsView,
    AppearanceSettingsView, FeatureFlagsView, AboutInfoView, CheckUpdatesView,
    SettingsBundleView,
)
from system.views import (
    StoreListView, StoreDetailView,
    HardwareDeviceListView, HardwareDeviceDetailView, HardwareDeviceTestView,
    CustomerGroupListView, CustomerGroupDetailView,
    CustomFieldListView, CustomFieldDetailView,
    ScheduledReportListView, ScheduledReportDetailView,
    ReceiptTemplateListView, ReceiptTemplateDetailView,
)
from system.views import (
    PasswordPolicyCheckView, LoginAttemptListView,
    TrustedDeviceListView, TrustedDeviceAuthorizeView, TrustedDeviceRevokeView, TrustedDeviceDeleteView,
)
from system.views import (
    BackupListView, BackupCreateView, BackupDownloadView, BackupRestoreView,
    ExportDatabaseView, ImportDatabaseView,
    ExportProductsView, ImportProductsView, ExportCustomersView, ImportCustomersView,
    ExportInventoryView, ExportSalesView, ClearCacheView, RebuildSearchIndexView, OptimizeDatabaseView,
)
from system.views import (
    EmailTemplateListView, EmailTemplateDetailView,
    SMSTemplateListView, SMSTemplateDetailView,
)
from system.operations_facade import (
    APIKeyListView, APIKeyDetailView, APIKeyRegenerateView,
    WebhookListView, WebhookDetailView, WebhookTestView, WebhookDeliveryListView,
    ErrorLogListView, ErrorLogResolveView, SystemHealthView,
)

urlpatterns = [
    # ─── One-shot bundle ────────────────────────────────────────────────────
    path("settings/all/", SettingsBundleView.as_view()),

    # ─── 1 & 2. General / Company ───────────────────────────────────────────
    path("settings/company/", CompanySettingsView.as_view()),

    # ─── 3. POS ──────────────────────────────────────────────────────────────
    path("settings/pos/", POSSettingsView.as_view()),

    # ─── 4. Inventory ────────────────────────────────────────────────────────
    path("settings/inventory/", InventorySettingsView.as_view()),

    # ─── 5. Taxes (global config; individual Tax rows are at /api/taxes/) ──
    path("settings/tax/", TaxSettingsView.as_view()),

    # ─── 7. Receipt ──────────────────────────────────────────────────────────
    path("settings/receipt/", ReceiptSettingsView.as_view()),
    path("settings/receipt/templates/", ReceiptTemplateListView.as_view()),
    path("settings/receipt/templates/<int:pk>/", ReceiptTemplateDetailView.as_view()),

    # ─── 9. Notification settings ───────────────────────────────────────────
    path("settings/notifications/", NotificationSettingsView.as_view()),

    # ─── 10 / 19. Hardware ───────────────────────────────────────────────────
    path("hardware-devices/", HardwareDeviceListView.as_view()),
    path("hardware-devices/<int:pk>/", HardwareDeviceDetailView.as_view()),
    path("hardware-devices/<int:pk>/test/", HardwareDeviceTestView.as_view()),
    path("settings/barcode/", BarcodeSettingsView.as_view()),

    # ─── 3. Stores (multi-store) ─────────────────────────────────────────────
    path("stores/", StoreListView.as_view()),
    path("stores/<int:pk>/", StoreDetailView.as_view()),

    # ─── 12. Customer ────────────────────────────────────────────────────────
    path("settings/customer/", CustomerSettingsView.as_view()),
    path("customer-groups/", CustomerGroupListView.as_view()),
    path("customer-groups/<int:pk>/", CustomerGroupDetailView.as_view()),

    # ─── 13. Product ─────────────────────────────────────────────────────────
    path("settings/product/", ProductSettingsView.as_view()),
    path("custom-fields/", CustomFieldListView.as_view()),
    path("custom-fields/<int:pk>/", CustomFieldDetailView.as_view()),

    # ─── 14. Security ────────────────────────────────────────────────────────
    path("settings/security/", SecuritySettingsView.as_view()),
    path("security/password-policy-check/", PasswordPolicyCheckView.as_view()),
    path("security/login-attempts/", LoginAttemptListView.as_view()),
    path("security/trusted-devices/", TrustedDeviceListView.as_view()),
    path("security/trusted-devices/<int:pk>/authorize/", TrustedDeviceAuthorizeView.as_view()),
    path("security/trusted-devices/<int:pk>/revoke/", TrustedDeviceRevokeView.as_view()),
    path("security/trusted-devices/<int:pk>/", TrustedDeviceDeleteView.as_view()),

    # ─── 15. Backup & Restore ────────────────────────────────────────────────
    path("settings/backup/", BackupSettingsView.as_view()),
    path("backups/", BackupListView.as_view()),
    path("backups/create/", BackupCreateView.as_view()),
    path("backups/<int:pk>/download/", BackupDownloadView.as_view()),
    path("backups/restore/", BackupRestoreView.as_view()),
    path("backups/export-database/", ExportDatabaseView.as_view()),
    path("backups/import-database/", ImportDatabaseView.as_view()),

    # ─── 16. Data Management ─────────────────────────────────────────────────
    path("settings/data-management/", DataManagementSettingsView.as_view()),
    path("data/export/products/", ExportProductsView.as_view()),
    path("data/import/products/", ImportProductsView.as_view()),
    path("data/export/customers/", ExportCustomersView.as_view()),
    path("data/import/customers/", ImportCustomersView.as_view()),
    path("data/export/inventory/", ExportInventoryView.as_view()),
    path("data/export/sales/", ExportSalesView.as_view()),
    path("data/clear-cache/", ClearCacheView.as_view()),
    path("data/rebuild-search-index/", RebuildSearchIndexView.as_view()),
    path("data/optimize-database/", OptimizeDatabaseView.as_view()),

    # ─── 17. Reports ─────────────────────────────────────────────────────────
    path("settings/reports/", ReportSettingsView.as_view()),
    path("scheduled-reports/", ScheduledReportListView.as_view()),
    path("scheduled-reports/<int:pk>/", ScheduledReportDetailView.as_view()),

    # ─── 18. Appearance ──────────────────────────────────────────────────────
    path("settings/appearance/", AppearanceSettingsView.as_view()),

    # ─── Feature flags ───────────────────────────────────────────────────────
    path("settings/feature-flags/", FeatureFlagsView.as_view()),

    # ─── Developer / Integrations ────────────────────────────────────────────
    path("api-keys/", APIKeyListView.as_view()),
    path("api-keys/<int:pk>/", APIKeyDetailView.as_view()),
    path("api-keys/<int:pk>/regenerate/", APIKeyRegenerateView.as_view()),
    path("webhooks/", WebhookListView.as_view()),
    path("webhooks/<int:pk>/", WebhookDetailView.as_view()),
    path("webhooks/<int:pk>/test/", WebhookTestView.as_view()),
    path("webhooks/<int:pk>/deliveries/", WebhookDeliveryListView.as_view()),
    path("email-templates/", EmailTemplateListView.as_view()),
    path("email-templates/<int:pk>/", EmailTemplateDetailView.as_view()),
    path("sms-templates/", SMSTemplateListView.as_view()),
    path("sms-templates/<int:pk>/", SMSTemplateDetailView.as_view()),

    # ─── System health / error logs ──────────────────────────────────────────
    path("error-logs/", ErrorLogListView.as_view()),
    path("error-logs/<int:pk>/resolve/", ErrorLogResolveView.as_view()),
    path("system-health/", SystemHealthView.as_view()),

    # ─── 20. About ───────────────────────────────────────────────────────────
    path("settings/about/", AboutInfoView.as_view()),
    path("settings/about/check-updates/", CheckUpdatesView.as_view()),
]
