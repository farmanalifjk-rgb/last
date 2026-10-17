from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("rbac", "0012_phase15_governance_scopes")]

    operations = [
        migrations.RemoveConstraint(model_name="userrole", name="rbac_unique_user_role_scope"),
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.UniqueConstraint(
                fields=("user", "role", "tenant"),
                condition=Q(("branch__isnull", True)),
                name="rbac_unique_user_role_tenant_unbranched",
            ),
        ),
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.UniqueConstraint(
                fields=("user", "role", "tenant", "branch"),
                condition=Q(("branch__isnull", False)),
                name="rbac_unique_user_role_tenant_branch",
            ),
        ),
    ]
