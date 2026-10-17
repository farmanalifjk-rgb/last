import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from pos.models import Order
from tax.models import TaxRate, ProductTaxAssignment, TaxBreakdown
from fbr.models import FBRConfiguration

order = Order.objects.get(pk=281)
print("\nORDER:", order.id, "TENANT:", order.tenant_id)
print("TOTALS:", order.subtotal, order.discount, order.tax, order.total)

print("\nACTIVE TAX RATES:")
for r in TaxRate.objects.filter(
    tenant_id=order.tenant_id, is_active=True
).order_by("priority", "id"):
    print(r.id, r.name, r.code, "rate=", r.rate, "mode=", r.mode,
          "compound=", r.compound_style, "applies_to_all=", r.applies_to_all,
          "product=", r.product_id, "category=", r.category_id)

print("\nORDER ITEMS:")
for item in order.items.select_related("product").all():
    p = item.product
    print("ITEM:", item.id, p.id, p.name, "subtotal:", item.subtotal)
    for a in ProductTaxAssignment.objects.filter(
        tenant_id=order.tenant_id, product=p, is_active=True
    ).select_related("tax_rate"):
        print("ASSIGNMENT:", a.tax_rate_id, a.tax_rate.code,
              "rate=", a.tax_rate.rate, "mode=", a.tax_rate.mode)

print("\nSAVED TAX BREAKDOWN:")
breakdowns = TaxBreakdown.objects.filter(order=order).order_by("id")
if not breakdowns.exists():
    print("NO TAX BREAKDOWN RECORDS")
for b in breakdowns:
    print("item=", b.order_item_id, "code=", b.tax_rate_code,
          "rate=", b.rate, "taxable=", b.taxable_amount,
          "tax=", b.tax_amount, "mode=", b.mode)

print("\nACTIVE FBR CONFIGURATION:")
configs = FBRConfiguration.objects.filter(
    tenant_id=order.tenant_id, is_active=True
).order_by("environment")
if not configs.exists():
    print("NO ACTIVE CONFIGURATION")
for c in configs:
    print("id=", c.id, "environment=", c.environment,
          "mode=", c.integration_mode, "simulator=", c.use_simulator)
