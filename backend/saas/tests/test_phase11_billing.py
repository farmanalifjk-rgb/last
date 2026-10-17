from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from saas.models import Invoice, PlanEntitlement, SubscriptionPlan, Tenant, TenantMembership


class Phase11BillingApiTests(TestCase):
    def make_plan(self, slug="starter"):
        fields = {"name": "Starter", "slug": slug}
        for field in SubscriptionPlan._meta.fields:
            if field.name in fields or field.auto_created or field.primary_key or field.has_default() or field.null:
                continue
            kind = field.get_internal_type()
            if kind in {"CharField", "TextField"}: fields[field.name] = ""
            elif kind == "BooleanField": fields[field.name] = True
            elif kind in {"DecimalField", "FloatField"}: fields[field.name] = Decimal("0")
            elif kind in {"IntegerField", "PositiveIntegerField", "PositiveSmallIntegerField"}: fields[field.name] = 0
        return SubscriptionPlan.objects.create(**fields)

    def make_invoice(self, tenant, number):
        fields = {"tenant": tenant, "number": number}
        for field in Invoice._meta.fields:
            if field.name in fields or field.auto_created or field.primary_key or field.has_default() or field.null:
                continue
            kind = field.get_internal_type()
            if kind in {"CharField", "TextField"}: fields[field.name] = Invoice.STATUS_OPEN if field.name == "status" else "USD"
            elif kind in {"DecimalField", "FloatField"}: fields[field.name] = Decimal("10.00")
            elif kind in {"IntegerField", "PositiveIntegerField", "PositiveSmallIntegerField"}: fields[field.name] = 1
        return Invoice.objects.create(**fields)

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="phase11-owner", password="x")
        self.other = User.objects.create_user(username="phase11-other", password="x")
        self.tenant = Tenant.objects.create(name="Billing A", slug="phase11-billing-a", owner=self.owner, status=Tenant.STATUS_ACTIVE)
        self.other_tenant = Tenant.objects.create(name="Billing B", slug="phase11-billing-b", owner=self.other, status=Tenant.STATUS_ACTIVE)
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.other_tenant, user=self.other, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        self.plan = self.make_plan()
        self.entitlement = PlanEntitlement.objects.create(plan=self.plan, code="inventory.module", label="Inventory module", enabled=True, limit_value=10)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_overview_is_active_tenant_scoped_and_entitlements_are_explicit(self):
        from saas.models import Subscription
        Subscription.objects.create(tenant=self.tenant, plan=self.plan, status=Subscription.STATUS_ACTIVE)
        response = self.client.get("/api/saas/billing/overview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tenant"]["id"], self.tenant.id)
        self.assertEqual(response.data["plan"]["features"][0]["code"], "inventory.module")
        self.assertNotIn("stripe_secret", response.data)

    def test_invoice_list_cannot_cross_tenant(self):
        self.make_invoice(self.other_tenant, "B-1")
        response = self.client.get("/api/saas/billing/invoices/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_provider_status_never_exposes_secret_and_reports_configuration_required(self):
        response = self.client.get("/api/saas/billing/provider-status/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["actions_enabled"])
        self.assertNotIn("STRIPE_SECRET_KEY", response.data)

    def test_plans_are_read_only_public_commercial_metadata_under_billing_permission(self):
        response = self.client.get("/api/saas/billing/plans/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["slug"], "starter")
        self.assertIn("price", response.data["results"][0])
        self.assertIn("currency", response.data["results"][0])



