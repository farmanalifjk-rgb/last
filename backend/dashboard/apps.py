# backend/backend/dashboard/apps.py

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'
    label = 'dashboard'
    verbose_name = 'Dashboard'

    def ready(self):
        """Import signals if needed"""
        pass