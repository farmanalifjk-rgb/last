from django.urls import path
from ..views.orders import *

urlpatterns = [
    path('checkout/', CheckoutView.as_view()),
    path("receipt/<int:order_id>/", receipt),
    path("order-history/",OrderHistoryView.as_view()),
    path("order-history/<int:order_id>/",OrderDetailView.as_view()),
    path("order-history/export/csv/",OrderHistoryCSVExportView.as_view()),
    path("order-history/export/excel/",OrderHistoryExportExcelView.as_view(),),
    path("order-history/export/pdf/",OrderHistoryExportPDFView.as_view(),), 
    path("order-stats/",order_stats,name="order-stats"),
]