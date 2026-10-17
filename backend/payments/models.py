from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q


class GiftCard(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    code = models.CharField(max_length=32, unique=True)
    initial_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=10, default="USD")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateField(null=True, blank=True)
    issued_to = models.ForeignKey("pos.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="gift_cards")
    issued_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class GiftCardTransaction(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    KIND_ISSUE = "issue"
    KIND_TOPUP = "topup"
    KIND_REDEEM = "redeem"
    KIND_VOID = "void"
    KIND_CHOICES = [(KIND_ISSUE, "Issue"), (KIND_TOPUP, "Top-up"), (KIND_REDEEM, "Redeem"), (KIND_VOID, "Void")]
    gift_card = models.ForeignKey(GiftCard, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    order = models.ForeignKey("pos.Order", null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class StoreCredit(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    customer = models.ForeignKey("pos.Customer", on_delete=models.CASCADE, related_name="store_credits")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=10, default="USD")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["customer"], name="unique_customer_storecredit")]


class StoreCreditTransaction(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    KIND_ISSUE = "issue"
    KIND_ADJUST = "adjust"
    KIND_REDEEM = "redeem"
    KIND_EXPIRE = "expire"
    KIND_CHOICES = [(KIND_ISSUE, "Issue"), (KIND_ADJUST, "Adjust"), (KIND_REDEEM, "Redeem"), (KIND_EXPIRE, "Expire")]
    store_credit = models.ForeignKey(StoreCredit, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    order = models.ForeignKey("pos.Order", null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class PaymentSettlement(models.Model):
    """The single posted settlement record for a POS order."""

    STATUS_SETTLED = "settled"
    STATUS_CHOICES = [(STATUS_SETTLED, "Settled")]

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="payment_settlements")
    order = models.OneToOneField("pos.Order", on_delete=models.PROTECT, related_name="payment_settlement")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SETTLED)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    settled_at = models.DateTimeField(auto_now_add=True)
    settled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payment_settlements")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False) & ~Q(idempotency_key=""),
                name="unique_payment_settlement_idempotency_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["tenant", "order"],
                name="unique_payment_settlement_per_order",
            ),
        ]


class TenderedPayment(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """An immutable, settled tender allocation for an order."""

    TENDER_CASH = "cash"
    TENDER_CARD = "card"
    TENDER_BANK = "bank"
    TENDER_GIFT_CARD = "gift_card"
    TENDER_STORE_CREDIT = "store_credit"
    TENDER_LOYALTY = "loyalty"
    TENDER_WALLET = "wallet"
    TENDER_CHOICES = [(TENDER_CASH, "Cash"), (TENDER_CARD, "Card"), (TENDER_BANK, "Bank"),
                      (TENDER_GIFT_CARD, "Gift card"), (TENDER_STORE_CREDIT, "Store credit"),
                      (TENDER_LOYALTY, "Loyalty points"), (TENDER_WALLET, "Wallet")]
    settlement = models.ForeignKey(PaymentSettlement, null=True, blank=True, on_delete=models.SET_NULL, related_name="tenders")
    order = models.ForeignKey("pos.Order", on_delete=models.CASCADE, related_name="tenders")
    tender_type = models.CharField(max_length=20, choices=TENDER_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    reference = models.CharField(max_length=120, blank=True)
    is_settled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [models.Index(fields=["tenant", "created_at"]), models.Index(fields=["tenant", "tender_type"])]


class RefundSettlement(models.Model):
    """Compensating financial record for a canonical POS refund, not a second refund engine."""

    METHOD_RECORDED = "recorded"
    METHOD_STORE_CREDIT = "store_credit"
    METHOD_PROVIDER = "provider"
    METHOD_CHOICES = [
        (METHOD_RECORDED, "Recorded refund"),
        (METHOD_STORE_CREDIT, "Store credit"),
        (METHOD_PROVIDER, "Provider refund"),
    ]
    STATUS_RECORDED = "recorded"
    STATUS_CHOICES = [(STATUS_RECORDED, "Recorded")]

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="refund_settlements")
    refund = models.OneToOneField("pos.Refund", on_delete=models.PROTECT, related_name="payment_settlement")
    original_settlement = models.ForeignKey(PaymentSettlement, null=True, blank=True, on_delete=models.PROTECT, related_name="refund_settlements")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Cash-session expected balances use this explicit component only.  A
    # recorded/provider/store-credit refund is not assumed to have left a cash drawer.
    cash_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=10, default="USD")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_RECORDED)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RECORDED)
    reference = models.CharField(max_length=32, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class PaymentReconciliation(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_OPEN = "open"
    STATUS_MATCHED = "matched"
    STATUS_DISCREPANCY = "discrepancy"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_MATCHED, "Matched"), (STATUS_DISCREPANCY, "Discrepancy"), (STATUS_CLOSED, "Closed")]
    session = models.ForeignKey("pos.CashSession", on_delete=models.CASCADE, related_name="reconciliations")
    expected_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    counted_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    variance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_payment_reconciliations")
    created_at = models.DateTimeField(auto_now_add=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="closed_payment_reconciliations")
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "session"], name="unique_payment_reconciliation_per_session")]


