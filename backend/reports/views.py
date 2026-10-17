import csv
from io import StringIO

from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from saas.permissions import HasActiveTenant, TenantRBACPermission

from .services import (
    ReportingValidationError,
    customer_sales,
    date_range,
    financial_balance_sheet,
    financial_dashboard,
    financial_exceptions,
    financial_general_ledger,
    financial_profit_loss,
    financial_trial_balance,
    financial_trial_balance_v2,
    inventory_valuation,
    pagination,
    purchase_summary,
    sales_by_category,
    sales_by_day,
    sales_by_payment_method,
    sales_by_product,
    sales_summary,
    stock_movements,
    supplier_spend,
)


class ReportPermissionMixin(APIView):
    rbac_module = "reports"
    rbac_action = "view"
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]

    def date_filters(self, request):
        try:
            return date_range(start=request.query_params.get("start"), end=request.query_params.get("end"))
        except ReportingValidationError as exc:
            raise ValidationError({"detail": str(exc)})

    def page_filters(self, request):
        try:
            return pagination(page=request.query_params.get("page", 1), page_size=request.query_params.get("page_size", 50))
        except ReportingValidationError as exc:
            raise ValidationError({"detail": str(exc)})


class SalesSummaryView(ReportPermissionMixin):
    def get(self, request):
        start, end = self.date_filters(request)
        return Response(sales_summary(tenant=request.tenant, start=start, end=end))


class SalesByDayView(ReportPermissionMixin):
    def get(self, request):
        start, end = self.date_filters(request)
        return Response(sales_by_day(tenant=request.tenant, start=start, end=end))


class TopProductsView(ReportPermissionMixin):
    def get(self, request):
        start, end = self.date_filters(request)
        page, page_size = self.page_filters(request)
        return Response(sales_by_product(tenant=request.tenant, start=start, end=end, page=page, page_size=page_size))


class SalesByCategoryView(ReportPermissionMixin):
    def get(self, request):
        start, end = self.date_filters(request)
        return Response(sales_by_category(tenant=request.tenant, start=start, end=end))


class SalesByPaymentMethodView(ReportPermissionMixin):
    def get(self, request):
        start, end = self.date_filters(request)
        return Response(sales_by_payment_method(tenant=request.tenant, start=start, end=end))


class CustomerSalesView(ReportPermissionMixin):
    def get(self, request):
        start, end = self.date_filters(request)
        page, page_size = self.page_filters(request)
        return Response(customer_sales(tenant=request.tenant, start=start, end=end, page=page, page_size=page_size))


class InventoryValuationView(ReportPermissionMixin):
    def get(self, request):
        page, page_size = self.page_filters(request)
        return Response(inventory_valuation(tenant=request.tenant, page=page, page_size=page_size))


class StockMovementView(ReportPermissionMixin):
    def get(self, request):
        start, end = self.date_filters(request)
        page, page_size = self.page_filters(request)
        return Response(stock_movements(
            tenant=request.tenant,
            start=start,
            end=end,
            page=page,
            page_size=page_size,
            movement_type=request.query_params.get("movement_type"),
        ))


class PurchaseSummaryView(ReportPermissionMixin):
    def get(self, request):
        start, end = self.date_filters(request)
        return Response(purchase_summary(tenant=request.tenant, start=start, end=end))


class SupplierSpendView(ReportPermissionMixin):
    def get(self, request):
        start, end = self.date_filters(request)
        page, page_size = self.page_filters(request)
        return Response(supplier_spend(tenant=request.tenant, start=start, end=end, page=page, page_size=page_size))


class FinancialTrialBalanceView(ReportPermissionMixin):
    """Financial data only from posted canonical ledger lines; not a full financial statement."""

    rbac_module = "accounting"
    rbac_action = "view"

    def get(self, request):
        try:
            return Response(financial_trial_balance_v2(
                tenant=request.tenant,
                start=request.query_params.get("start"),
                end=request.query_params.get("end"),
                period_id=request.query_params.get("period"),
            ))
        except ReportingValidationError as exc:
            raise ValidationError({"detail": str(exc)})


