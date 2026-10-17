"""Payload tests for the Tier-1 IMS Software Fiscal Component (FBR spec tables)."""
from decimal import Decimal

from pos.models import Payment

from fbr.ims_payload import build_ims_invoice_payload, _pct_code
from fbr.payload import FBRValidationError
from fbr.constants import IMS_INVOICE_TYPE_NEW
from fbr.models import FBRProductProfile
from fiscal.services import FiscalServiceError

from .base import FBRTestBase

HEADER_KEYS = {
    "InvoiceNumber", "POSID", "USIN", "RefUSIN", "DateTime",
    "BuyerName", "BuyerNTN", "BuyerCNIC", "BuyerPhoneNumber",
    "TotalSaleValue", "TotalTaxCharged", "TotalQuantity", "Discount",
    "FurtherTax", "TotalBillAmount", "PaymentMode", "InvoiceType", "Items",
}
ITEM_KEYS = {
    "ItemCode", "ItemName", "PCTCode", "Quantity", "TaxRate", "SaleValue",
    "Discount", "FurtherTax", "TaxCharged", "TotalAmount", "InvoiceType", "RefUSIN",
}


class IMSHeaderTests(FBRTestBase):
    def setUp(self):
        super().setUp()
        self.config = self.make_ims_config(self.tenant_a)

    def _payload(self, invoice=None, **kwargs):
        return build_ims_invoice_payload(
            invoice or self.invoice_a, config=self.config, **kwargs
        )

    def test_datetime_is_pakistan_business_time(self):
        # 19:05 UTC == 00:05 PKT next day (audit H6): the fiscal component is
        # reconciled in branch hours, not UTC.
        from datetime import date, datetime
        from django.utils import timezone as dj_tz

        naive = datetime(2026, 9, 5, 19, 5, 0)
        self.invoice_a.created_at = dj_tz.make_aware(naive)
        self.invoice_a.issue_date = date(2026, 9, 6)
        payload = self._payload()
        # 19:05 UTC == 00:05 PKT next day; the business date comes from issue_date.
        self.assertEqual(payload["DateTime"], "2026-09-06 00:05:00")

    def test_header_shape_follows_spec_tables(self):
        payload = self._payload()
        self.assertEqual(set(payload.keys()), HEADER_KEYS)
        self.assertEqual(payload["InvoiceNumber"], "")  # blank — component assigns it
        self.assertEqual(payload["POSID"], 110014)
        self.assertTrue(payload["USIN"])  # uuid or invoice number
        self.assertLessEqual(len(payload["USIN"]), 50)
        # "2020-01-01 12:00:00" format
        self.assertRegex(payload["DateTime"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertEqual(payload["InvoiceType"], 1)  # New

    def test_totals_arithmetic_matches_spec_example(self):
        payload = self._payload()
        # fixture: 2 x 100 = 200 subtotal, no order discount, 18% tax
        self.assertEqual(payload["TotalSaleValue"], 200.0)
        self.assertEqual(payload["TotalTaxCharged"], 36.0)
        self.assertEqual(payload["TotalQuantity"], 2.0)
        self.assertEqual(payload["Discount"], 0.0)
        self.assertEqual(payload["TotalBillAmount"], 236.0)  # 200 + 36 (spec: 1298 + 221 = 1519)
        item = payload["Items"][0]
        self.assertEqual(set(item.keys()), ITEM_KEYS)
        self.assertEqual(item["SaleValue"], 200.0)
        self.assertEqual(item["TaxCharged"], 36.0)
        self.assertEqual(item["TotalAmount"], 236.0)

    def test_order_discount_is_allocated_and_netted(self):
        # Fiscal lines freeze order-level discounts at invoice creation.
        invoice = self.make_invoice(self.tenant_a, "discounted", discount=Decimal("20.00"))
        payload = self._payload(invoice)
        self.assertEqual(payload["Discount"], 20.0)
        # SaleValue is net of discount; tax applies to the net value
        self.assertEqual(payload["TotalSaleValue"], 180.0)
        self.assertEqual(payload["TotalTaxCharged"], 32.4)
        self.assertEqual(payload["TotalBillAmount"], 212.4)

    def test_tax_rate_is_plain_float_not_percent_string(self):
        item = self._payload()["Items"][0]
        self.assertEqual(item["TaxRate"], 18.0)
        self.assertIsInstance(item["TaxRate"], float)

    def test_explicit_pct_code_is_emitted(self):
        item = self._payload()["Items"][0]
        self.assertEqual(item["PCTCode"], "84713010")  # from the profile's explicit pct_code

    def test_blank_pct_code_is_rejected_not_guessed(self):
        # Audit H7: validate the immutable fiscal snapshot, not a live profile.
        line = self.invoice_a.lines.first()
        snapshot = dict(line.fbr_snapshot or {})
        snapshot["pct_code"] = ""
        line.fbr_snapshot = snapshot
        line.save(update_fields=["fbr_snapshot"])
        with self.assertRaises(FBRValidationError) as ctx:
            self._payload()
        self.assertTrue(any("explicit PCT code" in e for e in ctx.exception.errors))

    def test_explicit_pct_code_wins_and_is_validated(self):
        line = self.invoice_a.lines.first()
        snapshot = dict(line.fbr_snapshot or {})
        snapshot["pct_code"] = "11001010"
        line.fbr_snapshot = snapshot
        line.save(update_fields=["fbr_snapshot"])
        self.assertEqual(self._payload()["Items"][0]["PCTCode"], "11001010")
        # Audit H7: an explicit PCT code wins over any HS-derived value and is
        # length-validated (PCTCode is varchar(8)).
        #
        # A PCT code longer than 8 digits is intentionally invalid. The model
        # persists ``pct_code`` in a VARCHAR(8) column, so an invalid 9-digit
        # value cannot be saved to the database (it would raise a DataError on
        # PostgreSQL). We therefore exercise the same length-validating code
        # path the payload builder uses directly, instead of persisting an
        # intentionally invalid value into the column.
        profile = FBRProductProfile.objects.get(product=self.invoice_a.order.items.first().product)
        profile.pct_code = "110010101"  # 9 digits — intentionally invalid
        errors = []
        result = _pct_code(profile, errors)
        self.assertEqual(result, "110010101")
        self.assertTrue(any("PCT" in e for e in errors))

    def test_posid_required(self):
        self.config.pos_registration_number = None
        with self.assertRaises(FBRValidationError) as ctx:
            self._payload()
        self.assertTrue(any("POS registration number" in e for e in ctx.exception.errors))

    def test_payment_mode_single_tender(self):
        self.invoice_a.order.payment_method = "cash"
        self.assertEqual(self._payload()["PaymentMode"], 1)  # Cash
        self.invoice_a.order.payment_method = "card"
        self.assertEqual(self._payload()["PaymentMode"], 2)  # Card

    def test_payment_mode_mixed_when_multiple_payments(self):
        order = self.invoice_a.order
        order.payment_method = "split"
        order.save()
        Payment.objects.create(tenant=self.tenant_a, order=order, amount=Decimal("50"), payment_method="cash")
        Payment.objects.create(tenant=self.tenant_a, order=order, amount=Decimal("50"), payment_method="card")
        self.assertEqual(self._payload()["PaymentMode"], 5)  # Mixed

    def test_payment_mode_uses_canonical_settled_tenders(self):
        # Checkout persists payments.TenderedPayment rows (order.tenders) —
        # the canonical tender record drives PaymentMode (audit H3).
        from payments.models import PaymentSettlement, TenderedPayment

        order = self.invoice_a.order
        settlement = PaymentSettlement.objects.create(
            tenant=self.tenant_a, order=order, total_amount=Decimal("100.00"), currency="PKR",
        )
        TenderedPayment.objects.create(tenant=self.tenant_a, settlement=settlement, order=order,
                                       tender_type="cash", amount=Decimal("60.00"))
        TenderedPayment.objects.create(tenant=self.tenant_a, settlement=settlement, order=order,
                                       tender_type="card", amount=Decimal("40.00"))
        self.assertEqual(self._payload()["PaymentMode"], 5)  # Mixed: cash + card

    def test_payment_mode_single_card_tender(self):
        from payments.models import TenderedPayment

        order = self.invoice_a.order
        TenderedPayment.objects.create(tenant=self.tenant_a, order=order,
                                       tender_type="card", amount=Decimal("100.00"))
        self.assertEqual(self._payload()["PaymentMode"], 2)  # Card

    def test_buyer_fields_are_optional(self):
        # Deleting the customer nulls both invoice.customer and order.customer
        # (SET_NULL) — IMS buyer fields are all Optional and stay blank.
        self.invoice_a.customer.delete()
        self.invoice_a.refresh_from_db()
        payload = self._payload()
        self.assertEqual(payload["BuyerName"], "")
        self.assertEqual(payload["BuyerNTN"], "")
        self.assertEqual(payload["BuyerCNIC"], "")

    def test_buyer_ntn_cnic_routing(self):
        # 13 digits -> CNIC; short digits -> NTN
        profile = self.invoice_a.customer.fbr_profile
        profile.ntn_cnic = "3520212345678"
        payload = self._payload()
        self.assertEqual(payload["BuyerCNIC"], "3520212345678")
        self.assertEqual(payload["BuyerNTN"], "")
        profile.ntn_cnic = "1234567"
        payload = self._payload()
        self.assertEqual(payload["BuyerNTN"], "1234567")
        self.assertEqual(payload["BuyerCNIC"], "")

    def test_third_schedule_item_type(self):
        invoice = self.make_invoice(
            self.tenant_a,
            "thirdschedule",
            product_profile_overrides={"third_schedule": True},
        )
        # The newly created fiscal invoice snapshots the profile.
        item = self._payload(invoice)["Items"][0]
        self.assertEqual(item["InvoiceType"], 11)  # 3rd Schedule New
        self.assertEqual(self._payload()["InvoiceType"], 1)  # header stays New

    def test_credit_note_requires_ref_usin(self):
        with self.assertRaises(FBRValidationError) as ctx:
            self._payload(di_invoice_type=4)  # credit note
        self.assertTrue(any("RefUSIN" in e for e in ctx.exception.errors))

    def test_credit_note_maps_types_and_ref(self):
        payload = self._payload(di_invoice_type=4, ref_usin="USIN0")
        self.assertEqual(payload["InvoiceType"], 3)  # Credit
        self.assertEqual(payload["RefUSIN"], "USIN0")
        self.assertEqual(payload["Items"][0]["InvoiceType"], 3)
        self.assertEqual(payload["Items"][0]["RefUSIN"], "USIN0")

    def test_debit_note_maps_header_type_2(self):
        payload = self._payload(di_invoice_type=3, ref_usin="USIN0")
        self.assertEqual(payload["InvoiceType"], 2)  # Debit

    def test_missing_product_profile_rejected(self):
        # Fiscal snapshots require an active FBR product profile at invoice
        # creation time, so this is rejected before payload construction.
        with self.assertRaises(FiscalServiceError) as ctx:
            self.make_invoice(self.tenant_a, "missingprofile", with_product_profile=False)
        self.assertIn("no active FBR profile", str(ctx.exception))
