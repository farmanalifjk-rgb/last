from django.urls import include, path
from rest_framework.routers import DefaultRouter

from operations.views import (
    ApprovalRequestViewSet,
    ApprovalRuleViewSet,
    EmailQueueViewSet,
    NotificationViewSet,
    SMSQueueViewSet,
)

router = DefaultRouter()
router.register(r"workflow/rules", ApprovalRuleViewSet, basename="workflow-rules")
router.register(r"workflow/requests", ApprovalRequestViewSet, basename="workflow-requests")
router.register(r"operations/notifications", NotificationViewSet, basename="operations-notifications")
router.register(r"notifications/email-queue", EmailQueueViewSet, basename="email-queue")
router.register(r"notifications/sms-queue", SMSQueueViewSet, basename="sms-queue")

urlpatterns = [path("", include(router.urls))]
