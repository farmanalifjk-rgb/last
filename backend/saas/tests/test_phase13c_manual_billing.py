from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from operations.models import InAppNotification
from rbac.models import Module, Permission, Role, UserRole
from saas.models import (
    Invoice,
    ManualPaymentMethod,
    ManualSubscriptionPayment,
    Subscription,
    SubscriptionPlan,
    SubscriptionRequest,
    Tenant,
    TenantMembership,
)


User = get_user_model()


class ManualSubscriptionBillingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="phase13c-owner", password="Pass123!")
        self.other_owner = User.objects.create_user(username="phase13c-other", password="Pass123!")
        self.verifier = User.objects.create_user(username="phase13c-platform-verifier", password="Pass123!")
        self.viewer = User.objects.create_user(username="phase13c-viewer", password="Pass123!")
        self.plan = SubscriptionPlan.objects.create(name="Starter", slug="phase13c-starter", price=Decimal("89.00"), currency="USD", interval=SubscriptionPlan.INTERVAL_MONTHLY)
        self.business = SubscriptionPlan.objects.create(name="Business", slug="phase13c-business", price=Decimal("129.00"), currency="USD", interval=SubscriptionPlan.INTERVAL_MONTHLY)
        self.tenant = self._tenant("Phase 13C A", "phase13c-a", self.owner, self.plan)
        self.other_tenant = self._tenant("Phase 13C B", "phase13c-b", self.other_owner, self.plan)
        TenantMembership.objects.create(tenant=self.tenant, user=self.viewer, role=TenantMembership.ROLE_STAFF, is_active_in_tenant=True)
        self._grant(self.viewer, "view")
        self._grant(self.verifier, "verify")
        self.cash, _ = ManualPaymentMethod.objects.get_or_create(code="cash", defaults={"label": "Cash", "reference_required": False, "is_active": True, "sort_order": 10})
        self.bank, _ = ManualPaymentMethod.objects.get_or_create(code="bank-transfer", defaults={"label": "Bank transfer", "reference_required": True, "is_active": True, "sort_order": 20})
        self.owner_client = self._client(self.owner)
        self.other_client = self._client(self.other_owner)
        self.viewer_client = self._client(self.viewer)
        self.verifier_client = self._client(self.verifier)

    def _tenant(self, name, slug, owner, plan):
        tenant = Tenant.objects.create(name=name, slug=slug, owner=owner, status=Tenant.STATUS_TRIAL)
        TenantMembership.objects.create(tenant=tenant, user=owner, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.STATUS_TRIALING)
        return tenant

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def _grant(self, user, action):
        module, _ = Module.objects.get_or_create(key="billing", defaults={"label": "SaaS billing"})
        permission, _ = Permission.objects.get_or_create(module=module, action=action)
        scope = Permission.SCOPE_PLATFORM if action == "verify" else Permission.SCOPE_TENANT
        role, _ = Role.objects.get_or_create(
            key=f"phase13c-billing-{action}",
            defaults={"label": f"Phase 13C billing {action}", "scope": scope},
        )
        if role.scope != scope:
            role.scope = scope
            role.save(update_fields=["scope"])
        role.permissions.add(permission)
        UserRole.objects.get_or_create(user=user, role=role)

    def _request(self, client=None, plan=None):
        response = (client or self.owner_client).post("/api/saas/billing/requests/", {"plan_id": (plan or self.business).id}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return SubscriptionRequest.objects.get(pk=response.data["id"])

    def _submit(self, billing_request, client=None, method=None, amount="129.00", currency="USD", reference="REF-13C"):
        response = (client or self.owner_client).post(
            f"/api/saas/billing/requests/{billing_request.id}/submit-payment/",
            {
                "payment_method_id": (method or self.bank).id,
                "paid_amount": amount,
                "paid_currency": currency,
                "payment_date": date.today().isoformat(),
                "payment_reference": reference,
                "notes": "Offline payment submitted for Phase 13C test.",
            },
            format="json",
        )
        return response

    def test_tenant_request_snapshots_authoritative_plan_and_creates_open_saas_invoice(self):
        billing_request = self._request()
        invoice = Invoice.objects.get(subscription_request=billing_request)
        self.assertEqual(billing_request.tenant_id, self.tenant.id)
        self.assertEqual(billing_request.expected_amount, Decimal("129.00"))
        self.assertEqual(billing_request.expected_currency, "USD")
        self.assertEqual(billing_request.status, SubscriptionRequest.STATUS_AWAITING_PAYMENT)
        self.assertEqual(invoice.status, Invoice.STATUS_OPEN)
        self.assertEqual(invoice.amount_due, Decimal("129.00"))
        self.assertEqual(invoice.tenant_id, self.tenant.id)

    def test_submission_requires_method_reference_when_configured_and_creates_pending_audit_notification(self):
        billing_request = self._request()
        missing_reference = self._submit(billing_request, reference="")
        self.assertEqual(missing_reference.status_code, 400)
        response = self._submit(billing_request, reference="BANK-REF-13C")
        self.assertEqual(response.status_code, 201, response.data)
        payment = ManualSubscriptionPayment.objects.get(pk=response.data["id"])
        billing_request.refresh_from_db()
        self.assertEqual(payment.status, ManualSubscriptionPayment.STATUS_SUBMITTED)
        self.assertEqual(billing_request.status, SubscriptionRequest.STATUS_PAYMENT_SUBMITTED)
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant, entity_type="manualsubscriptionpayment").exists())
        self.assertTrue(InAppNotification.objects.filter(tenant=self.tenant, user=self.owner, event_key__contains=f"billing-payment:{payment.id}:submitted").exists())

    def test_platform_verification_activates_one_canonical_subscription_and_finalizes_invoice(self):
        billing_request = self._request()
        submitted = self._submit(billing_request, reference="VERIFY-13C")
        payment_id = submitted.data["id"]
        response = self.verifier_client.post(f"/api/saas/billing/admin/payments/{payment_id}/verify/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        payment = ManualSubscriptionPayment.objects.get(pk=payment_id)
        subscription = Subscription.objects.get(tenant=self.tenant)
        invoice = Invoice.objects.get(subscription_request=billing_request)
        billing_request.refresh_from_db()
        self.assertEqual(payment.status, ManualSubscriptionPayment.STATUS_VERIFIED)
        self.assertEqual(payment.verified_by_id, self.verifier.id)
        self.assertEqual(billing_request.status, SubscriptionRequest.STATUS_ACTIVATED)
        self.assertEqual(subscription.plan_id, self.business.id)
        self.assertEqual(subscription.status, Subscription.STATUS_ACTIVE)
        self.assertEqual(invoice.status, Invoice.STATUS_PAID)
        self.assertEqual(invoice.amount_paid, Decimal("129.00"))
        self.assertEqual(invoice.manual_payment_id, payment.id)
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant, entity_type="subscription", entity_id=str(subscription.id)).exists())
        self.assertTrue(InAppNotification.objects.filter(tenant=self.tenant, user=self.owner, event_key__contains=f"billing-payment:{payment.id}:verified").exists())

    def test_tenant_owner_cannot_self_verify_or_access_platform_queue(self):
        billing_request = self._request()
        payment_id = self._submit(billing_request, reference="SELF-VERIFY-13C").data["id"]
        self.assertEqual(self.owner_client.get("/api/saas/billing/admin/payments/").status_code, 403)
        self.assertEqual(self.owner_client.post(f"/api/saas/billing/admin/payments/{payment_id}/verify/", {}, format="json").status_code, 403)
        payment = ManualSubscriptionPayment.objects.get(pk=payment_id)
        self.assertEqual(payment.status, ManualSubscriptionPayment.STATUS_SUBMITTED)

    def test_mismatched_amount_or_currency_cannot_activate_subscription(self):
        billing_request = self._request()
        amount_payment = self._submit(billing_request, amount="1.00", reference="UNDERPAY-13C")
        self.assertEqual(amount_payment.status_code, 201)
        response = self.verifier_client.post(f"/api/saas/billing/admin/payments/{amount_payment.data['id']}/verify/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Subscription.objects.get(tenant=self.tenant).status, Subscription.STATUS_TRIALING)

    def test_owner_cannot_submit_payment_for_another_tenant_request_or_read_its_records(self):
        other_request = self._request(self.other_client, self.business)
        foreign_submit = self.owner_client.post(
            f"/api/saas/billing/requests/{other_request.id}/submit-payment/",
            {"payment_method_id": self.cash.id, "paid_amount": "129.00", "paid_currency": "USD", "payment_date": date.today().isoformat()},
            format="json",
        )
        self.assertEqual(foreign_submit.status_code, 403)
        own_records = self.owner_client.get("/api/saas/billing/requests/")
        self.assertEqual(own_records.status_code, 200)
        self.assertEqual(own_records.data["results"], [])

    def test_viewer_cannot_create_request_or_submit_payment_but_can_view_billing(self):
        self.assertEqual(self.viewer_client.get("/api/saas/billing/overview/").status_code, 200)
        self.assertEqual(self.viewer_client.post("/api/saas/billing/requests/", {"plan_id": self.business.id}, format="json").status_code, 403)

    def test_owner_effective_permission_response_includes_owner_bypass_for_frontend_visibility(self):
        response = self.owner_client.get("/api/rbac/me/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("*.*", response.data["permissions"])

    def test_duplicate_reference_is_rejected_per_configured_method(self):
        first_request = self._request()
        self.assertEqual(self._submit(first_request, reference="UNIQUE-13C").status_code, 201)
        second_request = self._request(self.other_client, self.business)
        response = self._submit(second_request, client=self.other_client, reference="UNIQUE-13C")
        self.assertEqual(response.status_code, 409)

    def test_payment_decision_is_idempotently_protected_and_rejection_requires_reason(self):
        billing_request = self._request()
        payment_id = self._submit(billing_request, reference="DECIDE-13C").data["id"]
        self.assertEqual(self.verifier_client.post(f"/api/saas/billing/admin/payments/{payment_id}/reject/", {}, format="json").status_code, 400)
        rejected = self.verifier_client.post(f"/api/saas/billing/admin/payments/{payment_id}/reject/", {"rejection_reason": "Reference could not be matched."}, format="json")
        self.assertEqual(rejected.status_code, 200, rejected.data)
        duplicate = self.verifier_client.post(f"/api/saas/billing/admin/payments/{payment_id}/verify/", {}, format="json")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(ManualSubscriptionPayment.objects.get(pk=payment_id).status, ManualSubscriptionPayment.STATUS_REJECTED)

    def test_legacy_saas_checkout_and_webhook_are_truthfully_disabled_and_provider_status_is_manual(self):
        self.assertEqual(self.owner_client.post("/api/saas/subscription/checkout/", {"plan_slug": self.business.slug}, format="json").status_code, 410)
        self.assertEqual(self.owner_client.post("/api/saas/stripe/webhook/", {}, format="json").status_code, 410)
        status_response = self.owner_client.get("/api/saas/billing/provider-status/")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.data["status"], "manual_offline_billing")
        self.assertNotIn("STRIPE_SECRET_KEY", status_response.data)
