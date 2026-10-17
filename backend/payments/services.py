import re
import secrets
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from audit.models import AuditEvent
from audit.recorder import record
from pos.models import CashSession, Company, Customer, Order, Refund

from .models import (
    GiftCard,
    GiftCardTransaction,
    PaymentReconciliation,
    PaymentSettlement,
    ReconciliationLine,
    RefundCreditNote,
    RefundSettlement,
    StoreCredit,
    StoreCreditTransaction,
    TenderedPayment,
)

MONEY = Decimal("0.01")


def _tenant_currency(tenant):
    """Return the currency stored in the canonical tenant-owned company profile.

    Older tenants may predate company-profile provisioning.  In that case this
    creates the same persisted default profile used by the company settings API;
    subsequent payment records read that tenant-owned value rather than a
    payment-service constant.
    """
    company = Company.objects.filter(tenant=tenant).order_by("id").first()
    if company is None:
        company = Company.objects.create(tenant=tenant, name=tenant.name, address="")
    if not company.currency or not str(company.currency).strip():
        raise ValueError("Configure the tenant company currency before processing payments.")
    return str(company.currency).strip().upper()


SUPPORTED_TENDERS = {
    TenderedPayment.TENDER_CASH,
    TenderedPayment.TENDER_CARD,
    TenderedPayment.TENDER_BANK,
    TenderedPayment.TENDER_GIFT_CARD,
    TenderedPayment.TENDER_STORE_CREDIT,
}


def _gen_code(prefix="GC"):
    return f"{prefix}-{secrets.token_hex(6).upper()}"


def _money(value, *, field="amount", allow_zero=False):
    try:
        amount = Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid decimal amount.") from exc
    if amount < 0 or (not allow_zero and amount == 0):
        raise ValueError(f"{field} must be greater than zero.")
    return amount


def _require_tenant_customer(tenant, customer):
    if customer is not None and customer.tenant_id != tenant.id:
        raise ValueError("Customer does not belong to the active tenant.")
    return customer


def _safe_reference(value, *, tender_type):
    reference = str(value or "").strip()[:120]
    # A card tender may carry a processor reference or masked label only; raw PAN-like data is rejected.
    if tender_type == TenderedPayment.TENDER_CARD and re.search(r"(?:\d[ -]?){12,19}", reference):
        raise ValueError("Raw card numbers must not be submitted or stored.")
    return reference


def _audit(*, tenant, actor, action, instance, summary, after):
    record(tenant=tenant, actor=actor, action=action, instance=instance, summary=summary, icon="wallet-cards", after=after)


@transaction.atomic
def issue_gift_card(*, tenant, initial_balance, customer=None, expires_at=None, user=None, code=None):
    amount = _money(initial_balance, field="initial_balance", allow_zero=True)
    _require_tenant_customer(tenant, customer)
    gift_card = GiftCard.objects.create(
        tenant=tenant,
        code=code or _gen_code(),
        initial_balance=amount,
        balance=amount,
        currency=_tenant_currency(tenant),
        issued_to=customer,
        expires_at=expires_at,
        created_by=user,
    )
    GiftCardTransaction.objects.create(tenant=tenant, gift_card=gift_card, kind=GiftCardTransaction.KIND_ISSUE, amount=amount, created_by=user)
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_CREATE, instance=gift_card, summary="Issued gift card", after={"amount": str(amount), "currency": gift_card.currency})
    return gift_card


@transaction.atomic
def topup_gift_card(*, tenant, gift_card_id, amount, user=None):
    amount = _money(amount)
    gift_card = GiftCard.objects.select_for_update().get(tenant=tenant, pk=gift_card_id, is_active=True)
    if gift_card.expires_at and gift_card.expires_at < timezone.localdate():
        raise ValueError("Gift card is expired.")
    gift_card.balance = _money(Decimal(gift_card.balance) + amount, allow_zero=True)
    gift_card.save(update_fields=["balance"])
    GiftCardTransaction.objects.create(tenant=tenant, gift_card=gift_card, kind=GiftCardTransaction.KIND_TOPUP, amount=amount, created_by=user)
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_UPDATE, instance=gift_card, summary="Topped up gift card", after={"amount": str(amount), "balance": str(gift_card.balance)})
    return gift_card


