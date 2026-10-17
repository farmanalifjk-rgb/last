from django.urls import path
from .views import (TenantListCreateView, TenantDetailView, BranchListCreateView, BranchDetailView,
                    MembershipListCreateView, MembershipDetailView, TenantSettingListCreateView,
                    BranchSettingListCreateView, MyTenantView, GetSettingView)

urlpatterns = [
    path("tenants/", TenantListCreateView.as_view()),
    path("tenants/<int:pk>/", TenantDetailView.as_view()),
    path("branches/", BranchListCreateView.as_view()),
    path("branches/<int:pk>/", BranchDetailView.as_view()),
    path("memberships/", MembershipListCreateView.as_view()),
    path("memberships/<int:pk>/", MembershipDetailView.as_view()),
    path("tenant-settings/", TenantSettingListCreateView.as_view()),
    path("branch-settings/", BranchSettingListCreateView.as_view()),
    path("me/", MyTenantView.as_view()),
    path("setting/", GetSettingView.as_view()),
]