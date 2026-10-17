from django.urls import path
from .views import (
    InvoiceSequenceListCreateView, InvoiceSequenceDetailView, FiscalInvoiceListView, FiscalInvoiceDetailView,
    IssueInvoiceView, CancelInvoiceView, FiscalDeviceListCreateView,
    SubmitToDeviceView, InvoiceXMLView, SubmissionListView,
)

urlpatterns = [
    path("sequences/", InvoiceSequenceListCreateView.as_view()),
    path("sequences/<int:pk>/", InvoiceSequenceDetailView.as_view()),
    path("invoices/", FiscalInvoiceListView.as_view()),
    path("invoices/<int:pk>/", FiscalInvoiceDetailView.as_view()),
    path("invoices/issue/", IssueInvoiceView.as_view()),
    path("invoices/<int:pk>/cancel/", CancelInvoiceView.as_view()),
    path("invoices/<int:pk>/xml/", InvoiceXMLView.as_view()),
    path("devices/", FiscalDeviceListCreateView.as_view()),
    path("invoices/<int:invoice_id>/submit/", SubmitToDeviceView.as_view()),
    path("submissions/", SubmissionListView.as_view()),
]