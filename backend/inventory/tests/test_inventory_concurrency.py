from decimal import Decimal
from threading import Barrier, Thread

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase

from enterprise.models import Warehouse, WarehouseStock
from inventory.models import StockReservation
from inventory.services import available_stock, reserve_stock
from pos.models import Product
from saas.models import Tenant, TenantMembership


class InventoryConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()

        self.owner = user_model.objects.create_user(
            username="inventory-concurrency-owner",
            password="test-password",
        )

        self.tenant = Tenant.objects.create(
            name="Inventory Concurrency Tenant",
            slug="inventory-concurrency-tenant",
            owner=self.owner,
            is_active=True,
        )

        TenantMembership.objects.create(
            user=self.owner,
            tenant=self.tenant,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )

        self.warehouse = Warehouse.objects.create(
            tenant=self.tenant,
            code="CONC",
            name="Concurrency Warehouse",
        )

        self.product = Product.objects.create(
            tenant=self.tenant,
            name="Concurrency Widget",
            sku="CONC-001",
            stock_quantity=Decimal("10"),
            sales_price=Decimal("10"),
            cost_price=Decimal("4"),
        )

        WarehouseStock.objects.create(
            tenant=self.tenant,
            warehouse=self.warehouse,
            product=self.product,
            quantity=Decimal("10"),
        )

    def test_concurrent_reservations_cannot_oversell_stock(self):
        barrier = Barrier(2)
        results = []
        errors = []

        def reserve():
            close_old_connections()

            try:
                barrier.wait()

                reservation = reserve_stock(
                    tenant=self.tenant,
                    product_id=self.product.id,
                    warehouse_id=self.warehouse.id,
                    quantity=Decimal("7"),
                    reference="CONCURRENT-RESERVATION",
                    reserved_by=self.owner,
                )

                results.append(reservation.id)

            except Exception as exc:
                errors.append(type(exc).__name__)

            finally:
                close_old_connections()

        threads = [
            Thread(target=reserve),
            Thread(target=reserve),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(
            len(results),
            1,
            f"Expected exactly one reservation to succeed; "
            f"results={results}, errors={errors}",
        )

        self.assertEqual(
            len(errors),
            1,
            f"Expected exactly one reservation to fail; "
            f"results={results}, errors={errors}",
        )

        active_reservations = StockReservation.objects.filter(
            tenant=self.tenant,
            product=self.product,
            warehouse=self.warehouse,
            status=StockReservation.STATUS_ACTIVE,
        )

        self.assertEqual(active_reservations.count(), 1)
        self.assertEqual(
            active_reservations.first().quantity,
            Decimal("7"),
        )

        self.product.refresh_from_db()

        self.assertEqual(
            available_stock(
                self.tenant,
                self.product,
                self.warehouse,
            ),
            Decimal("3"),
        )

    def test_concurrent_adjustments_cannot_drive_stock_negative(self):
        from inventory.services import apply_adjustment

        barrier = Barrier(2)
        results = []
        errors = []

        def adjust():
            close_old_connections()

            try:
                barrier.wait()

                apply_adjustment(
                    tenant=self.tenant,
                    product_id=self.product.id,
                    warehouse_id=self.warehouse.id,
                    quantity=Decimal("-7"),
                    reason="Concurrent stock deduction",
                    note="Concurrency test",
                    user=self.owner,
                    movement_type="adjustment",
                    reference="CONCURRENT-ADJUSTMENT",
                )

                results.append("success")

            except Exception as exc:
                errors.append(type(exc).__name__)

            finally:
                close_old_connections()

        threads = [
            Thread(target=adjust),
            Thread(target=adjust),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(
            len(results),
            1,
            f"Expected exactly one adjustment to succeed; "
            f"results={results}, errors={errors}",
        )

        self.assertEqual(
            len(errors),
            1,
            f"Expected exactly one adjustment to fail; "
            f"results={results}, errors={errors}",
        )

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.stock_quantity,
            Decimal("3"),
        )

        warehouse_stock = WarehouseStock.objects.get(
            tenant=self.tenant,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            warehouse_stock.quantity,
            Decimal("3"),
        )  

    def test_adjustment_does_not_silently_break_existing_reservation(self):
        reservation = reserve_stock(
            tenant=self.tenant,
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=Decimal("6"),
            reference="RESERVED-BEFORE-ADJUSTMENT",
            reserved_by=self.owner,
        )

        self.assertEqual(
            available_stock(
                self.tenant,
                self.product,
                self.warehouse,
            ),
            Decimal("4"),
        )

        from inventory.services import apply_adjustment

        with self.assertRaises(ValueError):
            apply_adjustment(
                tenant=self.tenant,
                product_id=self.product.id,
                warehouse_id=self.warehouse.id,
                quantity=Decimal("-6"),
                reason="Physical count correction",
                note="Adjustment after reservation",
                user=self.owner,
                movement_type="adjustment",
                reference="ADJUSTMENT-AFTER-RESERVATION",
            )

        self.product.refresh_from_db()

        warehouse_stock = WarehouseStock.objects.get(
            tenant=self.tenant,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            self.product.stock_quantity,
            Decimal("10"),
        )

        self.assertEqual(
            warehouse_stock.quantity,
            Decimal("10"),
        )

        self.assertEqual(
            reservation.status,
            StockReservation.STATUS_ACTIVE,
        )

        self.assertEqual(
            available_stock(
                self.tenant,
                self.product,
                self.warehouse,
            ),
            Decimal("4"),
        )

    def test_normal_stock_decrease_cannot_consume_reserved_stock(self):
        from inventory.services import apply_adjustment

        reserve_stock(
            tenant=self.tenant,
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=Decimal("6"),
            reference="PROVIDER-RESERVED",
            reserved_by=self.owner,
        )

        with self.assertRaises(ValueError):
            apply_adjustment(
                tenant=self.tenant,
                product_id=self.product.id,
                warehouse_id=self.warehouse.id,
                quantity=Decimal("-6"),
                reason="Physical count correction",
                note="Adjustment after reservation",
                user=self.owner,
                movement_type="adjustment",
                reference="ADJUSTMENT-AFTER-RESERVATION",
            )

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.stock_quantity,
            Decimal("10"),
        )

        warehouse_stock = WarehouseStock.objects.get(
            tenant=self.tenant,
            warehouse=self.warehouse,
            product=self.product,
        )

        self.assertEqual(
            warehouse_stock.quantity,
            Decimal("10"),
        )

        self.assertEqual(
            available_stock(
                self.tenant,
                self.product,
                self.warehouse,
            ),
            Decimal("4"),
        )                  