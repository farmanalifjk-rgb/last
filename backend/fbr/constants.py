"""Constants defined by the PRAL "Technical Specification for DI API" v1.12 (2025-07-24).

Section references point at v1.12 (51 pp). Legacy v1.0 constants are retained as
LEGACY_* for the dual-version flag while the default routing is now PRAL v1.12
(di_data/v1/di/postinvoicedata). This file is the single source for the new
envelope.
"""

# §4.1.1/4.1.2 — invoice type as STRING (v1.12 sample) — int 1-4 still accepted
# internally and mapped to the string PRAL expects.
INVOICE_TYPE_PURCHASE = 1
INVOICE_TYPE_SALE = 2
INVOICE_TYPE_DEBIT_NOTE = 3
INVOICE_TYPE_CREDIT_NOTE = 4

INVOICE_TYPE_CHOICES = [
    (INVOICE_TYPE_PURCHASE, "Purchase"),
    (INVOICE_TYPE_SALE, "Sale"),
    (INVOICE_TYPE_DEBIT_NOTE, "Debit note"),
    (INVOICE_TYPE_CREDIT_NOTE, "Credit note"),
]

# String envelope PRAL expects (§4.1.1 p7-8: "Sale Invoice")
INVOICE_TYPE_STRINGS = {
    INVOICE_TYPE_PURCHASE: "Purchase Invoice",
    INVOICE_TYPE_SALE: "Sale Invoice",
    INVOICE_TYPE_DEBIT_NOTE: "Debit Note",
    INVOICE_TYPE_CREDIT_NOTE: "Credit Note",
}
# Reverse for incoming string → int
INVOICE_TYPE_FROM_STRING = {v: k for k, v in INVOICE_TYPE_STRINGS.items()}

# buyerRegistrationType — §4.1 table p10 Required: Registered / Unregistered
BUYER_REGISTRATION_REGISTERED = "Registered"
BUYER_REGISTRATION_UNREGISTERED = "Unregistered"
BUYER_REGISTRATION_CHOICES = [
    (BUYER_REGISTRATION_REGISTERED, "Registered"),
    (BUYER_REGISTRATION_UNREGISTERED, "Unregistered"),
]

# §2.3 / §4.1 — posting endpoints. v1.12 routing is token-based but the
# documented URLs are now di_data/v1/di/... with _sb suffix for sandbox.
# Legacy v1.0 endpoints are kept for backward routing via api_version flag.
ENVIRONMENT_SANDBOX = "sandbox"
ENVIRONMENT_PRODUCTION = "production"
ENVIRONMENT_CHOICES = [
    (ENVIRONMENT_SANDBOX, "Sandbox"),
    (ENVIRONMENT_PRODUCTION, "Production"),
]

# v1.12 canonical
ENDPOINT_SANDBOX = "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata_sb"
ENDPOINT_PRODUCTION = "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata"
ENDPOINT_VALIDATE_SANDBOX = "https://gw.fbr.gov.pk/di_data/v1/di/validateinvoicedata_sb"
ENDPOINT_VALIDATE_PRODUCTION = "https://gw.fbr.gov.pk/di_data/v1/di/validateinvoicedata"

# Legacy v1.0 (retained for dual-version tenants)
LEGACY_ENDPOINT_SANDBOX = "https://esp.fbr.gov.pk:8244/DigitalInvoicing/v1/PostInvoiceData_v1"
LEGACY_ENDPOINT_PRODUCTION = "https://gw.fbr.gov.pk/pdi/v1/api/DigitalInvoicing/PostInvoiceData_v1"

DEFAULT_ENDPOINTS = {
    ENVIRONMENT_SANDBOX: ENDPOINT_SANDBOX,
    ENVIRONMENT_PRODUCTION: ENDPOINT_PRODUCTION,
}
DEFAULT_VALIDATE_ENDPOINTS = {
    ENVIRONMENT_SANDBOX: ENDPOINT_VALIDATE_SANDBOX,
    ENVIRONMENT_PRODUCTION: ENDPOINT_VALIDATE_PRODUCTION,
}

