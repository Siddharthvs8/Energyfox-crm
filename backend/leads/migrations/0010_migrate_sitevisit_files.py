from django.db import migrations

# Legacy single-file slots on SiteVisit → copied into SiteVisitDocument rows.
# doc_type intentionally equals the old field name so labels carry over.
OLD_FIELDS = [
    'kseb_bill_file', 'aadhaar_card', 'pan_card', 'passbook', 'land_tax',
    'ownership_certificate', 'customer_passport_photo', 'building_certificate',
    'loan_document', 'itr_report',
    'photo_meterbox', 'photo_earthing_1', 'photo_earthing_2', 'photo_earthing_3',
    'photo_directional', 'photo_hand_sketch', 'photo_feasibility_report',
]


def copy_files_to_documents(apps, schema_editor):
    SiteVisit = apps.get_model('leads', 'SiteVisit')
    SiteVisitDocument = apps.get_model('leads', 'SiteVisitDocument')
    for sv in SiteVisit.objects.all():
        for field in OLD_FIELDS:
            f = getattr(sv, field, None)
            name = getattr(f, 'name', '') if f else ''
            if name:
                SiteVisitDocument.objects.create(site_visit=sv, doc_type=field, file=name)


def noop(apps, schema_editor):
    # Old fields are dropped in a later migration; reverse is a no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0009_sitevisitdocument'),
    ]

    operations = [
        migrations.RunPython(copy_files_to_documents, noop),
    ]
