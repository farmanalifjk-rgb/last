from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from pos.models import CashSession, Customer, Order, Product, Refund
from pos.pagination import CustomPagination
from saas.permissions import HasActiveTenant, TenantRBACPermission, tenant_member_has_permission

from ..serializers import CashSessionSerializer
from ..services.canonical_pos import (
    IdempotencyConflictError,
    active_session_for_user,
    checkout,
    discount_requested,
    close_own_session,
    open_session,
    park_cart,
    preview_sale,
    process_refund,
    receipt_payload,
    record_cash_movement,
    resume_parked_cart,
)


class CanonicalPOSAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"


def _as_error(exc):
    from django.db import DatabaseError, IntegrityError

    # Infrastructure failures (aborted transaction, lost connection, ...) are not
    # client mistakes: let canonical_exception_handler log them and return a
    # generic 500 instead of echoing database internals as a 400.
    if isinstance(exc, DatabaseError) and not isinstance(exc, IntegrityError):
        raise exc
    if isinstance(exc, LookupError):
        raise NotFound(str(exc))
    if isinstance(exc, IdempotencyConflictError):
        from rest_framework.exceptions import APIException
        error = APIException(str(exc))
        error.status_code = status.HTTP_409_CONFLICT
        error.default_code = "idempotency_key_reused"
        raise error
    raise ValidationError(str(exc))


def _order_data(order, *, detail=False):
    payload = {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "customer_id": order.customer_id,
        "customer_name": order.customer.name if order.customer else "Walk-in customer",
        "session_id": order.session_id,
        "warehouse_id": order.warehouse_id,
        "payment_method": order.payment_method,
        "subtotal": str(order.subtotal),
        "discount": str(order.discount),
        "tax": str(order.tax),
        "total": str(order.total),
        "amount_received": str(order.amount_received),
        "change_amount": str(order.change_amount),
        "created_at": order.created_at,
    }
    if detail:
        payload["items"] = [{
            "id": item.id, "product_id": item.product_id, "name": item.product.name,
            "quantity": str(item.quantity), "unit_price": str(item.unit_price), "subtotal": str(item.subtotal),
        } for item in order.items.select_related("product")]
        payload["tenders"] = [
            {
                "tender_type": tender.tender_type,
                "amount": str(tender.amount),
                "currency": tender.currency,
                "reference": tender.reference,
            }
            for tender in order.tenders.all()
        ]
        payload["refunds"] = [{"id": refund.id, "reason": refund.reason, "total_amount": str(refund.total_amount), "created_at": refund.created_at} for refund in order.refunds.all()]
    return payload


class POSSessionOpenView(CanonicalPOSAPIView):
    rbac_action = "create"

    def post(self, request):
        try:
            session = open_session(
                tenant=request.tenant, user=request.user,
                opening_balance=request.data.get("opening_balance", "0"),
                warehouse_id=request.data.get("warehouse_id"),
                employee_name=request.data.get("employee_name", ""), notes=request.data.get("notes", ""),
            )
        except Exception as exc:
            _as_error(exc)
        return Response(CashSessionSerializer(session, context={"request": request}).data, status=status.HTTP_201_CREATED)


class POSActiveSessionView(CanonicalPOSAPIView):
    def get(self, request):
        session = active_session_for_user(tenant=request.tenant, user=request.user)
        return Response({"session": CashSessionSerializer(session, context={"request": request}).data if session else None})


class POSSessionCloseView(CanonicalPOSAPIView):
    rbac_action = "update"

    def post(self, request):
        try:
            session, expected, difference = close_own_session(
                tenant=request.tenant, user=request.user, actual_cash=request.data.get("actual_cash", request.data.get("actual_closing_balance", "0")),
            )
        except Exception as exc:
            _as_error(exc)
        return Response({"session": CashSessionSerializer(session, context={"request": request}).data, "expected_cash": str(expected), "difference": str(difference)})


class POSCashMovementView(CanonicalPOSAPIView):
    rbac_action = "update"

    def post(self, request):
        try:
            movement = record_cash_movement(
                tenant=request.tenant, user=request.user, transaction_type=request.data.get("type"),
                amount=request.data.get("amount"), reason=request.data.get("reason"),
            )
        except Exception as exc:
            _as_error(exc)
        return Response({"id": movement.id, "type": movement.transaction_type, "amount": str(movement.amount), "reason": movement.reason}, status=status.HTTP_201_CREATED)


