from decimal import Decimal
from pos.models import Order
from tax.models import TaxRate, TaxBreakdown, ProductTaxAssignment

orders = list(Order.objects.filter(
    tenant_id=235,
    subtotal=Decimal("8999.00")
).order_by("-id")[:5])

print("\n=== MATCHING ORDERS AND SAVED TAX BREAKDOWN ===")
for order in orders:
    print("\nORDER", order.id, order.order_number, "status:", order.status)
    print("subtotal:", order.subtotal, "discount:", order.discount,
          "tax:", order.tax, "total:", order.total)

    for item in order.items.select_related("product").all():
        p = item.product
        print("ITEM", item.id, "product:", p.id, p.name,
              "category:", p.category_id, "subtotal:", item.subtotal)

        assignments = list(ProductTaxAssignment.objects.filter(
            tenant_id=order.tenant_id,
            product_id=p.id,
            is_active=True
        ).select_related("tax_rate"))

        print("PRODUCT ASSIGNMENTS:", len(assignments))
        for a in assignments:
            r = a.tax_rate
            print(" ", r.id, r.code, "rate:", r.rate,
                  "active:", r.is_active, "all:", r.applies_to_all)

    print("BREAKDOWN:")
    for b in TaxBreakdown.objects.filter(order=order).order_by("id"):
        print(" ", "rate_id:", b.tax_rate_id, "code:", b.tax_rate_code,
              "rate:", b.rate, "taxable:", b.taxable_amount,
              "tax:", b.tax_amount, "mode:", b.mode)

print("\n=== ALL ACTIVE TAX RATES ===")
for r in TaxRate.objects.filter(is_active=True).order_by(
    "tenant_id", "priority", "id"
):
    print("tenant:", r.tenant_id, "id:", r.id, "code:", r.code,
          "rate:", r.rate, "mode:", r.mode,
          "compound:", r.compound_style, "priority:", r.priority,
          "all:", r.applies_to_all,
          "product:", r.product_id, "category:", r.category_id)
