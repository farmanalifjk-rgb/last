from django.urls import path
from ..views.cash_session import OpenSessionView, ActiveSessionView, CloseSessionView

urlpatterns = [
    path("session/open/",OpenSessionView.as_view(),name="session-open",),
    path("session/active/",ActiveSessionView.as_view(),name="session-active",),
    path("session/close/",CloseSessionView.as_view(),name="session-close",),
]