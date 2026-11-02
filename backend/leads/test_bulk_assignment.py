"""Bulk assignment: on the record, and inside the caller's own book.

A page of leads handed to a BDE through the bulk Assign showed that BDE on every
one of them, with nothing anywhere to say who had done it. Bulk assignment
writes with queryset.update(), which sends no signals, so the audit trail never
heard of it — and a change nobody can be seen making reads as the CRM making it
by itself.
"""
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import F
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import AuditEntry
from users.models import User

from .models import Lead, SiteVisit


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456')
    u.role = role
    u.save()
    return u


def token_for(user):
    return f'Bearer {RefreshToken.for_user(user).access_token}'


class BulkAssignmentTestCase(TestCase):
    def post(self, path, body, user):
        r = self.client.post(path, data=body, content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(user))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r

    @staticmethod
    def edits_of(lead):
        return AuditEntry.objects.filter(model_label='leads.Lead', object_id=str(lead.id),
                                         action=AuditEntry.UPDATED)


class BulkAssignmentRecordTests(BulkAssignmentTestCase):
    def setUp(self):
        self.admin = mk('ba_admin', 'admin')
        self.caller = mk('ba_caller', 'tele_caller')
        self.bde = mk('ba_bde', 'bde')
        self.leads = [Lead.objects.create(first_name=f'Meta {n}', phone=f'98950010{n:02d}',
                                          assigned_to=self.caller)
                      for n in range(3)]

    def test_handing_leads_to_a_bde_in_bulk_is_on_the_record(self):
        self.post('/api/leads/bulk_assign/',
                  {'ids': [lead.id for lead in self.leads], 'user_id': self.bde.id}, self.admin)
        for lead in self.leads:
            entry = self.edits_of(lead).get()
            self.assertEqual(entry.actor, self.admin)
            self.assertEqual(entry.changes['assigned_to'],
                             {'from': str(self.caller.id), 'to': str(self.bde.id)})
            self.assertEqual(entry.changes['bde'], {'from': None, 'to': str(self.bde.id)})
            self.assertIn('bde_assigned_at', entry.changes)

    def test_a_bulk_update_of_the_assignee_is_on_the_record(self):
        lead = self.leads[0]
        self.post('/api/leads/bulk_update/',
                  {'ids': [lead.id], 'data': {'assigned_to_id': self.bde.id}}, self.admin)
        entry = self.edits_of(lead).get()
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.changes['bde'], {'from': None, 'to': str(self.bde.id)})

    def test_a_lead_the_assignment_did_not_change_is_not_recorded(self):
        """Already the caller's: nothing moved, so there is nothing to say."""
        lead = self.leads[0]
        self.post('/api/leads/bulk_assign/', {'ids': [lead.id], 'user_id': self.caller.id},
                  self.admin)
        self.assertFalse(self.edits_of(lead).exists())


class BulkAssignmentScopeTests(BulkAssignmentTestCase):
    """The ownership stamps follow the assignment and never reach past it.

    They were applied to every id sent, while the assignment itself only moved
    the leads the caller may route — so a lead outside their book could be
    given a BDE without being assigned to anyone.
    """

    def setUp(self):
        self.caller = mk('bs_caller', 'tele_caller')
        self.other = mk('bs_other', 'tele_caller')
        self.bde = mk('bs_bde', 'bde')
        self.mine = Lead.objects.create(first_name='Mine', phone='9895002001',
                                        assigned_to=self.caller)
        self.theirs = Lead.objects.create(first_name='Theirs', phone='9895002002',
                                          assigned_to=self.other)

    def assert_theirs_untouched(self):
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.assigned_to_id, self.other.id)
        self.assertIsNone(self.theirs.bde_id)
        self.assertIsNone(self.theirs.bde_assigned_at)

    def test_bulk_assign_leaves_a_lead_outside_the_callers_book_alone(self):
        self.post('/api/leads/bulk_assign/',
                  {'ids': [self.mine.id, self.theirs.id], 'user_id': self.bde.id}, self.caller)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.bde_id, self.bde.id)
        self.assert_theirs_untouched()

    def test_bulk_update_leaves_a_lead_outside_the_callers_book_alone(self):
        self.post('/api/leads/bulk_update/',
                  {'ids': [self.mine.id, self.theirs.id],
                   'data': {'assigned_to_id': self.bde.id}}, self.caller)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.bde_id, self.bde.id)
        self.assert_theirs_untouched()


