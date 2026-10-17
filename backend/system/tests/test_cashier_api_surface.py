"""Phase 5: hiding navigation is not security — verify the backend refuses a
cashier everything the hidden screens (API explorer, FBR / Fiscal, admin) use.

The cashier holds exactly the Cashier template permissions (pos.view,
pos.create, customers.view, customers.create, products.view) as a "staff"
member of the tenant. The API explorer can send any request, so the whole
parameterless GET surface from the frontend API map is swept as well.
"""
import json
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from pos.models import Product
from rbac.models import Permission, Role, UserRole
from saas.models import Tenant, TenantMembership

OPERATIONS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "js" / "api-map" / "operations.json"
CASHIER_PERMISSIONS = ["pos.view", "pos.create", "customers.view", "customers.create", "products.view"]

# Screens hidden from cashiers; every one must be refused by the backend.
MUST_DENY_GET = [
    "/api/fbr/configurations/", "/api/fbr/product-profiles/", "/api/fbr/submissions/", "/api/fbr/eligibility/",
    "/api/fbr/ims/health/", "/api/fbr/buyer-profiles/", "/api/fbr/reference/hs-codes/",
    "/api/fiscal/invoices/", "/api/fiscal/sequences/", "/api/fiscal/devices/", "/api/fiscal/submissions/",
    "/api/accounting/journal/", "/api/accounting/trial-balance/", "/api/hr/employees/", "/api/hr/payroll/",
    "/api/audit/events/", "/api/backups/", "/api/backups/export-database/", "/api/api-keys/", "/api/webhooks/",
    "/api/integrations/", "/api/users/", "/api/rbac/roles/", "/api/rbac/user-roles/", "/api/rbac/overrides/",
    "/api/rbac/governance/members/", "/api/security/login-attempts/", "/api/company/",
    "/api/settings/company/", "/api/settings/security/", "/api/settings/backup/",
    "/api/catalog/products/export/csv/", "/api/inventory/adjustments/", "/api/pos/refunds/order/1/",
]


