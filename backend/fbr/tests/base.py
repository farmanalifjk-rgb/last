"""Shared fixtures for the FBR Digital Invoicing tests — DI API v1.12."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from fiscal.models import InvoiceSequence
from fiscal.services import issue_invoice
from pos.models import Category, Customer, Order, OrderItem, Product
from saas.models import Tenant, TenantMembership

from fbr.models import (
    FBRBuyerProfile,
    FBRConfiguration,
    FBRHSCode,
    FBRProductProfile,
    FBRProvince,
    FBRTransactionType,
    FBRUnitOfMeasure,
)

User = get_user_model()


class FBRTestBase(TestCase):
    def setUp(self):
        self.province_sindh = FBRProvince.objects.create(code="Sindh", description="Sindh")
        self.province_punjab = FBRProvince.objects.create(code="Punjab", description="Punjab")
        self.hs_code = FBRHSCode.objects.create(code="84713010", description="Laptops")
        self.uom = FBRUnitOfMeasure.objects.create(code="U1000012", description="Numbers, pieces, units")
        self.transaction_type = FBRTransactionType.objects.create(code="T1000075", description="Goods at standard rate (default)")

        self.user_a, self.tenant_a = self._make_tenant("a")
        self.user_b, self.tenant_b = self._make_tenant("b")
        self.config_a = self.make_config(self.tenant_a)
        self.invoice_a = self.make_invoice(self.tenant_a, "a")

    def _make_tenant(self, suffix):
        user = User.objects.create_user(
            username=f"admin_{suffix}", password="testpass123", email=f"{suffix}@test.com", is_staff=True
        )
        tenant = Tenant.objects.create(
            name=f"Tenant {suffix}", slug=f"tenant-{suffix}", owner=user, status="active"
        )
        TenantMembership.objects.create(tenant=tenant, user=user, role="owner", is_active_in_tenant=True)
        return user, tenant

    def make_config(self, tenant, **overrides):
        values = {
            "environment": "sandbox",
            "security_token": "test-token",
            "seller_ntn_cnic": "1234567",
            "seller_business_name": f"Seller {tenant.slug}",
            "seller_address": "Plot 5, Karachi",
            "seller_province": self.province_sindh,
            "scenario_id": "SN001",
            "default_transaction_type": self.transaction_type,
        }
        values.update(overrides)
        # Allow passing seller_province as string code for convenience
        if isinstance(values.get("seller_province"), str):
            prov, _ = FBRProvince.objects.get_or_create(code=values["seller_province"])
            values["seller_province"] = prov
        return FBRConfiguration.objects.create(tenant=tenant, **values)

    def make_ims_config(self, tenant, **overrides):
        """Tier-1 IMS Software Fiscal Component configuration (localhost:8524).

        One configuration exists per (tenant, environment), so when the base
        setUp already created one, it is upgraded to IMS mode in place.
        """
        values = {
            "environment": "sandbox",
            "integration_mode": "ims",
            "pos_registration_number": 110014,
            "seller_ntn_cnic": "1234567",
            "seller_business_name": f"Seller {tenant.slug}",
            "seller_address": "Plot 5, Karachi",
            "seller_province": self.province_sindh,
        }
        values.update(overrides)
        environment = values.get("environment", "sandbox")
        if isinstance(values.get("seller_province"), str):
            prov, _ = FBRProvince.objects.get_or_create(code=values["seller_province"])
            values["seller_province"] = prov
        existing = FBRConfiguration.objects.filter(tenant=tenant, environment=environment).first()
        if existing is not None:
            for field, value in values.items():
                setattr(existing, field, value)
            existing.save()
            return existing
        return FBRConfiguration.objects.create(tenant=tenant, **values)

    def make_invoice(self, tenant, suffix, *, quantity=Decimal("2"), unit_price=Decimal("100.00"),
                     discount=Decimal("0.00"), with_buyer_profile=True, with_product_profile=True,
                     buyer_province=None, buyer_registration_type="Registered", product_profile_overrides=None):
        category = Category.objects.create(tenant=tenant, name=f"Cat {suffix}")
        product = Product.objects.create(
            tenant=tenant, name=f"Product {suffix}", sku=f"SKU-{suffix}".upper(),
            sales_price=unit_price, cost_price=Decimal("50.00"), category=category,
        )
        customer = Customer.objects.create(
            tenant=tenant, name=f"Customer {suffix}", phone=f"0300-{suffix}",
            address="1 Main Street, Karachi",
        )
        subtotal = quantity * unit_price
        order = Order.objects.create(
            tenant=tenant, customer=customer, subtotal=subtotal, tax=Decimal("0.00"),
            discount=discount, total=subtotal - discount,
        )
        OrderItem.objects.create(
            tenant=tenant, order=order, product=product, quantity=quantity,
            unit_price=unit_price, subtotal=subtotal,
        )
        if with_product_profile:
            profile_values = {
                "tenant": tenant, "product": product, "hs_code": self.hs_code, "uom": self.uom,
                "transaction_type": self.transaction_type, "sales_tax_rate": Decimal("18.000"),
                "pct_code": "84713010",  # explicit PCT — IMS never guesses from HS (audit H7)
            }
            if product_profile_overrides:
                profile_values.update(product_profile_overrides)
            FBRProductProfile.objects.create(**profile_values)
        if with_buyer_profile:
            prov = buyer_province or self.province_sindh
            FBRBuyerProfile.objects.create(
                tenant=tenant, customer=customer, ntn_cnic="3520212345678",
                registered_name=f"Customer {suffix} (Pvt) Ltd", destination_address="1 Main Street, Karachi",
                buyer_province=prov, buyer_registration_type=buyer_registration_type,
            )
        sequence = InvoiceSequence.objects.create(
            tenant=tenant, name="Default", prefix=f"INV{suffix.upper()}", next_number=1, padding=6,
            document_type="invoice",
        )
        invoice = issue_invoice(
            tenant=tenant, order_id=order.id, sequence_id=sequence.id,
            customer_id=customer.id, user=tenant.owner,
        )
        # A fixture sale must be charged exactly what it reports to FBR (the
        # payload builders refuse a fiscal document that differs from the
        # amount collected). The order above is created untaxed, so record the
        # tax the product's FBR profile levies as what the customer paid.
        lines = list(invoice.lines.all())
        if lines:
            charged_total = sum((line.total_amount for line in lines), Decimal("0.00"))
            charged_tax = charged_total - (subtotal - discount)
            Order.objects.filter(pk=order.pk).update(tax=charged_tax, total=charged_total)
            invoice.tax, invoice.total = charged_tax, charged_total
            invoice.save(update_fields=["tax", "total"])
        return invoice

    def api_client(self, user):
        from auth_app.models import AuthToken

        client = APIClient()
        token = AuthToken.objects.create(user=user)
        client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        return client


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.text = str(body)

    def json(self):
        return self._body


class FakeSession:
    """Records the calls a client makes and replays queued responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _next(self, url, kwargs):
        self.calls.append({"url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, **kwargs):
        return self._next(url, kwargs)

    def get(self, url, **kwargs):
        return self._next(url, kwargs)
