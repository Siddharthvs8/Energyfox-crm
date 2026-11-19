""""Assigned to me" on the lead list: the leads a person is on, in the order
they reached them — not the order the leads were created in.

A BDE given a lead today wants it at the top of their list, however long ago
the customer first enquired. That needs to know when each person got each lead,
which nothing recorded: bde_assigned_at dates the site visit stage, and stays
put when the lead moves from one BDE to another.
"""
from datetime import timedelta
from importlib import import_module

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import AuditEntry
from users.models import User
from .models import ActivityLog, Lead


def mk(username, role, first_name='', last_name=''):
    u = User.objects.create_user(username=username, password='Pw@123456',
                                 first_name=first_name, last_name=last_name)
    u.role = role
    u.save()
    return u


def token_for(user):
    return f'Bearer {RefreshToken.for_user(user).access_token}'


def days_ago(n):
    return timezone.now() - timedelta(days=n)


def fresh(lead):
    """The lead as a request would load it, so save() can see what changed."""
    return Lead.objects.get(pk=lead.pk)


class HolderDatesTests(TestCase):
    """Lead.save() dates each person as they are put on a lead."""

    def setUp(self):
        self.caller = mk('hd_caller', 'tele_caller')
        self.bde = mk('hd_bde', 'bde')
        self.other_bde = mk('hd_bde2', 'bde')

    def test_a_new_lead_dates_whoever_it_was_given_to(self):
        lead = Lead.objects.create(first_name='New', phone='9811100001', assigned_to=self.caller)
        self.assertIsNotNone(lead.owner_since)
        # The owner is a tele caller, so they are its tele caller too, as of the same moment.
        self.assertEqual(lead.tele_caller_since, lead.owner_since)
        self.assertIsNone(lead.bde_since)

    def test_a_lead_moved_to_another_bde_is_new_to_them_but_not_to_the_stage(self):
        lead = Lead.objects.create(first_name='Moved', phone='9811100002',
                                   assigned_to=self.caller, bde=self.bde)
        long_ago = days_ago(20)
        Lead.objects.filter(pk=lead.pk).update(bde_assigned_at=long_ago, bde_since=long_ago)

        lead = fresh(lead)
        lead.bde = self.other_bde
        lead.save()
        lead.refresh_from_db()
        self.assertEqual(lead.bde_assigned_at, long_ago)     # the stage was reached once
        self.assertGreater(lead.bde_since, days_ago(1))      # the new BDE got it today

    def test_a_save_that_moves_nobody_keeps_the_dates(self):
        lead = Lead.objects.create(first_name='Kept', phone='9811100003',
                                   assigned_to=self.caller, bde=self.bde)
        then = days_ago(5)
        Lead.objects.filter(pk=lead.pk).update(owner_since=then, tele_caller_since=then,
                                               bde_since=then)
        lead = fresh(lead)
        lead.status = 'contacted'
        lead.save()
        lead.refresh_from_db()
        self.assertEqual((lead.owner_since, lead.tele_caller_since, lead.bde_since),
                         (then, then, then))

    def test_taking_the_bde_off_clears_their_date(self):
        lead = Lead.objects.create(first_name='Off', phone='9811100004',
                                   assigned_to=self.caller, bde=self.bde)
        lead = fresh(lead)
        lead.bde = None
        lead.save()
        lead.refresh_from_db()
        self.assertIsNone(lead.bde_since)

    def test_handing_it_over_through_update_fields_writes_the_dates(self):
        """The automation engine saves with update_fields=['assigned_to']; an
        owner who is a BDE becomes the BDE too, and both are dated."""
        lead = Lead.objects.create(first_name='Routed', phone='9811100005', assigned_to=self.caller)
        then = days_ago(5)
        Lead.objects.filter(pk=lead.pk).update(owner_since=then, tele_caller_since=then)
        lead = fresh(lead)
        lead.assigned_to = self.bde
        lead.save(update_fields=['assigned_to'])
        lead.refresh_from_db()
        self.assertEqual(lead.bde_id, self.bde.id)
        self.assertGreater(lead.owner_since, days_ago(1))
        self.assertGreater(lead.bde_since, days_ago(1))
        self.assertEqual(lead.tele_caller_since, then)      # the tele caller stays on

    def test_a_save_not_writing_a_holder_leaves_its_date(self):
        lead = Lead.objects.create(first_name='Partial', phone='9811100006', assigned_to=self.caller)
        then = days_ago(5)
        Lead.objects.filter(pk=lead.pk).update(owner_since=then)
        lead = fresh(lead)
        lead.assigned_to = self.bde            # changed in memory, but not what is saved
        lead.status = 'contacted'
        lead.save(update_fields=['status'])
        self.assertEqual(fresh(lead).owner_since, then)


