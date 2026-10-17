"""
models_settings.py
═══════════════════════════════════════════════════════════════════════════════
All NEW models that power the Settings module (tabs: General, Company, POS,
Inventory, Payments, Taxes, Receipt, Users & Roles, Notifications, Hardware,
Backup & Restore, Appearance, Security, Data Management, About) plus the
extra platform features (multi-store, API keys, webhooks, templates, custom
fields, scheduled reports, error/crash logs, audit logs, etc).

Nothing here touches existing models — Company, Tax, PaymentMethod, Role,
UserProfile continue to live in models.py and are only extended with a
migration that adds new fields to them.

Imported into models.py with `from .models_settings import *` so Django's
app registry picks everything up automatically.
"""
import uuid
import secrets
from django.db import models
from django.conf import settings
from django.utils import timezone


# ═══════════════════════════════════════════════════════════════════════════
# Helper: Singleton pattern for "one row" settings groups
# ═══════════════════════════════════════════════════════════════════════════
class SingletonModel(models.Model):
    """Base class for per-tenant settings groups.

    Each settings model has one row per tenant.  ``load()`` accepts a tenant
    keyword argument; when omitted it falls back to the global singleton row
    (pk=1) for backward compatibility during migration.
    """
    tenant = models.ForeignKey(
        "saas.Tenant", null=True, blank=True, on_delete=models.CASCADE,
        related_name="%(class)s_settings",
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # settings rows can't be deleted

    @classmethod
    def load(cls, tenant=None):
        """Return the settings row for *tenant* (one row per tenant).

        Tenant-scoped singleton: one row per tenant, created atomically on
        first access. When *tenant* is ``None`` the legacy global row (pk=1)
        is returned for backward-compatibility during the migration window.
        Uses ``get_or_create`` inside ``transaction.atomic`` to avoid races
        when two requests create the first row concurrently.
        """
        from django.db import transaction
        if tenant is not None:
            try:
                with transaction.atomic():
                    obj, _ = cls.objects.get_or_create(tenant=tenant)
                    return obj
            except Exception:
                # Unique constraint race — another request won, return it
                return cls.objects.filter(tenant=tenant).first() or cls.objects.create(tenant=tenant)
        else:
            try:
                with transaction.atomic():
                    obj, _ = cls.objects.get_or_create(pk=1, defaults={"tenant": None})
                    return obj
            except Exception:
                return cls.objects.filter(pk=1).first() or cls.objects.create(pk=1, tenant=None)


# ═══════════════════════════════════════════════════════════════════════════
# 3. STORE SETTINGS (multi-store support)
# ═══════════════════════════════════════════════════════════════════════════
class Store(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30)

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="managed_stores",
    )
    currency = models.CharField(max_length=10, default="Rs")
    timezone = models.CharField(max_length=64, default="UTC")
    language = models.CharField(max_length=20, default="en")
    date_format = models.CharField(max_length=30, default="DD/MM/YYYY")
    time_format = models.CharField(max_length=10, default="24h", choices=[("12h", "12 Hour"), ("24h", "24 Hour")])
    weight_unit = models.CharField(max_length=10, default="kg", choices=[("kg", "Kilogram"), ("lb", "Pound"), ("g", "Gram")])
    dimension_unit = models.CharField(max_length=10, default="cm", choices=[("cm", "Centimeter"), ("in", "Inch"), ("m", "Meter")])
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="system_unique_store_code_per_tenant"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if self.is_default:
            Store.objects.filter(tenant=self.tenant).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# 4. POS SETTINGS  (Selling / Cart / Session behaviour)
