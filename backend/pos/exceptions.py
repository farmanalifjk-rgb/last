"""Canonical API error responses for the POS backend."""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def _field_errors(detail: Any) -> dict[str, list[str]]:
    if not isinstance(detail, dict):
        return {}
    fields: dict[str, list[str]] = {}
    for key, value in detail.items():
        values = value if isinstance(value, list) else [value]
        fields[str(key)] = [str(item) for item in values]
    return fields


def canonical_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Return one stable envelope for all handled DRF errors."""
    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API exception", exc_info=exc)
        return Response(
            {
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected server error occurred.",
                    "fields": {},
                },
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    if isinstance(exc, ValidationError):
        code = "VALIDATION_ERROR"
        message = "Request validation failed."
        fields = _field_errors(detail)
        # Business-rule errors raised as ValidationError("text") or as {"detail": "text"}
        # keep their text, so the client can show the reason instead of a generic message.
        if isinstance(detail, list) and detail:
            message = " ".join(str(item) for item in detail)
        elif isinstance(detail, dict) and set(detail.keys()) == {"detail"}:
            message = " ".join(str(item) for item in (detail["detail"] if isinstance(detail["detail"], list) else [detail["detail"]]))
    elif isinstance(exc, DjangoValidationError):
        code = "VALIDATION_ERROR"
        message = "Request validation failed."
        fields = _field_errors(getattr(exc, "message_dict", {}))
        if not fields and getattr(exc, "messages", None):
            fields = {"non_field_errors": [str(message) for message in exc.messages]}
    elif isinstance(exc, APIException):
        code = getattr(exc, "default_code", "API_ERROR").upper()
        message = str(detail.get("detail", detail)) if isinstance(detail, dict) else str(detail)
        fields = {}
    else:
        code = "API_ERROR"
        message = str(detail)
        fields = {}

    response.data = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "fields": fields,
        },
    }
    return response