class UndoBulkBdeHandoffTests(BulkAssignmentTestCase):
    """Putting back what one bulk hand-off to a BDE did, and nothing else."""

    def setUp(self):
        self.admin = mk('ub_admin', 'admin')
        self.caller = mk('ub_caller', 'tele_caller')
        self.bde = mk('ub_bde', 'bde')
        self.batch = [Lead.objects.create(first_name=f'Batch {n}', phone=f'98950030{n:02d}',
                                          assigned_to=self.caller)
                      for n in range(3)]
        self.post('/api/leads/bulk_assign/',
                  {'ids': [lead.id for lead in self.batch], 'user_id': self.bde.id}, self.admin)
        # Handed over the usual way, on its own: no part of any bulk hand-off.
        # Dated an hour back outright, because a coarse clock (Windows ticks
        # every 15.6 ms) can stamp it in the same tick as the hand-off above.
        self.single = Lead.objects.create(first_name='Single', phone='9895003099',
                                          assigned_to=self.caller)
        self.single.bde = self.bde
        self.single.save()
        Lead.objects.filter(pk=self.single.pk).update(
            bde_assigned_at=F('bde_assigned_at') - timedelta(hours=1))
        for lead in self.batch + [self.single]:
            lead.refresh_from_db()
        self.moment = self.batch[0].bde_assigned_at.isoformat()

    def run_command(self, *args):
        out = StringIO()
        call_command('undo_bulk_bde_handoff', *args, stdout=out)
        return out.getvalue()

    def test_the_bulk_hand_off_is_listed_and_the_single_one_is_not(self):
        out = self.run_command()
        self.assertIn(self.moment, out)
        self.assertIn('3 leads', out)
        self.assertNotIn(self.single.bde_assigned_at.isoformat(), out)

    def test_without_apply_nothing_changes(self):
        out = self.run_command('--at', self.moment)
        self.assertIn('Nothing was changed', out)
        for lead in self.batch:
            lead.refresh_from_db()
            self.assertEqual(lead.bde_id, self.bde.id)

    def test_apply_gives_the_leads_back_to_the_tele_caller(self):
        self.run_command('--at', self.moment, '--apply')
        for lead in self.batch:
            lead.refresh_from_db()
            self.assertEqual(lead.assigned_to_id, self.caller.id)
            self.assertEqual(lead.tele_caller_id, self.caller.id)
            self.assertIsNone(lead.bde_id)
            self.assertIsNone(lead.bde_assigned_at)
            self.assertEqual(lead.pipeline_stage, 'tele_caller')
        self.single.refresh_from_db()
        self.assertEqual(self.single.bde_id, self.bde.id)

    def test_a_lead_the_bde_has_taken_further_stays_with_them(self):
        signed, plain = self.batch[0], self.batch[1]
        SiteVisit.objects.create(lead=signed, po_signed_date=date(2026, 11, 2))
        out = self.run_command('--at', self.moment, '--apply')
        self.assertIn('kept: already at PO Signed', out)
        signed.refresh_from_db()
        plain.refresh_from_db()
        self.assertEqual(signed.bde_id, self.bde.id)
        self.assertIsNone(plain.bde_id)

    def test_the_undo_is_on_the_record(self):
        self.run_command('--at', self.moment, '--apply')
        entry = self.edits_of(self.batch[0]).order_by('-id').first()
        self.assertEqual(entry.changes['bde'], {'from': str(self.bde.id), 'to': None})
        self.assertEqual(entry.changes['assigned_to'],
                         {'from': str(self.bde.id), 'to': str(self.caller.id)})

    def test_a_moment_that_was_no_bulk_hand_off_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command('--at', self.single.bde_assigned_at.isoformat(), '--apply')
        self.single.refresh_from_db()
        self.assertEqual(self.single.bde_id, self.bde.id)