# ═══════════════════════════════════════════════════════════════════════════
class POSSettings(SingletonModel):
    # Selling
    default_customer = models.ForeignKey(
        "pos.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    default_payment_method = models.ForeignKey(
        "pos.PaymentMethod", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    allow_negative_stock = models.BooleanField(default=False)
    allow_price_editing = models.BooleanField(default=True)
    allow_quantity_editing = models.BooleanField(default=True)
    allow_discount = models.BooleanField(default=True)
    allow_custom_discount = models.BooleanField(default=True)
    allow_custom_price = models.BooleanField(default=False)
    enable_barcode_scanner = models.BooleanField(default=True)
    auto_focus_barcode = models.BooleanField(default=True)
    auto_print_receipt = models.BooleanField(default=True)
    auto_open_cash_drawer = models.BooleanField(default=True)
    ask_before_closing_sale = models.BooleanField(default=True)
    enable_draft_orders = models.BooleanField(default=True)
    enable_hold_orders = models.BooleanField(default=True)
    enable_order_notes = models.BooleanField(default=True)

    # Cart
    merge_duplicate_products = models.BooleanField(default=True)
    allow_decimal_quantity = models.BooleanField(default=False)
    auto_remove_zero_quantity = models.BooleanField(default=True)
    show_stock_in_cart = models.BooleanField(default=True)
    show_product_image = models.BooleanField(default=True)
    show_sku = models.BooleanField(default=True)
    show_barcode = models.BooleanField(default=False)

    # Session
    require_opening_cash = models.BooleanField(default=True)
    require_closing_cash = models.BooleanField(default=True)
    auto_logout_minutes = models.PositiveIntegerField(default=0, help_text="0 = disabled")
    auto_save_draft = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "POS Settings"
        verbose_name_plural = "POS Settings"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="unique_pos_settings_per_tenant"),
        ]

    def __str__(self):
        return "POS Settings"


# ═══════════════════════════════════════════════════════════════════════════
# 5. INVENTORY SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
class InventorySettings(SingletonModel):
    VALUATION_CHOICES = [("fifo", "FIFO"), ("lifo", "LIFO"), ("average", "Weighted Average")]
    BARCODE_FORMAT_CHOICES = [
        ("CODE128", "CODE 128"), ("EAN13", "EAN-13"), ("EAN8", "EAN-8"),
        ("UPC", "UPC"), ("CODE39", "CODE 39"),
    ]

    # General
    low_stock_threshold = models.PositiveIntegerField(default=10)
    out_of_stock_threshold = models.PositiveIntegerField(default=0)
    default_stock_location = models.CharField(max_length=150, blank=True, default="Main Warehouse")
    stock_valuation_method = models.CharField(max_length=20, choices=VALUATION_CHOICES, default="fifo")

    # Barcode
    barcode_format = models.CharField(max_length=20, choices=BARCODE_FORMAT_CHOICES, default="CODE128")
    auto_generate_barcode = models.BooleanField(default=True)
    allow_duplicate_barcode = models.BooleanField(default=False)

    # Stock
    enable_stock_adjustments = models.BooleanField(default=True)
    enable_damage_tracking = models.BooleanField(default=True)
    enable_stock_transfers = models.BooleanField(default=True)
    enable_purchase_receiving = models.BooleanField(default=True)
    enable_inventory_audit = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Inventory Settings"
        verbose_name_plural = "Inventory Settings"

    def __str__(self):
        return "Inventory Settings"


