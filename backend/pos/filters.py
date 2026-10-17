from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import *
from suppliers.models import PurchaseReturn
from django.db.models import F
from django.db.models import Sum


def _tenant_queryset(model, request):
    tenant = getattr(request, "tenant", None)
    return model.objects.filter(tenant=tenant) if tenant is not None else model.objects.none()


def get_filtered_orders(request):

    orders = _tenant_queryset(Order, request).order_by("-id")

    search = request.GET.get("search", "").strip()

    if search:
        orders = orders.filter(
            Q(order_number__icontains=search) |
            Q(customer__name__icontains=search)
        )

    status = request.GET.get("status")

    if status and status != "draft":
        orders = orders.filter(status=status)

    payment = request.GET.get("payment")

    if payment:
        orders = orders.filter(payment_method=payment)

    customer = request.GET.get("customer")

    if customer:
        orders = orders.filter(customer_id=customer)

    session = request.GET.get("session")

    if session:
        orders = orders.filter(session_id=session)

    date = request.GET.get("date")

    today = timezone.now().date()

    if date == "today":
        orders = orders.filter(created_at__date=today)

    elif date == "yesterday":
        orders = orders.filter(
            created_at__date=today - timedelta(days=1)
        )

    elif date == "week":
        start_week = today - timedelta(days=today.weekday())

        orders = orders.filter(
            created_at__date__gte=start_week
        )

    elif date == "month":
        orders = orders.filter(
            created_at__year=today.year,
            created_at__month=today.month
        )

    return orders


def get_filtered_refunds(request):

    refunds = _tenant_queryset(Refund, request).select_related(
        "order",
        "order__customer",
        "order__session",
    ).order_by("-created_at")

    search = request.GET.get("search", "").strip()

    if search:

        normalized = search.upper()

        if normalized not in ("R", "RE"):

            refund_id = normalized.replace("RE-", "").lstrip("0")

            query = (
                Q(order__order_number__icontains=search) |
                Q(order__customer__name__icontains=search)
            )

            if refund_id.isdigit():
                query |= Q(id=int(refund_id))

            refunds = refunds.filter(query)

    payment = request.GET.get("payment")

    if payment:
        refunds = refunds.filter(order__payment_method=payment)

    customer = request.GET.get("customer")

    if customer:
        refunds = refunds.filter(order__customer_id=customer)

    session = request.GET.get("session")

    if session:
        refunds = refunds.filter(order__session_id=session)

    date = request.GET.get("date")

    today = timezone.now().date()

    if date == "today":
        refunds = refunds.filter(created_at__date=today)

    elif date == "yesterday":
        refunds = refunds.filter(
            created_at__date=today - timedelta(days=1)
        )

    elif date == "week":
        start_week = today - timedelta(days=today.weekday())

        refunds = refunds.filter(
            created_at__date__gte=start_week
        )

    elif date == "month":
        refunds = refunds.filter(
            created_at__year=today.year,
            created_at__month=today.month
        )

    return refunds


def get_filtered_drafts(request):

    drafts = _tenant_queryset(DraftOrder, request).order_by("-id")

    search = request.GET.get("search", "").strip()

    if search:
        drafts = drafts.filter(
            Q(order_number__icontains=search) |
            Q(customer__name__icontains=search)
        )

    customer = request.GET.get("customer")

    if customer:
        drafts = drafts.filter(customer_id=customer)

    session = request.GET.get("session")

    if session:
        drafts = drafts.filter(session_id=session)

    date = request.GET.get("date")

    today = timezone.now().date()

    if date == "today":
        drafts = drafts.filter(created_at__date=today)

    elif date == "yesterday":
        drafts = drafts.filter(
            created_at__date=today - timedelta(days=1)
        )

    elif date == "week":
        start_week = today - timedelta(days=today.weekday())

        drafts = drafts.filter(
            created_at__date__gte=start_week
        )

    elif date == "month":
        drafts = drafts.filter(
            created_at__year=today.year,
            created_at__month=today.month
        )

    return drafts


def get_filtered_stock_movements(request):

    movements = (
        _tenant_queryset(StockMovement, request)
        .select_related("product")
        .order_by("-created_at")
    )

    search = request.GET.get("search", "").strip()

    if search:

        movements = movements.filter(

            Q(product__name__icontains=search) |

            Q(product__sku__icontains=search) |

            Q(product__barcode__icontains=search) |

            Q(reference__icontains=search)

        )

    movement_type = request.GET.get("movement_type")

    if movement_type:

       movements = movements.filter(
           movement_type=movement_type
       )

    product = request.GET.get("product")

    if product:

        movements = movements.filter(
            product_id=product
        )

    start_date = request.GET.get("start_date")
    
    if start_date:
    
        movements = movements.filter(
            created_at__date__gte=start_date
        )
    
    end_date = request.GET.get("end_date")
    
    if end_date:
    
        movements = movements.filter(
            created_at__date__lte=end_date
        )

    category = request.GET.get("category")

    if category:

        movements = movements.filter(
            product__category_id=category
        )

    date = request.GET.get("date")

    today = timezone.now().date()

    if date == "today":

        movements = movements.filter(
            created_at__date=today
        )

    elif date == "yesterday":

        movements = movements.filter(
            created_at__date=today - timedelta(days=1)
        )

    elif date == "week":

        start_week = today - timedelta(days=today.weekday())

        movements = movements.filter(
            created_at__date__gte=start_week
        )

    elif date == "month":

        movements = movements.filter(
            created_at__year=today.year,
            created_at__month=today.month
        )

    return movements


