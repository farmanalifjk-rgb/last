from django.db import transaction
from django.shortcuts import get_object_or_404

from pos.models import CashSession, Company, Customer, DraftOrder, DraftOrderItem, Order, Product
from ..serializers import DraftOrderItemSerializer, DraftOrderSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, status
from django.utils import timezone
from django.http import HttpResponse
from ..filters import get_filtered_drafts
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.platypus import (SimpleDocTemplate,Table,TableStyle)
from io import BytesIO
from reportlab.platypus import Table, TableStyle
from ..pdf_helpers import add_company_header, add_report_info, add_report_title, style_report_table
from ..helpers import sanitize_csv_cell, add_page_footer, build_export_filename
from rest_framework.permissions import IsAuthenticated
from saas.permissions import HasActiveTenant, TenantRBACPermission



class DraftNoteView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def post(self, request):
        draft = get_object_or_404(DraftOrder, pk=request.data.get("draft_id"), tenant=request.tenant)
        draft.note = request.data.get("note", "")
        draft.save(update_fields=["note"])
        return Response({"success": True})


class DraftOrderListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"
    serializer_class = DraftOrderSerializer

    def get_queryset(self):
        session = CashSession.objects.filter(tenant=self.request.tenant, is_open=True).first()
        if session is None:
            return DraftOrder.objects.none()
        return DraftOrder.objects.filter(
            tenant=self.request.tenant,
            session=session,
            status="draft"
        ).order_by("order_number")


class DraftOrderCreateView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    @transaction.atomic
    def post(self, request):
        session = CashSession.objects.select_for_update().filter(tenant=request.tenant, is_open=True).first()
        if not session:
            return Response({"error": "No active session"}, status=400)
        draft = DraftOrder.objects.create(
            tenant=request.tenant,
            session=session,
            order_number=session.next_draft_number
        )
        session.next_draft_number += 1
        session.save(update_fields=["next_draft_number"])
        return Response({"id": draft.id, "order_number": draft.order_number})


class AddDraftItemView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    @transaction.atomic
    def post(self, request):
        draft_id = request.data.get("draft_id")
        product_id = request.data.get("product_id")
        product = get_object_or_404(Product, pk=product_id, tenant=request.tenant)
        draft = get_object_or_404(DraftOrder, pk=draft_id, tenant=request.tenant)
        # Ensure product and draft belong to same session tenant implicitly via tenant FK, but also verify session tenant matches
        if draft.tenant_id != request.tenant.id or product.tenant_id != request.tenant.id:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        item = DraftOrderItem.objects.select_for_update().filter(
            tenant=request.tenant,
            draft_order=draft,
            product_id=product_id
        ).first()
        if item:
            item.quantity += 1
            item.save(update_fields=["quantity"])
        else:
            DraftOrderItem.objects.create(
                tenant=request.tenant,
                draft_order=draft,
                product=product,
                quantity=1,
                unit_price=product.sales_price
            )
        return Response({"success": True})


class DraftOrderDetailView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    def get(self, request, draft_id):
        draft = get_object_or_404(DraftOrder, pk=draft_id, tenant=request.tenant)
        subtotal = sum(
            item.product.sales_price * item.quantity
            for item in draft.items.select_related("product").all()
        )
        return Response({
            "id": draft.id,
            "order_number": draft.order_number,
            "customer": draft.customer.name if draft.customer else "Walk-in Customer",
            "payment_method": "-",
            "status": "draft",
            "subtotal": subtotal,
            "discount": 0,
            "tax": 0,
            "total": subtotal,
            "amount_received": 0,
            "change_amount": 0,
            "created_at": draft.created_at,
            "items": DraftOrderItemSerializer(
                draft.items.select_related("product").all(),
                many=True
            ).data
        })

