"""Canonical tenant-scoped HR API views and serializers."""
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from audit.recorder import record
from rbac.checker import has_permission
from saas.models import TenantMembership
from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin

from hr.models import (
    Attendance,
    Department,
    Employee,
    LeaveRequest,
    LeaveType,
    PayrollEntry,
    PayrollRun,
    Shift,
)


def can_manage_hr(request):
    return has_permission(request.user, "hr", "manage", tenant=request.tenant)


class TenantSerializerMixin:
    def active_tenant(self):
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            if getattr(self.context.get("view"), "swagger_fake_view", False):
                return None
            raise ValidationError("An active tenant is required.")
        return tenant

    def tenant_queryset(self, model):
        tenant = self.active_tenant()
        return model.objects.filter(tenant=tenant) if tenant is not None else model.objects.none()


class DepartmentSerializer(TenantSerializerMixin, serializers.ModelSerializer):
    employee_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ["id", "tenant", "name", "description", "created_at", "employee_count"]
        read_only_fields = ["id", "tenant", "employee_count", "created_at"]

    def get_employee_count(self, obj):
        return obj.employees.count()


class EmployeeSerializer(TenantSerializerMixin, serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Employee
        fields = [
            "id", "user", "department", "department_name", "employee_id", "first_name", "last_name",
            "full_name", "gender", "date_of_birth", "phone", "email", "address", "role", "hire_date",
            "basic_salary", "status", "photo", "created_at",
        ]
        read_only_fields = ["id", "tenant", "created_at"]

    def get_fields(self):
        fields = super().get_fields()
        fields["department"].queryset = self.tenant_queryset(Department)
        return fields

    def validate_user(self, user):
        tenant = self.active_tenant()
        if user and not TenantMembership.objects.filter(
            tenant=tenant, user=user, is_active_in_tenant=True
        ).exists():
            raise ValidationError("Linked user must be an active tenant member.")
        return user

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request and not can_manage_hr(request):
            data.pop("basic_salary", None)
            data.pop("date_of_birth", None)
            data.pop("address", None)
        return data


class ShiftSerializer(TenantSerializerMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = Shift
        fields = ["id", "tenant", "employee", "employee_name", "date", "start_time", "end_time", "notes", "created_at"]
        read_only_fields = ["id", "tenant", "employee_name", "created_at"]

    def get_fields(self):
        fields = super().get_fields()
        fields["employee"].queryset = self.tenant_queryset(Employee)
        return fields


class AttendanceSerializer(TenantSerializerMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    hours_worked = serializers.FloatField(read_only=True)

    class Meta:
        model = Attendance
        fields = ["id", "tenant", "employee", "employee_name", "date", "clock_in", "clock_out", "status", "notes", "hours_worked"]
        read_only_fields = ["id", "tenant", "employee_name", "clock_in", "clock_out", "hours_worked"]

    def get_fields(self):
        fields = super().get_fields()
        fields["employee"].queryset = self.tenant_queryset(Employee)
        return fields


class LeaveTypeSerializer(TenantSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "name", "days_allowed", "is_paid"]
        read_only_fields = ["id"]


class LeaveRequestSerializer(TenantSerializerMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    total_days = serializers.IntegerField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "employee", "employee_name", "leave_type", "leave_type_name", "start_date", "end_date",
            "reason", "status", "reviewed_by", "reviewed_at", "total_days", "created_at",
        ]
        read_only_fields = ["id", "tenant", "created_at"]

    def get_fields(self):
        fields = super().get_fields()
        fields["employee"].queryset = self.tenant_queryset(Employee)
        fields["leave_type"].queryset = self.tenant_queryset(LeaveType)
        return fields


class PayrollEntrySerializer(TenantSerializerMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = PayrollEntry
        fields = ["id", "tenant", "payroll_run", "employee", "employee_name", "basic", "allowances", "deductions", "tax", "net"]
        read_only_fields = fields


class PayrollRunSerializer(TenantSerializerMixin, serializers.ModelSerializer):
    total_net = serializers.SerializerMethodField()
    entry_count = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRun
        fields = ["id", "tenant", "month", "year", "status", "notes", "created_by", "created_at", "total_net", "entry_count"]
        read_only_fields = ["id", "status", "created_by", "created_at", "total_net", "entry_count"]

    def get_total_net(self, obj):
        return sum((entry.net for entry in obj.entries.all()), 0)

    def get_entry_count(self, obj):
        return obj.entries.count()


class HRViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    rbac_module = "hr"
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    permission_by_action = {}

    def get_permissions(self):
        self.rbac_action = self.permission_by_action.get(self.action)
        return [permission() for permission in self.permission_classes]

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")

    def _audit(self, action, instance, summary):
        record(actor=self.request.user, action=action, instance=instance, request=self.request, summary=summary, icon="users")

    def perform_create(self, serializer):
        instance = serializer.save(tenant=self.request.tenant)
        self._audit(f"hr.{self.basename}.created", instance, f"Created {instance._meta.verbose_name}.")

    def perform_update(self, serializer):
        instance = serializer.save()
        self._audit(f"hr.{self.basename}.updated", instance, f"Updated {instance._meta.verbose_name}.")


class DepartmentViewSet(HRViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    rbac_module = "hr"

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("employees")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class EmployeeViewSet(HRViewSet):
    queryset = Employee.objects.select_related("department", "user").all()
    serializer_class = EmployeeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        department = self.request.query_params.get("department")
        state = self.request.query_params.get("status")
        search = self.request.query_params.get("search")
        if department:
            qs = qs.filter(department_id=department)
        if state:
            qs = qs.filter(status=state)
        if search:
            qs = qs.filter(first_name__icontains=search) | qs.filter(last_name__icontains=search) | qs.filter(employee_id__icontains=search)
        return qs

    def _reject_salary_change(self, serializer):
        if "basic_salary" in serializer.validated_data and not can_manage_hr(self.request):
            raise PermissionDenied("Salary data requires HR manage permission.")

    def perform_create(self, serializer):
        self._reject_salary_change(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._reject_salary_change(serializer)
        super().perform_update(serializer)


class ShiftViewSet(HRViewSet):
    queryset = Shift.objects.select_related("employee").all()
    serializer_class = ShiftSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if employee := self.request.query_params.get("employee"):
            qs = qs.filter(employee_id=employee)
        if day := self.request.query_params.get("date"):
            qs = qs.filter(date=day)
        return qs


class AttendanceViewSet(HRViewSet):
    queryset = Attendance.objects.select_related("employee").all()
    serializer_class = AttendanceSerializer
    permission_by_action = {"clock_in": "update", "clock_out": "update"}

    def get_queryset(self):
        qs = super().get_queryset()
        if employee := self.request.query_params.get("employee"):
            qs = qs.filter(employee_id=employee)
        if day := self.request.query_params.get("date"):
            qs = qs.filter(date=day)
        if state := self.request.query_params.get("status"):
            qs = qs.filter(status=state)
        return qs

    @action(detail=True, methods=["post"])
    def clock_in(self, request, pk=None):
        attendance = self.get_object()
        if attendance.clock_in:
            raise ValidationError("This attendance record is already clocked in.")
        attendance.clock_in = timezone.now()
        attendance.status = "present"
        attendance.full_clean()
        attendance.save(update_fields=["clock_in", "status"])
        self._audit("hr.attendance.clocked_in", attendance, "Recorded server-side attendance clock-in.")
        return Response(self.get_serializer(attendance).data)

    @action(detail=True, methods=["post"])
    def clock_out(self, request, pk=None):
        attendance = self.get_object()
        if not attendance.clock_in:
            raise ValidationError("Clock-in is required before clock-out.")
        if attendance.clock_out:
            raise ValidationError("This attendance record is already clocked out.")
        attendance.clock_out = timezone.now()
        attendance.full_clean()
        attendance.save(update_fields=["clock_out"])
        self._audit("hr.attendance.clocked_out", attendance, "Recorded server-side attendance clock-out.")
        return Response(self.get_serializer(attendance).data)


class LeaveTypeViewSet(HRViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer


class LeaveRequestViewSet(HRViewSet):
    queryset = LeaveRequest.objects.select_related("employee", "leave_type", "reviewed_by").all()
    serializer_class = LeaveRequestSerializer
    permission_by_action = {"approve": "manage", "reject": "manage"}

    def get_queryset(self):
        qs = super().get_queryset()
        if employee := self.request.query_params.get("employee"):
            qs = qs.filter(employee_id=employee)
        if state := self.request.query_params.get("status"):
            qs = qs.filter(status=state)
        return qs

    def perform_update(self, serializer):
        if self.get_object().status != LeaveRequest.STATUS_PENDING:
            raise ValidationError("Processed leave requests cannot be edited.")
        super().perform_update(serializer)

    def _decide(self, request, pk, decision):
        with transaction.atomic():
            # ``reviewed_by`` is a nullable select-related relation. PostgreSQL
            # cannot apply ``FOR UPDATE`` to that outer-joined table, so lock
            # only the LeaveRequest row whose pending state is being decided.
            leave = self.get_queryset().select_for_update(of=("self",)).get(pk=pk)
            if leave.status != LeaveRequest.STATUS_PENDING:
                raise ValidationError("Only pending leave requests can be decided.")
            if leave.employee.user_id and leave.employee.user_id == request.user.id:
                raise PermissionDenied("Employees cannot decide their own leave request.")
            leave.status = decision
            leave.reviewed_by = request.user
            leave.reviewed_at = timezone.now()
            leave.full_clean()
            leave.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        self._audit(f"hr.leave.{decision}", leave, f"{decision.title()} leave request.")
        return Response(self.get_serializer(leave).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, pk, LeaveRequest.STATUS_APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, pk, LeaveRequest.STATUS_REJECTED)


class PayrollRunViewSet(HRViewSet):
    queryset = PayrollRun.objects.prefetch_related("entries").all()
    serializer_class = PayrollRunSerializer
    rbac_action = "manage"
    permission_by_action = {
        "list": "manage", "retrieve": "manage", "create": "manage", "update": "manage",
        "partial_update": "manage", "generate_entries": "manage", "post_payroll": "manage",
    }

    def perform_create(self, serializer):
        payroll = serializer.save(tenant=self.request.tenant, created_by=self.request.user)
        self._audit("hr.payroll.created", payroll, "Created draft payroll run.")

    def perform_update(self, serializer):
        if self.get_object().status != PayrollRun.STATUS_DRAFT:
            raise ValidationError("Posted payroll runs are immutable.")
        super().perform_update(serializer)

    @action(detail=True, methods=["post"])
    def generate_entries(self, request, pk=None):
        with transaction.atomic():
            payroll = self.get_queryset().select_for_update().get(pk=pk)
            if payroll.status != PayrollRun.STATUS_DRAFT:
                raise ValidationError("Entries can only be generated for draft payroll.")
            employees = Employee.objects.filter(tenant=payroll.tenant, status__in=[Employee.STATUS_ACTIVE, Employee.STATUS_ON_LEAVE])
            created = 0
            for employee in employees:
                _, is_created = PayrollEntry.objects.get_or_create(
                    tenant=payroll.tenant,
                    payroll_run=payroll,
                    employee=employee,
                    defaults={"basic": employee.basic_salary},
                )
                created += int(is_created)
        self._audit("hr.payroll.entries_generated", payroll, f"Generated {created} payroll entries.")
        return Response({"created": created, "payroll": self.get_serializer(payroll).data})

    @action(detail=True, methods=["post"])
    def post_payroll(self, request, pk=None):
        with transaction.atomic():
            payroll = self.get_queryset().select_for_update().get(pk=pk)
            if payroll.status != PayrollRun.STATUS_DRAFT:
                raise ValidationError("Payroll is already posted.")
            if not payroll.entries.exists():
                raise ValidationError("Payroll entries must be generated before posting.")
            payroll.status = PayrollRun.STATUS_POSTED
            payroll.save(update_fields=["status"])
        self._audit("hr.payroll.posted", payroll, "Posted payroll run; accounting mapping remains policy required.")
        return Response(self.get_serializer(payroll).data)


class PayrollEntryViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    rbac_module = "hr"
    rbac_action = "manage"
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    queryset = PayrollEntry.objects.select_related("employee", "payroll_run").all()
    serializer_class = PayrollEntrySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if payroll_run := self.request.query_params.get("payroll_run"):
            qs = qs.filter(payroll_run_id=payroll_run)
        if employee := self.request.query_params.get("employee"):
            qs = qs.filter(employee_id=employee)
        return qs


