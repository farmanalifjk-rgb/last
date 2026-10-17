from django.contrib.auth import get_user_model
from django.test import TestCase

from audit.models import AuditEvent
from auth_app.models import AuthToken
from saas.models import Tenant, TenantMembership


class TokenLogoutAuditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="token-logout-audit-user",
            password="StrongPass123!",
        )
        self.tenant = Tenant.objects.create(
            name="Token Logout Audit Tenant",
            slug="token-logout-audit-tenant",
            owner=self.user,
            status="active",
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )
        self.token = AuthToken.objects.create(user=self.user)

    def test_token_logout_uses_active_membership_for_tenant_owned_audit_event(self):
        response = self.client.post(
            "/api/auth/logout/",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.token.refresh_from_db()
        self.assertTrue(self.token.is_revoked)
        event = AuditEvent.objects.get(
            tenant=self.tenant,
            action=AuditEvent.ACTION_LOGOUT,
            entity_type="User",
            actor=self.user,
        )
        self.assertEqual(event.entity_id, "")
