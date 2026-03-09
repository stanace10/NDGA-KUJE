from django.apps import AppConfig


class CbtConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.cbt'

    def ready(self):
        # Register content sync signal handlers.
        from apps.cbt import signal_handlers  # noqa: F401
