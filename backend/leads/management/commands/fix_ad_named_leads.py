"""Repair leads that were filed under their own campaign's or ad's name.

Meta returns the campaign, ad and form names on the same payload as the lead.
A `name` on that payload was being read as the person's, so whole batches came in
called the same thing — "Kerala ad 07/07/2026 campaign ad" for every row.

The importer no longer does that, but the rows already stored keep the wrong
name. This finds them by comparing each lead's name with the campaign it came in
on, and replaces the label with "Meta Lead" so the phone number is what the
caller works from.

    python manage.py fix_ad_named_leads --dry-run     # list them, change nothing
    python manage.py fix_ad_named_leads               # repair them

Only leads whose name matches their own campaign exactly (ignoring case and
spacing) are touched, so a customer who happens to share a word with the ad is
left alone.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from leads.meta_integration import is_ad_metadata_name
from leads.models import Lead

PLACEHOLDER = 'Meta Lead'


class Command(BaseCommand):
    help = "Clear lead names that are really their campaign's or ad's name."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing anything.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # A lead can carry the campaign two ways: `meta_campaign_name` when the
        # Meta importer created it, or the campaigns it was filed under when it
        # came from a CSV. Both are compared, because the name could have come in
        # by either route.
        candidates = (Lead.objects
                      .exclude(Q(meta_campaign_name='') | Q(meta_campaign_name=None),
                               campaigns_set__isnull=True)
                      .prefetch_related('campaigns_set')
                      .distinct())

        hits = []
        for lead in candidates:
            person = f'{lead.first_name} {lead.last_name}'.strip()
            labels = [lead.meta_campaign_name or '']
            labels += [c.name for c in lead.campaigns_set.all()]
            if is_ad_metadata_name(person, *labels):
                hits.append(lead)

        if not hits:
            self.stdout.write(self.style.SUCCESS('No leads are named after their campaign.'))
            return

        self.stdout.write(f'{len(hits)} lead(s) named after their own campaign:')
        for lead in hits[:20]:
            person = f'{lead.first_name} {lead.last_name}'.strip()
            self.stdout.write(f'  #{lead.id}  {person!r}  ({lead.phone or "no phone"})')
        if len(hits) > 20:
            self.stdout.write(f'  … and {len(hits) - 20} more')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                'Dry run — nothing written. Re-run without --dry-run to repair.'))
            return

        for lead in hits:
            lead.first_name = PLACEHOLDER
            lead.last_name = ''
        Lead.objects.bulk_update(hits, ['first_name', 'last_name'], batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f'Renamed {len(hits)} lead(s) to "{PLACEHOLDER}". Their phone numbers and '
            'campaigns are unchanged.'))
