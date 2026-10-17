"""Canonical, tenant-owned double-entry accounting models."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


class AccountType(models.TextChoices):
    ASSET = "asset", "Asset"
    LIABILITY = "liability", "Liability"
    EQUITY = "equity", "Equity"
    REVENUE = "revenue", "Revenue"
    EXPENSE = "expense", "Expense"


class AccountingEventType(models.TextChoices):
    """Explicit accounting-relevant source components; account policy is configured per tenant."""

    POS_SALE_NET = "pos_sale_net", "POS sale — net revenue"
    POS_SALE_TAX = "pos_sale_tax", "POS sale — tax"
    PAYMENT_TENDER = "payment_tender", "Payment settlement — tender"
    POS_REFUND_NET = "pos_refund_net", "POS refund — net revenue"
    POS_REFUND_TAX = "pos_refund_tax", "POS refund — tax"
    REFUND_SETTLEMENT = "refund_settlement", "Refund settlement"
    GOODS_RECEIPT = "goods_receipt", "Goods receipt"
    PURCHASE_RETURN = "purchase_return", "Purchase return"
    EXPENSE_MANUAL = "expense_manual", "Approved expense — manual post"


class AccountingEventStatus(models.TextChoices):
    PENDING = "pending", "Pending posting"
    POSTED = "posted", "Posted"
    CONFIGURATION_REQUIRED = "configuration_required", "Accounting configuration required"
    POLICY_REQUIRED = "policy_required", "Accounting policy required"
    FAILED = "failed", "Needs attention"
    REVERSED = "reversed", "Reversed"


class ChartOfAccount(models.Model):
    """A tenant-local account. Posted history is preserved through PROTECT lines."""

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=AccountType.choices)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="accounting_unique_account_code_per_tenant"),
        ]

    def clean(self):
        if self.parent_id and self.parent_id == self.pk:
            raise ValidationError({"parent": "An account cannot be its own parent."})
        if self.parent_id and self.parent.tenant_id != self.tenant_id:
            raise ValidationError({"parent": "The parent account must belong to the active tenant."})

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def balance(self):
        lines = self.journal_lines.filter(entry__status=JournalEntry.STATUS_POSTED).aggregate(
            debits=Sum("debit"), credits=Sum("credit")
        )
        debits = lines["debits"] or Decimal("0.00")
        credits = lines["credits"] or Decimal("0.00")
        if self.type in [AccountType.ASSET, AccountType.EXPENSE]:
            return debits - credits
        return credits - debits


class FinancialStatementRole(models.TextChoices):
    """Explicit presentation roles; no role is inferred from an account name."""

    COGS = "cogs", "Cost of goods sold"
    OPERATING_EXPENSE = "operating_expense", "Operating expense"
    OTHER_INCOME = "other_income", "Other income"
    OTHER_EXPENSE = "other_expense", "Other expense"
    CASH_BANK = "cash_bank", "Cash or bank"
    RETAINED_EARNINGS = "retained_earnings", "Retained earnings"


class FinancialAccountMapping(models.Model):
    """A tenant-approved statement role for one account, audited through the existing accounting views."""

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="accounting_financial_mappings")
    account = models.ForeignKey("ChartOfAccount", on_delete=models.PROTECT, related_name="financial_mappings")
    role = models.CharField(max_length=32, choices=FinancialStatementRole.choices)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_financial_account_mappings")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="updated_financial_account_mappings")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role", "account__code", "id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "account"], name="accounting_unique_financial_role_account"),
        ]
        indexes = [models.Index(fields=["tenant", "role", "is_active"], name="acct_fin_map_role_ix")]

    def clean(self):
        if self.account_id and self.account.tenant_id != self.tenant_id:
            raise ValidationError({"account": "The mapped account must belong to the active tenant."})
        required_types = {
            FinancialStatementRole.COGS: AccountType.EXPENSE,
            FinancialStatementRole.OPERATING_EXPENSE: AccountType.EXPENSE,
            FinancialStatementRole.OTHER_EXPENSE: AccountType.EXPENSE,
            FinancialStatementRole.OTHER_INCOME: AccountType.REVENUE,
            FinancialStatementRole.CASH_BANK: AccountType.ASSET,
            FinancialStatementRole.RETAINED_EARNINGS: AccountType.EQUITY,
        }
        if self.account_id and self.account.type != required_types[self.role]:
            raise ValidationError({"account": f"{self.get_role_display()} requires a {required_types[self.role]} account."})


class AccountingPeriod(models.Model):
    """A tenant-owned posting period. Closed periods are immutable to new postings."""

    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_CLOSED, "Closed")]

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    code = models.CharField(max_length=30)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="closed_accounting_periods")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="accounting_unique_period_code_per_tenant"),
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="accounting_period_end_not_before_start"),
        ]

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError({"end_date": "Period end date must be on or after its start date."})

    def __str__(self):
        return f"{self.code} ({self.start_date} – {self.end_date})"


class PostingRule(models.Model):
    """Tenant-approved two-sided mapping for one explicit accounting event component."""

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="accounting_posting_rules")
    event_type = models.CharField(max_length=40, choices=AccountingEventType.choices)
    source_key = models.CharField(max_length=40, blank=True, help_text="Optional payload key, such as tender_type.")
    source_value = models.CharField(max_length=40, blank=True, help_text="Optional payload value matched with source_key.")
    name = models.CharField(max_length=160)
    debit_account = models.ForeignKey("ChartOfAccount", on_delete=models.PROTECT, related_name="posting_rules_as_debit")
    credit_account = models.ForeignKey("ChartOfAccount", on_delete=models.PROTECT, related_name="posting_rules_as_credit")
    currency = models.CharField(max_length=10, default="USD")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_accounting_posting_rules")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="updated_accounting_posting_rules")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_type", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "event_type", "source_key", "source_value"], name="accounting_unique_rule_slot_per_tenant"),
            models.CheckConstraint(condition=~models.Q(debit_account=models.F("credit_account")), name="accounting_posting_rule_accounts_differ"),
        ]

    def clean(self):
        if bool(self.source_key) != bool(self.source_value):
            raise ValidationError({"source_key": "Source key and source value must be supplied together."})
        if self.debit_account_id and self.debit_account.tenant_id != self.tenant_id:
            raise ValidationError({"debit_account": "The debit account must belong to the active tenant."})
        if self.credit_account_id and self.credit_account.tenant_id != self.tenant_id:
            raise ValidationError({"credit_account": "The credit account must belong to the active tenant."})

    def __str__(self):
        return f"{self.get_event_type_display()}: {self.name}"


class JournalEntry(models.Model):
    """A tenant-local journal header. A posted entry is immutable and correctable only by reversal."""

    STATUS_DRAFT = "draft"
    STATUS_POSTED = "posted"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_POSTED, "Posted")]

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    reference = models.CharField(max_length=60)
    date = models.DateField()
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_journal_entries")
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="posted_journal_entries")
    posted_at = models.DateTimeField(null=True, blank=True)
    reversal_of = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal")
    created_at = models.DateTimeField(auto_now_add=True)
    is_auto_posted = models.BooleanField(default=False, help_text="Reserved for a future, idempotent upstream posting integration.")

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "reference"], name="accounting_unique_journal_reference_per_tenant"),
        ]

    def __str__(self):
        return f"JE-{self.reference} ({self.date})"

    @property
    def is_balanced(self):
        agg = self.lines.aggregate(d=Sum("debit"), c=Sum("credit"))
        return (agg["d"] or Decimal("0.00")) == (agg["c"] or Decimal("0.00"))


class AccountingEvent(models.Model):
    """One durable, tenant-local accounting event per operational source component."""

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="accounting_events")
    source_domain = models.CharField(max_length=40)
    event_type = models.CharField(max_length=40, choices=AccountingEventType.choices)
    source_id = models.CharField(max_length=64)
    source_reference = models.CharField(max_length=120, blank=True)
    event_date = models.DateField()
    currency = models.CharField(max_length=10, default="USD")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=32, choices=AccountingEventStatus.choices, default=AccountingEventStatus.PENDING)
    rule = models.ForeignKey(PostingRule, null=True, blank=True, on_delete=models.PROTECT, related_name="events")
    journal_entry = models.OneToOneField("JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="accounting_event")
    reversal_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal_events")
    payload = models.JSONField(default=dict, blank=True)
    exception_reason = models.TextField(blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="posted_accounting_events")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-event_date", "-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_domain", "event_type", "source_id"],
                name="accounting_unique_event_identity_per_tenant",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="accounting_event_amount_positive"),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "event_date"], name="acct_evt_stat_date_ix"),
            models.Index(fields=["tenant", "source_domain", "source_id"], name="acct_evt_source_ix"),
        ]

    def __str__(self):
        return f"{self.source_domain}:{self.event_type}:{self.source_id}"


class JournalEntryLine(models.Model):
    """A tenant-owned debit or credit line; cross-tenant references are rejected by services."""

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(ChartOfAccount, on_delete=models.PROTECT, related_name="journal_lines")
    description = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)),
                name="accounting_line_has_exactly_one_positive_side",
            ),
        ]

    def __str__(self):
        return f"DR {self.debit} / CR {self.credit} — {self.account}"


class ExpenseCategory(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Expense Categories"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="accounting_unique_expense_category_per_tenant"),
        ]

    def __str__(self):
        return self.name


class Expense(models.Model):
    """An expense approval record. It is not a journal until a permitted user manually posts one."""

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.TextField()
    date = models.DateField()
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses_paid")
    receipt_image = models.ImageField(upload_to="receipts/", null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDING)
    journal_entry = models.ForeignKey(JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="accounting_expense_amount_positive"),
        ]

    def __str__(self):
        return f"{self.category} — {self.amount} ({self.date})"
