"""Emergency service readings go from one photo each to several.

The single ac_*_photo fields become rows in EmergencyServiceDocument, which also
gives DC Voltage, Error Codes and Monthly Production their own photo slots.

The new table is created and the existing photos copied into it *before* the old
columns are dropped, so a shot already taken on site is not thrown away.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


# old column -> new doc_type slot
CARRIED_OVER = {
    'ac_ne_photo': 'ac_ne',
    'ac_pn_photo': 'ac_pn',
    'ac_pe_photo': 'ac_pe',
}


def carry_photos_over(apps, schema_editor):
    EmergencyService = apps.get_model('leads', 'EmergencyService')
    Document = apps.get_model('leads', 'EmergencyServiceDocument')
    for entry in EmergencyService.objects.all():
        for column, slot in CARRIED_OVER.items():
            name = getattr(entry, column, None)
            if name:
                Document.objects.create(entry=entry, doc_type=slot, file=str(name))


def put_them_back(apps, schema_editor):
    """Only the first photo per reading fits back into a single column."""
    EmergencyService = apps.get_model('leads', 'EmergencyService')
    Document = apps.get_model('leads', 'EmergencyServiceDocument')
    for entry in EmergencyService.objects.all():
        for column, slot in CARRIED_OVER.items():
            doc = Document.objects.filter(entry=entry, doc_type=slot).order_by('id').first()
            if doc:
                setattr(entry, column, doc.file.name)
        entry.save()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leads', '0058_emergencyservice_ac_side_condition_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmergencyServiceDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('doc_type', models.CharField(db_index=True, max_length=40)),
                ('file', models.FileField(upload_to='emergency-service/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='leads.emergencyservice')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['uploaded_at', 'id'],
            },
        ),
        migrations.RunPython(carry_photos_over, put_them_back),
        migrations.RemoveField(model_name='emergencyservice', name='ac_ne_photo'),
        migrations.RemoveField(model_name='emergencyservice', name='ac_pe_photo'),
        migrations.RemoveField(model_name='emergencyservice', name='ac_pn_photo'),
    ]
