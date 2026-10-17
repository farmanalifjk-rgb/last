"""
serializers_settings.py
Serializers for every model in models_settings.py plus the extended
Company / PaymentMethod / Customer / Product fields.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from pos.models import (
    Company, PaymentMethod, Tax, Customer, Product, Category, Brand,
)
from system.models import (
    Store, POSSettings, InventorySettings, TaxSettings, ReceiptSettings,
    NotificationSettings, Notification, HardwareDevice, BarcodeSettings,
    CustomerGroup, CustomerSettings, ProductSettings, CustomField,
    SecuritySettings, LoginAttempt, TrustedDevice, AuditLog,
    BackupSettings, BackupRecord, DataManagementSettings,
    ReportSettings, ScheduledReport, AppearanceSettings, FeatureFlags,
    APIKey, Webhook, WebhookDelivery, EmailTemplate, SMSTemplate,
    ReceiptTemplate, AboutInfo, ErrorLog,
)

User = get_user_model()


# ─── Company (General / Company tab) ───────────────────────────────────────
class CompanyFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id","tenant","name","tagline","address","phone","email","website","tax_number","footer_message","logo","currency","receipt_paper","gst","legal_name","cover_image","business_type","industry","business_registration_number","country","state","city","postal_code","full_address","receipt_header","thank_you_message","return_policy","show_qr_code_on_receipt","show_logo_on_receipt"]


# ─── Store ──────────────────────────────────────────────────────────────────
class StoreSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source="manager.get_full_name", read_only=True, default="")

    class Meta:
        model = Store
        fields = ["id", "tenant", "name", "code", "manager", "manager_name", "currency", "timezone", "language", "date_format", "time_format", "weight_unit", "dimension_unit", "address", "phone", "is_active", "is_default", "created_at"]


# ─── POS Settings ───────────────────────────────────────────────────────────
class POSSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSSettings
        fields = ["id","tenant","default_customer","default_payment_method","allow_negative_stock","allow_price_editing","allow_quantity_editing","allow_discount","allow_custom_discount","allow_custom_price","enable_barcode_scanner","auto_focus_barcode","auto_print_receipt","auto_open_cash_drawer","ask_before_closing_sale","enable_draft_orders","enable_hold_orders","enable_order_notes","merge_duplicate_products","allow_decimal_quantity","auto_remove_zero_quantity","show_stock_in_cart","show_product_image","show_sku","show_barcode","require_opening_cash","require_closing_cash","auto_logout_minutes","auto_save_draft","updated_at"]


# ─── Inventory Settings ─────────────────────────────────────────────────────
class InventorySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventorySettings
        fields = ["id","tenant","low_stock_threshold","out_of_stock_threshold","default_stock_location","stock_valuation_method","barcode_format","auto_generate_barcode","allow_duplicate_barcode","enable_stock_adjustments","enable_damage_tracking","enable_stock_transfers","enable_purchase_receiving","enable_inventory_audit","updated_at"]


# ─── Tax Settings + Tax ─────────────────────────────────────────────────────
class TaxSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxSettings
        fields = ["id","tenant","enable_taxes","prices_include_tax","default_tax","round_tax","tax_calculation_method","tax_precision","updated_at"]


class TaxFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tax
        fields = ["id","tenant","name","rate","tax_type","description","is_active","is_default","created_at"]


# ─── Payment Methods ────────────────────────────────────────────────────────
class PaymentMethodFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ["id","tenant","name","method_type","is_active","is_default","instructions","created_at","icon","color"]


# ─── Receipt Settings ───────────────────────────────────────────────────────
class ReceiptSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptSettings
        fields = ["id","tenant","receipt_width","font_size","font_family","margin_top","margin_bottom","margin_left","margin_right","show_logo","show_store_name","show_cashier","show_customer","show_tax","show_discounts","show_barcode","show_qr_code","show_order_number","show_date","show_time","show_payment_method","show_change_returned","updated_at"]


class ReceiptTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptTemplate
        fields = ["id","tenant","name","is_default","header_text","footer_text","layout_config","created_at"]
        ref_name = "SystemReceiptTemplate"


# ─── Notifications ──────────────────────────────────────────────────────────
class NotificationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSettings
        fields = ["id","tenant","low_stock_alerts","daily_sales_summary","backup_reminder","failed_login_alerts","new_version_available","notify_email","notify_sms_number","updated_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id","tenant","title","message","level","category","is_read","created_at"]


# ─── Hardware ───────────────────────────────────────────────────────────────
class HardwareDeviceSerializer(serializers.ModelSerializer):
    device_type_display = serializers.CharField(source="get_device_type_display", read_only=True)

    class Meta:
        model = HardwareDevice
        fields = ["id","tenant","device_type","device_type_display","name","connection_type","address","is_active","is_default","paper_width","auto_cut","open_drawer_after_print","copies","label_size","extra_config","created_at","updated_at"]


class BarcodeSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BarcodeSettings
        fields = ["id","tenant","scanner_prefix","scanner_suffix","auto_enter","camera_scanner_enabled","usb_scanner_enabled","updated_at"]


# ─── Customer ───────────────────────────────────────────────────────────────
class CustomerGroupSerializer(serializers.ModelSerializer):
    customers_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomerGroup
        fields = ["id","tenant","name","description","discount_percent","is_active","created_at","customers_count"]

    def get_customers_count(self, obj):
        return obj.customers.count()


class CustomerSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerSettings
        fields = ["id","tenant","enable_loyalty","loyalty_points_per_currency","loyalty_redemption_rate","birthday_rewards_enabled","birthday_reward_points","default_walkin_customer","updated_at"]


class CustomerFullSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True, default="")

    class Meta:
        model = Customer
        fields = ["id","tenant","name","phone","email","address","customer_code","is_active","created_at","updated_at","group","group_name","loyalty_points","date_of_birth"]


# ─── Product Settings + Custom Fields ───────────────────────────────────────
class ProductSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSettings
        fields = ["id","tenant","default_category","default_brand","default_tax","default_unit","default_image","enable_variants","enable_brands","enable_expiry","enable_batch_number","updated_at"]


class CustomFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomField
        fields = ["id","tenant","entity","name","field_type","options","is_required","is_active","sort_order","created_at"]


# ─── Security ───────────────────────────────────────────────────────────────
class SecuritySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecuritySettings
        fields = ["id","tenant","two_factor_enabled","two_factor_method","password_policy","password_min_length","password_expiry_days","session_timeout_minutes","max_login_attempts","lockout_duration_minutes","require_device_authorization","enable_audit_logs","updated_at"]


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = ["id","username","ip_address","user_agent","was_successful","reason","created_at"]


class TrustedDeviceSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = TrustedDevice
        fields = ["id","user","user_name","device_id","device_name","ip_address","user_agent","is_authorized","last_seen","created_at"]


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True, default="")

    class Meta:
        model = AuditLog
        fields = ["id","user","user_name","action","entity","entity_id","description","ip_address","metadata","created_at"]


# ─── Backup & Restore / Data Management ─────────────────────────────────────
class BackupSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupSettings
        fields = ["id","tenant","automatic_backup","backup_frequency","backup_time","keep_last_n_backups","last_backup_at","updated_at"]


class BackupRecordSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default="")

    class Meta:
        model = BackupRecord
        fields = ["id","tenant","file","file_size_bytes","backup_type","status","notes","created_by","created_by_name","created_at"]


class DataManagementSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataManagementSettings
        fields = ["id","tenant","automatic_database_optimization","automatic_data_cleanup","data_cleanup_older_than_days","last_cache_clear_at","last_index_rebuild_at","last_optimization_at","updated_at"]


# ─── Reports ────────────────────────────────────────────────────────────────
class ReportSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportSettings
        fields = ["id","tenant","default_date_range","default_chart_type","currency_display","decimal_places","auto_refresh_dashboard","auto_refresh_interval_seconds","updated_at"]


class ScheduledReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledReport
        fields = ["id","tenant","name","report_type","frequency","recipients","is_active","last_sent_at","created_at"]


# ─── Appearance ─────────────────────────────────────────────────────────────
class AppearanceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppearanceSettings
        fields = ["id","tenant","theme","sidebar_style","accent_color","compact_mode","large_fonts","custom_css","updated_at"]


# ─── Feature Flags ──────────────────────────────────────────────────────────
class FeatureFlagsSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureFlags
        fields = ["id","tenant","offline_mode","automatic_sync","multi_store_support","multi_currency","multi_language","keyboard_shortcuts","favorites_dashboard","recent_activity_timeline","system_health_dashboard","performance_monitor","usage_analytics","updated_at"]


# ─── Developer / Integrations ───────────────────────────────────────────────
class APIKeySerializer(serializers.ModelSerializer):
    key_display = serializers.SerializerMethodField()

    class Meta:
        model = APIKey
        fields = ["id", "name", "key_display", "scopes", "is_active", "last_used_at",
                  "created_by", "created_at", "expires_at"]

    def get_key_display(self, obj):
        # Full key is only ever shown once, at creation time (see view). Afterwards masked.
        return obj.masked_key()


class APIKeyCreateResponseSerializer(serializers.ModelSerializer):
    secret = serializers.SerializerMethodField()

    class Meta:
        model = APIKey
        fields = ["id", "name", "secret", "scopes", "is_active", "created_at", "expires_at"]

    def get_secret(self, obj):
        return self.context.get("secret")


class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = ["id", "name", "target_url", "events", "is_active", "last_triggered_at", "last_status_code", "created_at"]
        read_only_fields = ["id", "last_triggered_at", "last_status_code", "created_at"]


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = ["id", "webhook", "event", "status_code", "success", "created_at"]


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = ["id","tenant","key","subject","body_html","is_active","updated_at"]


class SMSTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSTemplate
        fields = ["id","tenant","key","body","is_active","updated_at"]


# ─── About ──────────────────────────────────────────────────────────────────
class AboutInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = AboutInfo
        fields = ["id","tenant","pos_version","license_key","license_status","device_id","support_email","support_phone","documentation_url","last_update_check_at","updated_at"]


# ─── Error / Crash Logs ──────────────────────────────────────────────────────
class ErrorLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True, default="")

    class Meta:
        model = ErrorLog
        fields = ["id", "log_type", "severity", "source", "message", "user", "user_name", "is_resolved", "created_at"]
        read_only_fields = ["id", "created_at"]


