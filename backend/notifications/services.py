"""Deprecated compatibility alert scans.

This module remains only to preserve existing alert-rule data during the Phase
19 migration.  New in-app notification work must target
``operations.InAppNotification``; these scans are not exposed by root routes.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from customers.models import CustomerCreditLimit
from hr.models import Shift
from pos.models import Product

from .models import AlertRule, Notification


def _rule(*, tenant, kind):
    return AlertRule.objects.filter(tenant=tenant, kind=kind, is_active=True).first()


def _emit(*, tenant, kind, title, body, severity="warning", link="", user=None):
    rule = _rule(tenant=tenant, kind=kind)
    if not rule:
        return None
    notification = Notification.objects.create(
        tenant=tenant,
        rule=rule,
        kind=kind,
        title=title,
        body=body,
        severity=severity,
        target_user=user,
        link=link,
    )
    if rule.channel in {"both", "email"}:
        _send_email(notification, rule)
    return notification


def _send_email(notification, rule):
    from notifications.emailer import send_alert_email

    recipients = [recipient.strip() for recipient in rule.email_recipients.split(",") if recipient.strip()]
    if recipients and send_alert_email(recipients, notification.title, notification.body):
        notification.is_sent_email = True
        notification.save(update_fields=["is_sent_email"])


@transaction.atomic
def scan_low_stock(*, tenant):
    rule = _rule(tenant=tenant, kind=AlertRule.KIND_LOW_STOCK)
    if not rule:
        return []
    notifications = []
    products = Product.objects.filter(
        tenant=tenant,
        is_active=True,
        stock_quantity__lte=rule.low_stock_threshold,
    )
    for product in products:
        notification = _emit(
            tenant=tenant,
            kind=AlertRule.KIND_LOW_STOCK,
            title=f"Low stock: {product.name}",
            body=f"{product.name} (SKU {product.sku}) is at {product.stock_quantity} units (threshold {rule.low_stock_threshold}).",
            severity="warning",
            link="#/products",
        )
        if notification:
            notifications.append(notification.id)
    return notifications


@transaction.atomic
def scan_expiry(*, tenant):
    rule = _rule(tenant=tenant, kind=AlertRule.KIND_EXPIRY)
    if not rule:
        return []
    cutoff = timezone.now().date() + timedelta(days=rule.expiry_days)
    notifications = []
    products = Product.objects.filter(
        tenant=tenant,
        is_active=True,
        expiry_date__isnull=False,
        expiry_date__lte=cutoff,
    )
    for product in products:
        notification = _emit(
            tenant=tenant,
            kind=AlertRule.KIND_EXPIRY,
            title=f"Near expiry: {product.name}",
            body=f"{product.name} expires on {product.expiry_date} (within {rule.expiry_days} days).",
            severity="critical",
            link="#/products",
        )
        if notification:
            notifications.append(notification.id)
    return notifications


@transaction.atomic
def scan_shift_handover(*, tenant):
    rule = _rule(tenant=tenant, kind=AlertRule.KIND_SHIFT_HANDOVER)
    if not rule:
        return []
    notifications = []
    open_shifts = Shift.objects.filter(
        tenant=tenant,
        status=Shift.STATUS_OPEN,
        started_at__lt=timezone.now() - timedelta(hours=8),
    )
    for shift in open_shifts:
        notification = _emit(
            tenant=tenant,
            kind=AlertRule.KIND_SHIFT_HANDOVER,
            title="Shift handover overdue",
            body=f"{shift.employee.full_name} has an open shift since {shift.started_at:%H:%M} — handover required.",
            severity="warning",
            link="#/shifts",
        )
        if notification:
            notifications.append(notification.id)
    return notifications


@transaction.atomic
def scan_credit_limits(*, tenant):
    rule = _rule(tenant=tenant, kind=AlertRule.KIND_CREDIT_LIMIT)
    if not rule:
        return []
    notifications = []
    for credit_limit in CustomerCreditLimit.objects.filter(tenant=tenant, is_active=True):
        if Decimal(credit_limit.used) >= Decimal(credit_limit.limit):
            notification = _emit(
                tenant=tenant,
                kind=AlertRule.KIND_CREDIT_LIMIT,
                title=f"Credit limit exceeded: {credit_limit.customer.name}",
                body=f"{credit_limit.customer.name} used {credit_limit.used} of {credit_limit.limit} credit.",
                severity="critical",
                link="#/customers",
            )
            if notification:
                notifications.append(notification.id)
    return notifications


def run_all_scans(*, tenant):
    fired = []
    fired += scan_low_stock(tenant=tenant)
    fired += scan_expiry(tenant=tenant)
    fired += scan_shift_handover(tenant=tenant)
    fired += scan_credit_limits(tenant=tenant)
    return {"fired": len(fired)}


def mark_read(*, tenant, notification_id, user=None):
    notification = Notification.objects.get(tenant=tenant, pk=notification_id)
    if user and notification.target_user_id and notification.target_user_id != user.id:
        raise PermissionError("Not your notification")
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return notification
