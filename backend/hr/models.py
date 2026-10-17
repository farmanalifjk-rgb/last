"""Canonical tenant-scoped HR and workforce models."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class TenantRecord(models.Model):
    tenant = models.ForeignKey(
        "saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records"
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Department(TenantRecord):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="hr_department_name_per_tenant")
        ]

    def __str__(self):
        return self.name


class Employee(TenantRecord):
    GENDER_CHOICES = [("male", "Male"), ("female", "Female"), ("other", "Other")]
    STATUS_ACTIVE = "active"
    STATUS_ON_LEAVE = "on_leave"
    STATUS_TERMINATED = "terminated"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_ON_LEAVE, "On Leave"),
        (STATUS_TERMINATED, "Terminated"),
    ]

    # User remains the authentication identity; Employee is tenant-local HR data.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee_profiles",
    )
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees"
    )
    employee_id = models.CharField(max_length=30)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    role = models.CharField(max_length=100, blank=True)
    hire_date = models.DateField()
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    photo = models.ImageField(upload_to="employees/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_name", "last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee_id"], name="hr_employee_reference_per_tenant"
            ),
            models.UniqueConstraint(
                fields=["tenant", "user"],
                condition=Q(user__isnull=False),
                name="hr_employee_user_per_tenant",
            ),
        ]

    def clean(self):
        if self.department_id and self.department.tenant_id != self.tenant_id:
            raise ValidationError({"department": "Department must belong to the active tenant."})

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Shift(TenantRecord):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="shifts")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "date"], name="unique_employee_shift_per_day")
        ]

    def clean(self):
        if self.employee_id and self.employee.tenant_id != self.tenant_id:
            raise ValidationError({"employee": "Employee must belong to the active tenant."})
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "Shift end time must be later than start time."})


class Attendance(TenantRecord):
    STATUS_CHOICES = [
        ("present", "Present"),
        ("absent", "Absent"),
        ("late", "Late"),
        ("half_day", "Half Day"),
        ("holiday", "Holiday"),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    clock_in = models.DateTimeField(null=True, blank=True)
    clock_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="present")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "date"], name="unique_employee_attendance_per_day")
        ]

    def clean(self):
        if self.employee_id and self.employee.tenant_id != self.tenant_id:
            raise ValidationError({"employee": "Employee must belong to the active tenant."})
        if self.clock_in and self.clock_out and self.clock_out <= self.clock_in:
            raise ValidationError({"clock_out": "Clock-out must be later than clock-in."})

    @property
    def hours_worked(self):
        if self.clock_in and self.clock_out:
            return round((self.clock_out - self.clock_in).total_seconds() / 3600, 2)
        return 0


class LeaveType(TenantRecord):
    name = models.CharField(max_length=80)
    days_allowed = models.PositiveIntegerField(default=0, help_text="Days allowed per year")
    is_paid = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="hr_leave_type_name_per_tenant")
        ]

    def __str__(self):
        return self.name


class LeaveRequest(TenantRecord):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_leave_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.employee_id and self.employee.tenant_id != self.tenant_id:
            raise ValidationError({"employee": "Employee must belong to the active tenant."})
        if self.leave_type_id and self.leave_type.tenant_id != self.tenant_id:
            raise ValidationError({"leave_type": "Leave type must belong to the active tenant."})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Leave end date cannot precede start date."})

    @property
    def total_days(self):
        return (self.end_date - self.start_date).days + 1 if self.start_date and self.end_date else 0


class PayrollRun(TenantRecord):
    STATUS_DRAFT = "draft"
    STATUS_POSTED = "posted"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_POSTED, "Posted")]

    month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    year = models.PositiveSmallIntegerField(validators=[MinValueValidator(2000)])
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "month", "year"], name="hr_payroll_period_per_tenant"
            )
        ]

    def __str__(self):
        return f"Payroll {self.year}-{self.month:02d}"


class PayrollEntry(TenantRecord):
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="entries")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT)
    basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["payroll_run", "employee"], name="unique_payroll_entry")
        ]

    def clean(self):
        if self.payroll_run_id and self.payroll_run.tenant_id != self.tenant_id:
            raise ValidationError({"payroll_run": "Payroll run must belong to the active tenant."})
        if self.employee_id and self.employee.tenant_id != self.tenant_id:
            raise ValidationError({"employee": "Employee must belong to the active tenant."})

    def save(self, *args, **kwargs):
        self.net = self.basic + self.allowances - self.deductions - self.tax
        super().save(*args, **kwargs)