# v1.12 success is validationResponse.statusCode "00" (string) per §4.1.3 p12.
# Legacy v1.0 used integer 200.
SUCCESS_STATUS_CODE = "00"
SUCCESS_STATUS_CODE_LEGACY = 200

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 2

# §9-10 Sandbox scenarios — SNxxx per business activity matrix pp46-51.
# Exhaustive list from spec §9 + §10 tables.
SCENARIO_CHOICES = [
    ("SN001", "SN001"), ("SN002", "SN002"), ("SN003", "SN003"), ("SN004", "SN004"),
    ("SN005", "SN005"), ("SN006", "SN006"), ("SN007", "SN007"), ("SN008", "SN008"),
    ("SN009", "SN009"), ("SN010", "SN010"), ("SN011", "SN011"), ("SN012", "SN012"),
    ("SN013", "SN013"), ("SN014", "SN014"), ("SN015", "SN015"), ("SN016", "SN016"),
    ("SN017", "SN017"), ("SN018", "SN018"), ("SN019", "SN019"), ("SN020", "SN020"),
    ("SN021", "SN021"), ("SN022", "SN022"), ("SN023", "SN023"), ("SN024", "SN024"),
    ("SN025", "SN025"), ("SN026", "SN026"), ("SN027", "SN027"), ("SN028", "SN028"),
]

# 5.1 Province reference — PRAL returns provinceId + description. Seed list
# mirrors sample "Sindh" (p7) and common FBR provinces.
PROVINCE_CHOICES = [
    ("Sindh", "Sindh"),
    ("Punjab", "Punjab"),
    ("Khyber Pakhtunkhwa", "Khyber Pakhtunkhwa"),
    ("Balochistan", "Balochistan"),
    ("Islamabad", "Islamabad"),
    ("Gilgit-Baltistan", "Gilgit-Baltistan"),
    ("Azad Kashmir", "Azad Kashmir"),
]

# Licensed integrator — user stated they will always use PRAL as licensed
# integrator, so default routing is PRAL. Kept as constant for future
# multi-integrator if needed.
INTEGRATOR_PRAL = "pral"
INTEGRATOR_CHOICES = [(INTEGRATOR_PRAL, "PRAL (licensed integrator)")]

# ============================================================================
# Tier-1 Retailer — IMS Software Fiscal Component
# (Technical Specification for Data Sharing through Software Fiscal Component
#  from TIER 1 Retailer with FBR — local component on the POS PC plus the
#  cloud PostData endpoint for cloud-hosted POS.)
#
# A tenant is fiscalized on exactly ONE track, selected per configuration:
#   integration_mode "di"  -> PRAL DI API v1.12 (postinvoicedata) — default
#   integration_mode "ims" -> Tier-1 IMS fiscal component (this block)
# ============================================================================

INTEGRATION_MODE_DI = "di"
INTEGRATION_MODE_IMS = "ims"
INTEGRATION_MODE_CHOICES = [
    (INTEGRATION_MODE_DI, "FBR Digital Invoicing (PRAL DI API v1.12)"),
    (INTEGRATION_MODE_IMS, "Tier-1 IMS Software Fiscal Component"),
]

# Local, self-hosted fiscal service installed on the POS PC (spec §Installation).
IMS_LOCAL_BASE_URL_DEFAULT = "http://localhost:8524"
IMS_LOCAL_HEALTH_PATH = "/api/IMSFiscal/get"
IMS_LOCAL_FISCALIZE_PATH = "/api/IMSFiscal/GetInvoiceNumberByModel"

# Cloud posting for cloud-hosted POS (spec §Web Client to post data from Cloud).
IMS_CLOUD_ENDPOINT_SANDBOX = "https://esp.fbr.gov.pk:8244/FBR/v1/api/Live/PostData"
IMS_CLOUD_ENDPOINT_PRODUCTION = "https://gw.fbr.gov.pk/imsp/v1/api/Live/PostData"
IMS_CLOUD_ENDPOINTS = {
    ENVIRONMENT_SANDBOX: IMS_CLOUD_ENDPOINT_SANDBOX,
    ENVIRONMENT_PRODUCTION: IMS_CLOUD_ENDPOINT_PRODUCTION,
}

