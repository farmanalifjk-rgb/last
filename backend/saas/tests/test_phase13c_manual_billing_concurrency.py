import threading
from datetime import date
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection, connections, transaction
from django.test import TransactionTestCase

from rbac.models import Module, Permission, Role, UserRole
from saas.manual_billing_services import create_subscription_request, submit_manual_payment, verify_manual_payment
from saas.models import ManualPaymentMethod, ManualSubscriptionPayment, Subscription, SubscriptionPlan, SubscriptionRequest, Tenant, TenantMembership


User = get_user_model()


@skipUnless(connection.vendor == "postgresql", "Manual billing locking tests require PostgreSQL.")
class PostgreSQLManualBillingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user(username="phase13c-pg-owner", password="Pass123!")
        self.verifier = User.objects.create_user(username="phase13c-pg-verifier", password="Pass123!")
        self.plan = SubscriptionPlan.objects.create(name="Phase13C PostgreSQL", slug="phase13c-pg-plan", price=Decimal("89.00"), currency="USD")
        self.tenant = Tenant.objects.create(name="Phase 13C PostgreSQL Tenant", slug="phase13c-pg-tenant", owner=self.owner, status=Tenant.STATUS_TRIAL)
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.tenant, user=self.verifier, role=TenantMembership.ROLE_STAFF, is_active_in_tenant=True)
        module, _ = Module.objects.get_or_create(key="billing", defaults={"label": "SaaS billing"})
        permission, _ = Permission.objects.get_or_create(module=module, action="verify", scope=Permission.SCOPE_PLATFORM)
        role, _ = Role.objects.get_or_create(key="phase13c-pg-verifier", defaults={"label": "Phase 13C PostgreSQL verifier", "scope": Permission.SCOPE_PLATFORM})
        role.permissions.add(permission)
        UserRole.objects.get_or_create(user=self.verifier, role=role)
        Subscription.objects.create(tenant=self.tenant, plan=self.plan, status=Subscription.STATUS_TRIALING)
        self.cash, _ = ManualPaymentMethod.objects.get_or_create(code="cash", defaults={"label": "Cash", "is_active": True, "sort_order": 10})

    def _submitted_payment(self):
        billing_request, _invoice = create_subscription_request(tenant=self.tenant, plan_id=self.plan.id, actor=self.owner)
        return submit_manual_payment(
            tenant=self.tenant,
            subscription_request_id=billing_request.id,
            actor=self.owner,
            payment_method_id=self.cash.id,
            paid_amount="89.00",
            paid_currency="USD",
            payment_date=date.today(),
            payment_reference="",
        )

    def _parallel(self, callback):
        # Commit the current transaction so worker threads (which get fresh
        # connections via connections.close_all()) can see setUp + test data.
        # TransactionTestCase cleans up by flushing tables, not by rollback.
        connection.cursor().execute("COMMIT")

        barrier = threading.Barrier(2)
        results = []
        result_lock = threading.Lock()

        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                callback(index)
                result = "ok"
            except Exception as exc:
                result = type(exc).__name__
            finally:
                connections.close_all()
            with result_lock:
                results.append(result)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=25)
        self.assertEqual(len(results), 2, results)
        return results

    def test_two_platform_verifiers_cannot_activate_one_manual_payment_twice(self):
        payment = self._submitted_payment()

        def verify(_index):
            verify_manual_payment(payment_id=payment.id, actor=self.verifier)

        results = self._parallel(verify)
        self.assertEqual(results.count("ok"), 1, results)
        payment.refresh_from_db()
        request = SubscriptionRequest.objects.get(pk=payment.subscription_request_id)
        subscription = Subscription.objects.get(tenant=self.tenant)
        self.assertEqual(payment.status, ManualSubscriptionPayment.STATUS_VERIFIED)
        self.assertEqual(request.status, SubscriptionRequest.STATUS_ACTIVATED)
        self.assertEqual(subscription.status, Subscription.STATUS_ACTIVE)
        self.assertEqual(ManualSubscriptionPayment.objects.filter(subscription_request=request).count(), 1)

    def test_two_workers_cannot_create_two_open_subscription_requests_for_one_tenant(self):
        def create_request(_index):
            tenant = Tenant.objects.get(pk=self.tenant.pk)
            create_subscription_request(tenant=tenant, plan_id=self.plan.id, actor=self.owner)

        results = self._parallel(create_request)
        self.assertEqual(results.count("ok"), 1, results)
        self.assertEqual(
            SubscriptionRequest.objects.filter(
                tenant=self.tenant,
                status=SubscriptionRequest.STATUS_AWAITING_PAYMENT,
            ).count(),
            1,
        )

    def test_two_workers_cannot_submit_two_manual_payments_for_one_request(self):
        billing_request, _invoice = create_subscription_request(tenant=self.tenant, plan_id=self.plan.id, actor=self.owner)

        def submit(_index):
            submit_manual_payment(
                tenant=Tenant.objects.get(pk=self.tenant.pk),
                subscription_request_id=billing_request.id,
                actor=self.owner,
                payment_method_id=self.cash.id,
                paid_amount="89.00",
                paid_currency="USD",
                payment_date=date.today(),
                payment_reference="",
            )

        results = self._parallel(submit)
        self.assertEqual(results.count("ok"), 1, results)
        self.assertEqual(ManualSubscriptionPayment.objects.filter(subscription_request_id=billing_request.id).count(), 1)
