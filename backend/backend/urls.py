"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.permissions import IsAdminUser
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from rest_framework.authentication import SessionAuthentication
from pos.authentication import ExpiringTokenAuthentication


# Only expose API schema and docs in DEBUG mode or to staff users.
class _StaffSpectacularAPIView(SpectacularAPIView):
    authentication_classes = [
        SessionAuthentication,
        ExpiringTokenAuthentication,
    ]
    permission_classes = [IsAdminUser]


class _StaffSwaggerView(SpectacularSwaggerView):
    authentication_classes = [
        SessionAuthentication,
        ExpiringTokenAuthentication,
    ]
    permission_classes = [IsAdminUser]


class _StaffRedocView(SpectacularRedocView):
    authentication_classes = [
        SessionAuthentication,
        ExpiringTokenAuthentication,
    ]
    permission_classes = [IsAdminUser]


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('pos.urls')),
]

# API schema and docs: DEBUG exposes staff-gated variants; production exposes only IsAdminUser-gated paths.
# No unauthenticated schema exposure.
if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", _StaffSpectacularAPIView.as_view(), name="openapi-schema"),
        path("api/docs/", _StaffSwaggerView.as_view(url_name="openapi-schema"), name="api-docs"),
        path("api/redoc/", _StaffRedocView.as_view(url_name="openapi-schema"), name="api-redoc"),
    ]
else:
    urlpatterns += [
        path("api/schema/", _StaffSpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", _StaffSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", _StaffRedocView.as_view(url_name="schema"), name="redoc"),
    ]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