def _annotate_sellable_stock(query, *, tenant, warehouse_id):
    """Annotate on-hand, reserved and available stock for the location checkout will decrement.

    Checkout (``canonical_pos.checkout``) decrements the cashier session's
    warehouse row when the session is bound to a warehouse, otherwise only the
    tenant-wide ``Product.stock_quantity`` aggregate. Listing must use the same
    scope so a cashier never sees stock that checkout will refuse to sell.
    Reservations are subtracted exactly as ``inventory.services.available_stock``
    does. Every subquery is filtered by the active tenant.
    """
    from django.db.models import DecimalField, OuterRef, Subquery, Value
    from django.db.models.functions import Coalesce
    from django.utils import timezone

    from enterprise.models import WarehouseStock
    from inventory.models import StockReservation

    decimal_field = DecimalField(max_digits=14, decimal_places=3)
    zero = Value(Decimal("0"), output_field=decimal_field)
    reservations = StockReservation.objects.filter(
        tenant=tenant, product=OuterRef("pk"), status=StockReservation.STATUS_ACTIVE,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
    if warehouse_id:
        reservations = reservations.filter(warehouse_id=warehouse_id)
        on_hand = Coalesce(Subquery(
            WarehouseStock.objects.filter(tenant=tenant, warehouse_id=warehouse_id, product=OuterRef("pk"))
            .values("quantity")[:1],
            output_field=decimal_field,
        ), zero)
    else:
        on_hand = Coalesce("stock_quantity", zero, output_field=decimal_field)
    reserved = Coalesce(Subquery(
        reservations.order_by().values("product").annotate(total=Sum("quantity")).values("total")[:1],
        output_field=decimal_field,
    ), zero)
    return query.annotate(sellable_on_hand=on_hand, sellable_reserved=reserved)


class POSProductSearchView(CanonicalPOSAPIView):
    def get(self, request):
        search = request.query_params.get("search", "").strip()
        barcode = request.query_params.get("barcode", "").strip()
        session = active_session_for_user(tenant=request.tenant, user=request.user)
        stock_warehouse_id = session.warehouse_id if session else None
        query = Product.objects.filter(tenant=request.tenant, is_active=True).select_related("category", "brand")
        query = _annotate_sellable_stock(query, tenant=request.tenant, warehouse_id=stock_warehouse_id)
        if barcode:
            query = query.filter(barcode=barcode)
        elif search:
            query = query.filter(Q(name__icontains=search) | Q(sku__icontains=search) | Q(barcode__iexact=search))
        category_id = request.query_params.get("category_id")
        if category_id:
            query = query.filter(category_id=category_id)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(query.order_by("name", "id"), request)
        rows = page if page is not None else query
        # Same scale as the stored source on every database (SQLite would
        # otherwise drop trailing zeros): WarehouseStock/StockReservation keep
        # 2 decimals, the tenant-wide Product.stock_quantity keeps 3.
        scale = Decimal("0.01") if stock_warehouse_id else Decimal("0.001")

        def qty(value):
            return str(Decimal(str(value or 0)).quantize(scale, rounding=ROUND_HALF_UP))

        data = [{
            "id": product.id, "name": product.name, "sku": product.sku, "barcode": product.barcode,
            "category_id": product.category_id, "category_name": product.category.name if product.category else "",
            "brand_name": product.brand.name if product.brand else "", "base_price": str(product.sales_price),
            # Tenant-wide aggregate kept for backward compatibility.
            "stock_quantity": str(product.stock_quantity),
            # Authoritative sellable figures for the location checkout will use.
            "on_hand_quantity": qty(product.sellable_on_hand),
            "reserved_quantity": qty(product.sellable_reserved),
            "available_quantity": qty(Decimal(str(product.sellable_on_hand or 0)) - Decimal(str(product.sellable_reserved or 0))),
            "stock_warehouse_id": stock_warehouse_id,
            "unit": product.unit, "image": product.image.url if product.image else None,
        } for product in rows]
        return paginator.get_paginated_response(data) if page is not None else Response(data)


class POSCustomerSearchView(CanonicalPOSAPIView):
    def get(self, request):
        search = request.query_params.get("search", "").strip()
        query = Customer.objects.filter(tenant=request.tenant, is_active=True)
        if search:
            query = query.filter(Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search) | Q(customer_code__icontains=search))
        return Response([{"id": customer.id, "name": customer.name, "phone": customer.phone, "email": customer.email, "customer_code": customer.customer_code, "loyalty_points": customer.loyalty_points, "group_id": customer.group_id} for customer in query.order_by("name", "id")[:50]])


