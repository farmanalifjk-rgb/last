from rest_framework import serializers

from .constants import INTEGRATION_MODE_DI
from .models import (
    FBRBuyerProfile,
    FBRConfiguration,
    FBRHSCode,
    FBRProductProfile,
    FBRProvince,
    FBRSubmission,
)


def _same_tenant(serializer, obj, label):
    """Reject objects that belong to another tenant than the request's."""
    tenant = getattr(serializer.context.get("request"), "tenant", None)
    if tenant is not None and obj.tenant_id != tenant.id:
        raise serializers.ValidationError(f"{label} does not belong to the active tenant.")
    return obj


class FBRReferenceSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    numeric_code = serializers.IntegerField(read_only=True)
    description = serializers.CharField(read_only=True)


class FBRProvinceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FBRProvince
        fields = ["id", "code", "description"]


class FBRHSCodeSerializer(serializers.ModelSerializer):
    dotted_code = serializers.CharField(read_only=True)

    class Meta:
        model = FBRHSCode
        fields = ["id", "code", "dotted_code", "description"]


class FBRConfigurationSerializer(serializers.ModelSerializer):
    # The security token is a credential: accepted on write, never echoed back.
    security_token = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=255)
    has_security_token = serializers.SerializerMethodField()
    resolved_endpoint_url = serializers.CharField(read_only=True)
    resolved_seller_province = serializers.CharField(read_only=True)

    class Meta:
        model = FBRConfiguration
        fields = [
            "id", "tenant", "environment", "integration_mode",
            "pos_registration_number", "ims_local_base_url", "ims_use_cloud", "ims_local_confirmed",
            "use_simulator", "security_token", "has_security_token", "bpos_id",
            "seller_ntn_cnic", "seller_business_name", "seller_address",
            "seller_province", "seller_province_text", "resolved_seller_province",
            "distributor_ntn_cnic", "distributor_name",
            "default_transaction_type", "scenario_id", "integrator",
            "endpoint_url", "resolved_endpoint_url",
            "timeout_seconds", "max_retries", "verify_tls", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["tenant", "created_at", "updated_at"]

    def get_has_security_token(self, obj):
        return bool(obj.security_token)

    def validate(self, attrs):
        instance = self.instance or FBRConfiguration()
        for name, value in attrs.items():
            setattr(instance, name, value)
        # ensure tenant is set for clean (when creating via serializer.save tenant not yet set)
        # but clean does not require tenant for these fields
        try:
            instance.clean()
        except Exception as e:
            # If ValidationError with dict, let DRF handle via raising
            raise serializers.ValidationError(getattr(e, "message_dict", str(e)))
        if attrs.get("use_simulator"):
            from .services import _simulator_available_for

            if not _simulator_available_for(instance):
                raise serializers.ValidationError({
                    "use_simulator": (
                        "The IMS simulator is available only in development/test sandbox mode "
                        "(FBR_SIMULATOR_ENABLED / FBR_SIMULATOR_MODE). It never falls back to an external endpoint."
                    ),
                })
        # Uniqueness of (tenant, environment) is enforced by a DB constraint;
        # surface it as a 400 instead of an uncaught IntegrityError (500).
        if self.instance is None:
            tenant = getattr(self.context.get("request"), "tenant", None)
            environment = attrs.get("environment", "sandbox")
            if (
                tenant is not None
                and FBRConfiguration.objects.filter(tenant=tenant, environment=environment).exists()
            ):
                raise serializers.ValidationError(
                    {"environment": "An FBR configuration already exists for this environment — update it instead of creating a second one."}
                )

        # Fiscal-scheme eligibility gate (models.clean can only check this on
        # updates, where the tenant is already set).
        if self.instance is None:
            from .models import tenant_allowed_modes

            tenant = getattr(self.context.get("request"), "tenant", None)
            if tenant is not None:
                allowed = tenant_allowed_modes(tenant)
                mode = attrs.get("integration_mode", INTEGRATION_MODE_DI)
                if mode not in allowed:
                    raise serializers.ValidationError(
                        {"integration_mode": (
                            "This tenant is not eligible for the "
                            f"'{mode}' fiscalization track (allowed: {', '.join(sorted(allowed))}). "
                            "Fiscal eligibility is verified by the platform operator."
                        )}
                    )
        return attrs


class FBRBuyerProfileSerializer(serializers.ModelSerializer):
    resolved_buyer_province = serializers.CharField(read_only=True)

    class Meta:
        model = FBRBuyerProfile
        fields = [
            "id", "tenant", "customer", "ntn_cnic", "registered_name",
            "destination_address", "buyer_province", "buyer_province_text", "resolved_buyer_province",
            "buyer_registration_type", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["tenant", "created_at", "updated_at"]

    def validate_customer(self, customer):
        return _same_tenant(self, customer, "Customer")


class FBRProductProfileSerializer(serializers.ModelSerializer):
    hs_code_value = serializers.CharField(source="hs_code.code", read_only=True)
    hs_code_dotted = serializers.CharField(source="hs_code.dotted_code", read_only=True)
    uom_value = serializers.CharField(source="uom.code", read_only=True)
    uom_description = serializers.CharField(source="uom.description", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = FBRProductProfile
        fields = [
            "id", "tenant", "product", "product_name", "product_sku", "hs_code", "hs_code_value", "hs_code_dotted", "uom", "uom_value", "uom_description",
            "transaction_type", "sro_schedule", "sro_item_serial_no", "product_code",
            "pct_code", "third_schedule", "sales_tax_rate", "retail_price",
            "extra_tax_rate", "further_tax_rate", "fed_payable_rate", "cvt_rate", "st_withheld_rate",
            "withholding_income_tax_rate", "withholding_income_tax_rate_2",
            "withholding_section_1", "withholding_section_2", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["tenant", "created_at", "updated_at"]

    def validate_product(self, product):
        return _same_tenant(self, product, "Product")


_REDACTED = "***"
# Credential-shaped keys that must never be echoed back if an upstream
# request/response payload happens to contain them (defense in depth: the
# FBR bearer token is sent as a header and never stored, but stored upstream
# payloads are arbitrary remote content and are redacted on read).
_SENSITIVE_PAYLOAD_KEYS = {"authorization", "securitytoken", "security_token", "token", "password", "bearer", "secret"}


def _redact_sensitive(value):
    if isinstance(value, dict):
        return {
            key: _REDACTED
            if str(key).replace("-", "_").lower() in _SENSITIVE_PAYLOAD_KEYS
            else _redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


class FBRSubmissionSerializer(serializers.ModelSerializer):
    request_payload = serializers.SerializerMethodField()
    response_payload = serializers.SerializerMethodField()
    validation_response = serializers.SerializerMethodField()
    invoice_number = serializers.SerializerMethodField()
    order_number = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = FBRSubmission
        fields = [
            "id", "tenant", "invoice", "configuration", "environment", "invoice_type", "status",
            "fbr_invoice_number", "status_code", "status_code_legacy", "error_message", "error_code", "errors",
            "request_payload", "response_payload", "validation_response", "response_timestamp",
            "attempts", "is_validate", "invoice_ref_no", "usin", "ims_code", "integration_mode",
            "is_simulated", "created_by", "created_at", "responded_at",
            "invoice_number", "order_number", "allowed_actions",
        ]
        read_only_fields = fields

    def get_invoice_number(self, obj):
        return obj.invoice.invoice_number if obj.invoice_id else None

    def get_order_number(self, obj):
        invoice = obj.invoice if obj.invoice_id else None
        return invoice.order.order_number if invoice is not None and invoice.order_id else None

    def get_allowed_actions(self, obj):
        """What the backend would currently permit for this submission and caller.

        Mirrors fbr.services.retry_submission / reconcile_submission: retry only
        a live rejected/failed attempt whose invoice has no accepted and no other
        pending attempt (fiscal.create); reconcile only an *unknown* outcome
        (fiscal.manage) — an unknown outcome is never retried before it is
        reconciled. The endpoints re-check everything; this only drives the UI.
        """
        from saas.permissions import tenant_member_has_permission

        request = self.context.get("request")
        user = getattr(request, "user", None)
        tenant = getattr(request, "tenant", None)
        invoice_id = obj.invoice_id
        accepted = getattr(obj, "invoice_has_accepted", None)
        if accepted is None:
            accepted = FBRSubmission.objects.filter(
                invoice_id=invoice_id, status=FBRSubmission.STATUS_ACCEPTED, is_validate=False,
            ).exists()
        other_pending = getattr(obj, "invoice_has_other_pending", None)
        if other_pending is None:
            other_pending = FBRSubmission.objects.filter(
                invoice_id=invoice_id, status=FBRSubmission.STATUS_PENDING, is_validate=False,
            ).exclude(pk=obj.pk).exists()
        retry_state = (
            not obj.is_validate
            and obj.status in (FBRSubmission.STATUS_REJECTED, FBRSubmission.STATUS_FAILED)
            and not accepted
            and not other_pending
        )
        reconcile_state = obj.status == FBRSubmission.STATUS_UNKNOWN and not accepted
        return {
            "retry": bool(retry_state and tenant_member_has_permission(user, tenant, "fiscal", "create")),
            "reconcile": bool(reconcile_state and tenant_member_has_permission(user, tenant, "fiscal", "manage")),
        }

    def get_request_payload(self, obj):
        return _redact_sensitive(obj.request_payload)

    def get_response_payload(self, obj):
        return _redact_sensitive(obj.response_payload)

    def get_validation_response(self, obj):
        return _redact_sensitive(obj.validation_response)


__all__ = [
    "FBRBuyerProfileSerializer",
    "FBRConfigurationSerializer",
    "FBRHSCodeSerializer",
    "FBRProvinceSerializer",
    "FBRProductProfileSerializer",
    "FBRReferenceSerializer",
    "FBRSubmissionSerializer",
]
