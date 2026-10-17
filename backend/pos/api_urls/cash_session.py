from django.urls import path
from ..views.cash_session import *
from ..views.cash_session_export import *

urlpatterns = [
    path("cash-sessions/", CashSessionListView.as_view()),
    path("cash-sessions/<int:pk>/close/", CashSessionCloseView.as_view()),
    path("cash-sessions/<int:pk>/timeline/", CashSessionTimelineView.as_view()),
    path("cash-sessions/<int:pk>/<str:action>/", CashTransactionView.as_view()),
    path("cash-sessions/cashiers/", CashSessionCashiersView.as_view()),
    path("cash-sessions/export/csv/", CashSessionExportCSVView.as_view()),
    path("cash-sessions/export/excel/", CashSessionExportExcelView.as_view()),
    path("cash-sessions/export/pdf/", CashSessionExportPDFView.as_view()),
]