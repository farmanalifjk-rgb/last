from decimal import Decimal
from django.conf import settings
from django.db import models

from backend.security import EncryptedCredentialField


class InvoiceSequence(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """A sequenced, gapless invoice-number pool (per branch / per type)."""
    TYPE_INVOICE = "invoice"
    TYPE_CREDIT_NOTE = "credit_note"
    TYPE_PROFORMA = "proforma"
    TYPE_CHOICES = [(TYPE_INVOICE, "Invoice"), (TYPE_CREDIT_NOTE, "Credit note"), (TYPE_PROFORMA, "Proforma")]
    name = models.CharField(max_length=120)
    prefix = models.CharField(max_length=20)
    next_number = models.PositiveIntegerField(default=1)
    padding = models.PositiveIntegerField(default=6)
    document_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_INVOICE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FiscalInvoice(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    STATUS_DRAFT = "draft"
    STATUS_ISSUED = "issued"
    STATUS_CANCELLED = "cancelled"
    STATUS_VOID = "void"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_ISSUED, "Issued"),
                      (STATUS_CANCELLED, "Cancelled"), (STATUS_VOID, "Void")]
    sequence = models.ForeignKey(InvoiceSequence, on_delete=models.PROTECT, related_name="invoices")
    invoice_number = models.CharField(max_length=40, unique=True)
    order = models.ForeignKey("pos.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="fiscal_invoices")
    customer = models.ForeignKey("pos.Customer", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    issue_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    qr_payload = models.TextField(blank=True)
    # Tracking number returned by FBR; printed on the invoice with the QR code.
    fbr_invoice_number = models.CharField(max_length=64, blank=True)
    uuid = models.CharField(max_length=64, unique=True, blank=True)
    xml_content = models.TextField(blank=True)
    pdf_url = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    


class FiscalInvoiceLine(models.Model):
    """
    Immutable transaction-time snapshot of one fiscal invoice line.

    Product/order/FBR references are retained for traceability.
    The fields below preserve the values that existed when the
    fiscal invoice was created.
    """

    tenant = models.ForeignKey(
        "saas.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_records",
    )

    invoice = models.ForeignKey(
        FiscalInvoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )

    source_order_item = models.ForeignKey(
        "pos.OrderItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fiscal_invoice_lines",
    )

    source_product = models.ForeignKey(
        "pos.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fiscal_invoice_lines",
    )

    line_number = models.PositiveIntegerField()

    # Historical product information
    product_name = models.CharField(max_length=255)
    product_sku = models.CharField(max_length=100, blank=True)
    product_description = models.CharField(max_length=500, blank=True)

    # Historical commercial values
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    discount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    taxable_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Exact tax-engine result at fiscal-invoice creation time.
    tax_breakdown = models.JSONField(
        default=list,
        blank=True,
    )

    # Snapshot of FBR classification/profile data.
    fbr_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

    # FBR fiscal monetary snapshot.
    #
    # These are calculated once when the fiscal invoice is created.
    # fbr/payload.py must only serialize these values.
    sales_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    sales_tax_withheld = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    extra_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    further_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    fed_payable = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    cvt = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    withholding_income_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    withholding_income_tax_2 = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    fixed_notified_value_or_retail_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )    

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["line_number"]

        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "line_number"],
                name="unique_fiscal_invoice_line_number",
            ),
        ]    


class FiscalDevice(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """ESD / fiscal printer integration stub."""
    KIND_PRINTER = "printer"
    KIND_ESD = "esd"           # electronic sales device
    KIND_API = "api"
    KIND_CHOICES = [(KIND_PRINTER, "Fiscal printer"), (KIND_ESD, "ESD"), (KIND_API, "Tax authority API")]
    PROVIDER_STUB = "stub"
    PROVIDER_FBR = "fbr"
    PROVIDER_CHOICES = [(PROVIDER_STUB, "Stub"), (PROVIDER_FBR, "FBR Digital Invoicing (PRAL)")]
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_API)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_STUB)
    endpoint_url = models.CharField(max_length=255, blank=True)
    api_key = EncryptedCredentialField(max_length=1024, blank=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FiscalSubmission(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Record of each invoice submitted to a fiscal device/authority."""
    STATUS_PENDING = "pending"
    STATUS_SUBMITTING = "submitting"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_REQUIRES_REVIEW = "requires_review"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUBMITTING, "Submitting"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_REQUIRES_REVIEW, "Requires Review"),
    ]
    invoice = models.ForeignKey(FiscalInvoice, on_delete=models.CASCADE, related_name="submissions")
    device = models.ForeignKey(FiscalDevice, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reference = models.CharField(max_length=120, blank=True)   # authority receipt number / UUID
    response_payload = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)