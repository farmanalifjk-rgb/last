from django.contrib import admin
from .models import *

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Customer)
admin.site.register(CashSession)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Payment)
admin.site.register(DraftOrder)
admin.site.register(StockMovement)
@admin.register(Company)

class CompanyAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "phone",
        "email"
    )

admin.site.register(Refund)
admin.site.register(RefundItem)
admin.site.register(StockAdjustment)
admin.site.register(Supplier)
admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderItem)

# ─── NEW: Settings module models ───────────────────────────────────────────
admin.site.register(Store)
admin.site.register(POSSettings)
admin.site.register(InventorySettings)
admin.site.register(TaxSettings)
admin.site.register(ReceiptSettings)
admin.site.register(NotificationSettings)
admin.site.register(Notification)
admin.site.register(HardwareDevice)
admin.site.register(BarcodeSettings)
admin.site.register(CustomerGroup)
admin.site.register(CustomerSettings)
admin.site.register(ProductSettings)
admin.site.register(CustomField)
admin.site.register(SecuritySettings)
admin.site.register(LoginAttempt)
admin.site.register(TrustedDevice)
admin.site.register(AuditLog)
admin.site.register(BackupSettings)
admin.site.register(BackupRecord)
admin.site.register(DataManagementSettings)
admin.site.register(ReportSettings)
admin.site.register(ScheduledReport)
admin.site.register(AppearanceSettings)
admin.site.register(FeatureFlags)
admin.site.register(APIKey)
admin.site.register(Webhook)
admin.site.register(WebhookDelivery)
admin.site.register(EmailTemplate)
admin.site.register(SMSTemplate)
admin.site.register(ReceiptTemplate)
admin.site.register(AboutInfo)
admin.site.register(ErrorLog)
from rbac.models import Role as RBACRole
admin.site.register(RBACRole)
admin.site.register(UserProfile)
admin.site.register(Tax)
admin.site.register(PaymentMethod)
admin.site.register(Brand)
admin.site.register(Variant)
admin.site.register(VariantValue)
admin.site.register(AuthToken)
admin.site.register(OneTimePasscode)

# ── Phase 3: Accounting ──────────────────────────────────────────────────────
from accounting.models import (
    ChartOfAccount, JournalEntry, JournalEntryLine, ExpenseCategory, Expense
)
admin.site.register(ChartOfAccount)
admin.site.register(JournalEntry)
admin.site.register(JournalEntryLine)
admin.site.register(ExpenseCategory)
admin.site.register(Expense)

# ── Phase 3: HR ───────────────────────────────────────────────────────────────
from hr.models import (
    Department, Employee, Shift, Attendance,
    LeaveType, LeaveRequest, PayrollRun, PayrollEntry
)
admin.site.register(Department)
admin.site.register(Employee)
admin.site.register(Shift)
admin.site.register(Attendance)
admin.site.register(LeaveType)
admin.site.register(LeaveRequest)
admin.site.register(PayrollRun)
admin.site.register(PayrollEntry)

# ── Phase 3: Loyalty ─────────────────────────────────────────────────────────
from loyalty.models import (
    LoyaltyProgram, MembershipTier, LoyaltyTransaction,
    Coupon, Promotion
)
admin.site.register(LoyaltyProgram)
admin.site.register(MembershipTier)
admin.site.register(LoyaltyTransaction)
admin.site.register(Coupon)
admin.site.register(Promotion)

# ── Phase 3: Notifications ───────────────────────────────────────────────────
from operations.models import EmailQueue, SMSQueue, InAppNotification

admin.site.register(InAppNotification)
admin.site.register(EmailQueue)
admin.site.register(SMSQueue)

# ── Phase 3: Workflow ────────────────────────────────────────────────────────
from operations.models import ApprovalRule, ApprovalRequest
admin.site.register(ApprovalRule)
admin.site.register(ApprovalRequest)