# ═══════════════════════════════════════════════════════════════════════════
# 5b. TAX SETTINGS (global config; individual Tax rows already exist)
# ═══════════════════════════════════════════════════════════════════════════
class TaxSettings(SingletonModel):
    CALC_METHOD_CHOICES = [("line", "Per Line Item"), ("total", "On Order Total")]

    enable_taxes = models.BooleanField(default=True)
    prices_include_tax = models.BooleanField(default=False)
    default_tax = models.ForeignKey("pos.Tax", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    round_tax = models.BooleanField(default=True)
    tax_calculation_method = models.CharField(max_length=10, choices=CALC_METHOD_CHOICES, default="line")
    tax_precision = models.PositiveSmallIntegerField(default=2)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tax Settings"
        verbose_name_plural = "Tax Settings"

    def __str__(self):
        return "Tax Settings"


# ═══════════════════════════════════════════════════════════════════════════
# 7. RECEIPT SETTINGS (layout + show/hide content)
# ═══════════════════════════════════════════════════════════════════════════
class ReceiptSettings(SingletonModel):
    WIDTH_CHOICES = [("58mm", "58mm"), ("80mm", "80mm"), ("A5", "A5"), ("A4", "A4")]

    # Layout
    receipt_width = models.CharField(max_length=10, choices=WIDTH_CHOICES, default="80mm")
    font_size = models.PositiveSmallIntegerField(default=12)
    font_family = models.CharField(max_length=60, default="Courier New")
    margin_top = models.PositiveSmallIntegerField(default=5)
    margin_bottom = models.PositiveSmallIntegerField(default=5)
    margin_left = models.PositiveSmallIntegerField(default=5)
    margin_right = models.PositiveSmallIntegerField(default=5)

    # Content show/hide
    show_logo = models.BooleanField(default=True)
    show_store_name = models.BooleanField(default=True)
    show_cashier = models.BooleanField(default=True)
    show_customer = models.BooleanField(default=True)
    show_tax = models.BooleanField(default=True)
    show_discounts = models.BooleanField(default=True)
    show_barcode = models.BooleanField(default=False)
    show_qr_code = models.BooleanField(default=True)
    show_order_number = models.BooleanField(default=True)
    show_date = models.BooleanField(default=True)
    show_time = models.BooleanField(default=True)
    show_payment_method = models.BooleanField(default=True)
    show_change_returned = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Receipt Settings"
        verbose_name_plural = "Receipt Settings"

    def __str__(self):
        return "Receipt Settings"


# ═══════════════════════════════════════════════════════════════════════════
# 9. NOTIFICATION SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
class NotificationSettings(SingletonModel):
    low_stock_alerts = models.BooleanField(default=True)
    daily_sales_summary = models.BooleanField(default=True)
    backup_reminder = models.BooleanField(default=True)
    failed_login_alerts = models.BooleanField(default=True)
    new_version_available = models.BooleanField(default=True)
    notify_email = models.EmailField(blank=True)
    notify_sms_number = models.CharField(max_length=30, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Settings"
        verbose_name_plural = "Notification Settings"

    def __str__(self):
        return "Notification Settings"


class Notification(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Individual notification records shown in a bell/inbox UI."""
    LEVEL_CHOICES = [("info", "Info"), ("success", "Success"), ("warning", "Warning"), ("error", "Error")]

    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default="info")
    category = models.CharField(max_length=50, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


# ═══════════════════════════════════════════════════════════════════════════
# 10 / 19. HARDWARE (Printers, Scanner, Drawer, Display, Scale, Pole Display)
# ═══════════════════════════════════════════════════════════════════════════
class HardwareDevice(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    DEVICE_TYPES = [
        ("receipt_printer", "Receipt Printer"),
        ("label_printer", "Label Printer"),
        ("invoice_printer", "Invoice Printer"),
        ("barcode_scanner", "Barcode Scanner"),
        ("cash_drawer", "Cash Drawer"),
        ("customer_display", "Customer Display"),
        ("weighing_scale", "Weighing Scale"),
        ("pole_display", "Pole Display"),
    ]
    CONNECTION_TYPES = [
        ("usb", "USB"), ("network", "Network/IP"), ("bluetooth", "Bluetooth"),
        ("serial", "Serial"), ("browser", "Browser/Web USB"),
    ]

    device_type = models.CharField(max_length=30, choices=DEVICE_TYPES)
    name = models.CharField(max_length=150)
    connection_type = models.CharField(max_length=20, choices=CONNECTION_TYPES, default="usb")
    address = models.CharField(max_length=200, blank=True, help_text="IP address, port name, or device id")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    # Printer specific
    paper_width = models.CharField(max_length=10, blank=True, default="80mm")
    auto_cut = models.BooleanField(default=True)
    open_drawer_after_print = models.BooleanField(default=False)
    copies = models.PositiveSmallIntegerField(default=1)
    label_size = models.CharField(max_length=30, blank=True)

    extra_config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["device_type", "-is_default", "name"]

    def __str__(self):
        return f"{self.get_device_type_display()}: {self.name}"

    def save(self, *args, **kwargs):
        if self.is_default:
            HardwareDevice.objects.filter(tenant=self.tenant, device_type=self.device_type).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class BarcodeSettings(SingletonModel):
    scanner_prefix = models.CharField(max_length=10, blank=True)
    scanner_suffix = models.CharField(max_length=10, blank=True, default="\\n")
    auto_enter = models.BooleanField(default=True)
    camera_scanner_enabled = models.BooleanField(default=True)
    usb_scanner_enabled = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Barcode Settings"
        verbose_name_plural = "Barcode Settings"

    def __str__(self):
        return "Barcode Settings"


# ═══════════════════════════════════════════════════════════════════════════
# 12. CUSTOMER SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
class CustomerGroup(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="unique_customer_group_name_per_tenant")]

    def __str__(self):
        return self.name


class CustomerSettings(SingletonModel):
    enable_loyalty = models.BooleanField(default=False)
    loyalty_points_per_currency = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    loyalty_redemption_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0.01,
                                                   help_text="Currency value of 1 point")
    birthday_rewards_enabled = models.BooleanField(default=False)
    birthday_reward_points = models.PositiveIntegerField(default=0)
    default_walkin_customer = models.ForeignKey(
        "pos.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer Settings"
        verbose_name_plural = "Customer Settings"

    def __str__(self):
        return "Customer Settings"


# ═══════════════════════════════════════════════════════════════════════════
# 13. PRODUCT SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
class ProductSettings(SingletonModel):
    default_category = models.ForeignKey("pos.Category", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    default_brand = models.ForeignKey("pos.Brand", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    default_tax = models.ForeignKey("pos.Tax", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    default_unit = models.CharField(max_length=20, default="Piece")
    default_image = models.ImageField(upload_to="settings/product_defaults/", blank=True, null=True)
    enable_variants = models.BooleanField(default=True)
    enable_brands = models.BooleanField(default=True)
    enable_expiry = models.BooleanField(default=False)
    enable_batch_number = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product Settings"
        verbose_name_plural = "Product Settings"

    def __str__(self):
        return "Product Settings"


class CustomField(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """User-defined custom fields, attachable to any entity (product, customer, order...)."""
    ENTITY_CHOICES = [
        ("product", "Product"), ("customer", "Customer"), ("order", "Order"), ("supplier", "Supplier"),
    ]
    FIELD_TYPES = [
        ("text", "Text"), ("number", "Number"), ("boolean", "Yes/No"),
        ("date", "Date"), ("select", "Dropdown"),
    ]

    entity = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    name = models.CharField(max_length=100)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default="text")
    options = models.JSONField(default=list, blank=True, help_text="Choices for 'select' type")
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["entity", "sort_order", "name"]
        unique_together = ("tenant", "entity", "name")

    def __str__(self):
        return f"{self.get_entity_display()}: {self.name}"


# ═══════════════════════════════════════════════════════════════════════════
# 14. SECURITY SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
class SecuritySettings(SingletonModel):
    PASSWORD_POLICY_CHOICES = [
        ("basic", "Basic (min 6 chars)"),
        ("standard", "Standard (min 8 chars, letters + numbers)"),
        ("strong", "Strong (min 10 chars, upper/lower/number/symbol)"),
    ]

    two_factor_enabled = models.BooleanField(default=False)
    two_factor_method = models.CharField(
        max_length=20, default="email", choices=[("email", "Email"), ("sms", "SMS"), ("app", "Authenticator App")]
    )
    password_policy = models.CharField(max_length=20, choices=PASSWORD_POLICY_CHOICES, default="standard")
    password_min_length = models.PositiveSmallIntegerField(default=8)
    password_expiry_days = models.PositiveIntegerField(default=0, help_text="0 = never expires")
    session_timeout_minutes = models.PositiveIntegerField(default=30)
    max_login_attempts = models.PositiveSmallIntegerField(default=5)
    lockout_duration_minutes = models.PositiveIntegerField(default=15)
    require_device_authorization = models.BooleanField(default=False)
    enable_audit_logs = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Security Settings"
        verbose_name_plural = "Security Settings"

    def __str__(self):
        return "Security Settings"


class LoginAttempt(models.Model):
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    was_successful = models.BooleanField(default=False)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.username} - {'OK' if self.was_successful else 'FAILED'}"


class TrustedDevice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trusted_devices")
    device_id = models.CharField(max_length=100, default=uuid.uuid4)
    device_name = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    is_authorized = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_seen"]
        unique_together = ("user", "device_id")

    def __str__(self):
        return f"{self.user} - {self.device_name or self.device_id}"


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("create", "Create"), ("update", "Update"), ("delete", "Delete"),
        ("login", "Login"), ("logout", "Logout"), ("refund", "Refund"),
        ("void", "Void"), ("export", "Export"), ("import", "Import"), ("other", "Other"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default="other")
    entity = models.CharField(max_length=100, blank=True, help_text="e.g. Product, Order")
    entity_id = models.CharField(max_length=50, blank=True)
    description = models.CharField(max_length=500, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.entity} by {self.user}"


# ═══════════════════════════════════════════════════════════════════════════
# 15 / 16. BACKUP & RESTORE + DATA MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════
class BackupSettings(SingletonModel):
    FREQUENCY_CHOICES = [("hourly", "Hourly"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")]

    automatic_backup = models.BooleanField(default=False)
    backup_frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default="daily")
    backup_time = models.TimeField(default="02:00")
    keep_last_n_backups = models.PositiveSmallIntegerField(default=7)
    last_backup_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Backup Settings"
        verbose_name_plural = "Backup Settings"

    def __str__(self):
        return "Backup Settings"


def backup_file_path(instance, filename):
    return f"backups/{timezone.now().strftime('%Y/%m')}/{filename}"


class BackupRecord(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_CHOICES = [("pending", "Pending"), ("success", "Success"), ("failed", "Failed")]
    TYPE_CHOICES = [("manual", "Manual"), ("automatic", "Automatic")]

    file = models.FileField(upload_to=backup_file_path, blank=True, null=True)
    file_size_bytes = models.BigIntegerField(default=0)
    backup_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="manual")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Backup #{self.id} ({self.status})"


class DataManagementSettings(SingletonModel):
    automatic_database_optimization = models.BooleanField(default=False)
    automatic_data_cleanup = models.BooleanField(default=False)
    data_cleanup_older_than_days = models.PositiveIntegerField(default=365)
    last_cache_clear_at = models.DateTimeField(null=True, blank=True)
    last_index_rebuild_at = models.DateTimeField(null=True, blank=True)
    last_optimization_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Data Management Settings"
        verbose_name_plural = "Data Management Settings"

    def __str__(self):
        return "Data Management Settings"


# ═══════════════════════════════════════════════════════════════════════════
# 17. REPORT SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
class ReportSettings(SingletonModel):
    DATE_RANGE_CHOICES = [
        ("today", "Today"), ("yesterday", "Yesterday"), ("last_7_days", "Last 7 Days"),
        ("last_30_days", "Last 30 Days"), ("this_month", "This Month"), ("this_year", "This Year"),
    ]
    CHART_CHOICES = [("line", "Line"), ("bar", "Bar"), ("area", "Area"), ("pie", "Pie")]

    default_date_range = models.CharField(max_length=20, choices=DATE_RANGE_CHOICES, default="last_7_days")
    default_chart_type = models.CharField(max_length=10, choices=CHART_CHOICES, default="line")
    currency_display = models.CharField(max_length=10, default="symbol", choices=[("symbol", "Symbol"), ("code", "Code")])
    decimal_places = models.PositiveSmallIntegerField(default=2)
    auto_refresh_dashboard = models.BooleanField(default=True)
    auto_refresh_interval_seconds = models.PositiveIntegerField(default=60)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Report Settings"
        verbose_name_plural = "Report Settings"

    def __str__(self):
        return "Report Settings"


class ScheduledReport(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    REPORT_TYPES = [
        ("sales_summary", "Sales Summary"), ("inventory", "Inventory"),
        ("tax", "Tax Report"), ("customer", "Customer Report"), ("staff_performance", "Staff Performance"),
    ]
    FREQUENCY_CHOICES = [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")]

    name = models.CharField(max_length=150)
    report_type = models.CharField(max_length=30, choices=REPORT_TYPES)
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default="daily")
    recipients = models.JSONField(default=list, help_text="List of email addresses")
    is_active = models.BooleanField(default=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


# ═══════════════════════════════════════════════════════════════════════════
# 18. APPEARANCE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
class AppearanceSettings(SingletonModel):
    THEME_CHOICES = [("light", "Light"), ("dark", "Dark"), ("system", "System")]
    SIDEBAR_CHOICES = [("expanded", "Expanded"), ("collapsed", "Collapsed"), ("icons_only", "Icons Only")]

    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="light")
    sidebar_style = models.CharField(max_length=20, choices=SIDEBAR_CHOICES, default="expanded")
    accent_color = models.CharField(max_length=20, default="#6366F1")
    compact_mode = models.BooleanField(default=False)
    large_fonts = models.BooleanField(default=False)
    custom_css = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Appearance Settings"
        verbose_name_plural = "Appearance Settings"

    def __str__(self):
        return "Appearance Settings"


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE FLAGS (platform-wide switches from the bottom of the spec)
# ═══════════════════════════════════════════════════════════════════════════
class FeatureFlags(SingletonModel):
    offline_mode = models.BooleanField(default=False)
    automatic_sync = models.BooleanField(default=True)
    multi_store_support = models.BooleanField(default=False)
    multi_currency = models.BooleanField(default=False)
    multi_language = models.BooleanField(default=False)
    keyboard_shortcuts = models.BooleanField(default=True)
    favorites_dashboard = models.BooleanField(default=True)
    recent_activity_timeline = models.BooleanField(default=True)
    system_health_dashboard = models.BooleanField(default=True)
    performance_monitor = models.BooleanField(default=False)
    usage_analytics = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Feature Flags"
        verbose_name_plural = "Feature Flags"

    def __str__(self):
        return "Feature Flags"


# ═══════════════════════════════════════════════════════════════════════════
# DEVELOPER / INTEGRATIONS: API Keys, Webhooks, Templates
# ═══════════════════════════════════════════════════════════════════════════
def generate_api_key():
    return f"pos_{secrets.token_hex(24)}"


class APIKey(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    name = models.CharField(max_length=150)
    key = models.CharField(max_length=64, unique=True, editable=False, help_text="SHA-256 digest of the one-time secret")
    key_prefix = models.CharField(max_length=8, editable=False)
    key_last4 = models.CharField(max_length=4, editable=False)
    scopes = models.JSONField(default=list, blank=True, help_text="e.g. ['read:products','write:orders']")
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def masked_key(self):
        return f"{self.key_prefix}{'*' * 24}{self.key_last4}"


class Webhook(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    EVENT_CHOICES = [
        ("order.created", "Order Created"), ("order.paid", "Order Paid"),
        ("order.refunded", "Order Refunded"), ("product.low_stock", "Product Low Stock"),
        ("customer.created", "Customer Created"), ("session.closed", "Session Closed"),
    ]

    name = models.CharField(max_length=150)
    target_url = models.URLField()
    events = models.JSONField(default=list, help_text="List of event keys this webhook subscribes to")
    secret = models.CharField(max_length=80, default=secrets.token_hex, editable=False)
    is_active = models.BooleanField(default=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    last_status_code = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class WebhookDelivery(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="deliveries")
    event = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    status_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    response_body = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class EmailTemplate(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    TEMPLATE_KEYS = [
        ("receipt", "Receipt Email"), ("order_confirmation", "Order Confirmation"),
        ("low_stock_alert", "Low Stock Alert"), ("daily_summary", "Daily Sales Summary"),
        ("password_reset", "Password Reset"), ("welcome", "Welcome Email"),
        ("backup_report", "Backup Report"),
    ]

    key = models.CharField(max_length=50, choices=TEMPLATE_KEYS)
    subject = models.CharField(max_length=255)

    body_html = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="system_unique_email_template_key_per_tenant"),
        ]

    def __str__(self):
        return self.get_key_display()


class SMSTemplate(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    TEMPLATE_KEYS = [
        ("order_confirmation", "Order Confirmation"), ("otp", "OTP / Verification Code"),
        ("low_stock_alert", "Low Stock Alert"), ("loyalty_reward", "Loyalty Reward"),
        ("birthday_reward", "Birthday Reward"),
    ]

    key = models.CharField(max_length=50, choices=TEMPLATE_KEYS)
    body = models.CharField(max_length=320, blank=True)

    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="system_unique_sms_template_key_per_tenant"),
        ]

    def __str__(self):
        return self.get_key_display()


class ReceiptTemplate(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Named, switchable receipt layouts (in addition to the live ReceiptSettings)."""
    name = models.CharField(max_length=150)
    is_default = models.BooleanField(default=False)
    header_text = models.TextField(blank=True)
    footer_text = models.TextField(blank=True)
    layout_config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            ReceiptTemplate.objects.filter(tenant=self.tenant).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# ABOUT
# ═══════════════════════════════════════════════════════════════════════════
class AboutInfo(SingletonModel):
    pos_version = models.CharField(max_length=30, default="1.0.0")
    license_key = models.CharField(max_length=150, blank=True)
    license_status = models.CharField(
        max_length=20, default="trial",
        choices=[("trial", "Trial"), ("active", "Active"), ("expired", "Expired")],
    )
    device_id = models.CharField(max_length=100, default=uuid.uuid4, editable=False)
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=50, blank=True)
    documentation_url = models.URLField(blank=True)
    last_update_check_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "About Info"
        verbose_name_plural = "About Info"

    def __str__(self):
        return "About Info"


# ═══════════════════════════════════════════════════════════════════════════
# LOGS: Error / Crash (system health + monitoring)
# ═══════════════════════════════════════════════════════════════════════════
class ErrorLog(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    LOG_TYPES = [("error", "Error"), ("crash", "Crash")]
    SEVERITY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")]

    log_type = models.CharField(max_length=10, choices=LOG_TYPES, default="error")
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="medium")
    source = models.CharField(max_length=150, blank=True, help_text="e.g. frontend, backend, printer-service")
    message = models.CharField(max_length=500)
    stack_trace = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.log_type}] {self.message[:60]}"


