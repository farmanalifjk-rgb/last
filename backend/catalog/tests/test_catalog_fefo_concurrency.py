from datetime import date
from decimal import Decimal
from threading import Barrier, Thread
from django.db import close_old_connections
from django.test import TransactionTestCase
from catalog.models import SerialNumber
from catalog.services import mark_serial_sold

from catalog.models import Batch, BatchMovement
from catalog.services import allocate_batch_fefo
from pos.models import Product
from saas.models import Tenant, TenantMembership
from django.contrib.auth import get_user_model
from pos.models import Order


class CatalogFefoConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()

        self.user = user_model.objects.create_user(
            username="fefo-owner",
            password="test-password",
        )

        self.tenant = Tenant.objects.create(
            name="FEFO Tenant",
            slug="fefo-tenant",
            owner=self.user,
            is_active=True,
        )

        TenantMembership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )

        self.product = Product.objects.create(
            tenant=self.tenant,
            name="FEFO Product",
            sku="FEFO-1",
            sales_price=Decimal("10.00"),
            cost_price=Decimal("5.00"),
        )

        self.batch = Batch.objects.create(
            tenant=self.tenant,
            product=self.product,
            batch_number="FEFO-BATCH-1",
            quantity=Decimal("10.00"),
            remaining_quantity=Decimal("10.00"),
            expiry_date=date(2026, 12, 31),
        )

    def test_concurrent_fefo_allocations_cannot_overspend_batch(self):
        barrier = Barrier(2)
        results = []
        errors = []

        def allocate():
            close_old_connections()
            try:
                barrier.wait()

                allocations = allocate_batch_fefo(
                    product=self.product,
                    quantity=Decimal("7.00"),
                    kind=BatchMovement.KIND_SALE,
                    reference="CONCURRENT-FEFO",
                    user=self.user,
                )

                results.append(
                    sum(quantity for _, quantity in allocations)
                )
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            Thread(target=allocate),
            Thread(target=allocate),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)

        self.batch.refresh_from_db()

        self.assertEqual(
            self.batch.remaining_quantity,
            Decimal("3.00"),
        )

        self.assertEqual(
            BatchMovement.objects.filter(
                tenant=self.tenant,
                batch=self.batch,
                kind=BatchMovement.KIND_SALE,
                reference="CONCURRENT-FEFO",
            ).count(),
            1,
        )

        self.assertEqual(
            results[0],
            Decimal("7.00"),
        )

    def test_concurrent_serial_sales_cannot_sell_same_serial_twice(self):
        order_one = Order.objects.create(
            tenant=self.tenant,
            payment_method="cash",
        )
        order_two = Order.objects.create(
            tenant=self.tenant,
            payment_method="cash",
        )
    
        serial = SerialNumber.objects.create(
            tenant=self.tenant,
            product=self.product,
            serial_number="SN-CONCURRENT-001",
            status=SerialNumber.STATUS_IN_STOCK,
        )
    
        barrier = Barrier(2)
        results = []
        errors = []
    
        def sell(order):
            close_old_connections()
            try:
                barrier.wait()
                sold = mark_serial_sold(serial, order)
                results.append(sold.sold_in_order_id)
            except Exception as exc:
                errors.append(str(exc))
            finally:
                close_old_connections()
    
        thread_one = Thread(target=sell, args=(order_one,))
        thread_two = Thread(target=sell, args=(order_two,))
    
        thread_one.start()
        thread_two.start()
    
        thread_one.join()
        thread_two.join()
    
        serial.refresh_from_db()
    
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(serial.status, SerialNumber.STATUS_SOLD)
        self.assertEqual(serial.sold_in_order_id, results[0])
    
        self.assertEqual(
            SerialNumber.objects.filter(
                tenant=self.tenant,
                product=self.product,
                serial_number="SN-CONCURRENT-001",
                status=SerialNumber.STATUS_SOLD,
            ).count(),
            1,
        )        