"""Leave one "Meta sent this customer again" note on each lead.

Every Meta sync reads each form's leads back from the start, so a customer
already in the lead book arrived again at every sync and was noted on their
lead each time — an entry a day, sixty-odd on some leads, burying the history
people actually read. From now on the note is written once
(create_lead_from_meta_payload); this takes the notes already written down to
that one, keeping the first: the day Meta first sent the customer again.

Only these notes are touched; every other entry in a lead's history stays. The
copies removed said nothing the kept note does not, and cannot be put back.
"""
from django.db import migrations


def keep_the_first_note(apps, schema_editor):
    ActivityLog = apps.get_model('leads', 'ActivityLog')

    notes = ActivityLog.objects.filter(activity_type='meta_import',
                                       extra__duplicate_skipped=True, lead__isnull=False)
    noted, copies = set(), []
    for note_id, lead_id in notes.order_by('created_at', 'id').values_list('id', 'lead_id'):
        if lead_id in noted:
            copies.append(note_id)
        else:
            noted.add(lead_id)

    # In batches: a delete signal is listening, so each copy is loaded before it
    # is deleted, and a lead book can hold tens of thousands of them.
    for start in range(0, len(copies), 1000):
        ActivityLog.objects.filter(id__in=copies[start:start + 1000]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0082_lead_referred_by'),
    ]

    operations = [
        migrations.RunPython(keep_the_first_note, migrations.RunPython.noop),
    ]
