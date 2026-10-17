from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from loyalty.models import LoyaltyTransaction
from pos.models import Customer, Order
from rbac.models import Module, Permission, Role, UserRole
from saas.models import Tenant, TenantMembership
from system.models import CustomerGroup


class CustomerApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="customer-owner", password="test-password")
        self.other_owner = user_model.objects.create_user(username="customer-other-owner", password="test-password")
        self.tenant = Tenant.objects.create(name="Customer Tenant", slug="customer-tenant", owner=self.owner, is_active=True)
        self.other_tenant = Tenant.objects.create(name="Customer Other Tenant", slug="customer-other-tenant", owner=self.other_owner, is_active=True)
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(user=self.other_owner, tenant=self.other_tenant, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        self.group = CustomerGroup.objects.create(tenant=self.tenant, name="Wholesale")
        self.customer = Customer.objects.create(tenant=self.tenant, name="Alice Customer", email="alice@example.test", phone="1001", group=self.group)
        self.foreign_customer = Customer.objects.create(tenant=self.other_tenant, name="Bob Foreign", email="bob@example.test", phone="2001")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_customer_crud_search_summary_and_duplicate_detection(self):
        created = self.client.post("/api/customers/", {
            "name": "Ada Lovelace", "email": "ada@example.test", "phone": "1100", "group": self.group.id,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(created.data["customer_code"].startswith(f"CU-{self.tenant.id}-"))
        customer_id = created.data["id"]

        duplicate = self.client.post("/api/customers/", {"name": "Ada Duplicate", "email": "ada@example.test", "phone": "1101"}, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("email", str(duplicate.data))

        listed = self.client.get("/api/customers/?search=ada&page_size=10")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["id"], customer_id)

        updated = self.client.patch(f"/api/customers/{customer_id}/", {"phone": "1101"}, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["phone"], "1101")

        summary = self.client.get(f"/api/customers/{customer_id}/summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data["total_orders"], 0)

    def test_customer_foreign_object_access_is_rejected_for_read_update_delete_and_children(self):
        for method, url, payload in [
            (self.client.get, f"/api/customers/{self.foreign_customer.id}/", None),
            (self.client.patch, f"/api/customers/{self.foreign_customer.id}/", {"name": "Attempt"}),
            (self.client.delete, f"/api/customers/{self.foreign_customer.id}/", None),
            (self.client.get, f"/api/customers/{self.foreign_customer.id}/addresses/", None),
            (self.client.get, f"/api/customers/{self.foreign_customer.id}/credit-limit/", None),
            (self.client.get, f"/api/customers/{self.foreign_customer.id}/documents/", None),
            (self.client.get, f"/api/customers/{self.foreign_customer.id}/notes/", None),
            (self.client.get, f"/api/customers/{self.foreign_customer.id}/loyalty/", None),
            (self.client.get, f"/api/customers/{self.foreign_customer.id}/activity/", None),
        ]:
            response = method(url, payload, format="json") if payload is not None else method(url)
            self.assertEqual(response.status_code, 404, f"{url} unexpectedly exposed another tenant")

    def test_addresses_notes_documents_credit_loyalty_and_order_history_are_customer_scoped(self):
        address = self.client.post(f"/api/customers/{self.customer.id}/addresses/", {
            "kind": "shipping", "label": "Office", "line1": "1 Ledgerline Way", "city": "Karachi", "is_default": True,
        }, format="json")
        self.assertEqual(address.status_code, 201, address.data)
        address_list = self.client.get(f"/api/customers/{self.customer.id}/addresses/")
        self.assertEqual(address_list.data["count"], 1)

        note = self.client.post(f"/api/customers/{self.customer.id}/notes/", {"body": "Call before delivery", "pinned": True}, format="json")
        self.assertEqual(note.status_code, 201, note.data)
        self.assertEqual(note.data["created_by_name"], self.owner.username)
        note_update = self.client.patch(f"/api/customer-notes/{note.data['id']}/", {"body": "Call in the morning"}, format="json")
        self.assertEqual(note_update.status_code, 200, note_update.data)

        document = self.client.post(
            f"/api/customers/{self.customer.id}/documents/",
            {"kind": "ID", "file": SimpleUploadedFile("identity.txt", b"verified customer"), "name": "Identity"},
            format="multipart",
        )
        self.assertEqual(document.status_code, 201, document.data)
        self.assertIn("download_url", document.data)

        credit = self.client.post(f"/api/customers/{self.customer.id}/credit-limit/", {"limit": "250.00", "terms_days": 30}, format="json")
        self.assertEqual(credit.status_code, 200, credit.data)
        self.assertEqual(credit.data["available"], "250.00")

        LoyaltyTransaction.objects.create(tenant=self.tenant, customer=self.customer, type="earn", points=25, reference="POS-1")
        loyalty = self.client.get(f"/api/customers/{self.customer.id}/loyalty/")
        self.assertEqual(loyalty.status_code, 200)
        self.assertEqual(loyalty.data["results"][0]["points"], 25)

        Order.objects.create(tenant=self.tenant, customer=self.customer, payment_method="cash", total=Decimal("90"), status="paid")
        order_history = self.client.get(f"/api/pos/orders/?customer_id={self.customer.id}")
        self.assertEqual(order_history.status_code, 200)
        self.assertEqual(order_history.data["count"], 1)
        self.assertEqual(order_history.data["results"][0]["customer_id"], self.customer.id)

    def test_customer_groups_are_tenant_scoped_and_customer_with_history_archives_instead_of_deleting(self):
        created_group = self.client.post("/api/customer-groups/", {"name": "VIP", "discount_percent": "5"}, format="json")
        self.assertEqual(created_group.status_code, 201, created_group.data)
        CustomerGroup.objects.create(tenant=self.other_tenant, name="Foreign Group")
        groups = self.client.get("/api/customer-groups/")
        self.assertEqual(groups.status_code, 200)
        self.assertEqual({row["name"] for row in groups.data}, {"Wholesale", "VIP"})

        Order.objects.create(tenant=self.tenant, customer=self.customer, payment_method="cash", total=Decimal("10"), status="paid")
        blocked_delete = self.client.delete(f"/api/customers/{self.customer.id}/")
        self.assertEqual(blocked_delete.status_code, 400)
        archived = self.client.post(f"/api/customers/{self.customer.id}/archive/")
        self.assertEqual(archived.status_code, 200, archived.data)
        self.assertFalse(archived.data["is_active"])

    def test_restricted_active_tenant_member_can_view_but_cannot_mutate_customer_data(self):
        user_model = get_user_model()
        restricted = user_model.objects.create_user(username="customer-viewer", password="test-password")
        TenantMembership.objects.create(user=restricted, tenant=self.tenant, role=TenantMembership.ROLE_STAFF, is_active_in_tenant=True)
        module, _ = Module.objects.get_or_create(key="customers", defaults={"label": "Customers"})
        view_permission, _ = Permission.objects.get_or_create(module=module, action="view")
        viewer_role = Role.objects.create(key="customer-viewer", label="Customer viewer")
        viewer_role.permissions.add(view_permission)
        UserRole.objects.create(user=restricted, role=viewer_role)
        client = APIClient()
        client.force_authenticate(restricted)

        self.assertEqual(client.get("/api/customers/").status_code, 200)
        self.assertEqual(client.get(f"/api/customers/{self.customer.id}/summary/").status_code, 200)
        self.assertEqual(client.get(f"/api/customers/{self.customer.id}/activity/").status_code, 200)
        self.assertEqual(client.get(f"/api/customers/{self.customer.id}/credit-limit/").status_code, 200)
        self.assertEqual(client.post("/api/customers/", {"name": "Blocked"}, format="json").status_code, 403)
        self.assertEqual(client.patch(f"/api/customers/{self.customer.id}/", {"name": "Blocked"}, format="json").status_code, 403)
        self.assertEqual(client.post(f"/api/customers/{self.customer.id}/credit-limit/", {"limit": "100"}, format="json").status_code, 403)
        self.assertEqual(client.post(f"/api/customers/{self.customer.id}/archive/", {}, format="json").status_code, 403)
