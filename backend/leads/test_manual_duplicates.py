"""A lead added by hand is refused when its phone number is already on a lead.

The Meta and CSV imports refused such a customer all along; the New Lead form
did not, which is how the same customer was in the list twice under two
spellings of their name.
"""
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User

from .models import Lead


def mk(username, role, first_name='', last_name=''):
    u = User.objects.create_user(username=username, password='Pw@123456',
                                 first_name=first_name, last_name=last_name)
    u.role = role
    u.save()
    return u


def token_for(user):
    return f'Bearer {RefreshToken.for_user(user).access_token}'


class ManualDuplicatePhoneTests(TestCase):
    def setUp(self):
        self.caller = mk('md_caller', 'tele_caller', 'Shruthi', 'G')
        self.owner = mk('md_owner', 'tele_caller', 'Sabitha', 'BS')
        # Another tele caller's customer: not on this caller's list, and still
        # the same customer.
        self.existing = Lead.objects.create(first_name='Salim', last_name='K I',
                                            phone='919495701534', assigned_to=self.owner)

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.caller)}

    def add(self, **fields):
        payload = {'first_name': 'Salim', 'last_name': 'K I K I', 'phone': '+91 94957 01534'}
        payload.update(fields)
        return self.client.post('/api/leads/', data=payload, content_type='application/json',
                                **self.auth())

    def edit(self, lead, **fields):
        return self.client.patch(f'/api/leads/{lead.id}/', data=fields,
                                 content_type='application/json', **self.auth())

    def check(self, user=None, **params):
        return self.client.get('/api/leads/phone-check/', params, **self.auth(user))

    def test_a_number_already_on_a_lead_is_refused_however_it_is_written(self):
        for written in ('+91 94957 01534', '9495701534', '094957-01534', '919495701534'):
            r = self.add(phone=written)
            self.assertEqual(r.status_code, 400, (written, r.content[:300]))
        self.assertEqual(Lead.objects.count(), 1)

    def test_the_refusal_names_the_lead_and_whose_desk_it_is_on(self):
        self.assertEqual(self.add().json()['phone'],
                         ['This phone number is already associated with another lead: '
                          'Salim K I (assigned to Sabitha BS).'])

    def test_an_archived_lead_still_holds_its_number_and_says_so(self):
        Lead.objects.filter(pk=self.existing.pk).update(is_archived=True)
        r = self.add()
        self.assertEqual(r.status_code, 400)
        self.assertIn('(assigned to Sabitha BS, archived)', r.json()['phone'][0])

    def test_a_lead_in_the_trash_does_not_hold_its_number(self):
        Lead.objects.filter(pk=self.existing.pk).update(is_trashed=True)
        self.assertEqual(self.add().status_code, 201)

    def test_a_new_number_is_added_as_before(self):
        self.assertEqual(self.add(phone='9895700099').status_code, 201)

    def test_editing_a_lead_onto_another_leads_number_is_refused(self):
        mine = Lead.objects.create(first_name='Mine', phone='9895700001', assigned_to=self.caller)
        r = self.edit(mine, phone='9495701534')
        self.assertEqual(r.status_code, 400, r.content[:300])
        mine.refresh_from_db()
        self.assertEqual(mine.phone, '9895700001')

    def test_a_lead_that_is_already_a_duplicate_can_still_be_edited(self):
        """The edit form posts the number back unchanged; that makes no copy."""
        twin = Lead.objects.create(first_name='Salim', last_name='K I K I',
                                   phone='919495701534', assigned_to=self.caller)
        r = self.edit(twin, first_name='Salim', last_name='K', phone='+91 9495701534')
        self.assertEqual(r.status_code, 200, r.content[:300])

    def test_the_form_can_ask_while_the_number_is_typed(self):
        r = self.check(phone='+91 94957 01534')
        self.assertEqual(r.status_code, 200)
        duplicate = r.json()['duplicate']
        self.assertEqual(duplicate['id'], self.existing.id)
        self.assertEqual(duplicate['owner'], 'Sabitha BS')
        self.assertIn('already associated with another lead', duplicate['message'])

    def test_a_free_number_or_the_lead_being_edited_finds_nothing(self):
        self.assertIsNone(self.check(phone='9895700099').json()['duplicate'])
        self.assertIsNone(self.check(phone='919495701534',
                                     exclude=self.existing.id).json()['duplicate'])

    def test_someone_who_cannot_add_or_edit_leads_cannot_ask(self):
        self.assertEqual(self.check(user=mk('md_bde', 'bde'), phone='9495701534').status_code, 403)
