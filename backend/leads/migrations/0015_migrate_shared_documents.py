from django.db import migrations


def move_shared_docs(apps, schema_editor):
    """Move existing shared-kind uploads into the lead-level shared pool.

    Pre-existing customer documents live as separate copies on SiteVisitDocument
    (e.g. 'aadhaar_card') and DocumentationStage1Document (e.g. 'mnre_aadhaar').
    Re-home each one whose doc_type maps to a canonical kind onto LeadDocument so
    it becomes a single shared copy inherited by every same-kind slot. The file
    on disk is reused (we copy the stored path, not the bytes). Stage-local slots
    (photos, generated PDFs, passbook copy) are left untouched.
    """
    from leads.document_kinds import SLOT_TO_KIND

    SiteVisitDocument = apps.get_model('leads', 'SiteVisitDocument')
    DocumentationStage1Document = apps.get_model('leads', 'DocumentationStage1Document')
    LeadDocument = apps.get_model('leads', 'LeadDocument')

    for d in SiteVisitDocument.objects.select_related('site_visit').all():
        kind = SLOT_TO_KIND.get(d.doc_type)
        if not kind:
            continue
        LeadDocument.objects.create(
            lead_id=d.site_visit.lead_id,
            kind=kind,
            file=d.file.name,
            uploaded_by_id=d.uploaded_by_id,
        )
        d.delete()

    for d in DocumentationStage1Document.objects.select_related('stage1').all():
        kind = SLOT_TO_KIND.get(d.doc_type)
        if not kind:
            continue
        LeadDocument.objects.create(
            lead_id=d.stage1.lead_id,
            kind=kind,
            file=d.file.name,
            uploaded_by_id=d.uploaded_by_id,
        )
        d.delete()


def noop_reverse(apps, schema_editor):
    # One-way data move; reversing would require knowing each doc's original slot.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0014_leaddocument'),
    ]

    operations = [
        migrations.RunPython(move_shared_docs, noop_reverse),
    ]
