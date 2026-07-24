"""Archive old, terminal leads so the active lists / dashboards stay fast.

A lead is "terminal" once nothing more will happen to it:
  - it was marked lost, or
  - it is not_interested, or
  - it is fully delivered — converted, project complete and fully paid.

Terminal leads older than ``Lead.ARCHIVE_AFTER_MONTHS`` (by last activity) are
flagged ``is_archived`` and drop out of the hot working set. They are never
deleted and can be viewed via the Leads "Archived" filter or restored.

Run periodically (see the AWS scheduler), e.g. nightly:

    python manage.py archive_old_leads
    python manage.py archive_old_leads --months 12 --dry-run
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone


class Command(BaseCommand):
    help = "Archive terminal leads older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument('--months', type=int, default=None,
                            help='Override Lead.ARCHIVE_AFTER_MONTHS.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be archived without changing anything.')

    def handle(self, *args, **opts):
        from leads.models import Lead

        months = opts['months'] if opts['months'] is not None else Lead.ARCHIVE_AFTER_MONTHS
        cutoff = timezone.now() - timedelta(days=months * 30)

        # Terminal set: lost, not interested, or fully delivered.
        terminal = (
            Q(is_lost=True)
            | Q(status='not_interested')
            | Q(status='converted', project__is_complete=True,
                payment_verification__is_complete=True)
        )
        # "Old" = no recent movement. updated_at covers edits; a fully-paid,
        # completed lead won't be touched again, so this is a safe age signal.
        qs = (Lead.objects.filter(terminal, is_archived=False, is_trashed=False)
              .filter(updated_at__lte=cutoff)
              # Never archive a customer whose balance is still due or who is
              # still moving through fulfilment.
              .exclude(status='converted', payment_verification__is_complete=False))

        count = qs.count()
        if opts['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'[dry-run] {count} terminal lead(s) older than {months} months would be archived.'))
            return

        updated = qs.update(is_archived=True, archived_at=timezone.now())
        self.stdout.write(self.style.SUCCESS(
            f'Archived {updated} terminal lead(s) older than {months} months.'))
