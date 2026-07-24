"""Move already-uploaded purchase orders into the shared document pool.

`mnre_purchase_order` and `loan_agreement_purchase_order` used to be stage-local
slots. They are now the shared 'purchase_order' kind, so a purchase order is
uploaded once and inherited by both. Existing stage-local files must move to the
shared pool, otherwise they would stop appearing in their slots.
"""
from django.db import migrations

PO_SLOTS = ['mnre_purchase_order', 'loan_agreement_purchase_order']


def to_shared(apps, schema_editor):
    Stage1Doc = apps.get_model('leads', 'DocumentationStage1Document')
    LeadDocument = apps.get_model('leads', 'LeadDocument')

    for doc in Stage1Doc.objects.filter(doc_type__in=PO_SLOTS).select_related('stage1'):
        lead_id = doc.stage1.lead_id
        # Don't duplicate a file already present in the pool for this lead.
        if LeadDocument.objects.filter(lead_id=lead_id, kind='purchase_order',
                                       file=doc.file.name).exists():
            doc.delete()
            continue
        LeadDocument.objects.create(
            lead_id=lead_id, kind='purchase_order', file=doc.file.name,
            uploaded_by_id=doc.uploaded_by_id,
        )
        doc.delete()   # the file itself is reused, only the row moves


def back_to_local(apps, schema_editor):
    """Best-effort reverse: put shared purchase orders back on the MNRE slot."""
    Stage1 = apps.get_model('leads', 'DocumentationStage1')
    Stage1Doc = apps.get_model('leads', 'DocumentationStage1Document')
    LeadDocument = apps.get_model('leads', 'LeadDocument')

    for shared in LeadDocument.objects.filter(kind='purchase_order'):
        stage1 = Stage1.objects.filter(lead_id=shared.lead_id).first()
        if stage1:
            Stage1Doc.objects.create(
                stage1=stage1, doc_type='mnre_purchase_order',
                file=shared.file.name, uploaded_by_id=shared.uploaded_by_id,
            )
        shared.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0036_sitevisit_lightning_conductor_length'),
    ]

    operations = [
        migrations.RunPython(to_shared, back_to_local),
    ]