class ReconciliationLine(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    reconciliation = models.ForeignKey(PaymentReconciliation, on_delete=models.CASCADE, related_name="lines")
    tender_type = models.CharField(max_length=20)
    expected_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    counted_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    variance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    note = models.CharField(max_length=255, blank=True)


class RefundCreditNote(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    refund = models.ForeignKey("pos.Refund", on_delete=models.CASCADE, related_name="credit_notes")
    customer = models.ForeignKey("pos.Customer", null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    code = models.CharField(max_length=32, unique=True)
    is_redeemed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "refund"], name="unique_refund_credit_note_per_tenant")]


class ProviderPaymentOperation(models.Model):
    """Tenant-owned bridge between one draft POS order and one provider payment object."""

    PROVIDER_STRIPE = "stripe"
    PROVIDER_CHOICES = [(PROVIDER_STRIPE, "Stripe")]

    STATUS_PENDING = "pending"
    STATUS_REQUIRES_ACTION = "requires_action"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_VERIFICATION_REQUIRED = "verification_required"
    STATUS_EXCEPTION = "exception"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_REQUIRES_ACTION, "Requires action"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_VERIFICATION_REQUIRED, "Verification required"),
        (STATUS_EXCEPTION, "Exception"),
    ]

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="provider_payment_operations")
    order = models.OneToOneField("pos.Order", on_delete=models.PROTECT, related_name="provider_payment_operation")
    provider = models.CharField(max_length=40, default=PROVIDER_STRIPE)
    provider_payment_id = models.CharField(max_length=160, blank=True)
    provider_status = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    idempotency_key = models.CharField(max_length=128)
    failure_code = models.CharField(max_length=80, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="provider_payment_operations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"]),
            models.Index(fields=["provider", "provider_payment_id"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "idempotency_key"], name="unique_provider_operation_idempotency_per_tenant"),
            models.UniqueConstraint(
                fields=["provider", "provider_payment_id"],
                condition=~Q(provider_payment_id=""),
                name="unique_provider_payment_reference",
            ),
        ]


class ProviderWebhookEvent(models.Model):
    """Minimal, replay-safe record of a verified provider event; raw payloads are never stored."""

    STATE_RECEIVED = "received"
    STATE_PROCESSED = "processed"
    STATE_IGNORED = "ignored"
    STATE_FAILED = "failed"
    STATE_CHOICES = [
        (STATE_RECEIVED, "Received"),
        (STATE_PROCESSED, "Processed"),
        (STATE_IGNORED, "Ignored"),
        (STATE_FAILED, "Failed"),
    ]

    tenant = models.ForeignKey("saas.Tenant", null=True, blank=True, on_delete=models.SET_NULL, related_name="provider_webhook_events")
    operation = models.ForeignKey(ProviderPaymentOperation, null=True, blank=True, on_delete=models.SET_NULL, related_name="webhook_events")
    provider = models.CharField(max_length=40)
    provider_event_id = models.CharField(max_length=160)
    event_type = models.CharField(max_length=120)
    processing_state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_RECEIVED)
    error_reason = models.CharField(max_length=255, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["tenant", "processing_state", "received_at"])]
        constraints = [
            models.UniqueConstraint(fields=["provider", "provider_event_id"], name="unique_provider_webhook_event"),
        ]


class ProviderRefundOperation(models.Model):
    """Provider-side execution reference for one canonical POS refund, never a standalone refund ledger."""

    STATUS_PENDING = "pending"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_VERIFICATION_REQUIRED = "verification_required"
    STATUS_EXCEPTION = "exception"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_VERIFICATION_REQUIRED, "Verification required"),
        (STATUS_EXCEPTION, "Exception"),
    ]

    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="provider_refund_operations")
    refund = models.OneToOneField("pos.Refund", on_delete=models.PROTECT, related_name="provider_refund_operation")
    payment_operation = models.ForeignKey(ProviderPaymentOperation, on_delete=models.PROTECT, related_name="refund_operations")
    provider = models.CharField(max_length=40, default=ProviderPaymentOperation.PROVIDER_STRIPE)
    provider_refund_id = models.CharField(max_length=160, blank=True)
    provider_status = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    idempotency_key = models.CharField(max_length=128)
    failure_code = models.CharField(max_length=80, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="provider_refund_operations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"]),
            models.Index(fields=["provider", "provider_refund_id"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "idempotency_key"], name="unique_provider_refund_idempotency_per_tenant"),
            models.UniqueConstraint(
                fields=["provider", "provider_refund_id"],
                condition=~Q(provider_refund_id=""),
                name="unique_provider_refund_reference",
            ),
        ]
