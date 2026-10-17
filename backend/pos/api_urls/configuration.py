from django.urls import path
from ..views.configuration import *

urlpatterns = [
    # Settings (GET/PUT)
    path("settings/", SettingsView.as_view()),

    # Users
    path("users/", UsersListView.as_view()),
    path("users/<int:pk>/", UserDetailView.as_view()),

    # Roles
    path("roles/", RolesListView.as_view()),
    path("roles/<int:pk>/", RoleDetailView.as_view()),

    # Taxes
    path("taxes/", TaxesListView.as_view()),
    path("taxes/<int:pk>/", TaxDetailView.as_view()),

    # Payment Methods
    path("payment-methods/", PaymentMethodsListView.as_view()),
    path("payment-methods/<int:pk>/", PaymentMethodDetailView.as_view()),
]