def get_filtered_low_stock_products(request):

    products = _tenant_queryset(Product, request).filter(
        is_active=True,
        stock_quantity__lte=F("min_stock")
    ).select_related(
        "category"
    ).order_by(
        "stock_quantity",
        "name"
    )

    search = request.GET.get("search", "").strip()

    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(sku__icontains=search) |
            Q(barcode__icontains=search)
        )

    category = request.GET.get("category")

    if category:
        products = products.filter(
            category_id=category
        )

    return products


def get_filtered_purchase_orders(request):

    purchases = _tenant_queryset(PurchaseOrder, request).select_related("supplier").prefetch_related("items").order_by("-id")

    search = request.GET.get("search", "").strip()

    if search:
        purchases = purchases.filter(
            Q(order_number__icontains=search) |
            Q(supplier__name__icontains=search)
        )

    supplier = request.GET.get("supplier")

    if supplier:
        purchases = purchases.filter(
            supplier_id=supplier
        )

    status = request.GET.get("status")

    if status and status != "all":
        purchases = purchases.filter(
            status=status
        )

    date = request.GET.get("date")

    today = timezone.now().date()

    if date == "today":
        purchases = purchases.filter(
            created_at__date=today
        )

    elif date == "yesterday":
        purchases = purchases.filter(
            created_at__date=today - timedelta(days=1)
        )

    elif date == "week":
        start_week = today - timedelta(days=today.weekday())

        purchases = purchases.filter(
            created_at__date__gte=start_week
        )

    elif date == "month":
        purchases = purchases.filter(
            created_at__year=today.year,
            created_at__month=today.month
        )

    return purchases


def get_filtered_purchase_returns(request):

    returns = _tenant_queryset(PurchaseReturn, request).select_related(
        "purchase_order",
        "purchase_order__supplier",
    ).prefetch_related(
        "items"
    ).order_by("-id")

    search = request.GET.get("search", "").strip()

    if search:

        returns = returns.filter(

            Q(
                purchase_order__order_number__icontains=search
            ) |

            Q(
                purchase_order__supplier__name__icontains=search
            )

        )

    supplier = request.GET.get("supplier")

    if supplier:

        returns = returns.filter(
            purchase_order__supplier_id=supplier
        )

    date = request.GET.get("date")

    today = timezone.now().date()

    if date == "today":

        returns = returns.filter(
            created_at__date=today
        )

    elif date == "yesterday":

        returns = returns.filter(
            created_at__date=today - timedelta(days=1)
        )

    elif date == "week":

        start_week = today - timedelta(
            days=today.weekday()
        )

        returns = returns.filter(
            created_at__date__gte=start_week
        )

    elif date == "month":

        returns = returns.filter(
            created_at__year=today.year,
            created_at__month=today.month,
        )

    return returns


def get_purchase_return_summary(request=None):
    # Tenant-isolated: never return cross-tenant returns
    if request is not None and getattr(request, "tenant", None) is not None:
        returns = PurchaseReturn.objects.filter(tenant=request.tenant)
    else:
        # No tenant context -> empty set (fail-closed) instead of leaking all tenants
        # Callers that pass explicit tenant= should use that overload; legacy callers updated to pass request.
        returns = PurchaseReturn.objects.none()
        # Fallback for internal calls without request that explicitly want tenant param:
        # If called as get_purchase_return_summary(tenant=tenant) that signature will be added below
        # For now return empty to avoid leakage

    return {

        "total_returns": returns.count(),

        "total_return_amount":
            returns.aggregate(
                total=Sum("total_amount")
            )["total"] or 0,

        "this_month":
            returns.filter(
                created_at__year=timezone.now().year,
                created_at__month=timezone.now().month,
            ).aggregate(
                total=Sum("total_amount")
            )["total"] or 0,

    }

def get_purchase_return_summary_for_tenant(tenant):
    returns = PurchaseReturn.objects.filter(tenant=tenant)
    return {
        "total_returns": returns.count(),
        "total_return_amount": returns.aggregate(total=Sum("total_amount"))["total"] or 0,
        "this_month": returns.filter(
            created_at__year=timezone.now().year,
            created_at__month=timezone.now().month,
        ).aggregate(total=Sum("total_amount"))["total"] or 0,
    }


def get_filtered_stock_adjustments(request):

    adjustments = (_tenant_queryset(StockAdjustment, request).select_related("created_by").prefetch_related("items").order_by("-id"))

    search = request.GET.get("search", "").strip()

    if search:

        adjustments = adjustments.filter(

            Q(adjustment_number__icontains=search) |

            Q(reason__icontains=search)

        )

    date = request.GET.get("date")

    today = timezone.now().date()

    if date == "today":

        adjustments = adjustments.filter(
            created_at__date=today
        )

    elif date == "yesterday":

        adjustments = adjustments.filter(
            created_at__date=today - timedelta(days=1)
        )

    elif date == "week":

        start_week = today - timedelta(
            days=today.weekday()
        )

        adjustments = adjustments.filter(
            created_at__date__gte=start_week
        )

    elif date == "month":

        adjustments = adjustments.filter(

            created_at__year=today.year,

            created_at__month=today.month,

        )

    return adjustments


def get_filtered_inventory(request):

    products = _tenant_queryset(Product, request).select_related(
        "category"
    )

    search = request.GET.get("search")

    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(sku__icontains=search) |
            Q(barcode__icontains=search)
        )

    status = request.GET.get("status")

    if status == "low":
        products = products.filter(
            stock_quantity__gt=0,
            stock_quantity__lte=F("min_stock")
        )

    elif status == "out":
        products = products.filter(
            stock_quantity=0
        )

    elif status == "inactive":
        products = products.filter(
            is_active=False
        )

    elif status == "all":
        products = products.filter(
            is_active=True
        )

    category = request.GET.get("category")

    if category:
        products = products.filter(
            category_id=category
        )

    return products.order_by("name")