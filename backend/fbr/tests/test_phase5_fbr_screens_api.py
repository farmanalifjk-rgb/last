"""Phase 5: backend capabilities behind the FBR retail setup screens.

* GET/PATCH /api/fiscal/sequences/<id>/ (numbering locked once used; no DELETE)
* /api/fiscal/invoices/ ?search= ?status= ?fbr_status= and opt-in pagination
* /api/fbr/submissions/ ?status= ?search=, opt-in pagination, allowed_actions
* /api/fbr/product-profiles/ ?search=, opt-in pagination, product name/SKU
* audit events for configuration/profile/sequence changes, retry, reconcile
No network: submissions are created in the database in each state.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings

from audit.models import AuditEvent
from fbr.models import FBRSubmission
from fiscal.models import InvoiceSequence
from rbac.models import Permission, Role, UserRole
from saas.models import TenantMembership

from .base import FBRTestBase

User = get_user_model()


def _fields(response):
    """Field errors from the API's validation envelope."""
    return response.data["error"]["fields"]


def _rows(response):
    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


@override_settings(ROOT_URLCONF="backend.urls")
class Phase5Base(FBRTestBase):
    def setUp(self):
        super().setUp()
        self.owner = self.api_client(self.user_a)

    def submission(self, invoice, status, **extra):
        values = {"tenant": invoice.tenant, "invoice": invoice, "environment": "sandbox", "status": status,
                  "integration_mode": "ims", "usin": f"U-{invoice.id}-{status}", "attempts": 1}
        values.update(extra)
        return FBRSubmission.objects.create(**values)

    def member(self, username, permissions):
        user = User.objects.create_user(username=username, password="x-pass-123")
        TenantMembership.objects.create(tenant=self.tenant_a, user=user, role="staff", is_active_in_tenant=True)
        role = Role.objects.create(key=f"p5-{username}", label=username, tenant=self.tenant_a)
        for key in permissions:
            module, action = key.split(".")
            role.permissions.add(*Permission.objects.filter(module__key=module, action=action, scope="tenant"))
        UserRole.objects.create(user=user, role=role, tenant=self.tenant_a)
        return self.api_client(user)


class SequenceDetailTests(Phase5Base):
    def test_unused_sequence_numbering_is_editable_and_audited(self):
        sequence = InvoiceSequence.objects.create(tenant=self.tenant_a, name="Spare", prefix="SP", next_number=1)
        response = self.owner.patch(f"/api/fiscal/sequences/{sequence.id}/",
                                    {"prefix": "SP2", "next_number": 50, "padding": 8}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        sequence.refresh_from_db()
        self.assertEqual((sequence.prefix, sequence.next_number, sequence.padding), ("SP2", 50, 8))
        self.assertEqual(response.data["invoices_issued"], 0)
        event = AuditEvent.objects.get(tenant=self.tenant_a, action="fiscal.sequence.updated")
        self.assertEqual((event.before["prefix"], event.after["prefix"]), ("SP", "SP2"))

    def test_used_sequence_numbering_is_locked_but_name_and_active_flag_are_not(self):
        sequence = self.invoice_a.sequence
        locked = self.owner.patch(f"/api/fiscal/sequences/{sequence.id}/", {"next_number": 1, "prefix": "X"}, format="json")
        self.assertEqual(locked.status_code, 400, locked.data)
        self.assertEqual(set(_fields(locked)), {"next_number", "prefix"})
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_number, 2)
        ok = self.owner.patch(f"/api/fiscal/sequences/{sequence.id}/", {"name": "Till 1", "is_active": False}, format="json")
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(ok.data["invoices_issued"], 1)
        self.assertFalse(InvoiceSequence.objects.get(pk=sequence.pk).is_active)

    def test_unchanged_numbering_values_in_a_full_payload_are_accepted(self):
        sequence = InvoiceSequence.objects.get(pk=self.invoice_a.sequence_id)  # fresh next_number
        payload = {"name": "Renamed", "prefix": sequence.prefix, "next_number": sequence.next_number,
                   "padding": sequence.padding, "document_type": sequence.document_type, "is_active": True}
        response = self.owner.patch(f"/api/fiscal/sequences/{sequence.id}/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_validation_delete_isolation_and_rbac(self):
        sequence = InvoiceSequence.objects.create(tenant=self.tenant_a, name="Spare", prefix="SP")
        url = f"/api/fiscal/sequences/{sequence.id}/"
        bad = self.owner.patch(url, {"padding": 0, "prefix": "  ", "next_number": 0}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(set(_fields(bad)), {"padding", "prefix", "next_number"})
        self.assertEqual(self.owner.delete(url).status_code, 405)
        self.assertEqual(self.api_client(self.user_b).patch(url, {"name": "x"}, format="json").status_code, 404)
        viewer = self.member("fiscal_viewer", ["fiscal.view"])
        self.assertEqual(viewer.patch(url, {"name": "x"}, format="json").status_code, 403)
        self.assertEqual(InvoiceSequence.objects.get(pk=sequence.pk).name, "Spare")

    def test_create_validates_and_is_audited(self):
        bad = self.owner.post("/api/fiscal/sequences/", {"name": "N", "prefix": "P", "padding": 20}, format="json")
        self.assertEqual(bad.status_code, 400)
        ok = self.owner.post("/api/fiscal/sequences/", {"name": "Till 2", "prefix": "T2"}, format="json")
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant_a, action="fiscal.sequence.created").exists())