class BulkHandOverDatesTests(TestCase):
    """The bulk paths write with update(), past save(), so they date it themselves."""

    def setUp(self):
        self.admin = mk('bh_admin', 'admin')
        self.caller = mk('bh_caller', 'tele_caller')
        self.other_caller = mk('bh_caller2', 'tele_caller')
        self.bde = mk('bh_bde', 'bde')
        self.then = days_ago(5)
        self.leads = [Lead.objects.create(first_name=f'Bulk {n}', phone=f'98222000{n:02d}',
                                          assigned_to=self.caller) for n in range(3)]
        Lead.objects.update(owner_since=self.then, tele_caller_since=self.then)

    def post(self, path, body):
        r = self.client.post(path, data=body, content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])

    def test_bulk_assign_to_a_bde_dates_the_owner_and_the_bde(self):
        moved, stayed = self.leads[:2], self.leads[2]
        self.post('/api/leads/bulk_assign/', {'ids': [l.id for l in moved], 'user_id': self.bde.id})
        for lead in moved:
            lead.refresh_from_db()
            self.assertGreater(lead.owner_since, days_ago(1))
            self.assertGreater(lead.bde_since, days_ago(1))
            self.assertEqual(lead.tele_caller_since, self.then)
        stayed.refresh_from_db()
        self.assertEqual(stayed.owner_since, self.then)

    def test_a_lead_that_is_already_theirs_keeps_its_date(self):
        self.post('/api/leads/bulk_assign/',
                  {'ids': [l.id for l in self.leads], 'user_id': self.caller.id})
        for lead in self.leads:
            lead.refresh_from_db()
            self.assertEqual(lead.owner_since, self.then)

    def test_bulk_update_dates_the_new_owner(self):
        self.post('/api/leads/bulk_update/', {'ids': [self.leads[0].id],
                                              'data': {'assigned_to_id': self.other_caller.id}})
        lead = fresh(self.leads[0])
        self.assertEqual(lead.assigned_to_id, self.other_caller.id)
        self.assertGreater(lead.owner_since, days_ago(1))
        # The tele caller who worked it stays on, and keeps their date.
        self.assertEqual((lead.tele_caller_id, lead.tele_caller_since), (self.caller.id, self.then))


class AssignedToMeListTests(TestCase):
    def setUp(self):
        self.admin = mk('am_admin', 'superadmin')
        self.caller = mk('am_caller', 'tele_caller')
        self.bde = mk('am_bde', 'bde')
        # Each owned by the tele caller who found it and handed to the BDE —
        # created in one order, reaching the BDE in another.
        self.oldest = self.lead('Oldest', created=30, bde_since=1)
        self.middle = self.lead('Middle', created=20, bde_since=10)
        self.newest = self.lead('Newest', created=2, bde_since=5)
        self.not_theirs = Lead.objects.create(first_name='Elsewhere', phone='9833300099',
                                              assigned_to=self.caller)

    def lead(self, name, created, bde_since):
        lead = Lead.objects.create(first_name=name, phone=f'98333{created:03d}{bde_since:02d}',
                                   assigned_to=self.caller, bde=self.bde)
        Lead.objects.filter(pk=lead.pk).update(created_at=days_ago(created),
                                               bde_since=days_ago(bde_since))
        return lead

    def rows(self, user, query):
        r = self.client.get(f'/api/leads/?{query}', HTTP_AUTHORIZATION=token_for(user))
        self.assertEqual(r.status_code, 200, r.content[:300])
        d = r.json()
        return d['results'] if isinstance(d, dict) else d

    def ids(self, user, query):
        return [row['id'] for row in self.rows(user, query)]

    def test_newest_hand_over_first_not_newest_lead(self):
        self.assertEqual(self.ids(self.bde, 'assigned_to_me=true&ordering=-assigned'),
                         [self.oldest.id, self.newest.id, self.middle.id])
        # What the list shows without it: the order the leads were created in.
        self.assertEqual(self.ids(self.bde, ''), [self.newest.id, self.middle.id, self.oldest.id])

    def test_and_oldest_hand_over_first(self):
        self.assertEqual(self.ids(self.bde, 'assigned_to_me=true&ordering=assigned'),
                         [self.middle.id, self.newest.id, self.oldest.id])

    def test_each_row_says_when_it_reached_them(self):
        first = self.rows(self.bde, 'assigned_to_me=true&ordering=-assigned')[0]
        self.assertEqual(parse_datetime(first['assigned_to_me_at']), fresh(self.oldest).bde_since)

    def test_a_bde_is_on_the_leads_their_tele_caller_still_owns(self):
        """The filter matched the owner alone, which left a BDE with nothing:
        every lead here is still owned by the tele caller."""
        self.assertEqual(set(self.ids(self.bde, 'assigned_to_me=true')),
                         {self.oldest.id, self.middle.id, self.newest.id})

    def test_for_someone_who_sees_every_lead_it_narrows_to_their_own(self):
        own = Lead.objects.create(first_name='Mine', phone='9833300098', assigned_to=self.admin)
        self.assertEqual(self.ids(self.admin, 'assigned_to_me=true&ordering=-assigned'), [own.id])
        self.assertEqual(len(self.ids(self.admin, '')), 5)

    def test_someone_in_two_roles_is_dated_by_the_later(self):
        """A tele caller owns the lead they worked: dated by when it was last put in their hands."""
        Lead.objects.filter(pk=self.not_theirs.pk).update(owner_since=days_ago(2),
                                                         tele_caller_since=days_ago(9))
        row = next(r for r in self.rows(self.caller, 'assigned_to_me=true&ordering=-assigned')
                   if r['id'] == self.not_theirs.id)
        self.assertEqual(parse_datetime(row['assigned_to_me_at']), fresh(self.not_theirs).owner_since)

    def test_an_undated_lead_goes_last_either_way(self):
        Lead.objects.filter(pk=self.middle.pk).update(bde_since=None)
        for ordering in ('-assigned', 'assigned'):
            self.assertEqual(self.ids(self.bde, f'assigned_to_me=true&ordering={ordering}')[-1],
                             self.middle.id, ordering)