class FinancialGeneralLedgerView(FinancialTrialBalanceView):
    def get(self, request, account_id):
        try:
            page, page_size = self.page_filters(request)
            return Response(financial_general_ledger(
                tenant=request.tenant, account_id=account_id,
                start=request.query_params.get("start"), end=request.query_params.get("end"),
                period_id=request.query_params.get("period"), page=page, page_size=page_size,
            ))
        except ReportingValidationError as exc:
            raise ValidationError({"detail": str(exc)})


class FinancialDashboardView(FinancialTrialBalanceView):
    def get(self, request):
        try:
            return Response(financial_dashboard(
                tenant=request.tenant, start=request.query_params.get("start"),
                end=request.query_params.get("end"), period_id=request.query_params.get("period"),
            ))
        except ReportingValidationError as exc:
            raise ValidationError({"detail": str(exc)})


class FinancialExceptionsView(FinancialTrialBalanceView):
    def get(self, request):
        try:
            page, page_size = self.page_filters(request)
            return Response(financial_exceptions(
                tenant=request.tenant, start=request.query_params.get("start"),
                end=request.query_params.get("end"), page=page, page_size=page_size,
            ))
        except ReportingValidationError as exc:
            raise ValidationError({"detail": str(exc)})


class FinancialProfitLossView(FinancialTrialBalanceView):
    def get(self, request):
        try:
            result = financial_profit_loss(
                tenant=request.tenant, start=request.query_params.get("start"),
                end=request.query_params.get("end"), period_id=request.query_params.get("period"),
            )
        except ReportingValidationError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(result, status=status.HTTP_200_OK if result["status"] == "implemented" else status.HTTP_409_CONFLICT)


class FinancialBalanceSheetView(FinancialTrialBalanceView):
    def get(self, request):
        try:
            result = financial_balance_sheet(
                tenant=request.tenant, as_of=request.query_params.get("as_of"), period_id=request.query_params.get("period"),
            )
        except ReportingValidationError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(result, status=status.HTTP_200_OK if result["status"] == "implemented" else status.HTTP_409_CONFLICT)


class FinancialCashFlowView(FinancialTrialBalanceView):
    def get(self, request):
        return Response({
            "status": "accounting_policy_required",
            "detail": "Cash-flow method and cash/bank classification policy are required before a cash-flow statement can be calculated.",
        }, status=status.HTTP_409_CONFLICT)


class LegacyUnsupportedFinancialView(ReportPermissionMixin):
    """Preserve deprecated paths without fabricating cost, cash-flow, or statement calculations."""

    def get(self, request):
        return Response(
            {"detail": "This financial statement is not available: statement mapping and accounting policy support are required."},
            status=status.HTTP_409_CONFLICT,
        )


class ReportExportView(ReportPermissionMixin):
    rbac_action = "export"

    def get(self, request, report_key):
        start, end = self.date_filters(request)
        page, page_size = self.page_filters(request)
        report_map = {
            "sales-by-day": lambda: sales_by_day(tenant=request.tenant, start=start, end=end),
            "sales-by-category": lambda: sales_by_category(tenant=request.tenant, start=start, end=end),
            "sales-by-payment": lambda: sales_by_payment_method(tenant=request.tenant, start=start, end=end),
            "sales-by-product": lambda: sales_by_product(tenant=request.tenant, start=start, end=end, page=page, page_size=page_size)["results"],
            "customer-sales": lambda: customer_sales(tenant=request.tenant, start=start, end=end, page=page, page_size=page_size)["results"],
            "stock-movements": lambda: stock_movements(tenant=request.tenant, start=start, end=end, page=page, page_size=page_size)["results"],
            "supplier-spend": lambda: supplier_spend(tenant=request.tenant, start=start, end=end, page=page, page_size=page_size)["results"],
            "financial-trial-balance": lambda: financial_trial_balance_v2(tenant=request.tenant, start=request.query_params.get("start"), end=request.query_params.get("end"), period_id=request.query_params.get("period"))["rows"],
        }
        producer = report_map.get(report_key)
        if producer is None:
            raise ValidationError({"detail": "This report is not exportable."})
        rows = producer()
        output = StringIO()
        headers = list(rows[0].keys()) if rows else []
        writer = csv.DictWriter(output, fieldnames=headers)
        if headers:
            writer.writeheader()
            writer.writerows(rows)
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{report_key}.csv"'
        return response
