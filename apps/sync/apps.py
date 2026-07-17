from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sync"

    def ready(self):
        from apps.sync import signal_handlers  # noqa: F401
