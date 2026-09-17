"""
Pulls Meta (Facebook/Instagram) Lead Ads leads for every configured integration.

Run it on a short timer — every minute. See deploy/energyfox-cron.md:

    python manage.py sync_meta_leads

It does nothing until a time on the schedule set in the CRM (Meta Integration →
Automatic sync) comes round, then syncs once for that time. That is what makes
"sync at 09:00 IST" land at nine: this app cannot wake itself up, so it is
polled often and checks the clock. Poll every minute and a sync is within a
minute of the time that was set.

A slot the poll missed entirely — host down, deploy, container restarting — is
still the most recent one that has passed, so it is caught up on the next poll
rather than skipped until tomorrow.

    --force          sync everything now, whatever the schedule says
    --limit 200      leads per form per call (Meta caps this at 500)
    --dry-run        report what is due without calling Meta
"""
from django.core.management.base import BaseCommand

from leads.models import IntegrationSettings, MetaSyncSchedule


class Command(BaseCommand):
    help = "Import Meta Lead Ads leads for every integration a scheduled sync time has come round for."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="Sync every integration now, ignoring the schedule.")
        parser.add_argument("--limit", type=int, default=100,
                            help="Leads per form per call (default 100, Meta's ceiling is 500).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Say which integrations are due without calling Meta.")

    def handle(self, *args, **options):
        from django.utils import timezone
        from leads.meta_integration import sync_due_integrations

        force = options["force"]
        schedule = MetaSyncSchedule.load()

        if options["dry_run"]:
            times = ", ".join(schedule.times) or "no times set"
            state = "" if schedule.enabled else " -- turned off"
            self.stdout.write(f"Schedule: {times} ({schedule.timezone}){state}")
            slot = schedule.last_due_at() if schedule.enabled else None
            if slot:
                self.stdout.write(
                    f"Most recent time due: {timezone.localtime(slot).strftime('%d %b %H:%M')}")

            due = skipped = 0
            for integration in IntegrationSettings.objects.all().order_by("id"):
                name = integration.name or f"#{integration.pk}"
                if not integration.meta_access_token:
                    self.stdout.write(f"  -- {name}: no access token, skipping")
                    skipped += 1
                elif force or integration.sync_due:
                    last = (timezone.localtime(integration.last_synced_at).strftime("%d %b %H:%M")
                            if integration.last_synced_at else "never")
                    self.stdout.write(f"  -> {name}: due (last synced {last})")
                    due += 1
                else:
                    nxt = integration.next_sync_due_at
                    when = timezone.localtime(nxt).strftime("%d %b %H:%M") if nxt else "nothing scheduled"
                    self.stdout.write(f"  -- {name}: not due until {when}")
                    skipped += 1
            self.stdout.write(self.style.SUCCESS(f"Dry run: {due} due, {skipped} skipped."))
            return

        results = sync_due_integrations(force=force, limit=options["limit"])

        synced = imported = skipped_leads = 0
        failures = []
        not_due = 0
        for integration, result in results:
            name = integration.name or f"#{integration.pk}"
            if result is None:
                not_due += 1
                continue
            synced += 1
            imported += result.imported
            skipped_leads += result.skipped
            if result.errors:
                failures.append(f"{name}: {result.errors[0]}")
                self.stderr.write(self.style.WARNING(f"  {name}: {result.errors[0]}"))
            else:
                self.stdout.write(f"  {name}: {result.imported} imported, {result.skipped} already here")

        # Silent when there was nothing to do. This runs every minute, and a
        # line of output on each one would bury the runs that mattered.
        if not synced and not failures:
            return

        summary = (f"Synced {synced} integration(s): {imported} new lead(s), "
                   f"{skipped_leads} already here. {not_due} not due.")
        if failures:
            # Non-zero exit so a systemd timer or cron mailer reports it rather
            # than failing quietly at every scheduled time for a week.
            self.stderr.write(self.style.ERROR(f"{summary} {len(failures)} failed."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(summary))
