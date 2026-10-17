import hashlib

from django.db import migrations, models


def hash_existing_api_keys(apps, schema_editor):
    APIKey = apps.get_model("system", "APIKey")
    for item in APIKey.objects.all().iterator():
        current = item.key or ""
        if len(current) == 64 and all(character in "0123456789abcdef" for character in current.lower()):
            continue
        item.key_prefix = current[:8]
        item.key_last4 = current[-4:]
        item.key = hashlib.sha256(current.encode("utf-8")).hexdigest()
        item.save(update_fields=["key", "key_prefix", "key_last4"])


class Migration(migrations.Migration):
    dependencies = [("system", "0005_alter_customergroup_name_and_more")]

    operations = [
        migrations.AddField(model_name="apikey", name="key_prefix", field=models.CharField(blank=True, default="", max_length=8)),
        migrations.AddField(model_name="apikey", name="key_last4", field=models.CharField(blank=True, default="", max_length=4)),
        migrations.RunPython(hash_existing_api_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="apikey",
            name="key",
            field=models.CharField(editable=False, help_text="SHA-256 digest of the one-time secret", max_length=64, unique=True),
        ),
        migrations.AlterField(model_name="apikey", name="key_prefix", field=models.CharField(editable=False, max_length=8)),
        migrations.AlterField(model_name="apikey", name="key_last4", field=models.CharField(editable=False, max_length=4)),
    ]
