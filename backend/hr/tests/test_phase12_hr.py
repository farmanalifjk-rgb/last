from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from hr.models import Department, Employee, LeaveRequest, LeaveType, PayrollRun, Shift
from saas.models import Tenant


class Phase12HRModelIntegrityTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="phase12-owner", password="unused-test-password")
        self.tenant_a = Tenant.objects.create(name="Phase 12 Tenant A", slug="phase12-tenant-a", owner=owner)
        self.tenant_b = Tenant.objects.create(name="Phase 12 Tenant B", slug="phase12-tenant-b", owner=owner)
        self.department_a = Department.objects.create(tenant=self.tenant_a, name="Operations")
        self.department_b = Department.objects.create(tenant=self.tenant_b, name="Operations")
        self.employee_a = Employee.objects.create(
            tenant=self.tenant_a,
            department=self.department_a,
            employee_id="EMP-001",
            first_name="Tenant",
            last_name="One",
            hire_date=date(2026, 1, 1),
        )

    def test_tenant_scoped_names_and_references_allow_same_values_across_tenants(self):
        employee_b = Employee.objects.create(
            tenant=self.tenant_b,
            department=self.department_b,
            employee_id="EMP-001",
            first_name="Tenant",
            last_name="Two",
            hire_date=date(2026, 1, 1),
        )
        self.assertNotEqual(self.employee_a.pk, employee_b.pk)
        with self.assertRaises(ValidationError):
            Department.objects.create(tenant=self.tenant_a, name="Operations")

    def test_cross_tenant_relations_are_rejected(self):
        employee = Employee(
            tenant=self.tenant_b,
            department=self.department_a,
            employee_id="EMP-002",
            first_name="Cross",
            last_name="Tenant",
            hire_date=date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            employee.full_clean()

    def test_shift_and_leave_date_rules_are_enforced(self):
        shift = Shift(
            tenant=self.tenant_a,
            employee=self.employee_a,
            date=date(2026, 2, 1),
            start_time=time(17, 0),
            end_time=time(9, 0),
        )
        with self.assertRaises(ValidationError):
            shift.full_clean()
        leave_type = LeaveType.objects.create(tenant=self.tenant_a, name="Annual")
        leave = LeaveRequest(
            tenant=self.tenant_a,
            employee=self.employee_a,
            leave_type=leave_type,
            start_date=date(2026, 3, 5),
            end_date=date(2026, 3, 4),
        )
        with self.assertRaises(ValidationError):
            leave.full_clean()

    def test_payroll_period_is_unique_per_tenant_not_globally(self):
        PayrollRun.objects.create(tenant=self.tenant_a, month=1, year=2026)
        PayrollRun.objects.create(tenant=self.tenant_b, month=1, year=2026)
        with self.assertRaises(ValidationError):
            PayrollRun.objects.create(tenant=self.tenant_a, month=1, year=2026)
