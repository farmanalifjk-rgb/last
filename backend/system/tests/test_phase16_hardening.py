from unittest.mock import patch
from django.utils import timezone
from datetime import timedelta

from system.models import SecuritySettings, TrustedDevice

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from auth_app.models import AuthToken
from auth_app.models import OneTimePasscode
from auth_app.views import OTPDeliveryUnavailable, _deliver_otp, _issue_otp
from backend.security import ProductionSecurityHeadersMiddleware
from system.views import _read_csv_import, _validated_import_upload
from hr.views import EmployeeSerializer
from saas.models import Tenant, TenantMembership
from tax.serializers import TaxBreakdownSerializer, TaxReportSerializer


User = get_user_model()


class Phase16HardeningTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")

    def test_readiness_health_is_public_and_contains_no_sensitive_configuration(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {"status": "ok", "database": "ok"})

    @patch("django.db.connection.cursor", side_effect=RuntimeError("database unavailable"))
    def test_readiness_health_fails_closed_without_exposing_exception_details(self, _cursor):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 503, response.data)
        self.assertEqual(response.data, {"status": "unavailable", "database": "unavailable"})

    def test_unconfigured_sms_otp_delivery_does_not_log_the_code(self):
        user = User.objects.create_user(username="p16-sms", password="StrongPass123!", email="p16@example.invalid")
        with self.assertLogs("auth_app.views", level="ERROR") as logs:
            delivered = _deliver_otp(user, "481516", "login_2fa", "sms")
        self.assertFalse(delivered)
        self.assertNotIn("481516", "\n".join(logs.output))

    def test_otp_challenge_is_not_persisted_when_delivery_is_unavailable(self):
        user = User.objects.create_user(username="p16-otp", password="StrongPass123!", email="p16@example.invalid")
        security = SecuritySettings.load()
        security.two_factor_method = "sms"
        security.save(update_fields=["two_factor_method"])
        with self.assertRaises(OTPDeliveryUnavailable):
            _issue_otp(user, "login_2fa")
        self.assertFalse(OneTimePasscode.objects.filter(user=user, purpose="login_2fa").exists())

    @override_settings(DEBUG=False)
    def test_production_security_headers_are_restrictive_and_font_compatible(self):
        middleware = ProductionSecurityHeadersMiddleware(lambda _request: HttpResponse("ok"))
        response = middleware(RequestFactory().get("/"))
        csp = response["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("fonts.googleapis.com", csp)
        self.assertNotIn("'unsafe-inline'", csp)
        self.assertEqual(response["Permissions-Policy"], "camera=(), geolocation=(), microphone=(), payment=(), usb=()")

    def test_import_validator_rejects_wrong_extension_mime_and_oversize_files(self):
        request = type("Request", (), {"FILES": {"file": SimpleUploadedFile("payload.exe", b"data", content_type="application/octet-stream")}})()
        with self.assertRaises(ValidationError):
            _validated_import_upload(request, extensions=(".csv",), content_types={"text/csv"})

        request.FILES["file"] = SimpleUploadedFile("payload.csv", b"data", content_type="application/json")
        with self.assertRaises(ValidationError):
            _validated_import_upload(request, extensions=(".csv",), content_types={"text/csv"})

        request.FILES["file"] = SimpleUploadedFile("payload.csv", b"x" * (2 * 1024 * 1024 + 1), content_type="text/csv")
        with self.assertRaises(ValidationError):
            _validated_import_upload(request, extensions=(".csv",), content_types={"text/csv"})

    def test_csv_reader_rejects_non_utf8_and_accepts_bounded_utf8_csv(self):
        invalid = SimpleUploadedFile("invalid.csv", b"\xff", content_type="text/csv")
        with self.assertRaises(ValidationError):
            _read_csv_import(invalid)

        valid = SimpleUploadedFile("valid.csv", b"Name,SKU\nDesk,SKU-1\n", content_type="text/csv")
        self.assertEqual(_read_csv_import(valid), [{"Name": "Desk", "SKU": "SKU-1"}])

    def test_hr_schema_generation_uses_empty_relation_querysets_without_active_tenant(self):
        schema_view = type("SchemaView", (), {"swagger_fake_view": True})()
        serializer = EmployeeSerializer(context={"view": schema_view})
        self.assertFalse(serializer.fields["department"].queryset.exists())

    def test_tax_reporting_serializers_are_explicitly_read_only(self):
        for serializer_class in (TaxBreakdownSerializer, TaxReportSerializer):
            serializer = serializer_class()
            self.assertTrue(all(field.read_only for field in serializer.fields.values()))

    def test_dashboard_uses_token_principal_tenant_over_stale_session_context(self):
        stale_user = User.objects.create_user(username="p16-dashboard-stale", password="StrongPass123!")
        token_user = User.objects.create_user(username="p16-dashboard-token", password="StrongPass123!")
        stale_tenant = Tenant.objects.create(name="P16 stale tenant", slug="p16-dashboard-stale", owner=stale_user, status=Tenant.STATUS_ACTIVE)
        token_tenant = Tenant.objects.create(name="P16 token tenant", slug="p16-dashboard-token", owner=token_user, status=Tenant.STATUS_ACTIVE)
        TenantMembership.objects.create(tenant=stale_tenant, user=stale_user, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        TenantMembership.objects.create(tenant=token_tenant, user=token_user, role=TenantMembership.ROLE_OWNER, is_active_in_tenant=True)
        token = AuthToken.objects.create(user=token_user)
        self.client.force_login(stale_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        with patch("dashboard.views.DashboardService.get_recent_orders", autospec=True, side_effect=lambda service, _limit: {"tenant_id": service.request.tenant.id}):
            response = self.client.get("/api/dashboard/recent-orders/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["tenant_id"], token_tenant.id)

    def test_otp_device_binding_rejects_code_from_different_device(self):
        user = User.objects.create_user(
            username="p16-device-bound",
            password="StrongPass123!",
        )
        device_a = TrustedDevice.objects.create(
            user=user,
            device_id="device-a",
            device_name="Device A",
        )
        device_b = TrustedDevice.objects.create(
            user=user,
            device_id="device-b",
            device_name="Device B",
        )

        otp = OneTimePasscode.objects.create(
            user=user,
            device=device_a,
            purpose="login_2fa",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        otp.set_code("123456")
        otp.save(update_fields=["code_hash"])

        response = self.client.post(
            "/api/auth/verify-otp/",
            {
                "username": user.username,
                "code": "123456",
                "device_id": device_b.device_id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("device", response.data["error"].lower())
        otp.refresh_from_db()
        self.assertFalse(otp.is_used)

    def test_resend_otp_does_not_resend_password_reset_otp(self):
        user = User.objects.create_user(username="p16-resend-password-reset", password="StrongPass123!", email="p16-resend@example.com")

        otp = OneTimePasscode.objects.create(user=user, purpose="password_reset", expires_at=timezone.now() + timedelta(minutes=10))
        otp.set_code("654321")
        otp.save(update_fields=["code_hash"])

        response = self.client.post("/api/auth/resend-otp/", {"username": user.username}, format="json")

        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(OneTimePasscode.objects.filter(user=user, purpose="password_reset").count(), 1)

    def test_verify_otp_rejects_password_reset_otp(self):
        user = User.objects.create_user(username="p16-password-reset-purpose", password="StrongPass123!")

        otp = OneTimePasscode.objects.create(user=user, purpose="password_reset", expires_at=timezone.now() + timedelta(minutes=10))
        otp.set_code("654321")
        otp.save(update_fields=["code_hash"])

        response = self.client.post("/api/auth/verify-otp/", {"username": user.username, "code": "654321"}, format="json")

        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn("token", response.data)
        otp.refresh_from_db()
        self.assertFalse(otp.is_used)
        
