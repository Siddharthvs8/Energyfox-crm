"""
Pulls Meta (Facebook/Instagram) Lead Ads leads for every configured integration.

Run it on a schedule — see `deploy/energyfox-cron.md`:

    python manage.py sync_meta_leads

Each integration is pulled at most once every twelve hours, and the command
decides that per integration rather than trusting the clock it was run on. That
is deliberate: the job can be run hourly, or twice by accident, or for the first
time after the host was down all day, and every page is still pulled on its own
twelve-hour cadence. It also means the Sync Now button and this command share
one schedule instead of fighting over it.

    --hours 6        use a different cadence
    --force          sync everything now, whatever the clock says
    --limit 200      leads per form per call (Meta caps this at 500)
    --dry-run        report what is due without calling Meta
"""
from django.core.management.base import BaseCommand

from leads.models import IntegrationSettings


class Command(BaseCommand):
    help = "Import Meta Lead Ads leads for every integration whose sync is due (default every 12 hours)."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=None,
                            help=f"Hours between syncs (default {IntegrationSettings.SYNC_EVERY_HOURS}).")
        parser.add_argument("--force", action="store_true",
                            help="Sync every integration now, ignoring when it last ran.")
        parser.add_argument("--limit", type=int, default=100,
                            help="Leads per form per call (default 100, Meta's ceiling is 500).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Say which integrations are due without calling Meta.")

    def handle(self, *args, **options):
        from django.utils import timezone
        from leads.meta_integration import sync_due_integrations

        hours = options["hours"] if options["hours"] is not None else IntegrationSettings.SYNC_EVERY_HOURS
        force = options["force"]

        if options["dry_run"]:
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
                    nxt = timezone.localtime(integration.next_sync_due_at).strftime("%d %b %H:%M")
                    self.stdout.write(f"  -- {name}: not due until {nxt}")
                    skipped += 1
            self.stdout.write(self.style.SUCCESS(f"Dry run: {due} due, {skipped} skipped."))
            return

        results = sync_due_integrations(hours=hours, force=force, limit=options["limit"])

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

        summary = (f"Synced {synced} integration(s): {imported} new lead(s), "
                   f"{skipped_leads} already here. {not_due} not due.")
        if failures:
            # Non-zero exit so a systemd timer or cron mailer reports it rather
            # than failing quietly twice a day for a week.
            self.stderr.write(self.style.ERROR(f"{summary} {len(failures)} failed."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(summary))
