from django.conf import settings
from django.db import migrations, models


def repair_bde_stamp(apps, schema_editor):
    """Point `bde` at the BDE who actually owns the lead now.

    The stamp used to be sticky: handing a lead from one BDE to another left the
    first one on the record, and the lead list matches on `bde`, so both of them
    kept seeing it. The stamp now follows the owner, but rows written before that
    still carry the old BDE — repair them here.

    Only leads whose current owner *is* a BDE are touched. One sitting with a
    tele caller keeps whatever BDE it last had, which is the shared ownership
    that is meant to survive a hand-back.

    The role is looked up before filtering rather than joined through
    `assigned_to__role`: the user model is swappable, so that join cannot be
    walked in migration state.
    """
    Lead = apps.get_model('leads', 'Lead')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    bde_ids = list(User.objects.filter(role='bde').values_list('id', flat=True))
    if not bde_ids:
        return
    (Lead.objects
        .filter(assigned_to_id__in=bde_ids)
        .exclude(bde_id=models.F('assigned_to_id'))
        .update(bde=models.F('assigned_to')))


def noop(apps, schema_editor):
    """Irreversible by nature — the previous owner was never recorded anywhere."""


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0002_branch_user_role_user_branch'),
        ('leads', '0047_product_hsn'),
    ]

    operations = [
        migrations.RunPython(repair_bde_stamp, noop),
    ]
