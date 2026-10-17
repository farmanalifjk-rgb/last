from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from enterprise.models import Warehouse, WarehouseStock
from inventory.models import CycleCount, StockReservation
from inventory.services import available_stock
from pos.models import Product, StockMovement
from saas.models import Tenant, TenantMembership


class InventoryApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="inventory-owner", password="test-password")
        self.other_owner = user_model.objects.create_user(username="inventory-other", password="test-password")
        self.tenant = Tenant.objects.create(name="Inventory Tenant", slug="inventory-tenant", owner=self.owner, is_active=True)
        self.other_tenant = Tenant.objects.create(name="Inventory Other", slug="inventory-other", owner=self.other_owner, is_active=True)
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(user=self.other_owner, tenant=self.other_tenant, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        self.warehouse = Warehouse.objects.create(tenant=self.tenant, code="MAIN", name="Main")
        self.destination = Warehouse.objects.create(tenant=self.tenant, code="BACK", name="Back")
        self.foreign_warehouse = Warehouse.objects.create(tenant=self.other_tenant, code="MAIN", name="Foreign")
        self.product = Product.objects.create(tenant=self.tenant, name="Widget", sku="INV-001", stock_quantity=Decimal("10"), sales_price=Decimal("10"), cost_price=Decimal("4"))
        self.foreign_product = Product.objects.create(tenant=self.other_tenant, name="Foreign Widget", sku="INV-002", stock_quantity=Decimal("7"), sales_price=Decimal("10"), cost_price=Decimal("4"))
        WarehouseStock.objects.create(tenant=self.tenant, warehouse=self.warehouse, product=self.product, quantity=Decimal("10"), reorder_point=Decimal("3"))
        WarehouseStock.objects.create(tenant=self.other_tenant, warehouse=self.foreign_warehouse, product=self.foreign_product, quantity=Decimal("7"))
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_inventory_warehouse_and_stock_queries_reject_cross_tenant_ids(self):
        own = self.client.get(f"/api/inventory/stock/?warehouse_id={self.warehouse.id}")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.data["count"], 1)
        self.assertEqual(own.data["results"][0]["product"], self.product.id)

        foreign_detail = self.client.get(f"/api/inventory/warehouses/{self.foreign_warehouse.id}/")
        self.assertEqual(foreign_detail.status_code, 404)

        foreign_stock = self.client.get(f"/api/inventory/stock/?warehouse_id={self.foreign_warehouse.id}")
        self.assertEqual(foreign_stock.status_code, 200)
        self.assertEqual(foreign_stock.data["count"], 0)

    def test_reservation_reduces_available_stock_and_release_restores_it(self):
        response = self.client.post("/api/inventory/reservations/", {"product": self.product.id, "warehouse": self.warehouse.id, "quantity": "3", "reference": "ORDER-1"}, format="json")
        self.assertEqual(response.status_code, 201)
        reservation = StockReservation.objects.get(pk=response.data["id"])
        self.assertEqual(available_stock(self.tenant, self.product, self.warehouse), Decimal("7"))

        release = self.client.post(f"/api/inventory/reservations/{reservation.id}/release/")
        self.assertEqual(release.status_code, 200)
        self.assertEqual(available_stock(self.tenant, self.product, self.warehouse), Decimal("10"))

    def test_adjustment_uses_inventory_service_and_writes_movement(self):
        response = self.client.post("/api/inventory/adjustments/", {"product": self.product.id, "warehouse": self.warehouse.id, "adjustment_quantity": "2", "reason": "Receiving correction", "note": "Counted extra units"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("12"))
        self.assertEqual(WarehouseStock.objects.get(tenant=self.tenant, warehouse=self.warehouse, product=self.product).quantity, Decimal("12"))
        self.assertTrue(StockMovement.objects.filter(tenant=self.tenant, product=self.product, movement_type="adjustment", quantity=Decimal("2")).exists())

    def test_cycle_count_applies_a_single_auditable_variance_adjustment(self):
        count = CycleCount.objects.create(tenant=self.tenant, warehouse=self.warehouse, reference="CC-1", started_by=self.owner)
        response = self.client.post(f"/api/inventory/cycle-counts/{count.id}/run/", {"lines": [{"product_id": self.product.id, "counted_quantity": "8", "note": "Physical count"}]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"]["status"], CycleCount.STATUS_RECONCILED)
        self.assertEqual(len(response.data["movements"]), 1)
        self.assertTrue(StockMovement.objects.filter(tenant=self.tenant, movement_type="adjustment", quantity=Decimal("-2")).exists())

    def test_bins_reorder_alerts_and_inventory_analytics_are_tenant_scoped(self):
        created_bin = self.client.post("/api/inventory/bins/", {
            "warehouse": self.warehouse.id, "code": "A-01-01", "zone": "A", "aisle": "01", "rack": "01", "bin": "01",
        }, format="json")
        self.assertEqual(created_bin.status_code, 201, created_bin.data)
        self.assertEqual(created_bin.data["warehouse"], self.warehouse.id)

        created_rule = self.client.post("/api/inventory/reorder-rules/", {
            "product": self.product.id, "warehouse": self.warehouse.id,
            "reorder_point": "12", "target_stock": "20", "is_active": True,
        }, format="json")
        self.assertEqual(created_rule.status_code, 201, created_rule.data)

        alerts = self.client.get("/api/inventory/reorder-alerts/")
        self.assertEqual(alerts.status_code, 200)
        self.assertEqual(alerts.data[0]["product_id"], self.product.id)
        self.assertEqual(alerts.data[0]["warehouse_id"], self.warehouse.id)

        abc = self.client.get("/api/inventory/abc/")
        aging = self.client.get("/api/inventory/aging/")
        self.assertEqual(abc.status_code, 200)
        self.assertEqual(aging.status_code, 200)
        self.assertEqual(aging.data["results"][0]["product"], self.product.id)

    def test_transfer_debits_source_then_receipt_credits_destination_with_movements(self):
        dispatched = self.client.post("/api/transfers/transfers/", {
            "source_warehouse": self.warehouse.id,
            "destination_warehouse": self.destination.id,
            "items": [{"product_id": self.product.id, "quantity": "4"}],
        }, format="json")
        self.assertEqual(dispatched.status_code, 201, dispatched.data)
        self.assertEqual(dispatched.data["status"], "in_transit")
        self.assertEqual(WarehouseStock.objects.get(tenant=self.tenant, warehouse=self.warehouse, product=self.product).quantity, Decimal("6"))
        received = self.client.post(f"/api/transfers/transfers/{dispatched.data['id']}/receive/", {}, format="json")
        self.assertEqual(received.status_code, 200, received.data)
        self.assertEqual(received.data["status"], "received")
        self.assertEqual(WarehouseStock.objects.get(tenant=self.tenant, warehouse=self.destination, product=self.product).quantity, Decimal("4"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10"))
        self.assertEqual(StockMovement.objects.filter(tenant=self.tenant, reference=dispatched.data["transfer_number"], movement_type="transfer_out").count(), 1)
        self.assertEqual(StockMovement.objects.filter(tenant=self.tenant, reference=dispatched.data["transfer_number"], movement_type="transfer_in").count(), 1)


class AdjustmentListFilterTests(TestCase):
    """Phase 5: the Adjustments screen filters and CSV export are server-side."""

    def setUp(self):
        InventoryApiTests.setUp(self)  # same fixture, without re-running its tests
        import datetime as dt

        from django.utils import timezone
        from pos.models import StockAdjustment, StockAdjustmentItem

        def make(number, reason, note="", product=None, tenant=None, days_ago=0):
            tenant = tenant or self.tenant
            adjustment = StockAdjustment.objects.create(
                tenant=tenant, adjustment_number=number, adjustment_type="decrease", reason=reason, note=note,
            )
            StockAdjustment.objects.filter(pk=adjustment.pk).update(created_at=timezone.now() - dt.timedelta(days=days_ago))
            StockAdjustmentItem.objects.create(
                tenant=tenant, adjustment=adjustment, product=product or self.product, adjustment_type="decrease",
                quantity=Decimal("1"), previous_stock=Decimal("10"), new_stock=Decimal("9"),
            )
            return adjustment

        self.today = timezone.localdate()
        self.damaged = make("ADJ-1", "Damaged", note="Dropped crate")
        self.count = make("ADJ-2", "Stock count", days_ago=10)
        self.foreign = make("ADJ-1", "Damaged", product=self.foreign_product, tenant=self.other_tenant)

    def numbers(self, query=""):
        response = self.client.get(f"/api/inventory/adjustments/{query}")
        self.assertEqual(response.status_code, 200, response.data)
        return [row["adjustment_number"] for row in response.data["results"]]

    def test_filters_are_applied_and_tenant_scoped(self):
        self.assertEqual(self.numbers(), ["ADJ-1", "ADJ-2"])
        self.assertEqual(self.numbers("?reason=damaged"), ["ADJ-1"])
        self.assertEqual(self.numbers("?search=crate"), ["ADJ-1"])
        self.assertEqual(self.numbers("?search=INV-001"), ["ADJ-1", "ADJ-2"])  # product SKU
        self.assertEqual(self.numbers("?search=Foreign"), [])  # other tenant's product
        self.assertEqual(self.numbers(f"?date_from={self.today.isoformat()}"), ["ADJ-1"])
        self.assertEqual(self.numbers(f"?date_to={(self.today - __import__('datetime').timedelta(days=5)).isoformat()}"), ["ADJ-2"])

    def test_invalid_date_is_a_validation_error(self):
        response = self.client.get("/api/inventory/adjustments/?date_from=yesterday")
        self.assertEqual(response.status_code, 400)
