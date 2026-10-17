from django.urls import path

from .views import (
    IntegrationDetailView,
    IntegrationListCreateView,
    PushInvoiceView,
    SyncLogListView,
    SyncMappingListView,
    SyncView,
)

# Mounted by pos.urls at /api/integrations/.  Do not repeat the mount prefix in
# child patterns: the canonical collection endpoint is exactly /api/integrations/.
urlpatterns = [
    path("", IntegrationListCreateView.as_view()),
    path("<int:pk>/", IntegrationDetailView.as_view()),
    path("<int:integration_id>/sync/", SyncView.as_view()),
    path("<int:integration_id>/push-invoice/", PushInvoiceView.as_view()),
    path("logs/", SyncLogListView.as_view()),
    path("mappings/", SyncMappingListView.as_view()),
]