class FiscalInvoiceHistoryTests(Phase5Base):
    def setUp(self):
        super().setUp()
        self.inv_rejected = self.make_invoice(self.tenant_a, "r")
        self.inv_simulated = self.make_invoice(self.tenant_a, "s")
        self.inv_accepted = self.make_invoice(self.tenant_a, "k")
        self.submission(self.inv_rejected, "rejected", error_message="Invalid POS ID.", error_code="401")
        self.submission(self.inv_simulated, "accepted", is_simulated=True, fbr_invoice_number="SIM-1")
        self.submission(self.inv_accepted, "failed")
        self.submission(self.inv_accepted, "accepted", fbr_invoice_number="FBR-777")
        self.make_invoice(self.tenant_b, "other")

    def test_unpaginated_response_is_unchanged_for_existing_clients(self):
        response = self.owner.get("/api/fiscal/invoices/")
        self.assertIsInstance(response.data, list)
        self.assertIn("xml_content", response.data[0])

    def test_paginated_history_rows_are_compact_and_tenant_scoped(self):
        response = self.owner.get("/api/fiscal/invoices/?page=1&page_size=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["count"], response.data["total_pages"]), (4, 2))
        row = response.data["results"][0]
        self.assertNotIn("xml_content", row)
        self.assertEqual(row["invoice_number"], self.inv_accepted.invoice_number)  # newest first
        self.assertEqual(row["order_number"], self.inv_accepted.order.order_number)
        self.assertEqual((row["fbr"]["status"], row["fbr"]["fbr_invoice_number"]), ("accepted", "FBR-777"))

    def test_fbr_status_filter_distinguishes_simulated_from_accepted(self):
        def ids(query):
            return {row["id"] for row in _rows(self.owner.get(f"/api/fiscal/invoices/?page=1&{query}"))}

        self.assertEqual(ids("fbr_status=accepted"), {self.inv_accepted.id})
        self.assertEqual(ids("fbr_status=simulated"), {self.inv_simulated.id})
        self.assertEqual(ids("fbr_status=rejected"), {self.inv_rejected.id})
        self.assertEqual(ids("fbr_status=not_submitted"), {self.invoice_a.id})
        simulated = _rows(self.owner.get("/api/fiscal/invoices/?page=1&fbr_status=simulated"))[0]["fbr"]
        # A simulator number is never surfaced as an FBR invoice number.
        self.assertEqual((simulated["status"], simulated["fbr_invoice_number"]), ("simulated", ""))
        rejected = _rows(self.owner.get("/api/fiscal/invoices/?page=1&fbr_status=rejected"))[0]["fbr"]
        self.assertEqual((rejected["error_code"], rejected["error_message"]), ("401", "Invalid POS ID."))

    def test_search_matches_invoice_and_order_numbers(self):
        by_invoice = _rows(self.owner.get(f"/api/fiscal/invoices/?page=1&search={self.inv_rejected.invoice_number}"))
        self.assertEqual([row["id"] for row in by_invoice], [self.inv_rejected.id])
        by_order = _rows(self.owner.get(f"/api/fiscal/invoices/?search={self.inv_simulated.order.order_number}"))
        self.assertEqual([row["id"] for row in by_order], [self.inv_simulated.id])
        self.assertEqual(_rows(self.owner.get("/api/fiscal/invoices/?page=1&search=INVOTHER")), [])

    def test_cashier_without_fiscal_permission_is_refused(self):
        cashier = self.member("till_only", ["pos.view", "pos.create"])
        self.assertEqual(cashier.get("/api/fiscal/invoices/?page=1").status_code, 403)
        self.assertEqual(cashier.get("/api/fbr/submissions/?page=1").status_code, 403)


class SubmissionManagementTests(Phase5Base):
    def setUp(self):
        super().setUp()
        self.failed = self.submission(self.invoice_a, "failed", error_message="IMS component not responding")
        inv_unknown = self.make_invoice(self.tenant_a, "u")
        self.unknown = self.submission(inv_unknown, "unknown")
        inv_done = self.make_invoice(self.tenant_a, "d")
        self.failed_then_accepted = self.submission(inv_done, "failed")
        self.accepted = self.submission(inv_done, "accepted", fbr_invoice_number="FBR-1")
        inv_sim = self.make_invoice(self.tenant_a, "s")
        self.simulated = self.submission(inv_sim, "accepted", is_simulated=True, fbr_invoice_number="SIM-9")
        self.validation = self.submission(self.make_invoice(self.tenant_a, "v"), "failed", is_validate=True)
        self.other_tenant = self.submission(self.make_invoice(self.tenant_b, "x"), "failed")

    def actions(self, client, submission):
        response = client.get(f"/api/fbr/submissions/{submission.id}/")
        self.assertEqual(response.status_code, 200)
        return response.data["allowed_actions"]

    def test_allowed_actions_follow_the_service_rules(self):
        self.assertEqual(self.actions(self.owner, self.failed), {"retry": True, "reconcile": False})
        # Unknown outcome: never retry before reconciling.
        self.assertEqual(self.actions(self.owner, self.unknown), {"retry": False, "reconcile": True})
        # The invoice was accepted later: nothing to retry.
        self.assertEqual(self.actions(self.owner, self.failed_then_accepted), {"retry": False, "reconcile": False})
        self.assertEqual(self.actions(self.owner, self.accepted), {"retry": False, "reconcile": False})
        self.assertEqual(self.actions(self.owner, self.validation), {"retry": False, "reconcile": False})

    def test_allowed_actions_respect_rbac(self):
        viewer = self.member("fiscal_viewer2", ["fiscal.view"])
        self.assertEqual(self.actions(viewer, self.failed), {"retry": False, "reconcile": False})
        self.assertEqual(self.actions(viewer, self.unknown), {"retry": False, "reconcile": False})
        operator = self.member("fiscal_operator", ["fiscal.view", "fiscal.create"])
        self.assertEqual(self.actions(operator, self.failed), {"retry": True, "reconcile": False})
        self.assertEqual(self.actions(operator, self.unknown), {"retry": False, "reconcile": False})
        # The endpoints agree with the flags.
        self.assertEqual(viewer.post(f"/api/fbr/submissions/{self.failed.id}/retry/").status_code, 403)
        self.assertEqual(operator.post(f"/api/fbr/submissions/{self.unknown.id}/reconcile/",
                                       {"outcome": "not_fiscalized"}, format="json").status_code, 403)

    def test_status_filter_search_and_pagination(self):
        def ids(query):
            return {row["id"] for row in _rows(self.owner.get(f"/api/fbr/submissions/?page=1&page_size=50&{query}"))}

        self.assertEqual(ids("status=accepted"), {self.accepted.id})
        self.assertEqual(ids("status=simulated"), {self.simulated.id})
        self.assertEqual(ids("status=unknown"), {self.unknown.id})
        self.assertEqual(ids("status=failed"), {self.failed.id, self.failed_then_accepted.id, self.validation.id})
        self.assertNotIn(self.other_tenant.id, ids(""))
        self.assertEqual(ids(f"search={self.unknown.usin}"), {self.unknown.id})
        self.assertEqual(ids(f"search={self.invoice_a.invoice_number}"), {self.failed.id})
        page = self.owner.get("/api/fbr/submissions/?page=1&page_size=2").data
        self.assertEqual((page["count"], len(page["results"])), (6, 2))
        row = page["results"][0]
        self.assertIn("invoice_number", row)
        self.assertIn("order_number", row)
        self.assertIsInstance(self.owner.get("/api/fbr/submissions/").data, list)

    def test_retry_of_unknown_is_refused_and_reconcile_is_audited(self):
        refused = self.owner.post(f"/api/fbr/submissions/{self.unknown.id}/retry/")
        self.assertEqual(refused.status_code, 400)
        self.assertIn("Reconcile", refused.data["error"])
        self.assertEqual(FBRSubmission.objects.get(pk=self.unknown.pk).attempts, 1)
        reconciled = self.owner.post(f"/api/fbr/submissions/{self.unknown.id}/reconcile/",
                                     {"outcome": "not_fiscalized"}, format="json")
        self.assertEqual(reconciled.status_code, 200, reconciled.data)
        self.assertEqual(reconciled.data["status"], "failed")
        self.assertEqual(reconciled.data["allowed_actions"], {"retry": True, "reconcile": False})
        event = AuditEvent.objects.get(tenant=self.tenant_a, action="fbr.submission.reconciled")
        self.assertEqual(event.after["outcome"], "not_fiscalized")

    def test_retry_is_audited_with_its_outcome(self):
        failed_again = FBRSubmission(status="failed", attempts=2, is_simulated=False, tenant=self.tenant_a,
                                     invoice=self.invoice_a, pk=self.failed.pk)
        with patch("fbr.views.retry_submission", return_value=failed_again):
            response = self.owner.post(f"/api/fbr/submissions/{self.failed.id}/retry/")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["status"], "failed")
        event = AuditEvent.objects.get(tenant=self.tenant_a, action="fbr.submission.retried")
        self.assertEqual((event.after["status"], event.after["attempts"]), ("failed", 2))


