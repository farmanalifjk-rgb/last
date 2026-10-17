"""Regression tests for backend defects found during the phase-2 frontend integration.

Each of these was reproduced against the running API before the fix:

* GET /api/notifications/rules/  -> 500  FieldError: select_related('channel') on a CharField
* GET /api/audit/feed/           -> 500  FieldError: select_related('actor'); ActivityFeed has no FK
* PATCH /api/notifications/rules/<id>/ accepted a client-supplied ``tenant`` (cross-tenant move)
* GET /api/i18n/format/          -> 500  Currency.DoesNotExist / InvalidOperation on bad input
* Global Currency/Language/TranslationKey were writable by any authenticated tenant user
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import ActivityFeed
from i18n_app.models import Currency
from notifications.models import AlertRule
from saas.models import Tenant, TenantMembership
from saas.tenant_context import set_current_tenant

User = get_user_model()


class _TwoTenants(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="p2-owner-a", password="StrongPass123!")
        self.other_owner = User.objects.create_user(username="p2-owner-b", password="StrongPass123!")
        self.tenant = Tenant.objects.create(name="P2 Tenant A", slug="p2-a", owner=self.owner, status="active")
        self.other = Tenant.objects.create(name="P2 Tenant B", slug="p2-b", owner=self.other_owner, status="active")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner", is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=self.other, user=self.other_owner, role="owner", is_active_in_tenant=True)
        set_current_tenant(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)


class AlertRuleEndpointTests(_TwoTenants):
    def test_rule_list_and_detail_no_longer_500_and_are_tenant_scoped(self):
        mine = AlertRule.objects.create(tenant=self.tenant, kind=AlertRule.KIND_LOW_STOCK)
        theirs = AlertRule.objects.create(tenant=self.other, kind=AlertRule.KIND_LOW_STOCK)

        response = self.client.get("/api/notifications/rules/")
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual({row["id"] for row in rows}, {mine.id})

        self.assertEqual(self.client.get(f"/api/notifications/rules/{mine.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/notifications/rules/{theirs.id}/").status_code, 404)

    def test_patch_cannot_move_a_rule_into_another_tenant(self):
        rule = AlertRule.objects.create(tenant=self.tenant, kind=AlertRule.KIND_EXPIRY)
        response = self.client.patch(
            f"/api/notifications/rules/{rule.id}/", {"tenant": self.other.id, "expiry_days": 9}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        rule.refresh_from_db()
        self.assertEqual(rule.tenant_id, self.tenant.id)
        self.assertEqual(rule.expiry_days, 9)

    def test_create_ignores_client_tenant(self):
        response = self.client.post(
            "/api/notifications/rules/", {"kind": AlertRule.KIND_REORDER, "tenant": self.other.id}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(AlertRule.objects.get(id=response.data["id"]).tenant_id, self.tenant.id)


class ActivityFeedEndpointTests(_TwoTenants):
    def test_feed_lists_only_own_tenant_and_actor_filter_works(self):
        ActivityFeed.objects.create(tenant=self.tenant, actor_name="alice", summary="mine")
        ActivityFeed.objects.create(tenant=self.tenant, actor_name="bob", summary="mine too")
        ActivityFeed.objects.create(tenant=self.other, actor_name="alice", summary="theirs")

        response = self.client.get("/api/audit/feed/")
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(sorted(row["summary"] for row in rows), ["mine", "mine too"])

        response = self.client.get("/api/audit/feed/", {"actor": "ali"})
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual([row["summary"] for row in rows], ["mine"])


class I18nEndpointTests(_TwoTenants):
    def setUp(self):
        super().setUp()
        self.pkr = Currency.objects.create(code="PKR", name="Pakistani Rupee", symbol="Rs", decimals=2,
                                           exchange_rate=Decimal("280"))

    def test_format_validates_input_instead_of_500(self):
        ok = self.client.get("/api/i18n/format/", {"amount": "1234.5", "currency": "PKR"})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.data["formatted"], "Rs1,234.50")
        self.assertEqual(self.client.get("/api/i18n/format/", {"currency": "XXX"}).status_code, 400)
        self.assertEqual(self.client.get("/api/i18n/format/", {"amount": "abc", "currency": "PKR"}).status_code, 400)
        self.assertEqual(self.client.get("/api/i18n/format/", {"amount": "NaN", "currency": "PKR"}).status_code, 400)
        self.assertEqual(self.client.get("/api/i18n/convert/", {"amount": "1", "from": "PKR", "to": "XXX"}).status_code, 400)

    def test_tenant_user_can_read_but_not_change_global_currencies(self):
        self.assertEqual(self.client.get("/api/i18n/currencies/").status_code, 200)
        self.assertEqual(
            self.client.post("/api/i18n/currencies/", {"code": "EUR", "name": "Euro", "symbol": "E"}, format="json").status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(f"/api/i18n/currencies/{self.pkr.id}/", {"exchange_rate": "1"}, format="json").status_code,
            403,
        )
        self.assertEqual(self.client.delete(f"/api/i18n/currencies/{self.pkr.id}/").status_code, 403)
        self.pkr.refresh_from_db()
        self.assertEqual(self.pkr.exchange_rate, Decimal("280"))
        self.assertEqual(self.client.post("/api/i18n/languages/", {"code": "xx", "name": "X"}, format="json").status_code, 403)

    def test_platform_superuser_can_still_manage_currencies(self):
        admin = User.objects.create_superuser(username="p2-platform-admin", password="StrongPass123!")
        client = APIClient()
        client.force_authenticate(admin)
        response = client.patch(f"/api/i18n/currencies/{self.pkr.id}/", {"exchange_rate": "281"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.pkr.refresh_from_db()
        self.assertEqual(self.pkr.exchange_rate, Decimal("281"))
