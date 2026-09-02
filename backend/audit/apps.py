from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'audit'
    verbose_name = 'Activity Log'

    def ready(self):
        # Connecting here rather than at import time is what guarantees the
        # receivers exist before the first request, however the process starts.
        from . import signals  # noqa: F401
