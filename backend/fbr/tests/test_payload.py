"""Payload construction against DI API v1.12 §4.1/4.1.2."""
from decimal import Decimal

from fbr.constants import INVOICE_TYPE_SALE
from fbr.models import FBRBuyerProfile, FBRProductProfile
from fbr.payload import FBRValidationError, build_invoice_payload

from .base import FBRTestBase

HEADER_FIELDS_V112 = [
    "invoiceType", "invoiceDate", "sellerNTNCNIC", "sellerBusinessName", "sellerProvince", "sellerAddress",
    "buyerNTNCNIC", "buyerBusinessName", "buyerProvince", "buyerAddress", "buyerRegistrationType",
    "invoiceRefNo", "items", "scenarioId",
]
# scenarioId only for sandbox — production omits it, so allow both shapes
HEADER_FIELDS_V112_SANDBOX = HEADER_FIELDS_V112
HEADER_FIELDS_V112_PROD = [f for f in HEADER_FIELDS_V112 if f != "scenarioId"]

ITEM_FIELDS_V112 = [
    "hsCode", "productDescription", "rate", "uoM", "quantity",
    "totalValues", "valueSalesExcludingST", "fixedNotifiedValueOrRetailPrice",
    "salesTaxApplicable", "salesTaxWithheldAtSource", "extraTax", "furtherTax",
    "sroScheduleNo", "fedPayable", "discount", "saleType", "sroItemSerialNo",
]


class PayloadStructureTests(FBRTestBase):
    def test_payload_has_every_v112_field(self):
        payload = build_invoice_payload(self.invoice_a, config=self.config_a)
        # sandbox includes scenarioId
        self.assertEqual(list(payload.keys()), HEADER_FIELDS_V112_SANDBOX)
        # items is list with 17-field dicts (internal _saleTypeId stripped)
        self.assertEqual(list(payload["items"][0].keys()), ITEM_FIELDS_V112)

    def test_header_values_come_from_configuration_and_buyer_profile(self):
        payload = build_invoice_payload(self.invoice_a, config=self.config_a)
        self.assertEqual(payload["invoiceType"], "Sale Invoice")
        self.assertEqual(payload["invoiceDate"], self.invoice_a.issue_date.isoformat())
        self.assertEqual(payload["sellerNTNCNIC"], "1234567")
        self.assertEqual(payload["sellerProvince"], "Sindh")
        self.assertEqual(payload["buyerNTNCNIC"], "3520212345678")
        self.assertEqual(payload["buyerBusinessName"], "Customer a (Pvt) Ltd")
        self.assertEqual(payload["buyerProvince"], "Sindh")
        self.assertEqual(payload["buyerRegistrationType"], "Registered")
        self.assertEqual(payload["buyerAddress"], "1 Main Street, Karachi")
        self.assertEqual(payload["scenarioId"], "SN001")
        self.assertEqual(payload["invoiceRefNo"], "")

    def test_item_amounts_and_types(self):
        payload = build_invoice_payload(self.invoice_a, config=self.config_a)
        item = payload["items"][0]
        # v1.12 emits the dotted HS code — 84713010 → 8471.3010
        self.assertEqual(item["hsCode"], "8471.3010")
        self.assertEqual(item["uoM"], "Numbers, pieces, units")
        self.assertEqual(item["quantity"], 2.0)  # 4dp but float 2.0
        self.assertEqual(item["valueSalesExcludingST"], 200.0)
        self.assertEqual(item["rate"], "18%")
        self.assertEqual(item["salesTaxApplicable"], 36.0)
        self.assertEqual(item["totalValues"], 236.0)
        self.assertEqual(item["saleType"], "Goods at standard rate (default)")
        self.assertEqual(item["sroScheduleNo"], "")
        self.assertEqual(item["sroItemSerialNo"], "")

    def test_production_payload_omits_scenario_id(self):
        prod = self.make_config(self.tenant_b, environment="production", seller_province=self.province_punjab, scenario_id="")
        inv = self.make_invoice(self.tenant_b, "prod")
        # need config for tenant_b with province — make_config already did, but invoice uses tenant_b
        from fbr.models import FBRConfiguration
        cfg = FBRConfiguration.objects.get(tenant=self.tenant_b, environment="production")
        payload = build_invoice_payload(inv, config=cfg)
        self.assertNotIn("scenarioId", payload)
        self.assertEqual(list(payload.keys()), HEADER_FIELDS_V112_PROD)

    def test_order_discount_reduces_the_taxable_value(self):
        invoice = self.make_invoice(self.tenant_a, "disc", discount=Decimal("50.00"))
        payload = build_invoice_payload(invoice, config=self.config_a)
        item = payload["items"][0]
        self.assertEqual(item["valueSalesExcludingST"], 150.0)
        self.assertEqual(item["salesTaxApplicable"], 27.0)

    def test_every_tax_component_is_derived_from_the_product_profile(self):
        # Configure the profile on the same product that will be invoiced.
        # The fiscal invoice then freezes these values into its immutable snapshot.
        invoice = self.make_invoice(
            self.tenant_a,
            "taxcomponents",
            product_profile_overrides={
                "extra_tax_rate": Decimal("2.000"),
                "further_tax_rate": Decimal("3.000"),
                "fed_payable_rate": Decimal("1.000"),
                "st_withheld_rate": Decimal("20.000"),
            },
        )
        item = build_invoice_payload(invoice, config=self.config_a)["items"][0]
        self.assertEqual(item["extraTax"], 4.0)
        self.assertEqual(item["furtherTax"], 6.0)
        self.assertEqual(item["fedPayable"], 2.0)
        self.assertEqual(item["salesTaxWithheldAtSource"], 7.2)
        self.assertEqual(item["fixedNotifiedValueOrRetailPrice"], 0.0)


