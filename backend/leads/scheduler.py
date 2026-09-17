"""The in-process ticker that makes the Meta sync schedule actually fire.

Why this exists. The schedule is set in the CRM, but something has to look at
the clock, and Django does nothing on its own between requests. That job used to
belong entirely to a systemd timer on the host — which means a schedule someone
sets in the app silently does nothing until a server is configured to match.
That is a trap: the screen says "syncs at 09:00" and it is telling the truth
about its intent and a lie about what will happen.

So the app now watches its own clock. A daemon thread wakes every
``POLL_SECONDS``, asks whether a scheduled time has come round, and runs the
sync if so.

Two things make that safe under gunicorn, which runs several worker processes:

  * **One winner per tick.** The schedule row is taken with
    ``select_for_update(skip_locked=True)``. Whichever worker gets it does the
    work; the others find the row locked, skip, and go back to sleep. No
    coordination service, no duplicate Graph API calls.
  * **Idempotence underneath.** Even if two workers did overlap, due-ness is
    measured against the scheduled moment and a sync stamps ``last_synced_at``,
    so the second finds nothing to do. Meta leads are also deduplicated by
    ``meta_lead_id``, so the worst case is a wasted call, never a double lead.

The management command still exists and still works — run it from cron if you
would rather own the scheduling on the host. Both paths call the same code, and
both are governed by the same schedule, so they cannot disagree.
"""
import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

# How often to look at the clock. Thirty seconds means a time set in the CRM
# fires within half a minute of itself, which is what "exactly at that time"
# can mean for a poller. A tick with nothing due is one indexed row read.
POLL_SECONDS = 30

# Commands that must never start a ticker: the database may not exist yet, may
# be halfway through a migration, or may be a throwaway test database.
_NO_SCHEDULER_COMMANDS = {
    'test', 'migrate', 'makemigrations', 'collectstatic', 'shell', 'dbshell',
    'createsuperuser', 'loaddata', 'dumpdata', 'flush', 'showmigrations',
    'sqlmigrate', 'check', 'sync_meta_leads',
}

_started = threading.Lock()
_running = False


def should_start() -> bool:
    """Whether this process should run the ticker.

    Off for management commands (see above) and switchable off entirely with
    ``META_SYNC_SCHEDULER=0`` for anyone who would rather drive it from cron.
    """
    if os.environ.get('META_SYNC_SCHEDULER', '1').lower() in ('0', 'false', 'no', 'off'):
        return False
    argv = {arg.lower() for arg in sys.argv[1:]}
    if argv & _NO_SCHEDULER_COMMANDS:
        return False
    # Django's autoreloader runs the app twice; only the reloaded child has this
    # set, and starting in both would double every tick in development.
    if 'runserver' in argv and os.environ.get('RUN_MAIN') != 'true':
        return '--noreload' in argv
    return True


def run_due_syncs_once(now=None) -> int:
    """One tick: sync whatever the schedule says is due. Returns how many ran.

    The lock is the point. Several gunicorn workers wake at the same moment and
    all ask the same question; taking the schedule row with `skip_locked` means
    exactly one of them answers it.
    """
    from django.db import transaction
    from leads.meta_integration import sync_due_integrations
    from leads.models import MetaSyncSchedule

    MetaSyncSchedule.load()  # make sure the row exists before locking it

    with transaction.atomic():
        locked = (MetaSyncSchedule.objects
                  .select_for_update(skip_locked=True)
                  .filter(pk=1)
                  .first())
        if locked is None:
            # Another worker is already on this tick.
            return 0
        if not locked.enabled:
            return 0

        results = sync_due_integrations(now=now)
        ran = sum(1 for _, result in results if result is not None)

        # Stamped every tick, not only when something synced: it is how the
        # screen can say "checked a moment ago" and prove the ticker is alive.
        # Without it, "nothing has synced" and "nothing is watching the clock"
        # look identical from the outside, which is exactly the confusion this
        # module exists to end.
        MetaSyncSchedule.objects.filter(pk=1).update(last_checked_at=_now())
        return ran


def _now():
    from django.utils import timezone
    return timezone.now()


def _loop():
    # A moment's grace so the first tick does not race the app finishing its
    # own start-up.
    time.sleep(5)
    while True:
        try:
            ran = run_due_syncs_once()
            if ran:
                logger.info('Meta sync schedule fired for %s integration(s).', ran)
        except Exception:  # noqa: BLE001 - a ticker that can die is not a ticker
            logger.exception('Meta sync ticker failed; carrying on.')
        time.sleep(POLL_SECONDS)


def start():
    """Start the ticker once per process. Safe to call more than once."""
    global _running
    with _started:
        if _running or not should_start():
            return
        _running = True
    thread = threading.Thread(target=_loop, name='meta-sync-ticker', daemon=True)
    thread.start()
    logger.info('Meta sync ticker started (every %ss).', POLL_SECONDS)
