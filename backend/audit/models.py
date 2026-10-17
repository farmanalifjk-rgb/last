from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_REFUND = "refund"
    ACTION_VOID = "void"
    ACTION_PRINT = "print"
    ACTION_EXPORT = "export"
    ACTION_CHOICES = [(ACTION_CREATE, "Create"), (ACTION_UPDATE, "Update"), (ACTION_DELETE, "Delete"),
                      (ACTION_LOGIN, "Login"), (ACTION_LOGOUT, "Logout"), (ACTION_REFUND, "Refund"),
                      (ACTION_VOID, "Void"), (ACTION_PRINT, "Print"), (ACTION_EXPORT, "Export")]
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="audit_events")
    actor_name = models.CharField(max_length=200, blank=True)
    # Namespaced operational events (for example, ``hr.attendance.clocked_in``)
    # are durable audit identifiers rather than a closed set of UI labels.
    action = models.CharField(max_length=120)
    entity_type = models.CharField(max_length=80)         # Order, Product, Customer...
    entity_id = models.CharField(max_length=60, blank=True)
    entity_label = models.CharField(max_length=255, blank=True)
    before = models.JSONField(default=dict, blank=True)   # snapshot prior to change
    after = models.JSONField(default=dict, blank=True)    # snapshot after change
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["entity_type", "entity_id"]),
                   models.Index(fields=["action"]),
                   models.Index(fields=["actor"])]


class ActivityFeed(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Lightweight, denormalised activity feed for the dashboard timeline."""
    actor_name = models.CharField(max_length=200, blank=True)
    summary = models.CharField(max_length=300)
    icon = models.CharField(max_length=40, blank=True)
    entity_type = models.CharField(max_length=80, blank=True)
    entity_id = models.CharField(max_length=60, blank=True)
    link = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