class DraftItemDecreaseView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    @transaction.atomic
    def post(self, request):
        draft_id = request.data.get("draft_id")
        product_id = request.data.get("product_id")
        # Verify draft belongs to tenant first to avoid leaking existence
        draft = get_object_or_404(DraftOrder, pk=draft_id, tenant=request.tenant)
        product = get_object_or_404(Product, pk=product_id, tenant=request.tenant)
        item = DraftOrderItem.objects.select_for_update().filter(
            tenant=request.tenant,
            draft_order=draft,
            product=product
        ).first()
        if not item:
            return Response({"error": "Not found"}, status=404)
        if item.quantity > 1:
            item.quantity -= 1
            item.save(update_fields=["quantity"])
        else:
            item.delete()
        return Response({"success": True})


class DraftItemRemoveView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"

    @transaction.atomic
    def post(self, request):
        draft_id = request.data.get("draft_id")
        product_id = request.data.get("product_id")
        draft = get_object_or_404(DraftOrder, pk=draft_id, tenant=request.tenant)
        product = get_object_or_404(Product, pk=product_id, tenant=request.tenant)
        DraftOrderItem.objects.filter(
            tenant=request.tenant,
            draft_order=draft,
            product=product
        ).delete()
        return Response({"success": True})


class DraftHistoryExportExcelView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request):

        drafts = get_filtered_drafts(request)

        workbook = Workbook()
        sheet = workbook.active

        sheet.title = "Draft Orders"
        sheet.freeze_panes = "A2"

        headers = [
            "Draft No",
            "Customer",
            "Session",
            "Date",
        ]

        sheet.append(headers)

        header_fill = PatternFill(
            fill_type="solid",
            fgColor="1F4E78"
        )

        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")



        for draft in drafts:

            sheet.append([
                draft.order_number,
                draft.customer.name if draft.customer else "Walk-in Customer",
                str(draft.session),
                draft.created_at.strftime("%Y-%m-%d %H:%M"),
            ])

        sheet.auto_filter.ref = sheet.dimensions

        for column_cells in sheet.columns:

            length = max(
                len(str(cell.value)) if cell.value else 0
                for cell in column_cells
            )

            sheet.column_dimensions[
                column_cells[0].column_letter
            ].width = length + 3

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        filename = build_export_filename(request,"draft_orders","xlsx")

        response["Content-Disposition"] = (f'attachment; filename=\"{filename}\"')

        workbook.save(response)

        return response


class DraftHistoryExportPDFView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request):

        buffer = BytesIO()

        doc = SimpleDocTemplate(buffer)

        company = Company.objects.filter(tenant=request.tenant).first()

        story = []

        add_company_header(
            story,
            company,
        )

        add_report_title(
            story,
            "DRAFT HISTORY REPORT",
        )

        drafts = get_filtered_drafts(request)

        generated = timezone.localtime().strftime("%d-%b-%Y %I:%M %p")

        report_info = [["Generated", generated]]

        add_report_info(story,report_info,)

        table_data = [[
            "S.No",
            "Order No",
            "Customer",
            "Date",
        ]]

        for index, draft in enumerate(drafts, start=1):

            table_data.append([

                index,

                draft.order_number,

                draft.customer.name
                if draft.customer
                else "Walk-in Customer",

                draft.created_at.strftime("%d-%b-%Y"),

            ])

        table = Table(
            table_data,
            colWidths=[35, 70, 120, 80,],
            repeatRows=1,
        )

        style_report_table(table,len(table_data),)

        table.setStyle(TableStyle([

            ("ALIGN", (0, 0), (0, -1), "CENTER"),  # S.No

            ("ALIGN", (5, 1), (5, -1), "RIGHT"),   # Amount

        ]))

        story.append(table)

        doc.build(
            story,
            onFirstPage=add_page_footer,
            onLaterPages=add_page_footer,
        )

        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(
            pdf,
            content_type="application/pdf",
        )

        filename = build_export_filename(
            request,
            "drafts",
            "pdf",
        )

        response["Content-Disposition"] = (
            f'attachment; filename=\"{filename}\"'
        )

        return response
