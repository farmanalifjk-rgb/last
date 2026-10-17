from django.urls import path
from auth_app.views import (
    LoginView, VerifyOTPView, ResendOTPView, LogoutView, MeView,
    MySessionsView, RevokeSessionView, ChangePasswordView, ExpiredPasswordChangeView,
    AdminUnlockAccountView, AdminRevokeUserSessionsView,
    RequestPasswordResetView, ConfirmPasswordResetView,
)

urlpatterns = [
    path("auth/login/", LoginView.as_view()),
    path("auth/verify-otp/", VerifyOTPView.as_view()),
    path("auth/resend-otp/", ResendOTPView.as_view()),
    path("auth/logout/", LogoutView.as_view()),
    path("auth/me/", MeView.as_view()),
    path("auth/sessions/", MySessionsView.as_view()),
    path("auth/sessions/<int:pk>/revoke/", RevokeSessionView.as_view()),
    path("auth/change-password/", ChangePasswordView.as_view()),
    path("auth/expired-password-change/", ExpiredPasswordChangeView.as_view()),
    path("auth/password-reset/request/", RequestPasswordResetView.as_view()),
    path("auth/password-reset/confirm/", ConfirmPasswordResetView.as_view()),
    path("auth/admin/unlock-account/", AdminUnlockAccountView.as_view()),
    path("auth/admin/users/<int:user_id>/revoke-sessions/", AdminRevokeUserSessionsView.as_view()),
]