@transaction.atomic
def disable_gift_card(*, tenant, gift_card_id, user=None):
    gift_card = GiftCard.objects.select_for_update().get(tenant=tenant, pk=gift_card_id, is_active=True)
    gift_card.is_active = False
    gift_card.save(update_fields=["is_active"])
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_UPDATE, instance=gift_card, summary="Disabled gift card", after={"is_active": False})
    return gift_card


@transaction.atomic
def redeem_gift_card(*, tenant, code, amount, order, user=None):
    if order is None or order.tenant_id != tenant.id:
        raise ValueError("Gift-card redemption requires an active-tenant order context.")
    amount = _money(amount)
    gift_card = GiftCard.objects.select_for_update().get(tenant=tenant, code=str(code).strip(), is_active=True)
    if gift_card.expires_at and gift_card.expires_at < timezone.localdate():
        raise ValueError("Gift card is expired.")
    if amount > Decimal(gift_card.balance):
        raise ValueError("Gift card balance insufficient.")
    gift_card.balance = _money(Decimal(gift_card.balance) - amount, allow_zero=True)
    gift_card.save(update_fields=["balance"])
    GiftCardTransaction.objects.create(tenant=tenant, gift_card=gift_card, kind=GiftCardTransaction.KIND_REDEEM, amount=amount, order=order, created_by=user)
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_UPDATE, instance=gift_card, summary="Redeemed gift card", after={"amount": str(amount), "balance": str(gift_card.balance), "order_id": order.id})
    return gift_card


def _locked_wallet(*, tenant, customer):
    _require_tenant_customer(tenant, customer)
    try:
        wallet, _ = StoreCredit.objects.get_or_create(tenant=tenant, customer=customer, defaults={"currency": _tenant_currency(tenant)})
    except IntegrityError:
        wallet = StoreCredit.objects.get(tenant=tenant, customer=customer)
    return StoreCredit.objects.select_for_update().get(tenant=tenant, pk=wallet.pk)


@transaction.atomic
def issue_store_credit(*, tenant, customer, amount, order=None, note="", user=None):
    if order is not None and order.tenant_id != tenant.id:
        raise ValueError("Order does not belong to the active tenant.")
    amount = _money(amount)
    wallet = _locked_wallet(tenant=tenant, customer=customer)
    wallet.balance = _money(Decimal(wallet.balance) + amount, allow_zero=True)
    wallet.save(update_fields=["balance"])
    transaction_row = StoreCreditTransaction.objects.create(tenant=tenant, store_credit=wallet, kind=StoreCreditTransaction.KIND_ISSUE, amount=amount, order=order, note=(note or "")[:255], created_by=user)
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_CREATE, instance=transaction_row, summary="Issued store credit", after={"amount": str(amount), "balance": str(wallet.balance), "customer_id": customer.id})
    return transaction_row


@transaction.atomic
def redeem_store_credit(*, tenant, customer, amount, order=None, user=None):
    if order is None or order.tenant_id != tenant.id:
        raise ValueError("Store-credit redemption requires an active-tenant order context.")
    amount = _money(amount)
    wallet = _locked_wallet(tenant=tenant, customer=customer)
    if amount > Decimal(wallet.balance):
        raise ValueError("Store credit balance insufficient.")
    wallet.balance = _money(Decimal(wallet.balance) - amount, allow_zero=True)
    wallet.save(update_fields=["balance"])
    transaction_row = StoreCreditTransaction.objects.create(tenant=tenant, store_credit=wallet, kind=StoreCreditTransaction.KIND_REDEEM, amount=amount, order=order, created_by=user)
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_UPDATE, instance=transaction_row, summary="Redeemed store credit", after={"amount": str(amount), "balance": str(wallet.balance), "order_id": order.id})
    return transaction_row


def record_tender(*, settlement, order, tender_type, amount, reference="", user=None):
    return TenderedPayment.objects.create(
        tenant=order.tenant,
        settlement=settlement,
        order=order,
        tender_type=tender_type,
        amount=amount,
        currency=_tenant_currency(order.tenant),
        reference=reference,
        is_settled=True,
        created_by=user,
    )


