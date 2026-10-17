"""Canonical Phase 6 POS transaction services.

The browser sends cart and tender intent only. This module owns all tenant-bound
validation, price/tax resolution, settlement, inventory mutation, refunds, and
idempotency within Django transactions.
"""

from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from enterprise.models import Warehouse
from inventory.services import apply_adjustment
from payments.models import RefundSettlement, TenderedPayment
from payments.services import record_refund_settlement, settle_order
from pricing.models import CustomerGroupPrice, PriceList, PriceListItem, TimeBasedPrice, VolumeTier
from tax.engine import allocate_order_discount, amount_added_to_price, compute_line_tax, compute_order_tax

from ..models import CashSession, CashTransaction, Customer, Order, OrderItem, Product, Refund, RefundItem


MONEY = Decimal("0.01")


def decimal(value, *, field="value"):
    try:
        parsed = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be a valid number.") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be a finite number.")
    return parsed


def money(value):
    return decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def parse_discount(value):
    """Return the requested order discount as money, or raise ValueError.

    Empty means no discount. NaN/Infinity and malformed amounts are rejected
    with a readable message instead of a decimal-module error.
    """
    raw = "0" if value is None or str(value).strip() == "" else str(value).strip()
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Discount must be a valid amount.") from None
    if not amount.is_finite():
        raise ValueError("Discount must be a valid amount.")
    return amount.quantize(MONEY, rounding=ROUND_HALF_UP)


def discount_requested(value):
    """True when *value* asks for a non-zero discount (needs ``pos.discount``).

    A malformed amount is not treated as a request here; the quote rejects it
    with a 400 so the cashier sees what is wrong.
    """
    try:
        return parse_discount(value) != 0
    except ValueError:
        return False


# S.R.O. 1006(I)/2021 B(iv): the buyer's name is recorded when the invoice value
# is above Rs.100,000. Override with settings.POS_BUYER_IDENTIFICATION_THRESHOLD
# (a number; 0 or None disables the rule).
BUYER_IDENTIFICATION_THRESHOLD_DEFAULT = Decimal("100000")


def buyer_identification_threshold():
    from django.conf import settings

    raw = getattr(settings, "POS_BUYER_IDENTIFICATION_THRESHOLD", BUYER_IDENTIFICATION_THRESHOLD_DEFAULT)
    if raw in (None, ""):
        return None
    value = Decimal(str(raw))
    return value if value > 0 else None


def buyer_identification_required(*, tenant, total):
    """True when this sale must record the buyer (FBR-integrated tenants only).

    Only tenants whose till is FBR-integrated (active IMS configuration) are
    affected; everyone else keeps their current checkout.
    """
    threshold = buyer_identification_threshold()
    if threshold is None or money(total) <= threshold:
        return False
    from fiscal.pos_fiscalization import till_fiscalization_configured

    return till_fiscalization_configured(tenant)


def _enforce_buyer_identification(*, tenant, customer, total):
    if customer is not None and (customer.name or "").strip():
        return
    if not buyer_identification_required(tenant=tenant, total=total):
        return
    threshold = buyer_identification_threshold()
    raise ValueError(
        f"Sales above {threshold:,.0f} must record the buyer's name (FBR S.R.O. 1006(I)/2021). "
        "Assign a customer to this sale before checkout."
    )


class IdempotencyConflictError(ValueError):
    """The same idempotency key was reused for a different checkout request."""


