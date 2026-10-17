from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from auth_app.models import AuthToken
from audit.models import AuditEvent
from hr.models import Attendance, Employee, LeaveRequest, LeaveType, PayrollRun
from rbac.models import Module, Permission, Role, UserRole
from saas.models import Tenant, TenantMembership


User = get_user_model()


def grant(user, *permission_keys):
    role = Role.objects.create(
        key=f"phase12-{user.username}",
        label=f"Phase 12 {user.username}",
    )
    for key in permission_keys:
        module_key, action = key.split(".", 1)
        module, _ = Module.objects.get_or_create(
            key=module_key,
            defaults={"label": module_key.title()},
        )
        permission, _ = Permission.objects.get_or_create(module=module, action=action)
        role.permissions.add(permission)
    UserRole.objects.create(user=user, role=role)


class Phase12HRApiRegressionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="phase12-api-owner", password="test-password"
        )
        self.tenant = Tenant.objects.create(
            name="Phase Twelve HR", slug="phase12-hr", owner=self.owner, status=Tenant.STATUS_ACTIVE
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.owner,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )

        self.foreign_owner = User.objects.create_user(
            username="phase12-api-foreign-owner", password="test-password"
        )
        self.foreign_tenant = Tenant.objects.create(
            name="Phase Twelve Foreign",
            slug="phase12-hr-foreign",
            owner=self.foreign_owner,
            status=Tenant.STATUS_ACTIVE,
        )
        TenantMembership.objects.create(
            tenant=self.foreign_tenant,
            user=self.foreign_owner,
            role=TenantMembership.ROLE_OWNER,
            is_active_in_tenant=True,
        )

        self.viewer = User.objects.create_user(
            username="phase12-api-viewer", password="test-password"
        )
        TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.viewer,
            role=TenantMembership.ROLE_STAFF,
            is_active_in_tenant=True,
        )
        grant(self.viewer, "hr.view")

        self.employee = Employee.objects.create(
            tenant=self.tenant,
            user=self.owner,
            employee_id="P12-OWNER",
            first_name="Phase",
            last_name="Owner",
            hire_date=date(2026, 1, 1),
            basic_salary=Decimal("1200.00"),
        )
        self.foreign_employee = Employee.objects.create(
            tenant=self.foreign_tenant,
            employee_id="P12-FOREIGN",
            first_name="Foreign",
            last_name="Employee",
            hire_date=date(2026, 1, 1),
        )
        self.leave_type = LeaveType.objects.create(
            tenant=self.tenant, name="Annual", days_allowed=20, is_paid=True
        )
        self.viewer_employee = Employee.objects.create(
            tenant=self.tenant,
            user=self.viewer,
            employee_id="P12-VIEWER",
            first_name="Phase",
            last_name="Viewer",
            hire_date=date(2026, 1, 1),
            basic_salary=Decimal("900.00"),
        )

        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)
        self.viewer_client = APIClient()
        self.viewer_client.force_authenticate(self.viewer)

    def test_employee_detail_is_tenant_scoped(self):
        visible = self.owner_client.get(f"/api/hr/employees/{self.employee.id}/")
        self.assertEqual(visible.status_code, 200, visible.data)

        foreign = self.owner_client.get(f"/api/hr/employees/{self.foreign_employee.id}/")
        self.assertEqual(foreign.status_code, 404, foreign.data)

        foreign_update = self.owner_client.patch(
            f"/api/hr/employees/{self.foreign_employee.id}/",
            {"first_name": "Attempt"},
            format="json",
        )
        self.assertEqual(foreign_update.status_code, 404, foreign_update.data)

    def test_token_authenticated_request_replaces_a_stale_session_tenant_context(self):
        """A DRF token must control tenancy even when the browser has an old Django session."""
        token = AuthToken.objects.create(user=self.owner)
        browser_client = APIClient()
        browser_client.force_login(self.foreign_owner)
        browser_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = browser_client.get("/api/hr/employees/?page_size=100")

        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(
            {row["id"] for row in rows},
            {self.employee.id, self.viewer_employee.id},
        )

    def test_viewer_can_read_employees_but_cannot_mutate_or_access_payroll(self):
        listed = self.viewer_client.get("/api/hr/employees/")
        self.assertEqual(listed.status_code, 200, listed.data)

        create = self.viewer_client.post(
            "/api/hr/employees/",
            {
                "employee_id": "P12-BLOCKED",
                "first_name": "Blocked",
                "last_name": "Viewer",
                "hire_date": "2026-01-01",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 403, create.data)

        update = self.viewer_client.patch(
            f"/api/hr/employees/{self.employee.id}/",
            {"first_name": "Blocked"},
            format="json",
        )
        self.assertEqual(update.status_code, 403, update.data)

        payroll_list = self.viewer_client.get("/api/hr/payroll/")
        self.assertEqual(payroll_list.status_code, 403, payroll_list.data)
        payroll_create = self.viewer_client.post(
            "/api/hr/payroll/", {"month": 1, "year": 2026}, format="json"
        )
        self.assertEqual(payroll_create.status_code, 403, payroll_create.data)

    def test_leave_self_approval_and_attendance_duplicate_transitions_are_rejected(self):
        leave = LeaveRequest.objects.create(
            tenant=self.tenant,
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 2),
            reason="Phase 12 self-approval guard",
        )
        self_approval = self.owner_client.post(
            f"/api/hr/leave-requests/{leave.id}/approve/", format="json"
        )
        self.assertEqual(self_approval.status_code, 403, self_approval.data)
        leave.refresh_from_db()
        self.assertEqual(leave.status, LeaveRequest.STATUS_PENDING)

        attendance = Attendance.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 2, 3)
        )
        clock_out_first = self.owner_client.post(
            f"/api/hr/attendance/{attendance.id}/clock_out/", format="json"
        )
        self.assertEqual(clock_out_first.status_code, 400, clock_out_first.data)

        clock_in = self.owner_client.post(
            f"/api/hr/attendance/{attendance.id}/clock_in/", format="json"
        )
        self.assertEqual(clock_in.status_code, 200, clock_in.data)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action="hr.attendance.clocked_in",
                entity_id=str(attendance.id),
            ).exists()
        )
        duplicate_clock_in = self.owner_client.post(
            f"/api/hr/attendance/{attendance.id}/clock_in/", format="json"
        )
        self.assertEqual(duplicate_clock_in.status_code, 400, duplicate_clock_in.data)

    def test_owner_can_approve_another_employee_leave_and_it_is_audited(self):
        leave = LeaveRequest.objects.create(
            tenant=self.tenant,
            employee=self.viewer_employee,
            leave_type=self.leave_type,
            start_date=date(2026, 2, 5),
            end_date=date(2026, 2, 6),
            reason="Phase 12 owner decision regression",
        )

        approved = self.owner_client.post(
            f"/api/hr/leave-requests/{leave.id}/approve/", format="json"
        )

        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["status"], LeaveRequest.STATUS_APPROVED)
        leave.refresh_from_db()
        self.assertEqual(leave.reviewed_by, self.owner)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action="hr.leave.approved",
                entity_id=str(leave.id),
            ).exists()
        )

    def test_posted_payroll_is_immutable(self):
        payroll = PayrollRun.objects.create(
            tenant=self.tenant, month=2, year=2026, created_by=self.owner
        )
        generated = self.owner_client.post(
            f"/api/hr/payroll/{payroll.id}/generate_entries/", format="json"
        )
        self.assertEqual(generated.status_code, 200, generated.data)
        self.assertEqual(generated.data["created"], 2)

        posted = self.owner_client.post(
            f"/api/hr/payroll/{payroll.id}/post_payroll/", format="json"
        )
        self.assertEqual(posted.status_code, 200, posted.data)
        self.assertEqual(posted.data["status"], PayrollRun.STATUS_POSTED)

        update = self.owner_client.patch(
            f"/api/hr/payroll/{payroll.id}/", {"notes": "Attempted mutation"}, format="json"
        )
        self.assertEqual(update.status_code, 400, update.data)
