from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PurchaseOrderViewSet, PurchaseReturnViewSet, ReceiptDetailView, ReceiptListCreateView,
    SupplierContactDetailView, SupplierContactListCreateView, SupplierViewSet,
)

router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="suppliers")
router.register("purchasing/purchase-orders", PurchaseOrderViewSet, basename="purchase-orders")
router.register("purchasing/purchase-returns", PurchaseReturnViewSet, basename="purchase-returns")

urlpatterns = [
    path("", include(router.urls)),
    path("suppliers/<int:supplier_id>/contacts/", SupplierContactListCreateView.as_view(), name="supplier-contacts"),
    path("supplier-contacts/<int:pk>/", SupplierContactDetailView.as_view(), name="supplier-contact-detail"),
    path("purchasing/receipts/", ReceiptListCreateView.as_view(), name="purchase-receipts"),
    path("purchasing/receipts/<int:pk>/", ReceiptDetailView.as_view(), name="purchase-receipt-detail"),
]
