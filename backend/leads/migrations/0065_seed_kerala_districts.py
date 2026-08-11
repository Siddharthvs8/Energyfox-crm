from django.db import migrations

# Kerala's fourteen, north to south as the state lists them. The list is a
# starting point, not a fixture — Settings → Districts is where it is kept from
# here, so this only fills an empty table and never overwrites an edit.
KERALA_DISTRICTS = [
    'Thiruvananthapuram',
    'Kollam',
    'Pathanamthitta',
    'Alappuzha',
    'Kottayam',
    'Idukki',
    'Ernakulam',
    'Thrissur',
    'Palakkad',
    'Malappuram',
    'Kozhikode',
    'Wayanad',
    'Kannur',
    'Kasaragod',
]


def seed(apps, schema_editor):
    District = apps.get_model('leads', 'District')
    if District.objects.exists():
        return          # someone has already curated the list; leave it alone
    District.objects.bulk_create(
        [District(name=name) for name in KERALA_DISTRICTS])


def unseed(apps, schema_editor):
    """Only the untouched seed goes back out.

    A district someone added, renamed or deactivated is their data, so reversing
    the migration must not take it with them.
    """
    District = apps.get_model('leads', 'District')
    District.objects.filter(name__in=KERALA_DISTRICTS, is_active=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0064_district_district_uniq_district_name_ci'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
