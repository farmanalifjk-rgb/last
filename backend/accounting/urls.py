from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accounting.views import (
    AccountingEventViewSet,
    AccountingPeriodViewSet,
    BalanceSheetView,
    CashFlowReportView,
    ChartOfAccountViewSet,
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    FinancialAccountMappingViewSet,
    JournalEntryViewSet,
    LedgerView,
    ProfitLossReportView,
    PostingRuleViewSet,
    TrialBalanceView,
)

router = DefaultRouter()
router.register(r"accounting/accounts", ChartOfAccountViewSet, basename="accounting-accounts")
router.register(r"accounting/journal", JournalEntryViewSet, basename="accounting-journal")
router.register(r"accounting/expense-categories", ExpenseCategoryViewSet, basename="expense-categories")
router.register(r"accounting/expenses", ExpenseViewSet, basename="expenses")
router.register(r"accounting/periods", AccountingPeriodViewSet, basename="accounting-periods")
router.register(r"accounting/posting-rules", PostingRuleViewSet, basename="accounting-posting-rules")
router.register(r"accounting/financial-account-mappings", FinancialAccountMappingViewSet, basename="accounting-financial-account-mappings")
router.register(r"accounting/events", AccountingEventViewSet, basename="accounting-events")

urlpatterns = [
    path("", include(router.urls)),
    path("accounting/ledger/<int:account_id>/", LedgerView.as_view(), name="accounting-ledger"),
    path("accounting/trial-balance/", TrialBalanceView.as_view(), name="accounting-trial-balance"),
    path("reports/profit-loss/", ProfitLossReportView.as_view(), name="reports-profit-loss"),
    path("reports/balance-sheet/", BalanceSheetView.as_view(), name="reports-balance-sheet"),
    path("reports/cash-flow/", CashFlowReportView.as_view(), name="reports-cash-flow"),
]
