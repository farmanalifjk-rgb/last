import os
from django.db import migrations
from django.utils.text import slugify


TENANT_MODELS = [
    ("pos", name) for name in ["Category", "Brand", "Product", "Customer", "CashSession", "CashTransaction", "Order", "OrderItem", "Payment", "DraftOrder", "DraftOrderItem", "StockMovement", "Company", "Refund", "RefundItem", "StockAdjustment", "StockAdjustmentItem", "Supplier", "PurchaseOrder", "PurchaseOrderItem", "PurchaseReturn", "PurchaseReturnItem", "Variant", "VariantValue", "Tax", "PaymentMethod"]
] + [
    (app, name) for app, names in {
        "catalog": ["ProductVariant", "ProductVariantAttribute", "ProductBundle", "BundleComponent", "SerialNumber", "Batch", "BatchMovement", "ProductMedia"],
        "pricing": ["PriceList", "PriceListItem", "CustomerGroupPrice", "VolumeTier", "TimeBasedPrice", "BuyXGetY"],
        "inventory": ["BinLocation", "StockReservation", "CycleCount", "CycleCountLine", "ReorderRule", "ABCAnalysis", "InventoryAgingSnapshot"],
        "pos_core": ["ParkedOrder", "Layaway", "LayawayPayment", "SplitBill", "SplitBillShare", "ExchangeOrder", "OfflineSyncQueue", "ReceiptTemplate", "CashDrawerEvent"],
        "customers": ["CustomerAddress", "CustomerCreditLimit", "CustomerDocument", "LoyaltyEvent", "CustomerNote", "CustomerPortalToken"],
        "payments": ["GiftCard", "GiftCardTransaction", "StoreCredit", "StoreCreditTransaction", "TenderedPayment", "PaymentReconciliation", "ReconciliationLine", "RefundCreditNote"],
        "suppliers": ["SupplierContact", "GoodsReceipt", "GoodsReceiptLine", "PurchaseReturn", "PurchaseReturnLine", "SupplierPortalToken"],
        "transfers": ["StockTransfer", "StockTransferItem", "PutAwayRule", "PutAwayTask", "BinReplenishmentTask"],
        "tax": ["TaxRate", "TaxExemption", "TaxBreakdown", "TaxReport"],
        "notifications": ["AlertRule", "Notification", "NotificationDigest"],
        "audit": ["AuditEvent", "ActivityFeed"],
        "integrations": ["Integration", "SyncLog", "SyncMapping"],
        "hr": ["Department", "Employee", "Shift", "Attendance", "LeaveType", "LeaveRequest", "PayrollRun", "PayrollEntry"],
        "accounting": ["ChartOfAccount", "JournalEntry", "JournalEntryLine", "ExpenseCategory", "Expense"],
        "fiscal": ["InvoiceSequence", "FiscalInvoice", "FiscalDevice", "FiscalSubmission"],
        "loyalty": ["LoyaltyProgram", "MembershipTier", "LoyaltyTransaction", "Coupon", "Promotion"],
        "operations": ["ApprovalRule", "ApprovalRequest", "InAppNotification", "EmailQueue", "SMSQueue"],
        "enterprise": ["Warehouse", "WarehouseStock", "WarehouseTransfer", "WarehouseTransferItem"],
        "system": ["Store", "Notification", "HardwareDevice", "CustomerGroup", "CustomField", "BackupRecord", "ScheduledReport", "APIKey", "Webhook", "WebhookDelivery", "EmailTemplate", "SMSTemplate", "ReceiptTemplate", "ErrorLog"],
    }.items() for name in names
]


