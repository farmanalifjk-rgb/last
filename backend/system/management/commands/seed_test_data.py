from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from enterprise.models import Warehouse
from pos.models import (
    Brand,
    Category,
    Customer,
    PaymentMethod,
    Product,
    Supplier,
    Tax,
)
from saas.models import Tenant
from system.models import Store


class Command(BaseCommand):
    help = "Seed realistic development data for the POS system."

    def add_arguments(self, parser):
        parser.add_argument(
            "--large",
            action="store_true",
            help="Create a larger development dataset.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        is_large = options["large"]

        self.stdout.write(
            self.style.WARNING(
                "Starting POS development data seeding..."
            )
        )

        # ============================================================
        # 1. ADMIN USER
        # ============================================================

        User = get_user_model()

        user, created = User.objects.get_or_create(
            username="demo_admin",
            defaults={
                "email": "demo@example.com",
                "first_name": "Demo",
                "last_name": "Admin",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        if created:
            user.set_password("demo12345")
            user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"User ready: {user.username}"
            )
        )

        # ============================================================
        # 2. SAAS TENANT
        # ============================================================

        tenant, _ = Tenant.objects.update_or_create(
            slug="demo-pos",
            defaults={
                "name": "Demo POS Business",
                "owner": user,
                "status": "trial",
                "is_active": True,
                "suspended_reason": "",
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Tenant ready: {tenant.name}"
            )
        )

        # ============================================================
        # 3. STORE
        # ============================================================

        store, _ = Store.objects.update_or_create(
            tenant=tenant,
            code="MAIN",
            defaults={
                "name": "Main Store",
                "manager": user,
                "currency": "Rs",
                "timezone": "Asia/Karachi",
                "language": "en",
                "date_format": "DD/MM/YYYY",
                "time_format": "24h",
                "weight_unit": "kg",
                "dimension_unit": "cm",
                "address": "Demo Store, Pakistan",
                "phone": "+92-300-0000000",
                "is_active": True,
                "is_default": True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Store ready: {store.name}"
            )
        )

        # ============================================================
        # 4. WAREHOUSE
        # ============================================================

        warehouse, _ = Warehouse.objects.update_or_create(
            tenant=tenant,
            code="MAIN-WH",
            defaults={
                "store": store,
                "name": "Main Warehouse",
                "address": "Demo Warehouse, Pakistan",
                "is_active": True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Warehouse ready: {warehouse.name}"
            )
        )

        # ============================================================
        # 5. CATEGORIES
        # ============================================================

        category_names = [
            "Beverages",
            "Snacks",
            "Groceries",
            "Electronics",
            "Personal Care",
        ]

        if is_large:
            category_names.extend(
                [
                    "Dairy",
                    "Bakery",
                    "Frozen Foods",
                    "Household",
                    "Stationery",
                ]
            )

        categories = {}

        for name in category_names:
            category, _ = Category.objects.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "is_active": True,
                },
            )

            categories[name] = category

        self.stdout.write(
            self.style.SUCCESS(
                f"Categories ready: {len(categories)}"
            )
        )

        # ============================================================
        # 6. BRANDS
        # ============================================================

        brand_names = [
            "Coca-Cola",
            "Pepsi",
            "Nestle",
            "Unilever",
            "Demo Brand",
        ]

        if is_large:
            brand_names.extend(
                [
                    "Samsung",
                    "Apple",
                    "Dawlance",
                    "Surf",
                    "National",
                ]
            )

        brands = {}

        for name in brand_names:
            brand, _ = Brand.objects.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "description": f"Demo brand: {name}",
                    "is_active": True,
                },
            )

            brands[name] = brand

        self.stdout.write(
            self.style.SUCCESS(
                f"Brands ready: {len(brands)}"
            )
        )

        # ============================================================
        # 7. PAYMENT METHODS
        # ============================================================

        payment_methods = [
            {
                "name": "Cash",
                "method_type": "cash",
                "is_default": True,
                "icon": "banknote",
                "color": "#16A34A",
            },
            {
                "name": "Card",
                "method_type": "card",
                "is_default": False,
                "icon": "credit-card",
                "color": "#2563EB",
            },
            {
                "name": "Bank Transfer",
                "method_type": "bank",
                "is_default": False,
                "icon": "building-2",
                "color": "#7C3AED",
            },
        ]

        for data in payment_methods:
            PaymentMethod.objects.update_or_create(
                tenant=tenant,
                name=data["name"],
                defaults={
                    **data,
                    "is_active": True,
                    "instructions": "",
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Payment methods ready"
            )
        )

        # ============================================================
        # 8. TAXES
        # ============================================================

        Tax.objects.update_or_create(
            tenant=tenant,
            name="GST",
            defaults={
                "rate": Decimal("18.00"),
                "tax_type": "percentage",
                "description": "General Sales Tax",
                "is_active": True,
                "is_default": True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Tax ready"
            )
        )

        # ============================================================
        # 9. CUSTOMERS
        # ============================================================

        customer_count = 20 if is_large else 5
        customers = []

        for index in range(1, customer_count + 1):
            customer, _ = Customer.objects.update_or_create(
                tenant=tenant,
                customer_code=f"CUST-{index:04d}",
                defaults={
                    "name": f"Demo Customer {index}",
                    "phone": f"0300{index:07d}",
                    "email": f"customer{index}@example.com",
                    "address": "Karachi, Pakistan",
                    "is_active": True,
                    "loyalty_points": index * 10,
                },
            )

            customers.append(customer)

        self.stdout.write(
            self.style.SUCCESS(
                f"Customers ready: {len(customers)}"
            )
        )

        # ============================================================
        # 10. SUPPLIERS
        # ============================================================

        supplier_count = 10 if is_large else 3
        suppliers = []

        for index in range(1, supplier_count + 1):
            supplier, _ = Supplier.objects.get_or_create(
                tenant=tenant,
                name=f"Demo Supplier {index}",
                defaults={
                    "company": f"Supplier Company {index}",
                    "contact_person": f"Supplier Contact {index}",
                    "phone": f"0310{index:07d}",
                    "email": f"supplier{index}@example.com",
                    "address": "Pakistan",
                    "tax_number": f"TAX-{index:04d}",
                    "is_active": True,
                },
            )

            suppliers.append(supplier)

        self.stdout.write(
            self.style.SUCCESS(
                f"Suppliers ready: {len(suppliers)}"
            )
        )

        # ============================================================
        # 11. PRODUCTS
        # ============================================================

        product_count = 100 if is_large else 20

        category_list = list(categories.values())
        brand_list = list(brands.values())

        for index in range(1, product_count + 1):
            category = category_list[
                (index - 1) % len(category_list)
            ]

            brand = brand_list[
                (index - 1) % len(brand_list)
            ]

            cost_price = Decimal("100.00") + Decimal(index * 5)
            sales_price = cost_price * Decimal("1.30")

            Product.objects.update_or_create(
                tenant=tenant,
                sku=f"DEMO-SKU-{index:05d}",
                defaults={
                    "category": category,
                    "brand": brand,
                    "name": f"Demo Product {index}",
                    "barcode": f"890000{index:06d}",
                    "description": (
                        f"Realistic demo product number {index}"
                    ),
                    "sales_price": sales_price,
                    "cost_price": cost_price,
                    "stock_quantity": Decimal(
                        10 + (index * 3)
                    ),
                    "min_stock": 5,
                    "max_stock": 500,
                    "unit": "Piece",
                    "is_active": True,
                    "batch_number": "",
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Products ready: {product_count}"
            )
        )

        # ============================================================
        # COMPLETE
        # ============================================================

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                "========================================"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "POS development data seeded successfully!"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Mode: {'LARGE' if is_large else 'STANDARD'}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "========================================"
            )
        )

