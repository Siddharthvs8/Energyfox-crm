"""Clear districts that name no district anybody configured.

`Lead.save` settles this for anything written from now on, but it only re-checks
a district that is being written — a lead filed months ago under "Payyanur.kannur"
keeps it until someone edits that lead, which may be never.

Reports by default and changes nothing. Pass --apply to write, so the list can be
read and argued with before any lead is touched:

    python manage.py fix_lead_districts
    python manage.py fix_lead_districts --apply
"""
from django.core.management.base import BaseCommand
from leads.models import District, Lead


class Command(BaseCommand):
    help = "Report (or clear) lead districts that are not in the configured list."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually clear them. Without this the command only reports.')

    def handle(self, *args, **options):
        configured = District.lookup()
        if not configured:
            self.stdout.write(self.style.WARNING(
                'No districts are configured, so every lead would be cleared. '
                'Set the district list up in Settings first — refusing to run.'))
            return

        # Matched the same way the model does: case-insensitively, ignoring
        # surrounding space. Anything that still misses is not one of ours.
        stray = [lead for lead in Lead.objects.only('id', 'district').exclude(district='')
                 if lead.district.strip().lower() not in configured]

        if not stray:
            self.stdout.write(self.style.SUCCESS(
                'Every lead district is one of the configured ones. Nothing to do.'))
            return

        # Grouped, because the same stray spelling usually arrives many times
        # from one form and is easier to judge as a group than row by row.
        counts = {}
        for lead in stray:
            counts[lead.district] = counts.get(lead.district, 0) + 1

        self.stdout.write(f'{len(stray)} lead(s) hold a district that is not configured:\n')
        for value, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            near = self._closest(value, configured)
            hint = f'   (did someone mean "{near}"?)' if near else ''
            self.stdout.write(f'  {n:>5}  {value!r}{hint}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                '\nNothing was changed. Re-run with --apply to clear these.'))
            return

        # update() rather than save(): nothing else about these leads should move,
        # and their timestamps should not shift for a data repair.
        cleared = Lead.objects.filter(pk__in=[lead.pk for lead in stray]).update(district='')
        self.stdout.write(self.style.SUCCESS(
            f'\nCleared the district on {cleared} lead(s). '
            'They now read as having none, which is what they always meant.'))

    @staticmethod
    def _closest(value, configured):
        """A configured district the stray text contains, if any.

        "Payyanur.kannur" holds "kannur", and saying so turns a list of rejects
        into something someone can act on — the answer is usually to correct the
        Meta form, not to add a district.
        """
        text = value.strip().lower()
        for key, name in configured.items():
            if key in text:
                return name
        return None
