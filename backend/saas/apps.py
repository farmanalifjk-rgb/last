from django.apps import AppConfig


class SaasConfig(AppConfig):
    name = "saas"
    label = "saas"
    verbose_name = "saas"

    def ready(self):
        from . import signals  # noqa: F401
