from django.db import migrations
from backend.security import EncryptedCredentialField


def encrypt_existing_fiscal_device_credentials(apps, schema_editor):
    FiscalDevice = apps.get_model("fiscal", "FiscalDevice")
    for row in FiscalDevice.objects.exclude(api_key="").iterator():
        row.save(update_fields=["api_key"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("fiscal", "0008_fiscalinvoiceline_cvt_fiscalinvoiceline_extra_tax_and_more")]

    operations = [
        migrations.AlterField(
            model_name="fiscaldevice",
            name="api_key",
            field=EncryptedCredentialField(blank=True, max_length=1024),
        ),
        migrations.RunPython(encrypt_existing_fiscal_device_credentials, noop),
    ]