class HolderDatesBackfillTests(TestCase):
    """The migration dating the leads that were assigned before the dates existed."""

    def setUp(self):
        self.caller = mk('bf_caller', 'tele_caller', 'Asha', 'K')
        self.other_caller = mk('bf_caller2', 'tele_caller', 'Devi', 'R')
        self.bde = mk('bf_bde', 'bde', 'Anandu', 'S')
        self.other_bde = mk('bf_bde2', 'bde', 'Bibin', '')
        self.created = days_ago(40)

    def lead(self, phone, **holders):
        """A lead as the migration finds it: on its people, with no dates."""
        lead = Lead.objects.create(first_name='Old', phone=phone)
        Lead.objects.filter(pk=lead.pk).update(created_at=self.created, **holders)
        return lead

    def audited(self, lead, when, **to):
        entry = AuditEntry.objects.create(
            action=AuditEntry.UPDATED, category='Leads', model_label='leads.Lead',
            object_id=str(lead.id),
            changes={field: {'from': None, 'to': str(user.id)} for field, user in to.items()})
        AuditEntry.objects.filter(pk=entry.pk).update(created_at=when)

    def logged(self, lead, when, description):
        line = ActivityLog.objects.create(activity_type='note_added', lead=lead,
                                          description=description)
        ActivityLog.objects.filter(pk=line.pk).update(created_at=when)

    def backfill(self):
        migration = import_module('leads.migrations.0085_lead_holder_dates')
        migration.date_the_current_holders(django_apps, None)

    def test_the_audit_trail_dates_the_bde_a_lead_was_moved_to(self):
        moved, first = days_ago(3), days_ago(30)
        lead = self.lead('9844400001', assigned_to=self.caller, tele_caller=self.caller,
                         bde=self.bde, bde_assigned_at=first)
        self.audited(lead, first, bde=self.other_bde)
        self.audited(lead, moved, bde=self.bde)
        self.backfill()
        lead.refresh_from_db()
        self.assertEqual(lead.bde_since, moved)
        # Nothing on record for the tele caller: they had it from the start.
        self.assertEqual((lead.owner_since, lead.tele_caller_since), (self.created, self.created))

    def test_the_assign_bde_line_dates_the_bde_it_names(self):
        named = days_ago(6)
        lead = self.lead('9844400002', assigned_to=self.caller, bde=self.bde,
                         bde_assigned_at=days_ago(20))
        self.logged(lead, named, 'Assigned to BDE: Anandu S')
        self.logged(lead, days_ago(2), 'Assigned to BDE: Bibin')    # someone else's
        self.backfill()
        self.assertEqual(fresh(lead).bde_since, named)

    def test_without_a_record_the_stage_date_then_the_creation_date(self):
        stage = days_ago(12)
        staged = self.lead('9844400003', bde=self.bde, bde_assigned_at=stage)
        bare = self.lead('9844400004', bde=self.bde)
        self.backfill()
        self.assertEqual(fresh(staged).bde_since, stage)
        self.assertEqual(fresh(bare).bde_since, self.created)

    def test_a_lead_handed_away_and_back_is_theirs_from_the_second_time(self):
        back = days_ago(4)
        lead = self.lead('9844400005', assigned_to=self.caller)
        self.audited(lead, days_ago(20), assigned_to=self.caller)
        self.audited(lead, days_ago(10), assigned_to=self.other_caller)
        self.audited(lead, back, assigned_to=self.caller)
        self.backfill()
        self.assertEqual(fresh(lead).owner_since, back)

    def test_a_tele_caller_still_owning_the_lead_shares_the_owners_date(self):
        given = days_ago(8)
        lead = self.lead('9844400006', assigned_to=self.caller, tele_caller=self.caller)
        self.audited(lead, given, assigned_to=self.caller)
        self.backfill()
        lead.refresh_from_db()
        self.assertEqual((lead.owner_since, lead.tele_caller_since), (given, given))

    def test_nobody_on_the_lead_means_no_dates(self):
        lead = self.lead('9844400007')
        self.backfill()
        lead.refresh_from_db()
        self.assertEqual((lead.owner_since, lead.tele_caller_since, lead.bde_since),
                         (None, None, None))
