"""OpenAPI helpers for legacy APIViews and the POS token scheme.

The repository contains many service-backed APIViews that return JSON directly
rather than using GenericAPIView serializers. This module keeps those routes in
the API contract with an explicit generic JSON object instead of silently
omitting them from the generated specification.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import build_serializer_context


class GenericJSONPayloadSerializer(serializers.Serializer):
    """Fallback envelope for raw JSON APIView payloads.

    Endpoint-specific serializers still take precedence whenever a view exposes
    one. This fallback is used only to document a route whose implementation
    returns a service-generated JSON object/list without a serializer contract.
    """

    data = serializers.JSONField(required=False)


class LenientAutoSchema(AutoSchema):
    """Keep raw APIViews in the schema without emitting resolver errors."""

    def get_operation_id(self) -> str:
        # Path-derived IDs remain stable and cannot collide when collection and
        # detail routes share the same view class or method name.
        parts = [part for part in self.path.strip("/").split("/") if part]
        normalized = []
        for part in parts:
            if part.startswith("{") and part.endswith("}"):
                normalized.append("by_" + part[1:-1])
            else:
                normalized.append(part.replace("-", "_hyphen_"))
        return "_".join([self.method.lower(), *(normalized or ["root"])])

    def _get_serializer(self):  # type: ignore[override]
        view = self.view
        context = build_serializer_context(view)
        try:
            if isinstance(view, GenericAPIView):
                if view.__class__.get_serializer == GenericAPIView.get_serializer:
                    return view.get_serializer_class()(context=context)
                return view.get_serializer(context=context)
            if isinstance(view, APIView):
                get_serializer = getattr(view, "get_serializer", None)
                if callable(get_serializer):
                    return get_serializer(context=context)
                get_serializer_class = getattr(view, "get_serializer_class", None)
                if callable(get_serializer_class):
                    return get_serializer_class()(context=context)
                serializer_class = getattr(view, "serializer_class", None)
                if serializer_class:
                    return serializer_class
        except Exception:
            # The endpoint remains documented as generic JSON while runtime
            # behavior continues to be governed by the actual view code.
            pass
        return GenericJSONPayloadSerializer(context=context)


class ExpiringTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    """Document Authorization: Token <key> used by the POS backend."""

    target_class = "pos.authentication.ExpiringTokenAuthentication"
    name = "ExpiringTokenAuth"

    def get_security_definition(self, auto_schema):  # type: ignore[no-untyped-def]
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Send `Authorization: Token <key>`. Tokens expire after inactivity and may be revoked.",
        }
