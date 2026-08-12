import re

from django.db import migrations


def split_notes(apps, schema_editor):
    """Turn each lead's notes blob into one row per note.

    The field held notes appended with a blank line between them, which is
    exactly how they were written and exactly how they split. There is nobody to
    attribute them to — the old field recorded no author, which is the whole
    reason for this model — so they come across unowned, and only the admin tier
    can edit them.
    """
    Lead = apps.get_model('leads', 'Lead')
    LeadNote = apps.get_model('leads', 'LeadNote')
    if LeadNote.objects.exists():
        return                      # already carried across

    rows = []
    for lead in Lead.objects.exclude(notes='').exclude(notes=None).only('id', 'notes').iterator():
        for block in re.split(r'\r?\n\s*\r?\n', lead.notes or ''):
            body = block.strip()
            if body:
                rows.append(LeadNote(lead_id=lead.id, body=body, author=None))
    if rows:
        LeadNote.objects.bulk_create(rows, batch_size=500)


def rejoin_notes(apps, schema_editor):
    """The blob was never emptied, so there is nothing to put back — the rows go
    with the previous migration."""


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0068_leadnote'),
    ]

    operations = [
        migrations.RunPython(split_notes, rejoin_notes),
    ]
