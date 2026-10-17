from django.db import models


class Integration(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    KIND_SHOPIFY = "shopify"
    KIND_WOOCOMMERCE = "woocommerce"
    KIND_QUICKBOOKS = "quickbooks"
    KIND_XERO = "xero"
    KIND_CHOICES = [(KIND_SHOPIFY, "Shopify"), (KIND_WOOCOMMERCE, "WooCommerce"),
                    (KIND_QUICKBOOKS, "QuickBooks"), (KIND_XERO, "Xero")]
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    name = models.CharField(max_length=120)
    # credentials / config stored as JSON (api keys, tokens, shop URLs)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "name"]
        unique_together = [("tenant", "kind", "name")]


class SyncLog(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    DIRECTION_INBOUND = "inbound"   # remote → local
    DIRECTION_OUTBOUND = "outbound"  # local → remote
    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_SUCCESS, "Success"), (STATUS_FAILED, "Failed")]
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="sync_logs")
    direction = models.CharField(max_length=10, choices=[(DIRECTION_INBOUND, "Inbound"), (DIRECTION_OUTBOUND, "Outbound")])
    entity_type = models.CharField(max_length=60)   # product, order, customer, invoice
    entity_id = models.CharField(max_length=60, blank=True)
    remote_id = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.integration_id and self.tenant_id and self.integration.tenant_id != self.tenant_id:
            raise ValidationError({"integration": "Integration must belong to the same tenant as its sync log."})

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["integration", "status"]),
                   models.Index(fields=["entity_type", "entity_id"])]


class SyncMapping(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Maps a local entity to its remote counterpart (local product ↔ Shopify variant)."""
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="mappings")
    entity_type = models.CharField(max_length=60)
    local_id = models.CharField(max_length=60)
    remote_id = models.CharField(max_length=60)
    last_hash = models.CharField(max_length=64, blank=True, help_text="Content hash to detect changes")
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.integration_id and self.tenant_id and self.integration.tenant_id != self.tenant_id:
            raise ValidationError({"integration": "Integration must belong to the same tenant as its mapping."})

    class Meta:
        unique_together = [("integration", "entity_type", "local_id")]
        indexes = [models.Index(fields=["integration", "entity_type", "remote_id"])]