def _checkout_request_hash(*, user, items, tenders, customer_id=None, discount=Decimal("0")):
    """Return a stable fingerprint for the logical checkout request.

    Values are normalized before hashing so harmless numeric formatting differences
    such as ``1``, ``1.0`` and ``1.000`` do not create different fingerprints.
    Item order is normalized because the cart has product/quantity semantics rather
    than positional semantics. Tender order is retained because tender sequencing
    can be meaningful to payment processing.
    """
    if not isinstance(items, list) or not isinstance(tenders, list):
        raise ValueError("Checkout items and tenders must be lists.")

    normalized_items = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("Each cart item must be an object.")
        try:
            product_id = int(raw["product_id"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Each cart item requires a valid product_id.") from exc
        normalized_items.append({
            "product_id": product_id,
            "quantity": str(decimal(raw.get("quantity"), field="quantity").normalize()),
        })
    normalized_items.sort(key=lambda row: row["product_id"])

    normalized_tenders = []
    for raw in tenders:
        if not isinstance(raw, dict):
            raise ValueError("Each tender must be an object.")
        tender = {}
        for key in sorted(raw):
            value = raw[key]
            if key == "amount":
                value = str(money(value))
            elif value is None:
                value = None
            else:
                value = str(value)
            tender[str(key)] = value
        normalized_tenders.append(tender)

    payload = {
        "user_id": int(user.pk),
        "customer_id": int(customer_id) if customer_id not in (None, "") else None,
        "discount": str(parse_discount(discount)),
        "items": normalized_items,
        "tenders": normalized_tenders,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _tenant_customer(tenant, customer_id):
    if customer_id in (None, ""):
        return None
    return Customer.objects.get(tenant=tenant, pk=customer_id, is_active=True)


def _tenant_warehouse(tenant, warehouse_id):
    if warehouse_id in (None, ""):
        return None
    return Warehouse.objects.get(tenant=tenant, pk=warehouse_id, is_active=True)


def active_session_for_user(*, tenant, user, lock=False):
    queryset = CashSession.objects.filter(tenant=tenant, is_open=True, opened_by=user)
    return queryset.select_for_update().order_by("id").first() if lock else queryset.order_by("id").first()


@transaction.atomic
def open_session(*, tenant, user, opening_balance, warehouse_id=None, employee_name="", notes=""):
    opening_balance = money(opening_balance)
    if opening_balance < 0:
        raise ValueError("Opening balance cannot be negative.")
    if opening_balance > 100000:
        raise ValueError("Opening balance cannot exceed 100,000.")
    if CashSession.objects.select_for_update().filter(tenant=tenant, opened_by=user, is_open=True).exists():
        raise ValueError("You already have an open cash session in this tenant.")
    warehouse = _tenant_warehouse(tenant, warehouse_id)
    return CashSession.objects.create(
        tenant=tenant,
        warehouse=warehouse,
        opened_by=user,
        employee_name=(employee_name or user.get_full_name() or user.get_username()).strip(),
        opening_balance=opening_balance,
        notes=notes or "",
        is_open=True,
    )


@transaction.atomic
def close_own_session(*, tenant, user, actual_cash):
    session = active_session_for_user(tenant=tenant, user=user, lock=True)
    if session is None:
        raise LookupError("No active cash session is available for this cashier.")

    # Reconciliation is an optional downstream payment-control workflow, not a
    # prerequisite for the canonical POS session close. The drawer close must
    # remain usable from the POS itself and derive expected cash from settled
    # tenders and explicit cash refunds.
    actual_cash = money(actual_cash)
    if actual_cash < 0:
        raise ValueError("Actual cash cannot be negative.")
    cash_in = session.transactions.filter(transaction_type="in").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    cash_out = session.transactions.filter(transaction_type="out").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    tendered_cash = TenderedPayment.objects.filter(tenant=tenant, order__session=session, tender_type="cash").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    refunded_cash = RefundSettlement.objects.filter(
        tenant=tenant,
        refund__order__session=session,
    ).aggregate(total=Sum("cash_amount"))["total"] or Decimal("0")
    expected = money(Decimal(session.opening_balance) + Decimal(cash_in) - Decimal(cash_out) + Decimal(tendered_cash) - Decimal(refunded_cash))
    session.orders.filter(status="draft").update(status="cancelled")
    session.is_open = False
    session.closed_by = user
    session.closed_at = timezone.now()
    session.actual_closing_balance = actual_cash
    session.closing_balance = expected
    session.save(update_fields=["is_open", "closed_by", "closed_at", "actual_closing_balance", "closing_balance"])
    return session, expected, money(actual_cash - expected)


@transaction.atomic
def record_cash_movement(*, tenant, user, transaction_type, amount, reason):
    if transaction_type not in {"in", "out"}:
        raise ValueError("Cash transaction type must be 'in' or 'out'.")
    amount = money(amount)
    if amount <= 0:
        raise ValueError("Cash movement amount must be greater than zero.")
    session = active_session_for_user(tenant=tenant, user=user, lock=True)
    if session is None:
        raise LookupError("No active cash session is available for this cashier.")
    return CashTransaction.objects.create(
        tenant=tenant,
        session=session,
        transaction_type=transaction_type,
        amount=amount,
        reason=(reason or "").strip(),
        created_by=user,
    )


def resolve_unit_price(*, tenant, product, customer, quantity):
    """Resolve an existing certified pricing rule under explicit tenant filters."""
    quantity = decimal(quantity, field="quantity")
    now = timezone.now()
    current_price = Decimal(product.sales_price)
    if customer and customer.group_id:
        group_price = CustomerGroupPrice.objects.filter(
            tenant=tenant, customer_group_id=customer.group_id, product=product
        ).order_by("id").first()
        if group_price:
            return money(group_price.price)
    active_lists = PriceList.objects.filter(tenant=tenant, is_active=True, is_default=True).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now)
    ).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=now))
    item = PriceListItem.objects.filter(
        tenant=tenant, price_list__in=active_lists, product=product, variant__isnull=True, min_quantity__lte=quantity
    ).order_by("-min_quantity", "id").first()
    if item:
        current_price = Decimal(item.price)
    today, current_time = now.date(), now.time()
    timed = TimeBasedPrice.objects.filter(tenant=tenant, product=product, is_active=True).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=today)
    ).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today)).filter(
        Q(start_time__isnull=True) | Q(start_time__lte=current_time)
    ).filter(Q(end_time__isnull=True) | Q(end_time__gte=current_time)).order_by("id").first()
    if timed:
        weekdays = {value.strip() for value in (timed.weekdays or "").split(",") if value.strip()}
        if not weekdays or str(today.weekday()) in weekdays:
            current_price = Decimal(timed.price)
    tier = VolumeTier.objects.filter(tenant=tenant, product=product, min_quantity__lte=quantity).order_by("-min_quantity", "id").first()
    if tier:
        current_price = Decimal(tier.unit_price)
    return money(current_price)


