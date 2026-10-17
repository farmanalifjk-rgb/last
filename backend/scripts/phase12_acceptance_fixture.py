"""Provision or remove isolated Phase 12 HR browser-acceptance fixtures.

Run from the Django project directory:
    py -3.14 scripts/phase12_acceptance_fixture.py setup
    py -3.14 scripts/phase12_acceptance_fixture.py cleanup

All records are deliberately named with the P12-CERT prefix, isolated inside a
single tenant, and deleted in dependency order by the cleanup command.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction

from hr.models import Attendance, Department, Employee, LeaveRequest, LeaveType, PayrollEntry, PayrollRun, Shift
from rbac.models import Module, Permission, Role, UserRole
from saas.models import Tenant, TenantMembership


User = get_user_model()
TENANT_SLUG = "phase12-browser-cert-hr"
OWNER_USERNAME = "phase12-browser-cert-owner"
VIEWER_USERNAME = "phase12-browser-cert-viewer"
OWNER_ROLE_KEY = "phase12-browser-cert-owner-role"
VIEWER_ROLE_KEY = "phase12-browser-cert-viewer-role"
PASSWORD = "Phase12Cert!486"


def permission_for(key: str) -> Permission:
    module_key, action = key.split(".", 1)
    module, _ = Module.objects.get_or_create(
        key=module_key,
        defaults={"label": module_key.replace("_", " ").title()},
    )
    permission, _ = Permission.objects.get_or_create(module=module, action=action)
    return permission


@transaction.atomic
def cleanup() -> None:
    """Delete only P12-CERT tenant data, temporary users, and temporary roles."""
    tenant_ids = list(Tenant.objects.filter(slug=TENANT_SLUG).values_list("id", flat=True))
    if tenant_ids:
        PayrollEntry.objects.filter(tenant_id__in=tenant_ids).delete()
        PayrollRun.objects.filter(tenant_id__in=tenant_ids).delete()
        LeaveRequest.objects.filter(tenant_id__in=tenant_ids).delete()
        Attendance.objects.filter(tenant_id__in=tenant_ids).delete()
        Shift.objects.filter(tenant_id__in=tenant_ids).delete()
        Employee.objects.filter(tenant_id__in=tenant_ids).delete()
        LeaveType.objects.filter(tenant_id__in=tenant_ids).delete()
        Department.objects.filter(tenant_id__in=tenant_ids).delete()
        Tenant.objects.filter(id__in=tenant_ids).delete()
    User.objects.filter(username__in=[OWNER_USERNAME, VIEWER_USERNAME]).delete()
    Role.objects.filter(key__in=[OWNER_ROLE_KEY, VIEWER_ROLE_KEY]).delete()
    print("Phase 12 HR browser-acceptance fixtures removed.")


@transaction.atomic
def setup() -> None:
    """Create isolated owner/viewer users and only API-supported HR records."""
    cleanup()
    for key in ("hr.view", "hr.create", "hr.update", "hr.manage"):
        permission_for(key)

    owner = User.objects.create_user(
        username=OWNER_USERNAME,
        password=PASSWORD,
        first_name="Phase 12",
        last_name="Certification Owner",
        email="phase12-owner@example.test",
    )
    viewer = User.objects.create_user(
        username=VIEWER_USERNAME,
        password=PASSWORD,
        first_name="Phase 12",
        last_name="Certification Viewer",
        email="phase12-viewer@example.test",
    )
    tenant = Tenant.objects.create(
        name="P12-CERT HR Browser Acceptance",
        slug=TENANT_SLUG,
        owner=owner,
        status=Tenant.STATUS_ACTIVE,
        is_active=True,
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=owner,
        role=TenantMembership.ROLE_OWNER,
        is_active_in_tenant=True,
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=viewer,
        role=TenantMembership.ROLE_STAFF,
        is_active_in_tenant=True,
    )

    owner_role = Role.objects.create(
        key=OWNER_ROLE_KEY,
        label="Phase 12 Certification Owner",
        description="Disposable browser acceptance role with the current permission catalog.",
    )
    owner_role.permissions.set(Permission.objects.all())
    UserRole.objects.create(user=owner, role=owner_role)

    viewer_role = Role.objects.create(
        key=VIEWER_ROLE_KEY,
        label="Phase 12 Certification Viewer",
        description="Disposable browser acceptance role with HR read permission only.",
    )
    viewer_role.permissions.add(permission_for("hr.view"))
    UserRole.objects.create(user=viewer, role=viewer_role)

    department = Department.objects.create(
        tenant=tenant,
        name="P12-CERT Operations",
        description="Disposable Phase 12 HR browser-acceptance department.",
    )
    owner_employee = Employee.objects.create(
        tenant=tenant,
        user=owner,
        department=department,
        employee_id="P12-CERT-OWNER",
        first_name="Phase",
        last_name="Owner",
        role="HR Director",
        hire_date=date(2025, 1, 1),
        basic_salary="5000.00",
    )
    viewer_employee = Employee.objects.create(
        tenant=tenant,
        user=viewer,
        department=department,
        employee_id="P12-CERT-VIEWER",
        first_name="Phase",
        last_name="Viewer",
        role="Operations Associate",
        hire_date=date(2025, 2, 1),
        basic_salary="3000.00",
    )
    Shift.objects.create(
        tenant=tenant,
        employee=owner_employee,
        date=date.today(),
        start_time="09:00",
        end_time="17:00",
        notes="Disposable browser acceptance shift.",
    )
    attendance = Attendance.objects.create(
        tenant=tenant,
        employee=owner_employee,
        date=date.today(),
        status="present",
        notes="Disposable browser acceptance attendance record.",
    )
    leave_type = LeaveType.objects.create(
        tenant=tenant,
        name="P12-CERT Annual",
        days_allowed=20,
        is_paid=True,
    )
    leave_request = LeaveRequest.objects.create(
        tenant=tenant,
        employee=viewer_employee,
        leave_type=leave_type,
        start_date=date.today() + timedelta(days=7),
        end_date=date.today() + timedelta(days=8),
        reason="Disposable browser acceptance leave request.",
    )
    payroll = PayrollRun.objects.create(
        tenant=tenant,
        month=date.today().month,
        year=date.today().year,
        notes="Disposable draft payroll for browser acceptance.",
        created_by=owner,
    )

    print(
        "Phase 12 HR browser-acceptance fixtures ready:\n"
        f"  tenant={tenant.slug} id={tenant.id}\n"
        f"  owner={OWNER_USERNAME} password={PASSWORD}\n"
        f"  viewer={VIEWER_USERNAME} password={PASSWORD}\n"
        f"  department={department.id} employee={owner_employee.id} attendance={attendance.id}\n"
        f"  leave_request={leave_request.id} payroll={payroll.id}"
    )


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command == "setup":
        setup()
    elif command == "cleanup":
        cleanup()
    else:
        raise SystemExit("Usage: py -3.14 scripts/phase12_acceptance_fixture.py [setup|cleanup]")
