from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from fbr.models import FBRHSCode, FBRProvince, FBRSROSchedule, FBRTransactionType, FBRUnitOfMeasure


class LoadReferenceDataTests(TestCase):
    def test_command_loads_every_published_code_list(self):
        call_command("load_fbr_reference_data", stdout=StringIO())

        self.assertGreater(FBRTransactionType.objects.count(), 0)
        self.assertGreater(FBRSROSchedule.objects.count(), 0)
        self.assertGreater(FBRUnitOfMeasure.objects.count(), 0)
        self.assertGreater(FBRHSCode.objects.count(), 0)
        self.assertGreater(FBRProvince.objects.count(), 0)

    def test_command_is_idempotent(self):
        call_command("load_fbr_reference_data", dataset="uom_codes", stdout=StringIO())
        first = list(FBRUnitOfMeasure.objects.values_list("code", "description").order_by("code"))

        call_command("load_fbr_reference_data", dataset="uom_codes", stdout=StringIO())
        second = list(FBRUnitOfMeasure.objects.values_list("code", "description").order_by("code"))

        self.assertEqual(first, second)

    def test_reactivating_a_retired_code_restores_it(self):
        call_command("load_fbr_reference_data", dataset="uom_codes", stdout=StringIO())
        uom = FBRUnitOfMeasure.objects.first()
        FBRUnitOfMeasure.objects.filter(pk=uom.pk).update(is_active=False, description="stale")

        call_command("load_fbr_reference_data", dataset="uom_codes", stdout=StringIO())

        uom.refresh_from_db()
        self.assertTrue(uom.is_active)
        self.assertNotEqual(uom.description, "stale")

    def test_provinces_are_loaded(self):
        call_command("load_fbr_reference_data", dataset="provinces", stdout=StringIO())
        self.assertTrue(FBRProvince.objects.filter(code="Sindh").exists())
