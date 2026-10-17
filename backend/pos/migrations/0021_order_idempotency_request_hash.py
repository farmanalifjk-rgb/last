from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0020_merge_20260827_2031"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="idempotency_request_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
