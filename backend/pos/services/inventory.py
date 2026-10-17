from django.db.models import Q

from django.db.models import F
from django.db.models import Sum
from pos.models import OrderItem,RefundItem
from pos.models import Product, StockMovement
from django.utils import timezone
from datetime import timedelta
from django.db.models.functions import Coalesce
from django.db.models import IntegerField





def get_low_stock_products(tenant=None):
    qs = Product.objects.filter(is_active=True, stock_quantity__lte=F("min_stock"))
    if tenant is not None:
        return qs.filter(tenant=tenant)
    # Fail-closed: no tenant -> empty instead of leaking all tenants
    return qs.none()    


def get_out_of_stock_products(tenant=None):
    qs = Product.objects.filter(is_active=True, stock_quantity=0)
    if tenant is not None:
        return qs.filter(tenant=tenant)
    return qs.none()


def get_overstock_products(tenant=None):
    qs = Product.objects.exclude(max_stock=None).filter(stock_quantity__gt=F("max_stock"), is_active=True)
    if tenant is not None:
        return qs.filter(tenant=tenant)
    return qs.none()


def get_inventory_summary(tenant=None):

    qs = Product.objects.filter(is_active=True)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)

    return {
        "total_products": qs.count(),
        "low_stock": qs.filter(stock_quantity__lte=F("min_stock")).count(),
        "out_of_stock": qs.filter(stock_quantity=0).count(),
        "overstock": qs.exclude(max_stock=None).filter(stock_quantity__gt=F("max_stock")).count(),
    }


def get_inventory_statistics(tenant=None):
    qs = Product.objects.filter(is_active=True)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    return {
        "total_products": qs.count(),
        "low_stock_products": qs.filter(stock_quantity__lte=F("min_stock"), stock_quantity__gt=0).count(),
        "out_of_stock_products": qs.filter(stock_quantity=0).count(),
        "overstock_products": qs.filter(stock_quantity__gt=F("max_stock"), max_stock__isnull=False).count(),
    }


def get_adjustment_summary(adjustments):

    total_adjustments = adjustments.count()

    total_products = 0

    increase_operations = 0

    decrease_operations = 0

    total_quantity_adjusted = 0

    for adjustment in adjustments:

        items = adjustment.items.all()

        total_products += items.count()

        for item in items:

            total_quantity_adjusted += item.quantity

            if item.adjustment.adjustment_type == "increase":
                increase_operations += 1

            elif item.adjustment.adjustment_type == "decrease":
                decrease_operations += 1

    return {

        "total_adjustments": total_adjustments,

        "total_products": total_products,

        "increase_operations": increase_operations,

        "decrease_operations": decrease_operations,

        "total_quantity_adjusted": total_quantity_adjusted,

    }


from django.db.models import (
    F,
    Sum,
    DecimalField,
    ExpressionWrapper,
)

from pos.models import Product


def get_inventory_valuation(tenant=None):
    products = Product.objects.filter(is_active=True)
    if tenant is not None:
        products = products.filter(tenant=tenant)

    inventory_cost = products.aggregate(
        total=Sum(
            ExpressionWrapper(
                F("stock_quantity") * F("cost_price"),
                output_field=DecimalField(
                    max_digits=14,
                    decimal_places=2,
                ),
            )
        )
    )["total"] or 0

    inventory_sale = products.aggregate(
        total=Sum(
            ExpressionWrapper(
                F("stock_quantity") * F("sales_price"),
                output_field=DecimalField(
                    max_digits=14,
                    decimal_places=2,
                ),
            )
        )
    )["total"] or 0

    return {
        "total_products": products.count(),
        "total_stock_units": sum(
            p.stock_quantity
            for p in products
        ),
        "inventory_cost_value": inventory_cost,
        "inventory_sale_value": inventory_sale,
        "expected_profit": (
            inventory_sale - inventory_cost
        ),
    }


from django.db.models import (
    F,
    DecimalField,
    ExpressionWrapper,
)


def get_inventory_valuation_products(tenant=None):

    qs = Product.objects.filter(is_active=True)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)

    return (
        qs
        .select_related("category")
        .annotate(

            cost_value=ExpressionWrapper(
                F("stock_quantity") * F("cost_price"),
                output_field=DecimalField(
                    max_digits=14,
                    decimal_places=2,
                ),
            ),

            sale_value=ExpressionWrapper(
                F("stock_quantity") * F("sales_price"),
                output_field=DecimalField(
                    max_digits=14,
                    decimal_places=2,
                ),
            ),

            expected_profit=ExpressionWrapper(
                (F("sales_price") - F("cost_price"))
                * F("stock_quantity"),
                output_field=DecimalField(
                    max_digits=14,
                    decimal_places=2,
                ),
            ),
        )
        .order_by("name")
    )