class PayloadValidationTests(FBRTestBase):
    def test_missing_buyer_province_is_rejected(self):
        FBRBuyerProfile.objects.filter(customer__tenant=self.tenant_a).update(buyer_province=None, buyer_province_text="")
        with self.assertRaises(FBRValidationError) as ctx:
            build_invoice_payload(self.invoice_a, config=self.config_a)
        self.assertTrue(any("buyer province" in e.lower() for e in ctx.exception.errors))

    def test_unregistered_buyer_may_have_blank_ntn(self):
        # Registered requires NTN, Unregistered does not
        bp = FBRBuyerProfile.objects.get(customer__name="Customer a")
        bp.buyer_registration_type = "Unregistered"
        bp.ntn_cnic = ""
        bp.save()
        payload = build_invoice_payload(self.invoice_a, config=self.config_a)
        self.assertEqual(payload["buyerRegistrationType"], "Unregistered")
        self.assertEqual(payload["buyerNTNCNIC"], "")

    def test_registered_buyer_without_ntn_is_rejected(self):
        bp = FBRBuyerProfile.objects.get(customer__name="Customer a")
        bp.buyer_registration_type = "Registered"
        bp.ntn_cnic = ""
        bp.save()
        with self.assertRaises(FBRValidationError) as ctx:
            build_invoice_payload(self.invoice_a, config=self.config_a)
        self.assertTrue(any("NTN/CNIC" in e for e in ctx.exception.errors))

    def test_missing_product_profile_is_rejected(self):
        # Fiscal snapshots require the FBR product profile before an invoice
        # can be issued, so rejection occurs during invoice creation.
        from fiscal.services import FiscalServiceError
        with self.assertRaises(FiscalServiceError) as ctx:
            self.make_invoice(self.tenant_a, "missingprofile", with_product_profile=False)
        self.assertIn("no active FBR profile", str(ctx.exception))

    def test_configuration_without_seller_province_is_rejected(self):
        self.config_a.seller_province = None
        self.config_a.seller_province_text = ""
        self.config_a.save(update_fields=["seller_province", "seller_province_text"])
        with self.assertRaises(FBRValidationError) as ctx:
            build_invoice_payload(self.invoice_a, config=self.config_a)
        self.assertTrue(any("seller province" in e.lower() for e in ctx.exception.errors))

    def test_sandbox_requires_scenario_id(self):
        self.config_a.scenario_id = ""
        self.config_a.save(update_fields=["scenario_id"])
        with self.assertRaises(FBRValidationError) as ctx:
            build_invoice_payload(self.invoice_a, config=self.config_a)
        self.assertTrue(any("scenarioId" in e for e in ctx.exception.errors))

    def test_unknown_invoice_type_is_rejected(self):
        with self.assertRaises(FBRValidationError):
            build_invoice_payload(self.invoice_a, config=self.config_a, invoice_type=9)
        with self.assertRaises(FBRValidationError):
            build_invoice_payload(self.invoice_a, config=self.config_a, invoice_type="Bad Type")

    def test_string_invoice_type_is_accepted(self):
        payload = build_invoice_payload(self.invoice_a, config=self.config_a, invoice_type="Sale Invoice")
        self.assertEqual(payload["invoiceType"], "Sale Invoice")

    def test_debit_note_requires_invoice_ref_no(self):
        with self.assertRaises(FBRValidationError) as ctx:
            build_invoice_payload(self.invoice_a, config=self.config_a, invoice_type=3, invoice_ref_no="")
        self.assertTrue(any("invoiceRefNo" in e for e in ctx.exception.errors))
        payload = build_invoice_payload(self.invoice_a, config=self.config_a, invoice_type=3, invoice_ref_no="3310227771151DI1700000000123")
        self.assertEqual(payload["invoiceRefNo"], "3310227771151DI1700000000123")
