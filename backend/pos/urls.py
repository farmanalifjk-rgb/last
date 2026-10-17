from django.urls import include, path
from rest_framework.routers import DefaultRouter

# pyrefly: ignore [missing-import]
from .views.categories import CategoryViewSet
from customers.views import CustomerViewSet
from system.customer_groups import CustomerGroupViewSet
from system.views import ReadinessHealthView
# pyrefly: ignore [missing-import]
from .views.products import ProductViewSet

router = DefaultRouter()
router.register("products", ProductViewSet, basename="products")
router.register("categories", CategoryViewSet, basename="categories")
router.register("customers", CustomerViewSet, basename="customers")
router.register("customer-groups", CustomerGroupViewSet, basename="customer-groups")

urlpatterns = [
    path("api/health/", ReadinessHealthView.as_view(), name="readiness-health"),
    path("", include("dashboard.urls")),
    path("api/", include(router.urls)),

    # Phase 6 canonical POS transaction APIs. Older POS route groups are retired
    # rather than leaving multiple checkout/session/refund engines public.
    path("api/pos/", include("pos.api_urls.canonical")),
    path("api/", include("pos.api_urls.auth_secure")),
    # The legacy POS purchasing routes are retired. The canonical Suppliers and
    # Purchasing APIs live under /api/suppliers/ and /api/purchasing/ below.
    path("api/", include("pos.api_urls.company")),
    path("api/", include("pos.api_urls.products")),
    path("api/", include("pos.api_urls.customers")),
    # The former products-management endpoints are retired. Canonical catalog
    # APIs under /api/products/, /api/categories/, and /api/catalog/ enforce
    # SaaS tenant scoping and backend RBAC consistently.
    path("api/", include("pos.api_urls.reports")),
    path("api/", include("pos.api_urls.configuration")),
    path("api/", include("pos.api_urls.settings_extra")),

    # Canonical accounting APIs are exposed at /api/accounting/*.
    path("api/", include("accounting.urls")),
    path("api/", include("loyalty.urls")),
    path("api/", include("operations.urls")),
    path("api/saas/", include("saas.urls")),
    path("api/catalog/", include("catalog.urls")),
    path("api/pricing/", include("pricing.urls")),
    path("api/inventory/", include("inventory.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/", include("customers.urls")),
    path("api/", include("suppliers.urls")),
    path("api/transfers/", include("transfers.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/tax/", include("tax.urls")),
    path("api/fiscal/", include("fiscal.urls")),
    path("api/fbr/", include("fbr.urls")),
    # Local IMS simulator is development/test sandbox only; it fails closed elsewhere.
    path("api/fbr-simulator/", include("fbr.simulator_urls")),
    path("api/", include("hr.urls")),
    path("api/audit/", include("audit.urls")),
    path("api/rbac/", include("rbac.urls")),
    # Legacy tenancy routes are retired; the SaaS tenant API is canonical.
    path("api/i18n/", include("i18n_app.urls")),
    path("api/integrations/", include("integrations.urls")),
    path("api/ai/", include("ai.urls")),
    # Notifications are a tenant-scoped, RBAC-protected public domain API.
    path("api/notifications/", include("notifications.urls")),
]
