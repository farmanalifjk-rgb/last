"""Development-only, local Tier-1 IMS simulator.

This module never imports or calls the production IMS transport. Simulator
requests and their complete attempt history are persisted per tenant. It is
not an FBR/PRAL service and its TEST numbers must never be represented as
FBR-issued invoice numbers.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from saas.permissions import HasActiveTenant, TenantRBACPermission

from .constants import ENVIRONMENT_SANDBOX
from .models import FBRSimulatorExchange

# Match the names emitted by fbr.ims_payload.build_ims_invoice_payload.
REQUIRED_HEADER_FIELDS = (
    "POSID", "USIN", "DateTime", "TotalSaleValue", "TotalTaxCharged",
    "TotalQuantity", "Discount", "FurtherTax", "TotalBillAmount",
    "PaymentMode", "InvoiceType", "Items",
)
REQUIRED_ITEM_FIELDS = (
    "ItemCode", "ItemName", "PCTCode", "Quantity", "TaxRate",
    "SaleValue", "Discount", "FurtherTax", "TaxCharged", "TotalAmount",
    "InvoiceType",
)
MONEY_FIELDS = (
    "TotalSaleValue", "TotalTaxCharged", "Discount", "FurtherTax",
    "TotalBillAmount",
)
ITEM_MONEY_FIELDS = ("SaleValue", "Discount", "FurtherTax", "TaxCharged", "TotalAmount")
SIMULATOR_SUCCESS_CODE = "100"
SIMULATOR_REJECTION_CODE = "101"  # Internal simulator code; not an official FBR code.
SIMULATOR_FAILURE_CODE = "500"
_ALLOWED_OUTCOMES = {"accepted", "rejected", "failed"}


def simulator_is_available(environment=ENVIRONMENT_SANDBOX):
    """One shared fail-closed guard for API views and the in-process client."""
    deployment = str(getattr(settings, "DJANGO_ENV", "development")).lower()
    enabled = bool(getattr(settings, "FBR_SIMULATOR_ENABLED", False))
    mode = getattr(settings, "FBR_SIMULATOR_MODE", "disabled")
    return deployment in {"development", "test"} and enabled and mode == "sandbox" and environment == ENVIRONMENT_SANDBOX


def _decimal(value, label, errors):
    if isinstance(value, bool) or value is None:
        errors.append(f"{label} must be a non-negative number.")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be a non-negative number.")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a non-negative finite number.")
        return None
    if result.adjusted() > 15 or len(result.as_tuple().digits) > 28:
        errors.append(f"{label} exceeds the supported numeric precision.")
        return None
    return result


def _money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _enum_number(value, allowed):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if str(value).strip() not in {str(number), f"{number}.0"} or number not in allowed:
        return None
    return number


def validate_ims_invoice(payload):
    """Return IMS-shaped validation errors for headers, lines, taxes and totals."""
    errors = []
    if not isinstance(payload, dict):
        return ["Request body must be a JSON object."]

    for field in REQUIRED_HEADER_FIELDS:
        if field not in payload or payload[field] is None or payload[field] == "":
            errors.append(f"{field} is required.")
    if errors:
        return errors

    pos_id = payload["POSID"]
    if (isinstance(pos_id, bool) or not str(pos_id).isdigit()
            or len(str(pos_id)) > 19 or int(pos_id) <= 0):
        errors.append("POSID must be a positive integer with at most 19 digits.")

    usin = payload.get("USIN")
    if not isinstance(usin, str) or not usin.strip() or len(usin.strip()) > 50:
        errors.append("USIN must be a non-empty string of at most 50 characters.")

    date_value = payload.get("DateTime")
    if not isinstance(date_value, str) or parse_datetime(date_value) is None:
        errors.append("DateTime must be a valid ISO-8601 date-time.")

    if _enum_number(payload.get("PaymentMode"), set(range(1, 7))) is None:
        errors.append("PaymentMode must be a supported IMS payment mode (1-6).")
    if _enum_number(payload.get("InvoiceType"), {1, 2, 3}) is None:
        errors.append("InvoiceType must be a supported IMS invoice type (1-3).")

    items = payload.get("Items")
    if not isinstance(items, list) or not items:
        errors.append("Items must be a non-empty array.")
        return errors

    item_totals = {field: Decimal("0") for field in ITEM_MONEY_FIELDS}
    quantity_total = Decimal("0")
    for index, item in enumerate(items):
        prefix = f"Items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        missing = [field for field in REQUIRED_ITEM_FIELDS
                   if field not in item or item[field] is None or item[field] == ""]
        for field in missing:
            errors.append(f"{prefix}.{field} is required.")
        if missing:
            continue
        for field, max_length in (("ItemCode", 50), ("ItemName", 150), ("PCTCode", 8)):
            value = item[field]
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}.{field} must be a non-empty string.")
            elif len(value.strip()) > max_length:
                errors.append(f"{prefix}.{field} must be at most {max_length} characters.")
            elif field == "PCTCode" and not value.strip().isdigit():
                errors.append(f"{prefix}.PCTCode must contain digits only.")

        quantity = _decimal(item.get("Quantity"), f"{prefix}.Quantity", errors)
        if quantity is not None:
            if quantity <= 0:
                errors.append(f"{prefix}.Quantity must be greater than zero.")
            quantity_total += quantity
        rate = _decimal(item.get("TaxRate"), f"{prefix}.TaxRate", errors)
        if rate is not None and rate > Decimal("100"):
            errors.append(f"{prefix}.TaxRate must not exceed 100 percent.")
        values = {}
        for field in ITEM_MONEY_FIELDS:
            value = _decimal(item.get(field), f"{prefix}.{field}", errors)
            values[field] = value
            if value is not None:
                item_totals[field] += value

        if _enum_number(item.get("InvoiceType"), {1, 3, 11, 12}) is None:
            errors.append(f"{prefix}.InvoiceType must be a supported IMS item type (1, 3, 11, or 12).")

        sale = values.get("SaleValue")
        tax, further, total = (values.get("TaxCharged"), values.get("FurtherTax"), values.get("TotalAmount"))
        if rate is not None and sale is not None and tax is not None:
            expected_tax = _money(sale * rate / Decimal("100"))
            if _money(tax) != expected_tax:
                errors.append(f"{prefix}.TaxCharged does not match SaleValue x TaxRate.")
        if all(value is not None for value in (sale, tax, further, total)):
            if _money(total) != _money(sale + tax + further):
                errors.append(f"{prefix}.TotalAmount must equal SaleValue + TaxCharged + FurtherTax.")

    header_totals = {field: _decimal(payload.get(field), field, errors) for field in MONEY_FIELDS}
    header_quantity = _decimal(payload.get("TotalQuantity"), "TotalQuantity", errors)

    for header, item_field in (
        ("TotalSaleValue", "SaleValue"),
        ("TotalTaxCharged", "TaxCharged"),
        ("Discount", "Discount"),
        ("FurtherTax", "FurtherTax"),
    ):
        value = header_totals.get(header)
        if value is not None and _money(value) != _money(item_totals[item_field]):
            errors.append(f"{header} does not match the sum of Items.{item_field}.")

    bill = header_totals.get("TotalBillAmount")
    if bill is not None and _money(bill) != _money(item_totals["TotalAmount"]):
        errors.append("TotalBillAmount does not match the sum of Items.TotalAmount.")
    if header_quantity is not None and header_quantity != quantity_total:
        errors.append("TotalQuantity does not match the sum of Items.Quantity.")
    return errors


def _error_response(message, errors=None, *, code=SIMULATOR_REJECTION_CODE):
    return {
        "InvoiceNumber": "",
        "Code": code,
        "Response": message,
        "Errors": errors or None,
    }


def _json_safe(payload):
    # Request data is JSON-safe via DRF but direct clients may pass Decimals.
    return json.loads(json.dumps(payload, default=str))


def _make_response(status, errors, invoice_number=""):
    if status == FBRSimulatorExchange.STATUS_ACCEPTED:
        return {
            "InvoiceNumber": invoice_number,
            "Code": SIMULATOR_SUCCESS_CODE,
            "Response": "SIMULATED TEST invoice generated successfully. NOT ISSUED BY FBR.",
            "Errors": None,
        }
    if status == FBRSimulatorExchange.STATUS_FAILED:
        return _error_response("Local IMS simulator is configured to fail this request.",
                               ["Simulated component failure; no external request was made."],
                               code=SIMULATOR_FAILURE_CODE)
    message = "Invoice validation failed." if errors else "Rejected by configured simulator outcome."
    return _error_response(message, errors or ["Rejected by configured simulator outcome."])


@transaction.atomic
def process_simulated_invoice(*, tenant, environment, payload, outcome=None):
    """Validate, persist, and return one tenant-scoped idempotent IMS exchange."""
    if not simulator_is_available(environment):
        raise RuntimeError("The local IMS simulator is not enabled in this development environment.")
    outcome = str(outcome or getattr(settings, "FBR_SIMULATOR_OUTCOME", "accepted")).lower()
    if outcome not in _ALLOWED_OUTCOMES:
        raise ValueError("FBR_SIMULATOR_OUTCOME must be accepted, rejected, or failed.")

    from saas.models import Tenant
    if not Tenant.objects.select_for_update().filter(pk=tenant.pk).exists():
        raise RuntimeError("Simulator tenant not found.")

    safe_payload = _json_safe(payload)
    errors = validate_ims_invoice(safe_payload)
    usin = safe_payload.get("USIN", "") if isinstance(safe_payload, dict) else ""
    valid_usin = isinstance(usin, str) and bool(usin.strip()) and len(usin.strip()) <= 50
    usin = usin.strip() if valid_usin else ""
    idempotency_key = usin if valid_usin else f"invalid-{uuid.uuid4().hex}"
    exchange = FBRSimulatorExchange.objects.select_for_update().filter(
        tenant=tenant, environment=environment, idempotency_key=idempotency_key,
    ).first()
    payload_fingerprint = hashlib.sha256(
        json.dumps(safe_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    now = datetime.now(datetime_timezone.utc).isoformat()

    if exchange is None:
        exchange = FBRSimulatorExchange.objects.create(
            tenant=tenant,
            environment=environment,
            usin=usin,
            idempotency_key=idempotency_key,
            request_payload=safe_payload,
            request_fingerprint=payload_fingerprint,
            response_payload={},
            status=FBRSimulatorExchange.STATUS_PENDING,
            attempt_history=[],
        )
    elif exchange.request_fingerprint != payload_fingerprint:
        # An accepted USIN cannot be reused with a different document body.
        conflict = _error_response("USIN has already been used for a different invoice payload.",
                                   ["USIN is an idempotency key and its invoice payload cannot be changed."])
        exchange.attempt_history.append({
            "at": now, "outcome": outcome, "status": FBRSimulatorExchange.STATUS_REJECTED,
            "request": safe_payload, "response": conflict, "idempotency_conflict": True,
        })
        exchange.attempts += 1
        exchange.save(update_fields=["attempt_history", "attempts", "updated_at"])
        return exchange, conflict, FBRSimulatorExchange.STATUS_REJECTED

    # An accepted exchange is immutable in its result: retries get the same
    # number even if the configured test outcome changes later.
    if exchange.status == FBRSimulatorExchange.STATUS_ACCEPTED:
        response = exchange.response_payload
        status = exchange.status
    else:
        effective_status = FBRSimulatorExchange.STATUS_REJECTED if errors or outcome == "rejected" else (
            FBRSimulatorExchange.STATUS_FAILED if outcome == "failed" else FBRSimulatorExchange.STATUS_ACCEPTED
        )
        if effective_status == FBRSimulatorExchange.STATUS_ACCEPTED and not exchange.simulated_invoice_number:
            # PK-derived numbering is collision-free; the column's unconditional
            # unique constraint is the database-enforced backstop.
            exchange.simulated_invoice_number = f"SIM-SBX-{tenant.pk}-{exchange.pk:010d}"
        response = _make_response(effective_status, errors, exchange.simulated_invoice_number)
        status = effective_status
        exchange.status = status
        exchange.configured_outcome = outcome
        exchange.response_payload = response
        exchange.save(update_fields=["status", "configured_outcome", "simulated_invoice_number",
                                     "response_payload", "updated_at"])

    exchange.attempt_history.append({
        "at": now,
        "outcome": outcome,
        "status": status,
        "request": safe_payload,
        "response": response,
    })
    exchange.attempts += 1
    exchange.save(update_fields=["attempt_history", "attempts", "updated_at"])
    return exchange, response, status


class IMSFiscalSimulatorView(APIView):
    """Authenticated local IMS endpoint; available only in development/test."""

    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "fiscal"
    rbac_action = "create"
    environment = ENVIRONMENT_SANDBOX

    def initial(self, request, *args, **kwargs):
        if not simulator_is_available(self.environment):
            from rest_framework.exceptions import NotFound
            raise NotFound("FBR simulator is disabled outside development/test.")
        super().initial(request, *args, **kwargs)

    def get_permissions(self):
        self.rbac_action = "view" if self.request.method == "GET" else "create"
        return super().get_permissions()

    def get(self, request):
        return Response(["Service is responding"])

    def post(self, request):
        _, body, status = process_simulated_invoice(
            tenant=request.tenant, environment=self.environment, payload=request.data,
        )
        return Response(body, status=503 if status == FBRSimulatorExchange.STATUS_FAILED else 200)


class SandboxIMSSimulatorView(IMSFiscalSimulatorView):
    environment = ENVIRONMENT_SANDBOX


class IMSSimulatorClient:
    """In-process IMS client used only by the existing submission service."""

    is_simulator = True

    def __init__(self, configuration):
        if not getattr(configuration, "use_simulator", False) or not simulator_is_available(configuration.environment):
            raise RuntimeError("The development-only IMS simulator is not enabled for this configuration.")
        self.configuration = configuration

    def health_check(self):
        return True

    def fiscalize(self, payload):
        from .ims_client import IMSResponse, IMSTransportError

        exchange, raw, status = process_simulated_invoice(
            tenant=self.configuration.tenant,
            environment=self.configuration.environment,
            payload=payload,
        )
        if status == FBRSimulatorExchange.STATUS_FAILED:
            error = IMSTransportError("Local IMS simulator configured a simulated failure; no network request was made.")
            error.simulator_response = raw
            raise error
        return IMSResponse(
            invoice_number=raw.get("InvoiceNumber", ""),
            code=str(raw.get("Code", "")),
            message=raw.get("Response", ""),
            errors=raw.get("Errors") or [],
            raw=raw,
            http_status=200,
        )
