from django.urls import path

from .views import (
    CustomerAddressDetailView, CustomerAddressListCreateView, CustomerCreditLimitView,
    CustomerDocumentDetailView, CustomerDocumentDownloadView, CustomerDocumentListCreateView,
    CustomerLoyaltyHistoryView, CustomerNoteDetailView, CustomerNoteListCreateView,
)

urlpatterns = [
    path("customers/<int:customer_id>/addresses/", CustomerAddressListCreateView.as_view()),
    path("customer-addresses/<int:pk>/", CustomerAddressDetailView.as_view()),
    path("customers/<int:customer_id>/credit-limit/", CustomerCreditLimitView.as_view()),
    path("customers/<int:customer_id>/documents/", CustomerDocumentListCreateView.as_view()),
    path("customer-documents/<int:pk>/", CustomerDocumentDetailView.as_view()),
    path("customer-documents/<int:pk>/download/", CustomerDocumentDownloadView.as_view()),
    path("customers/<int:customer_id>/notes/", CustomerNoteListCreateView.as_view()),
    path("customer-notes/<int:pk>/", CustomerNoteDetailView.as_view()),
    path("customers/<int:customer_id>/loyalty/", CustomerLoyaltyHistoryView.as_view()),
]
