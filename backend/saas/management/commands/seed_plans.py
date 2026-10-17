from django.core.management.base import BaseCommand
from saas.models import SubscriptionPlan


class Command(BaseCommand):
    def handle(self, *a, **kw):
        plans = [
            {"name": "Starter", "slug": "starter", "price": "29", "max_users": 3, "max_stores": 1, "max_warehouses": 1, "max_products": 200},
            {"name": "Business", "slug": "business", "price": "89", "max_users": 15, "max_stores": 5, "max_warehouses": 5, "max_products": 5000},
            {"name": "Enterprise", "slug": "enterprise", "price": "249", "max_users": None, "max_stores": None, "max_warehouses": None, "max_products": None},
        ]
        for p in plans:
            SubscriptionPlan.objects.update_or_create(slug=p["slug"], defaults={**p, "currency": "USD", "interval": "monthly", "trial_days": 14})
        self.stdout.write(self.style.SUCCESS("Seeded subscription plans"))
