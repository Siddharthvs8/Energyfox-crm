"""Move already-uploaded loan "passbook copy" files into the shared pool.

`loan_passbook_copy` used to be a stage-local slot. It is now the shared
'passbook' kind — the same customer passbook captured on the site visit — so
existing stage-local files must move across, otherwise they would stop
appearing in their slot.
"""
from django.db import migrations

SLOT = 'loan_passbook_copy'


def to_shared(apps, schema_editor):
    Stage1Doc = apps.get_model('leads', 'DocumentationStage1Document')
    LeadDocument = apps.get_model('leads', 'LeadDocument')

    for doc in Stage1Doc.objects.filter(doc_type=SLOT).select_related('stage1'):
        lead_id = doc.stage1.lead_id
        # Don't duplicate a file already present in the pool for this lead.
        if LeadDocument.objects.filter(lead_id=lead_id, kind='passbook',
                                       file=doc.file.name).exists():
            doc.delete()
            continue
        LeadDocument.objects.create(
            lead_id=lead_id, kind='passbook', file=doc.file.name,
            uploaded_by_id=doc.uploaded_by_id,
        )
        doc.delete()   # the file itself is reused, only the row moves


def back_to_local(apps, schema_editor):
    """Best-effort reverse: nothing to undo — shared passbooks predate this and
    can't be told apart from the copies once merged."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0039_lead_doc_stage2_staff'),
    ]

    operations = [
        migrations.RunPython(to_shared, back_to_local),
    ]
