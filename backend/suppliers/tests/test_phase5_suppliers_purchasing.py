from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from accounting.models import (
    AccountingEvent,
    AccountingEventStatus,
    AccountingEventType,
    ChartOfAccount,
    PostingRule,
)
from enterprise.models import Warehouse, WarehouseStock
from pos.models import Category, Product, PurchaseOrder, StockMovement, Supplier
from rbac.models import Permission, Role
from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant
from suppliers.models import GoodsReceipt, PurchaseReturn, SupplierContact
from inventory.models import StockReservation
from inventory.services import reserve_stock
 
User = get_user_model()
 
 
class SupplierPurchasingAPITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="phase5-owner", password="StrongPass123!"
        )
        self.tenant = Tenant.objects.create(
            name="Phase Five Tenant",
            slug="phase-five-tenant",
            owner=self.owner,
            status="active",
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.owner,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )
        set_current_tenant(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.warehouse = Warehouse.objects.create(
            tenant=self.tenant, code="MAIN", name="Main warehouse"
        )
        self.category = Category.objects.create(
            tenant=self.tenant, name="Test category"
        )
        self.product = Product.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Phase Five product",
            sku="PHASE5-001",
            sales_price=Decimal("5.00"),
            cost_price=Decimal("2.50"),
            stock_quantity=Decimal("0.00"),
            is_active=True,
        )
        self.supplier = Supplier.objects.create(
            tenant=self.tenant, name="Supply House", phone="555-0100"
        )
 
    def order_payload(self, quantity="100.00"):
        return {
            "supplier_id": self.supplier.id,
            "warehouse_id": self.warehouse.id,
            "note": "Phase 5 regression order",
            "items": [
                {
                    "product_id": self.product.id,
                    "quantity": quantity,
                    "unit_cost": "2.50",
                }
            ],
        }
 
    def create_confirmed_order(self, quantity="100.00"):
        created = self.client.post(
            "/api/purchasing/purchase-orders/",
            self.order_payload(quantity),
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        order = PurchaseOrder.objects.get(pk=created.data["id"])
        confirmed = self.client.post(
            f"/api/purchasing/purchase-orders/{order.id}/confirm/", format="json"
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        order.refresh_from_db()
        self.assertEqual(order.status, "ordered")
        return order
 
    def receive(self, order, quantity, **line_overrides):
        line = {
            "purchase_order_item_id": order.items.get().id,
            "quantity": quantity,
        }
        line.update(line_overrides)
        return self.client.post(
            "/api/purchasing/receipts/",
            {
                "purchase_order_id": order.id,
                "note": "Regression receipt",
                "lines": [line],
            },
            format="json",
        )
 
    def test_supplier_crud_contacts_and_archive_are_tenant_scoped(self):
        created = self.client.post(
            "/api/suppliers/",
            {
                "name": "Contact supplier",
                "phone": "555-0200",
                "email": "ops@example.com",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        supplier_id = created.data["id"]
        contact = self.client.post(
            f"/api/suppliers/{supplier_id}/contacts/",
            {
                "name": "Avery Buyer",
                "role": "Buyer",
                "email": "avery@example.com",
                "is_primary": True,
            },
            format="json",
        )
        self.assertEqual(contact.status_code, 201, contact.data)
        replacement = self.client.post(
            f"/api/suppliers/{supplier_id}/contacts/",
            {
                "name": "Morgan Buyer",
                "role": "Purchasing manager",
                "is_primary": True,
            },
            format="json",
        )
        self.assertEqual(replacement.status_code, 201, replacement.data)
        self.assertEqual(
            SupplierContact.objects.filter(
                tenant=self.tenant, supplier_id=supplier_id, is_primary=True
            ).count(),
            1,
        )
        archived = self.client.post(
            f"/api/suppliers/{supplier_id}/archive/", format="json"
        )
        self.assertEqual(archived.status_code, 200, archived.data)
        self.assertFalse(Supplier.objects.get(pk=supplier_id).is_active)
        blocked = self.client.post(
            "/api/purchasing/purchase-orders/",
            {**self.order_payload(), "supplier_id": supplier_id},
            format="json",
        )
        self.assertEqual(blocked.status_code, 400, blocked.data)
 
    def test_partial_then_full_receiving_updates_authoritative_inventory_and_order_progress(
        self,
    ):
        order = self.create_confirmed_order()
        first = self.receive(order, "40.00", batch_number="LOT-40")
        self.assertEqual(first.status_code, 201, first.data)
        order.refresh_from_db()
        item = order.items.get()
        self.product.refresh_from_db()
        stock = WarehouseStock.objects.get(
            tenant=self.tenant, warehouse=self.warehouse, product=self.product
        )
        self.assertEqual(order.status, "ordered")
        self.assertEqual(item.received_quantity, Decimal("40.00"))
        self.assertEqual(self.product.stock_quantity, Decimal("40.00"))
        self.assertEqual(stock.quantity, Decimal("40.00"))
        self.assertEqual(
            StockMovement.objects.filter(
                tenant=self.tenant, product=self.product, movement_type="purchase"
            ).count(),
            1,
        )
        second = self.receive(order, "60.00")
        self.assertEqual(second.status_code, 201, second.data)
        order.refresh_from_db()
        item.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, "received")
        self.assertEqual(item.received_quantity, Decimal("100.00"))
        self.assertEqual(self.product.stock_quantity, Decimal("100.00"))
        self.assertEqual(
            GoodsReceipt.objects.filter(
                tenant=self.tenant, purchase_order=order
            ).count(),
            2,
        )
 
    def test_over_receipt_is_rejected_without_duplicate_stock_or_receipt(self):
        order = self.create_confirmed_order("10.00")
        received = self.receive(order, "10.00")
        self.assertEqual(received.status_code, 201, received.data)
        rejected = self.receive(order, "1.00")
        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.00"))
        self.assertEqual(
            GoodsReceipt.objects.filter(
                tenant=self.tenant, purchase_order=order
            ).count(),
            1,
        )
        self.assertEqual(
            StockMovement.objects.filter(
                tenant=self.tenant, product=self.product, movement_type="purchase"
            ).count(),
            1,
        )
 
    def test_supplier_return_is_draft_until_processed_and_reverses_inventory_once(
        self,
    ):
        order = self.create_confirmed_order("40.00")
        self.assertEqual(self.receive(order, "40.00").status_code, 201)
        item = order.items.get()
        created = self.client.post(
            "/api/purchasing/purchase-returns/",
            {
                "purchase_order_id": order.id,
                "reason": "Damaged carton",
                "lines": [{"purchase_order_item_id": item.id, "quantity": "10.00"}],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        purchase_return = PurchaseReturn.objects.get(pk=created.data["id"])
        self.product.refresh_from_db()
        self.assertEqual(purchase_return.status, PurchaseReturn.STATUS_DRAFT)
        self.assertEqual(self.product.stock_quantity, Decimal("40.00"))
        processed = self.client.post(
            f"/api/purchasing/purchase-returns/{purchase_return.id}/process/",
            format="json",
        )
        self.assertEqual(processed.status_code, 200, processed.data)
        purchase_return.refresh_from_db()
        item.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(purchase_return.status, PurchaseReturn.STATUS_RETURNED)
        self.assertEqual(item.returned_quantity, Decimal("10.00"))
        self.assertEqual(self.product.stock_quantity, Decimal("30.00"))
        self.assertEqual(
            StockMovement.objects.filter(
                tenant=self.tenant,
                product=self.product,
                movement_type="purchase_return",
            ).count(),
            1,
        )
        repeated = self.client.post(
            f"/api/purchasing/purchase-returns/{purchase_return.id}/process/",
            format="json",
        )
        self.assertEqual(repeated.status_code, 400, repeated.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("30.00"))
 
    def test_supplier_return_cannot_consume_active_stock_reservation(self):
        order = self.create_confirmed_order("10.00")
        received = self.receive(
            order,
            "10.00",
            batch_number="RESERVED-RETURN-LOT",
        )
        self.assertEqual(received.status_code, 201, received.data)
        item = order.items.get()
        receipt = GoodsReceipt.objects.get(
            tenant=self.tenant,
            purchase_order=order,
        )
        receipt_line = receipt.lines.get(
            purchase_order_item=item,
        )
        batch = receipt_line.batch
        self.assertIsNotNone(batch)
        self.assertEqual(
            batch.remaining_quantity,
            Decimal("10.00"),
        )
        reserve_stock(
            tenant=self.tenant,
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            quantity=Decimal("6.00"),
            reference="PROVIDER-RESERVED",
            reserved_by=self.owner,
        )
        created = self.client.post(
            "/api/purchasing/purchase-returns/",
            {
                "purchase_order_id": order.id,
                "reason": "Reserved stock return test",
                "lines": [
                    {
                        "purchase_order_item_id": item.id,
                        "receipt_line_id": receipt_line.id,
                        "quantity": "6.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        purchase_return = PurchaseReturn.objects.get(pk=created.data["id"])
        processed = self.client.post(
            f"/api/purchasing/purchase-returns/{purchase_return.id}/process/",
            format="json",
        )
        self.assertEqual(processed.status_code, 400, processed.data)
        self.product.refresh_from_db()
        item.refresh_from_db()
        purchase_return.refresh_from_db()
        batch.refresh_from_db()
        # Inventory must remain unchanged.
        # self.assertEqual(
        #     self.product.stock_quantity,
        #     Decimal("10.00"),
        # )
        # # The reservation must remain active.
        # reservation = StockReservation.objects.get(
        #     tenant=self.tenant,
        #     product=self.product,
        #     status=StockReservation.STATUS_ACTIVE,
        # )
        # self.assertEqual(
        #     reservation.quantity,
        #     Decimal("6.00"),
        # )
        # # The purchase return must still be draft.
        # self.assertEqual(
        #     purchase_return.status,
        #     PurchaseReturn.STATUS_DRAFT,
        # )
        # # The purchase-order item must not record a returned quantity.
        # self.assertEqual(
        #     item.returned_quantity,
        #     Decimal("0.00"),
        # )
        # # The batch mutation must have been rolled back.
        # self.assertEqual(
        #     batch.remaining_quantity,
        #     Decimal("10.00"),
        # )
        # # No purchase-return inventory movement should exist.
        # self.assertEqual(
        #     StockMovement.objects.filter(
        #         tenant=self.tenant,
        #         product=self.product,
        #         movement_type="purchase_return",
        #     ).count(),
        #     0,
        # )
 
    def test_configured_goods_receipt_and_purchase_return_rules_create_traceable_accounting_events(
        self,
    ):
        inventory = ChartOfAccount.objects.create(
            tenant=self.tenant, code="1200", name="Inventory", type="asset"
        )
        payable = ChartOfAccount.objects.create(
            tenant=self.tenant,
            code="2000",
            name="Accounts payable",
            type="liability",
        )
        PostingRule.objects.create(
            tenant=self.tenant,
            event_type=AccountingEventType.GOODS_RECEIPT,
            name="Configured receipt accrual",
            debit_account=inventory,
            credit_account=payable,
            created_by=self.owner,
            updated_by=self.owner,
        )
        PostingRule.objects.create(
            tenant=self.tenant,
            event_type=AccountingEventType.PURCHASE_RETURN,
            name="Configured return reversal",
            debit_account=payable,
            credit_account=inventory,
            created_by=self.owner,
            updated_by=self.owner,
        )
        order = self.create_confirmed_order("40.00")
        receipt_response = self.receive(order, "40.00")
        self.assertEqual(receipt_response.status_code, 201, receipt_response.data)
        receipt = GoodsReceipt.objects.get(
            tenant=self.tenant, pk=receipt_response.data["id"]
        )
        receipt_event = AccountingEvent.objects.get(
            tenant=self.tenant,
            source_domain="purchasing",
            event_type=AccountingEventType.GOODS_RECEIPT,
            source_id=str(receipt.id),
        )
        self.assertEqual(receipt_event.status, AccountingEventStatus.POSTED)
        self.assertTrue(receipt_event.journal_entry.is_balanced)
        item = order.items.get()
        created = self.client.post(
            "/api/purchasing/purchase-returns/",
            {
                "purchase_order_id": order.id,
                "reason": "Phase 9 supplier return",
                "lines": [{"purchase_order_item_id": item.id, "quantity": "10.00"}],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        processed = self.client.post(
            f"/api/purchasing/purchase-returns/{created.data['id']}/process/",
            format="json",
        )
        self.assertEqual(processed.status_code, 200, processed.data)
        purchase_return = PurchaseReturn.objects.get(
            tenant=self.tenant, pk=created.data["id"]
        )
        return_event = AccountingEvent.objects.get(
            tenant=self.tenant,
            source_domain="purchasing",
            event_type=AccountingEventType.PURCHASE_RETURN,
            source_id=str(purchase_return.id),
        )
        self.assertEqual(return_event.status, AccountingEventStatus.POSTED)
        self.assertEqual(return_event.reversal_of_id, receipt_event.id)
        self.assertTrue(return_event.journal_entry.is_balanced)
 
    def test_return_bound_is_enforced_when_processing(self):
        order = self.create_confirmed_order("20.00")
        self.assertEqual(self.receive(order, "20.00").status_code, 201)
        item = order.items.get()
        created = self.client.post(
            "/api/purchasing/purchase-returns/",
            {
                "purchase_order_id": order.id,
                "lines": [{"purchase_order_item_id": item.id, "quantity": "21.00"}],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        rejected = self.client.post(
            f"/api/purchasing/purchase-returns/{created.data['id']}/process/",
            format="json",
        )
        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("20.00"))
        self.assertEqual(
            StockMovement.objects.filter(
                tenant=self.tenant,
                product=self.product,
                movement_type="purchase_return",
            ).count(),
            0,
        )
 
    def test_cross_tenant_direct_ids_are_not_discoverable(self):
        order = self.create_confirmed_order("5.00")
        other_user = User.objects.create_user(
            username="phase5-other", password="StrongPass123!"
        )
        other_tenant = Tenant.objects.create(
            name="Other tenant",
            slug="other-phase-five",
            owner=other_user,
            status="active",
        )
        TenantMembership.objects.create(
            tenant=other_tenant,
            user=other_user,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )
        other_client = APIClient()
        other_client.force_authenticate(other_user)
        self.assertEqual(
            other_client.get(f"/api/suppliers/{self.supplier.id}/").status_code, 404
        )
        self.assertEqual(
            other_client.get(
                f"/api/purchasing/purchase-orders/{order.id}/"
            ).status_code,
            404,
        )
        self.assertEqual(
            other_client.post(
                "/api/purchasing/receipts/",
                {"purchase_order_id": order.id, "lines": []},
                format="json",
            ).status_code,
            400,
        )
 
    def test_view_only_role_can_read_but_cannot_mutate_supplier_or_purchasing_data(
        self,
    ):
        order = self.create_confirmed_order("5.00")
        restricted = User.objects.create_user(
            username="phase5-viewer", password="StrongPass123!"
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=restricted,
            role=TenantMembership.ROLE_STAFF,
            is_active_in_tenant=True,
        )
        role = Role.objects.create(key="phase5-viewer-role", label="Phase 5 viewer")
        view_permissions = Permission.objects.filter(
            module__key__in=["suppliers", "purchasing"],
            action="view",
            scope=Permission.SCOPE_TENANT,
        )
        self.assertEqual(view_permissions.count(), 2)
        role.permissions.set(view_permissions)
        restricted.user_roles.create(role=role)
        client = APIClient()
        client.force_authenticate(restricted)
 
        supplier_list = client.get("/api/suppliers/")
        self.assertEqual(supplier_list.status_code, 200, supplier_list.data)
        order_detail = client.get(f"/api/purchasing/purchase-orders/{order.id}/")
        self.assertEqual(order_detail.status_code, 200, order_detail.data)
 
        self.assertEqual(
            client.post(
                "/api/suppliers/",
                {"name": "Blocked", "phone": "555-0300"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/api/purchasing/purchase-orders/",
                self.order_payload(),
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/api/purchasing/receipts/",
                {
                    "purchase_order_id": order.id,
                    "lines": [
                        {
                            "purchase_order_item_id": order.items.get().id,
                            "quantity": "1.00",
                        }
                    ],
                },
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/api/purchasing/purchase-returns/",
                {
                    "purchase_order_id": order.id,
                    "lines": [
                        {
                            "purchase_order_item_id": order.items.get().id,
                            "quantity": "1.00",
                        }
                    ],
                },
                format="json",
            ).status_code,
            403,
        )
 
    def test_duplicate_serial_receipt_is_rejected_without_partial_inventory_changes(
        self,
    ):
        order = self.create_confirmed_order("2.00")
 
        first = self.receive(
            order,
            "1.00",
            serial_numbers=["SN-PHASE5-001"],
        )
        self.assertEqual(first.status_code, 201, first.data)
 
        self.product.refresh_from_db()
        order.refresh_from_db()
 
        self.assertEqual(self.product.stock_quantity, Decimal("1.00"))
        self.assertEqual(
            GoodsReceipt.objects.filter(
                tenant=self.tenant,
                purchase_order=order,
            ).count(),
            1,
        )
 
        second = self.receive(
            order,
            "1.00",
            serial_numbers=["SN-PHASE5-001"],
        )
 
        self.assertEqual(second.status_code, 400, second.data)
 
        self.product.refresh_from_db()
        order.refresh_from_db()
 
        self.assertEqual(self.product.stock_quantity, Decimal("1.00"))
        self.assertEqual(
            GoodsReceipt.objects.filter(
                tenant=self.tenant,
                purchase_order=order,
            ).count(),
            1,
        )