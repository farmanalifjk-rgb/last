from rest_framework import viewsets
from pos.models import Company, Customer, DraftOrder, Order, OrderItem, Payment, RefundItem, Tax
from ..serializers import (
    DraftOrderHistorySerializer,
    OrderHistorySerializer,
    OrderSerializer,
)
from rest_framework.views import APIView
from decimal import Decimal
from rest_framework.decorators import api_view
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ..pagination import CustomPagination
import csv
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin

from ..filters import get_filtered_drafts, get_filtered_orders
from openpyxl import Workbook
from openpyxl.styles import *
from reportlab.platypus import (SimpleDocTemplate,Table,Paragraph,Spacer,)
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
from reportlab.platypus import Table
from ..pdf_helpers import (add_company_header, add_report_info, add_report_title, add_summary_table, getSampleStyleSheet, style_report_table)
from ..helpers import sanitize_csv_cell, add_page_footer, build_export_filename



class OrderViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    rbac_module = "pos"
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        if customer_id := self.request.query_params.get("customer"):
            queryset = queryset.filter(customer_id=customer_id)
        return queryset.order_by("-created_at")
 
    

@api_view(["GET"])
@permission_classes([IsAuthenticated, HasActiveTenant, TenantRBACPermission])
def receipt(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        tenant=request.tenant,
    )

    if order.status == "draft":
        return Response(
            {"error": "Draft orders cannot be printed."},
            status=400
        )

    company = Company.objects.filter(tenant=request.tenant).first()

    items = OrderItem.objects.filter(
        order=order
    ).select_related("product")

    return Response({

        "receipt_type": "sale",

        "company": {

            "name": company.name if company else "",
            "tagline": company.tagline if company else "",
            "address": company.address if company else "",
            "phone": company.phone if company else "",
            "email": company.email if company else "",
            "website": company.website if company else "",
            "tax_number": company.tax_number if company else "",
            "footer_message": company.footer_message if company else "",
            "currency": company.currency if company else "Rs",
            "logo": company.logo.url if company and company.logo else None,
            "receipt_paper": company.receipt_paper if company else "80mm",
            "gst": company.gst if company else "",
        },

        "order": {

            "id": order.id,
            "number": order.order_number,
            "date": order.created_at,
            "customer": order.customer.name if order.customer else "Walk-in Customer",
            "payment_method": order.payment_method,
            "status": order.status,
            "note": order.note

        },

        "items": [

            {

                "name": sanitize_csv_cell(item.product.name),
                "qty": item.quantity,
                "price": float(item.unit_price),
                "subtotal": float(item.subtotal)

            }

            for item in items

        ],

        "totals": {

            "subtotal": float(order.subtotal),
            "discount": float(order.discount),
            "tax": float(order.tax),
            "total": float(order.total),
            "paid": float(order.amount_received),
            "change": float(order.change_amount)

        },

    })


class OrderHistoryView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request):

        status = request.GET.get("status")

        paginator = CustomPagination()

        if status == "draft":

            drafts = get_filtered_drafts(request)

            page = paginator.paginate_queryset(drafts, request)

            serializer = DraftOrderHistorySerializer(page, many=True)

            return paginator.get_paginated_response(serializer.data)

        orders = get_filtered_orders(request)

        page = paginator.paginate_queryset(orders, request)

        serializer = OrderHistorySerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)