def _normalise_items(*, tenant, items):
    if not isinstance(items, list) or not items:
        raise ValueError("At least one cart item is required.")
    quantities = defaultdict(lambda: Decimal("0"))
    for raw in items:
        try:
            product_id = int(raw["product_id"])
            quantity = decimal(raw["quantity"], field="quantity")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Each cart item requires product_id and quantity.") from exc
        if quantity <= 0:
            raise ValueError("Cart quantities must be greater than zero.")
        quantities[product_id] += quantity
    products = Product.objects.select_for_update().filter(tenant=tenant, is_active=True, id__in=quantities).order_by("id")
    by_id = {product.id: product for product in products}
    missing = set(quantities) - set(by_id)
    if missing:
        raise ValueError("One or more products are unavailable in the active tenant.")
    return [(by_id[product_id], quantity) for product_id, quantity in quantities.items()]


def _quote(*, tenant, customer, items, discount):
    normalized = _normalise_items(tenant=tenant, items=items)
    lines, subtotal, tax, added_tax = [], Decimal("0"), Decimal("0"), Decimal("0")
    for product, quantity in normalized:
        unit_price = resolve_unit_price(tenant=tenant, product=product, customer=customer, quantity=quantity)
        line_subtotal = money(unit_price * quantity)
        subtotal += line_subtotal
        lines.append({"product": product, "quantity": quantity, "unit_price": unit_price, "subtotal": line_subtotal})
    discount = parse_discount(discount)
    if discount < 0 or discount > subtotal:
        raise ValueError("Discount must be between zero and the cart subtotal.")
    # Tax each line on its discounted value (Sales Tax Act s.2(46)(b)), using
    # the same discount split and per-line rounding as compute_order_tax.
    allocations = allocate_order_discount([line["subtotal"] for line in lines], discount)
    for line, line_discount in zip(lines, allocations):
        tax_rows = compute_line_tax(line["product"], line["subtotal"] - line_discount, customer)
        line_tax = money(sum((Decimal(row["amount"]) for row in tax_rows), Decimal("0")))
        tax += line_tax
        added_tax += money(amount_added_to_price(tax_rows))
        line["tax"] = line_tax
    # Inclusive tax is already inside the line prices; only exclusive tax is added.
    return lines, money(subtotal), discount, money(tax), money(subtotal - discount + added_tax)


