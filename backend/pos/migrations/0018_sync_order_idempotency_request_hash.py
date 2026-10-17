# The column already exists in the database.  This migration keeps the
# Django model in sync without touching the database.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0017_add_orderitem_cost_price_snapshot'),
    ]

    operations = []
