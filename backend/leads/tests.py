"""Lead-status ownership and the site-visit indicator the Leads list renders."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile

from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from .models import (DocumentationStage2, Lead, LiasoningService, PaymentVerification,
                     SiteVisit, Warranty, WarrantyDocument)


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456')
    u.role = role
    u.save()
    return u


class BdeCannotEditLeadStatusTests(TestCase):
    """A BDE reports through the site visit; the status belongs to the tele
    caller / managers."""

    def setUp(self):
        self.bde = mk('t_bde', 'bde')
        self.caller = mk('t_caller', 'tele_caller')
        self.admin = mk('t_admin', 'admin')
        # bde= makes the lead visible to the BDE (their queryset is scoped to
        # leads assigned to them or handed to them as BDE).
        self.lead = Lead.objects.create(first_name='A', last_name='One', phone='9990000001',
                                        status='new', assigned_to=self.caller, bde=self.bde, value=0)
        self.lead2 = Lead.objects.create(first_name='A', last_name='Two', phone='9990000002',
                                         status='new', assigned_to=self.caller, bde=self.bde, value=0)

    def patch_lead(self, actor, payload, lead=None):
        return self.client.patch(f'/api/leads/{(lead or self.lead).id}/', data=payload,
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor))

    def post(self, url, actor, payload):
        return self.client.post(url, data=payload, content_type='application/json',
                                HTTP_AUTHORIZATION=token_for(actor))

    def test_bde_cannot_change_status(self):
        r = self.patch_lead(self.bde, {'status': 'converted'})
        self.assertEqual(r.status_code, 403)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'new')

    def test_bde_cannot_change_status_through_the_edit_form(self):
        r = self.patch_lead(self.bde, {'status': 'positive', 'first_name': 'A'})
        self.assertEqual(r.status_code, 403)

    def test_bde_cannot_change_status_in_bulk(self):
        r = self.post('/api/leads/bulk_update/', self.bde,
                      {'ids': [self.lead.id, self.lead2.id], 'data': {'status': 'interested'}})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Lead.objects.filter(status='interested').count(), 0)

    def test_bde_cannot_edit_the_lead_at_all(self):
        """Editing the lead record is closed to a BDE — see
        BdeCannotEditOrDeleteLeadsTests. Nothing on the form saves for them."""
        r = self.patch_lead(self.bde, {'status': 'new', 'notes': 'Visit booked'})
        self.assertEqual(r.status_code, 403)
        self.lead.refresh_from_db()
        self.assertNotEqual(self.lead.notes, 'Visit booked')

    def test_tele_caller_and_admin_still_own_the_status(self):
        self.assertEqual(self.patch_lead(self.caller, {'status': 'interested'}).status_code, 200)
        self.assertEqual(self.patch_lead(self.admin, {'status': 'follow_up'}).status_code, 200)
        r = self.post('/api/leads/bulk_update/', self.admin,
                      {'ids': [self.lead2.id], 'data': {'status': 'positive'}})
        self.assertEqual(r.status_code, 200)
        self.lead2.refresh_from_db()
        self.assertEqual(self.lead2.status, 'positive')

    def test_can_edit_status_flag_matches_enforcement(self):
        """The UI disables the dropdown off this flag, so it must not over-promise."""
        for user, expected in ((self.bde, False), (self.caller, True), (self.admin, True)):
            r = self.client.get(f'/api/leads/{self.lead.id}/', HTTP_AUTHORIZATION=token_for(user))
            self.assertEqual(r.json()['can_edit_status'], expected, user.role)


class BdeCannotAddOrAssignLeadsTests(TestCase):
    """Leads are sourced and routed by the tele-calling side; a BDE receives
    them as a hand-off for the site visit."""

    def setUp(self):
        self.bde = mk('t_bde', 'bde')
        self.bde2 = mk('t_bde2', 'bde')
        self.caller = mk('t_caller', 'tele_caller')
        self.admin = mk('t_admin', 'admin')
        self.lead = Lead.objects.create(first_name='C', last_name='One', phone='9992000001',
                                        status='new', assigned_to=self.caller, bde=self.bde, value=0)

    def post(self, url, actor, payload):
        return self.client.post(url, data=payload, content_type='application/json',
                                HTTP_AUTHORIZATION=token_for(actor))

    def patch_lead(self, actor, payload):
        return self.client.patch(f'/api/leads/{self.lead.id}/', data=payload,
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor))

    # ── adding ──
    def test_bde_cannot_create_a_lead(self):
        r = self.post('/api/leads/', self.bde, {'first_name': 'C', 'last_name': 'New',
                                                'phone': '9992000002'})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Lead.objects.filter(last_name='New').exists())

    def test_bde_cannot_import_leads_from_csv(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv = SimpleUploadedFile('leads.csv', b'first_name,phone,status\nCsv,9992000003,converted\n',
                                 content_type='text/csv')
        r = self.client.post('/api/leads/bulk_upload/', {'file': csv},
                             HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Lead.objects.filter(first_name='Csv').exists())

    def test_tele_caller_and_admin_can_still_add(self):
        for actor, last in ((self.caller, 'ByCaller'), (self.admin, 'ByAdmin')):
            r = self.post('/api/leads/', actor, {'first_name': 'C', 'last_name': last,
                                                 'phone': f'999200{actor.id:04d}'})
            self.assertEqual(r.status_code, 201, actor.role)

    # ── assigning ──
    def test_bde_cannot_reassign_a_lead(self):
        r = self.patch_lead(self.bde, {'assigned_to': self.bde2.id})
        self.assertEqual(r.status_code, 403)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.caller.id)

    def test_bde_cannot_assign_in_bulk(self):
        r = self.post('/api/leads/bulk_assign/', self.bde,
                      {'ids': [self.lead.id], 'user_id': self.bde2.id})
        self.assertEqual(r.status_code, 403)
        r = self.post('/api/leads/bulk_update/', self.bde,
                      {'ids': [self.lead.id], 'data': {'assigned_to_id': self.bde2.id}})
        self.assertEqual(r.status_code, 403)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.caller.id)

    def test_bde_is_offered_nobody_to_assign_to(self):
        r = self.client.get('/api/users/assignable/', HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_bde_cannot_route_a_lead_to_a_bde(self):
        """Even on a lead they own — handing work to a BDE is not a BDE's call."""
        owned = Lead.objects.create(first_name='C', last_name='Owned', phone='9992000009',
                                    status='new', assigned_to=self.bde, bde=self.bde, value=0)
        r = self.client.get(f'/api/leads/{owned.id}/', HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertFalse(r.json()['can_assign_bde'])
        r = self.post(f'/api/leads/{owned.id}/assign-bde/', self.bde, {'bde_id': self.bde2.id})
        self.assertEqual(r.status_code, 403)

    def test_bde_editing_a_lead_is_refused_outright(self):
        """A BDE has no edit form at all now, so even an unchanged owner is a no."""
        r = self.patch_lead(self.bde, {'assigned_to': self.caller.id, 'notes': 'Reached site'})
        self.assertEqual(r.status_code, 403)
        self.lead.refresh_from_db()
        self.assertNotEqual(self.lead.notes, 'Reached site')

    def test_tele_caller_can_still_assign(self):
        r = self.post('/api/leads/bulk_assign/', self.caller,
                      {'ids': [self.lead.id], 'user_id': self.bde2.id})
        self.assertEqual(r.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.bde2.id)


class SiteVisitIndicatorTests(TestCase):
    """The Leads list's Site Visit button flips to 'completed' off this flag."""

    def setUp(self):
        self.admin = mk('t_admin', 'admin')
        self.done = Lead.objects.create(first_name='B', last_name='Done', phone='9991110001', value=0)
        SiteVisit.objects.create(lead=self.done, site_visit_complete=True)
        self.open = Lead.objects.create(first_name='B', last_name='Open', phone='9991110002', value=0)
        SiteVisit.objects.create(lead=self.open, site_visit_complete=False)
        # No SiteVisit row at all — must report False rather than error.
        self.bare = Lead.objects.create(first_name='B', last_name='Bare', phone='9991110003', value=0)

    def test_list_reports_site_visit_completion(self):
        r = self.client.get('/api/leads/?all=true', HTTP_AUTHORIZATION=token_for(self.admin))
        rows = r.json()
        rows = rows if isinstance(rows, list) else rows['results']
        flags = {x['last_name']: x['site_visit_complete'] for x in rows}
        self.assertTrue(flags['Done'])
        self.assertFalse(flags['Open'])
        self.assertFalse(flags['Bare'])

    def test_site_visit_is_not_queried_once_per_lead(self):
        """The flag is read for every row, so it must ride along in the main
        SELECT (a JOIN) rather than firing its own query per lead."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        for i in range(12):
            lead = Lead.objects.create(first_name='B', last_name=f'Bulk{i}',
                                       phone=f'99911200{i:02d}', value=0)
            SiteVisit.objects.create(lead=lead, site_visit_complete=bool(i % 2))

        with CaptureQueriesContext(connection) as ctx:
            self.client.get('/api/leads/?all=true', HTTP_AUTHORIZATION=token_for(self.admin))

        # A lazy per-row load reads FROM "leads_sitevisit"; the select_related
        # version only ever JOINs it.
        standalone = [q['sql'] for q in ctx.captured_queries
                      if 'FROM "leads_sitevisit"' in q['sql']]
        self.assertEqual(standalone, [], f"{len(standalone)} per-lead site_visit queries")


class LeaderboardTests(TestCase):
    """The board ranks BDEs on the deals they closed."""

    def setUp(self):
        self.caller = mk('t_caller', 'tele_caller')
        self.admin = mk('t_admin', 'admin')
        self.bde1 = mk('t_bde1', 'bde')
        self.bde2 = mk('t_bde2', 'bde')
        # Owned by the tele caller, closed by bde1 — the money follows the BDE.
        Lead.objects.create(first_name='A', last_name='Won', phone='9993000001',
                            status='converted', assigned_to=self.caller, bde=self.bde1, value=86676)
        Lead.objects.create(first_name='B', last_name='Open', phone='9993000002',
                            status='interested', assigned_to=self.caller, bde=self.bde2, value=50000)

    def board(self, actor=None, period='all_time'):
        r = self.client.get(f'/api/leaderboard/?period={period}',
                            HTTP_AUTHORIZATION=token_for(actor or self.admin))
        self.assertEqual(r.status_code, 200)
        return r.json()['leaderboard']

    def test_only_bdes_are_listed(self):
        names = [row['name'] for row in self.board()]
        self.assertEqual(sorted(names), ['t_bde1', 't_bde2'])
        self.assertTrue(all(row['role'] == 'BDE' for row in self.board()))

    def test_credit_follows_the_bde_not_the_owner(self):
        top = self.board()[0]
        self.assertEqual(top['name'], 't_bde1')
        self.assertEqual(top['closed_sales'], 1)
        self.assertEqual(top['revenue'], 86676.0)

    def test_unconverted_leads_are_not_counted(self):
        row = next(r for r in self.board() if r['name'] == 't_bde2')
        self.assertEqual(row['closed_sales'], 0)
        self.assertEqual(row['revenue'], 0.0)

    def test_bde_with_no_deals_still_appears_at_the_bottom(self):
        """Zero revenue must not sort to the top (NULLs did, before Coalesce)."""
        board = self.board()
        self.assertEqual(board[-1]['name'], 't_bde2')


class PoSignedDateTests(TestCase):
    """Signing the PO on the site visit is what puts a lead on the KSEB
    feasibility queue and starts its 2-day clock."""

    def setUp(self):
        self.bde = mk('t_bde', 'bde')
        self.caller = mk('t_caller', 'tele_caller')
        self.lead = Lead.objects.create(first_name='P', last_name='Owner', phone='9994000001',
                                        status='converted', assigned_to=self.caller,
                                        bde=self.bde, value=100000)

    def patch_site_visit(self, payload, actor=None):
        return self.client.patch(f'/api/leads/{self.lead.id}/site-visit/', data=payload,
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor or self.bde))

    def queue(self, actor=None):
        r = self.client.get('/api/leads/bde-feasibility/',
                            HTTP_AUTHORIZATION=token_for(actor or self.bde))
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_lead_is_absent_from_the_queue_before_the_po_is_signed(self):
        self.assertEqual(self.queue(), [])

    def test_signing_the_po_adds_the_lead_to_the_queue(self):
        r = self.patch_site_visit({'po_signed_date': '2026-07-27'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['po_signed_date'], '2026-07-27')
        ids = [row['id'] for row in self.queue()]
        self.assertIn(self.lead.id, ids)

    def test_the_save_reports_when_the_po_was_just_signed(self):
        """Drives the hand-off popup, so it must fire once and not again."""
        first = self.patch_site_visit({'po_signed_date': '2026-07-27'})
        self.assertTrue(first.json()['po_just_signed'])
        again = self.patch_site_visit({'po_signed_date': '2026-07-27'})
        self.assertFalse(again.json()['po_just_signed'])

    def test_full_form_save_with_a_blank_po_date(self):
        """The browser posts every scalar it holds, so an untouched date arrives
        as "". A DateField rejects that, which failed the whole save."""
        payload = {
            'roof_type': 'rcc', 'connection_type': '', 'connected_load': '',
            'kseb_section': 'Kollam', 'plant_capacity': '5 kW',
            'name_change': '', 'loan': '', 'loan_amount': '',
            'po_signed_date': '', 'kseb_feasibility_date': '',
            'rcc_roof_types': ['flat'], 'site_visit_complete': False, 'deal_value': '250000',
        }
        r = self.patch_site_visit(payload)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertIsNone(r.json()['po_signed_date'])
        self.assertFalse(r.json()['po_just_signed'])
        self.assertEqual(r.json()['kseb_section'], 'Kollam')

    def test_clearing_a_saved_po_date(self):
        self.patch_site_visit({'po_signed_date': '2026-07-27'})
        r = self.patch_site_visit({'po_signed_date': ''})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertIsNone(r.json()['po_signed_date'])
        r = self.patch_site_visit({'po_signed_date': None})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['po_signed_date'])

    def test_a_real_bad_date_is_still_rejected(self):
        r = self.patch_site_visit({'po_signed_date': 'not-a-date'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('po_signed_date', r.json())

    def test_other_edits_do_not_fire_the_prompt(self):
        r = self.patch_site_visit({'kseb_section': 'Kollam'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['po_just_signed'])

    def test_due_date_is_two_days_after_signing(self):
        r = self.patch_site_visit({'po_signed_date': '2026-07-27'})
        self.assertEqual(r.json()['kseb_feasibility_due_date'], '2026-07-29')

    def test_bde_gets_a_reminder_when_feasibility_is_outstanding(self):
        from ai_manager.models import Notification
        self.patch_site_visit({'po_signed_date': '2026-07-27', 'kseb_feasibility_taken': 'no'})
        self.assertTrue(Notification.objects.filter(
            user=self.bde, extra_data__kseb_feasibility_lead=self.lead.id).exists())

    def test_feasibility_is_editable_without_a_push_to_documentation(self):
        """It used to require pushed_to_documentation, which would have left the
        queue row read-only."""
        self.patch_site_visit({'po_signed_date': '2026-07-27'})
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.pushed_to_documentation)
        r = self.client.patch(f'/api/leads/{self.lead.id}/kseb-feasibility/',
                              data={'kseb_feasibility_taken': 'yes',
                                    'kseb_feasibility_date': '2026-07-28'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['kseb_feasibility_taken'], 'yes')

    def test_queue_still_carries_pushed_leads_with_no_po_date(self):
        pushed = Lead.objects.create(first_name='P', last_name='Pushed', phone='9994000002',
                                     status='converted', assigned_to=self.caller, bde=self.bde,
                                     value=1, pushed_to_documentation=True)
        ids = [row['id'] for row in self.queue()]
        self.assertIn(pushed.id, ids)

    def test_a_bde_only_sees_their_own_queue(self):
        other = mk('t_bde_other', 'bde')
        self.patch_site_visit({'po_signed_date': '2026-07-27'})
        self.assertEqual(self.queue(actor=other), [])


class ModuleCountsCoverageTests(TestCase):
    """The popup can only fire for modules that appear in module-counts, so every
    role must see keys for the queues it actually works."""

    EXPECTED = {
        'tele_caller': ['leads'],
        'bde': ['leads'],
        'documentation_staff': ['documentation', 'documentation-stage2', 'warranty'],
        'documentation_manager': ['documentation', 'documentation-stage2', 'warranty'],
        'accounts_staff': ['accounts', 'accounts/partially-paid', 'accounts/fully-paid', 'accounts/completed'],
        'purchase_staff': ['purchase'],
        'project_manager': ['project'],
        # Chasing the approval is the officer's job, so the follow-up queue is theirs.
        'liasoning_officer': ['liasoning', 'periodic-maintenance', 'discom-followup'],
        'admin': ['leads', 'documentation', 'accounts', 'purchase', 'project', 'liasoning'],
        'superadmin': ['leads', 'documentation', 'accounts', 'purchase', 'project', 'liasoning'],
        'coo': ['leads', 'documentation', 'accounts', 'purchase', 'project', 'liasoning'],
    }

    def counts(self, user):
        r = self.client.get('/api/leads/module-counts/', HTTP_AUTHORIZATION=token_for(user))
        self.assertEqual(r.status_code, 200, user.role)
        body = r.json()
        self.assertIn('counts', body)
        self.assertIn('assigned', body)
        return body

    def test_every_role_sees_its_own_modules(self):
        for role, modules in self.EXPECTED.items():
            body = self.counts(mk(f'c_{role}', role))
            for module in modules:
                self.assertIn(module, body['counts'], f'{role} is missing {module}')

    def test_assignment_targets_report_an_assigned_bucket(self):
        """`assigned` is what makes the modal say "assigned to you"."""
        for role, module in (('documentation_staff', 'documentation'),
                             ('accounts_staff', 'accounts'),
                             ('purchase_staff', 'purchase'),
                             ('project_manager', 'project'),
                             ('bde', 'leads')):
            body = self.counts(mk(f'a_{role}', role))
            self.assertIn(module, body['assigned'], f'{role} has no assigned bucket for {module}')

    def test_shared_queues_still_report_a_count(self):
        """No named assignee, so no `assigned` bucket — the modal falls back to
        "new work in your queue" and must still have a count to trigger on."""
        for username, role, modules in (('s_doc', 'documentation_staff', ('warranty',)),
                                        ('s_lia', 'liasoning_officer', ('discom-followup',))):
            body = self.counts(mk(username, role))
            for module in modules:
                self.assertIn(module, body['counts'])
                self.assertNotIn(module, body['assigned'])

    def test_a_newly_assigned_lead_moves_the_count(self):
        """The popup fires off a rising count, so the count has to move."""
        caller = mk('c_owner', 'tele_caller')
        before = self.counts(caller)['counts']['leads']
        Lead.objects.create(first_name='N', last_name='New', phone='9995100001',
                            status='new', assigned_to=caller, value=0)
        after = self.counts(caller)
        self.assertEqual(after['counts']['leads'], before + 1)
        self.assertEqual(after['assigned']['leads'], after['counts']['leads'])

    def test_b2b_roles_have_no_assignment_queues(self):
        """Documents the gap: the stock register has no per-user assignment, so
        these roles get no counts and therefore no popup."""
        for role in ('store_manager', 'store_keeper', 'accounts_b2b'):
            body = self.counts(mk(f'b_{role}', role))
            self.assertEqual(body['assigned'], {'leads': 0}, role)


class TeleCallerRetainsLeadTests(TestCase):
    """Handing a lead on must not drop it out of the tele caller's list."""

    def setUp(self):
        self.caller = mk('t_caller', 'tele_caller')
        self.caller2 = mk('t_caller2', 'tele_caller')
        self.bde = mk('t_bde', 'bde')
        self.admin = mk('t_admin', 'admin')

    def ids_for(self, user):
        r = self.client.get('/api/leads/?all=true', HTTP_AUTHORIZATION=token_for(user))
        self.assertEqual(r.status_code, 200)
        rows = r.json() if isinstance(r.json(), list) else r.json()['results']
        return [x['id'] for x in rows]

    def test_owning_a_lead_stamps_the_tele_caller(self):
        lead = Lead.objects.create(first_name='T', last_name='One', phone='9996000001',
                                   assigned_to=self.caller, value=0)
        lead.refresh_from_db()
        self.assertEqual(lead.tele_caller_id, self.caller.id)

    def test_a_bde_owner_is_not_stamped_as_the_tele_caller(self):
        lead = Lead.objects.create(first_name='T', last_name='Two', phone='9996000002',
                                   assigned_to=self.bde, value=0)
        lead.refresh_from_db()
        self.assertIsNone(lead.tele_caller_id)

    def test_lead_stays_visible_after_ownership_moves_to_the_bde(self):
        lead = Lead.objects.create(first_name='T', last_name='Handed', phone='9996000003',
                                   assigned_to=self.caller, value=0)
        self.assertIn(lead.id, self.ids_for(self.caller))

        r = self.client.patch(f'/api/leads/{lead.id}/', data={'assigned_to': self.bde.id},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 200, r.content[:200])
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to_id, self.bde.id)      # ownership did move
        self.assertIn(lead.id, self.ids_for(self.caller))        # …and it's still theirs to see
        self.assertIn(lead.id, self.ids_for(self.bde))

    def test_the_first_tele_caller_is_kept_not_overwritten(self):
        """Re-assigning between tele callers must not erase who worked it first."""
        lead = Lead.objects.create(first_name='T', last_name='Kept', phone='9996000004',
                                   assigned_to=self.caller, value=0)
        lead.assigned_to = self.caller2
        lead.save()
        lead.refresh_from_db()
        self.assertEqual(lead.tele_caller_id, self.caller.id)
        self.assertIn(lead.id, self.ids_for(self.caller))
        self.assertIn(lead.id, self.ids_for(self.caller2))

    def test_bulk_assign_stamps_too(self):
        """queryset.update() skips Lead.save(), so the bulk path needs its own stamp."""
        lead = Lead.objects.create(first_name='T', last_name='Bulk', phone='9996000005', value=0)
        r = self.client.post('/api/leads/bulk_assign/',
                             data={'ids': [lead.id], 'user_id': self.caller.id},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.tele_caller_id, self.caller.id)

    def test_bulk_update_assignee_stamps_too(self):
        lead = Lead.objects.create(first_name='T', last_name='BulkUpd', phone='9996000006', value=0)
        r = self.client.post('/api/leads/bulk_update/',
                             data={'ids': [lead.id], 'data': {'assigned_to_id': self.caller.id}},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.tele_caller_id, self.caller.id)

    def test_assigning_a_bde_leaves_the_owner_alone(self):
        """The dedicated hand-off only sets `bde`; the tele caller keeps the lead."""
        lead = Lead.objects.create(first_name='T', last_name='Bde', phone='9996000007',
                                   assigned_to=self.caller, value=0)
        r = self.client.post(f'/api/leads/{lead.id}/assign-bde/', data={'bde': self.bde.id},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 200, r.content[:200])
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to_id, self.caller.id)
        self.assertEqual(lead.bde_id, self.bde.id)
        self.assertIn(lead.id, self.ids_for(self.caller))

    def test_another_tele_caller_still_sees_nothing_of_it(self):
        lead = Lead.objects.create(first_name='T', last_name='Private', phone='9996000008',
                                   assigned_to=self.caller, value=0)
        self.assertNotIn(lead.id, self.ids_for(self.caller2))


