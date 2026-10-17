"""
Fiscal module cross-tenant isolation tests.
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from pos.models import Order, Customer, Category, Product
from saas.models import Tenant, TenantMembership
from fiscal.models import InvoiceSequence, FiscalDevice
User = get_user_model()

class FiscalTestBase(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="admin_a", password="testpass123", email="a@test.com", is_staff=True)
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a", owner=self.user_a, status="active")
        TenantMembership.objects.create(tenant=self.tenant_a, user=self.user_a, role="owner", is_active_in_tenant=True)
        self.cat_a = Category.objects.create(tenant=self.tenant_a, name="Cat A")
        self.product_a = Product.objects.create(tenant=self.tenant_a, name="Product A", sku="SKU-A", sales_price=Decimal("10.00"), cost_price=Decimal("5.00"), category=self.cat_a)
        self.customer_a = Customer.objects.create(tenant=self.tenant_a, name="Customer A", phone="111")
        self.order_a = Order.objects.create(tenant=self.tenant_a, customer=self.customer_a, subtotal=Decimal("100.00"), tax=Decimal("10.00"), discount=Decimal("0.00"), total=Decimal("110.00"))
        self.seq_a = InvoiceSequence.objects.create(tenant=self.tenant_a, name="Default", prefix="INV", next_number=1, padding=6, document_type="invoice")
        self.device_a = FiscalDevice.objects.create(tenant=self.tenant_a, name="Device A", kind="api", endpoint_url="https://tax-a.example.com", api_key="secret-key-a")
        self.user_b = User.objects.create_user(username="admin_b", password="testpass123", email="b@test.com", is_staff=True)
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b", owner=self.user_b, status="active")
        TenantMembership.objects.create(tenant=self.tenant_b, user=self.user_b, role="owner", is_active_in_tenant=True)
        self.seq_b = InvoiceSequence.objects.create(tenant=self.tenant_b, name="Default", prefix="INV", next_number=1, padding=6, document_type="invoice")
        self.device_b = FiscalDevice.objects.create(tenant=self.tenant_b, name="Device B", kind="api", endpoint_url="https://tax-b.example.com", api_key="secret-key-b")

    def _client(self, user):
        client = APIClient()
        from auth_app.models import AuthToken
        token = AuthToken.objects.create(user=user)
        client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        return client

    def _issue_a_invoice(self):
        from fiscal.services import issue_invoice
        return issue_invoice(tenant=self.tenant_a, order_id=self.order_a.id, sequence_id=self.seq_a.id, customer_id=self.customer_a.id, user=self.user_a)

    def _issue_b_invoice(self):
        from fiscal.services import issue_invoice
        cat = Category.objects.create(tenant=self.tenant_b, name="Cat B")
        Product.objects.create(tenant=self.tenant_b, name="Product B", sku="SKU-B", sales_price=Decimal("20.00"), cost_price=Decimal("10.00"), category=cat)
        customer = Customer.objects.create(tenant=self.tenant_b, name="Customer B", phone="222")
        order = Order.objects.create(tenant=self.tenant_b, customer=customer, subtotal=Decimal("200.00"), tax=Decimal("20.00"), discount=Decimal("0.00"), total=Decimal("220.00"))
        return issue_invoice(tenant=self.tenant_b, order_id=order.id, sequence_id=self.seq_b.id, customer_id=customer.id, user=self.user_b)

@override_settings(ROOT_URLCONF="backend.urls")
class FiscalSequenceIsolationTests(FiscalTestBase):
    def test_cannot_list_other_tenant_sequences(self):
        client = self._client(self.user_b)
        response = client.get("/api/fiscal/sequences/")
        self.assertEqual(response.status_code, 200)
        ids = [s["id"] for s in (response.data.get("results", response.data) if isinstance(response.data, dict) else response.data)]
        self.assertNotIn(self.seq_a.id, ids)

    def test_cannot_access_other_tenant_sequence_detail(self):
        client = self._client(self.user_b)
        response = client.get("/api/fiscal/sequences/" + str(self.seq_a.id) + "/")
        self.assertIn(response.status_code, [400, 403, 404])

@override_settings(ROOT_URLCONF="backend.urls")
class FiscalInvoiceIsolationTests(FiscalTestBase):
    def test_cannot_list_other_tenant_invoices(self):
        inv_a = self._issue_a_invoice()
        client = self._client(self.user_b)
        response = client.get("/api/fiscal/invoices/")
        self.assertEqual(response.status_code, 200)
        ids = [i["id"] for i in (response.data.get("results", response.data) if isinstance(response.data, dict) else response.data)]
        self.assertNotIn(inv_a.id, ids)

    def test_cannot_access_other_tenant_invoice_detail(self):
        inv_a = self._issue_a_invoice()
        client = self._client(self.user_b)
        response = client.get("/api/fiscal/invoices/" + str(inv_a.id) + "/")
        self.assertIn(response.status_code, [400, 403, 404])

    def test_cannot_cancel_other_tenant_invoice(self):
        inv_a = self._issue_a_invoice()
        client = self._client(self.user_b)
        response = client.post("/api/fiscal/invoices/" + str(inv_a.id) + "/cancel/")
        self.assertIn(response.status_code, [400, 403, 404])
        inv_a.refresh_from_db()
        self.assertEqual(inv_a.status, "issued")

    def test_tenant_field_cannot_be_injected(self):
        client = self._client(self.user_b)
        response = client.post("/api/fiscal/sequences/", {"name": "Hacked", "prefix": "HCK", "tenant": self.tenant_a.id}, format="json")
        if response.status_code == 201:
            self.assertEqual(response.data["tenant"], self.tenant_b.id)

@override_settings(ROOT_URLCONF="backend.urls")
class FiscalDeviceIsolationTests(FiscalTestBase):
    def test_cannot_list_other_tenant_devices(self):
        client = self._client(self.user_b)
        response = client.get("/api/fiscal/devices/")
        self.assertEqual(response.status_code, 200)
        ids = [d["id"] for d in (response.data.get("results", response.data) if isinstance(response.data, dict) else response.data)]
        self.assertNotIn(self.device_a.id, ids)

    def test_api_key_never_exposed_in_response(self):
        client = self._client(self.user_a)
        response = client.get("/api/fiscal/devices/")
        self.assertEqual(response.status_code, 200)
        for device in (response.data.get("results", response.data) if isinstance(response.data, dict) else response.data):
            self.assertNotIn("api_key", device)

@override_settings(ROOT_URLCONF="backend.urls")
class FiscalServiceErrorTests(FiscalTestBase):
    def test_issue_invoice_rejects_wrong_sequence(self):
        from fiscal.services import issue_invoice, FiscalServiceError
        with self.assertRaises(FiscalServiceError):
            issue_invoice(tenant=self.tenant_b, order_id=None, sequence_id=self.seq_a.id, customer_id=None, user=self.user_b)

    def test_cancel_invoice_rejects_wrong_tenant(self):
        inv_a = self._issue_a_invoice()
        from fiscal.services import cancel_invoice, FiscalServiceError
        with self.assertRaises(FiscalServiceError):
            cancel_invoice(tenant=self.tenant_b, invoice_id=inv_a.id, user=self.user_b)

    def test_submit_rejects_wrong_device(self):
        inv_b = self._issue_b_invoice()
        from fiscal.services import submit_to_device, FiscalServiceError
        with self.assertRaises(FiscalServiceError):
            submit_to_device(tenant=self.tenant_b, invoice_id=inv_b.id, device_id=self.device_a.id, user=self.user_b)
