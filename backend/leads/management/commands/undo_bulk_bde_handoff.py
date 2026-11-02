"""Undo a bulk hand-off of leads to a BDE.

Bulk assignment (Assign on the Leads list, or Update -> Assignee) moves every
selected lead to the person picked, and when that person is a BDE it makes them
the leads' BDE too: the leads go onto the BDE's list and into the Site Visit
stage. Done by mistake, one click took a page of new leads off a tele caller —
and until bulk assignment was put on the record, nothing said who had done it.

Every lead in one bulk hand-off got its BDE in the same UPDATE, so they share
the exact moment they did (`bde_assigned_at`), while a BDE given leads one at a
time gets a different moment for each. That is how the hand-offs are found. It
leans on the server's clock telling microseconds apart, as Linux's does; a
Windows clock ticks every 15.6 ms and can put two separate hand-offs together.

Reports by default and changes nothing:

    python manage.py undo_bulk_bde_handoff                         # every bulk hand-off, newest first
    python manage.py undo_bulk_bde_handoff --at <moment>           # the leads in one of them
    python manage.py undo_bulk_bde_handoff --at <moment> --apply

--apply takes the BDE off those leads and gives each back to its tele caller. A
lead the BDE has already taken further (PO signed, visit completed, sent on,
converted) stays where it is, and so does one with no tele caller to go back to;
both are listed with the reason.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from audit.bulk import recording
from leads.models import Lead


def _name(user):
    if user is None:
        return '-'
    return f'{user.first_name} {user.last_name}'.strip() or user.username


def _when(moment):
    return timezone.localtime(moment).strftime('%d %b %Y, %I:%M %p')


class Command(BaseCommand):
    help = "Report (or undo) leads handed to a BDE in one bulk assignment."

    def add_arguments(self, parser):
        parser.add_argument('--at', help='The moment of the hand-off, exactly as listed.')
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually undo it. Without this the command only reports.')

    def handle(self, *args, **options):
        if not options['at']:
            if options['apply']:
                raise CommandError('Name the hand-off to undo with --at. '
                                   'Run without arguments to list them.')
            return self._list()

        at = parse_datetime(options['at'])
        if at is None:
            raise CommandError(f'{options["at"]!r} is not a moment. Copy one from the list.')
        leads = list(Lead.objects.filter(bde_assigned_at=at, bde__isnull=False)
                     .select_related('assigned_to', 'tele_caller', 'bde', 'site_visit')
                     .order_by('id'))
        if len(leads) < 2:
            raise CommandError('No bulk hand-off happened at that moment. '
                               'Run without arguments to list them.')
        self._undo(leads, apply=options['apply'])

    def _list(self):
        handoffs = (Lead.objects.filter(bde__isnull=False, bde_assigned_at__isnull=False)
                    .values('bde_assigned_at', 'bde__first_name', 'bde__last_name', 'bde__username')
                    .annotate(leads=Count('id'))
                    .filter(leads__gt=1)
                    .order_by('-bde_assigned_at'))
        if not handoffs:
            self.stdout.write(self.style.SUCCESS('No lead was handed to a BDE in bulk. Nothing to do.'))
            return
        self.stdout.write('Leads handed to a BDE in one bulk assignment, newest first:\n')
        for h in handoffs:
            bde = (f"{h['bde__first_name']} {h['bde__last_name']}".strip()
                   or h['bde__username'])
            self.stdout.write(f"  {h['bde_assigned_at'].isoformat()}   {h['leads']:>4} leads   "
                              f"to {bde}, {_when(h['bde_assigned_at'])}")
        self.stdout.write('\nRe-run with --at <moment> to see the leads in one.')

    def _undo(self, leads, apply):
        bde = leads[0].bde
        self.stdout.write(f'{len(leads)} leads were handed to {_name(bde)} on '
                          f'{_when(leads[0].bde_assigned_at)}:\n')
        undo, kept = [], 0
        for lead in leads:
            reason = self._kept_because(lead)
            if reason:
                kept += 1
                outcome = f'kept: {reason}'
            else:
                undo.append(lead)
                back_to = lead.tele_caller if lead.assigned_to_id == lead.bde_id else lead.assigned_to
                outcome = f'back to {_name(back_to)}'
            self.stdout.write(f'  #{lead.id:<7} {str(lead)[:32]:<32}  {outcome}')

        if not apply:
            self.stdout.write(self.style.WARNING(
                f'\nNothing was changed. Re-run with --apply to undo it for {len(undo)} '
                f'lead(s){f" ({kept} kept)" if kept else ""}.'))
            return

        ids = [lead.id for lead in undo]
        # Still owned by the BDE they were handed to: back to the tele caller
        # who had them. One already moved on to someone else keeps its owner.
        owned_by_bde = [lead.id for lead in undo if lead.assigned_to_id == lead.bde_id]
        # update() rather than save(), as the hand-off was: save() would stamp
        # an owner who is a BDE straight back on as the BDE. `recording` puts
        # the undo on the record the way the hand-off now is.
        with recording(Lead, ids):
            Lead.objects.filter(id__in=owned_by_bde).update(assigned_to=F('tele_caller'))
            Lead.objects.filter(id__in=ids).update(bde=None, bde_assigned_at=None)
        self.stdout.write(self.style.SUCCESS(
            f'\nUndid the hand-off for {len(ids)} lead(s): they are back with their tele '
            f'callers, at the Tele Caller stage.{f" {kept} kept." if kept else ""}'))

    @staticmethod
    def _kept_because(lead):
        """Why this lead stays with its BDE, or None when it can go back."""
        stage = lead.pipeline_stage
        if stage != 'site_visit':
            return f'already at {Lead.PIPELINE_STAGE_LABELS.get(stage, stage)}'
        if lead.status == 'converted':
            return 'converted'
        site_visit = getattr(lead, 'site_visit', None)
        if site_visit is not None and site_visit.site_visit_complete:
            return 'site visit completed'
        if lead.assigned_to_id == lead.bde_id and not lead.tele_caller_id:
            return 'no tele caller to give it back to'
        return None