class ClosedDealTests(TestCase):
    """A deal is closed when money has arrived in accounts — part or full —
    not when it reaches documentation."""

    def setUp(self):
        from decimal import Decimal
        self.admin = mk('cd_admin', 'admin')
        self.lead = Lead.objects.create(first_name='C', last_name='Deal', phone='9997000001',
                                        status='converted', value=Decimal('100000'))

    def payload(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        return r.json()

    def pay(self, amount, complete=False, discount=0):
        from decimal import Decimal
        from .models import PaymentVerification
        pv, _ = PaymentVerification.objects.get_or_create(lead=self.lead)
        pv.amount_received = Decimal(str(amount))
        pv.discount_value = Decimal(str(discount))
        pv.is_complete = complete
        pv.save()
        return pv

    def test_converted_alone_is_not_a_closed_deal(self):
        d = self.payload()
        self.assertFalse(d['is_closed_deal'])
        self.assertIsNone(d['deal_classification'])

    def test_reaching_documentation_is_not_a_closed_deal(self):
        """This used to be the trigger; documentation is work in progress."""
        self.lead.pushed_to_documentation = True
        self.lead.save()
        d = self.payload()
        self.assertFalse(d['is_closed_deal'])
        self.assertIsNone(d['deal_classification'])

    def test_in_accounts_with_nothing_paid_is_not_closed(self):
        self.lead.pushed_to_accounts = True
        self.lead.save()
        self.pay(0)
        d = self.payload()
        self.assertFalse(d['is_closed_deal'])

    def test_part_payment_closes_the_deal(self):
        self.lead.pushed_to_accounts = True
        self.lead.save()
        self.pay(40000)
        d = self.payload()
        self.assertTrue(d['is_closed_deal'])
        self.assertEqual(d['deal_classification'], 'partially_paid')

    def test_full_payment_closes_the_deal(self):
        self.lead.pushed_to_accounts = True
        self.lead.save()
        self.pay(100000)
        d = self.payload()
        self.assertTrue(d['is_closed_deal'])
        self.assertEqual(d['deal_classification'], 'fully_paid')

    def test_a_discount_can_settle_the_balance(self):
        self.lead.pushed_to_accounts = True
        self.lead.save()
        self.pay(90000, discount=10000)
        self.assertEqual(self.payload()['deal_classification'], 'fully_paid')

    def test_verified_with_no_money_taken_is_not_closed(self):
        """Accounts can sign off a record before the customer has actually paid."""
        self.lead.pushed_to_accounts = True
        self.lead.save()
        self.pay(0, complete=True)
        self.assertFalse(self.payload()['is_closed_deal'])

    def test_a_lost_deal_is_never_closed(self):
        self.lead.pushed_to_accounts = True
        self.lead.is_lost = True
        self.lead.save()
        self.pay(50000)
        d = self.payload()
        self.assertFalse(d['is_closed_deal'])
        self.assertEqual(d['deal_classification'], 'lost')

    def test_an_unconverted_lead_is_never_closed(self):
        self.lead.status = 'interested'
        self.lead.pushed_to_accounts = True
        self.lead.save()
        self.pay(50000)
        d = self.payload()
        self.assertFalse(d['is_closed_deal'])
        self.assertIsNone(d['deal_classification'])


class SharedOwnershipTests(TestCase):
    """Assigning a lead to a BDE — through the owner field or the dedicated
    action — must record them as the BDE and leave the tele caller in place."""

    def setUp(self):
        self.caller = mk('so_caller', 'tele_caller')
        self.bde = mk('so_bde', 'bde')
        self.bde2 = mk('so_bde2', 'bde')
        self.admin = mk('so_admin', 'admin')
        self.lead = Lead.objects.create(first_name='S', last_name='Own', phone='9998000001',
                                        status='new', assigned_to=self.caller, value=0)

    def ids_for(self, user):
        r = self.client.get('/api/leads/?all=true', HTTP_AUTHORIZATION=token_for(user))
        rows = r.json() if isinstance(r.json(), list) else r.json()['results']
        return [x['id'] for x in rows]

    def patch(self, actor, payload):
        return self.client.patch(f'/api/leads/{self.lead.id}/', data=payload,
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor))

    def test_owning_a_lead_as_a_bde_records_the_bde(self):
        """The bug: this left `bde` empty, so the lead could never be converted."""
        r = self.patch(self.caller, {'assigned_to': self.bde.id})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.bde.id)
        self.assertEqual(self.lead.bde_id, self.bde.id)
        self.assertEqual(self.lead.tele_caller_id, self.caller.id)

    def test_the_lead_can_then_be_converted(self):
        self.patch(self.caller, {'assigned_to': self.bde.id})
        r = self.patch(self.caller, {'status': 'converted'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'converted')

    def test_converting_without_any_bde_is_still_refused(self):
        r = self.patch(self.caller, {'status': 'converted'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('Assign a BDE', str(r.json()))

    def test_both_sides_keep_the_lead(self):
        self.patch(self.caller, {'assigned_to': self.bde.id})
        self.assertIn(self.lead.id, self.ids_for(self.caller))
        self.assertIn(self.lead.id, self.ids_for(self.bde))

    def test_bulk_assign_to_a_bde_records_the_bde(self):
        """queryset.update() skips Lead.save(), so the bulk path stamps too."""
        r = self.client.post('/api/leads/bulk_assign/',
                             data={'ids': [self.lead.id], 'user_id': self.bde.id},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.bde_id, self.bde.id)

    def test_bulk_update_assignee_records_the_bde(self):
        r = self.client.post('/api/leads/bulk_update/',
                             data={'ids': [self.lead.id], 'data': {'assigned_to_id': self.bde.id}},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.bde_id, self.bde.id)

    def test_an_existing_bde_stands_until_the_lead_is_handed_to_another(self):
        """`assign-bde` names the BDE; a later hand-off moves it.

        The two must not disagree once the owner is itself a BDE: the lead list
        matches on either field, so a lead owned by one BDE while stamped to
        another showed up for both of them.
        """
        self.client.post(f'/api/leads/{self.lead.id}/assign-bde/', data={'bde': self.bde2.id},
                         content_type='application/json', HTTP_AUTHORIZATION=token_for(self.caller))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.bde_id, self.bde2.id)      # stands on its own

        # Editing something else leaves the hand-off alone.
        self.patch(self.caller, {'value': 4321})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.bde_id, self.bde2.id)

        # Handing the lead to another BDE moves it.
        self.patch(self.caller, {'assigned_to': self.bde.id})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.bde_id, self.bde.id)
        self.assertEqual(self.lead.assigned_to_id, self.bde.id)

    def test_tele_caller_can_still_change_the_bde_after_handing_it_over(self):
        """Ownership is shared, so passing the lead on must not cost them this."""
        self.patch(self.caller, {'assigned_to': self.bde.id})
        r = self.client.post(f'/api/leads/{self.lead.id}/assign-bde/', data={'bde': self.bde2.id},
                             content_type='application/json', HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.bde_id, self.bde2.id)

    def test_a_tele_caller_owner_is_not_recorded_as_a_bde(self):
        other = mk('so_caller2', 'tele_caller')
        self.patch(self.admin, {'assigned_to': other.id})
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.bde_id)
        self.assertEqual(self.lead.tele_caller_id, self.caller.id)   # first one sticks


