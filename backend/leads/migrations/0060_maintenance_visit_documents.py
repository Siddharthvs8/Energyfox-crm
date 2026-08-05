"""Maintenance visit photos go from two single slots to many slots, many files.

panel_before / panel_after become rows in MaintenanceVisitDocument, which also
gives the readings their own photo slots and adds the production-before and
production-after pictures.

The new table is created and the existing photos copied into it *before* the old
columns are dropped, so a wash already photographed on site is not lost.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


# old column -> new doc_type slot
CARRIED_OVER = {'panel_before': 'panel_before', 'panel_after': 'panel_after'}


def carry_photos_over(apps, schema_editor):
    MaintenanceVisit = apps.get_model('leads', 'MaintenanceVisit')
    Document = apps.get_model('leads', 'MaintenanceVisitDocument')
    for visit in MaintenanceVisit.objects.all():
        for column, slot in CARRIED_OVER.items():
            name = getattr(visit, column, None)
            if name:
                Document.objects.create(visit=visit, doc_type=slot, file=str(name))


def put_them_back(apps, schema_editor):
    """Only the first photo per slot fits back into a single column."""
    MaintenanceVisit = apps.get_model('leads', 'MaintenanceVisit')
    Document = apps.get_model('leads', 'MaintenanceVisitDocument')
    for visit in MaintenanceVisit.objects.all():
        for column, slot in CARRIED_OVER.items():
            doc = Document.objects.filter(visit=visit, doc_type=slot).order_by('id').first()
            if doc:
                setattr(visit, column, doc.file.name)
        visit.save()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leads', '0059_emergency_service_documents'),
    ]

    operations = [
        migrations.AddField(
            model_name='maintenancevisit',
            name='dc_floating_voltage',
            field=models.CharField(blank=True, default='', max_length=60),
        ),
        migrations.CreateModel(
            name='MaintenanceVisitDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('doc_type', models.CharField(db_index=True, max_length=40)),
                ('file', models.FileField(upload_to='maintenance/photos/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('visit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='leads.maintenancevisit')),
            ],
            options={
                'ordering': ['uploaded_at', 'id'],
            },
        ),
        migrations.RunPython(carry_photos_over, put_them_back),
        migrations.RemoveField(model_name='maintenancevisit', name='panel_before'),
        migrations.RemoveField(model_name='maintenancevisit', name='panel_after'),
    ]
