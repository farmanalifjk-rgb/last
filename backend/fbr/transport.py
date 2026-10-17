"""Shared transport-outcome classification for fiscal submissions.

A network timeout is NOT proof that the fiscalization never happened: the
request may have been delivered and the response lost. Each submission is
therefore classified as either:

* ``failed``      — the request provably never reached the endpoint (DNS
                    failure, connection refused, TCP connect timeout) or the
                    endpoint answered unusably (non-JSON body); or
* ``unknown``     — the request may have been processed (read timeout, an
                    HTTP 500/502/504 from the endpoint or a gateway in front
                    of it, or any other ambiguous transport condition); the
                    submission moves
                    to ``STATUS_UNKNOWN`` and MUST be reconciled before another
                    external attempt (see ``services.reconcile_submission``).
"""
import requests

OUTCOME_FAILED = "failed"
OUTCOME_UNKNOWN = "unknown"

# The request reached the endpoint (or a gateway in front of it) and the
# answer was a server error. The invoice may have been recorded before the
# error was produced, so these are never resent automatically (cashier audit
# E2). 429/503 are different: the server says it did not take the request.
AMBIGUOUS_HTTP_STATUSES = frozenset({500, 502, 504})
UNAVAILABLE_HTTP_STATUSES = frozenset({429, 503})


class AmbiguousHTTPResponse(Exception):
    """Cause attached to a transport error when the HTTP status is ambiguous."""

    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def classify_transport_outcome(exc):
    """Return ``unknown`` / ``failed`` for a client transport error.

    ``exc`` is the raised FBRTransportError / IMSTransportError; the original
    ``requests`` exception travels as its ``__cause__`` (both clients raise
    with ``from exc``). The classification errs on the conservative side: the
    cost asymmetry is one reconciliation step versus a duplicate fiscal
    invoice.
    """
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, AmbiguousHTTPResponse):
        # Delivered; a server error may have come after the invoice was recorded.
        return OUTCOME_UNKNOWN
    if isinstance(cause, requests.exceptions.ConnectTimeout):
        # TCP connection never established — the request was not delivered.
        return OUTCOME_FAILED
    if isinstance(cause, requests.exceptions.Timeout):
        # Read timeout / overall timeout — request delivered, response lost.
        return OUTCOME_UNKNOWN
    if isinstance(cause, requests.exceptions.ConnectionError):
        # Refused / DNS / connection dropped before a usable response.
        return OUTCOME_FAILED
    if cause is None:
        # No underlying cause (e.g. non-JSON body parse error): the endpoint
        # answered, so the outcome is known-failed.
        return OUTCOME_FAILED
    # Anything else ambiguous (e.g. chunked stream died mid-body) — treat as
    # unknown and require reconciliation.
    return OUTCOME_UNKNOWN


__all__ = [
    "AMBIGUOUS_HTTP_STATUSES",
    "AmbiguousHTTPResponse",
    "OUTCOME_FAILED",
    "OUTCOME_UNKNOWN",
    "UNAVAILABLE_HTTP_STATUSES",
    "classify_transport_outcome",
]
