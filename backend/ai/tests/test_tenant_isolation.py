from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ai.models import AIQuery
from saas.models import Tenant, TenantMembership


@override_settings(AI_FEATURE_ENABLED=False)
class AITenantIsolationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_superuser(
            username="ai-tenant-a", email="ai-a@example.test", password="test-password"
        )
        self.user_b = User.objects.create_user(username="ai-tenant-b", password="test-password")
        self.tenant_a = Tenant.objects.create(name="AI Tenant A", slug="ai-tenant-a", owner=self.user_a)
        self.tenant_b = Tenant.objects.create(name="AI Tenant B", slug="ai-tenant-b", owner=self.user_b)
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b,
            user=self.user_b,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )
        self.query_a = AIQuery.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            question="A only",
            answer="Tenant A answer",
        )
        self.query_b = AIQuery.objects.create(
            tenant=self.tenant_b,
            user=self.user_b,
            question="B only",
            answer="Tenant B answer",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user_a)

    def test_history_returns_only_current_tenant_and_current_user_records(self):
        response = self.client.get("/api/ai/history/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [self.query_a.id])

    def test_ask_returns_honest_unavailable_state_and_does_not_persist_fake_answer(self):
        before_count = AIQuery.objects.count()
        response = self.client.post("/api/ai/ask/", {"question": "How are sales?"}, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "ai_unavailable")
        self.assertEqual(AIQuery.objects.count(), before_count)

    def test_prompt_is_not_a_second_request_contract(self):
        response = self.client.post("/api/ai/ask/", {"prompt": "legacy payload"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "question is required")