@transaction.atomic
def settle_order(*, order, tenders, user=None):
    """The sole tender settlement authority invoked by canonical POS checkout."""
    # Do not join the nullable customer relation while locking on PostgreSQL;
    # locking an outer-joined nullable side is not supported by the database.
    order = Order.objects.select_for_update().get(tenant=order.tenant, pk=order.pk)
    tenant = order.tenant
    currency = _tenant_currency(tenant)
    if order.status != "draft":
        raise ValueError("Only draft orders can be settled.")
    if PaymentSettlement.objects.select_for_update().filter(tenant=tenant, order=order).exists():
        raise ValueError("This order already has a posted payment settlement.")
    if not isinstance(tenders, list) or not tenders:
        raise ValueError("At least one tender is required.")

    total = _money(order.total, field="order total", allow_zero=True)
    if total <= 0:
        raise ValueError("A positive order total is required to settle payment.")
    normalized = []
    for raw in tenders:
        try:
            tender_type = str(raw["tender_type"])
            amount = _money(raw["amount"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Each tender requires tender_type and amount.") from exc
        if tender_type not in SUPPORTED_TENDERS:
            raise ValueError(f"Unsupported tender type: {tender_type}.")
        normalized.append((tender_type, amount, _safe_reference(raw.get("reference", ""), tender_type=tender_type)))

    settlement = PaymentSettlement.objects.create(
        tenant=tenant,
        order=order,
        total_amount=total,
        currency=currency,
        idempotency_key=order.idempotency_key,
        settled_by=user,
    )
    paid = Decimal("0.00")
    change = Decimal("0.00")
    for tender_type, tendered_amount, reference in normalized:
        remaining = total - paid
        if remaining <= 0:
            raise ValueError("Tenders exceed the amount due.")
        applied = min(tendered_amount, remaining)
        if tendered_amount > remaining and tender_type != TenderedPayment.TENDER_CASH:
            raise ValueError("Non-cash tender cannot exceed the remaining balance.")
        if tender_type == TenderedPayment.TENDER_GIFT_CARD:
            redeem_gift_card(tenant=tenant, code=reference, amount=applied, order=order, user=user)
        elif tender_type == TenderedPayment.TENDER_STORE_CREDIT:
            if not order.customer:
                raise ValueError("Store credit needs a customer.")
            redeem_store_credit(tenant=tenant, customer=order.customer, amount=applied, order=order, user=user)
        record_tender(settlement=settlement, order=order, tender_type=tender_type, amount=applied, reference=reference, user=user)
        paid += applied
        if tendered_amount > applied:
            change += tendered_amount - applied

    if paid != total:
        raise ValueError("Tender total must exactly cover the order total.")
    order.amount_received = _money(paid + change, allow_zero=True)
    order.change_amount = _money(change, allow_zero=True)
    order.transition_to("paid")
    order.save(update_fields=["amount_received", "change_amount"])
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_CREATE, instance=settlement, summary="Settled POS payment", after={"order_id": order.id, "amount": str(total), "currency": currency, "tender_count": len(normalized)})
    # Accounting receives durable source events only. The central accounting engine decides whether a
    # configured tenant rule exists; an absent rule becomes a visible exception rather than an invented entry.
    from accounting.services import emit_accounting_event

    net_sales = _money(Decimal(order.subtotal) - Decimal(order.discount), field="net sales", allow_zero=True)
    if net_sales > 0:
        emit_accounting_event(
            tenant=tenant,
            source_domain="pos",
            event_type="pos_sale_net",
            source_id=str(order.id),
            event_date=order.created_at.date(),
            amount=net_sales,
            currency=currency,
            source_reference=order.order_number,
            payload={"order_id": order.id, "settlement_id": settlement.id, "order_total": str(order.total)},
            user=user,
        )
    if Decimal(order.tax) > 0:
        emit_accounting_event(
            tenant=tenant,
            source_domain="pos",
            event_type="pos_sale_tax",
            source_id=str(order.id),
            event_date=order.created_at.date(),
            amount=order.tax,
            currency=currency,
            source_reference=order.order_number,
            payload={"order_id": order.id, "settlement_id": settlement.id},
            user=user,
        )
    for tender in settlement.tenders.all():
        emit_accounting_event(
            tenant=tenant,
            source_domain="payments",
            event_type="payment_tender",
            source_id=str(tender.id),
            event_date=settlement.settled_at.date(),
            amount=tender.amount,
            currency=tender.currency,
            source_reference=f"{order.order_number} · {tender.tender_type}",
            payload={"order_id": order.id, "settlement_id": settlement.id, "tender_type": tender.tender_type},
            user=user,
        )
    return order


@transaction.atomic
def record_refund_settlement(*, refund, user=None, method=RefundSettlement.METHOD_RECORDED, cash_amount=Decimal("0")):
    """Record the payment-side counterpart of a canonical POS refund without claiming provider execution."""
    refund = Refund.objects.select_for_update().select_related("order").get(tenant=refund.tenant, pk=refund.pk)
    existing = RefundSettlement.objects.select_for_update().filter(tenant=refund.tenant, refund=refund).first()
    if existing:
        return existing
    settlement = PaymentSettlement.objects.filter(tenant=refund.tenant, order=refund.order).first()
    cash_amount = _money(cash_amount, field="cash_amount", allow_zero=True)
    total_amount = _money(refund.total_amount, allow_zero=True)
    if cash_amount > total_amount:
        raise ValueError("cash_amount cannot exceed the refund amount.")
    refund_settlement = RefundSettlement.objects.create(
        tenant=refund.tenant,
        refund=refund,
        original_settlement=settlement,
        amount=total_amount,
        cash_amount=cash_amount,
        currency=_tenant_currency(refund.tenant),
        method=method,
        reference=_gen_code("RF"),
        created_by=user,
    )
    _audit(tenant=refund.tenant, actor=user, action=AuditEvent.ACTION_REFUND, instance=refund_settlement, summary="Recorded POS refund settlement", after={"refund_id": refund.id, "amount": str(refund_settlement.amount), "cash_amount": str(refund_settlement.cash_amount), "method": refund_settlement.method})
    from accounting.models import AccountingEvent
    from accounting.services import emit_accounting_event

    original = AccountingEvent.objects.filter(
        tenant=refund.tenant,
        source_domain="pos",
        event_type="pos_sale_net",
        source_id=str(refund.order_id),
    ).first()
    net_refund = _money(Decimal(refund.total_amount) - Decimal(refund.tax), field="net refund", allow_zero=True)
    if net_refund > 0:
        emit_accounting_event(
            tenant=refund.tenant,
            source_domain="pos",
            event_type="pos_refund_net",
            source_id=str(refund.id),
            event_date=refund.created_at.date(),
            amount=net_refund,
            currency=refund_settlement.currency,
            source_reference=f"Refund {refund.id} for {refund.order.order_number}",
            payload={"refund_id": refund.id, "order_id": refund.order_id, "refund_settlement_id": refund_settlement.id},
            reversal_of=original,
            user=user,
        )
    if Decimal(refund.tax) > 0:
        original_tax = AccountingEvent.objects.filter(
            tenant=refund.tenant,
            source_domain="pos",
            event_type="pos_sale_tax",
            source_id=str(refund.order_id),
        ).first()
        emit_accounting_event(
            tenant=refund.tenant,
            source_domain="pos",
            event_type="pos_refund_tax",
            source_id=str(refund.id),
            event_date=refund.created_at.date(),
            amount=refund.tax,
            currency=refund_settlement.currency,
            source_reference=f"Tax refund {refund.id} for {refund.order.order_number}",
            payload={"refund_id": refund.id, "order_id": refund.order_id, "refund_settlement_id": refund_settlement.id},
            reversal_of=original_tax,
            user=user,
        )
    original_settlement_event = AccountingEvent.objects.filter(
        tenant=refund.tenant,
        source_domain="payments",
        event_type="payment_tender",
        payload__order_id=refund.order_id,
    ).order_by("id").first()
    emit_accounting_event(
        tenant=refund.tenant,
        source_domain="payments",
        event_type="refund_settlement",
        source_id=str(refund_settlement.id),
        event_date=refund_settlement.created_at.date(),
        amount=refund_settlement.amount,
        currency=refund_settlement.currency,
        source_reference=refund_settlement.reference,
        payload={"refund_id": refund.id, "order_id": refund.order_id, "refund_settlement_id": refund_settlement.id, "method": refund_settlement.method},
        reversal_of=original_settlement_event,
        user=user,
    )
    return refund_settlement


@transaction.atomic
def refund_as_store_credit(*, tenant, refund, customer, user=None):
    if refund.tenant_id != tenant.id:
        raise ValueError("Refund does not belong to the active tenant.")
    _require_tenant_customer(tenant, customer)
    refund = Refund.objects.select_for_update().get(tenant=tenant, pk=refund.pk)
    credit_note = RefundCreditNote.objects.select_for_update().filter(tenant=tenant, refund=refund).first()
    if credit_note:
        return credit_note
    settlement = record_refund_settlement(refund=refund, user=user)
    credit_note = RefundCreditNote.objects.create(tenant=tenant, refund=refund, customer=customer, amount=refund.total_amount, code=_gen_code("CN"))
    issue_store_credit(tenant=tenant, customer=customer, amount=refund.total_amount, order=refund.order, note=f"Credit note {credit_note.code}", user=user)
    settlement.method = RefundSettlement.METHOD_STORE_CREDIT
    settlement.save(update_fields=["method"])
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_REFUND, instance=credit_note, summary="Converted refund to store credit", after={"refund_id": refund.id, "amount": str(refund.total_amount)})
    return credit_note


