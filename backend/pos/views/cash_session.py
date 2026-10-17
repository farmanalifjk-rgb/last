from rest_framework.views import APIView
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from saas.permissions import HasActiveTenant, TenantRBACPermission
from ..serializers import CashSessionSerializer, OrderSerializer
from ..models import CashSession, CashTransaction, Order, Payment, Refund


def _session_for_user(user, *, lock=False, tenant=None):
    # Tenant-isolated: never return a session from another tenant, even if orphan.
    queryset = CashSession.objects.filter(tenant=tenant)
    if lock:
        queryset = queryset.select_for_update()
    # Only return sessions opened by this user in this tenant; legacy orphan (opened_by IS NULL) sessions are ignored for isolation.
    return queryset.filter(is_open=True, opened_by=user).order_by("id").first()


class OpenSessionView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "create"
    def post(self, request):
        try:
            opening_balance = Decimal(str(request.data.get("opening_balance", "0")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            return Response({"error": "opening_balance must be a valid number."}, status=status.HTTP_400_BAD_REQUEST)
        if opening_balance < 0:
            return Response({"error": "opening_balance cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)
        if opening_balance > 100000:
            return Response({"error": "opening_balance cannot exceed 100,000."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if CashSession.objects.select_for_update().filter(is_open=True, tenant=request.tenant, opened_by=request.user).exists():
                return Response({"error": "You already have an open session."}, status=status.HTTP_400_BAD_REQUEST)
            employee_name = str(request.data.get("employee_name", "")).strip()
            if not employee_name:
                employee_name = request.user.get_full_name() or request.user.get_username()
            session = CashSession.objects.create(
                tenant=request.tenant,
                opening_balance=opening_balance,
                employee_name=employee_name,
                opened_by=request.user,
                is_open=True,
                next_draft_number=1,
            )
        return Response(CashSessionSerializer(session, context={"request": request}).data, status=status.HTTP_201_CREATED)


class ActiveSessionView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        session = _session_for_user(request.user, tenant=request.tenant)
        if not session:
            return Response({"session": None, "session_id": None})
        return Response(CashSessionSerializer(session, context={"request": request}).data)


class CloseSessionView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "update"
    @transaction.atomic
    def post(self, request):
        session = _session_for_user(request.user, lock=True, tenant=request.tenant)
        if not session:
            return Response({"error": "No active session."}, status=status.HTTP_404_NOT_FOUND)
        try:
            actual_cash = Decimal(str(request.data.get("actual_cash", request.data.get("actual_closing_balance", "0"))))
        except (InvalidOperation, TypeError, ValueError):
            return Response({"error": "actual_cash must be a valid number."}, status=status.HTTP_400_BAD_REQUEST)
        if actual_cash < 0:
            return Response({"error": "actual_cash cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)

        session.orders.filter(status="draft").update(status="cancelled")
        cash_in = session.transactions.filter(transaction_type="in").aggregate(total=Sum("amount"))["total"] or Decimal("0")
        cash_out = session.transactions.filter(transaction_type="out").aggregate(total=Sum("amount"))["total"] or Decimal("0")
        legacy_cash = Payment.objects.filter(
            order__session=session,
            payment_method="cash",
            order__tenders__isnull=True,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        try:
            from payments.models import TenderedPayment
            tendered_cash = TenderedPayment.objects.filter(
                order__session=session,
                tender_type="cash",
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        except ImportError:
            tendered_cash = Decimal("0")
        refunds = Refund.objects.filter(order__session=session).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
        expected = Decimal(session.opening_balance) + Decimal(cash_in) - Decimal(cash_out) + Decimal(legacy_cash) + Decimal(tendered_cash) - Decimal(refunds)

        session.is_open = False
        session.closed_at = timezone.now()
        session.closed_by = request.user
        session.actual_closing_balance = actual_cash
        session.closing_balance = expected
        session.save(update_fields=["is_open", "closed_at", "closed_by", "actual_closing_balance", "closing_balance"])
        return Response({
            "message": "Session closed.",
            "session_id": session.id,
            "expected": expected,
            "actual": actual_cash,
            "difference": actual_cash - expected,
        })

class CashSessionListView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"
    def get(self, request):
        status_filter = request.query_params.get('status')
        date_filter = request.query_params.get('date')
        cashier_filter = request.query_params.get('cashier')
        sessions = CashSession.objects.filter(tenant=request.tenant).order_by("-id")
        
        if status_filter == 'open':
            sessions = sessions.filter(is_open=True)
        elif status_filter == 'closed':
            sessions = sessions.filter(is_open=False)
            
        if date_filter and date_filter != 'all' and date_filter != 'today':
            sessions = sessions.filter(opened_at__date=date_filter)
        elif date_filter == 'today':
            from django.utils.timezone import now
            sessions = sessions.filter(opened_at__date=now().date())
            
        if cashier_filter:
            sessions = sessions.filter(employee_name__icontains=cashier_filter)
            
        search_filter = request.query_params.get('search')
        if search_filter:
            sessions = sessions.filter(id__icontains=search_filter)
            
        serializer = CashSessionSerializer(sessions, many=True)
        return Response(serializer.data)

class CashTransactionView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "update"

    def post(self, request, pk, action):
        try:
            session = CashSession.objects.get(pk=pk, tenant=request.tenant, is_open=True)
        except CashSession.DoesNotExist:
            return Response({"error": "Active session not found."}, status=status.HTTP_404_NOT_FOUND)
            
        amount = request.data.get('amount')
        reason = request.data.get('reason')
        
        if not amount or not reason:
            return Response({"error": "Amount and reason are required."}, status=status.HTTP_400_BAD_REQUEST)
            
        CashTransaction.objects.create(
            tenant=request.tenant,
            session=session,
            transaction_type=action,
            amount=amount,
            reason=reason
        )
        return Response({"message": f"Cash {action} recorded."})

class CashSessionCloseView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "update"

    def post(self, request, pk):
        try:
            session = CashSession.objects.get(pk=pk, tenant=request.tenant, is_open=True)
            actual_cash = request.data.get("actual_cash", 0)

            # Auto-close related draft orders
            session.orders.filter(status='draft').update(status='cancelled')

            session.is_open = False
            session.closed_at = timezone.now()
            session.actual_closing_balance = actual_cash
            
            # Recalculate closing balance safely
            total_cash_in = session.transactions.filter(transaction_type='in').aggregate(total=Sum('amount'))['total'] or 0
            total_cash_out = session.transactions.filter(transaction_type='out').aggregate(total=Sum('amount'))['total'] or 0
            
            total_sales = session.orders.filter(status__in=['paid', 'partially_refunded']).aggregate(total=Sum('total'))['total'] or 0
            total_refunds = session.orders.filter(status__in=['refunded', 'partially_refunded']).aggregate(total=Sum('change_amount'))['total'] or 0 # Simplified

            expected = Decimal(session.opening_balance) + Decimal(total_cash_in) - Decimal(total_cash_out) + Decimal(total_sales) - Decimal(total_refunds)
            session.closing_balance = expected

            session.save()
            return Response({"message": "Session closed", "expected": expected})

        except CashSession.DoesNotExist:
            return Response({"error": "Session not found or already closed"}, status=status.HTTP_404_NOT_FOUND)

class CashSessionCashiersView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request):
        cashiers = CashSession.objects.filter(tenant=request.tenant).exclude(employee_name="").values_list('employee_name', flat=True).distinct()
        data = [{"name": c} for c in cashiers]
        return Response(data)

class CashSessionTimelineView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "pos"
    rbac_action = "view"

    def get(self, request, pk):
        try:
            session = CashSession.objects.get(pk=pk, tenant=request.tenant)
        except CashSession.DoesNotExist:
            return Response({"error": "Session not found."}, status=status.HTTP_404_NOT_FOUND)
            
        events = []
        
        events.append({
            "type": "opened",
            "description": f"Session Opened by {session.employee_name or 'Admin'}",
            "amount": session.opening_balance,
            "timestamp": session.opened_at
        })
        
        transactions = CashTransaction.objects.filter(session=session, tenant=request.tenant)
        for t in transactions:
            events.append({
                "type": f"cash_{t.transaction_type}",
                "description": t.reason,
                "amount": t.amount,
                "timestamp": t.created_at
            })
            
        orders = Order.objects.filter(session=session, tenant=request.tenant).exclude(status='draft').exclude(status='cancelled')
        for o in orders:
            event_type = "refund" if "refund" in o.status else "sale"
            events.append({
                "type": event_type,
                "description": f"Order #{o.order_number or o.id}",
                "amount": o.total,
                "timestamp": o.created_at
            })
            
        if not session.is_open:
            events.append({
                "type": "closed",
                "description": session.notes or "Session Closed",
                "amount": session.actual_closing_balance,
                "timestamp": session.closed_at
            })
            
        events.sort(key=lambda x: x["timestamp"])
        
        return Response(events)