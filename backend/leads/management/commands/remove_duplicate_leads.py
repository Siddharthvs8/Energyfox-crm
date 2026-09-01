"""Fold leads that are the same customer twice into the one that came first.

Imports now refuse a customer who is already on the books, so no new duplicates
are created. This is for the ones filed before that rule existed.

The oldest lead is kept and the later copies are folded into it: the older one
carries everything that has happened since — the calls, the notes, the owner it
was assigned to — and the arriving copy carried none of that. Keeping the newer
would throw that work away.

Nothing is destroyed. The later copies are trashed, so anything this gets wrong
can be put back from the Trash. A copy that has moved on by itself — one with a
site visit, a payment, its own project — is never folded away; it is reported
instead, for someone to settle by hand.

    python manage.py remove_duplicate_leads            # report, change nothing
    python manage.py remove_duplicate_leads --apply    # fold them in
"""
from django.core.management.base import BaseCommand

from leads.duplicates import MergeRefused, find_duplicate_groups, merge_leads


class Command(BaseCommand):
    help = "Fold duplicate leads into the earliest one (report unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually fold them in. Without this the command only reports.')

    def handle(self, *args, **options):
        apply = options['apply']
        groups = find_duplicate_groups()
        if not groups:
            self.stdout.write(self.style.SUCCESS(
                'No two leads share a phone or an email. Nothing to do.'))
            return

        folded = skipped = 0
        for group in groups:
            leads = list(group['leads']) if isinstance(group, dict) else list(group)
            # Oldest first. `created_at` is the truth; the primary key breaks a
            # tie for two rows written in the same instant.
            leads.sort(key=lambda l: (l.created_at, l.pk))
            keep, later = leads[0], leads[1:]
            if not later:
                continue

            # Plain ASCII: this runs in a Windows console, whose default code
            # page cannot encode an arrow and takes the whole command down with
            # a UnicodeEncodeError rather than printing a worse-looking line.
            names = ', '.join(f'#{l.pk} {l.first_name or l.phone or "?"}' for l in later)
            self.stdout.write(
                f'keep #{keep.pk} {keep.first_name or keep.phone or "?"} '
                f'({keep.created_at:%d %b %Y})  <-  fold in {names}')

            if not apply:
                continue
            try:
                merge_leads(keep, later)
                folded += len(later)
            except MergeRefused as exc:
                skipped += len(later)
                self.stdout.write(self.style.WARNING(f'    left alone: {exc}'))

        if not apply:
            self.stdout.write(self.style.WARNING(
                f'\n{len(groups)} group(s) above. Nothing was changed — '
                f'run again with --apply to fold them in.'))
            return

        self.stdout.write(self.style.SUCCESS(
            f'\nFolded {folded} later copy/copies into the lead that came first.'))
        if skipped:
            self.stdout.write(self.style.WARNING(
                f'{skipped} left alone — see above; those have work of their own '
                f'and need settling by hand.'))
