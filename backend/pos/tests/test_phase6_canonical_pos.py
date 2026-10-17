from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounting.models import AccountingEvent, AccountingEventStatus, AccountingEventType, ChartOfAccount, PostingRule
from enterprise.models import Warehouse, WarehouseStock
from inventory.models import StockReservation
from pos.models import CashSession, Category, Order, Product, Refund, StockAdjustment, StockMovement
from pricing.models import PriceList, PriceListItem
from rbac.models import Permission, Role, UserRole
from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant
from tax.models import TaxBreakdown, TaxRate


User = get_user_model()


class Phase6CanonicalPOSTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="phase6-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="Phase 6 Tenant", slug="phase6-tenant", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)
        set_current_tenant(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.category = Category.objects.create(tenant=self.tenant, name="Phase 6 Category")
        self.product = Product.objects.create(tenant=self.tenant, category=self.category, name="Phase 6 Coffee", sku="P6-COFFEE", barcode="909090", sales_price=Decimal("5.00"), cost_price=Decimal("2.00"), stock_quantity=Decimal("10.000"), is_active=True)
        TaxRate.objects.create(tenant=self.tenant, name="VAT", code="VAT10", rate=Decimal("0.1000"), is_active=True, applies_to_all=True)
        price_list = PriceList.objects.create(tenant=self.tenant, name="POS default", is_default=True, is_active=True)
        PriceListItem.objects.create(tenant=self.tenant, price_list=price_list, product=self.product, price=Decimal("4.50"), min_quantity=Decimal("1"))
        self.session = CashSession.objects.create(tenant=self.tenant, opened_by=self.owner, employee_name="Owner", opening_balance=Decimal("50.00"), is_open=True)

    def test_product_search_reports_available_stock_for_session_warehouse(self):
        warehouse = Warehouse.objects.create(tenant=self.tenant, code="POS-1", name="POS Warehouse")
        self.session.warehouse = warehouse
        self.session.save(update_fields=["warehouse"])
        WarehouseStock.objects.create(
            tenant=self.tenant,
            warehouse=warehouse,
            product=self.product,
            quantity=Decimal("4.00"),
        )
        StockReservation.objects.create(
            tenant=self.tenant,
            warehouse=warehouse,
            product=self.product,
            quantity=Decimal("1.00"),
        )

        response = self.client.get("/api/pos/products/?page_size=100")

        self.assertEqual(response.status_code, 200, response.data)
        product = next(row for row in response.data["results"] if row["id"] == self.product.id)
        self.assertEqual(product["stock_quantity"], "10.000")
        self.assertEqual(product["available_quantity"], "3.00")

    def _checkout(self, **overrides):
        payload = {
            "items": [{"product_id": self.product.id, "quantity": "2.000"}],
            "tenders": [{"tender_type": "cash", "amount": "20.00"}],
        }
        payload.update(overrides)
        return self.client.post("/api/pos/checkout/", payload, format="json", HTTP_IDEMPOTENCY_KEY=overrides.get("idempotency_key", "phase6-checkout-1"))

    def test_checkout_persists_idempotency_request_fingerprint(self):
        response = self._checkout(idempotency_key="phase6-fingerprint")
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(tenant=self.tenant, pk=response.data["order"]["id"])
        self.assertEqual(len(order.idempotency_request_hash), 64)
        self.assertNotEqual(order.idempotency_request_hash, "")

    def test_reusing_idempotency_key_with_different_request_is_rejected(self):
        created = self._checkout(idempotency_key="phase6-conflict")
        self.assertEqual(created.status_code, 201, created.data)

        replay = self._checkout(
            idempotency_key="phase6-conflict",
            items=[{"product_id": self.product.id, "quantity": "1.000"}],
        )
        self.assertEqual(replay.status_code, 409, replay.data)
        self.assertEqual(replay.data["error"]["code"], "IDEMPOTENCY_KEY_REUSED")
        self.assertEqual(Order.objects.filter(tenant=self.tenant, idempotency_key="phase6-conflict").count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("8.000"))

    def test_checkout_rejects_idempotency_keys_longer_than_128_characters(self):
        response = self._checkout(idempotency_key="x" * 129)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("128 characters or fewer", str(response.data))
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))

    def test_checkout_rejects_quantity_above_order_item_capacity_without_mutation(self):
        response = self._checkout(
            items=[{"product_id": self.product.id, "quantity": "100000000"}],
            idempotency_key="quantity-overflow",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("cannot exceed 99,999,999.99", str(response.data))
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))

    def test_checkout_rejects_combined_duplicate_quantity_overflow_without_mutation(self):
        response = self._checkout(
            items=[
                {"product_id": self.product.id, "quantity": "60000000"},
                {"product_id": self.product.id, "quantity": "40000000"},
            ],
            idempotency_key="combined-quantity-overflow",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Combined cart quantity cannot exceed 99,999,999.99", str(response.data))
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))

    def test_checkout_rejects_quantity_precision_that_order_item_cannot_store(self):
        response = self._checkout(
            items=[{"product_id": self.product.id, "quantity": "0.001"}],
            idempotency_key="quantity-precision",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("at most 2 decimal places", str(response.data))
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))

    def test_checkout_rejects_non_finite_quantity_without_mutation(self):
        response = self._checkout(
            items=[{"product_id": self.product.id, "quantity": "NaN"}],
            idempotency_key="non-finite-quantity",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("quantity must be a finite number", str(response.data))
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))

    def test_checkout_rejects_missing_product_id_without_mutation(self):
        response = self._checkout(
            items=[{"quantity": "1"}],
            idempotency_key="missing-product-id",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("valid product_id", str(response.data))
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))

    def test_checkout_rejects_null_product_id_without_mutation(self):
        response = self._checkout(
            items=[{"product_id": None, "quantity": "1"}],
            idempotency_key="null-product-id",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("valid product_id", str(response.data))
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))

    def test_checkout_rejects_fractional_product_id_without_mutation(self):
        response = self._checkout(
            items=[{"product_id": self.product.id + 0.9, "quantity": "1"}],
            idempotency_key="fractional-product-id",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("valid product_id", str(response.data))
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))

    def test_checkout_rejects_boolean_product_id_without_mutation(self):
        response = self._checkout(
            items=[{"product_id": True, "quantity": "1"}],
            idempotency_key="boolean-product-id",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("valid product_id", str(response.data))
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))

    def test_preview_uses_tenant_price_rule_and_tax_engine(self):
        response = self.client.post("/api/pos/preview/", {"items": [{"product_id": self.product.id, "quantity": "2.000"}]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["subtotal"], "9.00")
        self.assertEqual(response.data["tax"], "0.90")
        self.assertEqual(response.data["total"], "9.90")

    def test_17_percent_rate_preview_and_persisted_checkout_match_at_large_value(self):
        rate = TaxRate.objects.get(tenant=self.tenant, code="VAT10")
        rate.rate = Decimal("0.1700")
        rate.save(update_fields=["rate"])
        PriceListItem.objects.filter(tenant=self.tenant, product=self.product).update(price=Decimal("24999.00"))
        cart = [{"product_id": self.product.id, "quantity": "1"}]

        preview = self.client.post("/api/pos/preview/", {"items": cart}, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual((preview.data["subtotal"], preview.data["tax"], preview.data["total"]),
                         ("24999.00", "4249.83", "29248.83"))

        created = self._checkout(
            items=cart, tenders=[{"tender_type": "cash", "amount": "29248.83"}],
            idempotency_key="fractional-17-percent",
        )
        self.assertEqual(created.status_code, 201, created.data)
        order = Order.objects.get(tenant=self.tenant, pk=created.data["order"]["id"])
        breakdown = TaxBreakdown.objects.get(order=order)
        self.assertEqual((order.subtotal, order.tax, order.total),
                         (Decimal("24999.00"), Decimal("4249.83"), Decimal("29248.83")))
        self.assertEqual(breakdown.tax_amount, Decimal("4249.83"))
        self.assertEqual(order.amount_received, Decimal("29248.83"))
        self.assertEqual(created.data["receipt"]["totals"]["total"], "29248.83")

    def test_inclusive_tax_checkout_does_not_increase_payable_total(self):
        TaxRate.objects.filter(tenant=self.tenant, code="VAT10").update(mode=TaxRate.MODE_INCLUSIVE)
        body = {"items": [{"product_id": self.product.id, "quantity": "2"}]}
        preview = self.client.post("/api/pos/preview/", body, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual((preview.data["subtotal"], preview.data["tax"], preview.data["total"]),
                         ("9.00", "0.82", "9.00"))
        created = self._checkout(
            items=body["items"], tenders=[{"tender_type": "cash", "amount": "9.00"}],
            idempotency_key="inclusive-price",
        )
        self.assertEqual(created.status_code, 201, created.data)
        order = Order.objects.get(tenant=self.tenant, pk=created.data["order"]["id"])
        self.assertEqual((order.tax, order.total, order.amount_received),
                         (Decimal("0.82"), Decimal("9.00"), Decimal("9.00")))
        self.assertEqual(TaxBreakdown.objects.get(order=order).tax_amount, Decimal("0.82"))

    def test_discount_preview_checkout_breakdown_and_payment_round_identically(self):
        body = {"items": [{"product_id": self.product.id, "quantity": "2"}], "discount": "1.00"}
        preview = self.client.post("/api/pos/preview/", body, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual((preview.data["subtotal"], preview.data["discount"], preview.data["tax"], preview.data["total"]),
                         ("9.00", "1.00", "0.80", "8.80"))
        created = self._checkout(
            items=body["items"], discount=body["discount"],
            tenders=[{"tender_type": "cash", "amount": "8.80"}], idempotency_key="discount-rounding",
        )
        self.assertEqual(created.status_code, 201, created.data)
        order = Order.objects.get(tenant=self.tenant, pk=created.data["order"]["id"])
        self.assertEqual((order.tax, order.total, order.amount_received),
                         (Decimal("0.80"), Decimal("8.80"), Decimal("8.80")))
        self.assertEqual(TaxBreakdown.objects.get(order=order).tax_amount, Decimal("0.80"))

    def test_checkout_is_idempotent_and_persists_tax_payment_inventory_and_receipt(self):
        created = self._checkout()
        self.assertEqual(created.status_code, 201, created.data)
        self.assertFalse(created.data["idempotent_replay"])
        order_id = created.data["order"]["id"]
        order = Order.objects.get(pk=order_id, tenant=self.tenant)
        self.product.refresh_from_db()
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.total, Decimal("9.90"))
        self.assertEqual(order.change_amount, Decimal("10.10"))
        self.assertEqual(self.product.stock_quantity, Decimal("8.000"))
        self.assertEqual(order.tenders.count(), 1)
        self.assertEqual(TaxBreakdown.objects.filter(tenant=self.tenant, order=order).count(), 1)
        self.assertEqual(StockMovement.objects.filter(tenant=self.tenant, product=self.product, movement_type="sale").count(), 1)
        replayed = self._checkout()
        self.assertEqual(replayed.status_code, 200, replayed.data)
        self.assertTrue(replayed.data["idempotent_replay"])
        self.assertEqual(replayed.data["order"]["id"], order_id)
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(StockMovement.objects.filter(tenant=self.tenant, product=self.product, movement_type="sale").count(), 1)
        receipt = self.client.get(f"/api/pos/orders/{order_id}/receipt/")
        self.assertEqual(receipt.status_code, 200, receipt.data)
        self.assertEqual(receipt.data["totals"]["total"], "9.90")

    def test_underpayment_rolls_back_order_stock_movements_and_tax_breakdowns(self):
        response = self._checkout(tenders=[{"tender_type": "cash", "amount": "1.00"}], idempotency_key="underpayment")
        self.assertEqual(response.status_code, 400, response.data)
        self.product.refresh_from_db()
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))
        self.assertEqual(StockMovement.objects.filter(tenant=self.tenant).count(), 0)
        self.assertEqual(TaxBreakdown.objects.filter(tenant=self.tenant).count(), 0)

    def test_cross_tenant_product_and_order_ids_are_not_accepted(self):
        other_owner = User.objects.create_user(username="phase6-other", password="StrongPass123!")
        other_tenant = Tenant.objects.create(name="Other tenant", slug="phase6-other", owner=other_owner, status="active")
        TenantMembership.objects.create(tenant=other_tenant, user=other_owner, role="owner", is_active_in_tenant=True)
        other_category = Category.objects.create(tenant=other_tenant, name="Other category")
        other_product = Product.objects.create(tenant=other_tenant, category=other_category, name="Other product", sku="OTHER-SKU", sales_price=Decimal("5"), cost_price=Decimal("1"), stock_quantity=Decimal("5"), is_active=True)
        denied = self.client.post("/api/pos/preview/", {"items": [{"product_id": other_product.id, "quantity": "1"}]}, format="json")
        self.assertEqual(denied.status_code, 400, denied.data)
        created = self._checkout(idempotency_key="tenant-order")
        order_id = created.data["order"]["id"]
        self.client.force_authenticate(other_owner)
        detail = self.client.get(f"/api/pos/orders/{order_id}/")
        self.assertEqual(detail.status_code, 404)

    def test_park_and_resume_use_only_the_owner_active_session(self):
        parked = self.client.post("/api/pos/parked-sales/", {"label": "Counter hold", "items": [{"product_id": self.product.id, "quantity": "1"}]}, format="json")
        self.assertEqual(parked.status_code, 201, parked.data)
        listed = self.client.get("/api/pos/parked-sales/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        resumed = self.client.post(f"/api/pos/parked-sales/{parked.data['id']}/resume/", {}, format="json")
        self.assertEqual(resumed.status_code, 200, resumed.data)
        self.assertEqual(resumed.data["status"], "resumed")

    def test_refund_is_bounded_and_restores_canonical_inventory(self):
        checkout = self._checkout(idempotency_key="refund-sale")
        order = Order.objects.get(tenant=self.tenant, pk=checkout.data["order"]["id"])
        item = order.items.get()
        forbidden = self.client.post("/api/pos/refunds/", {"order_id": order.id, "items": [{"order_item_id": item.id, "quantity": "3"}]}, format="json")
        self.assertEqual(forbidden.status_code, 400, forbidden.data)
        valid = self.client.post("/api/pos/refunds/", {"order_id": order.id, "items": [{"order_item_id": item.id, "quantity": "2"}], "reason": "Customer changed mind"}, format="json")
        self.assertEqual(valid.status_code, 201, valid.data)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("10.000"))
        self.assertEqual(order.status, "refunded")
        self.assertEqual(Refund.objects.filter(tenant=self.tenant, order=order).count(), 1)

    def test_configured_sale_and_refund_rules_create_one_traceable_accounting_posting_per_operational_event(self):
        cash = ChartOfAccount.objects.create(tenant=self.tenant, code="1000", name="Cash", type="asset")
        revenue = ChartOfAccount.objects.create(tenant=self.tenant, code="4000", name="Revenue", type="revenue")
        PostingRule.objects.create(
            tenant=self.tenant,
            event_type=AccountingEventType.POS_SALE_NET,
            name="Configured sale revenue",
            debit_account=cash,
            credit_account=revenue,
            created_by=self.owner,
            updated_by=self.owner,
        )
        PostingRule.objects.create(
            tenant=self.tenant,
            event_type=AccountingEventType.POS_REFUND_NET,
            name="Configured sale refund",
            debit_account=revenue,
            credit_account=cash,
            created_by=self.owner,
            updated_by=self.owner,
        )
        settlement_clearing = ChartOfAccount.objects.create(tenant=self.tenant, code="1050", name="Settlement clearing", type="asset")
        PostingRule.objects.create(
            tenant=self.tenant,
            event_type=AccountingEventType.PAYMENT_TENDER,
            source_key="tender_type",
            source_value="cash",
            name="Configured cash settlement",
            debit_account=cash,
            credit_account=settlement_clearing,
            created_by=self.owner,
            updated_by=self.owner,
        )
        checkout = self._checkout(idempotency_key="phase9-configured-sale")
        self.assertEqual(checkout.status_code, 201, checkout.data)
        order = Order.objects.get(tenant=self.tenant, pk=checkout.data["order"]["id"])
        sale_event = AccountingEvent.objects.get(
            tenant=self.tenant,
            source_domain="pos",
            event_type=AccountingEventType.POS_SALE_NET,
            source_id=str(order.id),
        )
        self.assertEqual(sale_event.status, AccountingEventStatus.POSTED)
        self.assertTrue(sale_event.journal_entry.is_balanced)
        self.assertTrue(sale_event.journal_entry.is_auto_posted)
        tender_event = AccountingEvent.objects.get(
            tenant=self.tenant,
            source_domain="payments",
            event_type=AccountingEventType.PAYMENT_TENDER,
            payload__order_id=order.id,
        )
        self.assertEqual(tender_event.status, AccountingEventStatus.POSTED)
        self.assertTrue(tender_event.journal_entry.is_balanced)
        replay = self._checkout(idempotency_key="phase9-configured-sale")
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(AccountingEvent.objects.filter(tenant=self.tenant, event_type=AccountingEventType.POS_SALE_NET, source_id=str(order.id)).count(), 1)
        item = order.items.get()
        refund_response = self.client.post(
            "/api/pos/refunds/",
            {"order_id": order.id, "items": [{"order_item_id": item.id, "quantity": "2"}], "reason": "Phase 9 traceability"},
            format="json",
        )
        self.assertEqual(refund_response.status_code, 201, refund_response.data)
        refund = Refund.objects.get(tenant=self.tenant, order=order)
        refund_event = AccountingEvent.objects.get(
            tenant=self.tenant,
            source_domain="pos",
            event_type=AccountingEventType.POS_REFUND_NET,
            source_id=str(refund.id),
        )
        self.assertEqual(refund_event.status, AccountingEventStatus.POSTED)
        self.assertEqual(refund_event.reversal_of_id, sale_event.id)
        self.assertTrue(refund_event.journal_entry.is_balanced)

    def test_view_only_staff_can_read_but_cannot_mutate_pos(self):
        viewer = User.objects.create_user(username="phase6-viewer", password="StrongPass123!")
        TenantMembership.objects.create(tenant=self.tenant, user=viewer, role="staff", is_active_in_tenant=True)
        role = Role.objects.create(key="phase6-pos-viewer", label="Phase 6 POS viewer")
        role.permissions.add(Permission.objects.get(module__key="pos", action="view"))
        UserRole.objects.create(user=viewer, role=role)
        viewer_client = APIClient()
        viewer_client.force_authenticate(viewer)
        self.assertEqual(viewer_client.get("/api/pos/products/?barcode=909090").status_code, 200)
        self.assertEqual(viewer_client.get("/api/pos/orders/").status_code, 200)
        self.assertEqual(viewer_client.post("/api/pos/sessions/open/", {"opening_balance": "0"}, format="json").status_code, 403)
        self.assertEqual(viewer_client.post("/api/pos/checkout/", {"items": [{"product_id": self.product.id, "quantity": "1"}], "tenders": [{"tender_type": "cash", "amount": "10"}]}, format="json", HTTP_IDEMPOTENCY_KEY="viewer-checkout").status_code, 403)


class Phase19POSFinancialSafetyTests(Phase6CanonicalPOSTests):
    def test_checkout_uses_tenant_company_currency_and_canonical_tender_fields(self):
        from pos.models import Company

        Company.objects.create(tenant=self.tenant, name="Currency Tenant", address="", currency="PKR")
        response = self._checkout(idempotency_key="phase19-currency")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["order"]["tenders"][0]["tender_type"], "cash")
        self.assertEqual(response.data["order"]["tenders"][0]["currency"], "PKR")
        self.assertEqual(response.data["receipt"]["totals"]["currency"], "PKR")

    def test_cash_session_subtracts_only_explicit_cash_refunds(self):
        created = self._checkout(idempotency_key="phase19-cash-refund")
        order_id = created.data["order"]["id"]
        order = Order.objects.get(pk=order_id, tenant=self.tenant)
        item = order.items.get()

        refunded = self.client.post(
            "/api/pos/refunds/",
            {
                "order_id": order_id,
                "items": [{"order_item_id": item.id, "quantity": "2"}],
                "cash_refund_amount": "9.90",
            },
            format="json",
        )
        self.assertEqual(refunded.status_code, 201, refunded.data)
        self.assertEqual(refunded.data["cash_refund_amount"], "9.90")

        closed = self.client.post("/api/pos/sessions/close/", {"actual_cash": "50.00"}, format="json")
        self.assertEqual(closed.status_code, 200, closed.data)
        self.assertEqual(closed.data["expected_cash"], "50.00")
        self.assertEqual(closed.data["difference"], "0.00")

    def test_stock_adjustment_numbers_are_tenant_local(self):
        other_owner = User.objects.create_user(username="phase19-adjustment-owner", password="StrongPass123!")
        other_tenant = Tenant.objects.create(name="Adjustment Tenant B", slug="phase19-adjustment-b", owner=other_owner)
        first_a = StockAdjustment.objects.create(
            tenant=self.tenant, adjustment_type="increase", reason="Count correction"
        )
        first_b = StockAdjustment.objects.create(
            tenant=other_tenant, adjustment_type="increase", reason="Count correction"
        )
        second_a = StockAdjustment.objects.create(
            tenant=self.tenant, adjustment_type="decrease", reason="Count correction"
        )

        self.assertEqual(first_a.adjustment_number, "SA-000001")
        self.assertEqual(first_b.adjustment_number, "SA-000001")
        self.assertEqual(second_a.adjustment_number, "SA-000002")
