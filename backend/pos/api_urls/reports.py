from django.urls import path
from ..views.reports import *

urlpatterns = [
    # Sales Report
    path("reports/sales/", SalesReportView.as_view()),
    path("reports/sales/export/csv/", SalesReportExportCSVView.as_view()),
    path("reports/sales/export/excel/", SalesReportExportExcelView.as_view()),
    path("reports/sales/export/pdf/", SalesReportExportPDFView.as_view()),

    # Product Report
    path("reports/products/", ProductReportView.as_view()),
    path("reports/products/export/csv/", ProductReportExportCSVView.as_view()),
    path("reports/products/export/excel/", ProductReportExportExcelView.as_view()),
    path("reports/products/export/pdf/", ProductReportExportPDFView.as_view()),

    # Stock Report
    path("reports/stock/", StockReportView.as_view()),
    path("reports/stock/export/csv/", StockReportExportCSVView.as_view()),
    path("reports/stock/export/excel/", StockReportExportExcelView.as_view()),
    path("reports/stock/export/pdf/", StockReportExportPDFView.as_view()),

    # Tax Report
    path("reports/tax/", TaxReportView.as_view()),
    path("reports/tax/export/csv/", TaxReportExportCSVView.as_view()),
    path("reports/tax/export/excel/", TaxReportExportExcelView.as_view()),
    path("reports/tax/export/pdf/", TaxReportExportPDFView.as_view()),
]
