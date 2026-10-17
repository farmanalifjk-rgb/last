from django.urls import path
from .views import (ProductTaxAssignmentDetailView, ProductTaxAssignmentListCreateView, TaxRateListCreateView, TaxRateDetailView,
                    TaxExemptionListCreateView, TaxExemptionDetailView,
                    PreviewLineTaxView, ComputeOrderTaxView, TaxBreakdownByOrderView, TaxReportView)

urlpatterns = [
    path("rates/", TaxRateListCreateView.as_view()),
    path("rates/<int:pk>/", TaxRateDetailView.as_view()),
    path("products/<int:product_id>/assignments/", ProductTaxAssignmentListCreateView.as_view()),
    path("products/<int:product_id>/assignments/<int:pk>/", ProductTaxAssignmentDetailView.as_view()),
    path("exemptions/", TaxExemptionListCreateView.as_view()),
    path("exemptions/<int:pk>/", TaxExemptionDetailView.as_view()),
    path("preview-line/", PreviewLineTaxView.as_view()),
    path("orders/<int:order_id>/compute/", ComputeOrderTaxView.as_view()),
    path("breakdowns/", TaxBreakdownByOrderView.as_view()),
    path("report/", TaxReportView.as_view()),
]
