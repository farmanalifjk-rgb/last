from django.db import migrations
from backend.security import EncryptedCredentialField


def encrypt_existing_fbr_credentials(apps, schema_editor):
    FBRConfiguration = apps.get_model("fbr", "FBRConfiguration")
    for row in FBRConfiguration.objects.exclude(security_token="").iterator():
        row.save(update_fields=["security_token"])


def noop(apps, schema_editor):
    # Credential encryption is intentionally not reversible.
    pass


class Migration(migrations.Migration):
    dependencies = [("fbr", "0004_fbr_hardening")]

    operations = [
        migrations.AlterField(
            model_name="fbrconfiguration",
            name="security_token",
            field=EncryptedCredentialField(blank=True, max_length=1024),
        ),
        migrations.RunPython(encrypt_existing_fbr_credentials, noop),
    ]