class OwnerDisplayTests(TestCase):
    """The Leads list shows both owners once a lead is handed to a BDE."""

    def setUp(self):
        self.caller = mk('od_caller', 'tele_caller')
        self.bde = mk('od_bde', 'bde')
        self.admin = mk('od_admin', 'admin')

    def payload(self, lead):
        r = self.client.get(f'/api/leads/{lead.id}/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_before_a_bde_only_the_tele_caller_is_named(self):
        lead = Lead.objects.create(first_name='O', last_name='One', phone='9999000001',
                                   assigned_to=self.caller, value=0)
        d = self.payload(lead)
        self.assertEqual(d['tele_caller_name'], 'od_caller')
        self.assertIsNone(d['bde_name'])

    def test_after_the_hand_off_both_are_named(self):
        lead = Lead.objects.create(first_name='O', last_name='Two', phone='9999000002',
                                   assigned_to=self.caller, value=0)
        self.client.post(f'/api/leads/{lead.id}/assign-bde/', data={'bde': self.bde.id},
                         content_type='application/json', HTTP_AUTHORIZATION=token_for(self.caller))
        d = self.payload(lead)
        self.assertEqual(d['tele_caller_name'], 'od_caller')
        self.assertEqual(d['bde_name'], 'od_bde')

    def test_the_tele_caller_survives_ownership_moving_to_the_bde(self):
        """assigned_to_name would report the BDE — the tele caller must persist."""
        lead = Lead.objects.create(first_name='O', last_name='Three', phone='9999000003',
                                   assigned_to=self.caller, value=0)
        self.client.patch(f'/api/leads/{lead.id}/', data={'assigned_to': self.bde.id},
                          content_type='application/json', HTTP_AUTHORIZATION=token_for(self.caller))
        d = self.payload(lead)
        self.assertEqual(d['assigned_to_name'], 'od_bde')
        self.assertEqual(d['tele_caller_name'], 'od_caller')
        self.assertEqual(d['bde_name'], 'od_bde')

    def test_legacy_leads_fall_back_to_the_owner(self):
        """Rows that predate the tele_caller field still name their tele caller."""
        lead = Lead.objects.create(first_name='O', last_name='Four', phone='9999000004', value=0)
        Lead.objects.filter(pk=lead.pk).update(assigned_to=self.caller, tele_caller=None)
        self.assertEqual(self.payload(lead)['tele_caller_name'], 'od_caller')

    def test_a_non_agent_owner_is_not_reported_as_a_tele_caller(self):
        lead = Lead.objects.create(first_name='O', last_name='Five', phone='9999000005',
                                   assigned_to=self.admin, value=0)
        d = self.payload(lead)
        self.assertIsNone(d['tele_caller_name'])
        self.assertEqual(d['assigned_to_name'], 'od_admin')


class PurchaseQueueTests(TestCase):
    """Procurement starts on the first payment — part or full — and the queue
    keeps the two apart."""

    def setUp(self):
        from decimal import Decimal
        self.admin = mk('pq_admin', 'admin')
        self.purchase = mk('pq_staff', 'purchase_staff')
        self.accounts = mk('pq_acct', 'accounts_staff')
        self.bde = mk('pq_bde', 'bde')

    def make_lead(self, last, value='100000'):
        from decimal import Decimal
        lead = Lead.objects.create(first_name='P', last_name=last, phone=f'99931{last[:5]}',
                                   status='converted', bde=self.bde, value=Decimal(value),
                                   pushed_to_accounts=True)
        return lead

    def verify(self, lead, received, discount=0):
        """Run the real accounts flow so the hand-off fires as it does live."""
        from decimal import Decimal
        from .models import PaymentVerification
        pv, _ = PaymentVerification.objects.get_or_create(lead=lead)
        pv.amount_received = Decimal(str(received))
        pv.discount_value = Decimal(str(discount))
        pv.payment_mode = 'cash'
        pv.save()
        r = self.client.post(f'/api/leads/{lead.id}/complete-payment-verification/',
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        # Assert here: a wrong URL would 404 and every assertion below would then
        # be testing nothing.
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r

    def queue(self, actor=None, query=''):
        r = self.client.get(f'/api/leads/purchase/{query}',
                            HTTP_AUTHORIZATION=token_for(actor or self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def test_a_part_payment_reaches_purchase(self):
        """This used to wait in accounts until the balance was cleared."""
        lead = self.make_lead('Part')
        self.verify(lead, 40000)
        lead.refresh_from_db()
        self.assertTrue(lead.pushed_to_purchase)
        row = next(r for r in self.queue() if r['id'] == lead.id)
        self.assertEqual(row['payment_state'], 'partially_paid')
        self.assertEqual(Decimal(str(row['balance_amount'])), Decimal('60000'))

    def test_a_full_payment_still_reaches_purchase(self):
        lead = self.make_lead('Full')
        self.verify(lead, 100000)
        lead.refresh_from_db()
        self.assertTrue(lead.pushed_to_purchase)
        row = next(r for r in self.queue() if r['id'] == lead.id)
        self.assertEqual(row['payment_state'], 'fully_paid')

    def test_verifying_with_no_money_does_not_reach_purchase(self):
        lead = self.make_lead('Zero')
        self.verify(lead, 0)
        lead.refresh_from_db()
        self.assertFalse(lead.pushed_to_purchase)

    def test_the_queue_filters_by_payment_state(self):
        part = self.make_lead('FilterPart')
        full = self.make_lead('FilterFull')
        self.verify(part, 25000)
        self.verify(full, 100000)

        partial_ids = [r['id'] for r in self.queue(query='?payment=partially_paid')]
        self.assertIn(part.id, partial_ids)
        self.assertNotIn(full.id, partial_ids)

        full_ids = [r['id'] for r in self.queue(query='?payment=fully_paid')]
        self.assertIn(full.id, full_ids)
        self.assertNotIn(part.id, full_ids)

        both = [r['id'] for r in self.queue()]
        self.assertIn(part.id, both)
        self.assertIn(full.id, both)

    def test_clearing_the_balance_moves_the_row_to_fully_paid(self):
        lead = self.make_lead('Cleared')
        self.verify(lead, 40000)
        row = next(r for r in self.queue() if r['id'] == lead.id)
        self.assertEqual(row['payment_state'], 'partially_paid')

        from .models import PaymentVerification
        pv = PaymentVerification.objects.get(lead=lead)
        pv.amount_received = Decimal('100000')
        pv.save(update_fields=['amount_received'])

        row = next(r for r in self.queue() if r['id'] == lead.id)
        self.assertEqual(row['payment_state'], 'fully_paid')
        self.assertEqual(Decimal(str(row['balance_amount'])), Decimal('0'))

    def test_purchase_staff_see_the_same_buckets(self):
        lead = self.make_lead('Staff')
        self.verify(lead, 30000)
        lead.refresh_from_db()
        lead.purchase_staff = self.purchase
        lead.save(update_fields=['purchase_staff'])
        rows = self.queue(actor=self.purchase)
        self.assertEqual([r['payment_state'] for r in rows], ['partially_paid'])



class Stage1NeedsFeasibilityTests(TestCase):
    """Documentation Stage 1 hands the customer to accounts, so it waits for the
    BDE's KSEB feasibility sign-off."""

    def setUp(self):
        from .models import DocumentationStage1, LeadDocument, SiteVisit
        self.doc = mk('s1_doc', 'documentation_staff')
        self.bde = mk('s1_bde', 'bde')
        self.lead = Lead.objects.create(first_name='S', last_name='One', phone='9994100001',
                                        status='converted', bde=self.bde, value=100000,
                                        pushed_to_documentation=True,
                                        documentation_staff=self.doc)
        self.stage1 = DocumentationStage1.objects.create(lead=self.lead)
        self.sv = SiteVisit.objects.create(lead=self.lead)
        # Everything the MNRE gate needs, so feasibility is the only thing left.
        self.stage1.mnre_plant_capacity = '5 kW'
        self.stage1.mnre_completed = True
        self.stage1.save()
        # Every mandatory MNRE slot is a shared *kind*, satisfied from the lead's
        # shared document pool rather than a stage-local row.
        from .document_kinds import SLOT_TO_KIND
        for slot in ('mnre_aadhaar', 'mnre_pan', 'mnre_passbook',
                     'mnre_kseb_bill', 'mnre_purchase_order'):
            LeadDocument.objects.create(lead=self.lead, kind=SLOT_TO_KIND[slot],
                                        file=f'lead_documents/{slot}.pdf')
        self.assertEqual(self.stage1.missing_mandatory_fields(), [])   # only feasibility left

    def push(self):
        return self.client.post(f'/api/leads/{self.lead.id}/complete-documentation-stage1/',
                                HTTP_AUTHORIZATION=token_for(self.doc))

    def test_push_is_refused_while_feasibility_is_pending(self):
        r = self.push()
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertTrue(r.json().get('kseb_feasibility_pending'))
        self.lead.refresh_from_db(); self.stage1.refresh_from_db()
        self.assertFalse(self.stage1.is_complete)
        self.assertFalse(self.lead.pushed_to_accounts)

    def test_push_works_once_feasibility_is_complete(self):
        self.sv.kseb_feasibility_complete = True
        self.sv.save(update_fields=['kseb_feasibility_complete'])
        r = self.push()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db(); self.stage1.refresh_from_db()
        self.assertTrue(self.stage1.is_complete)
        self.assertTrue(self.lead.pushed_to_accounts)

    def test_a_lead_with_no_site_visit_at_all_is_refused(self):
        self.sv.delete()
        r = self.push()
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json().get('kseb_feasibility_pending'))

    def test_the_mnre_gate_still_comes_first(self):
        """A missing MNRE field is reported as such, not as a feasibility problem."""
        self.stage1.mnre_plant_capacity = ''
        self.stage1.save(update_fields=['mnre_plant_capacity'])
        r = self.push()
        self.assertEqual(r.status_code, 400)
        self.assertIn('missing', r.json())
        self.assertNotIn('kseb_feasibility_pending', r.json())

    def test_the_mnre_completed_tick_is_mandatory(self):
        """The uploads don't prove the portal submission was filed, so the staff
        member's own sign-off is part of the gate."""
        self.sv.kseb_feasibility_complete = True
        self.sv.save(update_fields=['kseb_feasibility_complete'])
        self.stage1.mnre_completed = False
        self.stage1.save(update_fields=['mnre_completed'])
        self.assertIn('mnre_completed', self.stage1.missing_mandatory_fields())

        r = self.push()
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertIn('mnre_completed', r.json()['missing'])
        self.stage1.refresh_from_db()
        self.assertFalse(self.stage1.is_complete)

        # Ticking it is the only thing standing in the way.
        self.stage1.mnre_completed = True
        self.stage1.save(update_fields=['mnre_completed'])
        self.assertEqual(self.push().status_code, 200)

    def test_the_tick_saves_through_the_record_endpoint(self):
        r = self.client.patch(f'/api/leads/{self.lead.id}/documentation-stage1/',
                              data={'mnre_completed': False}, content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.doc))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertIs(r.json()['mnre_completed'], False)
        self.stage1.refresh_from_db()
        self.assertFalse(self.stage1.mnre_completed)

    def test_the_documentation_payload_carries_the_feasibility_status(self):
        """The read-only card on Stage 1 reads this off the site visit."""
        r = self.client.get(f'/api/leads/{self.lead.id}/documentation-detail/',
                            HTTP_AUTHORIZATION=token_for(self.doc))
        self.assertEqual(r.status_code, 200, r.content[:200])
        sv = r.json()['site_visit']
        self.assertIs(sv['kseb_feasibility_complete'], False)

        self.sv.kseb_feasibility_complete = True
        self.sv.save(update_fields=['kseb_feasibility_complete'])
        r = self.client.get(f'/api/leads/{self.lead.id}/documentation-detail/',
                            HTTP_AUTHORIZATION=token_for(self.doc))
        self.assertIs(r.json()['site_visit']['kseb_feasibility_complete'], True)


class BdeLeadVisibilityTests(TestCase):
    """A lead belongs to the BDE working it now — not to whoever held it before."""

    def setUp(self):
        self.caller = mk('v_caller', 'tele_caller')
        self.bde1 = mk('v_bde1', 'bde')
        self.bde2 = mk('v_bde2', 'bde')
        self.admin = mk('v_admin', 'admin')

    def visible_to(self, user):
        r = self.client.get('/api/leads/?all=true', HTTP_AUTHORIZATION=token_for(user))
        self.assertEqual(r.status_code, 200, r.content[:200])
        d = r.json()
        rows = d if isinstance(d, list) else d.get('results', [])
        return {row['id'] for row in rows}

    def make(self, owner, **kw):
        return Lead.objects.create(first_name='V', last_name='One', phone='9994000001',
                                   status='new', assigned_to=owner, **kw)

    def test_a_lead_is_visible_only_to_the_bde_it_is_assigned_to(self):
        lead = self.make(self.bde1)
        self.assertIn(lead.id, self.visible_to(self.bde1))
        self.assertNotIn(lead.id, self.visible_to(self.bde2))

    def test_moving_it_between_bdes_takes_it_out_of_the_first_ones_list(self):
        """The reported bug: the old BDE kept seeing a lead handed to another."""
        lead = self.make(self.bde1)
        self.assertEqual(lead.bde_id, self.bde1.id)

        lead.assigned_to = self.bde2
        lead.save()

        lead.refresh_from_db()
        self.assertEqual(lead.bde_id, self.bde2.id)
        self.assertIn(lead.id, self.visible_to(self.bde2))
        self.assertNotIn(lead.id, self.visible_to(self.bde1))

    def test_reassigning_through_the_api_moves_it_too(self):
        lead = self.make(self.bde1)
        r = self.client.patch(f'/api/leads/{lead.id}/', data={'assigned_to': self.bde2.id},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        lead.refresh_from_db()
        self.assertEqual(lead.bde_id, self.bde2.id)
        self.assertNotIn(lead.id, self.visible_to(self.bde1))

    def test_bulk_assignment_moves_it_as_well(self):
        lead = self.make(self.bde1)
        r = self.client.post('/api/leads/bulk_assign/',
                             data={'ids': [lead.id], 'user_id': self.bde2.id},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        lead.refresh_from_db()
        self.assertEqual(lead.bde_id, self.bde2.id)
        self.assertNotIn(lead.id, self.visible_to(self.bde1))

    def test_the_tele_caller_keeps_sight_of_a_lead_handed_to_a_bde(self):
        """Shared ownership is unaffected — only the BDE half stops being sticky."""
        lead = self.make(self.caller)
        self.assertEqual(lead.tele_caller_id, self.caller.id)

        lead.assigned_to = self.bde1
        lead.save()
        lead.refresh_from_db()

        self.assertEqual(lead.tele_caller_id, self.caller.id)
        self.assertEqual(lead.bde_id, self.bde1.id)
        self.assertIn(lead.id, self.visible_to(self.caller))
        self.assertIn(lead.id, self.visible_to(self.bde1))
        self.assertNotIn(lead.id, self.visible_to(self.bde2))


class BdeCannotEditOrDeleteLeadsTests(TestCase):
    """The lead record belongs to the tele-calling side; a BDE reports through
    the site visit."""

    def setUp(self):
        self.bde = mk('e_bde', 'bde')
        self.caller = mk('e_caller', 'tele_caller')
        self.admin = mk('e_admin', 'admin')
        # Owned by the tele caller, handed to the BDE for the visit — the shape
        # both of them can see.
        self.lead = Lead.objects.create(first_name='E', last_name='One', phone='9995000001',
                                        status='new', assigned_to=self.caller,
                                        bde=self.bde, value=0)
        # One the BDE owns outright, for the "even their own" case.
        self.own = Lead.objects.create(first_name='E', last_name='Own', phone='9995000002',
                                       status='new', assigned_to=self.bde, value=0)

    def patch(self, actor, payload):
        return self.client.patch(f'/api/leads/{self.lead.id}/', data=payload,
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor))

    # ── editing ──
    def test_bde_cannot_edit_lead_details(self):
        r = self.patch(self.bde, {'first_name': 'Changed', 'phone': '9995009999'})
        self.assertEqual(r.status_code, 403)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.first_name, 'E')

    def test_bde_cannot_edit_even_a_lead_they_own(self):
        r = self.client.patch(f'/api/leads/{self.own.id}/', data={'notes': 'mine'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403)

    def test_others_can_still_edit(self):
        for actor in (self.caller, self.admin):
            r = self.patch(actor, {'notes': f'by {actor.username}'})
            self.assertEqual(r.status_code, 200, r.content[:200])

    # ── deleting ──
    def test_bde_cannot_delete_a_lead(self):
        r = self.client.delete(f'/api/leads/{self.lead.id}/',
                               HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403)
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.is_trashed)

    def test_bde_cannot_bulk_delete_either(self):
        r = self.client.post('/api/leads/bulk_delete/', data={'ids': [self.lead.id]},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403)
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.is_trashed)

    def test_others_can_still_delete(self):
        r = self.client.delete(f'/api/leads/{self.lead.id}/',
                               HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 204)
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.is_trashed)

    # ── what a BDE keeps ──
    def test_the_bde_still_sees_the_lead(self):
        r = self.client.get('/api/leads/?all=true', HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 200)
        d = r.json()
        rows = d if isinstance(d, list) else d.get('results', [])
        self.assertIn(self.lead.id, {row['id'] for row in rows})

    def test_the_bde_can_still_record_the_site_visit(self):
        """Their own workflow is a separate endpoint and must keep working."""
        r = self.client.patch(f'/api/leads/{self.lead.id}/site-visit/',
                              data={'roof_type': 'rcc'}, content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(SiteVisit.objects.get(lead=self.lead).roof_type, 'rcc')

    def test_the_bde_can_still_mark_a_converted_deal_lost(self):
        self.lead.status = 'converted'
        self.lead.save()
        r = self.client.post(f'/api/leads/{self.lead.id}/mark-lost/',
                             data={'reason': 'Customer backed out'},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.is_lost)


class BdeHasNoLeadListToolsTests(TestCase):
    """CSV template / export and the Archived + Trash views manage the lead
    book; a BDE works the leads handed to them."""

    def setUp(self):
        self.bde = mk('tl_bde', 'bde')
        self.caller = mk('tl_caller', 'tele_caller')
        self.admin = mk('tl_admin', 'admin')
        Lead.objects.create(first_name='T', last_name='One', phone='9996000001',
                            status='new', assigned_to=self.caller, bde=self.bde)

    def get(self, path, actor):
        return self.client.get(path, HTTP_AUTHORIZATION=token_for(actor))

    def test_bde_cannot_download_the_csv_template(self):
        self.assertEqual(self.get('/api/leads/csv_template/', self.bde).status_code, 403)

    def test_bde_cannot_export_leads(self):
        self.assertEqual(self.get('/api/leads/export_csv/', self.bde).status_code, 403)

    def test_bde_cannot_open_the_trash(self):
        self.assertEqual(self.get('/api/leads/trash/', self.bde).status_code, 403)

    def test_everyone_else_still_has_them(self):
        for actor in (self.caller, self.admin):
            for path in ('/api/leads/csv_template/', '/api/leads/export_csv/', '/api/leads/trash/'):
                self.assertEqual(self.get(path, actor).status_code, 200,
                                 f'{actor.role} {path}')

    def test_bde_cannot_archive_or_unarchive(self):
        lead = Lead.objects.filter(bde=self.bde).first()
        r = self.client.post(f'/api/leads/{lead.id}/archive/',
                             HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403)
        lead.refresh_from_db()
        self.assertFalse(lead.is_archived)

        lead.is_archived = True
        lead.save(update_fields=['is_archived'])
        r = self.client.post(f'/api/leads/{lead.id}/unarchive/',
                             HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403)

    def test_others_can_still_archive(self):
        lead = Lead.objects.filter(bde=self.bde).first()
        r = self.client.post(f'/api/leads/{lead.id}/archive/',
                             HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 200, r.content[:200])
        lead.refresh_from_db()
        self.assertTrue(lead.is_archived)

    def test_the_bde_still_gets_their_lead_list(self):
        r = self.get('/api/leads/?all=true', self.bde)
        self.assertEqual(r.status_code, 200)


class ConsumerNumberLimitTests(TestCase):
    """A KSEB consumer number is digits, at most fifteen of them."""

    def setUp(self):
        self.bde = mk('cn_bde', 'bde')
        self.caller = mk('cn_caller', 'tele_caller')
        self.lead = Lead.objects.create(first_name='C', last_name='Num', phone='9997000001',
                                        status='new', assigned_to=self.caller, bde=self.bde)

    def save(self, value):
        return self.client.patch(f'/api/leads/{self.lead.id}/site-visit/',
                                 data={'consumer_number': value},
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(self.bde))

    def test_fifteen_digits_is_accepted(self):
        r = self.save('123456789012345')
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(SiteVisit.objects.get(lead=self.lead).consumer_number,
                         '123456789012345')

    def test_a_sixteenth_digit_is_refused(self):
        r = self.save('1234567890123456')
        self.assertEqual(r.status_code, 400)
        self.assertIn('consumer_number', r.json())

    def test_letters_are_refused(self):
        r = self.save('12345ABC')
        self.assertEqual(r.status_code, 400)
        self.assertIn('consumer_number', r.json())

    def test_blank_is_still_allowed(self):
        """The field is optional — the visit may happen before the number is known."""
        self.assertEqual(self.save('').status_code, 200)


class EarthingSurfaceChoiceTests(TestCase):
    """Earthing surface is one of four surfaces, not free text."""

    def setUp(self):
        self.bde = mk('es_bde', 'bde')
        self.caller = mk('es_caller', 'tele_caller')
        self.lead = Lead.objects.create(first_name='E', last_name='Surface', phone='9999000001',
                                        status='new', assigned_to=self.caller, bde=self.bde)

    def save(self, value):
        return self.client.patch(f'/api/leads/{self.lead.id}/site-visit/',
                                 data={'earthing_surface': value},
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(self.bde))

    def test_each_surface_is_accepted(self):
        for value in ('soil', 'concrete', 'tile', 'interlock'):
            r = self.save(value)
            self.assertEqual(r.status_code, 200, f'{value}: {r.content[:120]}')
            self.assertEqual(SiteVisit.objects.get(lead=self.lead).earthing_surface, value)

    def test_free_text_is_refused(self):
        r = self.save('gravel')
        self.assertEqual(r.status_code, 400)
        self.assertIn('earthing_surface', r.json())

    def test_blank_is_still_allowed(self):
        self.assertEqual(self.save('').status_code, 200)


class LoanRemarksAndReceiptSendTests(TestCase):
    """Accounts: the Loan mode, the remarks note, and sending a receipt out."""

    @classmethod
    def setUpClass(cls):
        import shutil, tempfile
        from django.test import override_settings
        cls._media = tempfile.mkdtemp(prefix='receipt-test-')
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        cls._rmtree = shutil.rmtree
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        cls._rmtree(cls._media, ignore_errors=True)

    def setUp(self):
        from decimal import Decimal
        self.admin = mk('lr_admin', 'admin')
        self.admin.is_staff = True
        self.admin.save()
        self.lead = Lead.objects.create(first_name='L', last_name='Loan', phone='9993100001',
                                        email='buyer@example.com', status='converted',
                                        value=Decimal('100000'), pushed_to_accounts=True)

    def patch_pv(self, payload):
        return self.client.patch(f'/api/leads/{self.lead.id}/payment-verification/',
                                 data=payload, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(self.admin))

    # ── Loan mode ──
    def test_loan_is_an_accepted_payment_mode(self):
        r = self.patch_pv({'payment_mode': 'loan'})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['payment_mode'], 'loan')

    def test_loan_does_not_demand_a_utr(self):
        """Cash aside, the other modes need a reference; a loan is evidenced by
        the sanction, so it must not block verification."""
        from .models import PaymentVerification
        pv, _ = PaymentVerification.objects.get_or_create(lead=self.lead)
        pv.payment_mode = 'loan'
        pv.save()
        self.assertEqual(pv.missing_required_fields(), [])

    def test_an_unknown_mode_is_still_refused(self):
        self.assertEqual(self.patch_pv({'payment_mode': 'barter'}).status_code, 400)

    # ── Remarks ──
    def test_remarks_round_trip(self):
        r = self.patch_pv({'remarks': 'Cheque cleared on the 3rd.'})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['remarks'], 'Cheque cleared on the 3rd.')
        r = self.client.get(f'/api/leads/{self.lead.id}/payment-verification/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.json()['remarks'], 'Cheque cleared on the 3rd.')

    # ── Sending the receipt ──
    def _receipt(self):
        from decimal import Decimal
        from .receipts import issue_receipt
        return issue_receipt(self.lead, Decimal('50000'), on_account_of='Margin Money',
                             payment_mode='loan')

    @staticmethod
    def _pdf():
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('r.pdf', b'%PDF-1.4 x', content_type='application/pdf')

    def test_sending_by_email_stores_the_receipt(self):
        from unittest.mock import patch
        voucher = self._receipt()
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'sent', 'error': ''})()
            r = self.client.post(f'/api/leads/{self.lead.id}/send-receipt/', {
                'pdf': self._pdf(), 'channels': 'email', 'receipt_id': voucher.id,
            }, HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['sent']['email'], 'sent')
        # Falls back to the lead's own address when none is given.
        self.assertEqual(send.call_args.kwargs['to'], ['buyer@example.com'])
        self.assertEqual(send.call_args.kwargs['subject'], f'Receipt {voucher.number}')
        voucher.refresh_from_db()
        self.assertTrue(voucher.pdf)
        self.assertNotIn('/', voucher.pdf.name.split('/')[-1])

    def test_sending_by_whatsapp_sends_a_document_link(self):
        from unittest.mock import patch
        voucher = self._receipt()
        with patch('messaging.whatsapp.send_document') as send:
            send.return_value = 'wamid.1'
            r = self.client.post(f'/api/leads/{self.lead.id}/send-receipt/', {
                'pdf': self._pdf(), 'channels': 'whatsapp', 'phone': '9876543210',
                'receipt_id': voucher.id,
            }, HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        kwargs = send.call_args.kwargs
        self.assertEqual(kwargs['to'], '9876543210')
        self.assertTrue(kwargs['link'].startswith('http'))
        self.assertTrue(kwargs['filename'].endswith('.pdf'))

    def test_a_sent_receipt_lands_on_the_activity_timeline(self):
        """Sending a receipt is something that happened to this customer, so it
        belongs beside the payment it acknowledges."""
        from unittest.mock import patch
        voucher = self._receipt()
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'sent', 'error': ''})()
            self.client.post(f'/api/leads/{self.lead.id}/send-receipt/', {
                'pdf': self._pdf(), 'channels': 'email', 'email': 'asha@example.com',
                'receipt_id': voucher.id,
            }, HTTP_AUTHORIZATION=token_for(self.admin))

        r = self.client.get(f'/api/leads/{self.lead.id}/activity-timeline/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        entries = [e['description'] for e in r.json()['entries']]
        self.assertTrue(any(voucher.number in e and 'asha@example.com' in e for e in entries),
                        entries)

    def test_a_whatsapp_send_is_recorded_too(self):
        from unittest.mock import patch
        voucher = self._receipt()
        with patch('messaging.whatsapp.send_document'):
            self.client.post(f'/api/leads/{self.lead.id}/send-receipt/', {
                'pdf': self._pdf(), 'channels': 'whatsapp', 'phone': '9895271484',
                'receipt_id': voucher.id,
            }, HTTP_AUTHORIZATION=token_for(self.admin))
        entries = [e['description'] for e in self.client.get(
            f'/api/leads/{self.lead.id}/activity-timeline/',
            HTTP_AUTHORIZATION=token_for(self.admin)).json()['entries']]
        self.assertTrue(any('WhatsApp to 9895271484' in e for e in entries), entries)

    def test_a_failed_send_is_not_recorded_as_one(self):
        """A refusal is not an event — the timeline records deliveries."""
        from unittest.mock import patch
        from .models import ActivityLog
        voucher = self._receipt()
        before = ActivityLog.objects.filter(lead=self.lead).count()
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'failed', 'error': 'SMTP refused'})()
            r = self.client.post(f'/api/leads/{self.lead.id}/send-receipt/', {
                'pdf': self._pdf(), 'channels': 'email', 'email': 'asha@example.com',
                'receipt_id': voucher.id,
            }, HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.json()['sent']['email'], 'failed')
        self.assertEqual(ActivityLog.objects.filter(lead=self.lead).count(), before)

    def test_sending_without_a_receipt_says_so(self):
        r = self.client.post(f'/api/leads/{self.lead.id}/send-receipt/',
                             {'pdf': self._pdf(), 'channels': 'email'},
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 404)
        self.assertIn('No receipt', r.json()['error'])

    def test_a_missing_address_is_reported(self):
        self.lead.email = ''
        self.lead.save(update_fields=['email'])
        voucher = self._receipt()
        r = self.client.post(f'/api/leads/{self.lead.id}/send-receipt/', {
            'pdf': self._pdf(), 'channels': 'email', 'receipt_id': voucher.id,
        }, HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 502)
        self.assertIn('No email address', r.json()['error'])

    def test_accounts_access_still_gates_it(self):
        bde = mk('lr_bde', 'bde')
        voucher = self._receipt()
        r = self.client.post(f'/api/leads/{self.lead.id}/send-receipt/', {
            'pdf': self._pdf(), 'channels': 'email', 'receipt_id': voucher.id,
        }, HTTP_AUTHORIZATION=token_for(bde))
        self.assertIn(r.status_code, (403, 404))