def _require_discount_permission(request):
    """A non-zero discount needs pos.discount, for the preview as for checkout.

    Checking the preview too means the cashier sees the refusal before taking
    payment, instead of a discounted total that checkout then rejects.
    """
    if discount_requested(request.data.get("discount", "0")) and not tenant_member_has_permission(
        request.user, request.tenant, "pos", "discount"
    ):
        raise PermissionDenied("The active tenant role does not permit discounts.")


class POSPreviewView(CanonicalPOSAPIView):
    def post(self, request):
        _require_discount_permission(request)
        try:
            quote = preview_sale(tenant=request.tenant, customer_id=request.data.get("customer_id"), items=request.data.get("items"), discount=request.data.get("discount", "0"))
        except Exception as exc:
            _as_error(exc)
        return Response(quote)


class POSCheckoutView(CanonicalPOSAPIView):
    rbac_action = "create"

    def post(self, request):
        discount = request.data.get("discount", "0")
        _require_discount_permission(request)
        try:
            order, replayed = checkout(
                tenant=request.tenant, user=request.user, items=request.data.get("items"), tenders=request.data.get("tenders"),
                customer_id=request.data.get("customer_id"), discount=discount,
                idempotency_key=request.headers.get("Idempotency-Key", request.data.get("idempotency_key", "")),
            )
        except Exception as exc:
            _as_error(exc)
        # The sale is committed. Fiscalize it now (FBR's "on print" model);
        # this never raises and never alters the order, payments or stock.
        from fiscal.pos_fiscalization import fiscalize_pos_order

        fiscal = fiscalize_pos_order(tenant=request.tenant, order=order, user=request.user)
        return Response({"order": _order_data(order, detail=True), "receipt": receipt_payload(order=order, fiscal=fiscal), "fiscal": fiscal, "idempotent_replay": replayed}, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED)


class POSOrderListView(CanonicalPOSAPIView):
    def get(self, request):
        query = Order.objects.filter(tenant=request.tenant).select_related("customer", "session", "warehouse")
        if search := request.query_params.get("search", "").strip():
            query = query.filter(Q(order_number__icontains=search) | Q(customer__name__icontains=search))
        for parameter, field in (("customer_id", "customer_id"), ("session_id", "session_id"), ("status", "status")):
            if value := request.query_params.get(parameter):
                query = query.filter(**{field: value})
        if value := request.query_params.get("date_from"):
            query = query.filter(created_at__date__gte=value)
        if value := request.query_params.get("date_to"):
            query = query.filter(created_at__date__lte=value)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(query.order_by("-created_at", "-id"), request)
        rows = page if page is not None else query
        data = [_order_data(order) for order in rows]
        return paginator.get_paginated_response(data) if page is not None else Response(data)


class POSOrderDetailView(CanonicalPOSAPIView):
    def get(self, request, pk):
        order = get_object_or_404(Order.objects.select_related("customer", "session", "warehouse").prefetch_related("items__product", "tenders", "refunds"), tenant=request.tenant, pk=pk)
        return Response(_order_data(order, detail=True))


class POSReceiptView(CanonicalPOSAPIView):
    def get(self, request, order_id):
        order = get_object_or_404(Order.objects.select_related("customer", "session", "warehouse").prefetch_related("items__product", "tenders"), tenant=request.tenant, pk=order_id)
        if order.status == "draft":
            raise ValidationError("Draft orders do not have a receipt.")
        return Response(receipt_payload(order=order))


RECEIPT_PRINT_ENTITY = "pos_receipt"


