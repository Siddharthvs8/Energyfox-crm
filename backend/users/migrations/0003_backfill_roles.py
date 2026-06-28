from django.db import migrations


def backfill_roles(apps, schema_editor):
    """Set a role on existing users based on their current boolean flags."""
    User = apps.get_model('users', 'User')
    for u in User.objects.all():
        if u.role:
            continue
        if u.is_superuser:
            u.role = 'superadmin'
        elif u.is_staff:
            u.role = 'admin'
        elif u.is_general_manager:
            u.role = 'coo'
        elif u.is_manager:
            u.role = 'branch_manager'
        else:
            u.role = 'bde'
        u.save(update_fields=['role'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0002_branch_user_role_user_branch'),
    ]
    operations = [
        migrations.RunPython(backfill_roles, noop),
    ]