class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request, order_id):

        order = get_object_or_404(
            Order,
            id=order_id,
            tenant=request.tenant,
        )

        items_data = []

        refunded_total = (order.refunds.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00"))


        if order.total > 0:
            refund_ratio = refunded_total / order.total
        else:
            refund_ratio = Decimal("0.00")

        remaining_subtotal = order.subtotal * (Decimal("1.00") - refund_ratio)
        remaining_total = order.total - refunded_total

        for item in order.items.select_related("product").all():

            refunded_qty = (
            RefundItem.objects.filter(order_item=item)
            .aggregate(total=Sum("quantity"))["total"]
            or 0
        )

            remaining_qty = item.quantity - refunded_qty

            refunded_amount = item.unit_price * refunded_qty

            item_remaining_subtotal = item.unit_price * remaining_qty


            items_data.append({

                "product": sanitize_csv_cell(item.product.name),

                "purchased_qty": item.quantity,

                "refunded_qty": refunded_qty,

                "remaining_qty": remaining_qty,

                "price": float(item.unit_price),

                "subtotal": float(item_remaining_subtotal)

            })

        return Response({

            "id": order.id,

            "order_number": order.order_number,

            "customer": (
                order.customer.name
                if order.customer
                else "Walk-in Customer"
            ),

            "payment_method": order.payment_method,

            "created_at": order.created_at,

            "status": order.status,

            "subtotal": float(order.subtotal),

            "discount": float(order.discount),

            "tax": float(order.tax),

            "total": float(order.total),
            
            "refunded_total": float(refunded_total),
            
            "remaining_total": float(remaining_total),

            "amount_received": float(order.amount_received),

            "change_amount": float(order.change_amount),

            "items": items_data

        })  


class OrderHistoryCSVExportView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request):
        from django.conf import settings as dj_settings
        from django.http import StreamingHttpResponse

        MAX_ROWS = getattr(dj_settings, "MAX_EXPORT_ROWS", 50000)

        status = request.GET.get("status")

        if status == "draft":
            drafts = get_filtered_drafts(request).select_related("customer", "session")[:MAX_ROWS]

            def draft_rows():
                import csv as _csv
                from io import StringIO
                header = ["Draft No", "Customer", "Date", "Session"]
                buf = StringIO()
                w = _csv.writer(buf)
                w.writerow([sanitize_csv_cell(h) for h in header])
                yield buf.getvalue()
                buf.seek(0); buf.truncate(0)
                for draft in drafts.iterator(chunk_size=2000):
                    w.writerow([
                        sanitize_csv_cell(draft.order_number),
                        sanitize_csv_cell(draft.customer.name if draft.customer else "Walk-in Customer"),
                        sanitize_csv_cell(draft.created_at.strftime("%Y-%m-%d %H:%M")),
                        sanitize_csv_cell(str(draft.session)),
                    ])
                    yield buf.getvalue()
                    buf.seek(0); buf.truncate(0)

            filename = build_export_filename(request, "draft_orders", "csv")
            resp = StreamingHttpResponse(draft_rows(), content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="{filename}"'
            resp["X-Export-Limit"] = str(MAX_ROWS)
            return resp

        orders = get_filtered_orders(request).select_related("customer", "session")[:MAX_ROWS]

        def order_rows():
            import csv as _csv
            from io import StringIO
            header = ["Order No", "Customer", "Payment", "Session", "Subtotal", "Discount", "Tax", "Total", "Status", "Date"]
            buf = StringIO()
            w = _csv.writer(buf)
            w.writerow([sanitize_csv_cell(h) for h in header])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)
            for order in orders.iterator(chunk_size=2000):
                w.writerow([
                    sanitize_csv_cell(order.order_number),
                    sanitize_csv_cell(order.customer.name if order.customer else "Walk-in Customer"),
                    sanitize_csv_cell(order.payment_method),
                    sanitize_csv_cell(str(order.session) if order.session else ""),
                    sanitize_csv_cell(str(order.subtotal)),
                    sanitize_csv_cell(str(order.discount)),
                    sanitize_csv_cell(str(order.tax)),
                    sanitize_csv_cell(str(order.total)),
                    sanitize_csv_cell(order.status),
                    sanitize_csv_cell(order.created_at.strftime("%Y-%m-%d %H:%M:%S")),
                ])
                yield buf.getvalue()
                buf.seek(0); buf.truncate(0)

        filename = build_export_filename(request, "orders", "csv")
        resp = StreamingHttpResponse(order_rows(), content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["X-Export-Limit"] = str(MAX_ROWS)
        return resp


class OrderHistoryExportExcelView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request):

        orders = get_filtered_orders(request)

        workbook = Workbook()

        sheet = workbook.active

        sheet.title = "Orders"

        sheet.freeze_panes = "A2"

        headers = [
            "Order No",
            "Customer",
            "Payment",
            "Total",
            "Status",
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

        for order in orders:
        
            sheet.append([
                order.order_number,
                order.customer.name if order.customer else "Walk-in Customer",
                order.payment_method,
                float(order.total),
                order.status,
                str(order.session),
                order.created_at.strftime("%Y-%m-%d %H:%M"),
            ])

        # ---------- Add Excel filter ----------
        sheet.auto_filter.ref = sheet.dimensions

        # ---------- Format Total column ----------
        for cell in sheet["D"][1:]:
            cell.number_format = '#,##0.00'

        # ---------- Auto width ----------
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

        filename = build_export_filename(request,"orders","xlsx")

        response["Content-Disposition"] = (f'attachment; filename="{filename}"')

        workbook.save(response)

        return response


class OrderHistoryExportPDFView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request):

        buffer = BytesIO()

        doc = SimpleDocTemplate(buffer)

        styles = getSampleStyleSheet()
       
        total_orders = 0
        subtotal = 0
        discount = 0
        tax = 0
        grand_total = 0

        company = Company.objects.filter(tenant=request.tenant).first()

        story = []

        orders = get_filtered_orders(request)   

        add_company_header(story,company,)                                   

        add_report_title(story,"ORDER HISTORY REPORT",)        

        generated = timezone.localtime().strftime("%d-%b-%Y %I:%M %p")

        story.append(Spacer(1, 10))

        customer = request.GET.get("customer")
        payment = request.GET.get("payment")
        session = request.GET.get("session")
        date = request.GET.get("date")
        status = request.GET.get("status")

        report_info = [
            ["Generated", generated]
        ]

        if customer:
            try:
                customer_name = Customer.objects.get(id=customer, tenant=request.tenant).name
                report_info.append(["Customer", customer_name])
            except Customer.DoesNotExist:
                pass
            
        if payment:
            report_info.append(["Payment", payment])

        if session:
            report_info.append(["Session", session])

        if status:
            report_info.append(["Status", status.title()])

        if date:
            report_info.append(["Date Filter", date.title()])  

        add_report_info(story,report_info,)

        if not orders.exists():
        
            story.append(
            
                Paragraph(
                    "No orders found for the selected filters.",
                    styles["Heading3"]
                )

            )        

        table_data = [[
            "S.No",
            "Order No",
            "Customer",
            "Payment",
            "Total",
            "Status",
            "Date",
        ]]

        for index, order in enumerate(orders, start=1):

            total_orders += 1
            subtotal += order.subtotal
            discount += order.discount
            tax += order.tax
            grand_total += order.total
        
            table_data.append([

                index,
            
                order.order_number,

                order.customer.name
                if order.customer
                else "Walk-in Customer",

                order.payment_method,

                f"Rs {order.total:,.2f}",

                order.status.replace("_", " ").title(),

                order.created_at.strftime("%d-%b-%Y"),

            ])     

        table = Table(table_data)

        style_report_table(table,len(table_data))

        story.append(table)  

        story.append(Spacer(1, 25))

        summary_data = [

            ["Total Orders", str(total_orders)],

            ["Subtotal", f"Rs {subtotal:,.2f}"],

            ["Discount", f"Rs {discount:,.2f}"],

            ["Tax", f"Rs {tax:,.2f}"],

            ["Grand Total", f"Rs {grand_total:,.2f}"],
        ]

        add_summary_table(story,"SUMMARY",summary_data,)

        doc.build(
            story,
            onFirstPage=add_page_footer,
            onLaterPages=add_page_footer,
        )

        pdf = buffer.getvalue()

        buffer.close()

        response = HttpResponse(
            pdf,
            content_type="application/pdf"
        )

        filename = build_export_filename(
            request,
            "orders",
            "pdf"
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )

        return response     


@api_view(["GET"])
@permission_classes([IsAuthenticated, HasActiveTenant, TenantRBACPermission])
def order_stats(request):

    total_orders = Order.objects.filter(tenant=request.tenant).count()

    total_items = (
                OrderItem.objects.filter(tenant=request.tenant).aggregate(
            total=Sum("quantity")
        )["total"] or 0
    )

    refund_orders = Order.objects.filter(
        tenant=request.tenant, status__in=["refunded", "partially_refunded"]
    ).count()

    completed_orders = Order.objects.filter(
        tenant=request.tenant, status="paid"
    ).count()

    return Response({
        "total_orders": total_orders,
        "total_items": total_items,
        "refund_orders": refund_orders,
        "completed_orders": completed_orders,
    })           
