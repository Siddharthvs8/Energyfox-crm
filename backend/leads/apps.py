from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'leads'

    def ready(self):
        """Start the Meta sync ticker.

        The schedule is set in the CRM, so the app is what has to watch the
        clock — otherwise a time someone sets here does nothing until a server
        timer is configured to match it. See leads/scheduler.py, which also
        explains how this stays safe across gunicorn's several workers.
        """
        from . import scheduler
        scheduler.start()
