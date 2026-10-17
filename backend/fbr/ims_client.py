"""HTTP client for the FBR Tier-1 IMS Software Fiscal Component.

Two transports, selected by ``FBRConfiguration.ims_use_cloud``:

* **Local** (default) — the fiscal component self-hosted on the POS PC
  (``http://localhost:8524/api/IMSFiscal/...``). Health probe is
  ``GET /api/IMSFiscal/get`` → ``["Service is responding"]``; fiscalization is
  ``POST /api/IMSFiscal/GetInvoiceNumberByModel`` →
  ``{"InvoiceNumber": "...", "Code": "100", "Response": "...", "Errors": null}``.
  No bearer header — the component is bound to the POS registration at install
  time. The component itself relays recorded invoices to FBR asynchronously.

* **Cloud** — for cloud-hosted POS, ``POST`` the same document with a Bearer
  token to the ``Live/PostData`` endpoints:
  sandbox ``https://esp.fbr.gov.pk:8244/FBR/v1/api/Live/PostData``,
  production ``https://gw.fbr.gov.pk/imsp/v1/api/Live/PostData``.
  Response echoes ``FBRInvoiceNumber`` instead of ``InvoiceNumber``.

Security posture: the local base URL is re-validated against the platform
allowlist (``fbr.urlguard``) on every call, production always verifies TLS,
and transport errors never embed remote response bodies (they may only carry
the configured URL and the HTTP status), so a mis-tenant URL cannot be used to
introspect internal services through stored error strings.
"""
import contextvars
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import requests

from .constants import (
    ENVIRONMENT_PRODUCTION,
    IMS_CLOUD_ENDPOINTS,
    IMS_LOCAL_BASE_URL_DEFAULT,
    IMS_LOCAL_FISCALIZE_PATH,
    IMS_LOCAL_HEALTH_PATH,
    IMS_SUCCESS_CODE,
)
from .transport import (
    AMBIGUOUS_HTTP_STATUSES,
    OUTCOME_FAILED,
    UNAVAILABLE_HTTP_STATUSES,
    AmbiguousHTTPResponse,
    classify_transport_outcome,
)
from .urlguard import validate_ims_local_base_url

logger = logging.getLogger(__name__)

# Only statuses where the server says it did NOT take the request are retried
# in-call. 500/502/504 may come after the invoice was recorded: they end the
# call as UNKNOWN (reconcile before any resend). Cashier audit E2.
RETRY_HTTP_STATUSES = UNAVAILABLE_HTTP_STATUSES

INTERACTIVE_CONNECT_TIMEOUT_SECONDS = 5

_interactive_budget = contextvars.ContextVar("fbr_ims_interactive_budget", default=None)


@contextmanager
def interactive_budget(seconds):
    """Bound IMS fiscalization calls made inside the block (cashier waiting).

    Inside the block ``fiscalize`` makes exactly one attempt, never sleeps,
    and uses ``min(configured timeout, seconds)`` as its timeout. Whatever is
    not finished in time is left to ``fbr_process_pending`` (FAILED) or to
    reconciliation (UNKNOWN). ``None``/``0`` leaves the call unbounded.
    """
    token = _interactive_budget.set(seconds if seconds and seconds > 0 else None)
    try:
        yield
    finally:
        _interactive_budget.reset(token)


class IMSTransportError(Exception):
    """The fiscal component could not be reached or returned an unusable body."""


@dataclass
class IMSResponse:
    """Parsed body of an IMS fiscalization call."""

    invoice_number: str = ""   # InvoiceNumber (local) / FBRInvoiceNumber (cloud)
    code: str = ""             # "100" on success
    message: str = ""          # "Response" — e.g. "Invoice received successfully"
    errors: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    http_status: int | None = None

    @property
    def accepted(self):
        return str(self.code) == IMS_SUCCESS_CODE and bool(self.invoice_number)


def parse_ims_response(body, http_status=None):
    if not isinstance(body, dict):
        raise IMSTransportError("IMS returned a non-object response body.")
    invoice_number = body.get("InvoiceNumber", body.get("FBRInvoiceNumber", "")) or ""
    code = body.get("Code", "")
    message = body.get("Response", body.get("Message", "")) or ""
    errors = _parse_errors(body)
    return IMSResponse(
        invoice_number=str(invoice_number),
        code=str(code),
        message=str(message),
        errors=errors,
        raw=body,
        http_status=http_status,
    )


def _parse_errors(body):
    errors = body.get("Errors")
    if errors is None:
        errors = []
    if isinstance(errors, dict):
        errors = errors.get("$values", [])
    if not isinstance(errors, list):
        errors = [errors]
    return [str(e) for e in errors]


