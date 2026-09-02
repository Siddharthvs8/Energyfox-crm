"""The record of who changed what.

Two things matter most here and are tested hardest: that a change cannot avoid
being recorded, and that the record cannot be read by people it is about.
"""
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from leads.models import Lead
from users.models import User

from .context import actor_of
from .models import AuditEntry


def mk(username, role):
    return User.objects.create_user(username=username, password='x', role=role)


def token_for(user):
    return f'Bearer {RefreshToken.for_user(user).access_token}'


class AuditCaptureTests(TestCase):
    """Signals, not good intentions."""

    def setUp(self):
        self.admin = mk('aud_admin', 'admin')

    def test_creating_a_record_is_logged(self):
        with actor_of(self.admin):
            Lead.objects.create(first_name='Asha', phone='9895000001')
        entry = AuditEntry.objects.filter(action='created').first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.category, 'Leads')
        self.assertEqual(entry.actor, self.admin)
        self.assertIn('Asha', entry.object_label)

    def test_an_edit_records_what_it_used_to_say(self):
        """The whole point: "what was it before" has to be answerable."""
        with actor_of(self.admin):
            lead = Lead.objects.create(first_name='Asha', phone='9895000002')
            lead.phone = '9895000099'
            lead.save()
        entry = AuditEntry.objects.filter(action='updated').first()
        self.assertEqual(entry.changes['phone']['from'], '9895000002')
        self.assertEqual(entry.changes['phone']['to'], '9895000099')

    def test_a_delete_is_logged(self):
        with actor_of(self.admin):
            lead = Lead.objects.create(first_name='Gone', phone='9895000003')
            lead.delete()
        self.assertTrue(AuditEntry.objects.filter(action='deleted').exists())

    def test_a_save_that_changed_nothing_writes_nothing(self):
        """Otherwise the log fills with rows nobody caused."""
        with actor_of(self.admin):
            lead = Lead.objects.create(first_name='Same', phone='9895000004')
        before = AuditEntry.objects.count()
        with actor_of(self.admin):
            Lead.objects.get(pk=lead.pk).save()
        self.assertEqual(AuditEntry.objects.count(), before)

    def test_the_actor_is_recorded_by_name_as_well(self):
        """So the trail still reads after the account is closed — which is
        exactly when somebody goes looking at it."""
        user = mk('aud_leaver', 'bde')
        user.first_name, user.last_name = 'Ravi', 'Menon'
        user.save()
        with actor_of(user):
            Lead.objects.create(first_name='Left', phone='9895000005')
        entry = AuditEntry.objects.filter(object_label__contains='Left').first()
        self.assertEqual(entry.actor_name, 'Ravi Menon')
        user.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.actor_name, 'Ravi Menon')

    def test_a_password_change_is_recorded_without_the_password(self):
        user = mk('aud_pw', 'bde')
        AuditEntry.objects.all().delete()
        with actor_of(self.admin):
            user.set_password('a-new-secret')
            user.save()
        entry = AuditEntry.objects.filter(model_label='users.User').first()
        self.assertIsNotNone(entry)
        self.assertIn('password', entry.changes)
        self.assertNotIn('a-new-secret', str(entry.changes))

    def test_an_unregistered_model_is_not_logged(self):
        """The log is an allow-list; noise buries the line somebody wants."""
        before = AuditEntry.objects.count()
        AuditEntry.objects.create(action='created', category='Leads',
                                  model_label='x.Y', summary='not a real change')
        # The entry itself is the only new row — writing one must not log one.
        self.assertEqual(AuditEntry.objects.count(), before + 1)

    def test_a_change_with_no_request_behind_it_still_records(self):
        """A management command or a webhook is nobody's login, but it is still
        a change and the log should not be silent about it."""
        Lead.objects.create(first_name='Systemic', phone='9895000006')
        entry = AuditEntry.objects.filter(object_label__contains='Systemic').first()
        self.assertIsNotNone(entry)
        self.assertIsNone(entry.actor)


