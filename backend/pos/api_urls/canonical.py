from django.urls import path

from pos.views.canonical import (
    POSActiveSessionView,
    POSCashMovementView,
    POSCheckoutView,
    POSCustomerSearchView,
    POSOrderDetailView,
    POSOrderListView,
    POSParkedSaleListCreateView,
    POSParkedSaleResumeView,
    POSPreviewView,
    POSProductSearchView,
    POSReceiptPrintedView,
    POSReceiptView,
    POSRefundDetailView,
    POSRefundProcessView,
    POSSessionCloseView,
    POSSessionOpenView,
)


urlpatterns = [
    path("sessions/open/", POSSessionOpenView.as_view(), name="pos-session-open"),
    path("sessions/active/", POSActiveSessionView.as_view(), name="pos-session-active"),
    path("sessions/close/", POSSessionCloseView.as_view(), name="pos-session-close"),
    path("cash-movements/", POSCashMovementView.as_view(), name="pos-cash-movement"),
    path("products/", POSProductSearchView.as_view(), name="pos-products"),
    path("customers/", POSCustomerSearchView.as_view(), name="pos-customers"),
    path("preview/", POSPreviewView.as_view(), name="pos-preview"),
    path("checkout/", POSCheckoutView.as_view(), name="pos-checkout"),
    path("orders/", POSOrderListView.as_view(), name="pos-orders"),
    path("orders/<int:pk>/", POSOrderDetailView.as_view(), name="pos-order-detail"),
    path("orders/<int:order_id>/receipt/", POSReceiptView.as_view(), name="pos-receipt"),
    path("orders/<int:order_id>/receipt/printed/", POSReceiptPrintedView.as_view(), name="pos-receipt-printed"),
    path("parked-sales/", POSParkedSaleListCreateView.as_view(), name="pos-parked-sales"),
    path("parked-sales/<int:pk>/resume/", POSParkedSaleResumeView.as_view(), name="pos-parked-sale-resume"),
    path("refunds/order/<int:order_id>/", POSRefundDetailView.as_view(), name="pos-refund-detail"),
    path("refunds/", POSRefundProcessView.as_view(), name="pos-refunds"),
]