class IMSFiscalClient:
    """Fiscalizes invoices via the tenant's IMS component (local or cloud)."""

    def __init__(self, configuration, *, session=None, sleep=time.sleep):
        self.configuration = configuration
        self.session = session or requests.Session()
        self._sleep = sleep

    # -- addressing ---------------------------------------------------------
    @property
    def base_url(self):
        if self.configuration.ims_use_cloud:
            return IMS_CLOUD_ENDPOINTS[self.configuration.environment]
        return (self.configuration.ims_local_base_url or IMS_LOCAL_BASE_URL_DEFAULT).rstrip("/")

    @property
    def fiscalize_url(self):
        if self.configuration.ims_use_cloud:
            return self.base_url  # full Live/PostData endpoint
        return f"{self.base_url}{IMS_LOCAL_FISCALIZE_PATH}"

    @property
    def health_url(self):
        return f"{self.base_url}{IMS_LOCAL_HEALTH_PATH}"

    @property
    def headers(self):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.configuration.ims_use_cloud:
            headers["Authorization"] = f"Bearer {self.configuration.security_token}"
        return headers

    # -- guards -------------------------------------------------------------
    def _validate_local_url(self):
        """Defense-in-depth SSRF guard, independent of model validation."""
        if not self.configuration.ims_use_cloud:
            try:
                validate_ims_local_base_url(self.base_url)
            except ValueError as exc:
                raise IMSTransportError(str(exc)) from None

    def _production_guard(self):
        if self.configuration.environment == ENVIRONMENT_PRODUCTION and not self.configuration.verify_tls:
            raise IMSTransportError("TLS verification cannot be disabled for production.")

    # -- calls --------------------------------------------------------------
    def health_check(self):
        """GET the local service probe; True when it answers "Service is responding"."""
        if self.configuration.ims_use_cloud:
            raise IMSTransportError("Health probing only applies to the locally installed component.")
        self._validate_local_url()
        self._production_guard()
        url = self.health_url
        try:
            response = self.session.get(
                url, timeout=self.configuration.timeout_seconds,
                verify=self.configuration.verify_tls,
            )
        except requests.RequestException:
            raise IMSTransportError("Could not reach the IMS fiscal component.") from None
        if response.status_code != 200 or "service is responding" not in response.text.lower():
            # Body excerpt intentionally omitted — never leak remote content.
            raise IMSTransportError(
                f"The IMS fiscal component answered with an unexpected response (HTTP {response.status_code})."
            )
        return True

    def fiscalize(self, payload):
        """POST the invoice document and return the parsed fiscal response."""
        self._validate_local_url()
        self._production_guard()
        url = self.fiscalize_url
        attempts = max(1, self.configuration.max_retries + 1)
        timeout = self.configuration.timeout_seconds
        budget = _interactive_budget.get()
        if budget:
            attempts = 1
            read = min(timeout, budget) if timeout else budget
            # (connect, read): a component that does not accept the connection
            # within a few seconds is provably not processing this invoice.
            timeout = (min(read, INTERACTIVE_CONNECT_TIMEOUT_SECONDS), read)
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=timeout,
                    verify=self.configuration.verify_tls,
                )
            except requests.RequestException as exc:
                last_error = IMSTransportError("Could not reach the IMS endpoint.")
                # Chain the cause so the service layer can tell a read timeout
                # (may have been fiscalized -> UNKNOWN) from a refused connect.
                last_error.__cause__ = exc
                if classify_transport_outcome(last_error) != OUTCOME_FAILED:
                    # The document may already have been recorded: never
                    # re-POST it automatically (duplicate fiscalization risk).
                    raise last_error
            else:
                if response.status_code in AMBIGUOUS_HTTP_STATUSES:
                    # Delivered, then a server error: possibly recorded.
                    # Never re-POST; the service layer records UNKNOWN.
                    error = IMSTransportError(
                        f"The IMS endpoint responded with HTTP {response.status_code}."
                    )
                    error.__cause__ = AmbiguousHTTPResponse(response.status_code)
                    raise error
                if response.status_code in RETRY_HTTP_STATUSES:
                    last_error = IMSTransportError(
                        f"The IMS endpoint responded with HTTP {response.status_code}."
                    )
                else:
                    try:
                        body = response.json()
                    except ValueError:
                        # Body excerpt intentionally omitted — never leak remote content.
                        raise IMSTransportError(
                            f"The IMS endpoint returned a non-JSON response (HTTP {response.status_code})."
                        ) from None
                    return parse_ims_response(body, http_status=response.status_code)
            logger.warning("IMS fiscalization attempt %s/%s failed: %s", attempt, attempts, last_error)
            if attempt < attempts:
                self._sleep(min(2 ** (attempt - 1), 8))
        raise last_error


__all__ = [
    "IMSResponse",
    "IMSTransportError",
    "IMSFiscalClient",
    "interactive_budget",
    "parse_ims_response",
]