def get_filtered_inventory_valuation(request):

    tenant = getattr(request, "tenant", None)
    products = get_inventory_valuation_products(tenant=tenant)

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

    stock = request.GET.get("stock")

    if stock == "low":
        products = products.filter(
            stock_quantity__lte=F("min_stock")
        )

    elif stock == "out":
        products = products.filter(
            stock_quantity=0
        )

    elif stock == "over":
        products = products.filter(
            max_stock__isnull=False,
            stock_quantity__gte=F("max_stock")
        )

    return products


def get_inventory_report(request):

    products = get_filtered_inventory_valuation(request)

    summary = {

        "total_products": products.count(),

        "total_stock": products.aggregate(
            total=Sum("stock_quantity")
        )["total"] or 0,

        "total_cost": products.aggregate(
            total=Sum("cost_value")
        )["total"] or 0,

        "total_sale": products.aggregate(
            total=Sum("sale_value")
        )["total"] or 0,

        "total_profit": products.aggregate(
            total=Sum("expected_profit")
        )["total"] or 0,
    }

    return {
        "products": products,
        "summary": summary,
    }


def get_inventory_analytics(tenant=None):

    products = Product.objects.filter(is_active=True)
    if tenant is not None:
        products = products.filter(tenant=tenant)

    return {

        "total_products": products.count(),

        "total_stock": products.aggregate(
            total=Sum("stock_quantity")
        )["total"] or 0,

        "low_stock": products.filter(
            stock_quantity__lte=F("min_stock")
        ).count(),

        "out_of_stock": products.filter(
            stock_quantity=0
        ).count(),

        "overstock": products.filter(
            max_stock__isnull=False,
            stock_quantity__gte=F("max_stock")
        ).count(),

    }


def get_top_selling_products(
    limit=10,
    date_filter=None,
    tenant=None,
):

    items = OrderItem.objects.all()
    if tenant is not None:
        items = items.filter(tenant=tenant)

    today = timezone.now().date()

    if date_filter == "week":

        items = items.filter(
            order__created_at__date__gte=
            today - timedelta(days=7)
        )

    elif date_filter == "month":

        items = items.filter(
            order__created_at__month=today.month,
            order__created_at__year=today.year
        )

    elif date_filter == "year":

        items = items.filter(
            order__created_at__year=today.year
        )

    return (
        items
        .values(
            "product__id",
            "product__name",
            "product__sku"
        )
        .annotate(
            total_sold=Sum("quantity")
        )
        .order_by("-total_sold")[:limit]
    )


def get_slow_moving_products(limit=10, date_filter=None, tenant=None):

    products = Product.objects.filter(is_active=True)
    if tenant is not None:
        products = products.filter(tenant=tenant)

    today = timezone.now().date()

    filters = Q()

    if date_filter == "week":
        filters = Q(
            orderitem__order__created_at__date__gte=today - timedelta(days=7)
        )

    elif date_filter == "month":
        filters = Q(
            orderitem__order__created_at__year=today.year,
            orderitem__order__created_at__month=today.month,
        )

    elif date_filter == "year":
        filters = Q(
            orderitem__order__created_at__year=today.year
        )

    products = products.annotate(

        total_sold=Coalesce(
            Sum(
                "orderitem__quantity",
                filter=filters if filters else None,
            ),
            0,
            output_field=IntegerField(),
        )

    ).order_by(
        "total_sold",
        "-stock_quantity",
        "name"
    )[:limit]

    return products


def get_most_returned_products(limit=10, date_filter=None, tenant=None):

    items = RefundItem.objects.all()
    if tenant is not None:
        items = items.filter(tenant=tenant)

    today = timezone.now().date()

    if date_filter == "week":

        items = items.filter(
            refund__created_at__date__gte=today - timedelta(days=7)
        )

    elif date_filter == "month":

        items = items.filter(
            refund__created_at__year=today.year,
            refund__created_at__month=today.month
        )

    elif date_filter == "year":

        items = items.filter(
            refund__created_at__year=today.year
        )

    return (
        items
        .values(
            product_id=F("order_item__product__id"),
            product_name=F("order_item__product__name"),
            sku=F("order_item__product__sku"),
        )
        .annotate(
            total_returned=Sum("quantity")
        )
        .order_by("-total_returned")[:limit]
    )