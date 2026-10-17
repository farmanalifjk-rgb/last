from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from fiscal.models import FiscalDevice
from saas.models import Tenant


User = get_user_model()


class FiscalDeviceCredentialEncryptionTests(TestCase):
    def test_api_key_is_encrypted_at_rest(self):
        user = User.objects.create_user(username="credential-test", password="testpass123")
        tenant = Tenant.objects.create(
            name="Credential Tenant",
            slug="credential-tenant",
            owner=user,
            status="active",
        )
        device = FiscalDevice.objects.create(
            tenant=tenant,
            name="Encryption test",
            kind=FiscalDevice.KIND_API,
            endpoint_url="https://example.invalid",
            api_key="super-secret-api-key",
        )

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT api_key FROM {FiscalDevice._meta.db_table} WHERE id = %s",
                [device.id],
            )
            stored = cursor.fetchone()[0]

        self.assertTrue(stored.startswith("enc:v1:"))
        self.assertNotIn("super-secret-api-key", stored)
        device.refresh_from_db()
        self.assertEqual(device.api_key, "super-secret-api-key")
