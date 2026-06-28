# Convert DocumentationStage1 single-file slots → DocumentationStage1Document (multi-file).
# Order matters: create the new table, copy existing files into it, THEN drop old columns.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

# Legacy single-file slots → copied into DocumentationStage1Document rows.
# doc_type intentionally equals the old field name so labels/sections carry over.
OLD_FIELDS = [
    'nc_ownership', 'nc_building_certificate', 'nc_landtax', 'nc_customer_photo', 'nc_aadhaar', 'nc_kseb_bill',
    'le_aadhaar',
    'mnre_aadhaar', 'mnre_pan', 'mnre_passbook', 'mnre_purchase_order', 'mnre_kseb_bill',
    'loan_aadhaar', 'loan_pan', 'loan_passbook', 'loan_land_tax', 'loan_passbook_copy',
    'loan_itr', 'loan_agreement_purchase_order',
]


def copy_files_to_documents(apps, schema_editor):
    DocumentationStage1 = apps.get_model('leads', 'DocumentationStage1')
    DocumentationStage1Document = apps.get_model('leads', 'DocumentationStage1Document')
    for s1 in DocumentationStage1.objects.all():
        for field in OLD_FIELDS:
            f = getattr(s1, field, None)
            name = getattr(f, 'name', '') if f else ''
            if name:
                DocumentationStage1Document.objects.create(stage1=s1, doc_type=field, file=name)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leads', '0011_remove_sitevisit_aadhaar_card_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentationStage1Document',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('doc_type', models.CharField(db_index=True, max_length=40)),
                ('file', models.FileField(upload_to='documentation/stage1/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('stage1', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='leads.documentationstage1')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['uploaded_at', 'id'],
            },
        ),
        migrations.RunPython(copy_files_to_documents, noop),
        migrations.RemoveField(model_name='documentationstage1', name='le_aadhaar'),
        migrations.RemoveField(model_name='documentationstage1', name='loan_aadhaar'),
        migrations.RemoveField(model_name='documentationstage1', name='loan_agreement_purchase_order'),
        migrations.RemoveField(model_name='documentationstage1', name='loan_itr'),
        migrations.RemoveField(model_name='documentationstage1', name='loan_land_tax'),
        migrations.RemoveField(model_name='documentationstage1', name='loan_pan'),
        migrations.RemoveField(model_name='documentationstage1', name='loan_passbook'),
        migrations.RemoveField(model_name='documentationstage1', name='loan_passbook_copy'),
        migrations.RemoveField(model_name='documentationstage1', name='mnre_aadhaar'),
        migrations.RemoveField(model_name='documentationstage1', name='mnre_kseb_bill'),
        migrations.RemoveField(model_name='documentationstage1', name='mnre_pan'),
        migrations.RemoveField(model_name='documentationstage1', name='mnre_passbook'),
        migrations.RemoveField(model_name='documentationstage1', name='mnre_purchase_order'),
        migrations.RemoveField(model_name='documentationstage1', name='nc_aadhaar'),
        migrations.RemoveField(model_name='documentationstage1', name='nc_building_certificate'),
        migrations.RemoveField(model_name='documentationstage1', name='nc_customer_photo'),
        migrations.RemoveField(model_name='documentationstage1', name='nc_kseb_bill'),
        migrations.RemoveField(model_name='documentationstage1', name='nc_landtax'),
        migrations.RemoveField(model_name='documentationstage1', name='nc_ownership'),
    ]