class POSReceiptPrintedView(CanonicalPOSAPIView):
    """Record that a receipt was sent to the printer; returns its copy number.

    Copy 1 is the original. Every later copy is a reprint: the receipt marks it
    as such and each print is kept in the tenant's audit trail (cashier audit
    G11; Sales Tax Rules 150R(4)(g) system-event logging). Printing needs only
    the same ``pos.view`` permission as reading the receipt.
    """

    def post(self, request, order_id):
        from django.db import transaction

        from audit.models import AuditEvent
        from audit.recorder import record

        with transaction.atomic():
            # Lock the order row so concurrent prints get distinct copy numbers.
            order = get_object_or_404(Order.objects.select_for_update(), tenant=request.tenant, pk=order_id)
            if order.status == "draft":
                raise ValidationError("Draft orders do not have a receipt.")
            previous = AuditEvent.objects.filter(
                tenant=request.tenant, action=AuditEvent.ACTION_PRINT,
                entity_type=RECEIPT_PRINT_ENTITY, entity_id=str(order.id),
            ).count()
            copy = previous + 1
            record(
                actor=request.user, action=AuditEvent.ACTION_PRINT, tenant=request.tenant, request=request,
                entity_type=RECEIPT_PRINT_ENTITY, entity_id=str(order.id), entity_label=order.order_number,
                after={"copy": copy, "reprint": copy > 1},
            )
        return Response({"order_id": order.id, "copy": copy, "reprint": copy > 1})


class POSParkedSaleListCreateView(CanonicalPOSAPIView):
    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "create"
        return [permission() for permission in self.permission_classes]

    def get(self, request):
        from pos_core.models import ParkedOrder
        session = active_session_for_user(tenant=request.tenant, user=request.user)
        query = ParkedOrder.objects.filter(tenant=request.tenant, status=ParkedOrder.STATUS_PARKED).select_related("customer", "session")
        if session:
            query = query.filter(session=session)
        return Response([{"id": item.id, "label": item.label, "customer_id": item.customer_id, "customer_name": item.customer.name if item.customer else "Walk-in customer", "session_id": item.session_id, "payload": item.payload, "parked_at": item.parked_at} for item in query.order_by("-parked_at")])

    def post(self, request):
        try:
            parked = park_cart(tenant=request.tenant, user=request.user, label=request.data.get("label", ""), customer_id=request.data.get("customer_id"), items=request.data.get("items"))
        except Exception as exc:
            _as_error(exc)
        return Response({"id": parked.id, "status": parked.status, "payload": parked.payload}, status=status.HTTP_201_CREATED)


class POSParkedSaleResumeView(CanonicalPOSAPIView):
    rbac_action = "create"

    def post(self, request, pk):
        try:
            parked = resume_parked_cart(tenant=request.tenant, user=request.user, parked_order_id=pk)
        except Exception as exc:
            _as_error(exc)
        return Response({"id": parked.id, "status": parked.status, "customer_id": parked.customer_id, "payload": parked.payload})


class POSRefundDetailView(CanonicalPOSAPIView):
    rbac_action = "refund"

    def get(self, request, order_id):
        order = get_object_or_404(Order.objects.prefetch_related("items__product", "items__refunditem_set"), tenant=request.tenant, pk=order_id)
        rows = []
        for item in order.items.all():
            refunded = Refund.objects.filter(tenant=request.tenant, order=order, items__order_item=item).aggregate(total=Sum("items__quantity"))["total"] or 0
            rows.append({"order_item_id": item.id, "product_id": item.product_id, "name": item.product.name, "sold_quantity": str(item.quantity), "refunded_quantity": str(refunded), "remaining_quantity": str(item.quantity - refunded), "unit_price": str(item.unit_price)})
        return Response({"order": _order_data(order, detail=True), "items": rows})


class POSRefundProcessView(CanonicalPOSAPIView):
    rbac_action = "refund"

    def post(self, request):
        try:
            refund = process_refund(
                tenant=request.tenant,
                user=request.user,
                order_id=request.data.get("order_id"),
                rows=request.data.get("items"),
                reason=request.data.get("reason", ""),
                cash_refund_amount=request.data.get("cash_refund_amount", "0"),
            )
        except Exception as exc:
            _as_error(exc)
        settlement = getattr(refund, "payment_settlement", None)
        return Response({
            "id": refund.id,
            "order_id": refund.order_id,
            "total_amount": str(refund.total_amount),
            "cash_refund_amount": str(settlement.cash_amount) if settlement else "0.00",
            "reason": refund.reason,
        }, status=status.HTTP_201_CREATED)
