from rest_framework import serializers
from .models import (
    InvoiceSequence,
    FiscalInvoice,
    FiscalInvoiceLine,
    FiscalDevice,
    FiscalSubmission,
)


class InvoiceSequenceSerializer(serializers.ModelSerializer):
    """Invoice numbering pool.

    Once any invoice has been issued from a sequence its numbering (prefix,
    padding, document type, next number) is locked: changing it could reissue
    or skip numbers already printed on receipts. Name and active flag remain
    editable. Sequences are deactivated, never deleted (invoices PROTECT them).
    """

    NUMBERING_FIELDS = ("prefix", "padding", "document_type", "next_number")
    invoices_issued = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceSequence
        fields = ["id","tenant","name","prefix","next_number","padding","document_type","is_active","created_at","invoices_issued"]
        read_only_fields = ["tenant","created_at","invoices_issued"]

    def get_invoices_issued(self, obj):
        annotated = getattr(obj, "invoice_count", None)
        return annotated if annotated is not None else obj.invoices.count()

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Enter a name for the sequence.")
        return value

    def validate_prefix(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Enter an invoice number prefix.")
        return value

    def validate_padding(self, value):
        if value < 1 or value > 12:
            raise serializers.ValidationError("Padding must be between 1 and 12 digits.")
        return value

    def validate_next_number(self, value):
        if value < 1:
            raise serializers.ValidationError("The next number must be at least 1.")
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance is not None and instance.invoices.exists():
            changed = [
                field for field in self.NUMBERING_FIELDS
                if field in attrs and attrs[field] != getattr(instance, field)
            ]
            if changed:
                raise serializers.ValidationError({
                    field: "Locked: invoices have already been issued from this sequence. "
                           "Create a new sequence to change the numbering."
                    for field in changed
                })
        return attrs


class FiscalInvoiceHistorySerializer(serializers.ModelSerializer):
    """Compact row for the fiscal invoice history screen (no XML payload).

    ``fbr`` summarises the latest live (non dry-run) FBR submission; a
    simulated acceptance is flagged and must never be presented as official.
    """

    order_number = serializers.SerializerMethodField()
    sequence_name = serializers.SerializerMethodField()
    fbr = serializers.SerializerMethodField()

    class Meta:
        model = FiscalInvoice
        fields = ["id","invoice_number","order","order_number","customer","sequence","sequence_name","status",
                  "issue_date","subtotal","tax","discount","total","fbr_invoice_number","created_at","fbr"]
        read_only_fields = fields

    def get_order_number(self, obj):
        return obj.order.order_number if obj.order_id and obj.order else None

    def get_sequence_name(self, obj):
        return obj.sequence.name if obj.sequence_id and obj.sequence else None

    def get_fbr(self, obj):
        live = getattr(obj, "live_fbr_submissions", None)
        if live is None:
            live = list(obj.fbr_submissions.filter(is_validate=False).order_by("-id")[:1])
        latest = live[0] if live else None
        if latest is None:
            return {"status": "not_submitted", "submission_id": None, "attempts": 0}
        status = "simulated" if latest.status == "accepted" and latest.is_simulated else latest.status
        return {
            "status": status,
            "submission_id": latest.id,
            "environment": latest.environment,
            "integration_mode": latest.integration_mode,
            "is_simulated": latest.is_simulated,
            "fbr_invoice_number": latest.fbr_invoice_number if latest.status == "accepted" and not latest.is_simulated else "",
            "simulated_invoice_number": latest.fbr_invoice_number if latest.status == "accepted" and latest.is_simulated else "",
            "receipt_label": "TEST / SIMULATED — NOT AN FBR INVOICE" if latest.status == "accepted" and latest.is_simulated else "",
            "error_code": latest.error_code,
            "error_message": (latest.error_message or "")[:500],
            "attempts": latest.attempts,
            "submitted_at": latest.created_at,
            "responded_at": latest.responded_at,
        }


class FiscalInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalInvoice
        fields = ["id","tenant","sequence","invoice_number","order","customer","status","issue_date","subtotal","tax","discount","total","qr_payload","fbr_invoice_number","uuid","xml_content","pdf_url","created_by","created_at"]
        read_only_fields = ["tenant","invoice_number","uuid","qr_payload","fbr_invoice_number","xml_content","created_by","created_at"]


class FiscalDeviceSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=255)

    class Meta:
        model = FiscalDevice
        fields = ["id","tenant","name","kind","provider","endpoint_url","api_key","is_active","last_used_at","created_at"]
        read_only_fields = ["tenant","last_used_at","created_at"]


class FiscalSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalSubmission
        fields = ["id","tenant","invoice","device","status","reference","response_payload","submitted_at","responded_at"]
        read_only_fields = ["tenant","reference","response_payload","submitted_at","responded_at"]


class FiscalInvoiceLineSerializer(serializers.ModelSerializer):

    class Meta:
        model = FiscalInvoiceLine

        fields = [
            "id",
            "line_number",
            "source_order_item",
            "source_product",
            "product_name",
            "product_sku",
            "product_description",
            "quantity",
            "unit_price",
            "subtotal",
            "discount",
            "taxable_amount",
            "tax_amount",
            "total_amount",
            "tax_breakdown",
            "fbr_snapshot",
            "created_at",
        ]

        read_only_fields = fields        