class DashboardMatchesTheLeadListTests(TestCase):
    """The dashboard counts what the Leads page lists. A BDE's leads are owned by
    the tele caller who handed them over, so scoping on the owner alone reported
    nothing for them."""

    def setUp(self):
        from decimal import Decimal
        self.bde = mk('dm_bde', 'bde')
        self.caller = mk('dm_caller', 'tele_caller')
        self.other = mk('dm_other', 'bde')
        # Owned by the tele caller, handed to the BDE — the shape from the report.
        for n in range(2):
            Lead.objects.create(first_name='D', last_name=f'Handed{n}',
                                phone=f'999400000{n}', status='new',
                                assigned_to=self.caller, bde=self.bde,
                                value=Decimal('50000'))

    def stats(self, actor):
        r = self.client.get('/api/dashboard-stats/', HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def listed(self, actor):
        r = self.client.get('/api/leads/?all=true', HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:200])
        d = r.json()
        return d if isinstance(d, list) else d.get('results', [])

    def test_the_bde_sees_their_leads_counted(self):
        self.assertEqual(self.stats(self.bde)['total_leads'], 2)

    def test_the_count_equals_the_rows_on_the_leads_page(self):
        for actor in (self.bde, self.caller):
            self.assertEqual(self.stats(actor)['total_leads'], len(self.listed(actor)),
                             f'{actor.username} dashboard and list disagree')

    def test_pipeline_value_is_counted_too(self):
        """Revenue / pipeline read the same queryset, so they were zero as well."""
        self.assertEqual(float(self.stats(self.bde)['pipeline_value']), 100000.0)

    def test_another_bde_still_sees_nothing(self):
        self.assertEqual(self.stats(self.other)['total_leads'], 0)
        self.assertEqual(self.listed(self.other), [])


class FeasibilityPendingReminderTests(TestCase):
    """What the reminder popup polls: the BDE's outstanding feasibilities."""

    def setUp(self):
        from datetime import date, timedelta
        self.bde = mk('fp_bde', 'bde')
        self.other = mk('fp_other', 'bde')
        self.caller = mk('fp_caller', 'tele_caller')
        self.admin = mk('fp_admin', 'admin')
        self.today = date.today()

        # On the queue (PO signed), feasibility not taken.
        self.lead = Lead.objects.create(first_name='F', last_name='Pending', phone='9995500001',
                                        status='new', assigned_to=self.caller, bde=self.bde)
        self.sv = SiteVisit.objects.create(lead=self.lead,
                                           po_signed_date=self.today - timedelta(days=5))

    def pending(self, actor):
        r = self.client.get('/api/leads/feasibility-pending/',
                            HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def test_the_bde_is_told_what_is_outstanding(self):
        d = self.pending(self.bde)
        self.assertEqual(d['count'], 1)
        self.assertEqual(d['items'][0]['name'], 'F Pending')

    def test_it_reports_the_due_date_and_overdue_flag(self):
        """Feasibility is due 2 days after the PO; this one was signed 5 days ago."""
        item = self.pending(self.bde)['items'][0]
        self.assertIsNotNone(item['due_date'])
        self.assertTrue(item['overdue'])

    def test_a_completed_feasibility_stops_the_reminder(self):
        self.sv.kseb_feasibility_complete = True
        self.sv.save(update_fields=['kseb_feasibility_complete'])
        self.assertEqual(self.pending(self.bde)['count'], 0)

    def test_a_lead_not_yet_on_the_queue_is_not_counted(self):
        self.sv.po_signed_date = None
        self.sv.save(update_fields=['po_signed_date'])
        self.assertEqual(self.pending(self.bde)['count'], 0)

    def test_another_bde_is_not_nagged_about_it(self):
        self.assertEqual(self.pending(self.other)['count'], 0)

    def test_nobody_but_a_bde_is_nagged(self):
        """The popup is the BDE's task; other roles must never see it."""
        for actor in (self.caller, self.admin):
            self.assertEqual(self.pending(actor)['count'], 0, actor.role)

    def test_a_trashed_lead_drops_off(self):
        self.lead.is_trashed = True
        self.lead.save(update_fields=['is_trashed'])
        self.assertEqual(self.pending(self.bde)['count'], 0)

    def test_a_lead_pushed_to_documentation_also_counts(self):
        """Those join the queue without a PO date, and were already on it."""
        pushed = Lead.objects.create(first_name='F', last_name='Pushed', phone='9995500002',
                                     status='new', bde=self.bde, pushed_to_documentation=True)
        SiteVisit.objects.create(lead=pushed)
        names = {i['name'] for i in self.pending(self.bde)['items']}
        self.assertIn('F Pushed', names)


class EmptyTrashTests(TestCase):
    """Emptying the Trash is irreversible and workspace-wide — super admin only."""

    def setUp(self):
        self.superadmin = mk('et_super', 'superadmin')
        self.superadmin.is_superuser = True
        self.superadmin.is_staff = True
        self.superadmin.save()
        self.admin = mk('et_admin', 'admin')
        self.admin.is_staff = True
        self.admin.save()
        self.caller = mk('et_caller', 'tele_caller')
        self.bde = mk('et_bde', 'bde')

        self.trashed = [
            Lead.objects.create(first_name='T', last_name=f'Gone{n}', phone=f'999600000{n}',
                                status='new', assigned_to=self.caller, is_trashed=True,
                                trashed_at=timezone.now())
            for n in range(3)
        ]
        self.kept = Lead.objects.create(first_name='T', last_name='Kept', phone='9996000099',
                                        status='new', assigned_to=self.caller)

    def empty(self, actor):
        return self.client.delete('/api/leads/empty-trash/',
                                  HTTP_AUTHORIZATION=token_for(actor))

    def test_a_super_admin_can_empty_it(self):
        r = self.empty(self.superadmin)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['deleted'], 3)
        self.assertEqual(Lead.objects.filter(is_trashed=True).count(), 0)

    def test_active_leads_are_untouched(self):
        self.empty(self.superadmin)
        self.kept.refresh_from_db()
        self.assertFalse(self.kept.is_trashed)
        self.assertTrue(Lead.objects.filter(pk=self.kept.pk).exists())

    def test_an_admin_cannot(self):
        """Deleting the workspace's trash outright is above an admin."""
        r = self.empty(self.admin)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Lead.objects.filter(is_trashed=True).count(), 3)

    def test_other_roles_cannot_either(self):
        for actor in (self.caller, self.bde):
            self.assertEqual(self.empty(actor).status_code, 403, actor.role)
        self.assertEqual(Lead.objects.filter(is_trashed=True).count(), 3)

    def test_emptying_an_empty_trash_is_harmless(self):
        self.empty(self.superadmin)
        r = self.empty(self.superadmin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['deleted'], 0)

    def test_it_clears_the_whole_workspace_not_just_what_the_caller_owns(self):
        """Trash from another user's leads goes too — it is a workspace action."""
        other = mk('et_other', 'tele_caller')
        Lead.objects.create(first_name='T', last_name='Theirs', phone='9996000050',
                            status='new', assigned_to=other, is_trashed=True,
                            trashed_at=timezone.now())
        r = self.empty(self.superadmin)
        self.assertEqual(r.json()['deleted'], 4)
        self.assertEqual(Lead.objects.filter(is_trashed=True).count(), 0)


class ActivityTimelineTests(TestCase):
    """The whole of a customer's history, for whoever picks the file up."""

    def setUp(self):
        from .models import ActivityLog
        self.caller = mk('at_caller', 'tele_caller')
        self.docstaff = mk('at_doc', 'documentation_staff')
        self.accounts = mk('at_acc', 'accounts_staff')
        self.purchase = mk('at_pur', 'purchase_staff')
        self.project = mk('at_proj', 'project_manager')
        self.liasoning = mk('at_lia', 'liasoning_officer')
        self.docman = mk('at_docman', 'documentation_manager')
        self.bde = mk('at_bde', 'bde')
        self.stranger = mk('at_stranger', 'bde')

        self.lead = Lead.objects.create(first_name='Sidharth', last_name='V S',
                                        phone='9997700001', status='new',
                                        assigned_to=self.caller, bde=self.bde)
        ActivityLog.objects.create(activity_type='lead_created', lead=self.lead,
                                   actor=self.caller, description='New lead added: Sidharth')
        ActivityLog.objects.create(activity_type='lead_status_change', lead=self.lead,
                                   actor=self.caller, description='Sidharth: New → Converted')
        ActivityLog.objects.create(activity_type='note_added', lead=self.lead, actor=None,
                                   description='Auto-assigned to documentation: docstaff',
                                   extra={'auto_generated': True})

    def timeline(self, actor):
        return self.client.get(f'/api/leads/{self.lead.id}/activity-timeline/',
                               HTTP_AUTHORIZATION=token_for(actor))

    def test_every_downstream_role_can_open_it(self):
        for actor in (self.docstaff, self.docman, self.accounts,
                      self.purchase, self.project, self.liasoning):
            r = self.timeline(actor)
            self.assertEqual(r.status_code, 200, f'{actor.role}: {r.content[:120]}')
            self.assertEqual(r.json()['count'], 3, actor.role)

    def test_it_names_the_customer(self):
        d = self.timeline(self.accounts).json()
        self.assertEqual(d['lead']['name'], 'Sidharth V S')
        self.assertEqual(d['lead']['phone'], '9997700001')

    def test_entries_are_newest_first(self):
        entries = self.timeline(self.accounts).json()['entries']
        stamps = [e['timestamp'] for e in entries]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_system_entries_are_marked_auto_generated(self):
        entries = {e['description']: e for e in self.timeline(self.accounts).json()['entries']}
        self.assertTrue(entries['Auto-assigned to documentation: docstaff']['auto_generated'])
        self.assertFalse(entries['New lead added: Sidharth']['auto_generated'])

    def test_a_human_entry_names_its_actor(self):
        entries = {e['description']: e for e in self.timeline(self.accounts).json()['entries']}
        self.assertEqual(entries['New lead added: Sidharth']['actor'], 'at_caller')

    def test_the_people_working_the_lead_can_open_it_too(self):
        for actor in (self.caller, self.bde):
            self.assertEqual(self.timeline(actor).status_code, 200, actor.role)

    def test_a_bde_who_does_not_hold_the_lead_cannot(self):
        """Access rides on the lead's own scoping — no separate rule to drift."""
        self.assertEqual(self.timeline(self.stranger).status_code, 404)

    def test_a_lead_with_no_history_returns_an_empty_list(self):
        bare = Lead.objects.create(first_name='No', last_name='History',
                                   phone='9997700002', status='new', assigned_to=self.caller)
        r = self.client.get(f'/api/leads/{bare.id}/activity-timeline/',
                            HTTP_AUTHORIZATION=token_for(self.accounts))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['count'], 0)
        self.assertEqual(r.json()['entries'], [])


class DeletedLeadModuleCleanupTests(TestCase):
    """Trashing a lead leaves its rows in the modules it had reached; a super
    admin clears those out module by module."""

    def setUp(self):
        from .models import PaymentVerification
        # Super admin: the cleanup destroys another department's record, so it
        # sits above the admin tier. See can_cleanup_deleted_lead.
        self.admin = mk('dc_admin', 'superadmin')
        self.accounts = mk('dc_acc', 'accounts_staff')
        self.caller = mk('dc_caller', 'tele_caller')

        self.lead = Lead.objects.create(
            first_name='Sidharth1', last_name='', phone='9998800001', status='new',
            assigned_to=self.caller, pushed_to_accounts=True,
            pushed_to_accounts_at=timezone.now(), accounts_staff=self.accounts)
        PaymentVerification.objects.create(lead=self.lead)

    def trash(self):
        self.lead.is_trashed = True
        self.lead.trashed_at = timezone.now()
        self.lead.save(update_fields=['is_trashed', 'trashed_at'])

    def remove(self, actor, module='accounts'):
        return self.client.delete(
            f'/api/leads/{self.lead.id}/remove-from-module/?module={module}',
            HTTP_AUTHORIZATION=token_for(actor))

    def listed(self, actor):
        r = self.client.get('/api/leads/accounts/', HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    # ── the symptom ──
    def test_a_deleted_lead_is_flagged_in_the_module_list(self):
        """It still lists — the flag is what tells the screen it is a dead row."""
        self.trash()
        row = next(r for r in self.listed(self.admin) if r['id'] == self.lead.id)
        self.assertTrue(row['lead_deleted'])
        self.assertTrue(row['can_cleanup'])

    def test_a_live_lead_is_not_flagged(self):
        row = next(r for r in self.listed(self.admin) if r['id'] == self.lead.id)
        self.assertFalse(row['lead_deleted'])
        self.assertFalse(row['can_cleanup'])

    def test_only_an_admin_is_offered_the_cleanup(self):
        self.trash()
        row = next(r for r in self.listed(self.accounts) if r['id'] == self.lead.id)
        self.assertTrue(row['lead_deleted'])
        self.assertFalse(row['can_cleanup'])

    # ── the cleanup ──
    def test_an_admin_removes_it_from_the_module(self):
        from .models import PaymentVerification
        self.trash()
        r = self.remove(self.admin)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.pushed_to_accounts)
        self.assertIsNone(self.lead.accounts_staff_id)
        self.assertFalse(PaymentVerification.objects.filter(lead=self.lead).exists())
        self.assertNotIn(self.lead.id, [x['id'] for x in self.listed(self.admin)])

    def test_the_lead_itself_survives_in_the_trash(self):
        """Only the module residue goes — the lead can still be restored."""
        self.trash()
        self.remove(self.admin)
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.is_trashed)

    def test_a_live_lead_cannot_be_pulled_out_of_a_module(self):
        """The guard that stops this becoming a way to disrupt live work."""
        r = self.remove(self.admin)
        self.assertEqual(r.status_code, 400)
        self.assertIn('still active', r.json()['error'])
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_accounts)

    def test_non_admins_are_refused(self):
        self.trash()
        for actor in (self.accounts, self.caller):
            self.assertEqual(self.remove(actor).status_code, 403, actor.role)
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_accounts)

    def test_an_unknown_module_is_refused(self):
        self.trash()
        r = self.remove(self.admin, module='nowhere')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Unknown module', r.json()['error'])

    def test_a_module_the_lead_never_reached_says_so(self):
        self.trash()
        r = self.remove(self.admin, module='project')
        self.assertEqual(r.status_code, 404)

    def test_the_cleanup_is_recorded_on_the_timeline(self):
        from .models import ActivityLog
        self.trash()
        self.remove(self.admin)
        self.assertTrue(ActivityLog.objects.filter(
            lead=self.lead, description__icontains='removed from accounts').exists())