@transaction.atomic
def preview_sale(*, tenant, customer_id=None, items=None, discount=Decimal("0")):
    customer = _tenant_customer(tenant, customer_id)
    lines, subtotal, discount, tax, total = _quote(tenant=tenant, customer=customer, items=items, discount=discount)
    threshold = buyer_identification_threshold()
    return {
        "customer_id": customer.id if customer else None,
        # The till must collect the buyer before payment when this is true and
        # no customer is assigned (checkout enforces it).
        "buyer_identification_required": buyer_identification_required(tenant=tenant, total=total),
        "buyer_identification_threshold": str(threshold) if threshold is not None else None,
        "lines": [{"product_id": line["product"].id, "quantity": str(line["quantity"]), "unit_price": str(line["unit_price"]), "subtotal": str(line["subtotal"]), "tax": str(line["tax"])} for line in lines],
        "subtotal": str(subtotal), "discount": str(discount), "tax": str(tax), "total": str(total),
    }


def _idempotent_replay(*, tenant, key, request_hash):
    """Return the committed order for this Idempotency-Key, or None.

    Raises IdempotencyConflictError when the key was used for a different request.
    """
    existing = Order.objects.select_for_update().filter(tenant=tenant, idempotency_key=key).first()
    if existing is None:
        return None
    if not existing.idempotency_request_hash:
        raise IdempotencyConflictError(
            "This Idempotency-Key belongs to an existing checkout whose request fingerprint is unavailable."
        )
    if existing.idempotency_request_hash != request_hash:
        raise IdempotencyConflictError(
            "The Idempotency-Key was already used with a different checkout request."
        )
    return existing


@transaction.atomic
def checkout(*, tenant, user, items, tenders, customer_id=None, discount=Decimal("0"), idempotency_key=""):
    key = (idempotency_key or "").strip()
    if not key:
        raise ValueError("An Idempotency-Key is required to complete checkout safely.")
    # Bound attacker-controlled input before hashing or querying the database.
    if len(key) > 128:
        raise ValueError("Idempotency-Key must be 128 characters or fewer.")
    request_hash = _checkout_request_hash(
        user=user, items=items, tenders=tenders, customer_id=customer_id, discount=discount
    )
    existing = _idempotent_replay(tenant=tenant, key=key, request_hash=request_hash)
    if existing:
        return existing, True
    customer = _tenant_customer(tenant, customer_id)
    session = active_session_for_user(tenant=tenant, user=user, lock=True)
    if session is None:
        raise LookupError("Open a cash session before checkout.")
    # A concurrent duplicate submission (double click / network retry) from the
    # same cashier blocks on the session row lock above until the first request
    # commits. Re-check under the lock so it replays instead of failing.
    existing = _idempotent_replay(tenant=tenant, key=key, request_hash=request_hash)
    if existing:
        return existing, True
    lines, subtotal, discount, _preview_tax, _preview_total = _quote(tenant=tenant, customer=customer, items=items, discount=discount)
    _enforce_buyer_identification(tenant=tenant, customer=customer, total=_preview_total)
    try:
        # Savepoint: on PostgreSQL an IntegrityError aborts the enclosing
        # transaction, so the replay lookup below needs its own savepoint.
        with transaction.atomic():
            order = Order.objects.create(
                tenant=tenant,
                warehouse=session.warehouse,
                customer=customer,
                session=session,
                payment_method="split" if len(tenders or []) > 1 else str((tenders or [{}])[0].get("tender_type", "cash")),
                subtotal=subtotal,
                discount=discount,
                tax=Decimal("0"),
                total=Decimal("0"),
                status="draft",
                idempotency_key=key,
                idempotency_request_hash=request_hash,
            )
    except IntegrityError:
        existing = _idempotent_replay(tenant=tenant, key=key, request_hash=request_hash)
        if existing:
            return existing, True
        raise
    for line in lines:
        OrderItem.objects.create(
            tenant=tenant, order=order, product=line["product"], quantity=line["quantity"],
            unit_price=line["unit_price"], subtotal=line["subtotal"],
            cost_price=line["product"].cost_price,
        )
    compute_order_tax(order, customer)
    order.refresh_from_db()
    for line in lines:
        apply_adjustment(
            tenant=tenant, product_id=line["product"].id, warehouse_id=session.warehouse_id,
            quantity=-line["quantity"], reason="POS sale", note=f"Sale {order.order_number}",
            user=user, movement_type="sale", reference=order.order_number,
        )
    settled = settle_order(order=order, tenders=tenders, user=user)
    return settled, False