class ConfigurationAndProfileAuditTests(Phase5Base):
    def test_configuration_update_is_audited_without_the_token(self):
        response = self.owner.patch(f"/api/fbr/configurations/{self.config_a.id}/",
                                    {"seller_address": "New address", "security_token": "rotated-secret"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("security_token", response.data)
        self.assertTrue(response.data["has_security_token"])
        event = AuditEvent.objects.get(tenant=self.tenant_a, action="fbr.configuration.updated")
        self.assertEqual(event.after["seller_address"], "New address")
        self.assertTrue(event.after["has_security_token"])
        serialized = str(event.before) + str(event.after)
        self.assertNotIn("rotated-secret", serialized)
        self.assertNotIn("test-token", serialized)

    def test_product_profiles_search_paginate_and_name_the_product(self):
        self.make_invoice(self.tenant_a, "laptop")
        page = self.owner.get("/api/fbr/product-profiles/?page=1&page_size=1").data
        self.assertEqual((page["count"], len(page["results"])), (2, 1))
        found = _rows(self.owner.get("/api/fbr/product-profiles/?page=1&search=SKU-LAPTOP"))
        self.assertEqual([(row["product_name"], row["product_sku"]) for row in found], [("Product laptop", "SKU-LAPTOP")])
        self.assertIsInstance(self.owner.get("/api/fbr/product-profiles/").data, list)
        profile_id = found[0]["id"]
        self.assertEqual(self.owner.patch(f"/api/fbr/product-profiles/{profile_id}/", {"sales_tax_rate": "17.000"},
                                          format="json").status_code, 200)
        event = AuditEvent.objects.get(tenant=self.tenant_a, action="fbr.product_profile.updated")
        self.assertEqual((event.before["sales_tax_rate"], event.after["sales_tax_rate"]), ("18.000", "17.000"))
        self.assertEqual(self.api_client(self.user_b).get(f"/api/fbr/product-profiles/{profile_id}/").status_code, 404)

    def test_duplicate_profile_for_a_product_is_a_validation_error(self):
        existing = _rows(self.owner.get("/api/fbr/product-profiles/"))[0]
        response = self.owner.post("/api/fbr/product-profiles/", {
            "product": existing["product"], "hs_code": self.hs_code.id, "uom": self.uom.id,
            "sales_tax_rate": "18.000",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("product", _fields(response))
