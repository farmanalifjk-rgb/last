"""HTTP client for the FBR DI API v1.12 (postinvoicedata / validateinvoicedata)."""
import logging
import time
from dataclasses import dataclass, field

import requests

from .constants import SUCCESS_STATUS_CODE, SUCCESS_STATUS_CODE_LEGACY
from .transport import AMBIGUOUS_HTTP_STATUSES, AmbiguousHTTPResponse

logger = logging.getLogger(__name__)

RETRY_HTTP_STATUSES = {429, 500, 502, 503, 504}


class FBRTransportError(Exception):
    """The API could not be reached or returned an unusable response."""


@dataclass
class FBRResponse:
    """Parsed body of a DI API call (v1.12 or legacy v1.0)."""

    # v1.12 canonical
    invoice_number: str = ""  # invoiceNumber (v1.12) or result (v1.0)
    dated: str = ""
    status_code: str | int | None = None  # validationResponse.statusCode "00"/"01" or legacy 200
    error_message: str = ""  # validationResponse.error or errorMessage
    error_code: str = ""
    errors: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    http_status: int | None = None
    # full v1.12 validationResponse for storage
    validation_response: dict = field(default_factory=dict)
    invoice_statuses: list = field(default_factory=list)
    # legacy aliases
    result: str = ""
    timestamp: str = ""

    @property
    def accepted(self):
        # Never treat an application-level success body as accepted when the
        # HTTP transport itself failed. This protects against proxies/gateways
        # returning a misleading cached or partial body with a 5xx status.
        if self.http_status is not None and not (200 <= int(self.http_status) < 300):
            return False
        # v1.12 success is "00" string
        if self.status_code == SUCCESS_STATUS_CODE and bool(self.invoice_number):
            return True
        # legacy fallback 200
        if self.status_code == SUCCESS_STATUS_CODE_LEGACY and bool(self.result):
            return True
        # also handle string "00"
        if str(self.status_code) == "00" and bool(self.invoice_number):
            return True
        return False


def _parse_errors_v112(body):
    # v1.12 validationResponse may contain error, errorCode, invoiceStatuses
    vr = body.get("validationResponse") or {}
    errs = []
    if isinstance(vr, dict):
        if vr.get("error"):
            errs.append(str(vr.get("error")))
        if vr.get("errorCode"):
            errs.append(f"{vr.get('errorCode')}: {vr.get('error')}")
        for item in vr.get("invoiceStatuses") or []:
            if isinstance(item, dict) and item.get("error"):
                errs.append(f"Item {item.get('itemSNo')}: {item.get('error')} ({item.get('errorCode')})")
    # legacy $values style
    legacy_errs = body.get("errors")
    if isinstance(legacy_errs, dict):
        legacy_errs = legacy_errs.get("$values", [])
    if isinstance(legacy_errs, list):
        errs.extend([str(e) for e in legacy_errs])
    elif legacy_errs:
        errs.append(str(legacy_errs))
    # generic errors field
    if body.get("error") and body.get("error") not in errs:
        errs.append(str(body.get("error")))
    return errs


def _parse_errors_legacy(body):
    errors = body.get("errors")
    if isinstance(errors, dict):
        errors = errors.get("$values", [])
    if errors is None:
        errors = []
    if not isinstance(errors, list):
        errors = [str(errors)]
    return [str(error) for error in errors]


def parse_response(body, http_status=None):
    if not isinstance(body, dict):
        raise FBRTransportError(f"FBR returned a non-object response body: {body!r}")
    # Detect v1.12 shape: has invoiceNumber or validationResponse
    if "invoiceNumber" in body or "validationResponse" in body:
        vr = body.get("validationResponse") or {}
        status_code = vr.get("statusCode") if isinstance(vr, dict) else None
        # fallback to top-level statusCode if present (some errors)
        if status_code is None:
            status_code = body.get("statusCode")
        error = vr.get("error") if isinstance(vr, dict) else "" or body.get("error") or ""
        error_code = vr.get("errorCode") if isinstance(vr, dict) else "" or ""
        invoice_number = body.get("invoiceNumber") or body.get("result") or ""
        dated = body.get("dated") or body.get("timestamp") or body.get("timeStamp") or ""
        invoice_statuses = vr.get("invoiceStatuses") if isinstance(vr, dict) else []
        return FBRResponse(
            invoice_number=str(invoice_number or ""),
            result=str(invoice_number or ""),
            dated=str(dated or ""),
            timestamp=str(dated or ""),
            status_code=status_code,
            error_message=str(error or ""),
            error_code=str(error_code or ""),
            errors=_parse_errors_v112(body),
            raw=body,
            http_status=http_status,
            validation_response=vr if isinstance(vr, dict) else {},
            invoice_statuses=invoice_statuses if isinstance(invoice_statuses, list) else [],
        )
    # Legacy v1.0 shape
    return FBRResponse(
        status_code=body.get("statusCode"),
        error_message=str(body.get("errorMessage") or ""),
        result=str(body.get("result") or ""),
        invoice_number=str(body.get("result") or ""),
        timestamp=str(body.get("timestamp") or body.get("timeStamp") or ""),
        dated=str(body.get("timestamp") or body.get("timeStamp") or ""),
        errors=_parse_errors_legacy(body),
        raw=body,
        http_status=http_status,
        validation_response={},
    )