@transaction.atomic
def park_cart(*, tenant, user, label="", customer_id=None, items=None):
    from pos_core.models import ParkedOrder
    session = active_session_for_user(tenant=tenant, user=user, lock=True)
    if session is None:
        raise LookupError("Open a cash session before parking a sale.")
    customer = _tenant_customer(tenant, customer_id)
    normalized = _normalise_items(tenant=tenant, items=items)
    payload = {"items": [{"product_id": product.id, "quantity": str(quantity)} for product, quantity in normalized]}
    return ParkedOrder.objects.create(tenant=tenant, session=session, customer=customer, label=(label or "").strip(), payload=payload, parked_by=user)


@transaction.atomic
def resume_parked_cart(*, tenant, user, parked_order_id):
    from pos_core.models import ParkedOrder
    parked = ParkedOrder.objects.select_for_update().get(tenant=tenant, pk=parked_order_id, status=ParkedOrder.STATUS_PARKED)
    session = active_session_for_user(tenant=tenant, user=user, lock=True)
    if session is None or parked.session_id != session.id:
        raise ValueError("Only the active session that parked this sale can resume it.")
    parked.status = ParkedOrder.STATUS_RESUMED
    parked.resumed_at = timezone.now()
    parked.save(update_fields=["status", "resumed_at"])
    return parked


