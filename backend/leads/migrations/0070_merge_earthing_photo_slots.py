"""Fold the three numbered earthing photo slots into one.

Site Visit Photos offered Earthing 1, 2 and 3 as separate slots, which only ever
forced a choice about which photo went where — every slot already holds as many
files as the BDE wants to attach. The three are now one "Earthing" slot.

The photos already filed under the old slots move across. Without this they
would still be on disk and still bundled with the customer's documents, but
labelled with a raw key nobody recognises and invisible in the form, which for
whoever opens the lead next is indistinguishable from the photos being lost.
"""
from django.db import migrations

OLD_SLOTS = ['photo_earthing_1', 'photo_earthing_2', 'photo_earthing_3']
NEW_SLOT = 'photo_earthing'


def merge(apps, schema_editor):
    SiteVisitDocument = apps.get_model('leads', 'SiteVisitDocument')
    SiteVisitDocument.objects.filter(doc_type__in=OLD_SLOTS).update(doc_type=NEW_SLOT)


def unmerge(apps, schema_editor):
    """Put them back under the first slot.

    Which photo came from which of the three is not recorded anywhere once they
    are merged, so reversing cannot restore the original split. Everything lands
    in Earthing 1, where it stays visible — the alternative is a reverse that
    silently drops photos.
    """
    SiteVisitDocument = apps.get_model('leads', 'SiteVisitDocument')
    SiteVisitDocument.objects.filter(doc_type=NEW_SLOT).update(doc_type=OLD_SLOTS[0])


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0069_split_notes_into_rows'),
    ]

    operations = [
        migrations.RunPython(merge, unmerge),
    ]
