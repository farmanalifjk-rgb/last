"""POS product listing stock/tenant scope and checkout idempotency under concurrency.

Covers the production-readiness audit findings:
* /api/pos/products/ must only list the caller's active tenant, report sellable
  stock for the location checkout will decrement, and paginate deterministically.
* Checkout must never oversell, and concurrent duplicate submissions with one
  Idempotency-Key must create exactly one sale (second request replays).
"""

import threading
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from enterprise.models import Warehouse, WarehouseStock
from inventory.models import StockReservation
from pos.models import CashSession, Category, Order, Product, StockMovement
from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant


User = get_user_model()


def _product(tenant, name, *, stock, barcode="", sku=None, category=None, active=True):
    return Product.objects.create(
        tenant=tenant, category=category, name=name, sku=sku or name.upper().replace(" ", "-"), barcode=barcode,
        sales_price=Decimal("5.00"), cost_price=Decimal("2.00"), stock_quantity=Decimal(stock), is_active=active,
    )


class POSProductListingStockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="listing-cashier", password="StrongPass123!")
        self.other_owner = User.objects.create_user(username="listing-other-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Listing Tenant A", slug="listing-a", owner=self.user, status="active")
        self.other = Tenant.objects.create(name="Listing Tenant B", slug="listing-b", owner=self.other_owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role="owner", is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.other, user=self.other_owner, role="owner", is_active_in_tenant=True)
        set_current_tenant(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _list(self, **params):
        response = self.client.get("/api/pos/products/", params)
        self.assertEqual(response.status_code, 200, getattr(response, "data", response.content))
        return response.data

    def _row(self, data, product):
        rows = [row for row in data["results"] if row["id"] == product.id]
        self.assertEqual(len(rows), 1, f"product {product.id} not listed exactly once")
        return rows[0]

    def test_listing_never_returns_another_tenants_products_or_stock(self):
        mine = _product(self.tenant, "Shared Name Tea", stock="0", barcode="5550001")
        theirs = _product(self.other, "Shared Name Tea", stock="25", barcode="5550002")

        data = self._list(page_size=100)
        ids = {row["id"] for row in data["results"]}
        self.assertIn(mine.id, ids)
        self.assertNotIn(theirs.id, ids)
        self.assertEqual(Decimal(self._row(data, mine)["available_quantity"]), Decimal("0"))

        # Barcode and search lookups are tenant-scoped too.
        self.assertEqual(self._list(barcode="5550002")["results"], [])
        self.assertEqual({row["id"] for row in self._list(search="Shared")["results"]}, {mine.id})

    def test_zero_stock_follows_the_active_tenant_and_switching_changes_scope(self):
        """A user in two tenants sees the active tenant's stock only (no cross-tenant leakage)."""
        TenantMembership.objects.create(tenant=self.other, user=self.user, role="owner", is_active_in_tenant=False)
        mine = _product(self.tenant, "Milk", stock="0")
        theirs = _product(self.other, "Milk", stock="12")

        data = self._list()
        self.assertEqual([row["id"] for row in data["results"]], [mine.id])
        self.assertEqual(Decimal(data["results"][0]["available_quantity"]), Decimal("0"))

        switched = self.client.post("/api/saas/tenants/switch/", {"tenant_id": self.other.id}, format="json")
        self.assertEqual(switched.status_code, 200, switched.content)
        data = self._list()
        self.assertEqual([row["id"] for row in data["results"]], [theirs.id])
        self.assertEqual(Decimal(data["results"][0]["available_quantity"]), Decimal("12"))
        # The stock itself was never moved between tenants.
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual((mine.stock_quantity, theirs.stock_quantity), (Decimal("0"), Decimal("12")))

    def test_available_quantity_subtracts_only_active_unexpired_reservations(self):
        product = _product(self.tenant, "Reserved Rice", stock="10")
        now = timezone.now()
        StockReservation.objects.create(tenant=self.tenant, product=product, quantity=Decimal("3"))
        StockReservation.objects.create(tenant=self.tenant, product=product, quantity=Decimal("1"), expires_at=now + timedelta(hours=1))
        StockReservation.objects.create(tenant=self.tenant, product=product, quantity=Decimal("4"), expires_at=now - timedelta(minutes=1))
        StockReservation.objects.create(tenant=self.tenant, product=product, quantity=Decimal("2"), status=StockReservation.STATUS_RELEASED)
        StockReservation.objects.create(tenant=self.tenant, product=product, quantity=Decimal("2"), status=StockReservation.STATUS_FULFILLED)

        row = self._row(self._list(), product)
        self.assertEqual(Decimal(row["on_hand_quantity"]), Decimal("10"))
        self.assertEqual(Decimal(row["reserved_quantity"]), Decimal("4"))
        self.assertEqual(Decimal(row["available_quantity"]), Decimal("6"))
        self.assertEqual(Decimal(row["stock_quantity"]), Decimal("10"))
        self.assertIsNone(row["stock_warehouse_id"])

    def test_session_warehouse_scopes_listed_stock_to_that_warehouse(self):
        product = _product(self.tenant, "Warehouse Sugar", stock="10")
        unstocked = _product(self.tenant, "Warehouse Salt", stock="7")
        front = Warehouse.objects.create(tenant=self.tenant, code="FRONT", name="Front")
        back = Warehouse.objects.create(tenant=self.tenant, code="BACK", name="Back")
        WarehouseStock.objects.create(tenant=self.tenant, warehouse=front, product=product, quantity=Decimal("4"))
        WarehouseStock.objects.create(tenant=self.tenant, warehouse=back, product=product, quantity=Decimal("6"))
        StockReservation.objects.create(tenant=self.tenant, product=product, warehouse=front, quantity=Decimal("1"))
        StockReservation.objects.create(tenant=self.tenant, product=product, warehouse=back, quantity=Decimal("5"))

        # No open session: tenant aggregate minus all active reservations.
        row = self._row(self._list(), product)
        self.assertEqual(Decimal(row["available_quantity"]), Decimal("4"))

        CashSession.objects.create(tenant=self.tenant, opened_by=self.user, employee_name="Cashier", opening_balance=Decimal("0"), is_open=True, warehouse=front)
        data = self._list()
        row = self._row(data, product)
        self.assertEqual(row["stock_warehouse_id"], front.id)
        self.assertEqual(Decimal(row["on_hand_quantity"]), Decimal("4"))
        self.assertEqual(Decimal(row["reserved_quantity"]), Decimal("1"))
        self.assertEqual(Decimal(row["available_quantity"]), Decimal("3"))
        # No WarehouseStock row in this warehouse means nothing sellable here.
        self.assertEqual(Decimal(self._row(data, unstocked)["available_quantity"]), Decimal("0"))

    def test_inactive_products_are_not_listed(self):
        _product(self.tenant, "Inactive Item", stock="5", active=False)
        active = _product(self.tenant, "Active Item", stock="5")
        self.assertEqual([row["id"] for row in self._list()["results"]], [active.id])

    def test_pagination_envelope_lets_the_client_load_every_product_once(self):
        category = Category.objects.create(tenant=self.tenant, name="Bulk")
        created = [_product(self.tenant, f"Bulk {index:03d}", stock="1", category=category) for index in range(125)]
        _product(self.other, "Bulk other tenant", stock="1")

        default = self._list()
        self.assertEqual(default["count"], 125)
        self.assertEqual(len(default["results"]), 10)  # backend default page size
        self.assertTrue(default["has_next"])

        seen, page = [], 1
        while True:
            data = self._list(page=page, page_size=100)
            seen.extend(row["id"] for row in data["results"])
            self.assertEqual(data["total_pages"], 2)
            if not data["has_next"]:
                break
            page += 1
        self.assertEqual(page, 2)
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), {product.id for product in created})

        capped = self._list(page_size=1000)
        self.assertEqual(len(capped["results"]), 100)  # max_page_size


class POSCheckoutStockGuardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="guard-cashier", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Guard Tenant", slug="guard-tenant", owner=self.user, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role="owner", is_active_in_tenant=True)
        set_current_tenant(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.product = _product(self.tenant, "Guard Bread", stock="2")

    def _checkout(self, quantity, key):
        return self.client.post(
            "/api/pos/checkout/",
            {"items": [{"product_id": self.product.id, "quantity": str(quantity)}], "tenders": [{"tender_type": "cash", "amount": "100.00"}]},
            format="json", HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_checkout_cannot_sell_reserved_or_missing_stock(self):
        CashSession.objects.create(tenant=self.tenant, opened_by=self.user, employee_name="Cashier", opening_balance=Decimal("0"), is_open=True)
        StockReservation.objects.create(tenant=self.tenant, product=self.product, quantity=Decimal("1"))
        listed = self.client.get("/api/pos/products/").data["results"][0]
        self.assertEqual(Decimal(listed["available_quantity"]), Decimal("1"))

        refused = self._checkout(2, "guard-oversell")
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertFalse(Order.objects.filter(tenant=self.tenant).exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("2"))

        accepted = self._checkout(1, "guard-ok")
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("1"))

    def test_checkout_with_warehouse_session_uses_the_listed_warehouse_quantity(self):
        self.product.stock_quantity = Decimal("10")
        self.product.save(update_fields=["stock_quantity"])
        warehouse = Warehouse.objects.create(tenant=self.tenant, code="TILL", name="Till")
        WarehouseStock.objects.create(tenant=self.tenant, warehouse=warehouse, product=self.product, quantity=Decimal("1"))
        CashSession.objects.create(tenant=self.tenant, opened_by=self.user, employee_name="Cashier", opening_balance=Decimal("0"), is_open=True, warehouse=warehouse)
        listed = self.client.get("/api/pos/products/").data["results"][0]
        self.assertEqual(Decimal(listed["available_quantity"]), Decimal("1"))

        refused = self._checkout(2, "guard-warehouse-oversell")
        self.assertEqual(refused.status_code, 400, refused.data)
        self.assertEqual(WarehouseStock.objects.get(warehouse=warehouse, product=self.product).quantity, Decimal("1"))

        accepted = self._checkout(1, "guard-warehouse-ok")
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertEqual(WarehouseStock.objects.get(warehouse=warehouse, product=self.product).quantity, Decimal("0"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("9"))


@skipUnlessDBFeature("has_select_for_update")
class POSConcurrentDuplicateCheckoutTests(TransactionTestCase):
    """Double-click / client retry: the same Idempotency-Key submitted concurrently."""

    def setUp(self):
        self.user = User.objects.create_user(username="race-cashier", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Race Tenant", slug="race-tenant", owner=self.user, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role="owner", is_active_in_tenant=True)
        self.product = _product(self.tenant, "Race Coffee", stock="10")
        CashSession.objects.create(tenant=self.tenant, opened_by=self.user, employee_name="Cashier", opening_balance=Decimal("0"), is_open=True)

    def test_concurrent_duplicate_submission_creates_one_sale_and_replays_the_other(self):
        payload = {"items": [{"product_id": self.product.id, "quantity": "2"}], "tenders": [{"tender_type": "cash", "amount": "50.00"}]}
        barrier = threading.Barrier(2)
        results = []

        def submit():
            client = APIClient()
            client.force_authenticate(self.user)
            try:
                barrier.wait(timeout=10)
                response = client.post("/api/pos/checkout/", payload, format="json", HTTP_IDEMPOTENCY_KEY="race-key-1")
                results.append((response.status_code, getattr(response, "data", None)))
            except Exception as exc:  # pragma: no cover - surfaced through the assertion below
                results.append((None, repr(exc)))
            finally:
                connection.close()

        threads = [threading.Thread(target=submit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        statuses = sorted(status for status, _ in results)
        self.assertEqual(statuses, [200, 201], results)
        order_ids = {data["order"]["id"] for _, data in results}
        self.assertEqual(len(order_ids), 1, results)
        self.assertEqual([data["idempotent_replay"] for _, data in sorted(results, key=lambda r: r[0])], [True, False])
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(StockMovement.objects.filter(tenant=self.tenant, product=self.product, movement_type="sale").count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("8"))
