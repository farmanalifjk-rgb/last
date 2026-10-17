from django.urls import path
from .views import AuditEventListView, AuditEventDetailView, ActivityFeedListView, AuditStatsView

urlpatterns = [
    path("events/", AuditEventListView.as_view()),
    path("events/<int:pk>/", AuditEventDetailView.as_view()),
    path("feed/", ActivityFeedListView.as_view()),
    path("stats/", AuditStatsView.as_view()),
]