@transaction.atomic
def reconcile_session(*, tenant, session_id, counted_lines, note="", user=None):
    session = CashSession.objects.select_for_update().get(tenant=tenant, pk=session_id)
    if PaymentReconciliation.objects.select_for_update().filter(tenant=tenant, session=session).exists():
        raise ValueError("This session already has a payment reconciliation.")
    if not isinstance(counted_lines, list) or not counted_lines:
        raise ValueError("At least one counted tender line is required.")
    reconciliation = PaymentReconciliation.objects.create(tenant=tenant, session=session, created_by=user, note=(note or "")[:2000])
    expected_total = Decimal("0.00")
    counted_total = Decimal("0.00")
    seen_types = set()
    for raw in counted_lines:
        tender_type = str(raw.get("tender_type", ""))
        if tender_type not in SUPPORTED_TENDERS or tender_type in seen_types:
            raise ValueError("Each supported tender type may appear only once in reconciliation.")
        seen_types.add(tender_type)
        counted = _money(raw.get("counted_amount"), field="counted_amount", allow_zero=True)
        expected = TenderedPayment.objects.filter(tenant=tenant, order__session=session, tender_type=tender_type, is_settled=True).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        expected = _money(expected, allow_zero=True)
        ReconciliationLine.objects.create(tenant=tenant, reconciliation=reconciliation, tender_type=tender_type, expected_amount=expected, counted_amount=counted, variance=counted - expected, note=str(raw.get("note", ""))[:255])
        expected_total += expected
        counted_total += counted
    reconciliation.expected_total = _money(expected_total, allow_zero=True)
    reconciliation.counted_total = _money(counted_total, allow_zero=True)
    reconciliation.variance = _money(counted_total - expected_total, allow_zero=True) if counted_total >= expected_total else (counted_total - expected_total).quantize(MONEY, rounding=ROUND_HALF_UP)
    reconciliation.status = PaymentReconciliation.STATUS_MATCHED if reconciliation.variance == 0 else PaymentReconciliation.STATUS_DISCREPANCY
    reconciliation.save(update_fields=["expected_total", "counted_total", "variance", "status"])
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_CREATE, instance=reconciliation, summary="Created payment reconciliation", after={"session_id": session.id, "expected": str(reconciliation.expected_total), "counted": str(reconciliation.counted_total), "variance": str(reconciliation.variance)})
    return reconciliation


@transaction.atomic
def close_reconciliation(*, tenant, reconciliation_id, user=None):
    reconciliation = PaymentReconciliation.objects.select_for_update().get(tenant=tenant, pk=reconciliation_id)
    if reconciliation.status == PaymentReconciliation.STATUS_CLOSED:
        return reconciliation
    if reconciliation.status != PaymentReconciliation.STATUS_MATCHED:
        raise ValueError("Only matched reconciliations can be closed.")
    reconciliation.status = PaymentReconciliation.STATUS_CLOSED
    reconciliation.closed_by = user
    reconciliation.closed_at = timezone.now()
    reconciliation.save(update_fields=["status", "closed_by", "closed_at"])
    _audit(tenant=tenant, actor=user, action=AuditEvent.ACTION_UPDATE, instance=reconciliation, summary="Closed payment reconciliation", after={"status": reconciliation.status, "variance": str(reconciliation.variance)})
    return reconciliation
