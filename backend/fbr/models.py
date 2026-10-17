"""Models backing the FBR (PRAL) Digital Invoicing integration.

Reference tables (transaction types, SRO schedules, UoM, HS codes) are FBR
catalogs shared across the platform and are loaded with the
``load_fbr_reference_data`` management command.  Everything a tenant owns -
credentials, product/buyer mappings and submissions - is tenant scoped like the
rest of the platform.

This module implements the **DI API v1.12 (2025-07-24)** contract while
retaining legacy v1.0 columns for dual-version tenants. All new fields are
nullable/blank for zero-downtime migration; v1.12 payload emits them.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from backend.security import EncryptedCredentialField

from .constants import (
    BUYER_REGISTRATION_CHOICES,
    BUYER_REGISTRATION_REGISTERED,
    DEFAULT_ENDPOINTS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    ENVIRONMENT_CHOICES,
    ENVIRONMENT_PRODUCTION,
    ENVIRONMENT_SANDBOX,
    IMS_CLOUD_ENDPOINTS,
    IMS_LOCAL_BASE_URL_DEFAULT,
    INTEGRATION_MODE_CHOICES,
    INTEGRATION_MODE_DI,
    INTEGRATION_MODE_IMS,
    INTEGRATOR_CHOICES,
    INTEGRATOR_PRAL,
    INVOICE_TYPE_CHOICES,
    INVOICE_TYPE_SALE,
    PROVINCE_CHOICES,
    SCENARIO_CHOICES,
)
from .urlguard import validate_di_endpoint_url, validate_ims_local_base_url


class FBRReferenceCode(models.Model):
    """Shared behaviour for the code lists published by FBR in the annexures.

    FBR publishes the codes with a letter prefix (``T1000075``, ``U1000069``,
    ``S1000450``) while the invoice payload carries the numeric part of the
    code, so both representations are kept available.
    """

    code = models.CharField(max_length=12, unique=True)
    description = models.CharField(max_length=512, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.description}"

    @property
    def numeric_code(self):
        digits = "".join(ch for ch in self.code if ch.isdigit())
        return int(digits) if digits else None


class FBRTransactionType(FBRReferenceCode):
    """Annexure 4.1 transaction codes, posted as ``saleType`` (string description in v1.12)."""


class FBRSROSchedule(FBRReferenceCode):
    """Annexure 4.2 SRO / schedule codes, posted as ``sroScheduleNo`` (string in v1.12)."""


class FBRUnitOfMeasure(FBRReferenceCode):
    """Annexure 4.3 UoM codes, posted as ``uoM`` (string description in v1.12, e.g. 'Numbers, pieces, units')."""


class FBRProvince(models.Model):
    """5.1 Province reference — required for sellerProvince / buyerProvince (v1.12)."""

    code = models.CharField(max_length=64, unique=True, help_text="PRAL provinceId or name, e.g. Sindh")
    description = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class FBRHSCode(models.Model):
    """Annexure HS codes, posted as ``hsCode``.

    v1.0 used 8-char ``12345678``; v1.12 uses dotted ``0101.2100``. Both are
    accepted and normalized on emit.
    """

    # Accept both 8-digit and dotted 4.4 forms
    code = models.CharField(
        max_length=9, unique=True,
        validators=[RegexValidator(r"^(\d{8}|\d{4}\.\d{4})$", message="HS code must be 8 digits or dotted 0101.2100")],
    )
    description = models.CharField(max_length=512, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        indexes = [models.Index(fields=["code"])]

    def __str__(self):
        return self.code

    @property
    def dotted_code(self):
        """Return dotted form for v1.12 payload (01012100 -> 0101.2100)."""
        if "." in self.code:
            return self.code
        if len(self.code) == 8 and self.code.isdigit():
            return f"{self.code[:4]}.{self.code[4:]}"
        return self.code


class FBRConfiguration(models.Model):
    """Per-tenant FBR credentials and posting behaviour.

    A tenant keeps at most one configuration per environment so sandbox
    rehearsals and production filings never share a security token.
    """

    tenant = models.ForeignKey(
        "saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records"
    )
    environment = models.CharField(max_length=12, choices=ENVIRONMENT_CHOICES, default=ENVIRONMENT_SANDBOX)
    # Fiscalization track: PRAL DI API v1.12 (default) or the Tier-1 IMS
    # Software Fiscal Component. One tenant = one active track per environment.
    integration_mode = models.CharField(
        max_length=8, choices=INTEGRATION_MODE_CHOICES, default=INTEGRATION_MODE_DI,
        help_text="di = PRAL DI API v1.12; ims = Tier-1 IMS Software Fiscal Component",
    )
    # --- Tier-1 IMS fields (spec: POS Registration / Invoice Model) ---------
    pos_registration_number = models.BigIntegerField(
        null=True, blank=True,
        help_text="POSID — POS registration number issued on eFBR POS Client Registration (IMS mode)",
    )
    ims_local_base_url = models.URLField(
        default=IMS_LOCAL_BASE_URL_DEFAULT, blank=True,
        help_text="Self-hosted fiscal component on the POS PC (IMS mode)",
    )
    ims_use_cloud = models.BooleanField(
        default=False,
        help_text="Post to the FBR Live/PostData cloud endpoints instead of the local component (cloud-hosted POS)",
    )
    # Environment sanity gate: the local component is installed in either Test
    # or Production mode at setup time. A production environment row must
    # explicitly confirm the component it points at was installed in
    # production mode, so a forgotten sandbox install cannot fiscalize live
    # sales into the test stream.
    ims_local_confirmed = models.BooleanField(
        default=False,
        help_text="Confirm the local component at ims_local_base_url is installed in Production mode (required for production local mode)",
    )
    # The in-process simulator may only answer for a configuration that opts in
    # explicitly. Deployment flags (FBR_SIMULATOR_ENABLED/MODE) alone never
    # redirect a configuration away from its real IMS component or the official
    # PRAL endpoint, and an opted-in configuration fails closed (nothing is
    # sent anywhere) when the deployment has the simulator disabled.
    use_simulator = models.BooleanField(
        default=False,
        help_text="Development/test only: use the isolated IMS simulator instead of a real component. "
                  "The simulated number never becomes an official fiscal invoice number and receipts label it TEST / SIMULATED.",
    )
    # Section 2.1 - FBR assigns the operator a unique ID and a security token.
    security_token = EncryptedCredentialField(max_length=1024, blank=True)
    bpos_id = models.CharField(max_length=32, blank=True, help_text="Business POS/branch ID issued by FBR (legacy v1.0)")
    seller_ntn_cnic = models.CharField(max_length=20, blank=True)
    seller_business_name = models.CharField(max_length=255, blank=True)
    seller_address = models.CharField(max_length=255, blank=True)
    # v1.12: sellerProvince is required (5.1)
    seller_province = models.ForeignKey(
        FBRProvince, null=True, blank=True, on_delete=models.PROTECT,
        related_name="seller_configurations",
        help_text="Seller province (5.1) — required for v1.12",
    )
    seller_province_text = models.CharField(max_length=64, blank=True, help_text="Free-form province name if not using FK (legacy data)")
    # Distributor block of the payload, only relevant to some supply chains (v1.0 legacy).
    distributor_ntn_cnic = models.CharField(max_length=20, blank=True)
    distributor_name = models.CharField(max_length=255, blank=True)
    default_transaction_type = models.ForeignKey(
        FBRTransactionType, null=True, blank=True, on_delete=models.PROTECT,
        related_name="default_for_configurations",
        help_text="Sale type used when a product has no explicit mapping",
    )
    endpoint_url = models.URLField(blank=True, help_text="Overrides the published endpoint for this environment")
    timeout_seconds = models.PositiveIntegerField(default=DEFAULT_TIMEOUT_SECONDS, validators=[MinValueValidator(1)])
    max_retries = models.PositiveIntegerField(default=DEFAULT_MAX_RETRIES)
    verify_tls = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    # v1.12 sandbox scenario (Required for Sandbox only, p11)
    scenario_id = models.CharField(max_length=6, blank=True, choices=SCENARIO_CHOICES, help_text="Sandbox scenarioId SN001..SN028 (v1.12 §9, required for sandbox)")
    # Licensed integrator — user will always use PRAL
    integrator = models.CharField(max_length=20, choices=INTEGRATOR_CHOICES, default=INTEGRATOR_PRAL, help_text="Licensed integrator (default PRAL)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tenant_id", "environment"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "environment"], name="unique_fbr_configuration_per_environment"),
        ]

    def __str__(self):
        return f"FBR {self.environment} configuration for tenant {self.tenant_id}"

    @property
    def resolved_endpoint_url(self):
        return self.endpoint_url or DEFAULT_ENDPOINTS[self.environment]

    @property
    def resolved_seller_province(self):
        if self.seller_province:
            return self.seller_province.code
        return self.seller_province_text or ""

    @property
    def resolved_ims_base_url(self):
        """Full posting base for the IMS track (local component or cloud PostData)."""
        if self.integration_mode == INTEGRATION_MODE_IMS and self.ims_use_cloud:
            return IMS_CLOUD_ENDPOINTS[self.environment]
        return (self.ims_local_base_url or IMS_LOCAL_BASE_URL_DEFAULT).rstrip("/")

    def clean(self):
        errors = {}
        if self.environment == ENVIRONMENT_PRODUCTION:
            # The local IMS component is bound to the POS registration at
            # install time, so a bearer token is only needed for DI posting or
            # IMS cloud posting.
            needs_token = self.integration_mode != INTEGRATION_MODE_IMS or self.ims_use_cloud
            if needs_token and not self.security_token:
                errors["security_token"] = "A production configuration requires the FBR security token."
            if not self.seller_ntn_cnic:
                errors["seller_ntn_cnic"] = "A production configuration requires the seller NTN/CNIC."
            if not self.verify_tls:
                errors["verify_tls"] = "TLS verification cannot be disabled for production."
        # SSRF guard (audit): the DI endpoint override must never point the
        # platform's outbound fiscal client at a loopback/private/link-local
        # address. The IMS local URL is separately restricted to loopback/private
        # hosts because it targets the on-prem component.
        if self.integration_mode == INTEGRATION_MODE_DI and self.endpoint_url:
            try:
                validate_di_endpoint_url(self.endpoint_url)
            except ValueError as exc:
                errors["endpoint_url"] = str(exc)
        if self.integration_mode == INTEGRATION_MODE_IMS:
            if not self.pos_registration_number:
                errors["pos_registration_number"] = (
                    "IMS fiscalization requires the POS registration number issued on eFBR "
                    "(Registration > POS Client Registration)."
                )
            if self.ims_use_cloud:
                # Cloud PostData authenticates with the FBR bearer token in
                # every environment — never send an empty Authorization header.
                if not self.security_token:
                    errors["security_token"] = (
                        "Cloud IMS posting (ims_use_cloud) requires the FBR security token in every environment."
                    )
            else:
                # SSRF guard: the local component URL must be loopback/private.
                try:
                    validate_ims_local_base_url(self.ims_local_base_url or IMS_LOCAL_BASE_URL_DEFAULT)
                except ValueError as exc:
                    errors["ims_local_base_url"] = str(exc)
                # Environment sanity: production local mode must confirm the
                # component install is Production (not the sandbox component).
                if self.environment == ENVIRONMENT_PRODUCTION and not self.ims_local_confirmed:
                    errors["ims_local_confirmed"] = (
                        "Production local fiscalization requires confirming the component at "
                        "ims_local_base_url was installed in Production mode (ims_local_confirmed)."
                    )
        # Fiscal-scheme eligibility is a taxpayer-registration fact, not a free
        # tenant choice (audit H8). Without a platform-verified record the
        # tenant may only use the PRAL DI track.
        if self.tenant_id:
            allowed = tenant_allowed_modes(self.tenant)
            if self.integration_mode not in allowed:
                errors["integration_mode"] = (
                    "This tenant is not eligible for the "
                    f"'{self.integration_mode}' fiscalization track (allowed: {', '.join(sorted(allowed))}). "
                    "Fiscal eligibility is verified by the platform operator."
                )
        # v1.12: sandbox requires scenarioId
        if self.environment == ENVIRONMENT_SANDBOX and self.is_active and not self.scenario_id:
            # Not hard error for legacy tenants, but recommend
            pass
        if errors:
            raise ValidationError(errors)


class FBRTenantEligibility(models.Model):
    """Platform-verified fiscalization eligibility of a tenant.

    Whether a taxpayer fiscalizes through the PRAL DI API or the Tier-1 IMS
    Software Fiscal Component is a registration/legal fact (Sales Tax Rules
    2006 Ch. XIV-AA Tier-1 integration vs regular registered person), not a
    free per-tenant software choice. The platform operator records the
    verification here (e.g. after checking the eFBR registration); tenants can
    then only configure modes within their eligibility. Tenants without a
    record default to the PRAL DI track.
    """

    tenant = models.OneToOneField(
        "saas.Tenant", on_delete=models.CASCADE, related_name="fbr_eligibility"
    )
    allowed_modes = models.CharField(
        max_length=20, default=INTEGRATION_MODE_DI,
        help_text="Comma-separated fiscalization tracks this tenant may configure: di, ims",
    )
    reference = models.CharField(
        max_length=120, blank=True,
        help_text="Verification reference (eFBR registration / STRN record / approval ticket)",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="fbr_eligibility_verifications",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tenant_id"]

    def __str__(self):
        return f"FBR eligibility for tenant {self.tenant_id}: {self.allowed_modes}"

    def clean(self):
        modes = [m.strip() for m in (self.allowed_modes or "").split(",") if m.strip()]
        invalid = [m for m in modes if m not in (INTEGRATION_MODE_DI, INTEGRATION_MODE_IMS)]
        if not modes or invalid:
            raise ValidationError(
                {"allowed_modes": "allowed_modes must be a comma-separated list drawn from: di, ims."}
            )

    def allowed_mode_set(self):
        return {m.strip() for m in (self.allowed_modes or "").split(",") if m.strip()} & {
            INTEGRATION_MODE_DI,
            INTEGRATION_MODE_IMS,
        }


def tenant_allowed_modes(tenant):
    """Modes *tenant* may configure; DI-only when no verified record exists."""
    row = FBRTenantEligibility.objects.filter(tenant=tenant, is_active=True).first()
    if row is None:
        return {INTEGRATION_MODE_DI}
    return row.allowed_mode_set() or {INTEGRATION_MODE_DI}


class FBRBuyerProfile(models.Model):
    """FBR identity of a customer (v1.12 header fields: buyerProvince, buyerRegistrationType)."""

    tenant = models.ForeignKey(
        "saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records"
    )
    customer = models.OneToOneField("pos.Customer", on_delete=models.CASCADE, related_name="fbr_profile")
    ntn_cnic = models.CharField(max_length=20, blank=True, help_text="Blank allowed if buyerRegistrationType=Unregistered (v1.12 p10)")
    registered_name = models.CharField(max_length=255, blank=True)
    destination_address = models.CharField(max_length=255, blank=True)
    # v1.12: buyerProvince required (5.1) and buyerRegistrationType required
    buyer_province = models.ForeignKey(
        FBRProvince, null=True, blank=True, on_delete=models.PROTECT,
        related_name="buyer_profiles",
        help_text="Buyer province (5.1) — required for v1.12",
    )
    buyer_province_text = models.CharField(max_length=64, blank=True, help_text="Free-form province if not using FK")
    buyer_registration_type = models.CharField(
        max_length=12, choices=BUYER_REGISTRATION_CHOICES, default=BUYER_REGISTRATION_REGISTERED,
        help_text="Registered / Unregistered (v1.12 p10)",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["customer_id"]

    def __str__(self):
        return f"FBR buyer profile for customer {self.customer_id}"

    @property
    def resolved_buyer_province(self):
        if self.buyer_province:
            return self.buyer_province.code
        return self.buyer_province_text or self.buyer_province_text or ""

    def clean(self):
        if self.customer_id and self.tenant_id and self.customer.tenant_id != self.tenant_id:
            raise ValidationError({"customer": "Customer must belong to the same tenant as its FBR profile."})
        # v1.12: if Registered, NTN required
        if self.buyer_registration_type == BUYER_REGISTRATION_REGISTERED and not self.ntn_cnic:
            raise ValidationError({"ntn_cnic": "Registered buyers must have an NTN/CNIC (v1.12)."})


class FBRProductProfile(models.Model):
    """FBR classification of a product (v1.12 item-wise fields).

    Tax components are stored as percentages of the line value; the payload
    builder turns them into the amounts FBR expects.
    """

    tenant = models.ForeignKey(
        "saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records"
    )
    product = models.OneToOneField("pos.Product", on_delete=models.CASCADE, related_name="fbr_profile")
    hs_code = models.ForeignKey(FBRHSCode, on_delete=models.PROTECT, related_name="product_profiles")
    uom = models.ForeignKey(FBRUnitOfMeasure, on_delete=models.PROTECT, related_name="product_profiles")
    transaction_type = models.ForeignKey(
        FBRTransactionType, null=True, blank=True, on_delete=models.PROTECT, related_name="product_profiles",
        help_text="Sale type for this product; falls back to the configuration default",
    )
    sro_schedule = models.ForeignKey(
        FBRSROSchedule, null=True, blank=True, on_delete=models.PROTECT, related_name="product_profiles"
    )
    sro_item_serial_no = models.CharField(max_length=30, blank=True, help_text="sroItemSerialNo (v1.12 5.10) — optional")
    # --- Tier-1 IMS item fields ---------------------------------------------
    pct_code = models.CharField(
        max_length=8, blank=True,
        help_text="PCTCode — Pakistan Custom Tariff code, up to 8 digits (IMS mode); falls back to the HS code digits",
    )
    third_schedule = models.BooleanField(
        default=False,
        help_text="Goods taxed on retail price under the 3rd Schedule — item InvoiceType 11/12 in IMS mode",
    )
    product_code = models.CharField(max_length=60, blank=True, help_text="Defaults to the product SKU")
    sales_tax_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), help_text="Percent")
    retail_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Fixed/retail price for 3rd schedule goods; defaults to the sold unit price",
    )
    extra_tax_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), help_text="Percent")
    further_tax_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), help_text="Percent")
    fed_payable_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), help_text="Percent")
    cvt_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), help_text="Percent")
    st_withheld_rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"), help_text="Percent")
    withholding_income_tax_rate = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0"), help_text="Percent"
    )
    withholding_income_tax_rate_2 = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0"), help_text="Percent"
    )
    withholding_section_1 = models.CharField(max_length=60, blank=True)
    withholding_section_2 = models.CharField(max_length=60, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product_id"]

    def __str__(self):
        return f"FBR profile for product {self.product_id}"

    def clean(self):
        if self.product_id and self.tenant_id and self.product.tenant_id != self.tenant_id:
            raise ValidationError({"product": "Product must belong to the same tenant as its FBR profile."})


class FBRSimulatorExchange(models.Model):
    """Tenant-scoped audit/idempotency record for local IMS simulator traffic.

    ``attempt_history`` retains every request/response pair for the USIN while
    the unique simulated number is allocated at most once for that logical sale.
    """

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted (simulated)"),
        (STATUS_REJECTED, "Rejected (simulated)"),
        (STATUS_FAILED, "Failed (simulated)"),
    ]

    tenant = models.ForeignKey(
        "saas.Tenant", on_delete=models.CASCADE, related_name="fbr_simulator_exchanges"
    )
    environment = models.CharField(max_length=12, choices=ENVIRONMENT_CHOICES, default=ENVIRONMENT_SANDBOX)
    usin = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=80)
    request_fingerprint = models.CharField(max_length=64)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    configured_outcome = models.CharField(max_length=12, blank=True)
    simulated_invoice_number = models.CharField(max_length=64, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    attempt_history = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "created_at"], name="fbrsimex_tenant_created_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "environment", "idempotency_key"],
                name="unique_fbr_sim_exchange_usin",
            ),
            models.UniqueConstraint(
                fields=["simulated_invoice_number"],
                condition=~models.Q(simulated_invoice_number=""),
                name="unique_fbr_sim_invoice_number",
            ),
        ]

    def __str__(self):
        return f"IMS simulator exchange {self.pk} for tenant {self.tenant_id} ({self.status})"


class FBRSubmission(models.Model):
    """One posting attempt of a fiscal invoice to the FBR Digital Invoicing API (v1.12).

    v1.12 response shape is {invoiceNumber, dated, validationResponse:{statusCode 00/01, errorCode, invoiceStatuses[]}}.
    Legacy v1.0 fields (status_code int, result) are retained for dual-version decode.
    """

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_FAILED = "failed"
    # A transport timeout: the fiscalization request may or may not have been
    # processed by the component/FBR. The outcome must be reconciled before
    # another external attempt is allowed (prevents duplicate fiscalization).
    STATUS_UNKNOWN = "unknown"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FAILED, "Failed"),
        (STATUS_UNKNOWN, "Unknown (timed out — reconcile before retry)"),
    ]

    tenant = models.ForeignKey(
        "saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records"
    )
    invoice = models.ForeignKey("fiscal.FiscalInvoice", on_delete=models.CASCADE, related_name="fbr_submissions")
    configuration = models.ForeignKey(
        FBRConfiguration, null=True, blank=True, on_delete=models.SET_NULL, related_name="submissions"
    )
    environment = models.CharField(max_length=12, choices=ENVIRONMENT_CHOICES, default=ENVIRONMENT_SANDBOX)
    # Fiscalization track FROZEN when the submission row is created (audit H2).
    # Retries always reuse this mode, even if the tenant's configuration is
    # switched (or its eligibility flipped) between the original attempt and
    # the retry, so a DI attempt can never be re-posted as an IMS document and
    # vice-versa. Legacy rows predate the field and default to "di".
    integration_mode = models.CharField(
        max_length=8, choices=INTEGRATION_MODE_CHOICES, default=INTEGRATION_MODE_DI,
        help_text="Fiscalization track frozen at submission time (di / ims)",
    )
    invoice_type = models.PositiveSmallIntegerField(choices=INVOICE_TYPE_CHOICES, default=INVOICE_TYPE_SALE)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    # Section 2.1 - the tracking number returned by FBR must be printed on the
    # invoice together with the verification QR code. v1.12 field: invoiceNumber
    fbr_invoice_number = models.CharField(max_length=64, blank=True, help_text="invoiceNumber (v1.12) / result (v1.0)")
    # Legacy int statusCode 200 vs v1.12 string "00"/"01" — store string as well
    status_code = models.CharField(max_length=10, blank=True, help_text="statusCode string 00/01 (v1.12) or 200 (v1.0)")
    status_code_legacy = models.IntegerField(null=True, blank=True, help_text="Legacy integer statusCode")
    error_message = models.TextField(blank=True)
    error_code = models.CharField(max_length=10, blank=True, help_text="errorCode 0001.. (v1.12 §7)")
    errors = models.JSONField(default=list, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    validation_response = models.JSONField(default=dict, blank=True, help_text="validationResponse object (v1.12)")
    response_timestamp = models.CharField(max_length=64, blank=True, help_text="dated (v1.12) or timestamp (v1.0)")
    attempts = models.PositiveIntegerField(default=0)
    is_validate = models.BooleanField(default=False, help_text="True if this was a validateinvoicedata call (dry-run)")
    invoice_ref_no = models.CharField(max_length=64, blank=True, help_text="invoiceRefNo for debit notes (v1.12)")
    # --- Tier-1 IMS fields ---------------------------------------------------
    usin = models.CharField(max_length=50, blank=True, help_text="USIN — client-side unique sale id (IMS mode)")
    ims_code = models.CharField(max_length=10, blank=True, help_text="IMS response Code — '100' on success")
    is_simulated = models.BooleanField(
        default=False,
        help_text="True when the isolated simulator, not FBR or a real IMS component, produced this outcome",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="fbr_submissions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When this submission last moved to pending (first post or retry); "
                  "used to detect submissions that never recorded a response.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["invoice", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["fbr_invoice_number"],
                condition=models.Q(is_simulated=True) & ~models.Q(fbr_invoice_number=""),
                name="unique_simulated_submission_number",
            ),
            models.UniqueConstraint(
                fields=["invoice"],
                condition=models.Q(status="accepted", is_validate=False),
                name="unique_accepted_fbr_submission_per_invoice",
            ),
            # Audit H1: at most one in-flight fiscalization per invoice. The
            # service layer raises a friendly error while this constraint is
            # the race-proof backstop: two concurrent submissions can never
            # both be pending, so two external fiscalization calls for the
            # same invoice cannot originate from the platform.
            models.UniqueConstraint(
                fields=["invoice"],
                condition=models.Q(status="pending", is_validate=False),
                name="unique_pending_fbr_submission_per_invoice",
            ),
        ]

    def __str__(self):
        return f"FBR submission {self.pk} for invoice {self.invoice_id} ({self.status})"

    def clean(self):
        if self.invoice_id and self.tenant_id and self.invoice.tenant_id != self.tenant_id:
            raise ValidationError({"invoice": "Invoice must belong to the same tenant as its FBR submission."})
        if self.configuration_id and self.tenant_id and self.configuration.tenant_id != self.tenant_id:
            raise ValidationError({"configuration": "Configuration must belong to the same tenant as its submission."})
