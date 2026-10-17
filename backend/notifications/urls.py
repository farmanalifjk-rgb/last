from django.urls import path
from .views import (AlertRuleListCreateView, AlertRuleDetailView, NotificationListView,
                    NotificationDetailView, MarkReadView, MarkAllReadView, RunScansView,
                    NotificationDigestListView)

urlpatterns = [
    path("rules/", AlertRuleListCreateView.as_view()),
    path("rules/<int:pk>/", AlertRuleDetailView.as_view()),
    path("notifications/", NotificationListView.as_view()),
    path("notifications/<int:pk>/", NotificationDetailView.as_view()),
    path("notifications/<int:pk>/read/", MarkReadView.as_view()),
    path("notifications/read-all/", MarkAllReadView.as_view()),
    path("scans/run/", RunScansView.as_view()),
    path("digests/", NotificationDigestListView.as_view()),
]