class FBRClient:
    """Posts invoice documents with the tenant's bearer security token (PRAL)."""

    def __init__(self, configuration, *, session=None, sleep=time.sleep):
        self.configuration = configuration
        self.session = session or requests.Session()
        self._sleep = sleep

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.configuration.security_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _production_guard(self):
        """TLS verification is mandatory in production (defense in depth)."""
        if self.configuration.environment == "production" and not self.configuration.verify_tls:
            raise FBRTransportError("TLS verification cannot be disabled for production.")

    def _post(self, url, payload, *, allow_retries=False):
        self._production_guard()
        # Fiscalization POSTs are not automatically retried: the remote system
        # may have accepted the invoice even when the response was lost. The
        # service layer then records UNKNOWN and requires reconciliation.
        attempts = max(1, self.configuration.max_retries + 1) if allow_retries else 1
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=self.configuration.timeout_seconds,
                    verify=self.configuration.verify_tls,
                )
            except requests.RequestException as exc:
                last_error = FBRTransportError(f"Could not reach FBR at {url}: {exc}")
                # Keep the requests exception as the cause: the service layer
                # classifies read timeouts as UNKNOWN (reconcile before retry)
                # from it. Without it every timeout looked "provably failed".
                last_error.__cause__ = exc
            else:
                if not 200 <= response.status_code < 300:
                    last_error = FBRTransportError(
                        f"FBR responded with HTTP {response.status_code}: {response.text[:500]}"
                    )
                    if not (allow_retries and response.status_code in RETRY_HTTP_STATUSES):
                        if not allow_retries and response.status_code in AMBIGUOUS_HTTP_STATUSES:
                            # An invoice POST that reached FBR (or its gateway)
                            # and got a server error may have been recorded:
                            # classify UNKNOWN, reconcile before any resend.
                            last_error.__cause__ = AmbiguousHTTPResponse(response.status_code)
                        raise last_error
                else:
                    try:
                        body = response.json()
                    except ValueError:
                        raise FBRTransportError(
                            f"FBR returned a non-JSON response (HTTP {response.status_code}): {response.text[:500]}"
                        )
                    return parse_response(body, http_status=response.status_code)
            logger.warning("FBR submission attempt %s/%s failed: %s", attempt, attempts, last_error)
            if attempt < attempts:
                self._sleep(min(2 ** (attempt - 1), 8))
        raise last_error

    def post_invoice(self, payload):
        from .constants import DEFAULT_ENDPOINTS
        url = self.configuration.resolved_endpoint_url
        # resolved_endpoint_url already resolves to di_data/v1/di/postinvoicedata per new constants
        # keep explicit fallback
        if not url:
            url = DEFAULT_ENDPOINTS[self.configuration.environment]
        return self._post(url, payload, allow_retries=False)

    def validate_invoice(self, payload):
        from .constants import DEFAULT_VALIDATE_ENDPOINTS
        # Resolve validate endpoint — use explicit override if endpoint_url contains validate, else use validate map
        if self.configuration.endpoint_url and "validate" in self.configuration.endpoint_url:
            url = self.configuration.endpoint_url
        else:
            url = DEFAULT_VALIDATE_ENDPOINTS[self.configuration.environment]
            if self.configuration.endpoint_url and "postinvoicedata" not in url:
                # if custom override is set for post, use it for validate too? fallback to validate map
                pass
        return self._post(url, payload, allow_retries=True)