class AuditAccessTests(TestCase):
    """Who may read it."""

    def setUp(self):
        with actor_of(mk('aud_seed', 'admin')):
            Lead.objects.create(first_name='Seeded', phone='9895000007')

    def get(self, role, url='/api/activity-log/'):
        return self.client.get(url, HTTP_AUTHORIZATION=token_for(mk(f'acc_{role}', role)))

    def test_an_admin_and_a_super_admin_can_read_it(self):
        for role in ('admin', 'superadmin'):
            self.assertEqual(self.get(role).status_code, 200, role)

    def test_everybody_else_is_refused(self):
        for role in ('bde', 'tele_caller', 'coo', 'sales_manager',
                     'documentation_staff', 'accounts_manager', 'branch_manager'):
            self.assertEqual(self.get(role).status_code, 403, role)

    def test_a_spectator_is_refused_too(self):
        """It watches the business, not the people. A record of who changed a
        role or a price is accountability, not a watching brief."""
        self.assertEqual(self.get('spectator').status_code, 403)

    def test_signing_out_closes_it(self):
        self.assertEqual(self.client.get('/api/activity-log/').status_code, 401)

    def test_the_log_cannot_be_edited(self):
        """An audit trail that can be rewritten is not one — not even by the
        admin whose changes it exists to record."""
        admin = mk('aud_ro', 'admin')
        entry = AuditEntry.objects.first()
        auth = {'HTTP_AUTHORIZATION': token_for(admin)}
        self.assertIn(self.client.post('/api/activity-log/', data={},
                                       content_type='application/json', **auth).status_code,
                      (403, 405))
        self.assertIn(self.client.delete(f'/api/activity-log/{entry.id}/', **auth).status_code,
                      (403, 405))
        self.assertIn(self.client.patch(f'/api/activity-log/{entry.id}/', data={},
                                        content_type='application/json', **auth).status_code,
                      (403, 405))


class AuditFilterTests(TestCase):
    """Finding one line in a log that only ever grows."""

    def setUp(self):
        self.admin = mk('flt_admin', 'admin')
        self.other = mk('flt_other', 'bde')
        with actor_of(self.admin):
            Lead.objects.create(first_name='Kollam', last_name='Customer', phone='9895000010')
        with actor_of(self.other):
            lead = Lead.objects.create(first_name='Kannur', last_name='Customer', phone='9895000011')
            lead.delete()

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def rows(self, query=''):
        r = self.client.get(f'/api/activity-log/{query}', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()['results']

    def test_it_filters_by_category(self):
        self.assertTrue(self.rows('?category=Leads'))
        self.assertEqual(self.rows('?category=Inventory'), [])

    def test_it_filters_by_action(self):
        self.assertTrue(all(e['action'] == 'deleted' for e in self.rows('?action=deleted')))

    def test_it_filters_by_who_made_the_change(self):
        rows = self.rows(f'?actor={self.other.id}')
        self.assertTrue(rows)
        self.assertTrue(all(e['actor'] == self.other.id for e in rows))

    def test_search_finds_the_record_that_was_touched(self):
        rows = self.rows('?search=Kollam')
        self.assertTrue(rows)
        self.assertTrue(all('Kollam' in e['object_label'] or 'Kollam' in e['summary']
                            for e in rows))

    def test_search_finds_by_who_did_it(self):
        self.assertTrue(self.rows(f'?search={self.other.username}'))

    def test_the_filters_endpoint_offers_what_exists(self):
        r = self.client.get('/api/activity-log/filters/', **self.auth())
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn('Leads', d['categories'])
        self.assertIn('Accounts', d['categories'])
        names = [a['name'] for a in d['actors']]
        self.assertTrue(any(self.other.username in n or 'flt_other' in n for n in names))

    def test_the_newest_change_is_first(self):
        rows = self.rows()
        stamps = [e['created_at'] for e in rows]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
