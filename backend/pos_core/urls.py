from django.urls import path
from .views import (
    ParkListCreateView, ResumeParkView,
    LayawayCreateView, LayawayInstallmentView,
    SplitBillCreateView, SplitSharePayView,
    ExchangeListCreateView,
    OfflineEnqueueView, OfflineSyncNowView,
    ReceiptTemplateListCreateView, ReceiptTemplateDetailView,
    DrawerEventListCreateView,
)

urlpatterns = [
    path("park/", ParkListCreateView.as_view()),
    path("park/<int:pk>/resume/", ResumeParkView.as_view()),
    path("orders/<int:order_id>/layaway/", LayawayCreateView.as_view()),
    path("layaways/<int:pk>/installment/", LayawayInstallmentView.as_view()),
    path("orders/<int:order_id>/split/", SplitBillCreateView.as_view()),
    path("split-shares/<int:share_id>/pay/", SplitSharePayView.as_view()),
    path("exchanges/", ExchangeListCreateView.as_view()),
    path("offline/enqueue/", OfflineEnqueueView.as_view()),
    path("offline/sync/", OfflineSyncNowView.as_view()),
    path("receipt-templates/", ReceiptTemplateListCreateView.as_view()),
    path("receipt-templates/<int:pk>/", ReceiptTemplateDetailView.as_view()),
    path("drawer-events/", DrawerEventListCreateView.as_view()),
]