@transaction.atomic
def process_refund(*, tenant, user, order_id, rows, reason="", cash_refund_amount=Decimal("0")):
    if not isinstance(rows, list) or not rows:
        raise ValueError("A refund requires at least one item.")
    order = Order.objects.select_for_update().get(tenant=tenant, pk=order_id)
    if order.status in {"draft", "cancelled", "refunded"}:
        raise ValueError("This order is not refundable.")
    refund = Refund.objects.create(tenant=tenant, order=order, reason=(reason or "").strip(), subtotal=Decimal("0"), discount=Decimal("0"), tax=Decimal("0"), total_amount=Decimal("0"))
    subtotal, total = Decimal("0"), Decimal("0")
    for raw in rows:
        try:
            item_id = int(raw["order_item_id"])
            quantity = decimal(raw["quantity"], field="quantity")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Each refund item requires order_item_id and quantity.") from exc
        if quantity <= 0:
            raise ValueError("Refund quantities must be greater than zero.")
        item = OrderItem.objects.select_for_update().select_related("product").get(tenant=tenant, order=order, pk=item_id)
        refunded = RefundItem.objects.filter(tenant=tenant, order_item=item).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        if quantity > Decimal(item.quantity) - Decimal(refunded):
            raise ValueError(f"Refund quantity exceeds the remaining quantity for {item.product.name}.")
        line_subtotal = money(Decimal(item.unit_price) * quantity)
        amount = money(Decimal(order.total) * (Decimal(item.subtotal) / Decimal(order.subtotal)) * (quantity / Decimal(item.quantity))) if order.subtotal else Decimal("0")
        apply_adjustment(
            tenant=tenant, product_id=item.product_id, warehouse_id=order.warehouse_id,
            quantity=quantity, reason="POS refund", note=f"Refund for {order.order_number}",
            user=user, movement_type="refund", reference=f"RE-{refund.id:06d}",
        )
        RefundItem.objects.create(tenant=tenant, refund=refund, order_item=item, quantity=quantity, subtotal=line_subtotal, amount=amount)
        subtotal += line_subtotal
        total += amount
    refund.subtotal = money(subtotal)
    refund.total_amount = money(total)
    ratio = Decimal("0") if not order.total else refund.total_amount / Decimal(order.total)
    refund.discount = money(Decimal(order.discount) * ratio)
    refund.tax = money(Decimal(order.tax) * ratio)
    refund.save(update_fields=["subtotal", "total_amount", "discount", "tax"])
    cash_refund_amount = money(cash_refund_amount)
    if cash_refund_amount < 0 or cash_refund_amount > refund.total_amount:
        raise ValueError("cash_refund_amount must be between zero and the refund total.")
    original_cash = TenderedPayment.objects.filter(
        tenant=tenant,
        order=order,
        tender_type=TenderedPayment.TENDER_CASH,
        is_settled=True,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    prior_cash_refunds = RefundSettlement.objects.filter(
        tenant=tenant,
        refund__order=order,
    ).aggregate(total=Sum("cash_amount"))["total"] or Decimal("0")
    if cash_refund_amount > Decimal(original_cash) - Decimal(prior_cash_refunds):
        raise ValueError("cash_refund_amount exceeds the remaining cash tender for this order.")
    from payments.models import ProviderPaymentOperation

    provider_paid = ProviderPaymentOperation.objects.filter(
        tenant=tenant,
        order=order,
        status=ProviderPaymentOperation.STATUS_SUCCEEDED,
    ).exists()
    if provider_paid and cash_refund_amount:
        raise ValueError("Provider-funded refunds cannot be recorded as cash drawer refunds.")
    if not provider_paid:
        record_refund_settlement(refund=refund, user=user, cash_amount=cash_refund_amount)
    fully_refunded = all((RefundItem.objects.filter(tenant=tenant, order_item=item).aggregate(total=Sum("quantity"))["total"] or Decimal("0")) >= Decimal(item.quantity) for item in order.items.all())
    new_status = "refunded" if fully_refunded else "partially_refunded"
    order.transition_to(new_status)
    return refund


def _receipt_fbr_identity(tenant):
    """Seller NTN and PoS registration number printed on the receipt.

    S.R.O. 1006(I)/2021 A(iv)/(v). Taken from the tenant's active FBR
    configuration; only these public fields are read (never credentials).
    The PoS registration number exists only on the IMS (FBR PoS) track.
    """
    from fbr.constants import INTEGRATION_MODE_IMS
    from fiscal.pos_fiscalization import _active_configuration

    config = _active_configuration(tenant)
    if config is None:
        return {"ntn": "", "pos_registration_number": "", "fbr_integrated": False}
    is_ims = config.integration_mode == INTEGRATION_MODE_IMS
    return {
        "ntn": config.seller_ntn_cnic or "",
        "pos_registration_number": str(config.pos_registration_number or "") if is_ims else "",
        "fbr_integrated": is_ims,
    }


def receipt_business(tenant):
    """Business header printed on every receipt (public receipt fields only).

    Returned with the receipt so any member allowed to view the sale (e.g. a
    cashier) can print it; /api/company/ itself stays settings-only.
    """
    from pos.models import Company

    identity = _receipt_fbr_identity(tenant)
    company = Company.objects.filter(tenant=tenant).order_by("id").first()
    if company is None:
        return {"name": tenant.name, "tagline": "", "address": "", "phone": "", "email": "", "website": "",
                "tax_number": "", "gst": "", "footer_message": "Thank you for your purchase!", "logo": None,
                "currency": None, "receipt_paper": "80mm", **identity}
    return {
        "name": company.name or tenant.name, "tagline": company.tagline, "address": company.address,
        "phone": company.phone, "email": company.email, "website": company.website,
        "tax_number": company.tax_number, "gst": company.gst, "footer_message": company.footer_message,
        "logo": company.logo.url if company.logo else None, "currency": company.currency,
        "receipt_paper": company.receipt_paper or "80mm",
        **identity,
    }


def _receipt_cashier(order):
    session = order.session
    if session is None:
        return ""
    if session.employee_name:
        return session.employee_name
    user = session.opened_by
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username() or "").strip()


