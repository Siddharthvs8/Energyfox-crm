from django.db import migrations

ALLOWED = {'soil', 'concrete', 'tile', 'interlock'}


def normalise(apps, schema_editor):
    """Fit existing earthing surfaces to the new choice list.

    The field used to be free text. Now that it is a dropdown, a stored value
    outside the list would fail validation the next time that site visit is
    saved — and the BDE would see a save error on a field they never touched.
    Values that match a choice once trimmed and lower-cased are kept; anything
    else is cleared, so the dropdown simply starts empty and can be answered.
    """
    SiteVisit = apps.get_model('leads', 'SiteVisit')
    for pk, value in (SiteVisit.objects
                      .exclude(earthing_surface='')
                      .values_list('pk', 'earthing_surface')):
        cleaned = (value or '').strip().lower()
        fitted = cleaned if cleaned in ALLOWED else ''
        if fitted != value:
            SiteVisit.objects.filter(pk=pk).update(earthing_surface=fitted)


def noop(apps, schema_editor):
    """Irreversible: the original free text isn't recorded anywhere else."""


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0050_alter_sitevisit_earthing_surface'),
    ]

    operations = [
        migrations.RunPython(normalise, noop),
    ]