@override_settings(ROOT_URLCONF="backend.urls")
class CashierApiSurfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(username="surface-owner", password="x-pass-123")
        cls.cashier = user_model.objects.create_user(username="surface-cashier", password="x-pass-123")
        cls.tenant = Tenant.objects.create(name="Surface", slug="surface", owner=cls.owner, status="active")
        TenantMembership.objects.create(tenant=cls.tenant, user=cls.owner, role="owner", is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=cls.tenant, user=cls.cashier, role="staff", is_active_in_tenant=True)
        role = Role.objects.create(key="surface-cashier", label="Cashier", tenant=cls.tenant)
        for key in CASHIER_PERMISSIONS:
            module, action = key.split(".")
            role.permissions.add(*Permission.objects.filter(module__key=module, action=action, scope="tenant"))
        UserRole.objects.create(user=cls.cashier, role=role, tenant=cls.tenant)
        Product.objects.create(tenant=cls.tenant, name="Tea", sku="TEA-1", sales_price=Decimal("100"), cost_price=Decimal("60"))

    def setUp(self):
        from auth_app.models import AuthToken

        # A real token, exactly like the frontend (force_authenticate leaves
        # request.auth empty, which /api/auth/me/ echoes back).
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + AuthToken.objects.create(user=self.cashier).key)

    def get(self, path):
        cache.clear()  # keep the per-user throttle out of a 250-request sweep (test DB only)
        return self.client.get(path)

    def test_hidden_screens_are_refused_by_the_backend(self):
        allowed = {path: self.get(path).status_code for path in MUST_DENY_GET}
        leaks = {path: code for path, code in allowed.items() if code != 403}
        self.assertEqual(leaks, {}, "cashier reached endpoints of hidden screens")

    def test_cashier_cannot_write_admin_or_fiscal_data(self):
        attempts = [
            ("/api/fbr/configurations/", {"environment": "sandbox"}),
            ("/api/fiscal/sequences/", {"name": "X", "prefix": "X"}),
            ("/api/saas/tenants/members/", {"username": "surface-cashier", "role": "admin"}),
            ("/api/fbr/submissions/1/retry/", {}),
            ("/api/fbr/submissions/1/reconcile/", {"outcome": "not_fiscalized"}),
            # Refunds need pos.refund, which the cashier template does not grant.
            ("/api/pos/refunds/", {"order_id": 1, "items": [{"order_item_id": 1, "quantity": "1"}]}),
        ]
        for path, body in attempts:
            cache.clear()
            response = self.client.post(path, body, format="json")
            # Permission is checked before any object lookup: always 403.
            self.assertEqual(response.status_code, 403, f"{path} -> {response.status_code}")

    def test_cashier_keeps_the_till(self):
        self.assertEqual(self.get("/api/products/?search=tea").status_code, 200)
        self.assertEqual(self.get("/api/pos/customers/?search=a").status_code, 200)
        self.assertEqual(self.get("/api/auth/me/").status_code, 200)

    def test_cashier_can_add_and_find_a_customer_from_the_till(self):
        cache.clear()
        # Exactly the POS "Add customer" payload (frontend/src/js/pos.js createCustomer).
        created = self.client.post("/api/customers/", {"name": "  Ayesha Khan ", "phone": "0300-1112223", "email": ""}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["name"], "Ayesha Khan")
        cache.clear()
        duplicate = self.client.post("/api/customers/", {"name": "Someone", "phone": "0300-1112223", "email": ""}, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("phone", duplicate.data["error"]["fields"])
        cache.clear()
        nameless = self.client.post("/api/customers/", {"name": "  ", "phone": "", "email": ""}, format="json")
        self.assertEqual(nameless.status_code, 400)
        for name in ("Walk-in A", "Walk-in B"):  # blank contact details never collide
            cache.clear()
            self.assertEqual(self.client.post("/api/customers/", {"name": name, "phone": "", "email": ""}, format="json").status_code, 201)
        found = self.get("/api/pos/customers/?search=1112223").data
        self.assertEqual([row["id"] for row in found], [created.data["id"]])

    def test_cashier_can_print_a_receipt_without_company_settings_access(self):
        from pos.models import Company, Order

        Company.objects.create(tenant=self.tenant, name="Surface Mart", address="1 Main Rd", phone="021-1", currency="PKR")
        other_owner = get_user_model().objects.create_user(username="surface-other", password="x-pass-123")
        other = Tenant.objects.create(name="Other", slug="surface-other", owner=other_owner, status="active")
        Company.objects.create(tenant=other, name="Other Mart", address="Elsewhere")
        own = Order.objects.create(tenant=self.tenant, status="paid", subtotal=Decimal("100"), total=Decimal("100"))
        foreign = Order.objects.create(tenant=other, status="paid", subtotal=Decimal("100"), total=Decimal("100"))

        self.assertEqual(self.get("/api/company/").status_code, 403)  # settings stay admin-only
        receipt = self.get(f"/api/pos/orders/{own.id}/receipt/")
        self.assertEqual(receipt.status_code, 200)
        business = receipt.data["business"]
        self.assertEqual((business["name"], business["address"], business["currency"]), ("Surface Mart", "1 Main Rd", "PKR"))
        self.assertEqual(self.get(f"/api/pos/orders/{foreign.id}/receipt/").status_code, 404)

    def test_full_get_surface_has_no_server_errors_or_data_dump(self):
        operations = json.loads(OPERATIONS.read_text())
        if isinstance(operations, dict):
            operations = operations.get("operations", operations)
        if isinstance(operations, dict):
            operations = list(operations.values())
        paths = sorted({op["path"] for op in operations if op.get("method") == "GET" and "{" not in op["path"]})
        self.assertGreater(len(paths), 200)
        results = {path: self.get(path).status_code for path in paths}
        errors = {path: code for path, code in results.items() if code >= 500 or code == 401}
        self.assertEqual(errors, {}, "unexpected 5xx/401 for an authenticated cashier")
        self.assertNotEqual(results.get("/api/backups/export-database/"), 200)
