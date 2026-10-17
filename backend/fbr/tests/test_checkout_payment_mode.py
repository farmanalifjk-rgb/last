"""PaymentMode must follow the REAL checkout flow (audit H3).

Checkout persists canonical ``payments.TenderedPayment`` rows via
``settle_order``; a mixed cash+card tender must fiscalize as IMS PaymentMode 5
through the actual ``POST /api/pos/checkout/`` endpoint, not a synthetic one.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from fbr.ims_payload import build_ims_invoice_payload
from fbr.models import FBRConfiguration, FBRHSCode, FBRProductProfile, FBRUnitOfMeasure
from fiscal.models import InvoiceSequence
from fiscal.services import issue_invoice
from payments.models import TenderedPayment
from pos.models import CashSession, Category, Company, Product
from pricing.models import PriceList, PriceListItem
from tax.models import TaxRate
from saas.models import Tenant, TenantMembership

User = get_user_model()


@override_settings(ROOT_URLCONF="backend.urls")
class CheckoutPaymentModeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="ims-checkout-owner", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="IMS Checkout", slug="ims-checkout", owner=self.owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)
        self.category = Category.objects.create(tenant=self.tenant, name="IMS Cat")
        self.product = Product.objects.create(
            tenant=self.tenant, category=self.category, name="IMS Widget", sku="IMS-W1",
            sales_price=Decimal("5.00"), cost_price=Decimal("2.00"),
            stock_quantity=Decimal("10.000"), is_active=True,
        )
        PriceList.objects.create(tenant=self.tenant, name="POS default", is_default=True, is_active=True)
        PriceListItem.objects.create(
            tenant=self.tenant,
            price_list=PriceList.objects.get(tenant=self.tenant, name="POS default"),
            product=self.product, price=Decimal("5.00"), min_quantity=Decimal("1"),
        )
        CashSession.objects.create(
            tenant=self.tenant, opened_by=self.owner, employee_name="Owner",
            opening_balance=Decimal("0.00"), is_open=True,
        )
        Company.objects.create(tenant=self.tenant, name="IMS Retail", address="Karachi", currency="PKR")
        # POS-side 18% tax so the receipt, the tenders and the FBR envelope agree.
        TaxRate.objects.create(tenant=self.tenant, name="GST", code="GST18", rate=Decimal("0.1800"),
                               is_active=True, applies_to_all=True)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _checkout_mixed(self):
        return self.client.post(
            "/api/pos/checkout/",
            {
                "items": [{"product_id": self.product.id, "quantity": "1.000"}],
                "tenders": [
                    {"tender_type": "cash", "amount": "2.95"},
                    {"tender_type": "card", "amount": "2.95"},
                ],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="ims-mixed-checkout-1",
        )

    def test_mixed_checkout_persists_tenders_and_yields_payment_mode_5(self):
        response = self._checkout_mixed()
        self.assertEqual(response.status_code, 201, response.data)
        from pos.models import Order as OrderModel

        order = OrderModel.objects.get(tenant=self.tenant, pk=response.data["order"]["id"])
        # The real checkout recorded both tenders and marked the order split.
        self.assertEqual(order.tenders.count(), 2)
        self.assertEqual(
            set(order.tenders.values_list("tender_type", flat=True)), {"cash", "card"}
        )
        self.assertEqual(order.payment_method, "split")
        self.assertEqual(order.status, "paid")

        # Fiscalizing that order reports IMS PaymentMode 5 (Mixed).
        hs = FBRHSCode.objects.create(code="84713010", description="Laptops")
        uom = FBRUnitOfMeasure.objects.create(code="U1000012", description="Numbers, pieces, units")
        FBRProductProfile.objects.create(
            tenant=self.tenant, product=self.product, hs_code=hs, uom=uom,
            pct_code="84713010", sales_tax_rate=Decimal("18.000"),
        )
        config = FBRConfiguration.objects.create(
            tenant=self.tenant, environment="sandbox", integration_mode="ims",
            pos_registration_number=110014, seller_ntn_cnic="1234567",
            seller_business_name="IMS Retail", seller_address="Karachi",
        )
        sequence = InvoiceSequence.objects.create(
            tenant=self.tenant, name="Default", prefix="IMS", document_type="invoice",
        )
        invoice = issue_invoice(
            tenant=self.tenant, order_id=order.id, sequence_id=sequence.id, user=self.owner,
        )
        payload = build_ims_invoice_payload(invoice, config=config)
        self.assertEqual(payload["PaymentMode"], 5)  # Mixed — genuine cash+card tender
        # The fiscal envelope matches the taxed receipt: 5.00 + 0.90 GST = 5.90.
        self.assertEqual(payload["TotalSaleValue"], 5.0)
        self.assertEqual(payload["TotalTaxCharged"], 0.9)
        self.assertEqual(payload["TotalBillAmount"], 5.9)
        self.assertEqual(Decimal(str(payload["TotalBillAmount"])), order.total)
        self.assertTrue(TenderedPayment.objects.filter(order=order, tender_type="card").exists())

    def test_single_tender_checkout_yields_its_own_payment_mode(self):
        response = self.client.post(
            "/api/pos/checkout/",
            {
                "items": [{"product_id": self.product.id, "quantity": "1.000"}],
                "tenders": [{"tender_type": "card", "amount": "5.90"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="ims-card-checkout-1",
        )
        self.assertEqual(response.status_code, 201, response.data)
        from pos.models import Order as OrderModel

        order = OrderModel.objects.get(tenant=self.tenant, pk=response.data["order"]["id"])
        self.assertEqual(order.tenders.count(), 1)
        self.assertEqual(order.payment_method, "card")

        hs = FBRHSCode.objects.create(code="84713010", description="Laptops")
        uom = FBRUnitOfMeasure.objects.create(code="U1000012", description="Numbers, pieces, units")
        FBRProductProfile.objects.create(
            tenant=self.tenant, product=self.product, hs_code=hs, uom=uom,
            pct_code="84713010", sales_tax_rate=Decimal("18.000"),
        )
        config = FBRConfiguration.objects.create(
            tenant=self.tenant, environment="sandbox", integration_mode="ims",
            pos_registration_number=110014, seller_ntn_cnic="1234567",
            seller_business_name="IMS Retail", seller_address="Karachi",
        )
        sequence = InvoiceSequence.objects.create(
            tenant=self.tenant, name="Default", prefix="IMS2", document_type="invoice",
        )
        invoice = issue_invoice(
            tenant=self.tenant, order_id=order.id, sequence_id=sequence.id, user=self.owner,
        )
        payload = build_ims_invoice_payload(invoice, config=config)
        self.assertEqual(payload["PaymentMode"], 2)  # Card — single tender
        self.assertEqual(payload["TotalQuantity"], 1.0)
