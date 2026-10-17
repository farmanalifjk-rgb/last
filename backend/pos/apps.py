from django.apps import AppConfig


class PosConfig(AppConfig):
    name = 'pos'

    def ready(self):
        # Import schema extensions so drf-spectacular discovers them.
        from . import schema  # noqa: F401
