from decimal import Decimal
from threading import Barrier, Thread

from django.db import close_old_connections
from django.test import TransactionTestCase
from transfers.models import StockTransfer

from django.contrib.auth import get_user_model

from enterprise.models import Warehouse, WarehouseStock
from pos.models import Category, Product
from saas.models import Tenant, TenantMembership
from transfers.services import create_transfer, receive_transfer


class TransferInventoryIntegrityTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="phase19-transfer", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase 19 Transfers", slug="phase19-transfers", owner=self.user)
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )
        self.category = Category.objects.create(tenant=self.tenant, name="Transfer Test")
        self.product = Product.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Transfer Product",
            sku="TRANSFER-SKU",
            sales_price=Decimal("10.00"),
            cost_price=Decimal("5.00"),
            stock_quantity=Decimal("10.000"),
        )
        self.source = Warehouse.objects.create(tenant=self.tenant, code="SOURCE", name="Source")
        self.destination = Warehouse.objects.create(tenant=self.tenant, code="DEST", name="Destination")
        WarehouseStock.objects.create(tenant=self.tenant, warehouse=self.source, product=self.product, quantity=Decimal("10.000"))

    def test_transfer_relocates_location_stock_without_changing_aggregate_product_stock(self):
        transfer = create_transfer(
            tenant=self.tenant,
            source=self.source,
            destination=self.destination,
            lines=[{"product_id": self.product.id, "quantity": "4"}],
            user=self.user,
        )
        self.product.refresh_from_db()
        self.assertEqual(transfer.transfer_number, f"TR-{self.tenant.id}-000001")
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))
        self.assertEqual(
            WarehouseStock.objects.get(tenant=self.tenant, warehouse=self.source, product=self.product).quantity,
            Decimal("6.000"),
        )

        receive_transfer(tenant=self.tenant, transfer_id=transfer.id, user=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))
        self.assertEqual(
            WarehouseStock.objects.get(tenant=self.tenant, warehouse=self.destination, product=self.product).quantity,
            Decimal("4.000"),
        )

    def test_concurrent_transfers_cannot_overspend_source_warehouse(self):
        barrier = Barrier(2)
        results = []
        errors = []

        def transfer():
            close_old_connections()

            try:
                barrier.wait()

                created = create_transfer(
                    tenant=self.tenant,
                    source=self.source,
                    destination=self.destination,
                    lines=[
                        {
                            "product_id": self.product.id,
                            "quantity": "7",
                        }
                    ],
                    user=self.user,
                )

                results.append(created.id)

            except Exception as exc:
                errors.append(type(exc).__name__)

            finally:
                close_old_connections()

        threads = [
            Thread(target=transfer),
            Thread(target=transfer),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(
            len(results),
            1,
            f"Expected exactly one transfer to succeed; "
            f"results={results}, errors={errors}",
        )

        self.assertEqual(
            len(errors),
            1,
            f"Expected exactly one transfer to fail; "
            f"results={results}, errors={errors}",
        )

        source_stock = WarehouseStock.objects.get(
            tenant=self.tenant,
            warehouse=self.source,
            product=self.product,
        )

        self.assertEqual(
            source_stock.quantity,
            Decimal("3.000"),
        )

        destination_stock = WarehouseStock.objects.filter(
            tenant=self.tenant,
            warehouse=self.destination,
            product=self.product,
        ).first()

        self.assertIsNone(
            destination_stock,
            "A transfer should not increase destination stock until received.",
        )

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.stock_quantity,
            Decimal("10.000"),
        )

        self.assertEqual(
            StockTransfer.objects.filter(
                tenant=self.tenant,
                product=self.product,
            ).count()
            if False
            else StockTransfer.objects.filter(
                tenant=self.tenant,
            ).count(),
            1,
        ) 

        self.assertEqual(
            StockTransfer.objects.filter(
                tenant=self.tenant,
            ).count(),
            1,
        )               