class DeletedLeadsAreOutOfTheFiguresTests(TestCase):
    """A lead in the Trash is gone as far as the customer is concerned, so its
    value must not count towards won revenue or any other reported figure."""

    def setUp(self):
        from decimal import Decimal
        self.admin = mk('df_admin', 'admin')
        self.admin.is_staff = True
        self.admin.save()
        self.caller = mk('df_caller', 'tele_caller')

        self.live = Lead.objects.create(first_name='D', last_name='Live', phone='9993300001',
                                        status='converted', assigned_to=self.caller,
                                        value=Decimal('100000'))
        self.deleted = Lead.objects.create(first_name='D', last_name='Deleted',
                                           phone='9993300002', status='converted',
                                           assigned_to=self.caller, value=Decimal('900000'),
                                           is_trashed=True, trashed_at=timezone.now())

    def converted(self, actor):
        r = self.client.get('/api/converted-analytics/', HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def stats(self, actor):
        r = self.client.get('/api/dashboard-stats/', HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def test_won_revenue_leaves_out_the_deleted_deal(self):
        d = self.converted(self.admin)
        self.assertEqual(float(d['total_revenue']), 100000.0)

    def test_the_conversion_count_leaves_it_out_too(self):
        self.assertEqual(self.converted(self.admin)['total_conversions'], 1)

    def test_the_dashboard_agrees(self):
        d = self.stats(self.admin)
        self.assertEqual(d['total_leads'], 1)
        self.assertEqual(float(d['total_revenue']), 100000.0)

    def test_restoring_it_brings_the_money_back(self):
        self.deleted.is_trashed = False
        self.deleted.trashed_at = None
        self.deleted.save(update_fields=['is_trashed', 'trashed_at'])
        self.assertEqual(float(self.converted(self.admin)['total_revenue']), 1000000.0)
        self.assertEqual(self.converted(self.admin)['total_conversions'], 2)

    def test_it_holds_for_a_plain_user_too(self):
        self.assertEqual(float(self.converted(self.caller)['total_revenue']), 100000.0)


class DeletedLeadFlaggedOnTheDocumentationTrackerTests(TestCase):
    """The admin-facing documentation tracker flags dead rows like the module
    queues do."""

    def setUp(self):
        # The cleanup button is a super admin's; see can_cleanup_deleted_lead.
        self.admin = mk('dt_admin', 'superadmin')
        self.caller = mk('dt_caller', 'tele_caller')
        self.lead = Lead.objects.create(first_name='Sidharth1', last_name='',
                                        phone='9993400001', status='new',
                                        assigned_to=self.caller,
                                        pushed_to_documentation=True,
                                        pushed_to_documentation_at=timezone.now())

    def rows(self, actor):
        r = self.client.get('/api/leads/documentation-overview/',
                            HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def test_a_live_lead_is_not_flagged(self):
        row = next(r for r in self.rows(self.admin) if r['id'] == self.lead.id)
        self.assertFalse(row['lead_deleted'])
        self.assertFalse(row['can_cleanup'])

    def test_a_deleted_lead_is_flagged_for_the_super_admin(self):
        self.lead.is_trashed = True
        self.lead.trashed_at = timezone.now()
        self.lead.save(update_fields=['is_trashed', 'trashed_at'])
        row = next(r for r in self.rows(self.admin) if r['id'] == self.lead.id)
        self.assertTrue(row['lead_deleted'])
        self.assertTrue(row['can_cleanup'])

    def test_a_non_admin_sees_the_flag_but_gets_no_button(self):
        self.lead.is_trashed = True
        self.lead.trashed_at = timezone.now()
        self.lead.save(update_fields=['is_trashed', 'trashed_at'])
        row = next(r for r in self.rows(self.caller) if r['id'] == self.lead.id)
        self.assertTrue(row['lead_deleted'])
        self.assertFalse(row['can_cleanup'])


class WarrantyAndFeasibilityCleanupTests(TestCase):
    """The same broom on the warranty and KSEB feasibility queues."""

    def setUp(self):
        from datetime import date
        from .models import SiteVisit, Warranty
        self.admin = mk('wf_admin', 'superadmin')
        self.caller = mk('wf_caller', 'tele_caller')
        self.bde = mk('wf_bde', 'bde')

        self.lead = Lead.objects.create(
            first_name='W', last_name='Gone', phone='9993500001', status='new',
            assigned_to=self.caller, bde=self.bde,
            pushed_to_warranty=True, pushed_to_warranty_at=timezone.now())
        Warranty.objects.create(lead=self.lead)
        self.sv = SiteVisit.objects.create(lead=self.lead, po_signed_date=date(2026, 7, 27),
                                           kseb_feasibility_taken='yes',
                                           kseb_feasibility_complete=True)
        self.lead.is_trashed = True
        self.lead.trashed_at = timezone.now()
        self.lead.save(update_fields=['is_trashed', 'trashed_at'])

    def remove(self, module, actor=None):
        return self.client.delete(
            f'/api/leads/{self.lead.id}/remove-from-module/?module={module}',
            HTTP_AUTHORIZATION=token_for(actor or self.admin))

    # ── warranty ──
    def test_warranty_rows_are_flagged(self):
        r = self.client.get('/api/leads/warranty/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        row = next(x for x in r.json() if x['id'] == self.lead.id)
        self.assertTrue(row['lead_deleted'])
        self.assertTrue(row['can_cleanup'])

    def test_warranty_data_can_be_cleared(self):
        from .models import Warranty
        r = self.remove('warranty')
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.pushed_to_warranty)
        self.assertFalse(Warranty.objects.filter(lead=self.lead).exists())

    # ── KSEB feasibility ──
    def test_feasibility_rows_are_flagged(self):
        r = self.client.get('/api/leads/bde-feasibility/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        row = next(x for x in r.json() if x['id'] == self.lead.id)
        self.assertTrue(row['lead_deleted'])
        self.assertTrue(row['can_cleanup'])

    def test_feasibility_data_can_be_cleared(self):
        r = self.remove('feasibility')
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.sv.refresh_from_db()
        self.assertIsNone(self.sv.po_signed_date)
        self.assertEqual(self.sv.kseb_feasibility_taken, '')
        self.assertFalse(self.sv.kseb_feasibility_complete)

    def test_clearing_feasibility_drops_it_from_the_queue(self):
        self.remove('feasibility')
        r = self.client.get('/api/leads/bde-feasibility/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertNotIn(self.lead.id, [x['id'] for x in r.json()])

    def test_a_lead_still_in_documentation_is_told_it_stays_listed(self):
        """The queue is 'PO signed OR in documentation', so the button would
        otherwise look like it did nothing."""
        self.lead.pushed_to_documentation = True
        self.lead.save(update_fields=['pushed_to_documentation'])
        r = self.remove('feasibility')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['still_listed'])
        self.assertIn('still in documentation', r.json()['message'])

    def test_feasibility_with_no_data_says_so(self):
        self.sv.po_signed_date = None
        self.sv.save(update_fields=['po_signed_date'])
        self.assertEqual(self.remove('feasibility').status_code, 404)

    # ── the guards still hold ──
    def test_non_admins_are_refused_on_both(self):
        for module in ('warranty', 'feasibility'):
            self.assertEqual(self.remove(module, self.caller).status_code, 403, module)

    def test_a_live_lead_is_refused_on_both(self):
        self.lead.is_trashed = False
        self.lead.save(update_fields=['is_trashed'])
        for module in ('warranty', 'feasibility'):
            r = self.remove(module)
            self.assertEqual(r.status_code, 400, module)
            self.assertIn('still active', r.json()['error'])


class LeaderboardAndPerformanceIgnoreDeletedTests(TestCase):
    """A deleted deal is not a closed sale, and a BDE's handed-over leads are
    still theirs — both boards have to agree with the Leads page."""

    def setUp(self):
        from decimal import Decimal
        self.bde = mk('lb_bde', 'bde')
        self.caller = mk('lb_caller', 'tele_caller')
        self.admin = mk('lb_admin', 'admin')
        self.admin.is_staff = True
        self.admin.save()

        # Owned by the tele caller, closed by the BDE — the normal shape.
        self.won = Lead.objects.create(first_name='L', last_name='Won', phone='9993600001',
                                       status='converted', assigned_to=self.caller,
                                       bde=self.bde, value=Decimal('100000'))
        self.deleted = Lead.objects.create(first_name='L', last_name='Deleted',
                                           phone='9993600002', status='converted',
                                           assigned_to=self.caller, bde=self.bde,
                                           value=Decimal('900000'),
                                           is_trashed=True, trashed_at=timezone.now())

    def board(self, actor=None):
        r = self.client.get('/api/leaderboard/?period=all_time',
                            HTTP_AUTHORIZATION=token_for(actor or self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return {row['name']: row for row in r.json()['leaderboard']}

    def performance(self, actor):
        r = self.client.get('/api/ai-manager/my-performance/',
                            HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()['lead_stats']

    # ── leaderboard ──
    def test_a_deleted_deal_is_off_the_board(self):
        row = self.board()['lb_bde']
        self.assertEqual(row['closed_sales'], 1)
        self.assertEqual(float(row['revenue']), 100000.0)

    def test_restoring_it_puts_it_back(self):
        self.deleted.is_trashed = False
        self.deleted.save(update_fields=['is_trashed'])
        row = self.board()['lb_bde']
        self.assertEqual(row['closed_sales'], 2)
        self.assertEqual(float(row['revenue']), 1000000.0)

    # ── my performance ──
    def test_a_bde_sees_the_leads_handed_to_them(self):
        """They are owned by the tele caller, so scoping on the owner lost them."""
        self.assertEqual(self.performance(self.bde)['total_leads'], 1)

    def test_my_performance_leaves_the_deleted_lead_out(self):
        d = self.performance(self.bde)
        self.assertEqual(d['total_leads'], 1)
        self.assertEqual(d['status_breakdown'].get('converted'), 1)

    def test_the_tele_caller_still_sees_their_own(self):
        self.assertEqual(self.performance(self.caller)['total_leads'], 1)

    def test_the_two_boards_agree_on_the_bde(self):
        board = self.board()['lb_bde']['closed_sales']
        perf = self.performance(self.bde)['status_breakdown'].get('converted', 0)
        self.assertEqual(board, perf)


class PurchaseCompletionConditionsTests(TestCase):
    """Purchase & logistics signs off only when everything has arrived and
    nothing is outstanding — unless an admin overrides it."""

    def setUp(self):
        from .models import PurchaseLogistics
        self.admin = mk('pc_admin', 'admin')
        self.admin.is_staff = True
        self.admin.save()
        self.staff = mk('pc_staff', 'purchase_staff')
        self.lead = Lead.objects.create(first_name='P', last_name='Cond', phone='9993700001',
                                        status='converted', pushed_to_purchase=True,
                                        pushed_to_purchase_at=timezone.now(),
                                        purchase_staff=self.staff)
        self.pl = PurchaseLogistics.objects.create(lead=self.lead)

    def patch(self, payload, actor=None):
        return self.client.patch(f'/api/leads/{self.lead.id}/purchase-logistics/',
                                 data=payload, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor or self.staff))

    def complete(self, actor=None, override=None):
        body = {} if override is None else {'override': override}
        return self.client.post(f'/api/leads/{self.lead.id}/complete-purchase-logistics/',
                                data=body, content_type='application/json',
                                HTTP_AUTHORIZATION=token_for(actor or self.staff))

    def satisfy(self):
        self.pl.panel_delivered = 'delivered'
        self.pl.structure_material = 'delivered'
        self.pl.bom = 'delivered'
        self.pl.pending_item = 'no'
        self.pl.save()

    # ── the new field ──
    def test_panel_delivered_round_trips(self):
        r = self.patch({'panel_delivered': 'delivered'})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['panel_delivered'], 'delivered')

    def test_only_the_two_delivery_values_are_accepted(self):
        self.assertEqual(self.patch({'panel_delivered': 'maybe'}).status_code, 400)

    # ── the gate ──
    def test_nothing_answered_lists_all_four_conditions(self):
        r = self.complete()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(r.json()['unmet']), 4)

    def test_answering_is_not_enough_it_has_to_be_delivered(self):
        """The old rule only checked the fields were filled in."""
        self.pl.panel_delivered = 'not_delivered'
        self.pl.structure_material = 'delivered'
        self.pl.bom = 'delivered'
        self.pl.pending_item = 'no'
        self.pl.save()
        r = self.complete()
        self.assertEqual(r.status_code, 400)
        self.assertEqual([u['field'] for u in r.json()['unmet']], ['panel_delivered'])

    def test_a_pending_item_blocks_it(self):
        self.satisfy()
        self.pl.pending_item = 'yes'
        self.pl.save()
        r = self.complete()
        self.assertEqual(r.status_code, 400)
        self.assertEqual([u['field'] for u in r.json()['unmet']], ['pending_item'])

    def test_all_four_met_completes(self):
        self.satisfy()
        r = self.complete()
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.pl.refresh_from_db()
        self.assertTrue(self.pl.is_complete)
        self.assertFalse(self.pl.completed_with_override)

    # ── the override ──
    def test_purchase_staff_cannot_override(self):
        r = self.complete(override=True)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['can_override'])
        self.pl.refresh_from_db()
        self.assertFalse(self.pl.is_complete)

    def test_an_admin_can_override(self):
        r = self.complete(self.admin, override=True)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.pl.refresh_from_db()
        self.assertTrue(self.pl.is_complete)
        self.assertTrue(self.pl.completed_with_override)
        self.assertIn('Panel delivered', self.pl.override_reason)

    def test_an_admin_without_ticking_override_is_still_blocked(self):
        r = self.complete(self.admin)
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()['can_override'])

    def test_the_override_is_recorded_on_the_timeline(self):
        from .models import ActivityLog
        self.complete(self.admin, override=True)
        self.assertTrue(ActivityLog.objects.filter(
            lead=self.lead, description__icontains='overridden').exists())

    # ── editing afterwards ──
    def test_purchase_staff_cannot_edit_once_complete(self):
        self.satisfy()
        self.complete()
        r = self.patch({'remark': 'late note'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('locked', r.json()['error'])

    def test_an_admin_can_still_edit_after_completion(self):
        """They signed it off, sometimes on an override, so they can correct it."""
        self.complete(self.admin, override=True)
        r = self.patch({'remark': 'panel arrived later'}, actor=self.admin)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.pl.refresh_from_db()
        self.assertEqual(self.pl.remark, 'panel arrived later')

    def test_the_override_flag_cannot_be_set_by_a_plain_patch(self):
        r = self.patch({'completed_with_override': True})
        self.assertEqual(r.status_code, 200)
        self.pl.refresh_from_db()
        self.assertFalse(self.pl.completed_with_override)


class LiasoningAnnexure3Tests(TestCase):
    """Liasoning is Annexure 3 only — feasibility belongs to the KSEB Feasibility
    module, so nothing here waits on it."""

    def setUp(self):
        self.officer = mk('lia_officer', 'liasoning_officer')
        self.lead = Lead.objects.create(first_name='Siddharth', last_name='V.S',
                                        phone='9954471855', status='converted',
                                        pushed_to_liasoning=True,
                                        pushed_to_liasoning_at=timezone.now())

    def patch(self, payload):
        return self.client.patch(f'/api/leads/{self.lead.id}/liasoning-record/',
                                 data=payload, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(self.officer))

    def test_annexure3_saves_without_any_feasibility_sign_off(self):
        r = self.patch({'annexure3_completed': True, 'annexure3_remark': 'submitted'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        rec = LiasoningService.objects.get(lead=self.lead)
        self.assertTrue(rec.annexure3_completed)
        self.assertFalse(rec.feasibility_completed)      # never touched here

    def test_it_still_syncs_through_to_documentation_stage_2(self):
        self.patch({'annexure3_completed': True, 'annexure3_remark': 'submitted'})
        s2 = DocumentationStage2.objects.get(lead=self.lead)
        self.assertTrue(s2.annexure3_completed)
        self.assertEqual(s2.annexure3_remark, 'submitted')
        # Discom approval is Stage 2's own — Annexure 3 does not carry it.
        self.assertEqual(s2.discom_approval, 'pending')


class DiscomApprovalDirectionTests(TestCase):
    """Documentation Stage 2 owns the discom approval; Liasoning displays it."""

    def setUp(self):
        self.docstaff = mk('disc_doc', 'documentation_staff')
        self.officer = mk('disc_officer', 'liasoning_officer')
        self.lead = Lead.objects.create(first_name='Rahul', last_name='aa', phone='9849394940',
                                        status='converted',
                                        pushed_to_doc_stage2=True, pushed_to_doc_stage2_at=timezone.now(),
                                        pushed_to_liasoning=True, pushed_to_liasoning_at=timezone.now(),
                                        # Stage 2 staff only work their assigned leads.
                                        doc_stage2_staff=self.docstaff)

    def stage2(self, payload, who=None):
        return self.client.patch(f'/api/leads/{self.lead.id}/documentation-stage2-record/',
                                 data=payload, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(who or self.docstaff))

    def liasoning(self, payload):
        return self.client.patch(f'/api/leads/{self.lead.id}/liasoning-record/',
                                 data=payload, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(self.officer))

    def test_stage2_sets_the_approval_and_it_reaches_liasoning(self):
        r = self.stage2({'discom_approval': 'yes'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(LiasoningService.objects.get(lead=self.lead).discom_approval, 'yes')

    def test_liasoning_cannot_change_it(self):
        self.stage2({'discom_approval': 'yes'})
        r = self.liasoning({'discom_approval': 'no', 'annexure3_remark': 'filed'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        rec = LiasoningService.objects.get(lead=self.lead)
        self.assertEqual(rec.discom_approval, 'yes')     # ignored, not applied
        self.assertEqual(rec.annexure3_remark, 'filed')  # the rest still saves
        # And nothing leaked back the other way.
        self.assertEqual(DocumentationStage2.objects.get(lead=self.lead).discom_approval, 'yes')

    def test_an_approval_still_lands_after_stage2_is_signed_off(self):
        rec, _ = DocumentationStage2.objects.get_or_create(lead=self.lead)
        rec.is_complete = True
        rec.save(update_fields=['is_complete'])
        # Only the approval gets through the lock.
        self.assertEqual(self.stage2({'mnre_remark': 'late edit'}).status_code, 400)
        self.assertEqual(self.stage2({'discom_approval': 'yes'}).status_code, 200)
        self.assertEqual(LiasoningService.objects.get(lead=self.lead).discom_approval, 'yes')

    def test_it_reaches_a_locked_liasoning_record_too(self):
        lia, _ = LiasoningService.objects.get_or_create(lead=self.lead)
        lia.is_complete = True
        lia.save(update_fields=['is_complete'])
        self.stage2({'discom_approval': 'yes'})
        lia.refresh_from_db()
        self.assertEqual(lia.discom_approval, 'yes')

    def test_approval_hands_the_customer_to_warranty(self):
        self.stage2({'discom_approval': 'yes'})
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_warranty)


class DiscomFollowupBelongsToLiasoningTests(TestCase):
    """The follow-up queue moved to Liasoning — the officer can work it without
    holding documentation access."""

    def setUp(self):
        self.officer = mk('foll_officer', 'liasoning_officer')
        self.docstaff = mk('foll_doc', 'documentation_staff')
        self.lead = Lead.objects.create(first_name='new', last_name='test', phone='7673873828',
                                        status='converted', pushed_to_doc_stage2=True,
                                        pushed_to_doc_stage2_at=timezone.now() - timedelta(days=10))

    def test_the_officer_can_read_the_queue(self):
        r = self.client.get('/api/leads/discom-followup/',
                            HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual([x['id'] for x in r.json()], [self.lead.id])

    def test_the_officer_can_tick_their_own_visit(self):
        r = self.client.patch(f'/api/leads/{self.lead.id}/discom-followup-sent/',
                              data={'sent_to_liasoning': True}, content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(DocumentationStage2.objects.get(lead=self.lead).sent_to_liasoning)

    def test_documentation_staff_no_longer_hold_the_queue(self):
        r = self.client.get('/api/leads/discom-followup/',
                            HTTP_AUTHORIZATION=token_for(self.docstaff))
        self.assertEqual(r.status_code, 403)

    def test_an_approved_customer_drops_off_the_queue(self):
        rec, _ = DocumentationStage2.objects.get_or_create(lead=self.lead)
        rec.discom_approval = 'yes'
        rec.save(update_fields=['discom_approval'])
        r = self.client.get('/api/leads/discom-followup/',
                            HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.json(), [])


class WarrantySendTests(TestCase):
    """The warranty goes out over the configured integrations, not the staff
    member's own WhatsApp or mail client."""

    def setUp(self):
        self.docstaff = mk('war_doc', 'documentation_staff')
        self.lead = Lead.objects.create(first_name='mini', last_name='A', phone='9526396823',
                                        email='mini@example.com', status='converted',
                                        pushed_to_warranty=True)
        self.rec, _ = Warranty.objects.get_or_create(lead=self.lead)

    def attach(self, name):
        return WarrantyDocument.objects.create(
            warranty=self.rec, doc_type='warranty',
            file=SimpleUploadedFile(name, b'%PDF-1.4 warranty', content_type='application/pdf'))

    def send(self, payload):
        return self.client.post(f'/api/leads/{self.lead.id}/send-warranty/', data=payload,
                                HTTP_AUTHORIZATION=token_for(self.docstaff))

    def test_it_refuses_before_the_certificate_exists(self):
        r = self.send({'channels': 'email'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('Generate the certificate', r.json()['error'])

    def test_email_goes_through_the_configured_account_with_the_pdf_attached(self):
        self.attach('Warranty_Certificate_mini_A.pdf')
        with patch('messaging.email.send_and_log') as send:
            send.return_value = SimpleNamespace(status='sent', error='')
            r = self.send({'channels': 'email'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        kwargs = send.call_args[1]
        self.assertEqual(kwargs['to'], ['mini@example.com'])
        self.assertEqual(kwargs['kind'], 'warranty')
        self.assertEqual(kwargs['attachments'][0][2], 'application/pdf')
        self.assertEqual(kwargs['lead'], self.lead)

    def test_whatsapp_sends_the_document_by_link(self):
        self.attach('Warranty_Certificate_mini_A.pdf')
        with patch('messaging.whatsapp.send_document') as send:
            r = self.send({'channels': 'whatsapp'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(send.call_args[1]['to'], '9526396823')
        self.assertIn('.pdf', send.call_args[1]['link'])

    def test_a_delivered_warranty_marks_itself_sent(self):
        self.attach('Warranty_Certificate_mini_A.pdf')
        self.assertFalse(self.rec.sent)
        with patch('messaging.email.send_and_log') as send:
            send.return_value = SimpleNamespace(status='sent', error='')
            self.send({'channels': 'email'})
        self.rec.refresh_from_db()
        self.assertTrue(self.rec.sent)

    def test_the_certificate_wins_over_later_attachments(self):
        self.attach('Warranty_Certificate_mini_A.pdf')
        self.attach('some_other_scan.pdf')
        with patch('messaging.whatsapp.send_document') as send:
            self.send({'channels': 'whatsapp'})
        self.assertIn('Warranty_Certificate', send.call_args[1]['filename'])

    def test_a_failed_send_is_reported_not_swallowed(self):
        self.attach('Warranty_Certificate_mini_A.pdf')
        with patch('messaging.email.send_and_log') as send:
            send.return_value = SimpleNamespace(status='failed', error='SMTP refused')
            r = self.send({'channels': 'email'})
        self.assertEqual(r.status_code, 502)
        self.assertIn('SMTP refused', r.json()['error'])
        self.rec.refresh_from_db()
        self.assertFalse(self.rec.sent)


class PaymentHistoryTests(TestCase):
    """Payment History lists every payment, including the first one — which is
    recorded on the verification form, not as a balance payment."""

    def setUp(self):
        self.staff = mk('ph_acct', 'accounts_staff')
        # Accounts staff may only collect on leads assigned to them.
        self.lead = Lead.objects.create(first_name='mini', last_name='A', phone='9526396820',
                                        status='converted', value=Decimal('330000'),
                                        pushed_to_accounts=True, accounts_staff=self.staff)
        self.pv = PaymentVerification.objects.create(
            lead=self.lead, amount_received=Decimal('140000'), payment_mode='cash',
            on_account_of='3 KW LOAN AMOUNT', is_complete=True, completed_by=self.staff)
        from leads.receipts import issue_receipt
        issue_receipt(self.lead, Decimal('140000'), on_account_of='3 KW LOAN AMOUNT',
                      payment_mode='Cash', is_initial=True, created_by=self.staff)

    def ledger(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/balance-payments/',
                            HTTP_AUTHORIZATION=token_for(self.staff))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def add(self, amount, on_account_of):
        return self.client.post(f'/api/leads/{self.lead.id}/balance-payments/',
                                data={'amount': str(amount), 'payment_mode': 'upi',
                                      'utr_details': '2323363', 'on_account_of': on_account_of},
                                content_type='application/json',
                                HTTP_AUTHORIZATION=token_for(self.staff))

    def test_the_first_payment_appears_even_with_no_installments_yet(self):
        rows = self.ledger()['payments']
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['is_initial'])
        self.assertEqual(Decimal(rows[0]['amount']), Decimal('140000'))
        self.assertEqual(rows[0]['on_account_of'], '3 KW LOAN AMOUNT')
        self.assertIsNotNone(rows[0]['receipt_id'])     # its receipt is downloadable

    def test_the_history_adds_up_to_the_received_figure(self):
        self.add(Decimal('130000'), 'DOWN PAYMENT')
        self.add(Decimal('60000'), 'SECOND PAYMENT')
        body = self.ledger()
        total = sum(Decimal(p['amount']) for p in body['payments'])
        self.assertEqual(total, Decimal(body['amount_received']))
        self.assertEqual(total, Decimal('330000'))
        self.assertEqual(len(body['payments']), 3)

    def test_the_first_payment_leads_the_list(self):
        self.add(Decimal('130000'), 'DOWN PAYMENT')
        rows = self.ledger()['payments']
        self.assertTrue(rows[0]['is_initial'])
        self.assertFalse(rows[1].get('is_initial'))
        self.assertEqual(rows[1]['on_account_of'], 'DOWN PAYMENT')

    def test_a_lead_whose_first_payment_was_nothing_shows_only_installments(self):
        """A zero-rupee verification is not a payment, so it earns no row."""
        self.lead.receipt_vouchers.all().delete()
        self.pv.amount_received = Decimal('0')
        self.pv.save(update_fields=['amount_received'])
        self.add(Decimal('50000'), 'DOWN PAYMENT')
        rows = self.ledger()['payments']
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].get('is_initial'))


class AccountsManagerTests(TestCase):
    """The accounts manager runs the accounts queue and hands leads to their
    staff — without inheriting company-wide powers."""

    def setUp(self):
        self.manager = mk('am_manager', 'accounts_manager')
        self.staff_a = mk('am_staff_a', 'accounts_staff')
        self.staff_b = mk('am_staff_b', 'accounts_staff')
        self.lead = Lead.objects.create(first_name='mini', last_name='A', phone='9526396821',
                                        status='converted', value=Decimal('330000'),
                                        pushed_to_accounts=True, accounts_staff=self.staff_a)

    def assign(self, staff, who=None):
        return self.client.post(f'/api/leads/{self.lead.id}/assign-accounts/',
                                data={'staff': staff.id if staff else None},
                                content_type='application/json',
                                HTTP_AUTHORIZATION=token_for(who or self.manager))

    def test_the_manager_assigns_a_lead_to_accounts_staff(self):
        r = self.assign(self.staff_b)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.accounts_staff_id, self.staff_b.id)

    def test_the_manager_can_unassign(self):
        self.assertEqual(self.assign(None).status_code, 200)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.accounts_staff_id)

    def test_accounts_staff_still_cannot_assign(self):
        r = self.assign(self.staff_b, who=self.staff_a)
        self.assertEqual(r.status_code, 403)

    def test_the_manager_sees_the_whole_queue_not_just_their_own(self):
        Lead.objects.create(first_name='other', phone='9000000001', status='converted',
                            pushed_to_accounts=True, accounts_staff=self.staff_b)
        r = self.client.get('/api/leads/accounts/', HTTP_AUTHORIZATION=token_for(self.manager))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(len(r.json()), 2)
        # A staff member sees only their own.
        r = self.client.get('/api/leads/accounts/', HTTP_AUTHORIZATION=token_for(self.staff_a))
        self.assertEqual([x['id'] for x in r.json()], [self.lead.id])

    def test_the_manager_may_edit_any_lead_in_accounts(self):
        from .access import can_edit_payment_verification
        self.assertTrue(can_edit_payment_verification(self.manager, self.lead))
        # ...while staff are held to their own assignments.
        self.assertTrue(can_edit_payment_verification(self.staff_a, self.lead))
        self.assertFalse(can_edit_payment_verification(self.staff_b, self.lead))

    def test_it_does_not_inherit_powers_over_other_desks(self):
        """Unlike the documentation manager, it carries no company-wide flag."""
        self.assertFalse(self.manager.is_staff)
        self.assertFalse(self.manager.is_general_manager)
        for url in ('/api/leads/documentation/', '/api/leads/purchase/', '/api/leads/project/'):
            r = self.client.get(url, HTTP_AUTHORIZATION=token_for(self.manager))
            self.assertEqual(r.status_code, 403, f'{url} should be closed to the accounts manager')

    def test_an_admin_may_create_one_but_the_manager_may_not_create_an_admin(self):
        from users.models import role_rank
        self.assertEqual(role_rank('accounts_manager'), role_rank('documentation_manager'))
        self.assertLess(role_rank('accounts_manager'), role_rank('admin'))
        self.assertGreater(role_rank('accounts_manager'), role_rank('accounts_staff'))


class LandTaxFlowsFromTheSiteVisitTests(TestCase):
    """Land tax is captured once on the site visit and inherited by the stages
    that need it — including Documentation Stage 1's loan paperwork, which a
    customer reaches whether or not they are also changing the name."""

    def setUp(self):
        from .models import DocumentationStage1, SiteVisit
        self.bde = mk('lt_bde', 'bde')
        self.doc = mk('lt_doc', 'documentation_staff')
        self.lead = Lead.objects.create(first_name='L', last_name='Tax', phone='9994200001',
                                        status='converted', bde=self.bde,
                                        pushed_to_documentation=True, documentation_staff=self.doc)
        # A loan customer with no name change — the case the old form missed.
        self.sv = SiteVisit.objects.create(lead=self.lead, loan='yes', name_change='no')
        self.stage1 = DocumentationStage1.objects.create(lead=self.lead)

    def upload(self):
        from .models import LeadDocument
        return LeadDocument.objects.create(lead=self.lead, kind='land_tax',
                                           file='lead_documents/land_tax.pdf')

    def slots_holding(self, payload, kind):
        return {d['doc_type'] for d in payload if d.get('kind') == kind}

    def test_it_reaches_the_stage_1_loan_slot(self):
        self.upload()
        r = self.client.get(f'/api/leads/{self.lead.id}/documentation-stage1/',
                            HTTP_AUTHORIZATION=token_for(self.doc))
        self.assertEqual(r.status_code, 200, r.content[:300])
        slots = self.slots_holding(r.json()['documents'], 'land_tax')
        self.assertIn('loan_land_tax', slots)

    def test_it_shows_on_the_site_visit_that_captured_it(self):
        self.upload()
        r = self.client.get(f'/api/leads/{self.lead.id}/site-visit/',
                            HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertIn('land_tax', self.slots_holding(r.json()['documents'], 'land_tax'))

    def test_one_upload_is_not_copied_per_stage(self):
        """A single shared row backs every slot — correcting it corrects all."""
        from .models import LeadDocument
        self.upload()
        self.assertEqual(LeadDocument.objects.filter(lead=self.lead, kind='land_tax').count(), 1)

    def test_the_name_change_slot_still_sees_it(self):
        self.upload()
        r = self.client.get(f'/api/leads/{self.lead.id}/documentation-stage1/',
                            HTTP_AUTHORIZATION=token_for(self.doc))
        self.assertIn('nc_landtax', self.slots_holding(r.json()['documents'], 'land_tax'))


class ModuleCleanupIsSuperAdminOnlyTests(TestCase):
    """Clearing a deleted lead out of a module destroys another department's
    record of that customer, so it is a super admin's call alone."""

    def setUp(self):
        from .models import PaymentVerification
        self.lead = Lead.objects.create(first_name='Gone', last_name='Lead',
                                        phone='9993900001', status='new',
                                        pushed_to_accounts=True,
                                        pushed_to_accounts_at=timezone.now())
        PaymentVerification.objects.create(lead=self.lead)
        self.lead.is_trashed = True
        self.lead.trashed_at = timezone.now()
        self.lead.save(update_fields=['is_trashed', 'trashed_at'])

    def remove(self, actor):
        return self.client.delete(
            f'/api/leads/{self.lead.id}/remove-from-module/?module=accounts',
            HTTP_AUTHORIZATION=token_for(actor))

    def offered_to(self, actor):
        r = self.client.get('/api/leads/accounts/', HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:200])
        row = next((x for x in r.json() if x['id'] == self.lead.id), None)
        self.assertIsNotNone(row, 'the dead row should still be listed')
        return row['can_cleanup']

    def test_a_super_admin_may(self):
        boss = mk('cl_super', 'superadmin')
        self.assertTrue(self.offered_to(boss))
        self.assertEqual(self.remove(boss).status_code, 200)

    def test_an_admin_may_not(self):
        admin = mk('cl_admin', 'admin')
        self.assertFalse(self.offered_to(admin))
        self.assertEqual(self.remove(admin).status_code, 403)

    def test_a_documentation_manager_may_not(self):
        docman = mk('cl_docman', 'documentation_manager')
        self.assertEqual(self.remove(docman).status_code, 403)

    def test_no_other_tier_may(self):
        for role in ('coo', 'sales_manager', 'branch_manager', 'accounts_staff',
                     'documentation_staff', 'project_manager', 'tele_caller', 'bde'):
            self.assertEqual(self.remove(mk(f'cl_{role}', role)).status_code, 403, role)

    def test_the_row_survives_a_refused_attempt(self):
        from .models import PaymentVerification
        self.remove(mk('cl_admin2', 'admin'))
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_accounts)
        self.assertTrue(PaymentVerification.objects.filter(lead=self.lead).exists())


class WarrantySendLandsOnTheTimelineTests(TestCase):
    """Handing the warranty to the customer belongs on their timeline."""

    def setUp(self):
        self.docstaff = mk('wt_doc', 'documentation_staff')
        self.lead = Lead.objects.create(first_name='mini', last_name='A', phone='9526396824',
                                        email='mini@example.com', status='converted',
                                        pushed_to_warranty=True)
        self.rec, _ = Warranty.objects.get_or_create(lead=self.lead)
        WarrantyDocument.objects.create(
            warranty=self.rec, doc_type='warranty',
            file=SimpleUploadedFile('Warranty_Certificate_mini_A.pdf', b'%PDF-1.4 w',
                                    content_type='application/pdf'))

    def entries(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/activity-timeline/',
                            HTTP_AUTHORIZATION=token_for(self.docstaff))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return [e['description'] for e in r.json()['entries']]

    def test_an_emailed_warranty_is_recorded(self):
        with patch('messaging.email.send_and_log') as send:
            send.return_value = SimpleNamespace(status='sent', error='')
            self.client.post(f'/api/leads/{self.lead.id}/send-warranty/',
                             data={'channels': 'email'},
                             HTTP_AUTHORIZATION=token_for(self.docstaff))
        self.assertTrue(any('Warranty certificate sent by email to mini@example.com' in e
                            for e in self.entries()), self.entries())

    def test_a_whatsapp_warranty_is_recorded(self):
        with patch('messaging.whatsapp.send_document'):
            self.client.post(f'/api/leads/{self.lead.id}/send-warranty/',
                             data={'channels': 'whatsapp'},
                             HTTP_AUTHORIZATION=token_for(self.docstaff))
        self.assertTrue(any('WhatsApp to 9526396824' in e for e in self.entries()), self.entries())

    def test_a_failed_send_is_not_recorded(self):
        from .models import ActivityLog
        before = ActivityLog.objects.filter(lead=self.lead).count()
        with patch('messaging.email.send_and_log') as send:
            send.return_value = SimpleNamespace(status='failed', error='SMTP refused')
            r = self.client.post(f'/api/leads/{self.lead.id}/send-warranty/',
                                 data={'channels': 'email'},
                                 HTTP_AUTHORIZATION=token_for(self.docstaff))
        self.assertEqual(r.status_code, 502)
        self.assertEqual(ActivityLog.objects.filter(lead=self.lead).count(), before)


class DocStage2SubsidyPendingTests(TestCase):
    """Documentation Stage 2 splits into Pending / Done / Subsidy Pending: a
    signed-off customer whose subsidy has not been claimed is not finished."""

    def setUp(self):
        # The manager sees the whole queue; documentation staff see only the rows
        # assigned to them, which would hide this one.
        self.docstaff = mk('s2_docman', 'documentation_manager')
        self.lead = Lead.objects.create(first_name='Asha', last_name='Devi T',
                                        phone='9895271485', status='converted',
                                        pushed_to_doc_stage2=True,
                                        pushed_to_doc_stage2_at=timezone.now())
        self.rec, _ = DocumentationStage2.objects.get_or_create(lead=self.lead)

    def row(self):
        r = self.client.get('/api/leads/documentation-stage2/',
                            HTTP_AUTHORIZATION=token_for(self.docstaff))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return next(x for x in r.json() if x['id'] == self.lead.id)

    def set(self, **kw):
        for k, v in kw.items():
            setattr(self.rec, k, v)
        self.rec.save()

    def test_an_open_stage_2_is_pending(self):
        row = self.row()
        self.assertFalse(row['is_complete'])
        self.assertFalse(row['subsidy_pending'])

    def test_signed_off_without_the_subsidy_is_subsidy_pending(self):
        self.set(is_complete=True, subsidy_requested=False)
        row = self.row()
        self.assertTrue(row['is_complete'])
        self.assertTrue(row['subsidy_pending'])
        self.assertFalse(row['subsidy_requested'])

    def test_signed_off_with_the_subsidy_is_done(self):
        self.set(is_complete=True, subsidy_requested=True)
        row = self.row()
        self.assertTrue(row['is_complete'])
        self.assertFalse(row['subsidy_pending'])
        self.assertTrue(row['subsidy_requested'])

    def test_an_unfinished_stage_2_is_never_subsidy_pending(self):
        """Ticking the box early must not move it out of Pending."""
        self.set(is_complete=False, subsidy_requested=True)
        self.assertFalse(self.row()['subsidy_pending'])
        self.set(is_complete=False, subsidy_requested=False)
        self.assertFalse(self.row()['subsidy_pending'])

    def test_the_three_states_are_disjoint(self):
        for complete, requested in ((False, False), (True, False), (True, True)):
            self.set(is_complete=complete, subsidy_requested=requested)
            row = self.row()
            pending = not row['is_complete']
            subsidy = row['subsidy_pending']
            done = row['is_complete'] and not subsidy
            self.assertEqual([pending, subsidy, done].count(True), 1,
                             f'complete={complete} requested={requested} -> {row}')


class LiasoningWaitsForThePlantPhotoTests(TestCase):
    """Signing off liasoning says the plant is live, so it waits on the photo."""

    def setUp(self):
        from .models import LiasoningService
        self.officer = mk('lp_officer', 'liasoning_officer')
        self.lead = Lead.objects.create(first_name='mini', last_name='A', phone='9526396825',
                                        status='converted', pushed_to_liasoning=True,
                                        pushed_to_liasoning_at=timezone.now())
        self.rec = LiasoningService.objects.create(lead=self.lead)

    def photo(self, name='plant.jpg'):
        return SimpleUploadedFile(name, b'\xff\xd8\xff jpeg', content_type='image/jpeg')

    def upload(self, **extra):
        data = {'file': self.photo()}
        data.update(extra)
        return self.client.post(f'/api/leads/{self.lead.id}/liasoning/documents/',
                                data=data, HTTP_AUTHORIZATION=token_for(self.officer))

    def complete(self):
        return self.client.post(f'/api/leads/{self.lead.id}/complete-liasoning/',
                                HTTP_AUTHORIZATION=token_for(self.officer))

    def test_completion_is_refused_without_the_photo(self):
        r = self.complete()
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertTrue(r.json().get('needs_plant_photo'))
        self.rec.refresh_from_db()
        self.assertFalse(self.rec.is_complete)

    def test_completion_works_once_the_photo_is_there(self):
        self.assertEqual(self.upload().status_code, 201)
        self.rec.refresh_from_db()
        self.assertTrue(self.rec.has_plant_photo)
        self.assertEqual(self.complete().status_code, 200)
        self.rec.refresh_from_db()
        self.assertTrue(self.rec.is_complete)

    def test_the_record_reports_whether_the_photo_is_there(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/liasoning-record/',
                            HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertIs(r.json()['has_plant_photo'], False)
        self.upload()
        r = self.client.get(f'/api/leads/{self.lead.id}/liasoning-record/',
                            HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertIs(r.json()['has_plant_photo'], True)
        self.assertEqual(len(r.json()['documents']), 1)

    def test_several_photos_are_allowed(self):
        self.assertEqual(self.upload().status_code, 201)
        self.assertEqual(self.upload().status_code, 201)
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.documents.count(), 2)

    def test_an_unknown_slot_is_refused(self):
        r = self.upload(doc_type='something_else')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.rec.documents.count(), 0)

    def test_a_file_is_required(self):
        r = self.client.post(f'/api/leads/{self.lead.id}/liasoning/documents/',
                             data={'doc_type': 'plant_commissioned'},
                             HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 400)

    def test_the_photo_is_locked_once_signed_off(self):
        """It is the evidence behind the sign-off, so it cannot be pulled after."""
        doc_id = self.upload().json()['id']
        self.complete()
        r = self.client.delete(f'/api/leads/{self.lead.id}/liasoning/documents/{doc_id}/',
                               HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.upload().status_code, 400)

    def test_someone_outside_liasoning_cannot_upload(self):
        """A BDE is refused as 404 rather than 403 — the lead is not in their
        queryset at all, so it is rejected before the permission check."""
        r = self.client.post(f'/api/leads/{self.lead.id}/liasoning/documents/',
                             data={'file': self.photo()},
                             HTTP_AUTHORIZATION=token_for(mk('lp_bde', 'bde')))
        self.assertIn(r.status_code, (403, 404), r.content[:200])
        self.assertEqual(self.rec.documents.count(), 0)


class MaintenanceVisitRescheduleTests(TestCase):
    """A scheduled visit can be moved, and the date it was originally due for is
    kept so the slip stays visible."""

    def setUp(self):
        from datetime import date
        from .models import PeriodicMaintenance, MaintenanceVisit
        self.officer = mk('mr_officer', 'liasoning_officer')
        self.lead = Lead.objects.create(first_name='Asha', last_name='Devi T',
                                        phone='9895271486', status='converted',
                                        pushed_to_liasoning=True,
                                        pushed_to_liasoning_at=timezone.now())
        self.plan = PeriodicMaintenance.objects.create(lead=self.lead,
                                                       start_date=date(2026, 8, 4))
        self.visit = MaintenanceVisit.objects.create(plan=self.plan, sequence=1,
                                                     due_date=date(2027, 2, 4))

    def move(self, to, reason='', visit=None):
        return self.client.post(
            f'/api/leads/{self.lead.id}/maintenance-visits/{(visit or self.visit).id}/reschedule/',
            data={'due_date': to, 'reason': reason}, content_type='application/json',
            HTTP_AUTHORIZATION=token_for(self.officer))

    def test_a_visit_can_be_moved(self):
        from datetime import date
        r = self.move('2027-03-15', 'customer away')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.due_date, date(2027, 3, 15))
        self.assertEqual(self.visit.original_due_date, date(2027, 2, 4))
        self.assertEqual(self.visit.reschedule_reason, 'customer away')
        self.assertTrue(self.visit.is_rescheduled)

    def test_moving_it_twice_keeps_the_first_date(self):
        from datetime import date
        self.move('2027-03-15')
        self.move('2027-04-20')
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.due_date, date(2027, 4, 20))
        self.assertEqual(self.visit.original_due_date, date(2027, 2, 4))

    def test_it_lands_on_the_activity_timeline(self):
        self.move('2027-03-15', 'monsoon')
        r = self.client.get(f'/api/leads/{self.lead.id}/activity-timeline/',
                            HTTP_AUTHORIZATION=token_for(self.officer))
        entries = [e['description'] for e in r.json()['entries']]
        self.assertTrue(any('2027-02-04' in e and '2027-03-15' in e and 'monsoon' in e
                            for e in entries), entries)

    def test_a_completed_visit_cannot_be_moved(self):
        self.visit.is_complete = True
        self.visit.save(update_fields=['is_complete'])
        r = self.move('2027-03-15')
        self.assertEqual(r.status_code, 400)
        self.assertIn('already done', r.json()['error'])

    def test_a_bad_date_is_refused(self):
        for bad in ('15-03-2027', 'soon', '', '2027-13-40'):
            r = self.move(bad)
            self.assertEqual(r.status_code, 400, bad)
        self.visit.refresh_from_db()
        self.assertIsNone(self.visit.original_due_date)

    def test_moving_it_to_the_same_date_is_refused(self):
        r = self.move('2027-02-04')
        self.assertEqual(r.status_code, 400)
        self.visit.refresh_from_db()
        self.assertIsNone(self.visit.original_due_date)

    def test_the_general_patch_still_cannot_change_the_date(self):
        """The date moves through the reschedule action, which records it."""
        from datetime import date
        r = self.client.patch(
            f'/api/leads/{self.lead.id}/maintenance-visits/{self.visit.id}/',
            data={'due_date': '2029-01-01', 'dc_voltage': '620'},
            content_type='application/json', HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.due_date, date(2027, 2, 4))   # unmoved
        self.assertEqual(self.visit.dc_voltage, '620')            # the rest saved

    def test_someone_outside_liasoning_cannot_move_it(self):
        r = self.client.post(
            f'/api/leads/{self.lead.id}/maintenance-visits/{self.visit.id}/reschedule/',
            data={'due_date': '2027-03-15'}, content_type='application/json',
            HTTP_AUTHORIZATION=token_for(mk('mr_bde', 'bde')))
        self.assertIn(r.status_code, (403, 404))
        self.visit.refresh_from_db()
        self.assertIsNone(self.visit.original_due_date)


class EmergencyServiceReadingPhotosTests(TestCase):
    """Every reading on an entry can carry photos — several of them. The number
    is what gets reported, the shots are the evidence behind it."""

    SLOTS = ['dc_voltage', 'dc_floating_voltage', 'error_codes', 'monthly_production',
             'ac_ne', 'ac_pn', 'ac_pe']
    # No number to type for these — only the photograph.
    PICTURE_ONLY = ['panel_before', 'panel_after', 'production_before', 'production_after']

    def setUp(self):
        self.officer = mk('es_officer', 'liasoning_officer')
        self.entry_id = self.client.post(
            '/api/emergency-services/',
            data={'customer_name': 'Asha Devi T', 'ac_ne_voltage': '2'},
            content_type='application/json',
            HTTP_AUTHORIZATION=token_for(self.officer)).json()['id']

    def photo(self, name):
        """A real image — the slot takes photos, so give it one."""
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new('RGB', (2, 2), (20, 20, 20)).save(buf, format='JPEG')
        return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')

    def upload(self, slot, name='shot.jpg', entry=None):
        return self.client.post(
            f'/api/emergency-services/{entry or self.entry_id}/documents/',
            data={'doc_type': slot, 'file': self.photo(name)},
            HTTP_AUTHORIZATION=token_for(self.officer))

    def docs(self):
        r = self.client.get(f'/api/emergency-services/{self.entry_id}/',
                            HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()['documents']

    def test_every_reading_has_a_photo_slot(self):
        for slot in self.SLOTS:
            self.assertEqual(self.upload(slot, f'{slot}.jpg').status_code, 201, slot)
        self.assertEqual({d['doc_type'] for d in self.docs()}, set(self.SLOTS))

    def test_the_wash_and_production_shots_have_their_own_slots(self):
        """Panel wash and production either side of the visit are photo-only."""
        for slot in self.PICTURE_ONLY:
            self.assertEqual(self.upload(slot, f'{slot}.jpg').status_code, 201, slot)
        self.assertEqual({d['doc_type'] for d in self.docs()}, set(self.PICTURE_ONLY))

    def test_the_dc_floating_reading_saves(self):
        r = self.client.patch(f'/api/emergency-services/{self.entry_id}/',
                              data={'dc_voltage': '240', 'dc_floating_voltage': '12'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual((r.json()['dc_voltage'], r.json()['dc_floating_voltage']), ('240', '12'))

    def test_a_reading_takes_several_photos(self):
        """A meter is often shot twice, and a burned board needs more angles."""
        for n in range(3):
            self.assertEqual(self.upload('ac_ne', f'ne{n}.jpg').status_code, 201)
        self.assertEqual(len([d for d in self.docs() if d['doc_type'] == 'ac_ne']), 3)

    def test_photos_are_optional(self):
        """The photo is evidence, not a requirement — a typed reading stands."""
        r = self.client.post('/api/emergency-services/',
                             data={'customer_name': 'No Photo', 'dc_voltage': '3'},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 201, r.content[:200])
        self.assertEqual(r.json()['documents'], [])

    def test_editing_the_text_leaves_the_photos_alone(self):
        self.upload('ac_ne')
        r = self.client.patch(f'/api/emergency-services/{self.entry_id}/',
                              data={'ac_ne_voltage': '5'}, content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['ac_ne_voltage'], '5')
        self.assertEqual(len(self.docs()), 1)

    def test_one_photo_can_be_removed_without_the_others(self):
        first = self.upload('ac_ne', 'a.jpg').json()['id']
        self.upload('ac_ne', 'b.jpg')
        r = self.client.delete(f'/api/emergency-services/{self.entry_id}/documents/{first}/',
                               HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 204)
        remaining = self.docs()
        self.assertEqual(len(remaining), 1)
        self.assertIn('b', remaining[0]['file'])

    def test_an_unknown_slot_is_refused(self):
        r = self.upload('somewhere_else')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.docs(), [])

    def test_a_file_is_required(self):
        r = self.client.post(f'/api/emergency-services/{self.entry_id}/documents/',
                             data={'doc_type': 'ac_ne'},
                             HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 400)

    def test_deleting_the_entry_takes_its_photos_with_it(self):
        from .models import EmergencyServiceDocument
        self.upload('ac_ne')
        self.client.delete(f'/api/emergency-services/{self.entry_id}/',
                           HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(EmergencyServiceDocument.objects.count(), 0)

    def test_the_module_is_still_liasoning_only(self):
        r = self.client.post(f'/api/emergency-services/{self.entry_id}/documents/',
                             data={'doc_type': 'ac_ne', 'file': self.photo('x.jpg')},
                             HTTP_AUTHORIZATION=token_for(mk('es_bde', 'bde')))
        self.assertEqual(r.status_code, 403)


class EmergencyServiceConditionTests(TestCase):
    """Service Condition: what was found wrong on each side, and what was
    replaced. Each is one optional pick."""

    # Spelled out here independently of the model, so a value that quietly
    # changes name breaks a test rather than a form the officer is using.
    DC_SIDE = ['inverter_damage', 'dc_fuse_damage', 'dc_mcb_damage',
               'dc_box_burned', 'dc_spd_damage']
    AC_SIDE = ['ac_spd_damage', 'ac_mcb_isolator_damage',
               'generation_meter_faulty', 'termination_point_damage']
    REPLACEMENTS = ['inverter', 'panel', 'dc_db', 'ac_db',
                    'dc_db_components', 'ac_db_components']

    def setUp(self):
        self.officer = mk('sc_officer', 'liasoning_officer')

    def create(self, **fields):
        return self.client.post('/api/emergency-services/', data={
            'customer_name': 'Asha Devi T', **fields,
        }, content_type='application/json', HTTP_AUTHORIZATION=token_for(self.officer))

    def test_every_dc_side_option_is_accepted(self):
        for value in self.DC_SIDE:
            r = self.create(dc_side_condition=value)
            self.assertEqual(r.status_code, 201, f'{value}: {r.content[:200]}')
            self.assertEqual(r.json()['dc_side_condition'], value)

    def test_every_ac_side_option_is_accepted(self):
        for value in self.AC_SIDE:
            r = self.create(ac_side_condition=value)
            self.assertEqual(r.status_code, 201, f'{value}: {r.content[:200]}')

    def test_every_replacement_option_is_accepted(self):
        for value in self.REPLACEMENTS:
            r = self.create(replacement=value)
            self.assertEqual(r.status_code, 201, f'{value}: {r.content[:200]}')

    def test_the_lists_are_exactly_what_the_form_offers(self):
        from .models import EmergencyService
        self.assertEqual([v for v, _ in EmergencyService.DC_SIDE_CHOICES], self.DC_SIDE)
        self.assertEqual([v for v, _ in EmergencyService.AC_SIDE_CHOICES], self.AC_SIDE)
        self.assertEqual([v for v, _ in EmergencyService.REPLACEMENT_CHOICES], self.REPLACEMENTS)

    def test_an_unknown_option_is_refused(self):
        r = self.create(dc_side_condition='something_else')
        self.assertEqual(r.status_code, 400)

    def test_all_three_are_optional(self):
        """Plenty of visits find nothing on one side and replace nothing."""
        r = self.create(service='Routine check')
        self.assertEqual(r.status_code, 201, r.content[:200])
        for f in ('dc_side_condition', 'ac_side_condition', 'replacement'):
            self.assertEqual(r.json()[f], '')

    def test_the_readable_label_comes_back_for_the_list(self):
        r = self.create(dc_side_condition='dc_box_burned',
                        ac_side_condition='ac_spd_damage',
                        replacement='dc_db_components')
        d = r.json()
        self.assertEqual(d['dc_side_condition_label'], 'DC box burned')
        self.assertEqual(d['ac_side_condition_label'], 'AC SPD damage')
        self.assertEqual(d['replacement_label'], 'DC DB components')

    def test_all_three_can_be_recorded_on_one_visit(self):
        from .models import EmergencyService
        r = self.create(dc_side_condition='inverter_damage',
                        ac_side_condition='termination_point_damage',
                        replacement='inverter')
        entry = EmergencyService.objects.get(pk=r.json()['id'])
        self.assertEqual((entry.dc_side_condition, entry.ac_side_condition, entry.replacement),
                         ('inverter_damage', 'termination_point_damage', 'inverter'))


class MaintenanceVisitPhotoSlotsTests(TestCase):
    """A visit records the wash, what the plant made either side of it, the
    cleaned inverter and every reading — each slot holding as many photos as the
    job needed."""

    PICTURE_ONLY = ['panel_before', 'panel_after', 'production_before', 'production_after',
                    'inverter_cleaned']
    READINGS = ['dc_voltage', 'dc_floating_voltage', 'error_codes', 'structure_damage',
                'monthly_production', 'ac_ne', 'ac_pn', 'ac_pe']

    def setUp(self):
        from datetime import date
        from .models import PeriodicMaintenance, MaintenanceVisit
        self.officer = mk('mv_officer', 'liasoning_officer')
        self.lead = Lead.objects.create(first_name='Asha', last_name='Devi T',
                                        phone='9895271487', status='converted',
                                        pushed_to_liasoning=True,
                                        pushed_to_liasoning_at=timezone.now())
        plan = PeriodicMaintenance.objects.create(lead=self.lead, start_date=date(2026, 8, 5))
        self.visit = MaintenanceVisit.objects.create(plan=plan, sequence=1,
                                                     due_date=date(2027, 2, 5))

    def photo(self, name):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new('RGB', (2, 2), (30, 30, 30)).save(buf, format='JPEG')
        return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')

    def upload(self, slot, name='shot.jpg'):
        return self.client.post(
            f'/api/leads/{self.lead.id}/maintenance-visits/{self.visit.id}/documents/',
            data={'doc_type': slot, 'file': self.photo(name)},
            HTTP_AUTHORIZATION=token_for(self.officer))

    def docs(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/maintenance-detail/',
                            HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:200])
        # Visits hang off the plan in this payload.
        visits = r.json()['plan']['visits']
        visit = next(v for v in visits if v['id'] == self.visit.id)
        return visit['documents']

    def test_every_slot_takes_a_photo(self):
        for slot in self.PICTURE_ONLY + self.READINGS:
            self.assertEqual(self.upload(slot, f'{slot}.jpg').status_code, 201, slot)
        self.assertEqual({d['doc_type'] for d in self.docs()},
                         set(self.PICTURE_ONLY + self.READINGS))

    def test_a_slot_takes_several_photos(self):
        for n in range(3):
            self.assertEqual(self.upload('panel_before', f'p{n}.jpg').status_code, 201)
        self.assertEqual(len([d for d in self.docs() if d['doc_type'] == 'panel_before']), 3)

    def test_one_photo_can_be_removed_without_the_others(self):
        first = self.upload('panel_after', 'a.jpg').json()['id']
        self.upload('panel_after', 'b.jpg')
        r = self.client.delete(
            f'/api/leads/{self.lead.id}/maintenance-visits/{self.visit.id}/documents/{first}/',
            HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 204)
        left = self.docs()
        self.assertEqual(len(left), 1)
        self.assertIn('b', left[0]['file'])

    def test_the_new_dc_floating_reading_saves(self):
        r = self.client.patch(
            f'/api/leads/{self.lead.id}/maintenance-visits/{self.visit.id}/',
            data={'dc_voltage': '240', 'dc_floating_voltage': '12'},
            content_type='application/json', HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.visit.refresh_from_db()
        self.assertEqual((self.visit.dc_voltage, self.visit.dc_floating_voltage), ('240', '12'))

    def test_an_unknown_slot_is_refused(self):
        r = self.upload('somewhere_else')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.docs(), [])

    def test_a_file_is_required(self):
        r = self.client.post(
            f'/api/leads/{self.lead.id}/maintenance-visits/{self.visit.id}/documents/',
            data={'doc_type': 'panel_before'}, HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 400)

    def test_photos_are_optional(self):
        """A visit filled in without photos still saves."""
        r = self.client.patch(
            f'/api/leads/{self.lead.id}/maintenance-visits/{self.visit.id}/',
            data={'is_complete': True}, content_type='application/json',
            HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.docs(), [])

    def test_someone_outside_liasoning_cannot_upload(self):
        r = self.client.post(
            f'/api/leads/{self.lead.id}/maintenance-visits/{self.visit.id}/documents/',
            data={'doc_type': 'panel_before', 'file': self.photo('x.jpg')},
            HTTP_AUTHORIZATION=token_for(mk('mv_bde', 'bde')))
        self.assertIn(r.status_code, (403, 404))


class ProjectDeadlineTests(TestCase):
    """The 20-day installation deadline.

    The clock starts the day accounts first records money against the lead â€”
    partial payment or full. Miss it and the project leaves the pending queue for
    Overdue, where only a super admin can act: they release it back with a fresh
    deadline and the project team resumes.
    """

    def setUp(self):
        from .models import Project
        self.pm = mk('pd_pm', 'project_manager')
        self.superadmin = mk('pd_super', 'superadmin')
        self.superadmin.is_superuser = True
        self.superadmin.is_staff = True
        self.superadmin.save()
        self.admin = mk('pd_admin', 'admin')

        self.lead = Lead.objects.create(
            first_name='Asha', last_name='Devi T', phone='9895271487',
            status='converted', value=Decimal('225000'),
            pushed_to_project=True, pushed_to_project_at=timezone.now(),
            project_manager=self.pm)
        self.project = Project.objects.create(lead=self.lead)

    def paid_days_ago(self, days, amount='50000'):
        """Accounts records a payment `days` ago â€” the deadline counts from there."""
        pv = PaymentVerification.objects.create(
            lead=self.lead, amount_received=Decimal(amount), payment_mode='upi',
            utr_details='X1', is_complete=True)
        when = timezone.now() - timedelta(days=days)
        PaymentVerification.objects.filter(pk=pv.pk).update(completed_at=when, created_at=when)
        return pv

    def row(self, user=None):
        r = self.client.get('/api/leads/project/', HTTP_AUTHORIZATION=token_for(user or self.pm))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return next(x for x in r.json() if x['id'] == self.lead.id)

    # â”€â”€ The clock â”€â”€
    def test_no_payment_means_no_deadline(self):
        """Nothing is late before the customer has paid anything."""
        row = self.row()
        self.assertIsNone(row['deadline_date'])
        self.assertFalse(row['project_overdue'])

    def test_a_partial_payment_starts_the_clock(self):
        self.paid_days_ago(0, amount='50000')
        row = self.row()
        expected = (timezone.localdate() + timedelta(days=20)).isoformat()
        self.assertEqual(row['deadline_date'], expected)
        self.assertEqual(row['days_to_deadline'], 20)
        self.assertFalse(row['project_overdue'])

    def test_a_balance_payment_can_start_the_clock(self):
        """A lead paid only through the balance ledger still has a deadline."""
        from .models import BalancePayment
        pv = PaymentVerification.objects.create(lead=self.lead, amount_received=Decimal('0'))
        bp = BalancePayment.objects.create(lead=self.lead, amount=Decimal('10000'))
        when = timezone.now() - timedelta(days=25)
        BalancePayment.objects.filter(pk=bp.pk).update(created_at=when)
        PaymentVerification.objects.filter(pk=pv.pk).update(created_at=when)
        self.assertTrue(self.row()['project_overdue'])

    def test_the_earliest_payment_is_the_one_that_counts(self):
        """A later installment must not push the deadline out."""
        from .models import BalancePayment
        self.paid_days_ago(25)
        BalancePayment.objects.create(lead=self.lead, amount=Decimal('10000'))
        row = self.row()
        self.assertEqual(row['payment_started_on'],
                         (timezone.localdate() - timedelta(days=25)).isoformat())
        self.assertTrue(row['project_overdue'])

    def test_day_twenty_is_still_inside_the_deadline(self):
        self.paid_days_ago(20)
        row = self.row()
        self.assertEqual(row['days_to_deadline'], 0)
        self.assertFalse(row['project_overdue'])

    def test_day_twenty_one_is_overdue(self):
        self.paid_days_ago(21)
        row = self.row()
        self.assertEqual(row['days_to_deadline'], -1)
        self.assertTrue(row['project_overdue'])

    def test_a_completed_project_is_never_overdue(self):
        """Finishing late is still finished â€” it does not sit in Overdue."""
        self.paid_days_ago(40)
        self.project.is_complete = True
        self.project.completed_at = timezone.now()
        self.project.save()
        self.assertFalse(self.row()['project_overdue'])

    # â”€â”€ The lock â”€â”€
    def test_the_project_manager_cannot_edit_an_overdue_project(self):
        self.paid_days_ago(30)
        r = self.client.patch(f'/api/leads/{self.lead.id}/project-record/',
                              data={'structure_work_start_date': '2026-08-01'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 403, r.content[:200])
        self.assertFalse(self.row()['can_edit_project'])

    def test_an_admin_cannot_edit_an_overdue_project_either(self):
        """The lock is not about rank below super admin â€” it holds for admins."""
        self.paid_days_ago(30)
        r = self.client.patch(f'/api/leads/{self.lead.id}/project-record/',
                              data={'structure_work_start_date': '2026-08-01'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 403, r.content[:200])

    def test_the_super_admin_can_edit_an_overdue_project(self):
        self.paid_days_ago(30)
        r = self.client.patch(f'/api/leads/{self.lead.id}/project-record/',
                              data={'structure_work_start_date': '2026-08-01'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertEqual(r.status_code, 200, r.content[:200])

    def test_an_overdue_project_cannot_be_completed_by_the_project_team(self):
        self.paid_days_ago(30)
        r = self.client.post(f'/api/leads/{self.lead.id}/complete-project/',
                             HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 403, r.content[:200])
        self.project.refresh_from_db()
        self.assertFalse(self.project.is_complete)

    def test_photos_cannot_be_uploaded_to_an_overdue_project(self):
        self.paid_days_ago(30)
        r = self.client.post(f'/api/leads/{self.lead.id}/project-record/documents/',
                             data={'doc_type': 'plant_photo',
                                   'file': SimpleUploadedFile('p.txt', b'x')},
                             HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 403, r.content[:200])

    def test_a_project_inside_its_deadline_is_still_editable(self):
        self.paid_days_ago(5)
        r = self.client.patch(f'/api/leads/{self.lead.id}/project-record/',
                              data={'structure_work_start_date': '2026-08-01'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 200, r.content[:200])

    def test_the_project_team_cannot_extend_its_own_deadline(self):
        """The release fields are read-only, or the lock would never bite."""
        self.paid_days_ago(5)
        far = (timezone.localdate() + timedelta(days=900)).isoformat()
        r = self.client.patch(f'/api/leads/{self.lead.id}/project-record/',
                              data={'extended_deadline': far},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.project.refresh_from_db()
        self.assertIsNone(self.project.extended_deadline)

    # â”€â”€ The release â”€â”€
    def test_only_the_super_admin_can_release(self):
        self.paid_days_ago(30)
        for user in (self.pm, self.admin):
            r = self.client.post(f'/api/leads/{self.lead.id}/release-project/',
                                 HTTP_AUTHORIZATION=token_for(user))
            self.assertEqual(r.status_code, 403, f'{user.username}: {r.content[:200]}')
        self.project.refresh_from_db()
        self.assertIsNone(self.project.extended_deadline)

    def test_a_release_hands_the_project_back_with_a_new_deadline(self):
        self.paid_days_ago(30)
        r = self.client.post(f'/api/leads/{self.lead.id}/release-project/',
                             data={'reason': 'Panel supply held up'},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        body = r.json()
        self.assertFalse(body['project_overdue'])
        self.assertEqual(body['deadline_date'],
                         (timezone.localdate() + timedelta(days=20)).isoformat())
        self.assertEqual(body['release_reason'], 'Panel supply held up')
        # And the project manager can work on it again.
        self.assertTrue(self.row()['can_edit_project'])
        r = self.client.patch(f'/api/leads/{self.lead.id}/project-record/',
                              data={'structure_work_start_date': '2026-08-01'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 200, r.content[:200])

    def test_a_release_can_name_its_own_deadline(self):
        self.paid_days_ago(30)
        wanted = (timezone.localdate() + timedelta(days=7)).isoformat()
        r = self.client.post(f'/api/leads/{self.lead.id}/release-project/',
                             data={'deadline': wanted}, content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['deadline_date'], wanted)

    def test_a_release_cannot_hand_back_a_deadline_already_gone(self):
        """A past date would drop the row straight back into Overdue."""
        self.paid_days_ago(30)
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        r = self.client.post(f'/api/leads/{self.lead.id}/release-project/',
                             data={'deadline': past}, content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertEqual(r.status_code, 400, r.content[:200])
        self.project.refresh_from_db()
        self.assertIsNone(self.project.extended_deadline)

    def test_a_released_project_goes_overdue_again_if_the_new_deadline_passes(self):
        self.paid_days_ago(30)
        self.project.extended_deadline = timezone.localdate() - timedelta(days=1)
        self.project.released_at = timezone.now()
        self.project.save()
        self.assertTrue(self.row()['project_overdue'])

    def test_a_project_inside_its_deadline_cannot_be_released(self):
        self.paid_days_ago(5)
        r = self.client.post(f'/api/leads/{self.lead.id}/release-project/',
                             HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertEqual(r.status_code, 400, r.content[:200])

    def test_the_release_is_written_to_the_timeline(self):
        from .models import ActivityLog
        self.paid_days_ago(30)
        self.client.post(f'/api/leads/{self.lead.id}/release-project/',
                         data={'reason': 'Customer away'}, content_type='application/json',
                         HTTP_AUTHORIZATION=token_for(self.superadmin))
        notes = [a.description for a in ActivityLog.objects.filter(lead=self.lead)]
        self.assertTrue(any('released back to the project team' in n and 'Customer away' in n
                            for n in notes), notes)


class MaintenanceReminderTests(TestCase):
    """A visit calls for attention the day before it is due, and the upcoming list
    puts every outstanding visit in the order it falls due."""

    def setUp(self):
        from datetime import date
        from .models import PeriodicMaintenance, MaintenanceVisit
        self.officer = mk('mr_officer', 'liasoning_officer')
        self.today = timezone.localdate()

        def customer(name, phone):
            lead = Lead.objects.create(
                first_name=name, phone=phone, status='converted',
                pushed_to_liasoning=True, pushed_to_liasoning_at=timezone.now())
            return PeriodicMaintenance.objects.create(lead=lead, start_date=self.today)

        # One plan whose visits sit either side of the reminder line.
        self.plan = customer('Asha', '9895271487')
        self.visits = {
            'overdue': MaintenanceVisit.objects.create(
                plan=self.plan, sequence=1, due_date=self.today - timedelta(days=3)),
            'today': MaintenanceVisit.objects.create(
                plan=self.plan, sequence=2, due_date=self.today),
            'tomorrow': MaintenanceVisit.objects.create(
                plan=self.plan, sequence=3, due_date=self.today + timedelta(days=1)),
            'later': MaintenanceVisit.objects.create(
                plan=self.plan, sequence=4, due_date=self.today + timedelta(days=30)),
        }
        # A second customer, so ordering has to cross plans.
        self.other = customer('Bina', '9895271488')
        self.other_visit = MaintenanceVisit.objects.create(
            plan=self.other, sequence=1, due_date=self.today + timedelta(days=2))

    def payload(self, user=None):
        r = self.client.get('/api/leads/periodic-maintenance/',
                            HTTP_AUTHORIZATION=token_for(user or self.officer))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def counts(self, user=None):
        r = self.client.get('/api/leads/module-counts/',
                            HTTP_AUTHORIZATION=token_for(user or self.officer))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()['counts']

    # â”€â”€ The day-before reminder â”€â”€
    def test_the_count_includes_tomorrows_visit(self):
        """Overdue + today + tomorrow â€” the officer gets a day's notice."""
        self.assertEqual(self.counts()['periodic-maintenance'], 3)

    def test_a_visit_further_out_is_not_counted_yet(self):
        """The 30-day visit must not be in the badge, or it never means anything."""
        from .models import MaintenanceVisit
        MaintenanceVisit.objects.filter(
            pk__in=[self.visits['overdue'].pk, self.visits['today'].pk,
                    self.visits['tomorrow'].pk, self.other_visit.pk]).delete()
        self.assertEqual(self.counts()['periodic-maintenance'], 0)

    def test_the_reminder_line_moves_with_the_lead_time(self):
        """A visit two days out is outside the window; one day out is inside."""
        from .models import MaintenanceVisit
        MaintenanceVisit.objects.exclude(pk=self.visits['later'].pk).delete()
        MaintenanceVisit.objects.filter(pk=self.visits['later'].pk).update(
            due_date=self.today + timedelta(days=2))
        self.assertEqual(self.counts()['periodic-maintenance'], 0)
        MaintenanceVisit.objects.filter(pk=self.visits['later'].pk).update(
            due_date=self.today + timedelta(days=MaintenanceVisit.REMINDER_LEAD_DAYS))
        self.assertEqual(self.counts()['periodic-maintenance'], 1)

    def test_a_finished_visit_stops_reminding(self):
        from .models import MaintenanceVisit
        MaintenanceVisit.objects.filter(
            pk__in=[self.visits['overdue'].pk, self.visits['today'].pk]).update(is_complete=True)
        self.assertEqual(self.counts()['periodic-maintenance'], 1)

    # â”€â”€ The upcoming list â”€â”€
    def test_upcoming_lists_every_outstanding_visit(self):
        rows = self.payload()['upcoming']
        self.assertEqual(len(rows), 5)

    def test_upcoming_is_sorted_by_due_date_across_customers(self):
        rows = self.payload()['upcoming']
        self.assertEqual([r['due_date'] for r in rows], sorted(r['due_date'] for r in rows))
        # Bina's visit (2 days out) sits between Asha's tomorrow and Asha's +30.
        self.assertEqual([r['first_name'] for r in rows],
                         ['Asha', 'Asha', 'Asha', 'Bina', 'Asha'])

    def test_upcoming_flags_what_needs_attention(self):
        rows = {(r['first_name'], r['sequence']): r for r in self.payload()['upcoming']}
        self.assertTrue(rows[('Asha', 1)]['is_overdue'])
        self.assertTrue(rows[('Asha', 1)]['is_due'])
        self.assertFalse(rows[('Asha', 2)]['is_overdue'])
        self.assertTrue(rows[('Asha', 2)]['is_due'])       # due today
        self.assertTrue(rows[('Asha', 3)]['is_due'])       # due tomorrow
        self.assertFalse(rows[('Bina', 1)]['is_due'])      # two days out
        self.assertFalse(rows[('Asha', 4)]['is_due'])

    def test_upcoming_reports_how_far_off_each_visit_is(self):
        rows = {(r['first_name'], r['sequence']): r for r in self.payload()['upcoming']}
        self.assertEqual(rows[('Asha', 1)]['days_to_due'], -3)
        self.assertEqual(rows[('Asha', 2)]['days_to_due'], 0)
        self.assertEqual(rows[('Asha', 3)]['days_to_due'], 1)
        self.assertEqual(rows[('Asha', 4)]['days_to_due'], 30)

    def test_a_finished_visit_leaves_the_upcoming_list(self):
        from .models import MaintenanceVisit
        MaintenanceVisit.objects.filter(pk=self.visits['overdue'].pk).update(is_complete=True)
        rows = self.payload()['upcoming']
        self.assertEqual(len(rows), 4)
        self.assertNotIn(self.visits['overdue'].id, [r['visit_id'] for r in rows])

    def test_upcoming_carries_the_reschedule_trail(self):
        """A moved visit shows where it came from, so the slip stays visible."""
        moved = self.visits['later']
        r = self.client.post(
            f'/api/leads/{self.plan.lead_id}/maintenance-visits/{moved.id}/reschedule/',
            data={'due_date': (self.today + timedelta(days=45)).isoformat(),
                  'reason': 'Customer travelling'},
            content_type='application/json', HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:300])
        row = next(x for x in self.payload()['upcoming'] if x['visit_id'] == moved.id)
        self.assertTrue(row['is_rescheduled'])
        self.assertEqual(row['original_due_date'], (self.today + timedelta(days=30)).isoformat())
        self.assertEqual(row['reschedule_reason'], 'Customer travelling')
        self.assertEqual(row['due_date'], (self.today + timedelta(days=45)).isoformat())

    def test_an_unscheduled_customer_contributes_nothing_upcoming(self):
        Lead.objects.create(first_name='Chandra', phone='9895271489', status='converted',
                            pushed_to_liasoning=True, pushed_to_liasoning_at=timezone.now())
        body = self.payload()
        self.assertIn('Chandra', [r['first_name'] for r in body['eligible']])
        self.assertNotIn('Chandra', [r['first_name'] for r in body['upcoming']])

    def test_someone_outside_liasoning_cannot_read_the_list(self):
        r = self.client.get('/api/leads/periodic-maintenance/',
                            HTTP_AUTHORIZATION=token_for(mk('mr_bde', 'bde')))
        self.assertEqual(r.status_code, 403)