def _receipt_fiscal_lines(order):
    """Item lines exactly as fiscalized (S.R.O. 1006 C): rate, tax, value excl. tax.

    Read from the order's fiscal invoice, the same rows the FBR payload is
    built from, so the printed figures match what was transmitted. Empty when
    the sale has no fiscal invoice.
    """
    from fiscal.pos_fiscalization import _order_invoice

    invoice = _order_invoice(order)
    if invoice is None:
        return []
    rows = []
    for line in invoice.lines.order_by("line_number", "id"):
        snapshot = line.fbr_snapshot if isinstance(line.fbr_snapshot, dict) else {}
        rate = snapshot.get("sales_tax_rate")
        try:
            rate = str(Decimal(str(rate)).quantize(Decimal("0.01"))) if rate not in (None, "") else ""
        except (InvalidOperation, ValueError):
            rate = ""
        rows.append({
            "line_number": line.line_number,
            "description": line.product_name,
            # Fixed-point, trailing zeros dropped: 2.5000 -> "2.5", 10.0000 -> "10" (never "1E+1").
            "quantity": format(line.quantity.normalize(), "f") if line.quantity is not None else "",
            "unit_price": str(line.unit_price),
            "discount": str(line.discount),
            "value_excl_tax": str(line.taxable_amount if line.taxable_amount is not None else line.subtotal - line.discount),
            "tax_rate": rate,
            "tax": str(line.sales_tax),
            "total": str(line.total_amount),
        })
    return rows


def receipt_payload(*, order, fiscal=None):
    if fiscal is None:
        from fiscal.pos_fiscalization import pos_fiscal_status

        fiscal = pos_fiscal_status(order)
    return {
        # Real FBR number stays separate; a simulator acceptance carries an
        # explicitly labelled TEST number and QR, never an official FBR number.
        "fiscal": fiscal,
        "business": receipt_business(order.tenant),
        "order": {
            "id": order.id, "number": order.order_number, "status": order.status,
            "created_at": order.created_at, "customer": order.customer.name if order.customer else "Walk-in customer",
            "session_id": order.session_id, "warehouse_id": order.warehouse_id,
            "cashier": _receipt_cashier(order),
        },
        "fiscal_lines": _receipt_fiscal_lines(order),
        "items": [{"product_id": item.product_id, "name": item.product.name, "quantity": str(item.quantity), "unit_price": str(item.unit_price), "subtotal": str(item.subtotal)} for item in order.items.select_related("product")],
        "tenders": [
            {
                "tender_type": item.tender_type,
                "label": item.get_tender_type_display(),
                "amount": str(item.amount),
                "currency": item.currency,
                "reference": item.reference,
            }
            for item in order.tenders.all()
        ],
        "totals": {
            "subtotal": str(order.subtotal),
            "discount": str(order.discount),
            "tax": str(order.tax),
            "total": str(order.total),
            "received": str(order.amount_received),
            "change": str(order.change_amount),
            "currency": order.tenders.order_by("id").values_list("currency", flat=True).first() or "",
        },
    }
