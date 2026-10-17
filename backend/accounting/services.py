"""Transactional services for the canonical tenant-safe accounting ledger."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from audit.recorder import record

from .models import (
    AccountingEvent,
    AccountingEventStatus,
    AccountingEventType,
    AccountingPeriod,
    ChartOfAccount,
    Expense,
    JournalEntry,
    JournalEntryLine,
    PostingRule,
)

MONEY = Decimal("0.01")
ZERO = Decimal("0.00")


class AccountingValidationError(ValueError):
    """A business-rule failure intentionally suitable for a 400 API response."""


def accounting_date(value, *, field="date"):
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value
    parsed = parse_date(str(value or ""))
    if parsed is None:
        raise AccountingValidationError(f"{field} must be an ISO date in YYYY-MM-DD format.")
    return parsed


def money(value, *, field="amount", allow_zero=False):
    try:
        amount = Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AccountingValidationError(f"{field} must be a valid decimal amount.") from exc
    if amount < ZERO or (not allow_zero and amount == ZERO):
        raise AccountingValidationError(f"{field} must be greater than zero.")
    return amount


def _audit(*, tenant, actor, action, instance, summary, after, request=None):
    record(tenant=tenant, actor=actor, action=action, instance=instance, request=request, summary=summary, icon="book-open-check", after=after)


def _normalise_lines(*, tenant, raw_lines):
    if not isinstance(raw_lines, list) or len(raw_lines) < 2:
        raise AccountingValidationError("A journal entry requires at least two lines.")
    normalised = []
    account_ids = []
    for index, raw in enumerate(raw_lines, start=1):
        if not isinstance(raw, dict):
            raise AccountingValidationError(f"Journal line {index} must be an object.")
        try:
            account_ids.append(int(raw["account"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise AccountingValidationError(f"Journal line {index} requires a valid account.") from exc
    accounts = {account.id: account for account in ChartOfAccount.objects.select_for_update().filter(tenant=tenant, id__in=account_ids)}
    if len(accounts) != len(set(account_ids)):
        raise AccountingValidationError("Every journal line account must belong to the active tenant.")
    total_debit = ZERO
    total_credit = ZERO
    for index, raw in enumerate(raw_lines, start=1):
        account = accounts[int(raw["account"])]
        if not account.is_active:
            raise AccountingValidationError(f"Journal line {index} uses an inactive account.")
        debit = money(raw.get("debit", ZERO), field=f"line {index} debit", allow_zero=True)
        credit = money(raw.get("credit", ZERO), field=f"line {index} credit", allow_zero=True)
        if (debit > ZERO) == (credit > ZERO):
            raise AccountingValidationError(f"Journal line {index} must have exactly one positive debit or credit amount.")
        total_debit += debit
        total_credit += credit
        normalised.append({"account": account, "description": str(raw.get("description", "")).strip()[:255], "debit": debit, "credit": credit})
    if total_debit != total_credit:
        raise AccountingValidationError("Journal entry is not balanced: total debits must equal total credits.")
    return normalised, total_debit


def _period_for_date(*, tenant, entry_date, lock=False):
    qs = AccountingPeriod.objects.filter(tenant=tenant, start_date__lte=entry_date, end_date__gte=entry_date)
    if lock:
        qs = qs.select_for_update()
    return qs.first()


def _assert_open_period(*, tenant, entry_date):
    period = _period_for_date(tenant=tenant, entry_date=entry_date, lock=True)
    if period and period.status == AccountingPeriod.STATUS_CLOSED:
        raise AccountingValidationError(f"The accounting period {period.code} is closed for {entry_date}.")
    return period


def _next_reversal_reference(*, tenant, entry):
    base = f"REV-{entry.reference}"[:60]
    candidate = base
    suffix = 2
    while JournalEntry.objects.filter(tenant=tenant, reference=candidate).exists():
        suffix_text = f"-{suffix}"
        candidate = f"{base[:60 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _event_reference(event):
    return f"AUTO-{event.id}"[:60]


def _event_description(event):
    label = event.get_event_type_display()
    source = event.source_reference or f"{event.source_domain} {event.source_id}"
    return f"{label}: {source}"[:2000]


@transaction.atomic
def create_accounting_event(*, tenant, source_domain, event_type, source_id, event_date, amount, currency="USD", source_reference="", payload=None, reversal_of=None, user=None, request=None):
    if event_type not in AccountingEventType.values:
        raise AccountingValidationError("Unsupported accounting event type.")
    event_date = accounting_date(event_date, field="event_date")
    amount = money(amount, field="event amount")
    source_domain = str(source_domain or "").strip()[:40]
    source_id = str(source_id or "").strip()[:64]
    if not source_domain or not source_id:
        raise AccountingValidationError("Accounting events require source_domain and source_id.")
    if reversal_of and reversal_of.tenant_id != tenant.id:
        raise AccountingValidationError("The reversal event must belong to the active tenant.")
    defaults = {"source_reference": str(source_reference or "").strip()[:120], "event_date": event_date, "amount": amount, "currency": str(currency or "USD").upper()[:10], "payload": payload or {}, "reversal_of": reversal_of}
    try:
        event, created = AccountingEvent.objects.get_or_create(tenant=tenant, source_domain=source_domain, event_type=event_type, source_id=source_id, defaults=defaults)
    except IntegrityError:
        event = AccountingEvent.objects.get(tenant=tenant, source_domain=source_domain, event_type=event_type, source_id=source_id)
        created = False
    if created:
        _audit(tenant=tenant, actor=user, action="create", instance=event, request=request, summary="Recorded accounting source event", after={"source_domain": event.source_domain, "event_type": event.event_type, "source_id": event.source_id, "amount": str(event.amount), "currency": event.currency})
    return event, created


@transaction.atomic
def post_accounting_event(*, tenant, event_id, user=None, request=None, debit_account_id=None, credit_account_id=None, reference=None, description=None):
    event = AccountingEvent.objects.select_for_update().get(tenant=tenant, pk=event_id)
    if event.status == AccountingEventStatus.POSTED:
        return event
    if event.status == AccountingEventStatus.REVERSED:
        raise AccountingValidationError("A reversed accounting event cannot be posted again.")
    _assert_open_period(tenant=tenant, entry_date=event.event_date)
    if debit_account_id is None or credit_account_id is None:
        rules = PostingRule.objects.select_for_update().filter(tenant=tenant, event_type=event.event_type, is_active=True).select_related("debit_account", "credit_account")
        rule = None
        for candidate in rules.exclude(source_key="").order_by("id"):
            if str((event.payload or {}).get(candidate.source_key, "")) == candidate.source_value:
                rule = candidate
                break
        if rule is None:
            rule = rules.filter(source_key="", source_value="").order_by("id").first()
        if rule is None:
            event.status = AccountingEventStatus.CONFIGURATION_REQUIRED
            event.exception_reason = "No active accounting posting rule is configured for this event type."
            event.rule = None
            event.save(update_fields=["status", "exception_reason", "rule", "updated_at"])
            _audit(tenant=tenant, actor=user, action="update", instance=event, request=request, summary="Accounting event requires configuration", after={"status": event.status, "reason": event.exception_reason, "event_type": event.event_type})
            return event
        debit_account_id, credit_account_id = rule.debit_account_id, rule.credit_account_id
        event.rule = rule
    else:
        event.rule = None
    accounts = {account.id: account for account in ChartOfAccount.objects.select_for_update().filter(tenant=tenant, id__in=[debit_account_id, credit_account_id], is_active=True)}
    if len(accounts) != 2 or debit_account_id == credit_account_id:
        raise AccountingValidationError("A posting requires two different active accounts in the active tenant.")
    entry_reference = str(reference or _event_reference(event)).strip()[:60]
    if not entry_reference:
        raise AccountingValidationError("A posting reference is required.")
    existing = JournalEntry.objects.select_for_update().filter(tenant=tenant, reference=entry_reference).first()
    if existing:
        if event.journal_entry_id == existing.id:
            event.status = AccountingEventStatus.POSTED
            event.save(update_fields=["status", "updated_at"])
            return event
        raise AccountingValidationError("An unrelated journal already uses this posting reference.")
    entry = JournalEntry.objects.create(tenant=tenant, reference=entry_reference, date=event.event_date, description=str(description or _event_description(event)).strip()[:2000], status=JournalEntry.STATUS_DRAFT, created_by=user, is_auto_posted=event.event_type != AccountingEventType.EXPENSE_MANUAL)
    JournalEntryLine.objects.bulk_create([
        JournalEntryLine(tenant=tenant, entry=entry, account=accounts[debit_account_id], description=_event_description(event)[:255], debit=event.amount, credit=ZERO),
        JournalEntryLine(tenant=tenant, entry=entry, account=accounts[credit_account_id], description=_event_description(event)[:255], debit=ZERO, credit=event.amount),
    ])
    entry = post_journal_entry(tenant=tenant, entry_id=entry.id, user=user, request=request)
    event.journal_entry = entry
    event.status = AccountingEventStatus.POSTED
    event.exception_reason = ""
    event.posted_at = timezone.now()
    event.posted_by = user
    event.save(update_fields=["rule", "journal_entry", "status", "exception_reason", "posted_at", "posted_by", "updated_at"])
    _audit(tenant=tenant, actor=user, action="post", instance=event, request=request, summary="Posted accounting event to journal", after={"event_type": event.event_type, "source_domain": event.source_domain, "source_id": event.source_id, "journal_entry_id": entry.id, "reference": entry.reference, "amount": str(event.amount), "rule_id": event.rule_id})
    return event


def emit_accounting_event(**kwargs):
    """Create an observable event and attempt posting without erasing the source transaction.

    A closed period is represented by a durable FAILED event.  No journal is created,
    and the operational transaction is not rolled back merely because accounting is
    unable to post into an immutable period.
    """
    event, _created = create_accounting_event(**kwargs)
    event_date = kwargs.get("event_date")
    period = None
    if event_date is not None:
        period = _period_for_date(tenant=kwargs["tenant"], entry_date=event_date, lock=False)
    if period and period.status == AccountingPeriod.STATUS_CLOSED:
        event.status = AccountingEventStatus.FAILED
        event.exception_reason = f"The accounting period {period.code} is closed for {accounting_date(event_date, field='event_date')}."
        event.rule = None
        event.journal_entry = None
        event.posted_at = None
        event.posted_by = None
        event.save(update_fields=["status", "exception_reason", "rule", "journal_entry", "posted_at", "posted_by", "updated_at"])
        _audit(tenant=kwargs["tenant"], actor=kwargs.get("user"), action="update", instance=event, request=kwargs.get("request"), summary="Accounting event blocked by closed period", after={"status": event.status, "reason": event.exception_reason, "event_type": event.event_type})
        return event
    if event.status in {AccountingEventStatus.POSTED, AccountingEventStatus.REVERSED}:
        return event
    try:
        return post_accounting_event(tenant=kwargs["tenant"], event_id=event.id, user=kwargs.get("user"), request=kwargs.get("request"))
    except AccountingValidationError as exc:
        event = AccountingEvent.objects.select_for_update().get(tenant=kwargs["tenant"], pk=event.id)
        event.status = AccountingEventStatus.FAILED
        event.exception_reason = str(exc)
        event.save(update_fields=["status", "exception_reason", "updated_at"])
        _audit(tenant=kwargs["tenant"], actor=kwargs.get("user"), action="update", instance=event, request=kwargs.get("request"), summary="Accounting event needs attention", after={"status": event.status, "reason": event.exception_reason, "event_type": event.event_type})
        return event


@transaction.atomic
def reverse_accounting_event(*, tenant, event_id, reversal_date=None, user=None, request=None):
    event = AccountingEvent.objects.select_for_update().get(tenant=tenant, pk=event_id)
    if event.status == AccountingEventStatus.REVERSED:
        return event.reversal_events.first() or event
    if event.status != AccountingEventStatus.POSTED or not event.journal_entry_id:
        raise AccountingValidationError("Only a posted accounting event with a journal may be reversed.")
    reversal = reverse_journal_entry(tenant=tenant, entry_id=event.journal_entry_id, reversal_date=reversal_date or timezone.localdate(), description=f"Operational reversal of {event.source_reference or event.source_id}", user=user, request=request)
    reversal_event, _created = create_accounting_event(tenant=tenant, source_domain=event.source_domain, event_type=event.event_type, source_id=f"{event.source_id}:reversal", event_date=reversal.date, amount=event.amount, currency=event.currency, source_reference=f"Reversal of {event.source_reference or event.source_id}", payload={"original_event_id": event.id, "original_journal_id": event.journal_entry_id}, reversal_of=event, user=user, request=request)
    reversal_event.journal_entry = reversal
    reversal_event.status = AccountingEventStatus.POSTED
    reversal_event.posted_at = reversal.posted_at
    reversal_event.posted_by = user
    reversal_event.save(update_fields=["journal_entry", "status", "posted_at", "posted_by", "updated_at"])
    event.status = AccountingEventStatus.REVERSED
    event.save(update_fields=["status", "updated_at"])
    _audit(tenant=tenant, actor=user, action="reverse", instance=reversal_event, request=request, summary="Reversed accounting event", after={"original_event_id": event.id, "reversal_journal_id": reversal.id, "reversal_event_id": reversal_event.id})
    return reversal_event


@transaction.atomic
def create_journal_draft(*, tenant, data, user=None, request=None):
    raw = dict(data or {})
    reference = str(raw.get("reference", "")).strip()[:60]
    if not reference:
        raise AccountingValidationError("reference is required.")
    entry_date = accounting_date(raw.get("date"))
    lines, total = _normalise_lines(tenant=tenant, raw_lines=raw.get("lines"))
    entry = JournalEntry.objects.create(tenant=tenant, reference=reference, date=entry_date, description=str(raw.get("description", "")).strip(), status=JournalEntry.STATUS_DRAFT, created_by=user)
    JournalEntryLine.objects.bulk_create([JournalEntryLine(tenant=tenant, entry=entry, **line) for line in lines])
    _audit(tenant=tenant, actor=user, action="create", instance=entry, request=request, summary="Created balanced journal draft", after={"reference": entry.reference, "date": str(entry.date), "line_count": len(lines), "total": str(total)})
    return entry


@transaction.atomic
def replace_journal_lines(*, tenant, entry_id, raw_lines, user=None, request=None):
    entry = JournalEntry.objects.select_for_update().get(tenant=tenant, pk=entry_id)
    if entry.status == JournalEntry.STATUS_POSTED:
        raise AccountingValidationError("Posted journal entries are immutable; create a reversal instead.")
    lines, total = _normalise_lines(tenant=tenant, raw_lines=raw_lines)
    entry.lines.all().delete()
    JournalEntryLine.objects.bulk_create([JournalEntryLine(tenant=tenant, entry=entry, **line) for line in lines])
    _audit(tenant=tenant, actor=user, action="update", instance=entry, request=request, summary="Replaced balanced journal draft lines", after={"reference": entry.reference, "line_count": len(lines), "total": str(total)})
    return entry


@transaction.atomic
def post_journal_entry(*, tenant, entry_id, user=None, request=None):
    entry = JournalEntry.objects.select_for_update().get(tenant=tenant, pk=entry_id)
    if entry.status == JournalEntry.STATUS_POSTED:
        return entry
    _assert_open_period(tenant=tenant, entry_date=entry.date)
    lines = list(entry.lines.select_for_update().select_related("account"))
    if len(lines) < 2:
        raise AccountingValidationError("A journal entry requires at least two lines before posting.")
    total_debit = sum((line.debit for line in lines), ZERO)
    total_credit = sum((line.credit for line in lines), ZERO)
    if total_debit != total_credit:
        raise AccountingValidationError("Journal entry is not balanced: total debits must equal total credits.")
    for line in lines:
        if line.tenant_id != tenant.id or line.account.tenant_id != tenant.id or line.entry_id != entry.id:
            raise AccountingValidationError("Journal entry includes an invalid tenant reference.")
        if (line.debit > ZERO) == (line.credit > ZERO):
            raise AccountingValidationError("Each posted journal line must have exactly one positive debit or credit amount.")
    entry.status = JournalEntry.STATUS_POSTED
    entry.posted_by = user
    entry.posted_at = timezone.now()
    entry.save(update_fields=["status", "posted_by", "posted_at"])
    _audit(tenant=tenant, actor=user, action="post", instance=entry, request=request, summary="Posted balanced journal entry", after={"reference": entry.reference, "date": str(entry.date), "debits": str(total_debit), "credits": str(total_credit)})
    return entry


@transaction.atomic
def reverse_journal_entry(*, tenant, entry_id, reversal_date=None, description="", user=None, request=None):
    entry = JournalEntry.objects.select_for_update().prefetch_related("lines").get(tenant=tenant, pk=entry_id)
    if entry.status != JournalEntry.STATUS_POSTED:
        raise AccountingValidationError("Only posted journal entries can be reversed.")
    if hasattr(entry, "reversal"):
        raise AccountingValidationError("This journal entry already has a posted reversal.")
    reversal_date = accounting_date(reversal_date or timezone.localdate())
    _assert_open_period(tenant=tenant, entry_date=reversal_date)
    lines = list(entry.lines.select_for_update())
    if not lines:
        raise AccountingValidationError("A journal entry without lines cannot be reversed.")
    reversal = JournalEntry.objects.create(tenant=tenant, reference=_next_reversal_reference(tenant=tenant, entry=entry), date=reversal_date, description=str(description or f"Reversal of {entry.reference}").strip(), status=JournalEntry.STATUS_DRAFT, created_by=user, reversal_of=entry)
    JournalEntryLine.objects.bulk_create([JournalEntryLine(tenant=tenant, entry=reversal, account_id=line.account_id, description=f"Reversal: {line.description}"[:255], debit=line.credit, credit=line.debit) for line in lines])
    reversal = post_journal_entry(tenant=tenant, entry_id=reversal.id, user=user, request=request)
    _audit(tenant=tenant, actor=user, action="reverse", instance=reversal, request=request, summary="Posted journal reversal", after={"reference": reversal.reference, "reversal_of": entry.reference})
    return reversal


@transaction.atomic
def transition_expense(*, tenant, expense_id, target_status, user=None, request=None):
    expense = Expense.objects.select_for_update().get(tenant=tenant, pk=expense_id)
    if expense.status != Expense.STATUS_PENDING:
        raise AccountingValidationError("Only pending expenses can be approved or rejected.")
    if target_status not in {Expense.STATUS_APPROVED, Expense.STATUS_REJECTED}:
        raise AccountingValidationError("Expense target status is invalid.")
    expense.status = target_status
    expense.save(update_fields=["status"])
    _audit(tenant=tenant, actor=user, action="approve" if target_status == Expense.STATUS_APPROVED else "reject", instance=expense, request=request, summary=f"{target_status.title()} expense", after={"status": target_status, "amount": str(expense.amount), "category_id": expense.category_id})
    return expense


@transaction.atomic
def post_expense_to_journal(*, tenant, expense_id, expense_account_id, payment_account_id, reference=None, user=None, request=None):
    expense = Expense.objects.select_for_update().select_related("category").get(tenant=tenant, pk=expense_id)
    if expense.status != Expense.STATUS_APPROVED:
        raise AccountingValidationError("Only approved expenses may be posted to the journal.")
    if expense.journal_entry_id:
        return expense
    event, _created = create_accounting_event(tenant=tenant, source_domain="accounting", event_type=AccountingEventType.EXPENSE_MANUAL, source_id=str(expense.id), event_date=expense.date, amount=expense.amount, source_reference=f"Expense {expense.id}", payload={"expense_id": expense.id, "expense_account_id": expense_account_id, "payment_account_id": payment_account_id}, user=user, request=request)
    event = post_accounting_event(tenant=tenant, event_id=event.id, debit_account_id=expense_account_id, credit_account_id=payment_account_id, reference=str(reference or f"EXP-{expense.id}").strip()[:60], description=f"Expense: {expense.description}"[:2000], user=user, request=request)
    if event.status != AccountingEventStatus.POSTED or not event.journal_entry_id:
        raise AccountingValidationError(event.exception_reason or "Expense accounting posting requires attention.")
    expense.journal_entry = event.journal_entry
    expense.save(update_fields=["journal_entry"])
    _audit(tenant=tenant, actor=user, action="post", instance=expense, request=request, summary="Posted approved expense to journal", after={"expense_id": expense.id, "journal_entry_id": event.journal_entry_id, "reference": event.journal_entry.reference, "amount": str(expense.amount), "accounting_event_id": event.id})
    return expense


@transaction.atomic
def close_accounting_period(*, tenant, period_id, user=None, request=None):
    period = AccountingPeriod.objects.select_for_update().get(tenant=tenant, pk=period_id)
    if period.status == AccountingPeriod.STATUS_CLOSED:
        return period
    open_drafts = JournalEntry.objects.filter(tenant=tenant, status=JournalEntry.STATUS_DRAFT, date__gte=period.start_date, date__lte=period.end_date).exists()
    if open_drafts:
        raise AccountingValidationError("All journal drafts in the period must be posted or removed before closing it.")
    period.status = AccountingPeriod.STATUS_CLOSED
    period.closed_by = user
    period.closed_at = timezone.now()
    period.save(update_fields=["status", "closed_by", "closed_at"])
    _audit(tenant=tenant, actor=user, action="close", instance=period, request=request, summary="Closed accounting period", after={"code": period.code, "start_date": str(period.start_date), "end_date": str(period.end_date)})
    return period


# ───────────────────────── Auto-posting engine ─────────────────────────
def process_pending_events(*, tenant, limit=50):
    """Attempt to post up to *limit* pending accounting events for a tenant."""
    pending = AccountingEvent.objects.filter(tenant=tenant, status=AccountingEventStatus.PENDING).order_by("event_date", "created_at", "id")[:limit]
    posted, failed, skipped = 0, 0, 0
    for event in pending:
        try:
            result = post_accounting_event(tenant=tenant, event_id=event.id)
            if result.status == AccountingEventStatus.POSTED:
                posted += 1
            else:
                skipped += 1
        except AccountingValidationError:
            failed += 1
        except Exception:
            failed += 1
    return {"posted": posted, "failed": failed, "skipped": skipped}
