from django.urls import path, include
from rest_framework.routers import DefaultRouter
from hr.views import (
    DepartmentViewSet, EmployeeViewSet, ShiftViewSet,
    AttendanceViewSet, LeaveTypeViewSet, LeaveRequestViewSet,
    PayrollRunViewSet, PayrollEntryViewSet,
)

router = DefaultRouter()
router.register(r"hr/departments",     DepartmentViewSet,   basename="hr-departments")
router.register(r"hr/employees",       EmployeeViewSet,     basename="hr-employees")
router.register(r"hr/shifts",          ShiftViewSet,        basename="hr-shifts")
router.register(r"hr/attendance",      AttendanceViewSet,   basename="hr-attendance")
router.register(r"hr/leave-types",     LeaveTypeViewSet,    basename="hr-leave-types")
router.register(r"hr/leave-requests",  LeaveRequestViewSet, basename="hr-leave-requests")
router.register(r"hr/payroll",         PayrollRunViewSet,   basename="hr-payroll")
router.register(r"hr/payroll-entries", PayrollEntryViewSet, basename="hr-payroll-entries")

urlpatterns = [
    path("", include(router.urls)),
]