def forwards(apps, schema_editor):
    Tenant = apps.get_model("saas", "Tenant")
    User = apps.get_model("auth", "User")
    Membership = apps.get_model("saas", "TenantMembership")
    default_slug = os.environ.get("TENANT_MIGRATION_DEFAULT_SLUG", "").strip()
    default_name = os.environ.get("TENANT_MIGRATION_DEFAULT_NAME", "Migrated Default Tenant").strip()
    owner_id = os.environ.get("TENANT_MIGRATION_DEFAULT_OWNER_ID", "").strip()

    legacy_tenants = []
    try:
        LegacyTenant = apps.get_model("tenancy", "Tenant")
        LegacyMembership = apps.get_model("tenancy", "UserTenantMembership")
        for legacy in LegacyTenant.objects.all().iterator():
            owner = LegacyMembership.objects.filter(tenant_id=legacy.id, is_active=True).order_by("id").first()
            owner_user_id = owner.user_id if owner else None
            if owner_user_id:
                tenant, _ = Tenant.objects.get_or_create(
                    slug=slugify(legacy.code or legacy.name)[:80],
                    defaults={"name": legacy.name, "owner_id": owner_user_id, "status": "active"},
                )
                legacy_tenants.append(tenant)
    except LookupError:
        pass

    owned_count = 0
    for app_label, model_name in TENANT_MODELS:
        Model = apps.get_model(app_label, model_name)
        owned_count += Model.objects.filter(tenant__isnull=False).count()

    if owned_count:
        return

    unowned_count = 0
    for app_label, model_name in TENANT_MODELS:
        Model = apps.get_model(app_label, model_name)
        unowned_count += Model.objects.filter(tenant__isnull=True).count()

    if not unowned_count:
        return

    if not default_slug:
        raise RuntimeError(
            "Tenant ownership migration found existing business records but "
            "TENANT_MIGRATION_DEFAULT_SLUG is not set. Refusing ambiguous assignment."
        )

    owner = None
    if owner_id:
        owner = User.objects.filter(pk=owner_id).first()
    if owner is None:
        owner = User.objects.filter(is_superuser=True).order_by("id").first() or User.objects.order_by("id").first()
    if owner is None:
        raise RuntimeError("Cannot create migration tenant: no existing user is available as owner.")

    tenant, _ = Tenant.objects.get_or_create(
        slug=default_slug[:80],
        defaults={"name": default_name, "owner_id": owner.id, "status": "active"},
    )
    Membership.objects.get_or_create(
        tenant_id=tenant.id,
        user_id=owner.id,
        defaults={"role": "owner", "is_active_in_tenant": True},
    )

    for app_label, model_name in TENANT_MODELS:
        Model = apps.get_model(app_label, model_name)
        Model.objects.filter(tenant__isnull=True).update(tenant_id=tenant.id)


def backwards(apps, schema_editor):
    # Ownership is intentionally not removed on rollback; deleting tenant links
    # would reintroduce ambiguity and could make a later forward migration unsafe.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("saas", "0001_initial"),
        ("tenancy", "0001_initial"),
        ("pos", "0006_brand_tenant_cashsession_tenant_and_more"),
        ("catalog", "0003_batch_tenant_batchmovement_tenant_and_more"),
        ("pricing", "0002_buyxgety_tenant_customergroupprice_tenant_and_more"),
        ("inventory", "0003_abcanalysis_tenant_binlocation_tenant_and_more"),
        ("pos_core", "0002_cashdrawerevent_tenant_exchangeorder_tenant_and_more"),
        ("customers", "0003_customeraddress_tenant_customercreditlimit_tenant_and_more"),
        ("payments", "0003_giftcard_tenant_giftcardtransaction_tenant_and_more"),
        ("suppliers", "0002_goodsreceipt_tenant_goodsreceiptline_tenant_and_more"),
        ("transfers", "0002_binreplenishmenttask_tenant_putawayrule_tenant_and_more"),
        ("tax", "0002_taxbreakdown_tenant_taxexemption_tenant_and_more"),
        ("notifications", "0002_alertrule_tenant_notification_tenant_and_more"),
        ("audit", "0002_activityfeed_tenant_auditevent_tenant"),
        ("integrations", "0002_integration_tenant_synclog_tenant_syncmapping_tenant"),
        ("hr", "0002_attendance_tenant_department_tenant_employee_tenant_and_more"),
        ("accounting", "0002_chartofaccount_tenant_expense_tenant_and_more"),
        ("fiscal", "0003_fiscaldevice_tenant_fiscalinvoice_tenant_and_more"),
        ("loyalty", "0003_coupon_tenant_loyaltyprogram_tenant_and_more"),
        ("operations", "0002_approvalrequest_tenant_approvalrule_tenant_and_more"),
        ("system", "0003_apikey_tenant_backuprecord_tenant_and_more"),
        ("enterprise", "0003_warehouse_tenant_warehousestock_tenant_and_more"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
