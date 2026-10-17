from django.db import connection

from fbr.models import FBRConfiguration
from fbr.tests.base import FBRTestBase


class FBRConfigurationCredentialEncryptionTests(FBRTestBase):
    def test_security_token_is_encrypted_at_rest(self):
        self.config_a.security_token = "super-secret-fbr-token"
        self.config_a.save(update_fields=["security_token"])

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT security_token FROM {FBRConfiguration._meta.db_table} WHERE id = %s",
                [self.config_a.id],
            )
            stored = cursor.fetchone()[0]

        self.assertTrue(stored.startswith("enc:v1:"))
        self.assertNotIn("super-secret-fbr-token", stored)
        self.config_a.refresh_from_db()
        self.assertEqual(self.config_a.security_token, "super-secret-fbr-token")