# Invoice Model §"Invoice Data 1" — success Code is the string "100".
IMS_SUCCESS_CODE = "100"

# Header InvoiceType — spec Table 1: New / Debit / Credit.
IMS_INVOICE_TYPE_NEW = 1
IMS_INVOICE_TYPE_DEBIT = 2
IMS_INVOICE_TYPE_CREDIT = 3

# Item-level InvoiceType — spec Invoice Item table: 1 New, 3 Credit, and the
# 3rd Schedule variants 11 (new) / 12 (credit) for goods taxed on retail price.
IMS_ITEM_TYPE_NEW = 1
IMS_ITEM_TYPE_CREDIT = 3
IMS_ITEM_TYPE_THIRD_SCHEDULE_NEW = 11
IMS_ITEM_TYPE_THIRD_SCHEDULE_CREDIT = 12

# Map the platform's DI-style invoice type (1 purchase, 2 sale, 3 debit note,
# 4 credit note) onto the IMS header enum.
IMS_INVOICE_TYPE_FROM_DI = {
    INVOICE_TYPE_PURCHASE: IMS_INVOICE_TYPE_NEW,
    INVOICE_TYPE_SALE: IMS_INVOICE_TYPE_NEW,
    INVOICE_TYPE_DEBIT_NOTE: IMS_INVOICE_TYPE_DEBIT,
    INVOICE_TYPE_CREDIT_NOTE: IMS_INVOICE_TYPE_CREDIT,
}

# PaymentMode — spec Table 1 (Int): Cash, Card, Gift Voucher, Loyalty Card,
# Mixed, Cheque. Mixed MUST be used when more than one payment method was
# tendered (e.g. cash + card).
IMS_PAYMENT_MODE_CASH = 1
IMS_PAYMENT_MODE_CARD = 2
IMS_PAYMENT_MODE_GIFT_VOUCHER = 3
IMS_PAYMENT_MODE_LOYALTY_CARD = 4
IMS_PAYMENT_MODE_MIXED = 5
IMS_PAYMENT_MODE_CHEQUE = 6

# Platform Order.payment_method / Payment.payment_method values -> IMS PaymentMode.
IMS_PAYMENT_MODE_MAP = {
    "cash": IMS_PAYMENT_MODE_CASH,
    "card": IMS_PAYMENT_MODE_CARD,
    "gift_card": IMS_PAYMENT_MODE_GIFT_VOUCHER,
    "loyalty": IMS_PAYMENT_MODE_LOYALTY_CARD,
    "store_credit": IMS_PAYMENT_MODE_LOYALTY_CARD,
    "bank": IMS_PAYMENT_MODE_CHEQUE,
    "split": IMS_PAYMENT_MODE_MIXED,
    "wallet": IMS_PAYMENT_MODE_MIXED,
}

# Field length limits from the Invoice Model tables.
IMS_USIN_MAX_LENGTH = 50          # USIN varchar(50)
IMS_REFUSIN_MAX_LENGTH = 50       # RefUSIN varchar(50)
IMS_ITEM_CODE_MAX_LENGTH = 50     # ItemCode varchar(50)
IMS_ITEM_NAME_MAX_LENGTH = 150    # ItemName varchar(150)
IMS_PCT_CODE_MAX_LENGTH = 8       # PCTCode varchar(8) — Pakistan Custom Tariff
IMS_BUYER_NTN_MAX_LENGTH = 9      # BuyerNTN varchar(9), e.g. 1234567-8
IMS_BUYER_CNIC_LENGTH = 13        # BuyerCNIC varchar(13), e.g. 1111122222223
IMS_BUYER_PHONE_MAX_LENGTH = 20   # BuyerPhoneNumber varchar(20)
