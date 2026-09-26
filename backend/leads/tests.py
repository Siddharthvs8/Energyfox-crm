"""Lead-status ownership and the site-visit indicator the Leads list renders."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile

from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from .models import (District, DocumentationStage2, Lead, LiasoningService, PaymentVerification,
                     SiteVisit, Warranty, WarrantyDocument)
from .meta_integration import create_lead_from_meta_payload, is_ad_metadata_name


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
        # Paid, because won means closed: see leads.scopes.CLOSED_DEAL_FILTER.
        won = Lead.objects.create(first_name='A', last_name='Won', phone='9993000001',
                                  status='converted', assigned_to=self.caller,
                                  bde=self.bde1, value=86676, pushed_to_accounts=True)
        PaymentVerification.objects.create(lead=won, amount_received=86676)
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
        # The escalation queue is theirs too — the count going up is how they are
        # told a project has passed its deadline.
        'project_manager': ['project', 'project-overdue'],
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
        for n, (role, module) in enumerate((('documentation_staff', 'documentation'),
                                           ('accounts_staff', 'accounts'),
                                           ('purchase_staff', 'purchase'),
                                           ('project_manager', 'project'),
                                           ('project_manager', 'project-overdue'),
                                           ('bde', 'leads'))):
            body = self.counts(mk(f'a{n}_{role}', role))
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
        from .models import SiteVisit
        lead = Lead.objects.create(first_name='P', last_name=last, phone=f'99931{last[:5]}',
                                   status='converted', bde=self.bde, value=Decimal(value),
                                   pushed_to_accounts=True)
        # Accounts refuses to verify a payment while KSEB feasibility is pending
        # (see AccountsPushToPurchaseTests). These tests are about the payment
        # buckets, so the sanction is already in hand.
        SiteVisit.objects.create(lead=lead, kseb_feasibility_complete=True)
        return lead

    def verify(self, lead, received, discount=0):
        """Run the real accounts flow so the hand-off happens as it does live.

        Two steps now, not one: verifying records the money, and a separate push
        hands the customer to purchase once KSEB has sanctioned the capacity —
        see AccountsPushToPurchaseTests. `make_lead` grants the sanction, because
        these tests are about the queue rather than the gate.
        """
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
        if Decimal(str(received)) > 0:
            push = self.client.post(f'/api/leads/{lead.id}/push-to-purchase/',
                                    HTTP_AUTHORIZATION=token_for(self.admin))
            self.assertEqual(push.status_code, 200, push.content[:200])
            return push
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



class AccountsPushToPurchaseTests(TestCase):
    """Verifying the payment and pushing to purchase are two different acts.

    Verifying says money arrived — true whatever KSEB has done, and accounts
    must be able to record it the day it lands. Pushing says procurement may
    start spending it, and that waits on the sanction: panels must not be
    ordered for a capacity the board has not approved. The two are often days
    apart, which is the whole reason they are separate buttons.

    This replaces the earlier rule, where verifying was itself the hand-off and
    was therefore blocked until the sanction came in.
    """

    def setUp(self):
        from .models import PaymentVerification, SiteVisit
        self.accountant = mk('acc_push', 'accounts_staff')
        self.lead = Lead.objects.create(
            first_name='Acc', last_name='Push', phone='9994100002',
            status='converted', value=200000,
            pushed_to_accounts=True, pushed_to_accounts_at=timezone.now(),
            accounts_staff=self.accountant)
        self.sv = SiteVisit.objects.create(lead=self.lead)
        self.pv = PaymentVerification.objects.create(
            lead=self.lead, amount_received=50000, payment_mode='cash')

    def verify(self):
        return self.client.post(
            f'/api/leads/{self.lead.id}/complete-payment-verification/',
            HTTP_AUTHORIZATION=token_for(self.accountant))

    def push(self, user=None):
        return self.client.post(
            f'/api/leads/{self.lead.id}/push-to-purchase/',
            HTTP_AUTHORIZATION=token_for(user or self.accountant))

    def payload(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/accounts-detail/',
                            HTTP_AUTHORIZATION=token_for(self.accountant))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def feasibility_done(self):
        self.sv.kseb_feasibility_complete = True
        self.sv.save(update_fields=['kseb_feasibility_complete'])

    # ── Verifying no longer waits on KSEB ──
    def test_the_payment_can_be_verified_while_feasibility_is_pending(self):
        """The money has arrived; recording that is not procurement's business."""
        r = self.verify()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.pv.refresh_from_db()
        self.assertTrue(self.pv.is_complete)

    def test_verifying_does_not_push_to_purchase_by_itself(self):
        """Even with the sanction in, the hand-off is a deliberate act now."""
        self.feasibility_done()
        self.assertEqual(self.verify().status_code, 200)
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.pushed_to_purchase)

    def test_a_lead_with_no_site_visit_can_still_be_verified(self):
        self.sv.delete()
        self.assertEqual(self.verify().status_code, 200)

    def test_the_payment_mode_gate_still_applies_to_verifying(self):
        self.pv.payment_mode = ''
        self.pv.save(update_fields=['payment_mode'])
        r = self.verify()
        self.assertEqual(r.status_code, 400)
        self.assertIn('missing', r.json())

    # ── Pushing waits on KSEB ──
    def test_pushing_is_refused_while_feasibility_is_pending(self):
        self.verify()
        r = self.push()
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertTrue(r.json().get('kseb_feasibility_pending'))
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.pushed_to_purchase)

    def test_pushing_works_once_feasibility_is_complete(self):
        self.verify()
        self.feasibility_done()
        r = self.push()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_purchase)
        self.assertIsNotNone(self.lead.pushed_to_purchase_at)

    def test_a_lead_with_no_site_visit_cannot_be_pushed(self):
        self.verify()
        self.sv.delete()
        r = self.push()
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json().get('kseb_feasibility_pending'))

    def test_pushing_before_verifying_is_refused(self):
        """The order matters: procurement should not start on money nobody has
        checked."""
        self.feasibility_done()
        r = self.push()
        self.assertEqual(r.status_code, 400)
        self.assertIn('Verify the payment first', r.json()['error'])

    def test_pushing_with_no_money_received_is_refused(self):
        self.pv.amount_received = 0
        self.pv.save(update_fields=['amount_received'])
        self.verify()
        self.feasibility_done()
        r = self.push()
        self.assertEqual(r.status_code, 400)
        self.assertIn('No money', r.json()['error'])

    def test_pushing_twice_says_it_has_already_gone(self):
        self.verify()
        self.feasibility_done()
        self.assertEqual(self.push().status_code, 200)
        r = self.push()
        self.assertEqual(r.status_code, 400)
        self.assertIn('already', r.json()['error'])

    def test_someone_without_accounts_rights_cannot_push(self):
        """Documentation staff rather than a BDE: a BDE cannot see this lead at
        all, so it would 404 before the permission was ever consulted."""
        docstaff = mk('acc_push_doc', 'documentation_staff')
        self.verify()
        self.feasibility_done()
        self.assertEqual(self.push(user=docstaff).status_code, 403)
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.pushed_to_purchase)

    # ── What the screen is told ──
    def test_the_screen_is_told_when_the_button_may_be_used(self):
        """The rule lives on the server; the screen asks rather than re-deriving."""
        d = self.payload()
        self.assertFalse(d['can_push_to_purchase'])   # not verified yet
        self.assertFalse(d['pushed_to_purchase'])

        self.verify()
        self.assertFalse(self.payload()['can_push_to_purchase'])   # no sanction

        self.feasibility_done()
        self.assertTrue(self.payload()['can_push_to_purchase'])

        self.push()
        d = self.payload()
        self.assertTrue(d['pushed_to_purchase'])
        self.assertFalse(d['can_push_to_purchase'])   # nothing left to do

    # ── What verification still does ──
    def test_verifying_still_turns_accepted_quotations_into_orders(self):
        """That is a fact about the customer's payment, not about procurement,
        so it must not have moved with the hand-off."""
        from inventory.models import Quotation
        q = Quotation.objects.create(lead=self.lead, package_amount=200000, status='accepted')
        self.verify()
        q.refresh_from_db()
        self.assertIsNotNone(q.order_converted_at)

    def test_a_pushed_customer_reaches_the_purchase_queue(self):
        self.verify()
        self.feasibility_done()
        self.push()
        admin = mk('acc_push_admin', 'admin')
        r = self.client.get('/api/leads/purchase/', HTTP_AUTHORIZATION=token_for(admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertIn(self.lead.id, [row['id'] for row in r.json()])


class Stage1DoesNotWaitForFeasibilityTests(TestCase):
    """Documentation finishes its own paperwork without the KSEB sanction.

    The gate moved to accounts: what must not start without a sanctioned
    capacity is procurement, not the documentation hand-over. Documentation can
    close while the BDE is still waiting on the section office.
    """

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

    def test_push_goes_through_while_feasibility_is_pending(self):
        self.assertFalse(self.sv.kseb_feasibility_complete)
        r = self.push()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db(); self.stage1.refresh_from_db()
        self.assertTrue(self.stage1.is_complete)
        self.assertTrue(self.lead.pushed_to_accounts)

    def test_push_works_once_feasibility_is_complete_too(self):
        self.sv.kseb_feasibility_complete = True
        self.sv.save(update_fields=['kseb_feasibility_complete'])
        r = self.push()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_accounts)

    def test_a_lead_with_no_site_visit_at_all_still_pushes(self):
        self.sv.delete()
        r = self.push()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_accounts)

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

        # Both are closed deals — in accounts with money against them — so the
        # deleted one is left out of the figures for being deleted, which is what
        # these tests are about, rather than for never having been paid.
        self.live = Lead.objects.create(first_name='D', last_name='Live', phone='9993300001',
                                        status='converted', assigned_to=self.caller,
                                        value=Decimal('100000'), pushed_to_accounts=True)
        PaymentVerification.objects.create(lead=self.live, amount_received=Decimal('100000'))
        self.deleted = Lead.objects.create(first_name='D', last_name='Deleted',
                                           phone='9993300002', status='converted',
                                           assigned_to=self.caller, value=Decimal('900000'),
                                           pushed_to_accounts=True,
                                           is_trashed=True, trashed_at=timezone.now())
        PaymentVerification.objects.create(lead=self.deleted, amount_received=Decimal('900000'))

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
        # Both are closed deals — money received — so the deleted one is off the
        # board for being deleted, which is what these tests are about.
        self.won = Lead.objects.create(first_name='L', last_name='Won', phone='9993600001',
                                       status='converted', assigned_to=self.caller,
                                       bde=self.bde, value=Decimal('100000'),
                                       pushed_to_accounts=True)
        PaymentVerification.objects.create(lead=self.won, amount_received=Decimal('100000'))
        self.deleted = Lead.objects.create(first_name='L', last_name='Deleted',
                                           phone='9993600002', status='converted',
                                           assigned_to=self.caller, bde=self.bde,
                                           value=Decimal('900000'), pushed_to_accounts=True,
                                           is_trashed=True, trashed_at=timezone.now())
        PaymentVerification.objects.create(lead=self.deleted, amount_received=Decimal('900000'))

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


class Stage2EarlierImagesTests(TestCase):
    """Stage 2 shows back what Stage 1 and the installation crew photographed.

    Annexure 3 is written from those pictures — the serial numbers, the meter,
    the plant — and they live in two modules a Stage 2 officer may not be able
    to open. Working from memory is how a serial number reaches KSEB wrong.
    """

    def setUp(self):
        from django.core.files.base import ContentFile
        from leads.models import (SiteVisit, SiteVisitDocument,
                                  Project, ProjectDocument)
        self.docstaff = mk('img_doc', 'documentation_staff')
        self.lead = Lead.objects.create(
            first_name='Gallery', last_name='Lead', phone='9849394941',
            status='converted', pushed_to_doc_stage2=True,
            pushed_to_doc_stage2_at=timezone.now(), doc_stage2_staff=self.docstaff)

        # The site visit's own files — what Documentation Stage 1 shows.
        visit, _ = SiteVisit.objects.get_or_create(lead=self.lead)
        for slot in ('photo_meterbox', 'kseb_bill_file'):
            d = SiteVisitDocument(site_visit=visit, doc_type=slot)
            d.file.save(f'{slot}.png', ContentFile(b'x'), save=True)

        project, _ = Project.objects.get_or_create(lead=self.lead)
        d = ProjectDocument(project=project, doc_type='panel_serial_numbers')
        d.file.save('panel.png', ContentFile(b'x'), save=True)

    def get(self, who=None):
        return self.client.get(
            f'/api/leads/{self.lead.id}/documentation-stage2-record/',
            HTTP_AUTHORIZATION=token_for(who or self.docstaff))

    def test_both_sets_come_back_with_the_record(self):
        r = self.get()
        self.assertEqual(r.status_code, 200, r.content[:300])
        images = r.json()['earlier_images']
        # Declared order, not upload order — kseb_bill_file is listed first.
        self.assertEqual([d['doc_type'] for d in images['stage1']],
                         ['kseb_bill_file', 'photo_meterbox'])
        self.assertEqual([d['doc_type'] for d in images['installation']],
                         ['panel_serial_numbers'])

    def test_each_file_is_named_the_way_its_own_module_names_it(self):
        """The labels come from the lists the collecting modules use, so the
        Stage 2 page and the Stage 1 page cannot end up disagreeing."""
        images = self.get().json()['earlier_images']
        self.assertEqual([d['label'] for d in images['stage1']],
                         ['KSEB Bill', 'Meter Box'])
        self.assertEqual([d['label'] for d in images['installation']],
                         ['Panel Serial Numbers'])

    def test_a_customer_with_neither_still_loads(self):
        """Stage 2 can be reached before the photos exist."""
        bare = Lead.objects.create(
            first_name='No', last_name='Pictures', phone='9849394942',
            status='converted', pushed_to_doc_stage2=True,
            pushed_to_doc_stage2_at=timezone.now(), doc_stage2_staff=self.docstaff)
        r = self.client.get(f'/api/leads/{bare.id}/documentation-stage2-record/',
                            HTTP_AUTHORIZATION=token_for(self.docstaff))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['earlier_images'],
                         {'stage1': [], 'installation': []})

    def test_they_are_not_offered_to_someone_outside_documentation(self):
        """The pictures inherit the stage's own gate rather than a wider one.

        A BDE is refused at the lead queryset before the stage check is even
        reached, so the refusal reads 404 rather than 403 — either way nothing
        comes back, which is what matters here.
        """
        outsider = mk('img_bde', 'bde')
        r = self.get(outsider)
        self.assertIn(r.status_code, (403, 404))
        self.assertNotIn('earlier_images', r.content.decode())


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

    def test_approval_alone_does_not_hand_the_customer_to_warranty(self):
        """The approval is not the hand-over; the liasoning sign-off is.

        A warranty is a promise about a plant that is live and cleared, and the
        officer still has to sign off after the discom answers.
        """
        self.stage2({'discom_approval': 'yes'})
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.pushed_to_warranty)


class LiasoningLockAndUnlockTests(TestCase):
    """Signing off closes the record; only the super admin can open it again.

    The tick states that the plant is live and the evidence is filed. If the
    officer who made that statement could also take it back, the lock would be
    a formality rather than a record — so reopening sits above the role.
    """

    def setUp(self):
        from .models import LiasoningService
        self.officer = mk('lock_officer', 'liasoning_officer')
        # The super admin is the role, not a hand-set flag: User.save() derives
        # is_superuser from `role`, so setting the boolean alone is overwritten.
        self.admin = mk('lock_admin', 'superadmin')
        self.assertTrue(self.admin.is_superuser)
        self.lead = Lead.objects.create(first_name='Locked', last_name='Case',
                                        phone='9526396826', status='converted',
                                        pushed_to_liasoning=True,
                                        pushed_to_liasoning_at=timezone.now())
        self.rec = LiasoningService.objects.create(lead=self.lead)

    def photo(self):
        return SimpleUploadedFile('p.jpg', b'jpeg bytes', content_type='image/jpeg')

    def sign_off(self):
        from .models import LiasoningService
        for slot in (LiasoningService.PLANT_PHOTO, LiasoningService.RF_IMAGE):
            self.client.post(f'/api/leads/{self.lead.id}/liasoning/documents/',
                             data={'file': self.photo(), 'doc_type': slot},
                             HTTP_AUTHORIZATION=token_for(self.officer))
        r = self.client.post(f'/api/leads/{self.lead.id}/complete-liasoning/',
                             HTTP_AUTHORIZATION=token_for(self.officer))
        self.assertEqual(r.status_code, 200, r.content[:300])

    def reopen(self, who):
        return self.client.post(f'/api/leads/{self.lead.id}/reopen-liasoning/',
                                HTTP_AUTHORIZATION=token_for(who))

    def patch(self, who, **body):
        return self.client.patch(f'/api/leads/{self.lead.id}/liasoning-record/',
                                 data=body, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(who))

    def test_the_sign_off_is_what_hands_the_customer_to_warranty(self):
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.pushed_to_warranty)
        self.sign_off()
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_warranty)
        from .models import Warranty
        self.assertTrue(Warranty.objects.filter(lead=self.lead).exists())

    def test_unlocking_does_not_take_the_customer_back_out_of_warranty(self):
        """Correcting the liasoning record must not withdraw a warranty that
        may already have been issued."""
        self.sign_off()
        self.reopen(self.admin)
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_warranty)

    def test_warranty_shows_the_photos_liasoning_signed_off_on(self):
        self.sign_off()
        r = self.client.get(f'/api/leads/{self.lead.id}/warranty-detail/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        labels = [i['label'] for i in r.json()['liasoning_images']]
        self.assertEqual(labels, ['Plant Photo', 'RF Image'])

    def test_the_record_cannot_be_edited_once_signed_off(self):
        self.sign_off()
        self.assertEqual(self.patch(self.officer, annexure3_remark='late').status_code, 400)
        self.rec.refresh_from_db()
        self.assertNotEqual(self.rec.annexure3_remark, 'late')

    def test_the_officer_cannot_unlock_it(self):
        self.sign_off()
        r = self.reopen(self.officer)
        self.assertEqual(r.status_code, 403, r.content[:200])
        self.rec.refresh_from_db()
        self.assertTrue(self.rec.is_complete)

    def test_a_plain_admin_cannot_unlock_it_either(self):
        """Grantable permissions do not reach this; it is the super admin alone."""
        self.sign_off()
        plain = mk('lock_plain_admin', 'admin')
        self.assertFalse(plain.is_superuser)
        self.assertEqual(self.reopen(plain).status_code, 403)

    def test_the_super_admin_unlocks_it_and_editing_resumes(self):
        self.sign_off()
        r = self.reopen(self.admin)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertFalse(r.json()['is_complete'])
        self.rec.refresh_from_db()
        self.assertFalse(self.rec.is_complete)
        self.assertIsNone(self.rec.completed_at)
        self.assertEqual(self.patch(self.officer, annexure3_remark='after unlock').status_code, 200)

    def test_unlocking_keeps_the_photos(self):
        """Reopening is for correcting the record, not for losing its evidence."""
        self.sign_off()
        self.reopen(self.admin)
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.documents.count(), 2)
        self.assertTrue(self.rec.photos_complete)

    def test_unlocking_one_that_is_not_locked_is_refused(self):
        self.assertEqual(self.reopen(self.admin).status_code, 400)

    def test_the_row_says_who_may_unlock(self):
        """The button is offered on the same answer the server would give."""
        self.sign_off()
        for who, expected in ((self.admin, True), (self.officer, False)):
            r = self.client.get(f'/api/leads/{self.lead.id}/liasoning-detail/',
                                HTTP_AUTHORIZATION=token_for(who))
            self.assertIs(r.json()['can_reopen'], expected)


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

    def upload_both(self):
        """Both required photos — the sign-off waits on the pair."""
        from .models import LiasoningService
        self.upload(doc_type=LiasoningService.PLANT_PHOTO)
        self.upload(doc_type=LiasoningService.RF_IMAGE)

    def complete(self):
        return self.client.post(f'/api/leads/{self.lead.id}/complete-liasoning/',
                                HTTP_AUTHORIZATION=token_for(self.officer))

    def test_completion_is_refused_without_the_photo(self):
        r = self.complete()
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertTrue(r.json().get('needs_plant_photo'))
        self.rec.refresh_from_db()
        self.assertFalse(self.rec.is_complete)

    def test_the_plant_photo_alone_is_not_enough(self):
        """Both pictures are the evidence, so both are required."""
        self.assertEqual(self.upload().status_code, 201)
        self.rec.refresh_from_db()
        self.assertTrue(self.rec.has_plant_photo)
        r = self.complete()
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertEqual(r.json()['missing_photos'], ['RF Image'])
        self.rec.refresh_from_db()
        self.assertFalse(self.rec.is_complete)

    def test_the_rf_image_alone_is_not_enough_either(self):
        from .models import LiasoningService
        self.upload(doc_type=LiasoningService.RF_IMAGE)
        r = self.complete()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['missing_photos'], ['Plant Photo'])

    def test_completion_works_once_both_photos_are_there(self):
        self.upload_both()
        self.rec.refresh_from_db()
        self.assertTrue(self.rec.photos_complete)
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

    def test_uploading_again_replaces_rather_than_piles_up(self):
        """A slot holds one picture. "The plant photo" is a single thing, and a
        slot quietly holding three leaves the next person guessing which one the
        sign-off meant."""
        first = self.upload().json()['id']
        second = self.upload().json()['id']
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.documents.count(), 1)
        self.assertEqual(self.rec.documents.first().id, second)
        self.assertNotEqual(first, second)

    def test_the_two_slots_do_not_replace_each_other(self):
        from .models import LiasoningService
        self.upload_both()
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.documents.count(), 2)
        self.assertTrue(self.rec.has_plant_photo)
        self.assertTrue(self.rec.has_rf_image)

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
        self.upload(doc_type='rf_image')
        self.assertEqual(self.complete().status_code, 200)
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


class MetaSyncTickerTests(TestCase):
    """The in-process ticker that makes the schedule fire.

    It exists because a schedule set in the CRM that depends on a server timer
    being configured to match it is a screen telling the truth about its intent
    and a lie about what will happen. The app watches its own clock instead.

    The thread itself is not started here — a background loop in a test suite is
    a source of flakes, not of confidence. What is tested is the tick it runs.
    """

    def setUp(self):
        from leads.models import IntegrationSettings, MetaSyncSchedule
        self.schedule = MetaSyncSchedule.load()
        self.schedule.enabled = True
        self.schedule.times = ['09:00', '21:00']
        self.schedule.timezone = 'Asia/Kolkata'
        self.schedule.last_checked_at = None
        self.schedule.save()
        self.a = IntegrationSettings.objects.create(
            name='Kochi', meta_page_id='111', meta_access_token='token-a')
        self.b = IntegrationSettings.objects.create(
            name='Calicut', meta_page_id='222', meta_access_token='token-b')

    @staticmethod
    def ist(y, m, d, hh, mm):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo('Asia/Kolkata'))

    @staticmethod
    def _ok():
        from leads.meta_integration import MetaImportResult
        r = MetaImportResult()
        r.imported, r.skipped = 2, 1
        return r

    def synced_at(self, integration, moment):
        from leads.models import IntegrationSettings
        IntegrationSettings.objects.filter(pk=integration.pk).update(last_synced_at=moment)

    # ── The tick ──
    def test_a_tick_syncs_every_integration_when_the_time_comes(self):
        """The whole ask: at the scheduled time, all of them import."""
        from leads import scheduler
        self.synced_at(self.a, self.ist(2026, 9, 17, 8, 0))
        self.synced_at(self.b, self.ist(2026, 9, 17, 8, 0))
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            ran = scheduler.run_due_syncs_once(now=self.ist(2026, 9, 17, 9, 0))
        self.assertEqual(ran, 2)
        self.assertEqual(call.call_count, 2)

    def test_a_tick_before_the_time_does_nothing(self):
        from leads import scheduler
        self.synced_at(self.a, self.ist(2026, 9, 17, 8, 0))
        self.synced_at(self.b, self.ist(2026, 9, 17, 8, 0))
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            ran = scheduler.run_due_syncs_once(now=self.ist(2026, 9, 17, 8, 59))
        self.assertEqual(ran, 0)
        call.assert_not_called()

    def test_a_disabled_schedule_ticks_but_never_syncs(self):
        from leads import scheduler
        self.schedule.enabled = False
        self.schedule.save()
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.assertEqual(scheduler.run_due_syncs_once(now=self.ist(2026, 9, 17, 9, 0)), 0)
            call.assert_not_called()

    # ── The heartbeat ──
    def test_every_tick_records_that_it_looked(self):
        """\"Nothing was due\" and \"nothing is watching the clock\" look identical
        without this, and the second is the one worth knowing about."""
        from leads import scheduler
        from leads.models import MetaSyncSchedule
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()):
            scheduler.run_due_syncs_once(now=self.ist(2026, 9, 17, 8, 59))
        self.assertIsNotNone(MetaSyncSchedule.load().last_checked_at)

    def test_the_heartbeat_reaches_the_api(self):
        from leads import scheduler
        admin = mk('tick_admin', 'admin')
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()):
            scheduler.run_due_syncs_once(now=self.ist(2026, 9, 17, 8, 59))
        r = self.client.get('/api/integration-settings/sync-schedule/',
                            HTTP_AUTHORIZATION=token_for(admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertIsNotNone(r.json()['last_checked_at'])

    def test_the_heartbeat_cannot_be_written_by_a_client(self):
        admin = mk('tick_admin2', 'admin')
        r = self.client.put('/api/integration-settings/sync-schedule/',
                            data={'enabled': True, 'times': ['09:00'],
                                  'timezone': 'Asia/Kolkata',
                                  'last_checked_at': '2020-01-01T00:00:00Z'},
                            content_type='application/json',
                            HTTP_AUTHORIZATION=token_for(admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        from leads.models import MetaSyncSchedule
        self.assertIsNone(MetaSyncSchedule.load().last_checked_at)

    # ── Which processes run it ──
    def test_the_ticker_stays_out_of_management_commands(self):
        """A migration or a test run must not start syncing in the background."""
        from leads import scheduler
        for argv in (['manage.py', 'migrate'], ['manage.py', 'test'],
                     ['manage.py', 'makemigrations'], ['manage.py', 'collectstatic'],
                     ['manage.py', 'sync_meta_leads']):
            with patch.object(scheduler.sys, 'argv', argv):
                self.assertFalse(scheduler.should_start(), argv)

    def test_the_ticker_runs_under_a_web_server(self):
        from leads import scheduler
        with patch.object(scheduler.sys, 'argv', ['gunicorn', 'config.wsgi:application']):
            self.assertTrue(scheduler.should_start())

    def test_the_ticker_can_be_turned_off_for_a_cron_setup(self):
        """Anyone who would rather own the scheduling on the host can."""
        from leads import scheduler
        with patch.dict(scheduler.os.environ, {'META_SYNC_SCHEDULER': '0'}):
            self.assertFalse(scheduler.should_start())

    def test_the_autoreloader_only_ticks_in_one_process(self):
        """`runserver` runs the app twice; ticking in both doubles every tick."""
        from leads import scheduler
        with patch.object(scheduler.sys, 'argv', ['manage.py', 'runserver']):
            with patch.dict(scheduler.os.environ, {'RUN_MAIN': ''}):
                self.assertFalse(scheduler.should_start())
            with patch.dict(scheduler.os.environ, {'RUN_MAIN': 'true'}):
                self.assertTrue(scheduler.should_start())


class MetaSyncScheduleTests(TestCase):
    """When the Meta sync runs — the times set in the CRM, in the zone set with them.

    The times are wall-clock times in the configured zone, so "09:00 Asia/Kolkata"
    is nine in the morning in Kerala whatever the server's own clock says. Every
    assertion here pins a real instant and asks what the schedule makes of it,
    rather than trusting the machine this happens to run on.
    """

    def setUp(self):
        from leads.models import MetaSyncSchedule
        self.schedule = MetaSyncSchedule.load()
        self.schedule.enabled = True
        self.schedule.times = ['09:00', '21:00']
        self.schedule.timezone = 'Asia/Kolkata'
        self.schedule.save()

    @staticmethod
    def ist(y, m, d, hh, mm):
        """A real instant, written in IST."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo('Asia/Kolkata'))

    def local(self, moment):
        from zoneinfo import ZoneInfo
        return moment.astimezone(ZoneInfo('Asia/Kolkata'))

    # ── Reading the schedule ──
    def test_the_defaults_are_twice_a_day_in_ist(self):
        """What the sync did before it became configurable, carried over."""
        from leads.models import MetaSyncSchedule
        MetaSyncSchedule.objects.all().delete()
        fresh = MetaSyncSchedule.load()
        self.assertEqual(fresh.times, ['09:00', '21:00'])
        self.assertEqual(fresh.timezone, 'Asia/Kolkata')
        self.assertTrue(fresh.enabled)

    def test_the_slot_is_the_most_recent_time_that_has_passed(self):
        at = self.ist(2026, 9, 17, 10, 30)
        self.assertEqual(self.local(self.schedule.last_due_at(at)), self.ist(2026, 9, 17, 9, 0))

    def test_before_the_first_time_it_is_yesterdays_last(self):
        """A machine started at 02:00 has not missed the 21:00 sync."""
        at = self.ist(2026, 9, 17, 2, 0)
        self.assertEqual(self.local(self.schedule.last_due_at(at)), self.ist(2026, 9, 16, 21, 0))

    def test_a_minute_before_the_time_the_slot_has_not_arrived(self):
        at = self.ist(2026, 9, 17, 8, 59)
        self.assertEqual(self.local(self.schedule.last_due_at(at)), self.ist(2026, 9, 16, 21, 0))

    def test_exactly_on_the_time_the_slot_has_arrived(self):
        at = self.ist(2026, 9, 17, 9, 0)
        self.assertEqual(self.local(self.schedule.last_due_at(at)), self.ist(2026, 9, 17, 9, 0))

    def test_the_next_time_is_reported_for_the_screen(self):
        at = self.ist(2026, 9, 17, 10, 30)
        self.assertEqual(self.local(self.schedule.next_due_at(at)), self.ist(2026, 9, 17, 21, 0))

    def test_after_the_last_time_the_next_is_tomorrow_morning(self):
        at = self.ist(2026, 9, 17, 22, 0)
        self.assertEqual(self.local(self.schedule.next_due_at(at)), self.ist(2026, 9, 18, 9, 0))

    def test_the_zone_is_the_one_set_not_the_servers(self):
        """09:00 New York is a different instant from 09:00 Kolkata, and the
        schedule has to mean the one that was chosen."""
        from zoneinfo import ZoneInfo
        self.schedule.timezone = 'America/New_York'
        self.schedule.times = ['09:00']
        self.schedule.save()
        # 13:30 UTC is 09:30 in New York — the slot has just passed there.
        from datetime import datetime, timezone as dt_timezone
        at = datetime(2026, 9, 17, 13, 30, tzinfo=dt_timezone.utc)
        slot = self.schedule.last_due_at(at)
        self.assertEqual(slot.astimezone(ZoneInfo('America/New_York')).hour, 9)
        # ...while in Kolkata that same instant is 19:00, well past 09:00 IST —
        # so reading the slot in the wrong zone would have given the wrong day.
        self.assertEqual(slot.astimezone(ZoneInfo('Asia/Kolkata')).hour, 18)

    def test_an_unknown_zone_falls_back_rather_than_stopping_the_sync(self):
        self.schedule.timezone = 'Mars/Olympus_Mons'
        self.schedule.save()
        self.assertIsNotNone(self.schedule.last_due_at(self.ist(2026, 9, 17, 23, 0)))

    def test_no_times_means_nothing_is_ever_due(self):
        self.schedule.times = []
        self.schedule.save()
        self.assertIsNone(self.schedule.last_due_at(self.ist(2026, 9, 17, 10, 0)))

    def test_rubbish_times_are_ignored_rather_than_crashing_the_job(self):
        self.schedule.times = ['09:00', 'tea time', '']
        self.schedule.save()
        self.assertEqual([t.strftime('%H:%M') for t in self.schedule.parsed_times()], ['09:00'])


class MetaScheduledSyncRunTests(TestCase):
    """The job the timer runs, against the schedule.

    Nothing here calls Meta — `import_meta_leads` is stubbed. What is being
    tested is when a sync fires, which is the whole point of a schedule.
    """

    def setUp(self):
        from leads.models import IntegrationSettings, MetaSyncSchedule
        self.admin = mk('sched_admin', 'admin')
        self.schedule = MetaSyncSchedule.load()
        self.schedule.enabled = True
        self.schedule.times = ['09:00', '21:00']
        self.schedule.timezone = 'Asia/Kolkata'
        self.schedule.save()
        self.integration = IntegrationSettings.objects.create(
            name='Kochi', meta_page_id='111', meta_access_token='token-a')

    @staticmethod
    def ist(y, m, d, hh, mm):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo('Asia/Kolkata'))

    @staticmethod
    def _ok(imported=2, skipped=1):
        from leads.meta_integration import MetaImportResult
        r = MetaImportResult()
        r.imported, r.skipped = imported, skipped
        return r

    def run_job(self, now=None, **kwargs):
        from leads.meta_integration import sync_due_integrations
        return sync_due_integrations(now=now, **kwargs)

    def synced_at(self, moment):
        from leads.models import IntegrationSettings
        IntegrationSettings.objects.filter(pk=self.integration.pk).update(last_synced_at=moment)
        self.integration.refresh_from_db()

    # ── Firing at the time ──
    def test_nothing_fires_before_the_time(self):
        self.synced_at(self.ist(2026, 9, 17, 8, 0))
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 8, 59))
            call.assert_not_called()

    def test_it_fires_once_the_time_has_come(self):
        self.synced_at(self.ist(2026, 9, 17, 8, 0))
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 9, 0))
            self.assertEqual(call.call_count, 1)

    # A note for whoever edits the two below. `now=` simulates the clock the
    # schedule is read against, but a real sync stamps `last_synced_at` with the
    # actual wall clock. So a test must never let one simulated run set up the
    # next — at 23:00 the stamp lands after a simulated 21:00 slot and the second
    # run finds nothing due. Both of these therefore set the stamp explicitly.

    def test_it_fires_only_once_for_a_time(self):
        """The timer runs every minute; the sync must not run every minute."""
        self.synced_at(self.ist(2026, 9, 17, 8, 0))
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 9, 0))
            self.assertEqual(call.call_count, 1)
            # Satisfied for the 09:00 slot, as a real sync would have left it.
            self.synced_at(self.ist(2026, 9, 17, 9, 0))
            call.reset_mock()
            for minute in (1, 2, 30):
                self.run_job(now=self.ist(2026, 9, 17, 9, minute))
            call.assert_not_called()

    def test_the_evening_time_fires_as_well(self):
        """The morning slot being satisfied must not swallow the evening one."""
        self.synced_at(self.ist(2026, 9, 17, 9, 1))
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 20, 59))
            call.assert_not_called()
            self.run_job(now=self.ist(2026, 9, 17, 21, 0))
            self.assertEqual(call.call_count, 1)

    def test_a_missed_time_is_caught_up_not_skipped(self):
        """Host down over 09:00: the next poll still syncs for it."""
        self.synced_at(self.ist(2026, 9, 16, 21, 5))
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 11, 30))
            self.assertEqual(call.call_count, 1)

    def test_a_manual_sync_after_the_time_satisfies_that_slot(self):
        """Pressing Sync Now at 09:05 must not be followed by the 09:00 sync."""
        self.synced_at(self.ist(2026, 9, 17, 9, 5))
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 9, 6))
            call.assert_not_called()

    def test_a_manual_sync_does_not_consume_the_next_slot(self):
        """...but the evening one still happens."""
        self.synced_at(self.ist(2026, 9, 17, 9, 5))
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 21, 0))
            self.assertEqual(call.call_count, 1)

    def test_a_never_synced_integration_fires_at_the_first_time(self):
        self.assertIsNone(self.integration.last_synced_at)
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 9, 0))
            self.assertEqual(call.call_count, 1)

    # ── Turning it off ──
    def test_a_disabled_schedule_never_fires(self):
        self.schedule.enabled = False
        self.schedule.save()
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 9, 0))
            call.assert_not_called()

    def test_no_times_never_fires(self):
        self.schedule.times = []
        self.schedule.save()
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 9, 0))
            call.assert_not_called()

    def test_force_syncs_even_with_the_schedule_off(self):
        """The manual path must not depend on the schedule being on."""
        self.schedule.enabled = False
        self.schedule.save()
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job(now=self.ist(2026, 9, 17, 9, 0), force=True)
            self.assertEqual(call.call_count, 1)

    # ── The API ──
    def test_the_schedule_is_readable(self):
        r = self.client.get('/api/integration-settings/sync-schedule/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['times'], ['09:00', '21:00'])
        self.assertEqual(r.json()['timezone'], 'Asia/Kolkata')
        self.assertIsNotNone(r.json()['next_due_at'])

    def test_the_schedule_can_be_set(self):
        r = self.client.put('/api/integration-settings/sync-schedule/',
                            data={'enabled': True, 'times': ['06:30', '18:45'],
                                  'timezone': 'Asia/Kolkata'},
                            content_type='application/json',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.times, ['06:30', '18:45'])

    def test_times_come_back_ordered_and_deduplicated(self):
        r = self.client.put('/api/integration-settings/sync-schedule/',
                            data={'enabled': True, 'times': ['21:00', '09:00', '09:00'],
                                  'timezone': 'Asia/Kolkata'},
                            content_type='application/json',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['times'], ['09:00', '21:00'])

    def test_a_time_that_is_not_a_time_is_refused(self):
        """Silently ignoring it would leave the screen showing a schedule that
        never fires."""
        r = self.client.put('/api/integration-settings/sync-schedule/',
                            data={'enabled': True, 'times': ['half past nine'],
                                  'timezone': 'Asia/Kolkata'},
                            content_type='application/json',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 400)
        self.assertIn('HH:MM', str(r.json()))

    def test_a_zone_this_server_does_not_know_is_refused(self):
        r = self.client.put('/api/integration-settings/sync-schedule/',
                            data={'enabled': True, 'times': ['09:00'],
                                  'timezone': 'Mars/Olympus_Mons'},
                            content_type='application/json',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 400)
        self.assertIn('timezone', str(r.json()).lower())

    def test_a_bde_cannot_read_or_set_the_schedule(self):
        bde = mk('sched_bde', 'bde')
        self.assertEqual(self.client.get('/api/integration-settings/sync-schedule/',
                                         HTTP_AUTHORIZATION=token_for(bde)).status_code, 403)


class MetaAutoSyncTests(TestCase):
    """What a Meta sync records, and the Sync Now button beside it.

    Meta pushes leads to the webhook as they are filled; this pull is the safety
    net for the ones that never arrived — a failed delivery, a form added while
    the webhook was misconfigured, the backlog from before a page was connected.

    Nothing here calls Meta: `import_meta_leads` is stubbed. *When* it runs is
    MetaSyncScheduleTests and MetaScheduledSyncRunTests; this is about what it
    writes down afterwards.
    """

    def setUp(self):
        from leads.models import IntegrationSettings
        self.admin = mk('meta_admin', 'admin')
        self.a = IntegrationSettings.objects.create(
            name='Kochi', meta_page_id='111', meta_access_token='token-a')
        self.b = IntegrationSettings.objects.create(
            name='Calicut', meta_page_id='222', meta_access_token='token-b')
        # Connected integrations only: one with no token has nothing to call.
        self.nc = IntegrationSettings.objects.create(name='Not connected', meta_page_id='333')

    @staticmethod
    def _ok(imported=2, skipped=1):
        from leads.meta_integration import MetaImportResult
        r = MetaImportResult()
        r.imported, r.skipped = imported, skipped
        return r

    @staticmethod
    def _failed(message='Meta says the token has expired.'):
        from leads.meta_integration import MetaImportResult
        r = MetaImportResult()
        r.errors.append(message)
        return r

    def run_job(self, **kwargs):
        from leads.meta_integration import sync_due_integrations
        return sync_due_integrations(**kwargs)

    # ── When it runs ──
    def test_an_integration_that_has_never_synced_is_due(self):
        """A scheduled time has already gone by today, and it has not synced
        for it. When that time is is MetaSyncScheduleTests' business."""
        self.assertTrue(self.a.sync_due)
        self.assertIsNotNone(self.a.next_sync_due_at)

    def test_force_syncs_whatever_the_clock_says(self):
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job()
            call.reset_mock()
            self.run_job(force=True)
            self.assertEqual(call.call_count, 2)

    def test_an_integration_with_no_token_is_left_alone(self):
        """There is nothing to call, and stamping a failure every twelve hours
        would bury the real ones."""
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()):
            self.run_job()
        self.nc.refresh_from_db()
        self.assertIsNone(self.nc.last_synced_at)
        self.assertIsNone(self.nc.last_sync_ok)

    # ── What it records ──
    def test_a_good_sync_is_recorded(self):
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok(3, 4)):
            self.run_job()
        self.a.refresh_from_db()
        self.assertTrue(self.a.last_sync_ok)
        self.assertIsNotNone(self.a.last_synced_at)
        self.assertIn('3 imported', self.a.last_sync_note)

    def test_a_failed_sync_is_recorded_just_as_loudly(self):
        """Leaving the stamp untouched on a failure reads on screen as 'never
        synced' for an integration that has been failing twice a day for a
        week."""
        with patch('leads.meta_integration.import_meta_leads', return_value=self._failed()):
            self.run_job()
        self.a.refresh_from_db()
        self.assertIsNotNone(self.a.last_synced_at)
        self.assertFalse(self.a.last_sync_ok)
        self.assertIn('expired', self.a.last_sync_note)

    def test_one_integration_blowing_up_does_not_stop_the_others(self):
        """A page with a dead token would otherwise hold up every other
        branch's leads."""
        def flaky(settings_obj, **kwargs):
            if settings_obj.pk == self.a.pk:
                raise RuntimeError('Graph API exploded')
            return self._ok()

        with patch('leads.meta_integration.import_meta_leads', side_effect=flaky):
            self.run_job()
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertFalse(self.a.last_sync_ok)
        self.assertIn('exploded', self.a.last_sync_note)
        self.assertTrue(self.b.last_sync_ok)

    # ── The manual button ──
    def test_sync_now_still_works(self):
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok(5, 0)):
            r = self.client.post(f'/api/integration-settings/{self.a.pk}/sync/',
                                 HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['imported'], 5)

    def test_sync_now_satisfies_the_time_it_follows(self):
        """Otherwise pressing the button just after a scheduled time would be
        followed by the automatic sync a minute later. The *next* scheduled
        time still fires — see MetaScheduledSyncRunTests."""
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()):
            self.client.post(f'/api/integration-settings/{self.a.pk}/sync/',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.a.refresh_from_db()
        self.assertIsNotNone(self.a.last_synced_at)
        self.assertFalse(self.a.sync_due)

        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()) as call:
            self.run_job()
            self.assertEqual([c.args[0].pk for c in call.call_args_list], [self.b.pk])

    def test_the_api_reports_the_sync_state(self):
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()):
            self.run_job()
        r = self.client.get('/api/integration-settings/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        payload = r.json()
        rows = payload if isinstance(payload, list) else payload['results']
        row = next(x for x in rows if x['id'] == self.a.pk)
        self.assertTrue(row['last_sync_ok'])
        self.assertIsNotNone(row['last_synced_at'])
        # The next scheduled time, which the schedule decides, not an interval.
        self.assertIsNotNone(row['next_sync_due_at'])

    def test_saving_the_form_cannot_fake_a_sync(self):
        """The stamps belong to the sync; a client editing a token must not be
        able to write them."""
        r = self.client.patch(f'/api/integration-settings/{self.a.pk}/',
                              data={'last_sync_ok': True, 'last_sync_note': 'faked'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.a.refresh_from_db()
        self.assertIsNone(self.a.last_sync_ok)
        self.assertEqual(self.a.last_sync_note, '')

    # ── The command ──
    def test_the_command_reports_failures_with_a_non_zero_exit(self):
        """A systemd timer only tells anyone if the job exits non-zero."""
        from django.core.management import call_command
        with patch('leads.meta_integration.import_meta_leads', return_value=self._failed()):
            with self.assertRaises(SystemExit):
                call_command('sync_meta_leads', verbosity=0)

    def test_the_command_is_quiet_when_all_is_well(self):
        from django.core.management import call_command
        with patch('leads.meta_integration.import_meta_leads', return_value=self._ok()):
            call_command('sync_meta_leads', verbosity=0)   # must not raise
        self.a.refresh_from_db()
        self.assertTrue(self.a.last_sync_ok)

    def test_a_dry_run_calls_nothing(self):
        from django.core.management import call_command
        with patch('leads.meta_integration.import_meta_leads') as call:
            call_command('sync_meta_leads', dry_run=True, verbosity=0)
            call.assert_not_called()
        self.a.refresh_from_db()
        self.assertIsNone(self.a.last_synced_at)


class KsebFeasibilitySuperAdminTests(TestCase):
    """The super admin editing or deleting a KSEB feasibility.

    Completing the feasibility locks it: it is what lets the customer be pushed
    to purchase, and accounts takes a copy of its dates. Correcting it after that
    is an override, and it sits with the super admin alone — the same rule as the
    site-visit and liasoning unlocks.
    """

    def setUp(self):
        from .models import PaymentVerification, SiteVisit
        self.superadmin = mk('fsa_super', 'superadmin')
        self.admin = mk('fsa_admin', 'admin')
        self.bde = mk('fsa_bde', 'bde')
        self.lead = Lead.objects.create(
            first_name='Manikantan', last_name='Nair', phone='9895271491',
            status='converted', value=Decimal('240000'), bde=self.bde)
        self.sv = SiteVisit.objects.create(
            lead=self.lead, po_signed_date=date(2026, 8, 10),
            kseb_feasibility_taken='yes', kseb_feasibility_date=date(2026, 9, 22),
            kseb_feasibility_complete=True)
        self.pv = PaymentVerification.objects.create(
            lead=self.lead, po_date=date(2026, 8, 10), kseb_feasibility_date=date(2026, 9, 22))

    def url(self, suffix=''):
        return f'/api/leads/{self.lead.id}/kseb-feasibility/{suffix}'

    def patch(self, user, **data):
        return self.client.patch(self.url(), data=data, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(user))

    def delete(self, user):
        return self.client.delete(self.url(), HTTP_AUTHORIZATION=token_for(user))

    def add_receipt(self, user):
        return self.client.post(
            self.url('documents/'),
            data={'file': SimpleUploadedFile('receipt.jpg', b'jpeg bytes', content_type='image/jpeg')},
            HTTP_AUTHORIZATION=token_for(user))

    def receipt(self):
        from .models import SiteVisitDocument
        doc = SiteVisitDocument(site_visit=self.sv, doc_type='kseb_feasibility_receipt')
        doc.file.save('receipt.jpg', SimpleUploadedFile('receipt.jpg', b'jpeg bytes'), save=True)
        return doc

    # ── The lock still holds for everyone else ──
    def test_the_bde_cannot_edit_a_completed_feasibility(self):
        r = self.patch(self.bde, kseb_feasibility_date='2026-09-25')
        self.assertEqual(r.status_code, 400, r.content[:200])
        self.assertIn('locked', r.json()['error'])

    def test_an_admin_is_not_the_super_admin(self):
        r = self.patch(self.admin, kseb_feasibility_date='2026-09-25')
        self.assertEqual(r.status_code, 400, r.content[:200])

    # ── Editing ──
    def test_the_super_admin_can_edit_a_completed_feasibility(self):
        r = self.patch(self.superadmin, kseb_feasibility_date='2026-09-25')
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.sv.refresh_from_db()
        self.assertEqual(self.sv.kseb_feasibility_date, date(2026, 9, 25))
        self.assertTrue(self.sv.kseb_feasibility_complete)

    def test_the_correction_reaches_accounts(self):
        """Accounts copied the dates on completion; left alone it would keep
        the wrong one for ever."""
        self.patch(self.superadmin, po_signed_date='2026-08-12', kseb_feasibility_date='2026-09-25')
        self.pv.refresh_from_db()
        self.assertEqual(self.pv.po_date, date(2026, 8, 12))
        self.assertEqual(self.pv.kseb_feasibility_date, date(2026, 9, 25))

    def test_an_edit_is_logged(self):
        from .models import ActivityLog
        self.patch(self.superadmin, kseb_feasibility_date='2026-09-25')
        self.assertTrue(ActivityLog.objects.filter(
            lead=self.lead, description__icontains='feasibility edited').exists())

    def test_an_edit_cannot_hollow_out_a_completed_record(self):
        """Blanking the date would leave it locked and complete with nothing
        behind it — clearing is what delete is for."""
        r = self.patch(self.superadmin, kseb_feasibility_date='')
        self.assertEqual(r.status_code, 400)
        self.assertIn('kseb_feasibility_date', r.json()['missing'])
        r = self.patch(self.superadmin, kseb_feasibility_taken='no')
        self.assertEqual(r.status_code, 400)
        self.sv.refresh_from_db()
        self.assertEqual(self.sv.kseb_feasibility_taken, 'yes')

    # ── Receipts on a completed record ──
    def test_the_super_admin_can_add_a_receipt_to_a_completed_record(self):
        self.assertEqual(self.add_receipt(self.superadmin).status_code, 201)

    def test_the_bde_still_cannot(self):
        self.assertEqual(self.add_receipt(self.bde).status_code, 400)

    def test_the_bde_can_no_longer_delete_a_receipt_from_a_completed_record(self):
        """This used to ignore the lock: the evidence could be stripped off a
        signed-off feasibility by the person who signed it."""
        doc = self.receipt()
        r = self.client.delete(self.url(f'documents/{doc.id}/'), HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 400)
        from .models import SiteVisitDocument
        self.assertTrue(SiteVisitDocument.objects.filter(pk=doc.pk).exists())

    def test_the_super_admin_can_delete_a_receipt_from_a_completed_record(self):
        doc = self.receipt()
        r = self.client.delete(self.url(f'documents/{doc.id}/'),
                               HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertEqual(r.status_code, 204)

    # ── Deleting ──
    def test_the_super_admin_can_delete_the_feasibility(self):
        self.receipt()
        r = self.delete(self.superadmin)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.sv.refresh_from_db()
        self.assertIsNone(self.sv.po_signed_date)
        self.assertEqual(self.sv.kseb_feasibility_taken, '')
        self.assertIsNone(self.sv.kseb_feasibility_date)
        self.assertFalse(self.sv.kseb_feasibility_complete)
        self.assertFalse(self.sv.documents.filter(doc_type='kseb_feasibility_receipt').exists())

    def test_deleting_clears_the_dates_from_accounts(self):
        """A payment record quoting a feasibility that no longer exists would be
        worse than one quoting none."""
        self.delete(self.superadmin)
        self.pv.refresh_from_db()
        self.assertIsNone(self.pv.po_date)
        self.assertIsNone(self.pv.kseb_feasibility_date)

    def test_deleting_is_logged(self):
        from .models import ActivityLog
        self.delete(self.superadmin)
        self.assertTrue(ActivityLog.objects.filter(
            lead=self.lead, description__icontains='feasibility deleted').exists())

    def test_only_the_super_admin_can_delete(self):
        self.assertEqual(self.delete(self.bde).status_code, 403)
        self.assertEqual(self.delete(self.admin).status_code, 403)
        self.sv.refresh_from_db()
        self.assertTrue(self.sv.kseb_feasibility_complete)

    def test_deleting_nothing_says_so(self):
        self.delete(self.superadmin)
        r = self.delete(self.superadmin)
        self.assertEqual(r.status_code, 404)

    def test_a_customer_already_with_purchase_stays_there(self):
        """Pulling them back out of procurement is not something clearing a form
        should do quietly."""
        Lead.objects.filter(pk=self.lead.pk).update(pushed_to_purchase=True)
        r = self.delete(self.superadmin)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['pushed_to_purchase'])
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_purchase)

    def test_the_answer_says_whether_the_customer_is_still_on_the_list(self):
        r = self.delete(self.superadmin)
        self.assertFalse(r.json()['still_in_queue'])     # no PO date, not in documentation

    def test_a_customer_in_documentation_stays_on_the_list(self):
        Lead.objects.filter(pk=self.lead.pk).update(pushed_to_documentation=True)
        r = self.delete(self.superadmin)
        self.assertTrue(r.json()['still_in_queue'])

    # ── What the screen is told ──
    def test_only_the_super_admin_is_offered_the_controls(self):
        r = self.client.get(self.url(), HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertTrue(r.json()['can_manage'])
        r = self.client.get(self.url(), HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertFalse(r.json()['can_manage'])


class ReopenSiteVisitTests(TestCase):
    """A super admin unlocking a signed-off site visit.

    The case this exists for is a correction found downstream: documentation
    notice the capacity is wrong days after the BDE signed off and the customer
    was handed over. The unlock puts the survey back in the BDE's hands without
    pulling the customer back out of documentation, and what they fix has to
    reach the stages that already took a copy of it.
    """

    def setUp(self):
        from .models import PaymentVerification, SiteVisit
        self.superadmin = mk('rsv_super', 'superadmin')
        self.admin = mk('rsv_admin', 'admin')
        self.bde = mk('rsv_bde', 'bde')
        self.lead = Lead.objects.create(
            first_name='Reopen', last_name='Case', phone='9895271489',
            status='converted', value=Decimal('200000'), bde=self.bde,
            pushed_to_documentation=True, pushed_to_documentation_at=timezone.now())
        self.sv = SiteVisit.objects.create(
            lead=self.lead, site_visit_complete=True, plant_capacity='5 kW',
            po_signed_date=date(2026, 8, 1), kseb_feasibility_date=date(2026, 8, 5))
        # Accounts already holds the dates it was handed when feasibility closed.
        self.pv = PaymentVerification.objects.create(
            lead=self.lead, po_date=date(2026, 8, 1), kseb_feasibility_date=date(2026, 8, 5))

    def reopen(self, user):
        return self.client.post(f'/api/leads/{self.lead.id}/reopen-site-visit/',
                                HTTP_AUTHORIZATION=token_for(user))

    def patch_sv(self, user, **data):
        return self.client.patch(f'/api/leads/{self.lead.id}/site-visit/', data=data,
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(user))

    def can_edit(self, user):
        r = self.client.get(f'/api/leads/{self.lead.id}/', HTTP_AUTHORIZATION=token_for(user))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()['can_edit_site_visit']

    # ── The lock ──
    def test_the_bde_is_locked_out_once_it_reaches_documentation(self):
        self.assertFalse(self.can_edit(self.bde))
        self.assertEqual(self.patch_sv(self.bde, plant_capacity='7 kW').status_code, 403)

    def test_only_the_super_admin_can_reopen(self):
        self.assertEqual(self.reopen(self.bde).status_code, 403)
        self.assertEqual(self.reopen(self.admin).status_code, 403)
        self.assertEqual(self.reopen(self.superadmin).status_code, 200)

    # ── The unlock ──
    def test_reopening_hands_the_survey_back_to_the_bde(self):
        """An unlock only the super admin could then type into would mean the
        BDE reading the roof down the phone to someone at a desk."""
        self.assertEqual(self.reopen(self.superadmin).status_code, 200)
        self.sv.refresh_from_db()
        self.assertFalse(self.sv.site_visit_complete)
        self.assertIsNotNone(self.sv.reopened_at)
        self.assertEqual(self.sv.reopened_by, self.superadmin)
        self.assertTrue(self.can_edit(self.bde))
        self.assertEqual(self.patch_sv(self.bde, plant_capacity='7.5 kW').status_code, 200)

    def test_the_customer_stays_in_documentation(self):
        """Reopening corrects a survey; it does not undo the hand-off."""
        self.reopen(self.superadmin)
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.pushed_to_documentation)

    def test_reopening_is_logged_against_the_lead(self):
        from .models import ActivityLog
        self.reopen(self.superadmin)
        note = (ActivityLog.objects.filter(lead=self.lead, description__icontains='reopened')
                .order_by('-id').first())
        self.assertIsNotNone(note)
        self.assertIn('documentation', note.description)

    def test_reopening_twice_says_it_is_already_open(self):
        self.assertEqual(self.reopen(self.superadmin).status_code, 200)
        r = self.reopen(self.superadmin)
        self.assertEqual(r.status_code, 400)
        self.assertIn('already open', r.json()['error'])

    # ── The correction reaching the stages that copied it ──
    def test_a_corrected_po_date_reaches_accounts(self):
        """Accounts took a copy when the feasibility closed. Left alone it would
        hold the old date for ever."""
        self.reopen(self.superadmin)
        r = self.patch_sv(self.bde, po_signed_date='2026-08-20', kseb_feasibility_date='2026-08-22')
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.pv.refresh_from_db()
        self.assertEqual(self.pv.po_date, date(2026, 8, 20))
        self.assertEqual(self.pv.kseb_feasibility_date, date(2026, 8, 22))

    def test_a_corrected_price_still_recomputes_the_deal_value(self):
        self.reopen(self.superadmin)
        r = self.patch_sv(self.bde, product_price='300000', discount='25000')
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.value, Decimal('275000'))

    def test_a_lead_with_no_accounts_record_is_not_given_one(self):
        """Editing a survey must not push a customer into the accounts queue as
        a side effect."""
        from .models import PaymentVerification, SiteVisit
        other = Lead.objects.create(first_name='No', last_name='Accounts', phone='9895271490',
                                    bde=self.bde, pushed_to_documentation=True)
        SiteVisit.objects.create(lead=other, site_visit_complete=True)
        self.client.post(f'/api/leads/{other.id}/reopen-site-visit/',
                         HTTP_AUTHORIZATION=token_for(self.superadmin))
        r = self.client.patch(f'/api/leads/{other.id}/site-visit/',
                              data={'po_signed_date': '2026-08-20'}, content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertFalse(PaymentVerification.objects.filter(lead=other).exists())

    # ── Closing it again ──
    def test_signing_off_again_locks_the_bde_back_out(self):
        self.reopen(self.superadmin)
        self.assertTrue(self.can_edit(self.bde))
        r = self.patch_sv(self.bde, site_visit_complete=True)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.sv.refresh_from_db()
        self.assertIsNone(self.sv.reopened_at)
        self.assertFalse(self.can_edit(self.bde))

    def test_the_lead_payload_tells_the_screen_what_to_show(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/', HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertTrue(r.json()['can_reopen_site_visit'])
        self.assertFalse(r.json()['site_visit_reopened'])
        self.reopen(self.superadmin)
        r = self.client.get(f'/api/leads/{self.lead.id}/', HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertFalse(r.json()['can_reopen_site_visit'])
        self.assertTrue(r.json()['site_visit_reopened'])


class ProjectWorkTeamTests(TestCase):
    """Who actually went to site for each half of the job.

    Free text rather than a user link: a fitting crew is usually a contractor's
    name, and nobody on it holds a CRM login.
    """

    def setUp(self):
        from .models import Project
        self.pm = mk('pwt_pm', 'project_manager')
        self.lead = Lead.objects.create(
            first_name='Ahsal', last_name='N', phone='9895271488',
            status='converted', value=Decimal('235000'),
            pushed_to_project=True, pushed_to_project_at=timezone.now(),
            project_manager=self.pm)
        self.project = Project.objects.create(lead=self.lead)

    def patch(self, **data):
        return self.client.patch(f'/api/leads/{self.lead.id}/project-record/',
                                 data=data, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(self.pm))

    def record(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/project-record/',
                            HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def test_both_teams_are_saved_and_read_back(self):
        r = self.patch(structure_work_team='Rajan & crew',
                       electrical_work_team='Volt Electricals')
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.project.refresh_from_db()
        self.assertEqual(self.project.structure_work_team, 'Rajan & crew')
        self.assertEqual(self.project.electrical_work_team, 'Volt Electricals')
        d = self.record()
        self.assertEqual(d['structure_work_team'], 'Rajan & crew')
        self.assertEqual(d['electrical_work_team'], 'Volt Electricals')

    def test_they_start_empty_rather_than_null(self):
        """The form binds them to a text input, which cannot hold null."""
        d = self.record()
        self.assertEqual(d['structure_work_team'], '')
        self.assertEqual(d['electrical_work_team'], '')

    def test_a_team_can_be_cleared(self):
        """A crew booked to the wrong job has to be removable."""
        self.patch(structure_work_team='Wrong crew')
        self.assertEqual(self.patch(structure_work_team='').status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.structure_work_team, '')

    def test_the_dates_still_save_alongside_them(self):
        """The client sends both in one PATCH — dates as null when blank, teams
        as an empty string — so the two must not tread on each other."""
        r = self.client.patch(
            f'/api/leads/{self.lead.id}/project-record/',
            data={'structure_work_start_date': '2026-09-09',
                  'structure_work_completed_date': None,
                  'structure_work_team': 'Rajan & crew'},
            content_type='application/json', HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.project.refresh_from_db()
        self.assertEqual(self.project.structure_work_start_date.isoformat(), '2026-09-09')
        self.assertIsNone(self.project.structure_work_completed_date)
        self.assertEqual(self.project.structure_work_team, 'Rajan & crew')

    def test_they_lock_with_the_rest_of_the_record(self):
        """A completed project is closed to editing, and a new field must not be
        a way around that."""
        self.project.is_complete = True
        self.project.completed_at = timezone.now()
        self.project.save()
        r = self.patch(structure_work_team='Slipped in')
        self.assertEqual(r.status_code, 400, r.content[:200])
        self.project.refresh_from_db()
        self.assertEqual(self.project.structure_work_team, '')


class OverdueProjectsModuleTests(TestCase):
    """Overdue Projects is its own module: its own queue, its own permission key,
    and its own sidebar count â€” the count going up is what pops the notice at the
    project team."""

    def setUp(self):
        from .models import Project
        self.pm = mk('op_pm', 'project_manager')
        self.other_pm = mk('op_pm2', 'project_manager')
        self.superadmin = mk('op_super', 'superadmin')
        self.superadmin.is_superuser = True
        self.superadmin.is_staff = True
        self.superadmin.save()

        self.late = self.project_for('Asha', '9895271487', self.pm, paid_days_ago=30)
        self.on_time = self.project_for('Bina', '9895271488', self.pm, paid_days_ago=5)
        self.someone_elses = self.project_for('Chandra', '9895271489', self.other_pm,
                                              paid_days_ago=40)

    def project_for(self, name, phone, manager, paid_days_ago):
        from .models import Project
        lead = Lead.objects.create(
            first_name=name, phone=phone, status='converted', value=Decimal('225000'),
            pushed_to_project=True, pushed_to_project_at=timezone.now(),
            project_manager=manager)
        Project.objects.create(lead=lead)
        pv = PaymentVerification.objects.create(
            lead=lead, amount_received=Decimal('50000'), payment_mode='upi',
            utr_details='X1', is_complete=True)
        when = timezone.now() - timedelta(days=paid_days_ago)
        PaymentVerification.objects.filter(pk=pv.pk).update(completed_at=when, created_at=when)
        return lead

    def queue(self, user=None):
        r = self.client.get('/api/leads/project-overdue/',
                            HTTP_AUTHORIZATION=token_for(user or self.pm))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    def counts(self, user=None):
        r = self.client.get('/api/leads/module-counts/',
                            HTTP_AUTHORIZATION=token_for(user or self.pm))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()

    # â”€â”€ The queue â”€â”€
    def test_the_queue_holds_only_overdue_projects(self):
        rows = self.queue(self.superadmin)
        self.assertEqual({r['first_name'] for r in rows}, {'Asha', 'Chandra'})
        self.assertTrue(all(r['project_overdue'] for r in rows))

    def test_a_project_manager_sees_only_their_own(self):
        self.assertEqual([r['first_name'] for r in self.queue()], ['Asha'])

    def test_the_worst_overdue_comes_first(self):
        rows = self.queue(self.superadmin)
        self.assertEqual([r['first_name'] for r in rows], ['Chandra', 'Asha'])

    def test_a_completed_project_drops_out_even_if_it_was_late(self):
        from .models import Project
        Project.objects.filter(lead=self.late).update(is_complete=True,
                                                      completed_at=timezone.now())
        self.assertEqual(self.queue(), [])

    def test_a_released_project_leaves_the_queue(self):
        r = self.client.post(f'/api/leads/{self.late.id}/release-project/',
                             HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(self.queue(), [])

    def test_someone_with_no_project_access_is_refused(self):
        r = self.client.get('/api/leads/project-overdue/',
                            HTTP_AUTHORIZATION=token_for(mk('op_bde', 'bde')))
        self.assertEqual(r.status_code, 403)

    # â”€â”€ The count, which is what raises the pop-up â”€â”€
    def test_the_module_has_its_own_count(self):
        body = self.counts()
        self.assertEqual(body['counts']['project-overdue'], 1)
        # Assigned to them by name, so the notice is theirs and not just ambient.
        self.assertEqual(body['assigned']['project-overdue'], 1)

    def test_the_count_is_scoped_like_the_queue(self):
        self.assertEqual(self.counts(self.superadmin)['counts']['project-overdue'], 2)
        self.assertEqual(self.counts(self.other_pm)['counts']['project-overdue'], 1)

    def test_the_count_rises_when_a_project_crosses_its_deadline(self):
        """0 -> 1 is the signal the client turns into the pop-up."""
        before = self.counts(self.other_pm)['counts']['project-overdue']
        self.assertEqual(before, 1)
        fresh = self.project_for('Devi', '9895271490', self.other_pm, paid_days_ago=5)
        self.assertEqual(self.counts(self.other_pm)['counts']['project-overdue'], 1)
        # The clock runs out.
        PaymentVerification.objects.filter(lead=fresh).update(
            completed_at=timezone.now() - timedelta(days=30),
            created_at=timezone.now() - timedelta(days=30))
        self.assertEqual(self.counts(self.other_pm)['counts']['project-overdue'], 2)

    def test_the_count_clears_once_the_row_has_been_opened(self):
        """Opening the customer in this module stops it counting, like everywhere."""
        r = self.client.post(f'/api/leads/{self.late.id}/seen/',
                             data={'modules': ['project', 'project-overdue']},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(self.counts()['counts']['project-overdue'], 0)

    def test_an_overdue_project_is_no_longer_in_the_project_queue_count(self):
        """It has moved modules â€” the working queue should not double-count it."""
        r = self.client.get('/api/leads/project/', HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 200)
        rows = {x['first_name']: x for x in r.json()}
        # The payload still tells the truth about both, so the client can move
        # the row to the other module and say where it went.
        self.assertTrue(rows['Asha']['project_overdue'])
        self.assertFalse(rows['Bina']['project_overdue'])

    # â”€â”€ The permission key â”€â”€
    def test_a_custom_role_can_be_given_the_module_on_its_own(self):
        from users.permission_catalog import ALL_PERMISSION_KEYS
        self.assertIn('project-overdue', ALL_PERMISSION_KEYS)

    def test_the_release_still_belongs_to_the_super_admin_alone(self):
        r = self.client.post(f'/api/leads/{self.late.id}/release-project/',
                             HTTP_AUTHORIZATION=token_for(self.pm))
        self.assertEqual(r.status_code, 403)
        self.assertEqual([x['first_name'] for x in self.queue()], ['Asha'])


class MetaLeadNamingTests(TestCase):
    """A lead must never be filed under its campaign's, ad's or form's name.

    Meta returns the campaign, ad and form names on the same payload as the lead.
    When one of those reached the name field, every lead in a batch arrived called
    the same thing â€” and deleting the leads did not help, because the next import
    read the same records from Meta and named them the same way again.
    """

    def payload(self, **extra):
        base = {'id': '99001', 'created_time': '2026-07-07T10:00:00+0000',
                'campaign_id': '120', 'campaign_name': 'Kerala ad 07/07/2026 campaign ad',
                'ad_id': '77', 'ad_name': 'Kerala ad 07/07/2026 campaign ad'}
        base.update(extra)
        return base

    def field(self, name, value):
        return {'name': name, 'values': [value]}

    # â”€â”€ The reported bug â”€â”€
    def test_a_lead_is_not_named_after_its_campaign(self):
        """The payload carries a `name` that belongs to the ad, not the person."""
        lead, dup = create_lead_from_meta_payload(
            self.payload(name='Kerala ad 07/07/2026 campaign ad',
                         phone_number='+919961131767'))
        self.assertFalse(dup)
        self.assertNotEqual(lead.first_name, 'Kerala')
        self.assertEqual((lead.first_name, lead.last_name), ('Meta Lead', ''))
        # The campaign is still recorded â€” refusing the name loses nothing.
        self.assertEqual(lead.meta_campaign_name, 'Kerala ad 07/07/2026 campaign ad')

    def test_the_split_no_longer_turns_an_ad_name_into_a_first_and_last_name(self):
        """'Kerala ad ...' used to become first='Kerala', last='ad ...' â€” the KA
        initials the leads list was showing."""
        lead, _ = create_lead_from_meta_payload(
            self.payload(field_data=[self.field('full_name', 'Kerala ad 07/07/2026 campaign ad'),
                                     self.field('phone_number', '+919961131767')]))
        self.assertEqual((lead.first_name, lead.last_name), ('Meta Lead', ''))

    def test_a_form_name_in_the_name_field_is_refused_too(self):
        lead, _ = create_lead_from_meta_payload(
            self.payload(campaign_name='', ad_name='', form_name='Solar enquiry form',
                         field_data=[self.field('full_name', 'Solar enquiry form')]))
        self.assertEqual(lead.first_name, 'Meta Lead')

    def test_the_match_ignores_case_and_spacing(self):
        lead, _ = create_lead_from_meta_payload(
            self.payload(field_data=[self.field('full_name', 'kerala  AD 07/07/2026   Campaign Ad')]))
        self.assertEqual(lead.first_name, 'Meta Lead')

    def test_re_importing_after_a_delete_still_refuses_the_name(self):
        """Deleting the leads and importing again was the user's workaround; the
        same records come back from Meta, so the fix has to hold on re-import."""
        lead, _ = create_lead_from_meta_payload(
            self.payload(name='Kerala ad 07/07/2026 campaign ad'))
        Lead.objects.filter(pk=lead.pk).delete()
        again, dup = create_lead_from_meta_payload(
            self.payload(name='Kerala ad 07/07/2026 campaign ad'))
        self.assertFalse(dup)
        self.assertEqual(again.first_name, 'Meta Lead')

    # â”€â”€ Real names still come through â”€â”€
    def test_a_real_full_name_is_still_split_into_first_and_last(self):
        lead, _ = create_lead_from_meta_payload(
            self.payload(field_data=[self.field('full_name', 'Asha Devi T'),
                                     self.field('phone_number', '+919895271487'),
                                     self.field('email', 'asha@example.com')]))
        self.assertEqual((lead.first_name, lead.last_name), ('Asha', 'Devi T'))
        self.assertEqual(lead.phone, '+919895271487')

    def test_separate_first_and_last_name_fields_are_kept(self):
        lead, _ = create_lead_from_meta_payload(
            self.payload(field_data=[self.field('first_name', 'Asha'),
                                     self.field('last_name', 'Devi T')]))
        self.assertEqual((lead.first_name, lead.last_name), ('Asha', 'Devi T'))

    def test_a_customer_who_happens_to_share_a_word_with_the_ad_is_untouched(self):
        """Only an exact match is refused â€” 'Kerala' alone is a plausible name."""
        lead, _ = create_lead_from_meta_payload(
            self.payload(field_data=[self.field('full_name', 'Kerala Kumar')]))
        self.assertEqual((lead.first_name, lead.last_name), ('Kerala', 'Kumar'))

    def test_a_nameless_lead_is_still_filed_as_meta_lead(self):
        lead, _ = create_lead_from_meta_payload(
            self.payload(field_data=[self.field('phone_number', '+919961131767')]))
        self.assertEqual(lead.first_name, 'Meta Lead')
        self.assertEqual(lead.phone, '+919961131767')

    # â”€â”€ The helper itself â”€â”€
    def test_the_guard_only_fires_on_an_actual_match(self):
        self.assertTrue(is_ad_metadata_name('Kerala Ad', 'kerala ad'))
        self.assertFalse(is_ad_metadata_name('Asha Devi', 'Kerala ad'))
        self.assertFalse(is_ad_metadata_name('', 'Kerala ad'))
        self.assertFalse(is_ad_metadata_name('Kerala ad', ''))


class LeadCsvImportNamingTests(TestCase):
    """The CSV importer reads the name column that actually has something in it."""

    def setUp(self):
        self.admin = mk('csv_admin', 'superadmin')
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save()

    def upload(self, text, campaign_id=None):
        from django.core.files.uploadedfile import SimpleUploadedFile
        data = {'file': SimpleUploadedFile('leads.csv', text.encode('utf-8'), content_type='text/csv')}
        if campaign_id:
            data['campaign_id'] = campaign_id
        return self.client.post('/api/leads/bulk_upload/', data=data,
                                HTTP_AUTHORIZATION=token_for(self.admin))

    def test_a_blank_first_name_column_no_longer_hides_a_filled_name_column(self):
        """Both columns present, only one filled â€” the row used to be skipped."""
        r = self.upload('First Name,Name,Phone\n,Asha Devi,9895271487\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(Lead.objects.filter(first_name='Asha Devi').exists())

    def test_a_meta_style_export_imports_instead_of_being_rejected(self):
        """`full_name` is what Meta calls it; the file used to import nothing."""
        r = self.upload('created_time,campaign_name,full_name,phone_number\n'
                        '2026-07-07,Kerala ad,Asha Devi,9895271487\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        lead = Lead.objects.get(phone='9895271487')
        self.assertEqual(lead.first_name, 'Asha Devi')

    def test_an_explicit_first_name_still_wins_over_full_name(self):
        r = self.upload('first_name,last_name,full_name,phone\nAsha,Devi,Ignore Me,9895271487\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        lead = Lead.objects.get(phone='9895271487')
        self.assertEqual((lead.first_name, lead.last_name), ('Asha', 'Devi'))

    def test_a_row_with_no_name_anywhere_is_still_skipped(self):
        r = self.upload('First Name,Phone\n,9895271487\n')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Lead.objects.filter(phone='9895271487').exists())

    def test_importing_into_a_campaign_does_not_rename_the_leads(self):
        """The reported flow, on the CSV side: the campaign link must not touch
        the name."""
        from campaigns.models import Campaign
        campaign = Campaign.objects.create(name='Kerala ad 07/07/2026 campaign ad',
                                           campaign_type='advertisement', status='active')
        r = self.upload('Name,Phone\nAsha Devi,9895271487\n', campaign_id=campaign.id)
        self.assertEqual(r.status_code, 200, r.content[:300])
        lead = Lead.objects.get(phone='9895271487')
        self.assertEqual(lead.first_name, 'Asha Devi')
        self.assertIn(lead, campaign.leads.all())



class FixAdNamedLeadsCommandTests(TestCase):
    """Repairing the leads already stored under their campaign's name.

    The importer fix stops it happening again; it cannot rewrite rows that are
    already there, so those need a pass of their own.
    """

    AD = 'Kerala ad 07/07/2026 campaign ad'

    def run_command(self, **kwargs):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('fix_ad_named_leads', stdout=out, **kwargs)
        return out.getvalue()

    def meta_lead(self, first, last='', campaign=None, phone='9895271487', source='meta_ads'):
        return Lead.objects.create(
            first_name=first, last_name=last, phone=phone, source=source,
            meta_campaign_name=campaign if campaign is not None else self.AD)

    def test_a_lead_named_after_its_campaign_is_cleared(self):
        lead = self.meta_lead('Kerala', 'ad 07/07/2026 campaign ad')
        self.run_command()
        lead.refresh_from_db()
        self.assertEqual((lead.first_name, lead.last_name), ('Meta Lead', ''))
        # What the caller actually needs is untouched.
        self.assertEqual(lead.phone, '9895271487')
        self.assertEqual(lead.meta_campaign_name, self.AD)

    def test_a_real_customer_is_left_alone(self):
        lead = self.meta_lead('Asha', 'Devi T')
        self.run_command()
        lead.refresh_from_db()
        self.assertEqual((lead.first_name, lead.last_name), ('Asha', 'Devi T'))

    def test_a_name_sharing_a_word_with_the_ad_is_left_alone(self):
        lead = self.meta_lead('Kerala', 'Kumar')
        self.run_command()
        lead.refresh_from_db()
        self.assertEqual((lead.first_name, lead.last_name), ('Kerala', 'Kumar'))

    def test_a_dry_run_reports_without_writing(self):
        lead = self.meta_lead('Kerala', 'ad 07/07/2026 campaign ad')
        output = self.run_command(dry_run=True)
        self.assertIn('1 lead(s) named after their own campaign', output)
        self.assertIn('Dry run', output)
        lead.refresh_from_db()
        self.assertEqual(lead.first_name, 'Kerala')

    def test_the_source_does_not_matter_only_the_name(self):
        """Restricting this to Meta-sourced leads would miss the ones that came
        in by CSV — which is how a batch can arrive named after its campaign
        without the Meta importer being involved at all."""
        lead = self.meta_lead('Kerala', 'ad 07/07/2026 campaign ad', source='manual')
        self.run_command()
        lead.refresh_from_db()
        self.assertEqual((lead.first_name, lead.last_name), ('Meta Lead', ''))

    def test_a_lead_with_no_campaign_recorded_is_skipped(self):
        """Without the campaign name there is nothing to compare against."""
        lead = self.meta_lead('Kerala', 'ad 07/07/2026 campaign ad', campaign='')
        self.run_command()
        lead.refresh_from_db()
        self.assertEqual(lead.first_name, 'Kerala')

    def test_a_whole_batch_is_repaired_at_once(self):
        for n in range(5):
            self.meta_lead('Kerala', 'ad 07/07/2026 campaign ad', phone=f'98952714{n:02d}')
        self.meta_lead('Asha', 'Devi T', phone='9000000000')
        self.run_command()
        self.assertEqual(Lead.objects.filter(first_name='Meta Lead').count(), 5)
        self.assertTrue(Lead.objects.filter(first_name='Asha').exists())

    def test_running_it_twice_changes_nothing_the_second_time(self):
        self.meta_lead('Kerala', 'ad 07/07/2026 campaign ad')
        self.run_command()
        output = self.run_command()
        self.assertIn('No leads are named after their campaign', output)

    def test_it_says_so_when_there_is_nothing_to_do(self):
        self.meta_lead('Asha', 'Devi T')
        self.assertIn('No leads are named after their campaign', self.run_command())


class LeadCsvImportRobustnessTests(TestCase):
    """A CSV that is slightly wrong must not lose the rows that are fine.

    A single over-long cell used to abort the whole upload with a database error
    the client could only report as "Upload failed" â€” one 191-character surname
    in a 93-row file lost all 93 of them.
    """

    def setUp(self):
        self.admin = mk('imp_admin', 'superadmin')
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save()

    def upload(self, text):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(
            '/api/leads/bulk_upload/',
            data={'file': SimpleUploadedFile('leads.csv', text.encode('utf-8'),
                                             content_type='text/csv')},
            HTTP_AUTHORIZATION=token_for(self.admin))

    # â”€â”€ The reported failure â”€â”€
    def test_an_over_long_surname_no_longer_fails_the_whole_file(self):
        long_last = 'Paikkaden ' + ('very good treatment ' * 12)   # ~250 chars
        r = self.upload('first_name,last_name,phone\n'
                        'Asha,Devi T,9895271487\n'
                        f'Khader,{long_last},9995418857\n'
                        'Reji,V N,9645096015\n')
        self.assertEqual(r.status_code, 200, r.content[:400])
        self.assertEqual(Lead.objects.count(), 3)
        # The good rows are intact and the long one is stored clipped, not lost.
        self.assertTrue(Lead.objects.filter(first_name='Asha').exists())
        self.assertTrue(Lead.objects.filter(first_name='Reji').exists())
        khader = Lead.objects.get(first_name='Khader')
        self.assertEqual(len(khader.last_name), 100)
        self.assertTrue(khader.last_name.startswith('Paikkaden'))

    def test_the_response_says_how_many_rows_were_shortened(self):
        r = self.upload('first_name,last_name,phone\n'
                        f'Khader,{"x" * 250},9995418857\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['truncated'], 1)
        self.assertIn('shortened', r.json()['message'])

    def test_a_clean_file_reports_nothing_shortened(self):
        r = self.upload('first_name,last_name,phone\nAsha,Devi T,9895271487\n')
        self.assertEqual(r.json()['truncated'], 0)
        self.assertNotIn('shortened', r.json()['message'])

    def test_an_over_long_first_name_is_clipped_too(self):
        r = self.upload(f'first_name,phone\n{"y" * 250},9895271487\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(len(Lead.objects.get(phone='9895271487').first_name), 100)

    def test_an_over_long_phone_is_clipped_rather_than_rejected(self):
        r = self.upload(f'first_name,phone\nAsha,{"9" * 40}\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(len(Lead.objects.get(first_name='Asha').phone), 20)

    # â”€â”€ Source labels â”€â”€
    def test_a_friendly_source_label_is_stored_as_its_slug(self):
        """"Meta Lead Ads" as typed is a source no filter would ever match."""
        r = self.upload('first_name,phone,source\nAsha,9895271487,Meta Lead Ads\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Lead.objects.get(first_name='Asha').source, 'meta_ads')

    def test_source_matching_ignores_case(self):
        self.upload('first_name,phone,source\nAsha,9895271487,META ADS\n')
        self.assertEqual(Lead.objects.get(first_name='Asha').source, 'meta_ads')

    def test_a_slug_that_is_already_right_is_left_alone(self):
        self.upload('first_name,phone,source\nAsha,9895271487,website\n')
        self.assertEqual(Lead.objects.get(first_name='Asha').source, 'website')

    def test_an_unknown_source_is_kept_as_written(self):
        """Not every source is one of ours â€” an unrecognised one is not an error."""
        self.upload('first_name,phone,source\nAsha,9895271487,Trade Show\n')
        self.assertEqual(Lead.objects.get(first_name='Asha').source, 'Trade Show')

    def test_a_missing_source_still_defaults_to_manual(self):
        self.upload('first_name,phone\nAsha,9895271487\n')
        self.assertEqual(Lead.objects.get(first_name='Asha').source, 'manual')

    # â”€â”€ The whole reported file â”€â”€
    def test_the_reported_93_row_file_imports(self):
        """The shape that failed: 93 rows, one surname far over the column width."""
        rows = ['first_name,last_name,email,phone,source,status']
        for n in range(92):
            rows.append(f'Lead{n},Surname{n},,+9199000000{n:02d},Meta Lead Ads,new')
        rows.append('Khader,' + 'Paikkaden eye treatment ' * 8 + ',,+919995418857,Meta Lead Ads,new')
        r = self.upload('\n'.join(rows) + '\n')
        self.assertEqual(r.status_code, 200, r.content[:400])
        self.assertEqual(Lead.objects.count(), 93)
        self.assertEqual(Lead.objects.filter(source='meta_ads').count(), 93)


class FixAdNamedLeadsFromCampaignTests(TestCase):
    """The repair also covers leads that were filed under a campaign by CSV.

    Those carry no `meta_campaign_name`, so the campaign they belong to is what
    their name has to be compared against.
    """

    AD = 'Kerala ad 07/07/2026 campaign ad'

    def run_command(self, **kwargs):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('fix_ad_named_leads', stdout=out, **kwargs)
        return out.getvalue()

    def campaign(self, name=None):
        from campaigns.models import Campaign
        return Campaign.objects.create(name=name or self.AD,
                                       campaign_type='advertisement', status='active')

    def test_a_csv_lead_named_after_the_campaign_it_joined_is_cleared(self):
        lead = Lead.objects.create(first_name='Kerala', last_name='ad 07/07/2026 campaign ad',
                                   phone='9895271487', source='meta_ads')
        self.campaign().leads.add(lead)
        self.run_command()
        lead.refresh_from_db()
        self.assertEqual((lead.first_name, lead.last_name), ('Meta Lead', ''))

    def test_a_real_customer_in_that_campaign_is_untouched(self):
        lead = Lead.objects.create(first_name='Asha', last_name='Devi T', phone='9895271487')
        self.campaign().leads.add(lead)
        self.run_command()
        lead.refresh_from_db()
        self.assertEqual(lead.first_name, 'Asha')

    def test_a_lead_with_neither_campaign_nor_meta_name_is_skipped(self):
        lead = Lead.objects.create(first_name='Kerala', last_name='ad 07/07/2026 campaign ad')
        self.run_command()
        lead.refresh_from_db()
        self.assertEqual(lead.first_name, 'Kerala')


class MetaDistrictOrderTests(TestCase):
    """Which district a Meta lead is filed under.

    In order: the answer to `which_district_are_you_from?`, then the city, then
    none. Each is matched against the districts Settings configured, so a
    garbled district answer falls through to a usable city instead of blocking
    it — and a city that is not a district (Kochi) files under nothing.

    CSV import is deliberately unchanged: this rule is for Meta leads only.
    """

    def setUp(self):
        from .models import District
        for name in ('Ernakulam', 'Kannur', 'Kollam', 'Malappuram', 'Palakkad', 'Thrissur'):
            District.objects.get_or_create(name=name, defaults={'is_active': True})
        self.seq = 0

    def lead(self, *fields):
        self.seq += 1
        lead, _ = create_lead_from_meta_payload({
            'id': f'9700{self.seq}',
            'field_data': [{'name': 'full_name', 'values': [f'Customer {self.seq}']},
                           {'name': 'phone_number', 'values': [f'+9198950{self.seq:05d}']},
                           *[{'name': n, 'values': [v]} for n, v in fields]],
        })
        return lead

    # ── The district question ──
    def test_the_district_question_is_used(self):
        """The field exactly as it arrives from EnergyFox's lead form."""
        lead = self.lead(('which_district_are_you_from?', 'palakkad'))
        self.assertEqual(lead.district, 'Palakkad')

    def test_the_form_answers_arrive_lowercase_and_are_filed_properly(self):
        """The real export is all lowercase — malappuram, thrissur — and the lead
        is filed under the configured spelling."""
        for answer, expected in (('malappuram', 'Malappuram'), ('thrissur', 'Thrissur'),
                                 ('ernakulam', 'Ernakulam'), ('kollam', 'Kollam')):
            self.assertEqual(self.lead(('which_district_are_you_from?', answer)).district, expected)

    def test_the_district_question_wins_over_the_city(self):
        lead = self.lead(('which_district_are_you_from?', 'kollam'), ('city', 'Thrissur'))
        self.assertEqual(lead.district, 'Kollam')

    def test_the_question_is_found_without_its_question_mark(self):
        lead = self.lead(('which_district_are_you_from', 'ernakulam'))
        self.assertEqual(lead.district, 'Ernakulam')

    def test_a_form_worded_differently_still_reads_its_district_question(self):
        """Another branch's form, asking the same question in other words."""
        lead = self.lead(('select_your_district', 'kannur'))
        self.assertEqual(lead.district, 'Kannur')

    # ── Falling back to the city ──
    def test_no_district_question_falls_back_to_the_city(self):
        lead = self.lead(('city', 'Malappuram'))
        self.assertEqual(lead.district, 'Malappuram')

    def test_an_empty_district_answer_falls_back_to_the_city(self):
        lead = self.lead(('which_district_are_you_from?', ''), ('city', 'Thrissur'))
        self.assertEqual(lead.district, 'Thrissur')

    def test_a_district_answer_naming_no_district_falls_back_to_the_city(self):
        """The fall-through is on a usable answer, not merely a present one."""
        lead = self.lead(('which_district_are_you_from?', 'Payyanur.kannur'), ('city', 'Kannur'))
        self.assertEqual(lead.district, 'Kannur')

    # ── No district at all ──
    def test_a_city_that_is_not_a_district_files_under_nothing(self):
        lead = self.lead(('city', 'Kochi'))
        self.assertEqual(lead.district, '')

    def test_neither_answer_usable_files_under_nothing(self):
        lead = self.lead(('which_district_are_you_from?', 'somewhere'), ('city', 'Kochi'))
        self.assertEqual(lead.district, '')

    def test_no_district_question_and_no_city_files_under_nothing(self):
        lead = self.lead()
        self.assertEqual(lead.district, '')

    # ── The webhook shape ──
    def test_the_webhook_shape_reads_the_district_question(self):
        """Webhook payloads can carry the fields on the payload itself."""
        lead, _ = create_lead_from_meta_payload({
            'id': '97099', 'full_name': 'Webhook Customer',
            'which_district_are_you_from?': 'palakkad',
        })
        self.assertEqual(lead.district, 'Palakkad')

    def test_the_webhook_shape_falls_back_to_the_city(self):
        lead, _ = create_lead_from_meta_payload({
            'id': '97098', 'full_name': 'Webhook Customer Two', 'city': 'Kollam',
        })
        self.assertEqual(lead.district, 'Kollam')

    # ── CSV is not affected ──
    def test_a_csv_city_column_is_still_not_a_district(self):
        """This rule was asked for Meta imports. The CSV import keeps its own."""
        admin = mk('mdo_admin', 'superadmin')
        from django.core.files.uploadedfile import SimpleUploadedFile
        r = self.client.post(
            '/api/leads/bulk_upload/',
            data={'file': SimpleUploadedFile('leads.csv', b'first_name,phone,city\nAsha,9895271499,Kollam\n',
                                             content_type='text/csv')},
            HTTP_AUTHORIZATION=token_for(admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Lead.objects.get(phone='9895271499').district, '')


class LeadDistrictImportTests(TestCase):
    """District comes in from the CSV template and from Meta.

    Only a column or question that actually says district — city, town and taluk
    are different things and are not filed as one.
    """

    def setUp(self):
        self.admin = mk('dist_admin', 'superadmin')
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save()

    def upload(self, text):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(
            '/api/leads/bulk_upload/',
            data={'file': SimpleUploadedFile('leads.csv', text.encode('utf-8'),
                                             content_type='text/csv')},
            HTTP_AUTHORIZATION=token_for(self.admin))

    # ── The template ──
    def test_the_template_offers_a_district_column(self):
        r = self.client.get('/api/leads/csv_template/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        header = r.content.decode().splitlines()[0]
        self.assertIn('district', header.lower())

    def test_the_export_carries_the_district_back_out(self):
        Lead.objects.create(first_name='Asha', phone='9895271487', district='Ernakulam')
        r = self.client.get('/api/leads/export_csv/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('District', body.splitlines()[0])
        self.assertIn('Ernakulam', body)

    # ── CSV import ──
    def test_a_district_column_is_imported(self):
        r = self.upload('first_name,phone,district\nAsha,9895271487,Ernakulam\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Lead.objects.get(phone='9895271487').district, 'Ernakulam')

    def test_the_header_may_be_spelled_loosely(self):
        r = self.upload('First Name,Phone,District\nAsha,9895271487,Thrissur\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Lead.objects.get(phone='9895271487').district, 'Thrissur')

    def test_a_city_column_is_not_taken_as_the_district(self):
        """The user's instruction: city is not a district."""
        r = self.upload('first_name,phone,city\nAsha,9895271487,Kochi\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Lead.objects.get(phone='9895271487').district, '')

    def test_neither_are_town_taluk_or_location(self):
        r = self.upload('first_name,phone,town,taluk,location\n'
                        'Asha,9895271487,Aluva,Kunnathunad,Kakkanad\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Lead.objects.get(phone='9895271487').district, '')

    def test_a_missing_district_is_simply_blank(self):
        r = self.upload('first_name,phone\nAsha,9895271487\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Lead.objects.get(phone='9895271487').district, '')

    def test_an_over_long_district_is_simply_not_one_of_ours(self):
        """It used to be clipped to fit the column. A district now has to name
        one Settings configured, and 200 characters of x names none of them, so
        the lead arrives without a district instead. See
        DistrictMatchingOnImportTests."""
        r = self.upload(f'first_name,phone,district\nAsha,9895271487,{"x" * 200}\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Lead.objects.get(phone='9895271487').district, '')

    # ── Meta import ──
    def test_a_meta_district_question_is_imported(self):
        lead, _ = create_lead_from_meta_payload({
            'id': '88001',
            'field_data': [{'name': 'full_name', 'values': ['Asha Devi']},
                           {'name': 'phone_number', 'values': ['+919895271487']},
                           {'name': 'district', 'values': ['Ernakulam']}],
        })
        self.assertEqual(lead.district, 'Ernakulam')

    def test_a_meta_city_that_names_no_district_is_not_filed_as_one(self):
        """City is only a fallback on Meta leads (see MetaDistrictOrderTests),
        and even then it has to name a configured district. Kochi is a city in
        Ernakulam, not a district, so it files under nothing."""
        lead, _ = create_lead_from_meta_payload({
            'id': '88002',
            'field_data': [{'name': 'full_name', 'values': ['Asha Devi']},
                           {'name': 'city', 'values': ['Kochi']}],
        })
        self.assertEqual(lead.district, '')

    def test_a_meta_lead_without_a_district_question_is_blank(self):
        lead, _ = create_lead_from_meta_payload({
            'id': '88003',
            'field_data': [{'name': 'full_name', 'values': ['Asha Devi']}],
        })
        self.assertEqual(lead.district, '')

    def test_a_meta_payload_with_no_field_data_still_reads_a_district(self):
        """The webhook shape: the fields sit on the payload itself."""
        lead, _ = create_lead_from_meta_payload({
            'id': '88004', 'full_name': 'Asha Devi', 'district': 'Kollam',
        })
        self.assertEqual(lead.district, 'Kollam')

    # ── The API ──
    def test_the_district_is_readable_and_writable_through_the_api(self):
        lead = Lead.objects.create(first_name='Asha', phone='9895271487')
        r = self.client.patch(f'/api/leads/{lead.id}/', data={'district': 'Alappuzha'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['district'], 'Alappuzha')
        lead.refresh_from_db()
        self.assertEqual(lead.district, 'Alappuzha')


class LeadDistrictFilterTests(TestCase):
    """The Leads page filters by district, and offers the districts that are
    actually on the leads as its options."""

    def setUp(self):
        self.admin = mk('dist_filter_admin', 'superadmin')
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save()
        self.ernakulam = Lead.objects.create(first_name='Asha', phone='9895271481', district='Ernakulam')
        self.thrissur = Lead.objects.create(first_name='Biju', phone='9895271482', district='Thrissur')
        self.nowhere = Lead.objects.create(first_name='Chitra', phone='9895271483')

    def names(self, query=''):
        r = self.client.get(f'/api/leads/{query}', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        body = r.json()
        return sorted(l['first_name'] for l in (body.get('results') if isinstance(body, dict) else body))

    def options(self):
        r = self.client.get('/api/leads/districts/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    # ── Filtering ──
    def test_no_district_param_leaves_every_lead_in(self):
        self.assertEqual(self.names(), ['Asha', 'Biju', 'Chitra'])

    def test_a_district_narrows_the_list_to_it(self):
        self.assertEqual(self.names('?district=Ernakulam'), ['Asha'])

    def test_the_match_ignores_case(self):
        """The same district arrives capitalised differently from CSV and Meta."""
        self.assertEqual(self.names('?district=ernakulam'), ['Asha'])

    def test_the_match_ignores_padding_around_a_stored_value(self):
        Lead.objects.filter(pk=self.thrissur.pk).update(district='  Thrissur ')
        self.assertEqual(self.names('?district=Thrissur'), ['Biju'])

    def test_none_picks_out_the_leads_without_one(self):
        self.assertEqual(self.names('?district=none'), ['Chitra'])

    def test_a_district_nobody_is_in_returns_nothing(self):
        self.assertEqual(self.names('?district=Wayanad'), [])

    def test_the_district_filter_stacks_with_the_others(self):
        Lead.objects.filter(pk=self.ernakulam.pk).update(status='contacted')
        self.assertEqual(self.names('?district=Ernakulam&status=contacted'), ['Asha'])
        self.assertEqual(self.names('?district=Ernakulam&status=new'), [])

    # ── The options list ──
    def test_the_options_are_the_districts_in_use_sorted(self):
        self.assertEqual(self.options(), ['Ernakulam', 'Thrissur'])

    def test_a_blank_district_is_not_an_option(self):
        self.assertNotIn('', self.options())

    def test_one_spelling_per_district(self):
        Lead.objects.create(first_name='Deepa', phone='9895271484', district='ERNAKULAM')
        self.assertEqual(len(self.options()), 2)

    def test_options_are_trimmed(self):
        Lead.objects.filter(pk=self.thrissur.pk).update(district=' Thrissur ')
        self.assertEqual(self.options(), ['Ernakulam', 'Thrissur'])

    def test_an_archived_lead_still_offers_its_district(self):
        """It is reachable through the Archived toggle, so it must stay filterable."""
        Lead.objects.filter(pk=self.ernakulam.pk).update(is_archived=True)
        self.assertIn('Ernakulam', self.options())

    def test_a_trashed_lead_does_not_offer_its_district(self):
        Lead.objects.filter(pk=self.ernakulam.pk).update(is_trashed=True)
        self.assertNotIn('Ernakulam', self.options())

    def test_a_tele_caller_only_sees_the_districts_of_their_own_leads(self):
        agent = mk('dist_filter_agent', 'tele_caller')
        Lead.objects.filter(pk=self.thrissur.pk).update(assigned_to=agent)
        r = self.client.get('/api/leads/districts/', HTTP_AUTHORIZATION=token_for(agent))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json(), ['Thrissur'])


class ClosedDealsBoardTests(TestCase):
    """The Closed Deals module: who may open it, and whose deals they find.

    Access and scope are two separate questions. Opening the board is a role
    check; what is on it is the same privilege scoping the Leads list runs on —
    so a BDE opens the module and finds the deals they closed, not the company's.
    """

    URL = '/api/leads/closed-deals/'

    def setUp(self):
        from decimal import Decimal
        from .models import PaymentVerification
        self.Decimal = Decimal
        self.PV = PaymentVerification

        self.admin = mk('cdb_admin', 'admin')
        self.caller = mk('cdb_caller', 'tele_caller')
        self.caller2 = mk('cdb_caller2', 'tele_caller')
        self.bde = mk('cdb_bde', 'bde')
        self.bde2 = mk('cdb_bde2', 'bde')

        # One closed deal each, so every scope has something to be right about.
        self.mine = self.closed_deal('Asha', '9895000001', value='100000', received='40000',
                                     assigned_to=self.caller, bde=self.bde)
        self.theirs = self.closed_deal('Biju', '9895000002', value='200000', received='200000',
                                       assigned_to=self.caller2, bde=self.bde2)

    def closed_deal(self, name, phone, value, received, assigned_to=None, bde=None,
                    discount='0', complete=True, **extra):
        lead = Lead.objects.create(first_name=name, phone=phone, status='converted',
                                   value=self.Decimal(value), pushed_to_accounts=True,
                                   assigned_to=assigned_to, tele_caller=assigned_to, bde=bde,
                                   **extra)
        self.PV.objects.create(lead=lead, amount_received=self.Decimal(received),
                               discount_value=self.Decimal(discount), is_complete=complete)
        return lead

    def board(self, user, query='', expect=200):
        r = self.client.get(f'{self.URL}{query}', HTTP_AUTHORIZATION=token_for(user))
        self.assertEqual(r.status_code, expect, r.content[:300])
        return r.json() if expect == 200 else None

    def names(self, user, query=''):
        return sorted(d['name'] for d in self.board(user, query)['deals'])

    # ── Who may open it ──
    def test_the_sales_side_may_open_it(self):
        for role in ('superadmin', 'admin', 'coo', 'sales_manager', 'leads_manager',
                     'branch_manager', 'bde', 'tele_caller'):
            with self.subTest(role=role):
                self.board(mk(f'cdb_ok_{role}', role))

    def test_a_spectator_may_watch_it(self):
        self.board(mk('cdb_spectator', 'spectator'))

    def test_the_fulfilment_desks_may_not(self):
        """They work a customer through their own stage and have their own queues."""
        for role in ('documentation_staff', 'documentation_manager', 'accounts_staff',
                     'accounts_manager', 'purchase_staff', 'project_manager',
                     'liasoning_officer', 'store_keeper'):
            with self.subTest(role=role):
                self.board(mk(f'cdb_no_{role}', role), expect=403)

    def test_a_custom_role_may_be_granted_it(self):
        from users.models import CustomRole
        role = CustomRole.objects.create(name='Deal Watcher', permissions=['closed-deals'])
        u = mk('cdb_custom', 'custom')
        u.custom_role = role
        u.save()
        self.board(u)
        role.permissions = ['leads']
        role.save()
        u.refresh_from_db()
        self.board(u, expect=403)

    # ── Whose deals are on it ──
    def test_an_admin_sees_the_whole_company(self):
        self.assertEqual(self.names(self.admin), ['Asha', 'Biju'])

    def test_a_bde_sees_only_the_deals_they_closed(self):
        self.assertEqual(self.names(self.bde), ['Asha'])
        self.assertEqual(self.names(self.bde2), ['Biju'])

    def test_a_tele_caller_sees_only_their_own(self):
        self.assertEqual(self.names(self.caller), ['Asha'])
        self.assertEqual(self.names(self.caller2), ['Biju'])

    def test_a_branch_manager_sees_their_branch(self):
        from users.models import Branch
        branch = Branch.objects.create(name='Kochi')
        self.bde.branch = branch
        self.bde.save()
        manager = mk('cdb_bm', 'branch_manager')
        manager.branch = branch
        manager.save()
        self.assertEqual(self.names(manager), ['Asha'])

    def test_the_pickers_only_offer_people_on_your_own_board(self):
        """A BDE must not be shown colleagues whose deals they cannot open."""
        board = self.board(self.bde)
        self.assertEqual([p['name'] for p in board['bdes']], ['cdb_bde'])
        self.assertEqual([p['id'] for p in board['tele_callers']], [self.caller.id])

    # ── What counts as closed ──
    def test_a_converted_lead_with_no_payment_is_not_on_the_board(self):
        Lead.objects.create(first_name='Nothing', phone='9895000003', status='converted',
                            value=self.Decimal('50000'))
        self.assertNotIn('Nothing', self.names(self.admin))

    def test_reaching_documentation_is_not_a_closed_deal(self):
        Lead.objects.create(first_name='InDocs', phone='9895000004', status='converted',
                            value=self.Decimal('50000'), pushed_to_documentation=True)
        self.assertNotIn('InDocs', self.names(self.admin))

    def test_accounts_without_money_taken_is_not_a_closed_deal(self):
        """Accounts can open a verification before the customer has paid."""
        lead = Lead.objects.create(first_name='Unpaid', phone='9895000005', status='converted',
                                   value=self.Decimal('50000'), pushed_to_accounts=True)
        self.PV.objects.create(lead=lead, amount_received=self.Decimal('0'))
        self.assertNotIn('Unpaid', self.names(self.admin))

    def test_a_lost_deal_drops_off_the_board(self):
        self.mine.is_lost = True
        self.mine.save()
        self.assertEqual(self.names(self.admin), ['Biju'])

    def test_a_trashed_deal_drops_off_the_board(self):
        self.mine.is_trashed = True
        self.mine.save()
        self.assertEqual(self.names(self.admin), ['Biju'])

    def test_a_part_payment_is_already_a_closed_deal(self):
        deal = next(d for d in self.board(self.admin)['deals'] if d['name'] == 'Asha')
        self.assertEqual(deal['payment_status'], 'partially_paid')

    def test_paid_in_full_reads_as_fully_paid(self):
        deal = next(d for d in self.board(self.admin)['deals'] if d['name'] == 'Biju')
        self.assertEqual(deal['payment_status'], 'fully_paid')

    def test_a_discount_can_settle_the_balance(self):
        """Balance is deal value − received − discount, the same as accounts."""
        self.closed_deal('Discounted', '9895000006', value='100000', received='90000',
                         discount='10000', assigned_to=self.caller)
        deal = next(d for d in self.board(self.admin)['deals'] if d['name'] == 'Discounted')
        self.assertEqual(deal['payment_status'], 'fully_paid')
        self.assertEqual(Decimal(deal['balance']), Decimal('0'))

    # ── The money on it ──
    def test_the_row_carries_the_figures_accounts_banked(self):
        deal = next(d for d in self.board(self.admin)['deals'] if d['name'] == 'Asha')
        self.assertEqual(Decimal(deal['value']), Decimal('100000'))
        self.assertEqual(Decimal(deal['amount_received']), Decimal('40000'))
        self.assertEqual(Decimal(deal['balance']), Decimal('60000'))

    def test_the_summary_totals_the_board(self):
        s = self.board(self.admin)['summary']
        self.assertEqual(s['count'], 2)
        self.assertEqual(Decimal(s['deal_value']), Decimal('300000'))
        self.assertEqual(Decimal(s['received']), Decimal('240000'))
        self.assertEqual(Decimal(s['outstanding']), Decimal('60000'))
        self.assertEqual(s['fully_paid'], 1)
        self.assertEqual(s['partially_paid'], 1)

    def test_the_summary_describes_only_what_is_listed(self):
        """Filter the board and the totals under it must follow, or the numbers
        would describe rows the user cannot see."""
        s = self.board(self.admin, '?payment=fully_paid')['summary']
        self.assertEqual(s['count'], 1)
        self.assertEqual(Decimal(s['received']), Decimal('200000'))

    def test_a_bdes_totals_cover_only_their_own_deals(self):
        s = self.board(self.bde)['summary']
        self.assertEqual(s['count'], 1)
        self.assertEqual(Decimal(s['deal_value']), Decimal('100000'))

    # ── The filters ──
    def test_filtering_by_payment(self):
        self.assertEqual(self.names(self.admin, '?payment=partially_paid'), ['Asha'])
        self.assertEqual(self.names(self.admin, '?payment=fully_paid'), ['Biju'])

    def test_filtering_by_tele_caller(self):
        self.assertEqual(self.names(self.admin, f'?tele_caller={self.caller.id}'), ['Asha'])

    def test_filtering_by_bde(self):
        self.assertEqual(self.names(self.admin, f'?bde={self.bde2.id}'), ['Biju'])

    def test_searching_by_name_and_phone(self):
        self.assertEqual(self.names(self.admin, '?search=asha'), ['Asha'])
        self.assertEqual(self.names(self.admin, '?search=9895000002'), ['Biju'])

    def test_searching_by_district(self):
        self.closed_deal('Local', '9895000007', value='1000', received='1000',
                         assigned_to=self.caller, district='Ernakulam')
        self.assertEqual(self.names(self.admin, '?search=ernakulam'), ['Local'])

    def test_the_filters_combine(self):
        self.assertEqual(self.names(self.admin, f'?payment=fully_paid&bde={self.bde.id}'), [])
        self.assertEqual(self.names(self.admin, f'?payment=partially_paid&bde={self.bde.id}'), ['Asha'])

    def test_a_filter_cannot_reach_past_your_scope(self):
        """Naming someone else's id must not hand over their deals."""
        self.assertEqual(self.names(self.bde, f'?bde={self.bde2.id}'), [])

    def test_rubbish_in_a_filter_is_ignored_rather_than_fatal(self):
        self.assertEqual(self.names(self.admin, '?tele_caller=abc&bde=&payment=maybe'),
                         ['Asha', 'Biju'])


class DashboardRevenueIsClosedDealsTests(TestCase):
    """The dashboard's Revenue tile counts deals that were actually closed.

    A lead flagged converted with no money against it is a promise, and counting
    promises as revenue overstates the business. Same definition the Closed Deals
    board uses — in accounts with a payment, part or full, received.

    The Converted Leads board's own "Won Revenue" is deliberately left alone: that
    page is about converted leads, and its tile has to agree with its own table.
    """

    def setUp(self):
        self.admin = mk('rev_admin', 'admin')
        self.caller = mk('rev_caller', 'tele_caller')

    def lead(self, name, value, **extra):
        return Lead.objects.create(first_name=name, phone=f'99934{name:0>5}'[:14],
                                   status='converted', assigned_to=self.caller,
                                   value=Decimal(value), **extra)

    def close(self, lead, received):
        PaymentVerification.objects.create(lead=lead, amount_received=Decimal(received))
        lead.pushed_to_accounts = True
        lead.save(update_fields=['pushed_to_accounts'])
        return lead

    def revenue(self, actor=None):
        r = self.client.get('/api/dashboard-stats/',
                            HTTP_AUTHORIZATION=token_for(actor or self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return Decimal(str(r.json()['total_revenue']))

    def won_revenue(self):
        """The Converted Leads board's figure, for contrast."""
        r = self.client.get('/api/converted-analytics/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return Decimal(str(r.json()['total_revenue']))

    def test_a_converted_lead_with_no_payment_is_not_revenue(self):
        self.lead('a', '100000')
        self.assertEqual(self.revenue(), Decimal('0'))

    def test_reaching_documentation_is_not_revenue(self):
        self.lead('b', '100000', pushed_to_documentation=True)
        self.assertEqual(self.revenue(), Decimal('0'))

    def test_accounts_without_money_taken_is_not_revenue(self):
        lead = self.lead('c', '100000', pushed_to_accounts=True)
        PaymentVerification.objects.create(lead=lead, amount_received=Decimal('0'))
        self.assertEqual(self.revenue(), Decimal('0'))

    def test_a_part_payment_is_revenue_only_for_what_arrived(self):
        """The deal is closed either way, but revenue is the instalment that
        landed — the rest of the deal is a debt, not income."""
        self.close(self.lead('d', '100000'), '25000')
        self.assertEqual(self.revenue(), Decimal('25000'))

    def test_a_fully_paid_deal_is_revenue(self):
        self.close(self.lead('e', '250000'), '250000')
        self.assertEqual(self.revenue(), Decimal('250000'))

    def test_closed_deals_add_up(self):
        self.close(self.lead('f', '100000'), '50000')
        self.close(self.lead('g', '250000'), '250000')
        self.lead('h', '900000')                       # converted, unpaid
        self.assertEqual(self.revenue(), Decimal('300000'))   # 50000 + 250000

    def test_a_lost_deal_is_not_revenue(self):
        lead = self.close(self.lead('i', '100000'), '100000')
        lead.is_lost = True
        lead.save(update_fields=['is_lost'])
        self.assertEqual(self.revenue(), Decimal('0'))

    def test_a_trashed_deal_is_not_revenue(self):
        lead = self.close(self.lead('j', '100000'), '100000')
        lead.is_trashed = True
        lead.save(update_fields=['is_trashed'])
        self.assertEqual(self.revenue(), Decimal('0'))

    def test_the_converted_board_agrees_on_the_money(self):
        """Won means closed on both, so the revenue figures match. What still
        differs is the *count*: the converted board lists every converted lead,
        because that is what its table shows."""
        self.close(self.lead('k', '100000'), '100000')
        self.lead('l', '900000')                       # converted, unpaid
        self.assertEqual(self.revenue(), Decimal('100000'))
        self.assertEqual(self.won_revenue(), Decimal('100000'))
        r = self.client.get('/api/converted-analytics/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.json()['total_conversions'], 2)
        self.assertEqual(r.json()['closed_deal_count'], 1)

    def test_a_plain_user_sees_only_their_own_closed_deals(self):
        other = mk('rev_other', 'tele_caller')
        mine = self.close(self.lead('m', '100000'), '100000')
        mine.assigned_to = other
        mine.tele_caller = other
        mine.save()
        self.close(self.lead('n', '40000'), '40000')   # stays with self.caller
        self.assertEqual(self.revenue(self.caller), Decimal('40000'))
        self.assertEqual(self.revenue(), Decimal('140000'))

    def test_the_six_month_chart_follows_the_tile(self):
        """A Revenue chart that disagrees with the Revenue tile above it is worse
        than either being wrong on its own."""
        self.close(self.lead('o', '100000'), '100000')
        self.lead('p', '900000')                       # converted, unpaid
        r = self.client.get('/api/dashboard-stats/', HTTP_AUTHORIZATION=token_for(self.admin))
        series = r.json()['revenue_over_time']
        self.assertEqual(Decimal(str(sum(m['Revenue'] for m in series))), Decimal('100000'))


class DistrictListTests(TestCase):
    """The district list itself — seeded with Kerala's fourteen, kept from
    Settings, and one spelling per district."""

    def setUp(self):
        self.admin = mk('dl_admin', 'admin')
        self.agent = mk('dl_agent', 'tele_caller')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.admin)}

    def names(self, query=''):
        r = self.client.get(f'/api/districts/{query}', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        body = r.json()
        rows = body if isinstance(body, list) else body['results']
        return [d['name'] for d in rows]

    def add(self, name, user=None):
        return self.client.post('/api/districts/', data={'name': name},
                                content_type='application/json', **self.auth(user))

    # ── What ships ──
    def test_kerala_is_there_to_begin_with(self):
        names = self.names()
        self.assertEqual(len(names), 14)
        for expected in ('Thiruvananthapuram', 'Kollam', 'Ernakulam', 'Wayanad', 'Kasaragod'):
            self.assertIn(expected, names)

    def test_they_are_listed_alphabetically(self):
        self.assertEqual(self.names(), sorted(self.names()))

    # ── Keeping the list ──
    def test_an_admin_can_add_one(self):
        self.assertEqual(self.add('Mahe').status_code, 201)
        self.assertIn('Mahe', self.names())

    def test_a_plain_user_may_read_but_not_change_it(self):
        self.assertEqual(len(self.names()), 14)          # readable
        r = self.client.post('/api/districts/', data={'name': 'Mahe'},
                             content_type='application/json', **self.auth(self.agent))
        self.assertEqual(r.status_code, 403, r.content[:200])

    def test_the_same_district_cannot_be_added_twice(self):
        r = self.add('Kollam')
        self.assertEqual(r.status_code, 400)
        self.assertIn('already on the list', str(r.json()))

    def test_nor_in_a_different_case(self):
        """One district, one spelling — that is the whole point of the list."""
        r = self.add('KOLLAM')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Kollam', str(r.json()))
        self.assertEqual(len(self.names()), 14)

    def test_a_blank_name_is_refused(self):
        self.assertEqual(self.add('   ').status_code, 400)

    def test_surrounding_space_is_trimmed_away(self):
        self.assertEqual(self.add('  Mahe  ').status_code, 201)
        self.assertIn('Mahe', self.names())

    def test_it_reports_how_many_leads_it_holds(self):
        Lead.objects.create(first_name='A', phone='9891100001', district='Kollam')
        Lead.objects.create(first_name='B', phone='9891100002', district='kollam')
        r = self.client.get('/api/districts/', **self.auth())
        body = r.json()
        rows = body if isinstance(body, list) else body['results']
        kollam = next(d for d in rows if d['name'] == 'Kollam')
        self.assertEqual(kollam['lead_count'], 2)

    def test_only_the_active_ones_when_asked(self):
        d = District.objects.get(name='Wayanad')
        d.is_active = False
        d.save()
        self.assertNotIn('Wayanad', self.names('?active=true'))
        self.assertIn('Wayanad', self.names())

    def test_deleting_one_that_holds_leads_asks_first(self):
        Lead.objects.create(first_name='A', phone='9891100003', district='Kollam')
        d = District.objects.get(name='Kollam')
        r = self.client.delete(f'/api/districts/{d.id}/', **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()['can_force'])
        r = self.client.delete(f'/api/districts/{d.id}/?force=1', **self.auth())
        self.assertEqual(r.status_code, 204)
        # The lead keeps its district text; it is a name, not a link.
        self.assertEqual(Lead.objects.get(phone='9891100003').district, 'Kollam')

    def test_an_unused_one_deletes_without_fuss(self):
        d = District.objects.get(name='Wayanad')
        self.assertEqual(self.client.delete(f'/api/districts/{d.id}/', **self.auth()).status_code, 204)


class DistrictMatchingOnImportTests(TestCase):
    """A lead's district has to name one we configured.

    Matching ignores case and settles on the configured spelling. An answer that
    names no district of ours is dropped — the lead is still created, with its
    district left empty, rather than inventing a district nobody set up.
    """

    def setUp(self):
        self.admin = mk('dm_admin', 'superadmin')
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save()

    def upload(self, text):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(
            '/api/leads/bulk_upload/',
            data={'file': SimpleUploadedFile('leads.csv', text.encode('utf-8'),
                                             content_type='text/csv')},
            HTTP_AUTHORIZATION=token_for(self.admin))

    def imported(self, district_cell, phone='9895271487'):
        r = self.upload(f'first_name,phone,district\nAsha,{phone},{district_cell}\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        return Lead.objects.get(phone=phone)

    # ── Case-insensitive, canonical spelling ──
    def test_the_configured_spelling_matches_itself(self):
        self.assertEqual(self.imported('Kollam').district, 'Kollam')

    def test_shouting_matches(self):
        self.assertEqual(self.imported('KOLLAM').district, 'Kollam')

    def test_whispering_matches(self):
        self.assertEqual(self.imported('kollam').district, 'Kollam')

    def test_a_mangled_case_matches(self):
        self.assertEqual(self.imported('kollaM').district, 'Kollam')

    def test_surrounding_space_does_not_stop_it_matching(self):
        self.assertEqual(self.imported('  Kollam  ').district, 'Kollam')

    def test_every_spelling_lands_in_one_district(self):
        """The point of it: four spellings, one district on the board."""
        for i, spelling in enumerate(('Kollam', 'KOLLAM', 'kollam', 'kollaM')):
            self.imported(spelling, phone=f'989527200{i}')
        self.assertEqual(
            set(Lead.objects.exclude(district='').values_list('district', flat=True)),
            {'Kollam'})

    # ── Anything else is dropped, but the lead is kept ──
    def test_a_district_we_do_not_have_is_left_empty(self):
        lead = self.imported('Chennai')
        self.assertEqual(lead.district, '')

    def test_but_the_lead_is_still_imported(self):
        lead = self.imported('Chennai')
        self.assertEqual(lead.first_name, 'Asha')
        self.assertEqual(lead.phone, '9895271487')

    def test_a_near_miss_is_not_a_match(self):
        """No fuzzy matching: "Kollum" is not Kollam, and guessing would file
        leads under a district nobody chose."""
        self.assertEqual(self.imported('Kollum').district, '')

    def test_a_blank_cell_is_left_empty(self):
        self.assertEqual(self.imported('').district, '')

    def test_a_deactivated_district_stops_matching(self):
        d = District.objects.get(name='Wayanad')
        d.is_active = False
        d.save()
        self.assertEqual(self.imported('Wayanad').district, '')

    def test_a_district_added_in_settings_starts_matching(self):
        District.objects.create(name='Mahe')
        self.assertEqual(self.imported('MAHE').district, 'Mahe')

    def test_a_whole_file_is_matched_row_by_row(self):
        r = self.upload('first_name,phone,district\n'
                        'Asha,9895272101,ERNAKULAM\n'
                        'Biju,9895272102,Chennai\n'
                        'Chitra,9895272103,thrissur\n')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Lead.objects.get(phone='9895272101').district, 'Ernakulam')
        self.assertEqual(Lead.objects.get(phone='9895272102').district, '')
        self.assertEqual(Lead.objects.get(phone='9895272103').district, 'Thrissur')
        self.assertEqual(Lead.objects.count(), 3)

    # ── Meta forms go through the same door ──
    def test_a_meta_answer_matches_case_insensitively(self):
        lead, _ = create_lead_from_meta_payload({
            'id': '99001',
            'field_data': [{'name': 'full_name', 'values': ['Asha Devi']},
                           {'name': 'district', 'values': ['kOLLaM']}],
        })
        self.assertEqual(lead.district, 'Kollam')

    def test_a_meta_answer_we_do_not_recognise_is_dropped(self):
        lead, _ = create_lead_from_meta_payload({
            'id': '99002',
            'field_data': [{'name': 'full_name', 'values': ['Asha Devi']},
                           {'name': 'district', 'values': ['Chennai']}],
        })
        self.assertEqual(lead.district, '')
        self.assertEqual(lead.first_name, 'Asha')

    def test_a_meta_lead_without_a_district_is_still_created(self):
        lead, _ = create_lead_from_meta_payload({
            'id': '99003',
            'field_data': [{'name': 'full_name', 'values': ['Asha Devi']}],
        })
        self.assertEqual(lead.district, '')

    # ── Typing one by hand is not the import path ──
    def test_the_api_still_takes_a_district_as_typed(self):
        """The gate is on *import*. Someone editing a lead in the CRM picks from
        the list in the form; the field itself stays free text so historical
        values survive a district being renamed or removed."""
        lead = Lead.objects.create(first_name='Asha', phone='9895273001')
        r = self.client.patch(f'/api/leads/{lead.id}/', data={'district': 'Kollam'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['district'], 'Kollam')


class EditingNotesTests(TestCase):
    """Notes can be corrected, not only appended to.

    They are one text field the lead detail page rewrites wholesale, so the
    interesting cases are the ones that are not a pure append: fixing a typo in
    an earlier note, and clearing the field.
    """

    def setUp(self):
        self.admin = mk('ne_admin', 'admin')
        self.caller = mk('ne_caller', 'tele_caller')
        self.bde = mk('ne_bde', 'bde')
        self.lead = Lead.objects.create(first_name='Peter', phone='9895400001',
                                        assigned_to=self.caller, bde=self.bde,
                                        notes='Customer peter c/o')

    def patch_notes(self, actor, notes):
        return self.client.patch(f'/api/leads/{self.lead.id}/', data={'notes': notes},
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor))

    def notes(self):
        self.lead.refresh_from_db()
        return self.lead.notes

    def test_a_note_can_be_corrected(self):
        r = self.patch_notes(self.caller, 'Customer Peter, care of his son')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.notes(), 'Customer Peter, care of his son')

    def test_an_earlier_note_can_be_fixed_without_losing_the_later_ones(self):
        """The whole field is rewritten, so the edit has to carry the history."""
        self.patch_notes(self.caller, 'First note\n\nSecond note')
        self.patch_notes(self.caller, 'First note, corrected\n\nSecond note')
        self.assertEqual(self.notes(), 'First note, corrected\n\nSecond note')

    def test_notes_can_be_cleared(self):
        r = self.patch_notes(self.admin, '')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.notes(), '')

    def test_an_edit_is_recorded_on_the_timeline(self):
        from .models import ActivityLog
        self.patch_notes(self.caller, 'Corrected note')
        log = ActivityLog.objects.filter(lead=self.lead, activity_type='note_added').latest('created_at')
        self.assertIn('Note updated', log.description)
        self.assertEqual(log.actor, self.caller)

    def test_appending_still_records_only_what_was_added(self):
        """The append path logs the new note alone; a rewrite has no such tail to
        isolate and logs what the field now says."""
        from .models import ActivityLog
        self.patch_notes(self.caller, 'Customer peter c/o\n\nCalled back, interested')
        log = ActivityLog.objects.filter(lead=self.lead, activity_type='note_added').latest('created_at')
        self.assertEqual(log.extra.get('note'), 'Called back, interested')

    def test_a_bde_cannot_rewrite_them(self):
        """The lead record belongs to the tele-calling side; a BDE reports through
        the site visit. Mirrors BdeCannotEditOrDeleteLeadsTests — the detail page
        withholds the Edit and Add Note controls from them for the same reason."""
        r = self.patch_notes(self.bde, 'Rewritten by the BDE')
        self.assertEqual(r.status_code, 403, r.content[:200])
        self.assertEqual(self.notes(), 'Customer peter c/o')

    def test_a_spectator_cannot_rewrite_them(self):
        r = self.patch_notes(mk('ne_spectator', 'spectator'), 'Rewritten by a watcher')
        self.assertEqual(r.status_code, 403, r.content[:200])
        self.assertEqual(self.notes(), 'Customer peter c/o')


class SiteVisitDealTests(TestCase):
    """The deal value is derived, not typed: product price − discount.

    It lives on the Lead, where every report and the whole accounts stage read
    it, but it is settled on the site visit — the screen the BDE owns, since a
    BDE cannot write to the lead record itself.
    """

    def setUp(self):
        from .models import Product
        self.admin = mk('sd_admin', 'admin')
        self.bde = mk('sd_bde', 'bde')
        self.other_bde = mk('sd_bde2', 'bde')
        self.caller = mk('sd_caller', 'tele_caller')
        self.lead = Lead.objects.create(first_name='Anoop', phone='9895600001',
                                        assigned_to=self.caller, bde=self.bde)
        self.panel = Product.objects.create(name='5kW Rooftop', default_price=Decimal('350000'))

    def url(self):
        return f'/api/leads/{self.lead.id}/site-visit/'

    def patch(self, actor, payload):
        return self.client.patch(self.url(), data=payload, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor))

    def get(self, actor=None):
        r = self.client.get(self.url(), HTTP_AUTHORIZATION=token_for(actor or self.bde))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def value(self):
        self.lead.refresh_from_db()
        return self.lead.value

    # ── The arithmetic ──
    def test_the_deal_value_is_the_price_less_the_discount(self):
        r = self.patch(self.bde, {'product_price': '350000', 'discount': '25000'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.value(), Decimal('325000'))
        self.assertEqual(Decimal(str(r.json()['deal_value'])), Decimal('325000'))

    def test_no_discount_leaves_the_price_as_the_deal(self):
        self.patch(self.bde, {'product_price': '350000', 'discount': '0'})
        self.assertEqual(self.value(), Decimal('350000'))

    def test_changing_the_discount_moves_the_deal_value(self):
        self.patch(self.bde, {'product_price': '350000', 'discount': '25000'})
        self.patch(self.bde, {'product_price': '350000', 'discount': '50000'})
        self.assertEqual(self.value(), Decimal('300000'))

    def test_changing_the_price_moves_it_too(self):
        self.patch(self.bde, {'product_price': '350000', 'discount': '25000'})
        self.patch(self.bde, {'product_price': '400000'})
        self.assertEqual(self.value(), Decimal('375000'))     # the discount stands

    def test_a_discount_equal_to_the_price_is_a_free_deal_not_an_error(self):
        r = self.patch(self.bde, {'product_price': '350000', 'discount': '350000'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.value(), Decimal('0'))

    def test_a_discount_larger_than_the_price_is_refused(self):
        """A negative deal value would flow straight into the revenue figures."""
        r = self.patch(self.bde, {'product_price': '350000', 'discount': '400000'})
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertEqual(self.value(), Decimal('0'))          # nothing was written

    def test_a_negative_price_is_refused(self):
        self.assertEqual(self.patch(self.bde, {'product_price': '-1'}).status_code, 400)

    def test_an_emptied_price_box_means_nothing_owed(self):
        self.patch(self.bde, {'product_price': '350000'})
        r = self.patch(self.bde, {'product_price': '', 'discount': ''})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.value(), Decimal('0'))

    def test_saving_the_rest_of_the_form_leaves_the_deal_alone(self):
        """A PATCH that says nothing about money must not recompute it to zero —
        nor quietly wipe the price and discount it was worked out from."""
        self.patch(self.bde, {'product_price': '350000', 'discount': '50000'})
        r = self.patch(self.bde, {'roof_type': 'rcc'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.value(), Decimal('300000'))
        d = self.get()
        self.assertEqual(Decimal(d['product_price']), Decimal('350000'))
        self.assertEqual(Decimal(d['discount']), Decimal('50000'))

    def test_the_figures_come_back_on_the_next_visit(self):
        self.patch(self.bde, {'product_price': '350000', 'discount': '25000'})
        d = self.get()
        self.assertEqual(Decimal(d['product_price']), Decimal('350000'))
        self.assertEqual(Decimal(d['discount']), Decimal('25000'))
        self.assertEqual(Decimal(str(d['deal_value'])), Decimal('325000'))

    # ── The product ──
    def test_a_bde_can_set_the_product_here(self):
        """They are refused on the lead record, so this is their way in."""
        r = self.patch(self.bde, {'product': self.panel.id})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.product, self.panel)
        self.assertEqual(r.json()['product_name'], '5kW Rooftop')

    def test_a_bde_still_cannot_edit_the_lead_record_itself(self):
        r = self.client.patch(f'/api/leads/{self.lead.id}/', data={'product': self.panel.id},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403, r.content[:200])

    def test_the_product_can_be_set_with_its_price_in_one_go(self):
        r = self.patch(self.bde, {'product': self.panel.id, 'product_price': '350000'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.value(), Decimal('350000'))
        self.assertEqual(Decimal(r.json()['product_default_price']), Decimal('350000'))

    def test_the_product_can_be_cleared(self):
        self.patch(self.bde, {'product': self.panel.id})
        r = self.patch(self.bde, {'product': None})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.product)

    def test_a_product_that_does_not_exist_is_refused(self):
        r = self.patch(self.bde, {'product': 999999})
        self.assertEqual(r.status_code, 400, r.content[:200])

    def test_another_bdes_site_visit_is_not_theirs_to_touch(self):
        """They cannot see the lead at all, so the scoping turns them away before
        the site-visit permission is even asked."""
        r = self.patch(self.other_bde, {'product': self.panel.id, 'product_price': '1'})
        self.assertEqual(r.status_code, 404, r.content[:200])
        self.assertEqual(self.value(), Decimal('0'))

    def test_an_admin_can_settle_the_deal_too(self):
        r = self.patch(self.admin, {'product_price': '200000', 'discount': '10000'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.value(), Decimal('190000'))

    def test_a_spectator_cannot(self):
        r = self.patch(mk('sd_spectator', 'spectator'), {'product_price': '1'})
        self.assertEqual(r.status_code, 403, r.content[:200])


class LeadNoteTests(TestCase):
    """Notes carry who wrote them, which is what makes "edit your own" possible.

    Anyone working the lead can add one — the BDE included, because writing a
    note is not editing the lead record. Correcting one is limited to its author,
    with an admin override for the notes nobody owns.
    """

    def setUp(self):
        from .models import LeadNote
        self.LeadNote = LeadNote
        self.admin = mk('ln_admin', 'admin')
        self.caller = mk('ln_caller', 'tele_caller')
        self.bde = mk('ln_bde', 'bde')
        self.other_bde = mk('ln_bde2', 'bde')
        self.lead = Lead.objects.create(first_name='Anoop', phone='9895700001',
                                        assigned_to=self.caller, tele_caller=self.caller,
                                        bde=self.bde)

    def url(self, note_id=None):
        base = f'/api/leads/{self.lead.id}/notes/'
        return f'{base}{note_id}/' if note_id else base

    def add(self, actor, body):
        return self.client.post(self.url(), data={'body': body},
                                content_type='application/json',
                                HTTP_AUTHORIZATION=token_for(actor))

    def edit(self, actor, note_id, body):
        return self.client.patch(self.url(note_id), data={'body': body},
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor))

    def remove(self, actor, note_id):
        return self.client.delete(self.url(note_id), HTTP_AUTHORIZATION=token_for(actor))

    def listing(self, actor):
        r = self.client.get(self.url(), HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def note_by(self, actor, body='A note'):
        r = self.add(actor, body)
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.json()['id']

    # ── Adding ──
    def test_a_bde_can_add_a_note(self):
        """The reason for all of this: a BDE is refused on the lead record, but
        the notes are how the team talks about a customer."""
        r = self.add(self.bde, 'Met the customer, roof is clear')
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.json()['author_name'], 'ln_bde')

    def test_a_tele_caller_can_add_one(self):
        self.assertEqual(self.add(self.caller, 'Called back').status_code, 201)

    def test_a_spectator_cannot(self):
        self.assertEqual(self.add(mk('ln_spectator', 'spectator'), 'Watching').status_code, 403)

    def test_an_empty_note_is_refused(self):
        self.assertEqual(self.add(self.bde, '   ').status_code, 400)

    def test_notes_come_back_oldest_first(self):
        self.add(self.caller, 'First')
        self.add(self.bde, 'Second')
        self.assertEqual([n['body'] for n in self.listing(self.admin)], ['First', 'Second'])

    def test_adding_shows_on_the_timeline(self):
        from .models import ActivityLog
        self.add(self.bde, 'Site looks good')
        log = ActivityLog.objects.filter(lead=self.lead, activity_type='note_added').latest('created_at')
        self.assertEqual(log.actor, self.bde)
        self.assertEqual(log.extra.get('note'), 'Site looks good')

    # ── Editing: your own only ──
    def test_a_bde_can_edit_their_own_note(self):
        note_id = self.note_by(self.bde, 'Roof is clear')
        r = self.edit(self.bde, note_id, 'Roof is clear, 12 panels fit')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['body'], 'Roof is clear, 12 panels fit')
        self.assertIsNotNone(r.json()['edited_at'])

    def test_a_bde_cannot_edit_someone_elses(self):
        note_id = self.note_by(self.caller, 'Customer called')
        r = self.edit(self.bde, note_id, 'Rewritten by the BDE')
        self.assertEqual(r.status_code, 403, r.content[:200])
        self.assertEqual(self.LeadNote.objects.get(pk=note_id).body, 'Customer called')

    def test_one_bde_cannot_edit_anothers(self):
        """A BDE on another lead cannot see this one at all, so the scoping
        turns them away before the note's own rule is reached."""
        note_id = self.note_by(self.bde, 'Mine')
        self.assertEqual(self.edit(self.other_bde, note_id, 'Not yours').status_code, 404)
        self.assertEqual(self.LeadNote.objects.get(pk=note_id).body, 'Mine')

    def test_an_admin_can_edit_anyones(self):
        """Someone has to be able to take back what should not have been said."""
        note_id = self.note_by(self.bde, 'Careless remark')
        self.assertEqual(self.edit(self.admin, note_id, 'Redacted').status_code, 200)

    def test_a_tele_caller_cannot_edit_a_bdes_note(self):
        note_id = self.note_by(self.bde, 'Mine')
        self.assertEqual(self.edit(self.caller, note_id, 'Theirs').status_code, 403)

    def test_a_note_cannot_be_emptied(self):
        note_id = self.note_by(self.bde, 'Something')
        self.assertEqual(self.edit(self.bde, note_id, '  ').status_code, 400)

    def test_an_unowned_note_is_an_admins_to_edit(self):
        """The ones carried over from the old blob have no author to claim them."""
        note = self.LeadNote.objects.create(lead=self.lead, body='Legacy note', author=None)
        self.assertEqual(self.edit(self.bde, note.id, 'Mine now').status_code, 403)
        self.assertEqual(self.edit(self.admin, note.id, 'Tidied').status_code, 200)

    def test_the_listing_says_who_may_edit_what(self):
        """So the pencil is only drawn where the API would accept it."""
        self.add(self.bde, 'By the BDE')
        self.add(self.caller, 'By the tele caller')
        by_body = {n['body']: n['can_edit'] for n in self.listing(self.bde)}
        self.assertTrue(by_body['By the BDE'])
        self.assertFalse(by_body['By the tele caller'])

    # ── Deleting ──
    def test_the_author_can_delete_their_own(self):
        note_id = self.note_by(self.bde, 'Mistake')
        self.assertEqual(self.remove(self.bde, note_id).status_code, 204)
        self.assertFalse(self.LeadNote.objects.filter(pk=note_id).exists())

    def test_someone_else_cannot_delete_it(self):
        """The tele caller can see the lead, so this is the note's own rule
        rather than the scoping — and it still says no."""
        note_id = self.note_by(self.bde, 'Mine')
        self.assertEqual(self.remove(self.caller, note_id).status_code, 403)
        self.assertTrue(self.LeadNote.objects.filter(pk=note_id).exists())

    def test_a_note_on_another_lead_is_not_found_here(self):
        other = Lead.objects.create(first_name='Someone', phone='9895700002')
        stray = self.LeadNote.objects.create(lead=other, body='Elsewhere', author=self.bde)
        self.assertEqual(self.edit(self.bde, stray.id, 'Reached across').status_code, 404)

    # ── The lead's own notes field follows ──
    def test_the_lead_still_reads_as_one_blob(self):
        """The list, the export and the edit form all read Lead.notes; the rows
        are the record, that field is the rendering of it."""
        self.add(self.caller, 'First')
        self.add(self.bde, 'Second')
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.notes, 'First\n\nSecond')

    def test_editing_a_note_rewrites_the_blob(self):
        note_id = self.note_by(self.caller, 'First')
        self.add(self.bde, 'Second')
        self.edit(self.caller, note_id, 'First, corrected')
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.notes, 'First, corrected\n\nSecond')

    def test_deleting_a_note_takes_it_out_of_the_blob(self):
        note_id = self.note_by(self.caller, 'First')
        self.add(self.bde, 'Second')
        self.remove(self.caller, note_id)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.notes, 'Second')

    def test_a_bde_still_cannot_edit_the_lead_record(self):
        """Notes opened up; the lead itself did not."""
        r = self.client.patch(f'/api/leads/{self.lead.id}/', data={'first_name': 'Changed'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403, r.content[:200])


class PastMaintenanceCustomerTests(TestCase):
    """Customers installed before this CRM are still owed their visits.

    They come in as a name, a phone number and the date the project finished —
    and that date is the whole schedule, since every visit counts from it.
    """

    ADD = '/api/leads/maintenance-customers/'
    IMPORT = '/api/leads/maintenance-import/'
    TEMPLATE = '/api/leads/maintenance-template/'

    def setUp(self):
        from .models import PeriodicMaintenance
        self.PM = PeriodicMaintenance
        self.officer = mk('pm_officer', 'liasoning_officer')
        self.outsider = mk('pm_bde', 'bde')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.officer)}

    def add(self, name='Ramesh Kumar', phone='9895000000', completed_on='2023-03-15', user=None):
        return self.client.post(self.ADD,
                                data={'name': name, 'phone': phone, 'completed_on': completed_on},
                                content_type='application/json', **self.auth(user))

    def upload(self, text, filename='past.csv', user=None):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(
            self.IMPORT,
            data={'file': SimpleUploadedFile(filename, text.encode('utf-8'),
                                             content_type='text/csv')},
            **self.auth(user))

    def plan_for(self, name):
        return self.PM.objects.get(lead__first_name=name)

    # ── One at a time ──
    def test_a_past_customer_is_added_and_scheduled(self):
        r = self.add()
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.json()['visits'], self.PM.VISIT_COUNT)
        plan = self.plan_for('Ramesh')
        self.assertEqual(plan.start_date, date(2023, 3, 15))

    def test_the_schedule_counts_from_the_completion_date(self):
        """A visit every six months from the day the job finished."""
        self.add(completed_on='2023-03-15')
        due = list(self.plan_for('Ramesh').visits.order_by('sequence')
                   .values_list('due_date', flat=True))
        self.assertEqual(len(due), 10)
        self.assertEqual(due[0], date(2023, 9, 15))
        self.assertEqual(due[1], date(2024, 3, 15))
        self.assertEqual(due[-1], date(2028, 3, 15))

    def test_an_old_job_lands_part_way_through_its_five_years(self):
        """Its earlier visits are already past, which is the point of taking the
        completion date rather than today's."""
        self.add(completed_on='2023-03-15')
        today = timezone.localdate()
        overdue = self.plan_for('Ramesh').visits.filter(due_date__lt=today).count()
        self.assertGreater(overdue, 0)

    def test_the_customer_shows_on_the_maintenance_board(self):
        self.add()
        r = self.client.get('/api/leads/periodic-maintenance/', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        names = [c['first_name'] for c in r.json()['scheduled']]
        self.assertIn('Ramesh', names)

    def test_the_name_is_split_into_first_and_last(self):
        self.add(name='Ramesh Kumar Nair')
        lead = Lead.objects.get(phone='9895000000')
        self.assertEqual(lead.first_name, 'Ramesh')
        self.assertEqual(lead.last_name, 'Kumar Nair')

    def test_a_one_word_name_is_fine(self):
        self.assertEqual(self.add(name='Ramesh').status_code, 201)

    def test_they_are_kept_out_of_the_active_lead_book(self):
        """The sale was years ago; a pile of history must not bury today's work."""
        self.add()
        lead = Lead.objects.get(phone='9895000000')
        self.assertTrue(lead.is_archived)
        self.assertTrue(lead.pushed_to_liasoning)

    def test_why_they_are_here_is_written_on_the_lead(self):
        self.add(completed_on='2023-03-15')
        lead = Lead.objects.get(phone='9895000000')
        self.assertIn('before this CRM', lead.notes)
        self.assertIn('15/03/2023', lead.notes)

    # ── What it refuses ──
    def test_a_customer_with_no_name_is_refused(self):
        self.assertEqual(self.add(name='  ').status_code, 400)

    def test_a_customer_with_no_phone_is_refused(self):
        self.assertEqual(self.add(phone='').status_code, 400)

    def test_a_missing_completion_date_is_refused(self):
        self.assertEqual(self.add(completed_on='').status_code, 400)

    def test_a_completion_date_in_the_future_is_refused(self):
        ahead = (timezone.localdate() + timedelta(days=30)).isoformat()
        r = self.add(completed_on=ahead)
        self.assertEqual(r.status_code, 400, r.content[:200])
        self.assertEqual(self.PM.objects.count(), 0)

    def test_a_refusal_leaves_no_half_made_customer(self):
        self.add(completed_on='not a date')
        self.assertEqual(Lead.objects.count(), 0)

    # ── Dates as people write them ──
    def test_a_day_first_date_is_understood(self):
        self.add(completed_on='15/03/2023')
        self.assertEqual(self.plan_for('Ramesh').start_date, date(2023, 3, 15))

    def test_a_dashed_day_first_date_is_understood(self):
        self.add(completed_on='15-03-2023')
        self.assertEqual(self.plan_for('Ramesh').start_date, date(2023, 3, 15))

    # ── In bulk ──
    def test_a_csv_of_customers_is_imported_and_scheduled(self):
        r = self.upload('customer name,phone number,project completed date\n'
                        'Ramesh Kumar,9895000001,15/03/2023\n'
                        'Asha Devi,9895000002,2022-11-01\n')
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.json()['created'], 2)
        self.assertEqual(self.PM.objects.count(), 2)
        self.assertEqual(self.plan_for('Asha').start_date, date(2022, 11, 1))

    def test_every_imported_customer_gets_the_full_schedule(self):
        self.upload('customer name,phone number,project completed date\n'
                    'Ramesh Kumar,9895000001,15/03/2023\n')
        self.assertEqual(self.plan_for('Ramesh').visits.count(), self.PM.VISIT_COUNT)

    def test_a_bad_row_is_reported_and_the_rest_still_land(self):
        """One unreadable date must not cost the other rows."""
        r = self.upload('customer name,phone number,project completed date\n'
                        'Ramesh Kumar,9895000001,15/03/2023\n'
                        'Broken Row,9895000002,whenever\n'
                        'Asha Devi,9895000003,2022-11-01\n')
        body = r.json()
        self.assertEqual(body['created'], 2)
        self.assertEqual(body['skipped'], 1)
        self.assertEqual(body['errors'][0]['row'], 3)
        self.assertIn('Broken Row', body['errors'][0]['reason'])

    def test_a_row_missing_a_phone_is_skipped_by_name(self):
        r = self.upload('customer name,phone number,project completed date\n'
                        'No Phone,,15/03/2023\n')
        self.assertEqual(r.json()['skipped'], 1)
        self.assertIn('no phone number', r.json()['errors'][0]['reason'])

    def test_blank_lines_are_not_mistakes(self):
        r = self.upload('customer name,phone number,project completed date\n'
                        'Ramesh Kumar,9895000001,15/03/2023\n'
                        ',,\n')
        self.assertEqual(r.json()['created'], 1)
        self.assertEqual(r.json()['skipped'], 0)

    def test_loosely_spelled_headers_are_accepted(self):
        r = self.upload('Name,Mobile,Completion Date\n'
                        'Ramesh Kumar,9895000001,15/03/2023\n')
        self.assertEqual(r.json()['created'], 1)

    def test_an_empty_file_says_so(self):
        r = self.upload('customer name,phone number,project completed date\n')
        self.assertEqual(r.status_code, 400)

    def test_a_file_of_only_bad_rows_is_a_failure_not_a_success(self):
        r = self.upload('customer name,phone number,project completed date\n'
                        'Broken,9895000002,whenever\n')
        self.assertEqual(r.status_code, 400, r.content[:200])
        self.assertEqual(r.json()['created'], 0)

    def test_uploading_nothing_is_refused(self):
        r = self.client.post(self.IMPORT, data={}, **self.auth())
        self.assertEqual(r.status_code, 400)

    def test_an_xlsx_file_is_read(self):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.append(['customer name', 'phone number', 'project completed date'])
        sheet.append(['Ramesh Kumar', '9895000001', date(2023, 3, 15)])
        buf = BytesIO()
        book.save(buf)
        r = self.client.post(self.IMPORT, data={'file': SimpleUploadedFile(
            'past.xlsx', buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
            **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(self.plan_for('Ramesh').start_date, date(2023, 3, 15))

    # ── The template ──
    def test_the_template_names_the_three_columns(self):
        r = self.client.get(self.TEMPLATE, **self.auth())
        self.assertEqual(r.status_code, 200)
        header = r.content.decode().splitlines()[0].lower()
        for column in ('customer name', 'phone number', 'project completed date'):
            self.assertIn(column, header)

    def test_the_template_round_trips_through_the_import(self):
        """What it hands out must be what the import will take back."""
        template = self.client.get(self.TEMPLATE, **self.auth()).content.decode()
        r = self.upload(template)
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.json()['created'], 1)

    # ── Who may ──
    def test_someone_without_the_module_cannot_add(self):
        self.assertEqual(self.add(user=self.outsider).status_code, 403)

    def test_someone_without_the_module_cannot_import(self):
        r = self.upload('customer name,phone number,project completed date\n'
                        'Ramesh,9895000001,15/03/2023\n', user=self.outsider)
        self.assertEqual(r.status_code, 403)

    def test_an_admin_may_do_both(self):
        admin = mk('pm_admin', 'admin')
        self.assertEqual(self.add(user=admin).status_code, 201)


class WonMeansClosedEverywhereTests(TestCase):
    """A deal is won when the money has landed, and every screen agrees.

    One definition — leads.scopes.CLOSED_DEAL_FILTER — read by the dashboard, the
    Converted Leads board, the leaderboard, My Performance, the team report and
    the targets. A lead flagged converted with nothing against it is a promise,
    and the point of these tests is that no figure counts promises.
    """

    def setUp(self):
        self.admin = mk('won_admin', 'admin')
        self.agent = mk('won_agent', 'tele_caller')
        self.bde = mk('won_bde', 'bde')
        # One that landed, one that only says it did.
        self.closed = self.lead('Closed', '9895800001', '200000', paid='200000')
        self.promised = self.lead('Promised', '9895800002', '900000')

    def lead(self, name, phone, value, paid=None):
        obj = Lead.objects.create(first_name=name, phone=phone, status='converted',
                                  assigned_to=self.agent, tele_caller=self.agent,
                                  bde=self.bde, value=Decimal(value),
                                  status_changed_at=timezone.now())
        if paid is not None:
            obj.pushed_to_accounts = True
            obj.save(update_fields=['pushed_to_accounts'])
            PaymentVerification.objects.create(lead=obj, amount_received=Decimal(paid))
        return obj

    def get(self, path, user=None):
        r = self.client.get(path, HTTP_AUTHORIZATION=token_for(user or self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    # ── The definition itself ──
    def test_the_filter_picks_only_the_landed_deal(self):
        from leads.scopes import closed_deals
        self.assertEqual([l.first_name for l in closed_deals()], ['Closed'])

    def test_a_part_payment_still_counts_as_won(self):
        from leads.scopes import closed_deals
        self.lead('Partly', '9895800003', '500000', paid='1')
        self.assertIn('Partly', [l.first_name for l in closed_deals()])

    def test_a_lost_deal_is_not_won(self):
        from leads.scopes import closed_deals
        self.closed.is_lost = True
        self.closed.save(update_fields=['is_lost'])
        self.assertEqual(list(closed_deals()), [])

    # ── Every screen reads it ──
    def test_the_dashboard_revenue_is_the_closed_deal(self):
        d = self.get('/api/dashboard-stats/')
        self.assertEqual(Decimal(str(d['total_revenue'])), Decimal('200000'))

    def test_the_converted_boards_won_revenue_is_the_closed_deal(self):
        d = self.get('/api/converted-analytics/')
        self.assertEqual(Decimal(str(d['total_revenue'])), Decimal('200000'))
        self.assertEqual(d['closed_deal_count'], 1)

    def test_the_converted_board_still_counts_every_converted_lead(self):
        """Its table lists them, so its count has to match what is on screen."""
        self.assertEqual(self.get('/api/converted-analytics/')['total_conversions'], 2)

    def test_the_leaderboard_credits_only_the_closed_deal(self):
        rows = self.get('/api/leaderboard/?period=all_time')['leaderboard']
        mine = next(r for r in rows if r['id'] == self.bde.id)
        self.assertEqual(mine['closed_sales'], 1)
        self.assertEqual(Decimal(str(mine['revenue'])), Decimal('200000'))

    def test_my_performance_counts_the_closed_deal(self):
        d = self.get(f'/api/users/{self.agent.id}/performance/')
        self.assertEqual(d['summary']['won_count'], 1)
        self.assertEqual(Decimal(str(d['summary']['won_value'])), Decimal('200000'))

    def test_the_dashboards_member_table_agrees(self):
        d = self.get('/api/dashboard-stats/')
        rows = {r['name']: r for r in d.get('performance_stats', [])}
        mine = next((r for n, r in rows.items() if 'won_agent' in n or 'won_agent' == n), None)
        if mine:
            self.assertEqual(mine['won_count'], 1)
            self.assertEqual(Decimal(str(mine['won_value'])), Decimal('200000'))

    def test_the_figures_agree_with_the_closed_deals_board(self):
        """The whole point: the same question, asked once."""
        board = self.get('/api/leads/closed-deals/')
        self.assertEqual(board['summary']['count'], 1)
        self.assertEqual(Decimal(board['summary']['deal_value']),
                         Decimal(str(self.get('/api/dashboard-stats/')['total_revenue'])))

    # ── Targets are met by business landed ──
    def test_a_target_is_measured_against_closed_deals(self):
        """Achievement is business landed, not leads marked converted."""
        from ai_manager.engine import check_monthly_progress
        from ai_manager.models import MonthlyTarget
        today = timezone.localdate()
        MonthlyTarget.objects.create(agent=self.agent, month=today.month, year=today.year,
                                     target_leads=5, target_amount=Decimal('500000'))
        progress = check_monthly_progress(self.agent, today.month, today.year)
        self.assertEqual(progress['actual_leads'], 1)
        self.assertEqual(Decimal(str(progress['actual_amount'])), Decimal('200000'))

    # ── A BDE's own report ──
    def test_a_bdes_report_counts_the_deals_they_closed(self):
        """Handing a lead to a BDE moves nothing — `assigned_to` stays with the
        tele caller — so a report scoped on the owner shows a BDE as having
        closed nothing at all, whatever the win rule says."""
        d = self.get(f'/api/users/{self.bde.id}/performance/')['summary']
        self.assertEqual(d['total_leads'], 2)          # both leads are theirs as BDE
        self.assertEqual(d['won_count'], 1)            # one of them closed
        self.assertEqual(Decimal(str(d['won_value'])), Decimal('200000'))
        self.assertEqual(d['win_rate'], 50.0)

    def test_the_tele_caller_keeps_their_own_credit_too(self):
        """Ownership is shared, not moved: the same deal counts for both."""
        d = self.get(f'/api/users/{self.agent.id}/performance/')['summary']
        self.assertEqual(d['won_count'], 1)

    # ── Revenue is what was actually received ──
    def test_a_discount_moves_what_was_billed_not_what_came_in(self):
        """Revenue is money in. A discount changes what the customer was asked
        for — the billed figure — and cannot change what already arrived."""
        pv = self.closed.payment_verification
        pv.discount_value = Decimal('20000')
        pv.save(update_fields=['discount_value'])
        self.assertEqual(Decimal(str(self.get('/api/dashboard-stats/')['total_revenue'])),
                         Decimal('200000'))                       # what was received

    def test_the_discount_still_shows_up_in_what_was_billed(self):
        """It has not gone missing: billed is what outstanding measures against."""
        pv = self.closed.payment_verification
        pv.discount_value = Decimal('20000')
        pv.save(update_fields=['discount_value'])
        head = self.get('/api/company-performance/?period=all')['headline']
        self.assertEqual(head['billed'], '180000.00')             # 200000 - 20000
        self.assertEqual(head['revenue'], '200000.00')

    def test_every_revenue_figure_reports_the_same_received_amount(self):
        pv = self.closed.payment_verification
        pv.discount_value = Decimal('20000')
        pv.save(update_fields=['discount_value'])
        expected = Decimal('200000')
        self.assertEqual(Decimal(str(self.get('/api/dashboard-stats/')['total_revenue'])), expected)
        self.assertEqual(Decimal(str(self.get('/api/converted-analytics/')['total_revenue'])), expected)
        rows = self.get('/api/leaderboard/?period=all_time')['leaderboard']
        mine = next(r for r in rows if r['id'] == self.bde.id)
        self.assertEqual(Decimal(str(mine['revenue'])), expected)
        perf = self.get(f'/api/users/{self.agent.id}/performance/')['summary']
        self.assertEqual(Decimal(str(perf['won_value'])), expected)

    def test_no_discount_leaves_revenue_at_the_deal_value(self):
        self.assertEqual(Decimal(str(self.get('/api/dashboard-stats/')['total_revenue'])),
                         Decimal('200000'))

    def test_a_target_counts_the_money_received(self):
        from ai_manager.engine import check_monthly_progress
        from ai_manager.models import MonthlyTarget
        pv = self.closed.payment_verification
        pv.discount_value = Decimal('20000')
        pv.save(update_fields=['discount_value'])
        today = timezone.localdate()
        MonthlyTarget.objects.create(agent=self.agent, month=today.month, year=today.year,
                                     target_leads=5, target_amount=Decimal('500000'))
        progress = check_monthly_progress(self.agent, today.month, today.year)
        # Progress against a target is revenue, so it is the money that landed.
        self.assertEqual(Decimal(str(progress['actual_amount'])), Decimal('200000'))

    def test_paying_the_promised_deal_moves_every_figure_together(self):
        self.promised.pushed_to_accounts = True
        self.promised.save(update_fields=['pushed_to_accounts'])
        PaymentVerification.objects.create(lead=self.promised, amount_received=Decimal('10'))
        # It counts as a closed deal at once, and brings its ten rupees of
        # revenue with it — not the nine lakh it is still expected to pay.
        self.assertEqual(Decimal(str(self.get('/api/dashboard-stats/')['total_revenue'])),
                         Decimal('200010'))
        self.assertEqual(self.get('/api/leads/closed-deals/')['summary']['count'], 2)


class EditAndRemoveMaintenanceTests(TestCase):
    """A scheduled customer can be corrected, or taken off the schedule.

    Correcting the completed date re-dates what is still to come; a visit
    already filled in keeps its date and its readings, because it happened.
    Removing takes away the schedule, not the customer.
    """

    def setUp(self):
        from .models import PeriodicMaintenance, MaintenanceVisit
        self.PM, self.MV = PeriodicMaintenance, MaintenanceVisit
        self.officer = mk('me_officer', 'liasoning_officer')
        self.outsider = mk('me_bde', 'bde')
        r = self.client.post('/api/leads/maintenance-customers/',
                             data={'name': 'Ramesh Kumar', 'phone': '9895000200',
                                   'completed_on': '2023-03-15'},
                             content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.lead = Lead.objects.get(pk=r.json()['id'])

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.officer)}

    def url(self, lead=None):
        return f'/api/leads/{(lead or self.lead).id}/maintenance-customer/'

    def patch(self, payload, user=None):
        return self.client.patch(self.url(), data=payload, content_type='application/json',
                                 **self.auth(user))

    def delete(self, user=None):
        return self.client.delete(self.url(), **self.auth(user))

    def plan(self):
        return self.PM.objects.get(lead=self.lead)

    def due(self):
        return list(self.plan().visits.order_by('sequence').values_list('due_date', flat=True))

    # ── Editing ──
    def test_the_name_can_be_corrected(self):
        r = self.patch({'name': 'Ramesh Kumar Nair'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.first_name, 'Ramesh')
        self.assertEqual(self.lead.last_name, 'Kumar Nair')

    def test_the_phone_can_be_corrected(self):
        self.patch({'phone': '9895000201'})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.phone, '9895000201')

    def test_a_location_can_be_added(self):
        self.patch({'location': 'Kollam'})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.company, 'Kollam')

    def test_the_phone_cannot_be_emptied(self):
        r = self.patch({'phone': '  '})
        self.assertEqual(r.status_code, 400, r.content[:200])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.phone, '9895000200')

    # ── Re-dating ──
    def test_a_corrected_completed_date_re_dates_the_schedule(self):
        r = self.patch({'completed_on': '2024-01-01'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['visits_moved'], 10)
        self.assertEqual(self.plan().start_date, date(2024, 1, 1))
        self.assertEqual(self.due()[0], date(2024, 7, 1))
        self.assertEqual(self.due()[-1], date(2029, 1, 1))

    def test_a_day_first_date_is_understood_here_too(self):
        self.patch({'completed_on': '01/01/2024'})
        self.assertEqual(self.plan().start_date, date(2024, 1, 1))

    def test_a_visit_already_filled_in_keeps_its_date(self):
        """It happened; re-dating it would rewrite history to match a typo."""
        first = self.plan().visits.order_by('sequence').first()
        first.is_complete = True
        first.save(update_fields=['is_complete'])
        original = first.due_date

        r = self.patch({'completed_on': '2024-01-01'})
        self.assertEqual(r.json()['visits_moved'], 9)      # the other nine
        first.refresh_from_db()
        self.assertEqual(first.due_date, original)
        self.assertEqual(self.due()[1], date(2025, 1, 1))  # #2 moved

    def test_a_future_completed_date_is_refused(self):
        ahead = (timezone.localdate() + timedelta(days=10)).isoformat()
        r = self.patch({'completed_on': ahead})
        self.assertEqual(r.status_code, 400, r.content[:200])
        self.assertEqual(self.plan().start_date, date(2023, 3, 15))

    def test_an_unreadable_date_is_refused(self):
        self.assertEqual(self.patch({'completed_on': 'whenever'}).status_code, 400)

    def test_saving_without_a_date_leaves_the_schedule_alone(self):
        before = self.due()
        r = self.patch({'name': 'Ramesh K'})
        self.assertEqual(r.json()['visits_moved'], 0)
        self.assertEqual(self.due(), before)

    # ── Removing ──
    def test_the_schedule_can_be_removed(self):
        r = self.delete()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['visits_deleted'], 10)
        self.assertFalse(self.PM.objects.filter(lead=self.lead).exists())
        self.assertEqual(self.MV.objects.count(), 0)

    def test_removing_keeps_the_customer(self):
        """They stay on the books, and can be scheduled again."""
        self.delete()
        self.lead.refresh_from_db()
        self.assertTrue(Lead.objects.filter(pk=self.lead.pk).exists())
        self.assertTrue(self.lead.pushed_to_liasoning)

    def test_a_removed_customer_can_be_scheduled_again(self):
        self.delete()
        r = self.client.post(f'/api/leads/{self.lead.id}/schedule-maintenance/',
                             data={'start_date': '2024-01-01'},
                             content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.plan().visits.count(), 10)

    def test_the_reply_says_how_much_recorded_work_it_cost(self):
        visit = self.plan().visits.order_by('sequence').first()
        visit.is_complete = True
        visit.save(update_fields=['is_complete'])
        self.assertEqual(self.delete().json()['completed_visits_deleted'], 1)

    def test_removing_twice_is_not_found(self):
        self.delete()
        self.assertEqual(self.delete().status_code, 404)

    def test_a_customer_who_was_never_scheduled_is_not_found(self):
        other = Lead.objects.create(first_name='Unscheduled', phone='9895000202')
        r = self.client.patch(self.url(other), data={'name': 'X'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 404, r.content[:200])

    # ── Who may ──
    def test_someone_without_the_module_cannot_edit(self):
        self.assertEqual(self.patch({'name': 'Nope'}, user=self.outsider).status_code, 403)

    def test_someone_without_the_module_cannot_remove(self):
        self.assertEqual(self.delete(user=self.outsider).status_code, 403)
        self.assertTrue(self.PM.objects.filter(lead=self.lead).exists())


class CompanyPerformanceTests(TestCase):
    """One report over the whole company, agreeing with every other screen.

    A deal counts here on the same terms it counts on the Closed Deals board —
    converted, not lost, pushed to accounts, money actually received — and it is
    worth the agreed value less any discount.
    """

    def setUp(self):
        from users.models import Branch
        self.boss = mk('cp_super', 'superadmin')
        self.kochi = Branch.objects.create(name='Kochi', code='KCH')
        self.kollam = Branch.objects.create(name='Kollam', code='KLM')
        self.bde_k = mk('cp_bde_kochi', 'bde')
        self.bde_k.branch = self.kochi
        self.bde_k.save()
        self.bde_l = mk('cp_bde_kollam', 'bde')
        self.bde_l.branch = self.kollam
        self.bde_l.save()

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.boss)}

    def get(self, user=None, **params):
        qs = '&'.join(f'{k}={v}' for k, v in params.items())
        return self.client.get(f'/api/company-performance/?{qs}', **self.auth(user))

    def won(self, value, discount=0, bde=None, when=None, source='manual', district='Ernakulam'):
        """A deal on the same terms the Closed Deals board uses."""
        from .models import PaymentVerification
        who = bde or self.bde_k
        lead = Lead.objects.create(
            first_name='Won', last_name=str(value), phone=f'98{value:08d}',
            status='converted', is_lost=False, pushed_to_accounts=True,
            value=Decimal(value), bde=who, assigned_to=who,
            source=source, district=district)
        PaymentVerification.objects.create(
            lead=lead, amount_received=Decimal(value) - Decimal(discount),
            discount_value=Decimal(discount))
        stamp = when or timezone.now()
        Lead.objects.filter(pk=lead.pk).update(status_changed_at=stamp)
        if when:
            Lead.objects.filter(pk=lead.pk).update(created_at=when)
        return lead

    # -- Who may look --
    def test_the_top_of_the_house_may_look(self):
        for role in ('superadmin', 'admin', 'coo'):
            user = mk(f'cp_ok_{role}', role)
            self.assertEqual(self.get(user).status_code, 200, role)

    def test_the_spectator_may_look(self):
        self.assertEqual(self.get(mk('cp_spec', 'spectator')).status_code, 200)

    def test_a_manager_may_not(self):
        """They run a function; the Manager module reports their own people."""
        for role in ('sales_manager', 'branch_manager', 'leads_manager'):
            user = mk(f'cp_no_{role}', role)
            self.assertEqual(self.get(user).status_code, 403, role)

    def test_a_bde_may_not(self):
        self.assertEqual(self.get(self.bde_k).status_code, 403)

    def test_a_stranger_may_not(self):
        self.assertEqual(self.client.get('/api/company-performance/').status_code, 401)

    # -- What counts as won --
    def test_revenue_is_what_the_customer_actually_paid(self):
        self.won(100000, discount=10000)
        head = self.get(period='all').json()['headline']
        self.assertEqual(head['revenue'], '90000.00')
        self.assertEqual(head['discounts'], '10000.00')

    def test_a_converted_lead_without_money_is_not_a_closed_deal(self):
        Lead.objects.create(first_name='NoMoney', phone='9800000001', status='converted',
                            value=Decimal(50000), pushed_to_accounts=True)
        head = self.get(period='all').json()['headline']
        self.assertEqual(head['converted'], 1)
        self.assertEqual(head['closed_deals'], 0)
        self.assertEqual(head['revenue'], '0.00')

    def test_a_lost_deal_is_not_won(self):
        lead = self.won(50000)
        Lead.objects.filter(pk=lead.pk).update(is_lost=True)
        self.assertEqual(self.get(period='all').json()['headline']['closed_deals'], 0)

    def test_a_trashed_lead_is_out_of_every_figure(self):
        lead = self.won(50000)
        Lead.objects.filter(pk=lead.pk).update(is_trashed=True)
        head = self.get(period='all').json()['headline']
        self.assertEqual((head['leads'], head['closed_deals'], head['revenue']), (0, 0, '0.00'))

    def test_outstanding_is_the_gap_between_billed_and_received(self):
        self.won(100000, discount=0)
        lead = self.won(200000)
        lead.payment_verification.amount_received = Decimal(50000)
        lead.payment_verification.save()
        head = self.get(period='all').json()['headline']
        # Revenue is the money in; billed is what was asked for; the difference
        # is the debt. Three different figures, not one repeated.
        self.assertEqual(head['revenue'], '150000.00')     # 100000 + 50000
        self.assertEqual(head['billed'], '300000.00')
        self.assertEqual(head['outstanding'], '150000.00')

    def test_an_overpayment_is_not_a_negative_debt(self):
        lead = self.won(100000)
        lead.payment_verification.amount_received = Decimal(120000)
        lead.payment_verification.save()
        self.assertEqual(self.get(period='all').json()['headline']['outstanding'], '0.00')

    def test_the_average_deal_is_net_too(self):
        self.won(100000, discount=20000)
        self.won(60000)
        self.assertEqual(self.get(period='all').json()['headline']['avg_deal_value'], '70000.00')

    # -- The window --
    def test_money_is_counted_by_when_the_deal_was_won(self):
        """A lead from last year that closes this month is this month's revenue."""
        lead = self.won(80000, when=timezone.now() - timedelta(days=400))
        Lead.objects.filter(pk=lead.pk).update(status_changed_at=timezone.now())
        data = self.get(period='this_month').json()
        self.assertEqual(data['headline']['closed_deals'], 1)
        self.assertEqual(data['headline']['revenue'], '80000.00')
        self.assertEqual(data['headline']['leads'], 0)

    def test_this_month_leaves_out_last_year(self):
        self.won(80000, when=timezone.now() - timedelta(days=400))
        self.assertEqual(self.get(period='this_month').json()['headline']['closed_deals'], 0)

    def test_all_time_takes_everything(self):
        self.won(80000, when=timezone.now() - timedelta(days=400))
        self.assertEqual(self.get(period='all').json()['headline']['closed_deals'], 1)

    def test_a_custom_window_is_honoured(self):
        self.won(80000, when=timezone.now() - timedelta(days=100))
        self.won(50000)
        far = (timezone.localdate() - timedelta(days=120)).isoformat()
        near = (timezone.localdate() - timedelta(days=80)).isoformat()
        data = self.get(period='custom', **{'from': far, 'to': near}).json()
        self.assertEqual(data['headline']['revenue'], '80000.00')

    def test_a_backwards_custom_window_is_read_the_right_way_round(self):
        self.won(80000, when=timezone.now() - timedelta(days=100))
        far = (timezone.localdate() - timedelta(days=120)).isoformat()
        near = (timezone.localdate() - timedelta(days=80)).isoformat()
        data = self.get(period='custom', **{'from': near, 'to': far}).json()
        self.assertEqual(data['headline']['revenue'], '80000.00')

    # -- Branches --
    def test_a_branch_is_credited_through_the_people_who_worked_the_lead(self):
        self.won(300000, bde=self.bde_k)
        self.won(100000, bde=self.bde_l)
        rows = {r['name']: r for r in self.get(period='all').json()['branches']['rows']}
        self.assertEqual(rows['Kochi']['revenue'], '300000.00')
        self.assertEqual(rows['Kollam']['revenue'], '100000.00')

    def test_the_best_and_least_earning_branches_are_named(self):
        self.won(300000, bde=self.bde_k)
        self.won(100000, bde=self.bde_l)
        branches = self.get(period='all').json()['branches']
        self.assertEqual(branches['best']['name'], 'Kochi')
        self.assertEqual(branches['worst']['name'], 'Kollam')

    def test_a_branch_that_earned_nothing_is_named_rather_than_ranked_last(self):
        """A tie on zero is not a ranking anyone can act on."""
        self.won(300000, bde=self.bde_k)
        branches = self.get(period='all').json()['branches']
        self.assertEqual(branches['best']['name'], 'Kochi')
        self.assertEqual(branches['without_revenue'], ['Kollam'])

    def test_one_earner_is_not_reported_as_both_ends(self):
        """The same name as most and least revenue is not a ranking."""
        self.won(300000, bde=self.bde_k)
        branches = self.get(period='all').json()['branches']
        self.assertTrue(branches['only_earner'])
        self.assertIsNone(branches['worst'])

    def test_nothing_is_the_best_when_nobody_earned(self):
        """Calling a branch on zero the top earner would be a plain untruth."""
        Lead.objects.create(first_name='Raw', phone='9800000003', assigned_to=self.bde_k)
        branches = self.get(period='all').json()['branches']
        self.assertIsNone(branches['best'])
        self.assertIsNone(branches['worst'])
        self.assertIn('Kochi', branches['without_revenue'])

    def test_revenue_nobody_can_be_credited_with_is_declared(self):
        """Branch rows will not add up when the closer is on no branch, and the
        difference is stated rather than left for someone to chase."""
        loose = mk('cp_no_branch', 'bde')
        self.won(300000, bde=self.bde_k)
        self.won(70000, bde=loose)
        branches = self.get(period='all').json()['branches']
        self.assertEqual(branches['unattributed_revenue'], '70000.00')
        self.assertEqual(branches['unattributed_deals'], 1)
        self.assertEqual(sum(Decimal(r['revenue']) for r in branches['rows']), Decimal('300000'))

    def test_nothing_is_unattributed_when_everyone_has_a_branch(self):
        self.won(300000, bde=self.bde_k)
        self.assertEqual(self.get(period='all').json()['branches']['unattributed_revenue'], '0.00')

    # -- People --
    def test_a_bde_is_credited_for_what_they_closed(self):
        self.won(250000, bde=self.bde_k)
        rows = {r['name']: r for r in self.get(period='all').json()['employees']['rows']}
        self.assertEqual(rows['cp_bde_kochi']['revenue'], '250000.00')

    def test_a_bde_is_credited_even_when_the_lead_is_owned_by_someone_else(self):
        """Handing a lead to a BDE moves the work, not the credit."""
        lead = self.won(120000, bde=self.bde_k)
        Lead.objects.filter(pk=lead.pk).update(assigned_to=self.boss)
        rows = {r['name']: r for r in self.get(period='all').json()['employees']['rows']}
        self.assertEqual(rows['cp_bde_kochi']['revenue'], '120000.00')

    def test_people_who_worked_nothing_are_left_out(self):
        self.won(120000, bde=self.bde_k)
        names = [r['name'] for r in self.get(period='all').json()['employees']['rows']]
        self.assertNotIn('cp_bde_kollam', names)

    # -- The rest of the board --
    def test_the_funnel_narrows(self):
        self.won(50000)
        Lead.objects.create(first_name='Raw', phone='9800000002')
        funnel = {s['stage']: s['count'] for s in self.get(period='all').json()['funnel']}
        self.assertEqual(funnel['Leads'], 2)
        self.assertEqual(funnel['Converted'], 1)
        self.assertEqual(funnel['Closed deals'], 1)

    def test_sources_and_districts_carry_their_revenue(self):
        self.won(90000, source='meta', district='Ernakulam')
        data = self.get(period='all').json()
        self.assertEqual(data['sources'][0]['name'], 'meta')
        self.assertEqual(data['sources'][0]['revenue'], '90000.00')
        self.assertEqual(data['districts'][0]['name'], 'Ernakulam')

    def test_a_lead_without_a_district_is_labelled_not_dropped(self):
        self.won(40000, district='')
        names = [r['name'] for r in self.get(period='all').json()['districts']]
        self.assertIn('No district', names)

    def test_the_monthly_series_is_capped_at_a_year(self):
        self.won(10000, when=timezone.now() - timedelta(days=900))
        self.assertLessEqual(len(self.get(period='all').json()['monthly']), 12)

    def test_the_report_agrees_with_the_closed_deals_board(self):
        """The whole point: two screens, one definition."""
        self.won(100000, discount=15000)
        self.won(60000)
        board = self.client.get('/api/leads/closed-deals/', **self.auth()).json()
        head = self.get(period='all').json()['headline']
        self.assertEqual(head['closed_deals'], board['summary']['count'])
        self.assertEqual(head['collected'], board['summary']['received'])
        # The board reports the value agreed; revenue is that less the discount.
        self.assertEqual(Decimal(head['revenue']),
                         Decimal(board['summary']['deal_value']) - Decimal(head['discounts']))


class CompanyPerformanceRoleBoardsTests(TestCase):
    """The BDE and tele caller boards are the People rows filtered by role.

    Not a second calculation: a person's figures must read the same on their own
    board, on Everyone, and on My Performance.
    """

    def setUp(self):
        self.boss = mk('cpr_super', 'superadmin')
        self.bde = mk('cpr_bde', 'bde')
        self.caller = mk('cpr_caller', 'tele_caller')
        self.manager = mk('cpr_mgr', 'branch_manager')

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.boss)}

    def board(self, key, period='all'):
        data = self.client.get(f'/api/company-performance/?period={period}', **self.auth()).json()
        return data[key]

    def won(self, value, bde=None, caller=None, owner=None):
        from .models import PaymentVerification
        lead = Lead.objects.create(
            first_name='Won', last_name=str(value), phone=f'97{value:08d}',
            status='converted', is_lost=False, pushed_to_accounts=True,
            value=Decimal(value), bde=bde, tele_caller=caller, assigned_to=owner or bde or caller)
        PaymentVerification.objects.create(lead=lead, amount_received=Decimal(value))
        Lead.objects.filter(pk=lead.pk).update(status_changed_at=timezone.now())
        return lead

    def test_the_bde_board_holds_only_bdes(self):
        self.won(100000, bde=self.bde, caller=self.caller)
        roles = {r['role_key'] for r in self.board('bdes')['rows']}
        self.assertEqual(roles, {'bde'})

    def test_the_tele_caller_board_holds_only_tele_callers(self):
        self.won(100000, bde=self.bde, caller=self.caller)
        roles = {r['role_key'] for r in self.board('tele_callers')['rows']}
        self.assertEqual(roles, {'tele_caller'})

    def test_a_person_reads_the_same_on_their_own_board(self):
        """The whole reason the boards are a filter and not a second sum."""
        self.won(250000, bde=self.bde, caller=self.caller)
        everyone = {r['name']: r for r in self.board('employees')['rows']}
        bdes = {r['name']: r for r in self.board('bdes')['rows']}
        self.assertEqual(bdes['cpr_bde'], everyone['cpr_bde'])

    def test_both_roles_are_credited_for_the_deal_they_shared(self):
        self.won(250000, bde=self.bde, caller=self.caller)
        self.assertEqual(self.board('bdes')['rows'][0]['revenue'], '250000.00')
        self.assertEqual(self.board('tele_callers')['rows'][0]['revenue'], '250000.00')

    def test_everyone_still_holds_the_other_roles(self):
        self.won(90000, bde=self.bde, owner=self.manager)
        names = [r['name'] for r in self.board('employees')['rows']]
        self.assertIn('cpr_mgr', names)
        self.assertNotIn('cpr_mgr', [r['name'] for r in self.board('bdes')['rows']])

    def test_each_board_is_ranked_on_its_own_members(self):
        """Sorting one board must not disturb another — they share their rows."""
        other = mk('cpr_bde2', 'bde')
        self.won(50000, bde=self.bde)
        self.won(300000, bde=other)
        bdes = self.board('bdes')
        self.assertEqual([r['name'] for r in bdes['rows']], ['cpr_bde2', 'cpr_bde'])
        self.assertEqual(bdes['best']['name'], 'cpr_bde2')
        self.assertEqual(bdes['worst']['name'], 'cpr_bde')

    def test_the_count_is_the_board_not_the_company(self):
        self.won(100000, bde=self.bde, caller=self.caller)
        self.assertEqual(self.board('bdes')['count'], 1)
        self.assertEqual(self.board('tele_callers')['count'], 1)
        self.assertEqual(self.board('employees')['count'], 2)

    def test_an_empty_role_board_says_so_rather_than_erroring(self):
        self.won(100000, bde=self.bde)
        callers = self.board('tele_callers')
        self.assertEqual(callers['rows'], [])
        self.assertIsNone(callers['best'])


class CompanyPerformanceAnalysisTests(TestCase):
    """Losses, collection, delivery and segments — the sections that say why."""

    def setUp(self):
        self.boss = mk('cpa_super', 'superadmin')
        self.bde = mk('cpa_bde', 'bde')

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.boss)}

    def get(self, key, period='all'):
        return self.client.get(f'/api/company-performance/?period={period}', **self.auth()).json()[key]

    def won(self, value, discount=0, received=None, mode='cash', conn='', roof=''):
        from .models import PaymentVerification, SiteVisit
        lead = Lead.objects.create(
            first_name='Won', last_name=str(value), phone=f'96{value:08d}',
            status='converted', is_lost=False, pushed_to_accounts=True,
            value=Decimal(value), bde=self.bde, assigned_to=self.bde)
        net = Decimal(value) - Decimal(discount)
        PaymentVerification.objects.create(
            lead=lead, amount_received=net if received is None else Decimal(received),
            discount_value=Decimal(discount), payment_mode=mode)
        if conn or roof:
            SiteVisit.objects.create(lead=lead, connection_type=conn, roof_type=roof)
        Lead.objects.filter(pk=lead.pk).update(status_changed_at=timezone.now())
        return lead

    def lost(self, value, reason='', when=None, stage=None, owner=True):
        # owner=False leaves the lead unassigned: handing one to a BDE fills in
        # the bde field, which moves it to the Site Visit stage.
        lead = Lead.objects.create(
            first_name='Lost', last_name=str(value), phone=f'95{value:08d}',
            value=Decimal(value), is_lost=True, lost_reason=reason,
            assigned_to=self.bde if owner else None, **(stage or {}))
        Lead.objects.filter(pk=lead.pk).update(lost_at=when or timezone.now())
        return lead

    # ── Losses ──
    def test_losses_are_counted_with_their_value(self):
        self.lost(120000, 'Price too high')
        self.lost(80000, 'Price too high')
        self.lost(50000, 'Went elsewhere')
        lost = self.get('lost')
        self.assertEqual(lost['count'], 3)
        self.assertEqual(lost['value'], '250000.00')
        self.assertEqual(lost['reasons'][0], {'name': 'Price too high', 'count': 2, 'value': '200000.00'})

    def test_a_loss_with_no_reason_is_labelled_not_dropped(self):
        self.lost(40000, '   ')
        self.assertEqual(self.get('lost')['reasons'][0]['name'], 'No reason given')

    def test_blank_and_missing_reasons_collapse_into_one_row(self):
        self.lost(10000, '')
        self.lost(20000, '  ')
        reasons = self.get('lost')['reasons']
        self.assertEqual(len(reasons), 1)
        self.assertEqual(reasons[0]['count'], 2)

    def test_a_loss_is_dated_by_when_it_was_written_off(self):
        """A lead from last year written off this month is this month's loss."""
        lead = self.lost(90000, 'Dropped')
        Lead.objects.filter(pk=lead.pk).update(created_at=timezone.now() - timedelta(days=400))
        self.assertEqual(self.get('lost', period='this_month')['count'], 1)

    def test_a_loss_written_off_long_ago_is_out_of_this_month(self):
        self.lost(90000, 'Dropped', when=timezone.now() - timedelta(days=400))
        self.assertEqual(self.get('lost', period='this_month')['count'], 0)

    def test_how_far_a_lost_deal_got_is_reported(self):
        self.lost(50000, 'Finance', stage={'pushed_to_accounts': True})
        self.lost(30000, 'Quote ignored')                  # with a BDE: site visit
        self.lost(20000, 'No contact', owner=False)        # never left the desk
        stages = {r['stage']: r['count'] for r in self.get('lost')['by_stage']}
        self.assertEqual(stages, {'accounts': 1, 'site_visit': 1, 'tele_caller': 1})

    def test_a_trashed_lost_lead_is_not_a_loss(self):
        lead = self.lost(50000, 'Gone')
        Lead.objects.filter(pk=lead.pk).update(is_trashed=True)
        self.assertEqual(self.get('lost')['count'], 0)

    # ── Collection ──
    def test_a_discounted_deal_paid_in_full_is_fully_paid(self):
        """Net, not gross — otherwise every discount looks like a shortfall."""
        self.won(100000, discount=20000)
        c = self.get('collection')
        self.assertEqual(c['fully_paid'], 1)
        self.assertEqual(c['partially_paid'], 0)
        self.assertEqual(c['billed'], '80000.00')

    def test_a_short_payment_is_partly_paid(self):
        self.won(100000, received=40000)
        c = self.get('collection')
        self.assertEqual((c['fully_paid'], c['partially_paid']), (0, 1))
        self.assertEqual(c['collection_rate'], 40.0)

    def test_payment_modes_are_split_by_what_came_in(self):
        self.won(100000, mode='cash')
        self.won(60000, mode='upi')
        modes = {m['mode']: m['amount'] for m in self.get('collection')['by_mode']}
        self.assertEqual(modes, {'cash': '100000.00', 'upi': '60000.00'})

    def test_a_deal_with_no_recorded_mode_is_named_not_hidden(self):
        self.won(50000, mode='')
        modes = [m['label'] for m in self.get('collection')['by_mode']]
        self.assertIn('Not recorded', modes)

    # ── Delivery ──
    def test_delivery_counts_built_against_won(self):
        from .models import Project
        a = self.won(100000)
        self.won(50000)
        Project.objects.create(lead=a, is_complete=True, completed_at=timezone.now())
        d = self.get('delivery')
        self.assertEqual(d['won'], 2)
        self.assertEqual(d['completed'], 1)
        self.assertEqual(d['not_started'], 1)
        self.assertEqual(d['completion_rate'], 50.0)

    def test_a_project_underway_is_neither_done_nor_unstarted(self):
        from .models import Project
        lead = self.won(100000)
        Project.objects.create(lead=lead, is_complete=False)
        d = self.get('delivery')
        self.assertEqual((d['completed'], d['in_progress'], d['not_started']), (0, 1, 0))

    # ── Segments ──
    def test_revenue_splits_by_connection_type(self):
        self.won(300000, conn='commercial')
        self.won(100000, conn='residential')
        rows = {r['name']: r['revenue'] for r in self.get('segments')['by_connection']}
        self.assertEqual(rows, {'Commercial': '300000.00', 'Residential': '100000.00'})

    def test_a_deal_with_no_site_visit_is_labelled_not_recorded(self):
        self.won(90000)
        rows = [r['name'] for r in self.get('segments')['by_connection']]
        self.assertEqual(rows, ['Not recorded'])

    # ── Running total ──
    def test_the_monthly_series_carries_a_running_total(self):
        self.won(100000)
        monthly = self.client.get('/api/company-performance/?period=all',
                                  **self.auth()).json()['monthly']
        self.assertEqual(monthly[-1]['cumulative'], '100000.00')

    def test_the_running_total_ends_at_the_period_revenue(self):
        self.won(100000)
        self.won(50000)
        data = self.client.get('/api/company-performance/?period=all', **self.auth()).json()
        self.assertEqual(data['monthly'][-1]['cumulative'], data['headline']['revenue'])


class DuplicateLeadSubmissionTests(TestCase):
    """The same lead submitted twice is one lead.

    A double-click, a retried request or a second tab all arrive as separate
    POSTs carrying identical details. Each used to become its own row, which is
    how one customer appeared in the list five times over.
    """

    def setUp(self):
        self.caller = mk('dup_caller', 'tele_caller')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.caller)}

    def post(self, user=None, **fields):
        payload = {'first_name': 'Pradeep', 'last_name': 'Kumar', 'phone': '918943350861'}
        payload.update(fields)
        return self.client.post('/api/leads/', data=payload,
                                content_type='application/json', **self.auth(user))

    def test_the_first_submission_creates_the_lead(self):
        r = self.post()
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(Lead.objects.count(), 1)

    def test_a_second_identical_submission_makes_no_second_lead(self):
        self.post()
        self.post()
        self.assertEqual(Lead.objects.count(), 1)

    def test_five_clicks_still_make_one_lead(self):
        """The shape of the bug as it was reported."""
        for _ in range(5):
            self.post()
        self.assertEqual(Lead.objects.filter(phone='918943350861').count(), 1)

    def test_the_repeat_is_answered_with_the_lead_that_exists(self):
        """Not an error: from the caller's side the submission did succeed."""
        first = self.post().json()
        again = self.post()
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()['id'], first['id'])

    def test_a_different_person_on_the_same_phone_is_still_created(self):
        """A shared family phone is not a duplicate."""
        self.post()
        self.post(first_name='Anitha')
        self.assertEqual(Lead.objects.count(), 2)

    def test_a_different_phone_is_still_created(self):
        self.post()
        self.post(phone='919000000001')
        self.assertEqual(Lead.objects.count(), 2)

    def test_a_lead_with_no_phone_is_never_treated_as_a_duplicate(self):
        """Without a phone there is nothing identifying enough to match on."""
        self.post(phone='')
        self.post(phone='')
        self.assertEqual(Lead.objects.count(), 2)

    def test_the_same_customer_can_be_filed_again_later(self):
        """A second enquiry weeks later is real business, not a stray click."""
        self.post()
        Lead.objects.all().update(created_at=timezone.now() - timedelta(days=30))
        self.post()
        self.assertEqual(Lead.objects.count(), 2)

    def test_refiling_a_trashed_lead_creates_it_again(self):
        """It was deleted on purpose; adding it back is a real create."""
        self.post()
        Lead.objects.all().update(is_trashed=True)
        r = self.post()
        self.assertEqual(r.status_code, 201, r.content[:200])
        self.assertEqual(Lead.objects.filter(is_trashed=False).count(), 1)

    def test_the_name_match_ignores_case_and_padding(self):
        self.post()
        self.post(first_name='  pradeep ', last_name='KUMAR')
        self.assertEqual(Lead.objects.count(), 1)

    def test_a_duplicate_leaves_no_second_activity_log(self):
        """Otherwise the lead's history shows it being created twice."""
        self.post()
        self.post()
        from .models import ActivityLog
        created = ActivityLog.objects.filter(activity_type='lead_created').count()
        self.assertEqual(created, 1)

    def test_a_bde_is_still_refused_outright(self):
        """The duplicate check must not become a way around who may add leads."""
        bde = mk('dup_bde', 'bde')
        self.assertEqual(self.post(user=bde).status_code, 403)
        self.assertEqual(Lead.objects.count(), 0)


class DuplicateGroupingTests(TestCase):
    """Two leads are the same customer when they share a phone or an email."""

    def setUp(self):
        self.boss = mk('dg_admin', 'admin')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.boss)}

    def lead(self, name, phone='', email=''):
        return Lead.objects.create(first_name=name, phone=phone, email=email)

    def groups(self, user=None):
        r = self.client.get('/api/leads/duplicates/', **self.auth(user))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()['groups']

    # ── Phone shapes ──
    def test_a_country_code_does_not_make_a_second_customer(self):
        """The single biggest source of duplicates the import route produces."""
        self.lead('Nikhil', phone='+919380077570')
        self.lead('Prarthana', phone='9380077570')
        groups = self.groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['match'], 'phone')
        self.assertEqual(groups[0]['key'], '9380077570')
        self.assertEqual(groups[0]['count'], 2)

    def test_spacing_and_punctuation_are_ignored(self):
        self.lead('A', phone='+91 93800-77570')
        self.lead('B', phone='9380077570')
        self.assertEqual(len(self.groups()), 1)

    def test_different_numbers_are_not_grouped(self):
        self.lead('A', phone='9380077570')
        self.lead('B', phone='9380077571')
        self.assertEqual(self.groups(), [])

    def test_a_lead_with_no_phone_or_email_is_never_grouped(self):
        self.lead('A')
        self.lead('B')
        self.assertEqual(self.groups(), [])

    # ── Email ──
    def test_the_same_email_groups_regardless_of_case(self):
        self.lead('A', email='Shefin@Gmail.com')
        self.lead('B', email='shefin@gmail.com')
        groups = self.groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['match'], 'email')

    def test_a_pair_sharing_both_is_reported_once(self):
        """Otherwise merging the phone group leaves a stale email group behind."""
        self.lead('A', phone='+919380077570', email='x@y.com')
        self.lead('B', phone='9380077570', email='x@y.com')
        groups = self.groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['match'], 'phone')

    def test_an_email_pairing_the_phone_pass_missed_is_still_reported(self):
        self.lead('A', phone='9000000001', email='same@y.com')
        self.lead('B', phone='9000000002', email='same@y.com')
        self.assertEqual([g['match'] for g in self.groups()], ['email'])

    # ── What the page needs ──
    def test_the_oldest_is_suggested_as_the_one_to_keep(self):
        first = self.lead('Older', phone='9380077570')
        self.lead('Newer', phone='9380077570')
        Lead.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=5))
        self.assertEqual(self.groups()[0]['suggested_keep'], first.pk)

    def test_a_trashed_lead_is_not_a_duplicate(self):
        self.lead('A', phone='9380077570')
        gone = self.lead('B', phone='9380077570')
        Lead.objects.filter(pk=gone.pk).update(is_trashed=True)
        self.assertEqual(self.groups(), [])

    def test_a_row_says_what_would_block_a_merge(self):
        from .models import SiteVisit
        self.lead('A', phone='9380077570')
        stuck = self.lead('B', phone='9380077570')
        SiteVisit.objects.create(lead=stuck)
        rows = {r['id']: r for r in self.groups()[0]['leads']}
        self.assertEqual(rows[stuck.pk]['blockers'], ['a site visit'])

    def test_a_bde_cannot_open_the_duplicate_list(self):
        self.assertEqual(
            self.client.get('/api/leads/duplicates/', **self.auth(mk('dg_bde', 'bde'))).status_code,
            403)


class MergeDuplicateLeadsTests(TestCase):
    """Merging keeps one lead and folds the others into it."""

    def setUp(self):
        self.boss = mk('md_admin', 'admin')
        self.keep = Lead.objects.create(first_name='Nikhil', phone='+919380077570')
        self.dupe = Lead.objects.create(first_name='Nikhil', last_name='Joseph',
                                        phone='9380077570', email='nik@gmail.com',
                                        district='Ernakulam')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.boss)}

    def merge(self, keep=None, others=None, user=None):
        return self.client.post('/api/leads/merge-duplicates/', data={
            'keep': (keep or self.keep).pk,
            'merge': [l.pk for l in (others or [self.dupe])],
        }, content_type='application/json', **self.auth(user))

    def test_the_duplicate_goes_to_trash(self):
        r = self.merge()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.dupe.refresh_from_db()
        self.assertTrue(self.dupe.is_trashed)

    def test_the_kept_lead_stays(self):
        self.merge()
        self.keep.refresh_from_db()
        self.assertFalse(self.keep.is_trashed)

    def test_the_merge_is_recoverable(self):
        """Trashed, not destroyed — a merge made in error can be undone."""
        self.merge()
        self.assertTrue(Lead.objects.filter(pk=self.dupe.pk).exists())

    def test_blanks_on_the_kept_lead_are_filled_in(self):
        self.merge()
        self.keep.refresh_from_db()
        self.assertEqual(self.keep.email, 'nik@gmail.com')
        self.assertEqual(self.keep.last_name, 'Joseph')
        self.assertEqual(self.keep.district, 'Ernakulam')

    def test_what_the_kept_lead_already_had_is_not_overwritten(self):
        self.keep.district = 'Kollam'
        self.keep.save()
        self.merge()
        self.keep.refresh_from_db()
        self.assertEqual(self.keep.district, 'Kollam')

    def test_notes_are_joined_rather_than_dropped(self):
        """Two notes are two things the customer said."""
        self.keep.notes = 'Called Monday'
        self.keep.save()
        self.dupe.notes = 'Wants a quote'
        self.dupe.save()
        self.merge()
        self.keep.refresh_from_db()
        self.assertIn('Called Monday', self.keep.notes)
        self.assertIn('Wants a quote', self.keep.notes)

    def test_history_moves_to_the_kept_lead(self):
        from .models import ActivityLog
        ActivityLog.objects.create(activity_type='note_added', description='Spoke to them',
                                   lead=self.dupe)
        self.merge()
        self.assertTrue(ActivityLog.objects.filter(lead=self.keep,
                                                   description='Spoke to them').exists())

    def test_the_merge_is_recorded_on_the_kept_lead(self):
        from .models import ActivityLog
        self.merge()
        self.assertTrue(ActivityLog.objects.filter(
            lead=self.keep, description__icontains='Merged').exists())

    # ── What it refuses ──
    def test_a_duplicate_carrying_real_work_is_refused(self):
        """Folding away a site visit would discard something that happened."""
        from .models import SiteVisit
        SiteVisit.objects.create(lead=self.dupe)
        r = self.merge()
        self.assertEqual(r.status_code, 400)
        self.assertIn('site visit', r.json()['error'])
        self.dupe.refresh_from_db()
        self.assertFalse(self.dupe.is_trashed)

    def test_a_converted_duplicate_is_refused(self):
        self.dupe.status = 'converted'
        self.dupe.save()
        self.assertEqual(self.merge().status_code, 400)

    def test_work_on_the_kept_lead_is_no_obstacle(self):
        """It is being kept, so nothing of its own is at risk."""
        from .models import SiteVisit
        SiteVisit.objects.create(lead=self.keep)
        self.assertEqual(self.merge().status_code, 200)

    def test_merging_a_lead_into_itself_is_refused(self):
        r = self.merge(others=[self.keep])
        self.assertEqual(r.status_code, 400)

    def test_a_lead_that_is_not_visible_cannot_be_merged(self):
        caller = mk('md_caller', 'tele_caller')
        r = self.merge(user=caller)
        self.assertIn(r.status_code, (403, 404))

    def test_a_bde_cannot_merge(self):
        self.assertEqual(self.merge(user=mk('md_bde', 'bde')).status_code, 403)


class ImportSkipsDuplicateLeadsTests(TestCase):
    """A re-uploaded sheet must not double the lead book."""

    def setUp(self):
        self.boss = mk('imp_admin', 'admin')

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.boss)}

    def upload(self, body):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('leads.csv', body.encode('utf-8'), content_type='text/csv')
        return self.client.post('/api/leads/bulk_upload/', data={'file': f}, **self.auth())

    HEAD = 'first_name,last_name,email,phone\n'

    def test_a_row_matching_an_existing_lead_is_skipped(self):
        Lead.objects.create(first_name='Nikhil', phone='+919380077570')
        r = self.upload(self.HEAD + 'Prarthana,,,9380077570\n')
        self.assertEqual(r.json()['duplicates_skipped'], 1)
        self.assertEqual(Lead.objects.count(), 1)

    def test_a_row_matching_on_email_is_skipped(self):
        Lead.objects.create(first_name='A', email='x@y.com')
        r = self.upload(self.HEAD + 'B,,X@Y.com,9000000001\n')
        self.assertEqual(r.json()['duplicates_skipped'], 1)
        self.assertEqual(Lead.objects.count(), 1)

    def test_the_same_person_listed_twice_in_one_sheet_lands_once(self):
        r = self.upload(self.HEAD + 'A,,,9380077570\nA,,,+919380077570\n')
        self.assertEqual(r.json()['created'], 1)
        self.assertEqual(r.json()['duplicates_skipped'], 1)

    def test_new_rows_still_import(self):
        Lead.objects.create(first_name='Old', phone='9000000000')
        r = self.upload(self.HEAD + 'New,,,9111111111\nOld,,,9000000000\n')
        self.assertEqual(r.json()['created'], 1)
        self.assertEqual(r.json()['duplicates_skipped'], 1)

    def test_re_uploading_the_same_file_says_so_rather_than_failing(self):
        """Not an error: there was simply nothing new in it."""
        body = self.HEAD + 'A,,,9380077570\n'
        self.upload(body)
        r = self.upload(body)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['created'], 0)
        self.assertIn('already on the books', r.json()['message'])

    def test_rows_without_a_phone_or_email_are_all_imported(self):
        """Nothing identifies them, so nothing marks them as the same person."""
        r = self.upload(self.HEAD + 'A,,,\nB,,,\n')
        self.assertEqual(r.json()['created'], 2)

    def test_a_row_matching_a_trashed_lead_is_imported(self):
        gone = Lead.objects.create(first_name='Old', phone='9380077570')
        Lead.objects.filter(pk=gone.pk).update(is_trashed=True)
        r = self.upload(self.HEAD + 'Back,,,9380077570\n')
        self.assertEqual(r.json()['created'], 1)


class ProjectionTests(TestCase):
    """Where the period lands if the rest of it goes like the part already run."""

    def setUp(self):
        self.boss = mk('pj_admin', 'admin')

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.boss)}

    def get(self, period='this_fy'):
        return self.client.get(f'/api/company-performance/?period={period}',
                               **self.auth()).json()

    def test_a_financial_year_projects_to_the_end_of_march(self):
        """Not to today: `resolve_period` caps its end so no figure counts
        tomorrow's business, but a year still finishes when it finishes."""
        from leads.performance_insights import period_end_for
        self.assertEqual(period_end_for('this_fy', date(2026, 4, 1), date(2026, 8, 13)),
                         date(2027, 3, 31))

    def test_a_month_projects_to_the_end_of_the_month(self):
        from leads.performance_insights import period_end_for
        self.assertEqual(period_end_for('this_month', date(2026, 8, 1), date(2026, 8, 13)),
                         date(2026, 8, 31))

    def test_february_is_not_assumed_to_have_thirty_days(self):
        from leads.performance_insights import period_end_for
        self.assertEqual(period_end_for('this_month', date(2024, 2, 1), date(2024, 2, 10)),
                         date(2024, 2, 29))

    def test_a_custom_range_ends_where_the_user_said(self):
        from leads.performance_insights import period_end_for
        self.assertEqual(period_end_for('custom', date(2026, 1, 1), date(2026, 3, 15)),
                         date(2026, 3, 15))

    def test_the_run_rate_scales_what_has_come_in(self):
        from leads.performance_insights import build_projections
        with patch('leads.performance_insights.timezone.localdate',
                   return_value=date(2026, 8, 10)):
            p = build_projections(start=date(2026, 8, 1), end=date(2026, 8, 10),
                                  period_key='this_month', revenue=Decimal('100000'),
                                  closed=5, leads=20, close_rate=25.0,
                                  avg_deal=Decimal('20000'))
        self.assertEqual((p['days_elapsed'], p['days_total']), (10, 31))
        self.assertEqual(p['revenue_per_day'], '10000.00')
        self.assertEqual(p['projected_revenue'], '310000.00')
        self.assertEqual(p['projected_closed_deals'], 16)

    def test_the_projection_says_what_it_assumed(self):
        from leads.performance_insights import build_projections
        with patch('leads.performance_insights.timezone.localdate',
                   return_value=date(2026, 8, 10)):
            p = build_projections(start=date(2026, 8, 1), end=date(2026, 8, 10),
                                  period_key='this_month', revenue=Decimal('100000'),
                                  closed=5, leads=20, close_rate=25.0,
                                  avg_deal=Decimal('20000'))
        self.assertIn('21 day(s)', p['assumption'])

    def test_all_time_has_nothing_to_project_to(self):
        self.assertIsNone(self.get(period='all')['projections'])

    def test_the_open_pipeline_leaves_out_what_is_finished(self):
        from .models import PaymentVerification
        Lead.objects.create(first_name='Open', phone='9500000001', status='new',
                            value=Decimal('50000'))
        Lead.objects.create(first_name='Dead', phone='9500000002',
                            status='not_interested', value=Decimal('90000'))
        won = Lead.objects.create(first_name='Won', phone='9500000003',
                                  status='converted', pushed_to_accounts=True,
                                  value=Decimal('70000'))
        PaymentVerification.objects.create(lead=won, amount_received=Decimal('70000'))
        p = self.get()['projections']
        self.assertEqual(p['open_leads'], 1)
        self.assertEqual(p['open_pipeline_value'], '50000.00')


class PeriodComparisonTests(TestCase):
    """This period against the same stretch of the one before."""

    def setUp(self):
        self.boss = mk('cmp_admin', 'admin')

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.boss)}

    def test_a_part_month_is_compared_with_the_same_part_of_the_last(self):
        """Comparing a fortnight against a whole month would show a collapse in
        business every month."""
        from leads.performance_insights import previous_window
        self.assertEqual(previous_window('this_month', date(2026, 8, 1), date(2026, 8, 13)),
                         (date(2026, 7, 1), date(2026, 7, 13)))

    def test_a_full_month_is_compared_with_the_whole_of_the_last(self):
        from leads.performance_insights import previous_window
        start, end = previous_window('this_month', date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual((start, end), (date(2026, 7, 1), date(2026, 7, 31)))

    def test_a_short_previous_month_is_not_overrun(self):
        """31 March has no counterpart in February."""
        from leads.performance_insights import previous_window
        _, end = previous_window('this_month', date(2026, 3, 1), date(2026, 3, 31))
        self.assertEqual(end, date(2026, 2, 28))

    def test_a_year_is_compared_with_the_year_before(self):
        from leads.performance_insights import previous_window
        self.assertEqual(previous_window('this_fy', date(2026, 4, 1), date(2026, 8, 13)),
                         (date(2025, 4, 1), date(2025, 8, 13)))

    def test_a_leap_day_survives_the_shift(self):
        from leads.performance_insights import previous_window
        start, end = previous_window('this_year', date(2024, 1, 1), date(2024, 2, 29))
        self.assertEqual(end, date(2023, 2, 28))

    def test_a_custom_range_is_compared_with_the_stretch_before_it(self):
        from leads.performance_insights import previous_window
        self.assertEqual(previous_window('custom', date(2026, 6, 10), date(2026, 6, 19)),
                         (date(2026, 5, 31), date(2026, 6, 9)))

    def test_all_time_has_nothing_before_it(self):
        from leads.performance_insights import previous_window
        self.assertIsNone(previous_window('all', None, None))

    def test_a_rise_is_reported_with_its_share(self):
        from leads.performance_insights import build_comparison
        c = build_comparison({'revenue': '150000'}, {'revenue': '100000'},
                             (date(2026, 7, 1), date(2026, 7, 13)))
        revenue = next(m for m in c['metrics'] if m['key'] == 'revenue')
        self.assertEqual(revenue['direction'], 'up')
        self.assertEqual(revenue['change_pct'], 50.0)

    def test_a_fall_is_reported_as_a_fall(self):
        from leads.performance_insights import build_comparison
        c = build_comparison({'revenue': '50000'}, {'revenue': '100000'},
                             (date(2026, 7, 1), date(2026, 7, 13)))
        revenue = next(m for m in c['metrics'] if m['key'] == 'revenue')
        self.assertEqual((revenue['direction'], revenue['change_pct']), ('down', -50.0))

    def test_growth_from_nothing_is_not_called_a_percentage(self):
        """Going from zero to something is a start, not a rate."""
        from leads.performance_insights import build_comparison
        c = build_comparison({'revenue': '50000'}, {'revenue': '0'},
                             (date(2026, 7, 1), date(2026, 7, 13)))
        revenue = next(m for m in c['metrics'] if m['key'] == 'revenue')
        self.assertIsNone(revenue['change_pct'])
        self.assertTrue(revenue['from_nothing'])

    def test_no_movement_reads_as_flat(self):
        from leads.performance_insights import build_comparison
        c = build_comparison({'leads': 5}, {'leads': 5},
                             (date(2026, 7, 1), date(2026, 7, 13)))
        leads = next(m for m in c['metrics'] if m['key'] == 'leads')
        self.assertEqual(leads['direction'], 'flat')

    def test_the_board_carries_a_comparison(self):
        r = self.client.get('/api/company-performance/?period=this_month', **self.auth())
        self.assertIsNotNone(r.json()['comparison'])

    def test_all_time_carries_none(self):
        r = self.client.get('/api/company-performance/?period=all', **self.auth())
        self.assertIsNone(r.json()['comparison'])


class GrowthPaceTests(TestCase):
    """How fast the business is moving, month on month."""

    def growth(self, revenues):
        from leads.performance_insights import build_growth
        return build_growth([{'name': f'M{i}', 'revenue': str(v), 'closed': 1}
                             for i, v in enumerate(revenues)])

    def test_a_steady_climb_reports_its_pace(self):
        g = self.growth([100, 110, 121])
        self.assertEqual(g['average_pace'], 10.0)
        self.assertEqual(g['months_measured'], 2)

    def test_a_fall_is_a_negative_pace(self):
        self.assertEqual(self.growth([100, 50])['average_pace'], -50.0)

    def test_a_month_with_nothing_before_it_is_left_out_of_the_average(self):
        """Counting a leap from zero as a percentage would swamp the average."""
        g = self.growth([0, 100, 110])
        self.assertEqual(g['months_measured'], 1)
        self.assertEqual(g['average_pace'], 10.0)

    def test_one_month_is_not_a_pace(self):
        self.assertIsNone(self.growth([100]))

    def test_the_best_and_leanest_months_are_named(self):
        g = self.growth([100, 500, 50])
        self.assertEqual(g['best_month']['name'], 'M1')
        self.assertEqual(g['worst_month']['name'], 'M2')

    def test_the_direction_of_travel_compares_halves(self):
        """One good month can hide a decline and one bad month can fake it."""
        g = self.growth([100, 100, 200, 200])
        self.assertEqual(g['trend'], 'up')
        self.assertEqual(g['recent_vs_earlier_pct'], 100.0)

    def test_a_flat_business_is_steady_not_growing(self):
        self.assertEqual(self.growth([100, 100, 100, 100])['trend'], 'steady')

    def test_growth_survives_a_period_with_one_month_in_it(self):
        """It reads the trailing year, so picking This month must not blank it."""
        boss = mk('gr_admin', 'admin')
        r = self.client.get('/api/company-performance/?period=this_month',
                            HTTP_AUTHORIZATION=token_for(boss))
        self.assertIn('growth', r.json())


class PerformanceFindingsTests(TestCase):
    """Observations read off the figures, each one checkable against the page."""

    def findings(self, payload):
        from leads.performance_insights import build_findings
        return build_findings(payload)

    def base(self, **head):
        figures = {'leads': 50, 'converted': 10, 'closed_deals': 10, 'lost': 0,
                   'revenue': '1000000', 'outstanding': '0', 'close_rate': 20}
        figures.update(head)
        return {'headline': figures}

    def test_money_left_uncollected_is_flagged(self):
        texts = [f['text'] for f in self.findings(
            self.base(revenue='1000000', outstanding='400000'))]
        self.assertTrue(any('not been collected' in t for t in texts))

    def test_a_small_outstanding_balance_is_not_worth_flagging(self):
        texts = [f['text'] for f in self.findings(
            self.base(revenue='1000000', outstanding='1000'))]
        self.assertFalse(any('not been collected' in t for t in texts))

    def test_a_slump_against_last_period_is_flagged(self):
        payload = self.base()
        payload['comparison'] = {'metrics': [
            {'key': 'revenue', 'change_pct': -35.0, 'direction': 'down'}]}
        texts = [f['text'] for f in self.findings(payload)]
        self.assertTrue(any('below the same' in t for t in texts))

    def test_a_falling_trend_is_flagged(self):
        payload = self.base()
        payload['growth'] = {'trend': 'down', 'recent_vs_earlier_pct': -40.0}
        texts = [f['text'] for f in self.findings(payload)]
        self.assertTrue(any('below' in t and 'earlier' in t for t in texts))

    def test_a_thin_lead_book_is_not_judged_on_its_close_rate(self):
        texts = [f['text'] for f in self.findings(
            self.base(leads=2, converted=0, closed_deals=0, close_rate=0))]
        self.assertFalse(any('closed' in t and '%' in t for t in texts))

    def test_findings_carry_a_number_every_time(self):
        """A finding without a figure is an opinion."""
        payload = self.base(revenue='1000000', outstanding='400000', closed_deals=4)
        payload['delivery'] = {'won': 5, 'not_started': 2}
        for f in self.findings(payload):
            self.assertTrue(any(ch.isdigit() for ch in f['text']), f['text'])

    def test_nothing_is_invented_when_there_is_nothing_to_say(self):
        self.assertEqual(self.findings({'headline': {'leads': 0}}), [])


class AiSuggestionsTests(TestCase):
    """Advice is optional; the figures are not."""

    def payload(self):
        return {'period_label': 'FY 26-27',
                'headline': {'leads': 50, 'closed_deals': 10, 'revenue': '100000'}}

    def test_no_key_means_no_suggestions_rather_than_a_placeholder(self):
        from leads.performance_insights import ai_suggestions
        with self.settings(GEMINI_API_KEY=''):
            self.assertIsNone(ai_suggestions(self.payload(), [{'text': 'x'}], None))

    def test_a_failed_call_does_not_take_the_board_down(self):
        from leads.performance_insights import ai_suggestions
        with self.settings(GEMINI_API_KEY='test-key'), \
             patch('ai_manager.ai_meeting._call_gemini', side_effect=RuntimeError('no')):
            self.assertIsNone(ai_suggestions(self.payload(), [{'text': 'x'}], None))

    def test_the_model_is_given_the_findings_not_asked_for_the_numbers(self):
        from leads.performance_insights import ai_suggestions
        with self.settings(GEMINI_API_KEY='test-key'), \
             patch('ai_manager.ai_meeting._call_gemini', return_value='1. Do the thing.') as call:
            out = ai_suggestions(self.payload(),
                                 [{'text': '4 deals have no money against them.'}], None)
        self.assertEqual(out, '1. Do the thing.')
        prompt = call.call_args[0][0]
        self.assertIn('4 deals have no money against them.', prompt)
        self.assertIn('Revenue', prompt)

    def test_the_model_is_told_not_to_invent_figures(self):
        from leads.performance_insights import AI_SYSTEM
        self.assertIn('Never state a number that is not in the data', AI_SYSTEM)

    def test_an_empty_reply_is_treated_as_no_advice(self):
        from leads.performance_insights import ai_suggestions
        with self.settings(GEMINI_API_KEY='test-key'), \
             patch('ai_manager.ai_meeting._call_gemini', return_value='   '):
            self.assertIsNone(ai_suggestions(self.payload(), [{'text': 'x'}], None))

    def test_the_board_still_answers_when_the_model_is_unavailable(self):
        boss = mk('ai_admin', 'admin')
        with self.settings(GEMINI_API_KEY=''):
            r = self.client.get('/api/company-performance/?period=this_fy',
                                HTTP_AUTHORIZATION=token_for(boss))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['ai_suggestions'])
        self.assertIn('findings', r.json())


class MaintenanceBadgeMatchesThePageTests(TestCase):
    """The sidebar badge counts what the module can actually show.

    It used to count MaintenanceVisit rows outright, with no join back to a
    customer, so a visit went on being counted after its customer had been
    trashed or taken off liasoning — a badge of 2 sitting over a page reading
    "Nothing scheduled yet".
    """

    def setUp(self):
        self.officer = mk('badge_officer', 'liasoning_officer')

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.officer)}

    def customer(self, name='Ramesh Kumar', phone='9895000300', completed='2023-03-15'):
        r = self.client.post('/api/leads/maintenance-customers/',
                             data={'name': name, 'phone': phone, 'completed_on': completed},
                             content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:300])
        return Lead.objects.get(pk=r.json()['id'])

    def badge(self):
        r = self.client.get('/api/leads/module-counts/', **self.auth())
        return r.json()['counts'].get('periodic-maintenance', 0)

    def page(self):
        r = self.client.get('/api/leads/periodic-maintenance/', **self.auth())
        return r.json()

    # ── The invariant the bug broke ──
    def test_the_badge_equals_what_the_page_lists(self):
        self.customer()
        page = self.page()
        due = [v for v in page['upcoming']
               if v['due_date'] <= (timezone.localdate() + timedelta(days=1)).isoformat()]
        self.assertEqual(self.badge(), len(due))

    def test_a_trashed_customer_takes_its_visits_off_the_badge(self):
        lead = self.customer()
        self.assertGreater(self.badge(), 0)
        Lead.objects.filter(pk=lead.pk).update(is_trashed=True)
        self.assertEqual(self.badge(), 0)

    def test_a_customer_taken_off_liasoning_takes_its_visits_too(self):
        lead = self.customer()
        Lead.objects.filter(pk=lead.pk).update(pushed_to_liasoning=False)
        self.assertEqual(self.badge(), 0)

    def test_the_page_does_not_list_a_trashed_customer(self):
        """The Trash is out of every figure, here as everywhere."""
        lead = self.customer()
        Lead.objects.filter(pk=lead.pk).update(is_trashed=True)
        page = self.page()
        self.assertEqual(page['scheduled'], [])
        self.assertEqual(page['upcoming'], [])

    def test_the_badge_and_the_page_agree_once_the_customer_is_gone(self):
        lead = self.customer()
        Lead.objects.filter(pk=lead.pk).update(is_trashed=True)
        self.assertEqual(self.badge(), 0)
        self.assertEqual(self.page()['upcoming'], [])

    # ── What still counts ──
    def test_an_overdue_visit_counts(self):
        self.customer(completed='2023-03-15')
        self.assertGreater(self.badge(), 0)

    def test_a_visit_falling_due_tomorrow_counts(self):
        """A day's notice, so the officer can arrange the trip."""
        from .models import MaintenanceVisit
        lead = self.customer()
        MaintenanceVisit.objects.filter(plan__lead=lead).update(
            is_complete=True, due_date=timezone.localdate() + timedelta(days=365))
        one = MaintenanceVisit.objects.filter(plan__lead=lead).first()
        one.is_complete = False
        one.due_date = timezone.localdate() + timedelta(days=1)
        one.save(update_fields=['is_complete', 'due_date'])
        self.assertEqual(self.badge(), 1)

    def test_a_visit_further_out_does_not_count_yet(self):
        from .models import MaintenanceVisit
        lead = self.customer()
        MaintenanceVisit.objects.filter(plan__lead=lead).update(
            is_complete=False, due_date=timezone.localdate() + timedelta(days=30))
        self.assertEqual(self.badge(), 0)

    def test_a_visit_already_filled_in_does_not_count(self):
        from .models import MaintenanceVisit
        lead = self.customer()
        MaintenanceVisit.objects.filter(plan__lead=lead).update(is_complete=True)
        self.assertEqual(self.badge(), 0)

    def test_two_customers_are_counted_together(self):
        from .models import MaintenanceVisit
        a = self.customer(phone='9895000301')
        b = self.customer(name='Asha Devi', phone='9895000302')
        for lead in (a, b):
            MaintenanceVisit.objects.filter(plan__lead=lead).update(
                is_complete=True, due_date=timezone.localdate() + timedelta(days=365))
            one = MaintenanceVisit.objects.filter(plan__lead=lead).first()
            one.is_complete = False
            one.due_date = timezone.localdate()
            one.save(update_fields=['is_complete', 'due_date'])
        self.assertEqual(self.badge(), 2)

    def test_trashing_one_of_two_leaves_the_other_counted(self):
        from .models import MaintenanceVisit
        a = self.customer(phone='9895000303')
        b = self.customer(name='Asha Devi', phone='9895000304')
        for lead in (a, b):
            MaintenanceVisit.objects.filter(plan__lead=lead).update(
                is_complete=True, due_date=timezone.localdate() + timedelta(days=365))
            one = MaintenanceVisit.objects.filter(plan__lead=lead).first()
            one.is_complete = False
            one.due_date = timezone.localdate()
            one.save(update_fields=['is_complete', 'due_date'])
        Lead.objects.filter(pk=a.pk).update(is_trashed=True)
        self.assertEqual(self.badge(), 1)

    def test_a_customer_with_no_schedule_adds_nothing(self):
        Lead.objects.create(first_name='Unscheduled', phone='9895000305',
                            pushed_to_liasoning=True)
        self.assertEqual(self.badge(), 0)


class SiteVisitPhotoSlotTests(TestCase):
    """Site Visit Photos: a Site Photos slot, and one Earthing slot in place of
    the numbered three.

    Every slot already holds as many files as the BDE wants to attach, so the
    trio only forced a choice about which photo went where.
    """

    def setUp(self):
        # Filling in a site visit belongs to the BDE, not the tele caller.
        self.officer = mk('slot_bde', 'bde')
        self.lead = Lead.objects.create(first_name='Sitevisit', phone='9895000400',
                                        bde=self.officer, assigned_to=self.officer)

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.officer)}

    def upload(self, doc_type, name='shot.jpg'):
        return self.client.post(
            f'/api/leads/{self.lead.id}/site-visit/documents/',
            data={'doc_type': doc_type,
                  'file': SimpleUploadedFile(name, b'\xff\xd8\xff', content_type='image/jpeg')},
            **self.auth())

    def slots(self):
        from .views import SITE_VISIT_ATTACHMENTS
        return dict(SITE_VISIT_ATTACHMENTS)

    # ── The new slots ──
    def test_site_photos_is_a_slot(self):
        self.assertEqual(self.slots().get('photo_site'), 'Site Photos')

    def test_earthing_is_a_slot(self):
        self.assertEqual(self.slots().get('photo_earthing'), 'Earthing')

    def test_a_site_photo_can_be_uploaded(self):
        r = self.upload('photo_site')
        self.assertEqual(r.status_code, 201, r.content[:200])

    def test_an_earthing_photo_can_be_uploaded(self):
        r = self.upload('photo_earthing')
        self.assertEqual(r.status_code, 201, r.content[:200])

    def test_the_one_earthing_slot_takes_several_photos(self):
        """Which is what made three numbered slots pointless."""
        from .models import SiteVisitDocument
        for i in range(3):
            self.assertEqual(self.upload('photo_earthing', f'e{i}.jpg').status_code, 201)
        self.assertEqual(
            SiteVisitDocument.objects.filter(site_visit__lead=self.lead,
                                             doc_type='photo_earthing').count(), 3)

    # ── The old slots ──
    def test_the_numbered_earthing_slots_are_gone(self):
        for old in ('photo_earthing_1', 'photo_earthing_2', 'photo_earthing_3'):
            self.assertNotIn(old, self.slots(), old)

    def test_uploading_to_a_numbered_slot_is_refused(self):
        for old in ('photo_earthing_1', 'photo_earthing_2', 'photo_earthing_3'):
            self.assertEqual(self.upload(old).status_code, 400, old)

    # ── The rest of the section is untouched ──
    def test_the_other_photo_slots_still_exist(self):
        slots = self.slots()
        for key in ('photo_meterbox', 'photo_directional', 'photo_hand_sketch',
                    'photo_feasibility_report'):
            self.assertIn(key, slots, key)

    def test_an_earthing_photo_is_labelled_earthing_not_a_raw_key(self):
        """The document bundle labels each file from this same map."""
        self.upload('photo_earthing')
        self.assertEqual(self.slots()['photo_earthing'], 'Earthing')


class EarthingSlotMergeMigrationTests(TestCase):
    """The photos already filed under Earthing 1/2/3 move to the new slot.

    Left behind they would still be on disk and still bundled, but labelled with
    a raw key and invisible in the form — which for whoever opens the lead next
    is indistinguishable from the photos being lost.
    """

    def setUp(self):
        from .models import SiteVisit, SiteVisitDocument
        self.SiteVisitDocument = SiteVisitDocument
        lead = Lead.objects.create(first_name='Old', phone='9895000401')
        self.sv = SiteVisit.objects.create(lead=lead)

    def add(self, doc_type):
        return self.SiteVisitDocument.objects.create(
            site_visit=self.sv, doc_type=doc_type,
            file=SimpleUploadedFile(f'{doc_type}.jpg', b'\xff\xd8\xff',
                                    content_type='image/jpeg'))

    def run_merge(self):
        """Run the migration's own function, so the test covers what ships."""
        from importlib import import_module
        from django.apps import apps
        module = import_module('leads.migrations.0070_merge_earthing_photo_slots')
        module.merge(apps, None)
        return module

    def test_every_numbered_photo_moves_across(self):
        for slot in ('photo_earthing_1', 'photo_earthing_2', 'photo_earthing_3'):
            self.add(slot)
        self.run_merge()
        self.assertEqual(
            self.SiteVisitDocument.objects.filter(doc_type='photo_earthing').count(), 3)

    def test_nothing_is_left_under_the_old_slots(self):
        self.add('photo_earthing_1')
        self.add('photo_earthing_2')
        self.run_merge()
        self.assertEqual(
            self.SiteVisitDocument.objects.filter(doc_type__startswith='photo_earthing_').count(), 0)

    def test_no_photo_is_lost(self):
        for slot in ('photo_earthing_1', 'photo_earthing_2', 'photo_meterbox'):
            self.add(slot)
        before = self.SiteVisitDocument.objects.count()
        self.run_merge()
        self.assertEqual(self.SiteVisitDocument.objects.count(), before)

    def test_other_slots_are_left_alone(self):
        self.add('photo_meterbox')
        self.add('photo_directional')
        self.run_merge()
        self.assertEqual(self.SiteVisitDocument.objects.filter(doc_type='photo_meterbox').count(), 1)
        self.assertEqual(self.SiteVisitDocument.objects.filter(doc_type='photo_directional').count(), 1)

    def test_reversing_keeps_the_photos_visible(self):
        """Which of the three a photo came from is not recorded once merged, so
        the reverse puts them all somewhere they can still be seen."""
        self.add('photo_earthing_1')
        self.add('photo_earthing_2')
        module = self.run_merge()
        from django.apps import apps
        module.unmerge(apps, None)
        self.assertEqual(
            self.SiteVisitDocument.objects.filter(doc_type='photo_earthing_1').count(), 2)
        self.assertEqual(
            self.SiteVisitDocument.objects.filter(doc_type='photo_earthing').count(), 0)


class ClosedDealsPeriodFilterTests(TestCase):
    """The Closed Deals board, filtered by when the deals closed.

    Measured on the Closed date — the one in the table — so the filter selects
    what the reader can see rather than some other date behind it.
    """

    def setUp(self):
        self.boss = mk('cdp_admin', 'admin')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.boss)}

    def won(self, value, closed_on):
        from .models import PaymentVerification
        lead = Lead.objects.create(
            first_name='Deal', last_name=str(value), phone=f'94{value:08d}',
            status='converted', is_lost=False, pushed_to_accounts=True,
            value=Decimal(value))
        PaymentVerification.objects.create(lead=lead, amount_received=Decimal(value))
        Lead.objects.filter(pk=lead.pk).update(status_changed_at=closed_on)
        return lead

    def board(self, **params):
        qs = '&'.join(f'{k}={v}' for k, v in params.items())
        r = self.client.get(f'/api/leads/closed-deals/?{qs}', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    # ── The default ──
    def test_the_board_shows_everything_by_default(self):
        """A working list: a deal closed last year must not go missing behind a
        filter nobody set."""
        self.won(50000, timezone.now() - timedelta(days=800))
        self.won(60000, timezone.now())
        d = self.board()
        self.assertEqual(d['summary']['count'], 2)
        self.assertEqual(d['period'], 'all')
        self.assertEqual(d['period_label'], 'All time')

    # ── The windows ──
    def test_this_month_keeps_only_this_month(self):
        self.won(50000, timezone.now() - timedelta(days=400))
        self.won(60000, timezone.now())
        self.assertEqual(self.board(period='this_month')['summary']['count'], 1)

    def test_this_year_keeps_only_this_year(self):
        self.won(50000, timezone.now() - timedelta(days=800))
        self.won(60000, timezone.now())
        self.assertEqual(self.board(period='this_year')['summary']['count'], 1)

    def test_all_time_keeps_everything(self):
        self.won(50000, timezone.now() - timedelta(days=800))
        self.won(60000, timezone.now())
        self.assertEqual(self.board(period='all')['summary']['count'], 2)

    def test_a_custom_range_is_honoured(self):
        self.won(50000, timezone.now() - timedelta(days=100))
        self.won(60000, timezone.now())
        far = (timezone.localdate() - timedelta(days=120)).isoformat()
        near = (timezone.localdate() - timedelta(days=80)).isoformat()
        d = self.board(period='custom', **{'from': far, 'to': near})
        self.assertEqual(d['summary']['count'], 1)
        self.assertEqual(d['summary']['deal_value'], '50000.00')

    # ── The totals follow the filter ──
    def test_the_summary_describes_exactly_the_rows_listed(self):
        """The point of filtering on the server rather than in the client."""
        self.won(50000, timezone.now() - timedelta(days=400))
        self.won(60000, timezone.now())
        d = self.board(period='this_month')
        self.assertEqual(len(d['deals']), d['summary']['count'])
        self.assertEqual(Decimal(d['summary']['deal_value']),
                         sum(Decimal(x['value']) for x in d['deals']))

    def test_the_window_is_named_back(self):
        d = self.board(period='this_month')
        self.assertIn('This month', d['period_label'])

    # ── It works with the other filters ──
    def test_the_window_and_the_owner_filter_together(self):
        caller = mk('cdp_caller', 'tele_caller')
        mine = self.won(70000, timezone.now())
        Lead.objects.filter(pk=mine.pk).update(tele_caller=caller)
        self.won(80000, timezone.now())
        d = self.board(period='this_month', tele_caller=caller.pk)
        self.assertEqual(d['summary']['count'], 1)
        self.assertEqual(d['summary']['deal_value'], '70000.00')

    def test_the_window_and_the_bde_filter_together(self):
        bde = mk('cdp_bde', 'bde')
        mine = self.won(90000, timezone.now())
        Lead.objects.filter(pk=mine.pk).update(bde=bde)
        self.won(30000, timezone.now())
        d = self.board(period='this_month', bde=bde.pk)
        self.assertEqual(d['summary']['count'], 1)

    # ── The pickers ──
    def test_the_pickers_offer_the_people_on_the_board(self):
        bde = mk('cdp_bde2', 'bde')
        lead = self.won(40000, timezone.now())
        Lead.objects.filter(pk=lead.pk).update(bde=bde)
        d = self.board()
        self.assertEqual([p['id'] for p in d['bdes']], [bde.pk])

    def test_one_person_still_gets_a_picker_entry(self):
        """The page shows the control whenever there is anyone to pick — a board
        with a single owner must not look as though it cannot filter at all."""
        caller = mk('cdp_caller2', 'tele_caller')
        lead = self.won(45000, timezone.now())
        Lead.objects.filter(pk=lead.pk).update(tele_caller=caller)
        self.assertEqual(len(self.board()['tele_callers']), 1)


class RevenueIsMoneyReceivedTests(TestCase):
    """Revenue is what was paid, not what was invoiced.

    A deal billed for a lakh with forty thousand received is forty thousand of
    revenue; the rest is a debt. Every screen that says "revenue", "won value"
    or "converted revenue" reports the same thing, so one page cannot mean a
    different kind of number from another.
    """

    def setUp(self):
        self.boss = mk('rev_admin', 'admin')
        self.bde = mk('rev_bde', 'bde')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.boss)}

    def deal(self, value, received, discount=0, who=None):
        """A closed deal billed `value`, of which `received` has come in."""
        from .models import PaymentVerification
        who = who or self.bde
        lead = Lead.objects.create(
            first_name='Deal', last_name=str(value), phone=f'93{value:08d}',
            status='converted', is_lost=False, pushed_to_accounts=True,
            value=Decimal(value), bde=who, assigned_to=who, tele_caller=who)
        PaymentVerification.objects.create(
            lead=lead, amount_received=Decimal(received),
            discount_value=Decimal(discount))
        Lead.objects.filter(pk=lead.pk).update(status_changed_at=timezone.now())
        return lead

    # ── The definition itself ──
    def test_the_helper_sums_what_was_received(self):
        from .scopes import closed_deal_revenue
        self.deal(320000, 204000)
        self.assertEqual(closed_deal_revenue(), Decimal('204000.00'))

    def test_a_part_paid_deal_contributes_only_what_was_paid(self):
        from .scopes import closed_deal_revenue
        self.deal(100000, 40000)
        self.assertEqual(closed_deal_revenue(), Decimal('40000.00'))

    def test_billed_is_still_available_and_still_net_of_discount(self):
        """It has not gone away — it is what outstanding is measured against."""
        from django.db.models import Sum
        from .scopes import closed_deals, net_value
        self.deal(100000, 40000, discount=10000)
        billed = closed_deals().aggregate(t=Sum(net_value()))['t']
        self.assertEqual(billed, Decimal('90000.00'))

    # ── The screens ──
    def test_the_dashboard_revenue_tile_is_the_paid_amount(self):
        self.deal(320000, 204000)
        r = self.client.get('/api/dashboard-stats/', **self.auth())
        self.assertEqual(float(r.json()['total_revenue']), 204000.0)

    def test_company_performance_revenue_is_the_paid_amount(self):
        self.deal(320000, 204000)
        h = self.client.get('/api/company-performance/?period=all',
                            **self.auth()).json()['headline']
        self.assertEqual(h['revenue'], '204000.00')

    def test_company_performance_still_reports_what_was_billed(self):
        self.deal(320000, 204000)
        h = self.client.get('/api/company-performance/?period=all',
                            **self.auth()).json()['headline']
        self.assertEqual(h['billed'], '320000.00')

    def test_outstanding_is_the_gap_between_billed_and_received(self):
        """The figure that would have collapsed to zero if revenue and collected
        were the same number."""
        self.deal(320000, 204000)
        h = self.client.get('/api/company-performance/?period=all',
                            **self.auth()).json()['headline']
        self.assertEqual(h['outstanding'], '116000.00')

    def test_the_leaderboard_ranks_on_money_received(self):
        self.deal(320000, 204000)
        rows = self.client.get('/api/leaderboard/', **self.auth()).json()['leaderboard']
        mine = [r for r in rows if r.get('id') == self.bde.id]
        self.assertTrue(mine)
        self.assertEqual(float(mine[0]['revenue']), 204000.0)

    def test_my_performance_won_value_is_money_received(self):
        """It is shown to users as Converted Revenue."""
        self.deal(320000, 204000, who=self.bde)
        r = self.client.get(f'/api/users/{self.bde.id}/performance/', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(float(r.json()['summary']['won_value']), 204000.0)

    # ── What must not change ──
    def test_the_open_pipeline_is_still_valued_at_what_it_would_bill(self):
        """Nothing has been paid on an open lead, so valuing it at revenue would
        report the whole pipeline as worth nothing."""
        Lead.objects.create(first_name='Open', phone='9300000001', status='new',
                            value=Decimal('500000'))
        p = self.client.get('/api/company-performance/?period=this_fy',
                            **self.auth()).json()['projections']
        self.assertEqual(p['open_pipeline_value'], '500000.00')

    def test_the_closed_deals_board_still_shows_the_deal_value(self):
        """That board reports deal value, received and balance as three separate
        columns — it never called any of them revenue."""
        self.deal(320000, 204000)
        s = self.client.get('/api/leads/closed-deals/?period=all',
                            **self.auth()).json()['summary']
        self.assertEqual(s['deal_value'], '320000.00')
        self.assertEqual(s['received'], '204000.00')
        self.assertEqual(s['outstanding'], '116000.00')

    def test_a_deal_with_nothing_received_is_not_revenue(self):
        """It cannot be a closed deal at all without a payment, but a zero-value
        receipt must not sneak in as revenue either."""
        from .scopes import closed_deal_revenue
        self.deal(100000, 0)
        self.assertEqual(closed_deal_revenue(), Decimal('0.00'))


class BulkRestoreFromTrashTests(TestCase):
    """Restoring several leads at once.

    A bulk action is a shortcut, never a wider door: it is scoped exactly as
    restoring one at a time is, so ticking a box cannot reach a lead the caller
    could not already restore alone.
    """

    def setUp(self):
        self.admin = mk('br_admin', 'admin')
        self.caller = mk('br_caller', 'tele_caller')
        self.other = mk('br_other', 'tele_caller')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.admin)}

    def trashed(self, name, owner=None):
        lead = Lead.objects.create(first_name=name, phone=f'9895{abs(hash(name)) % 1000000:06d}',
                                   assigned_to=owner)
        Lead.objects.filter(pk=lead.pk).update(is_trashed=True, trashed_at=timezone.now())
        lead.refresh_from_db()
        return lead

    def restore(self, ids, user=None):
        return self.client.post('/api/leads/bulk-restore-trash/',
                                data={'ids': ids}, content_type='application/json',
                                **self.auth(user))

    def live(self, lead):
        lead.refresh_from_db()
        return not lead.is_trashed

    # ── The happy path ──
    def test_several_leads_come_back_together(self):
        a, b, c = self.trashed('A'), self.trashed('B'), self.trashed('C')
        r = self.restore([a.pk, b.pk, c.pk])
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['restored'], 3)
        self.assertTrue(all(self.live(x) for x in (a, b, c)))

    def test_the_ones_not_chosen_stay_in_the_trash(self):
        a, b = self.trashed('A'), self.trashed('B')
        self.restore([a.pk])
        self.assertTrue(self.live(a))
        self.assertFalse(self.live(b))

    def test_restoring_clears_the_trash_stamps(self):
        """Otherwise the lead comes back still carrying who binned it and when."""
        a = self.trashed('A')
        self.restore([a.pk])
        a.refresh_from_db()
        self.assertIsNone(a.trashed_at)
        self.assertIsNone(a.trashed_by)

    def test_the_reply_names_what_it_restored(self):
        a, b = self.trashed('A'), self.trashed('B')
        d = self.restore([a.pk, b.pk]).json()
        self.assertEqual(sorted(d['ids']), sorted([a.pk, b.pk]))

    # ── Scoping: no wider than restoring one at a time ──
    def test_a_caller_cannot_restore_someone_elses_lead(self):
        mine, theirs = self.trashed('Mine', owner=self.caller), self.trashed('Theirs', owner=self.other)
        d = self.restore([mine.pk, theirs.pk], user=self.caller).json()
        self.assertEqual(d['restored'], 1)
        self.assertTrue(self.live(mine))
        self.assertFalse(self.live(theirs))

    def test_what_could_not_be_restored_is_reported_not_hidden(self):
        """Half a restore that says nothing looks like a bug to whoever ticked
        the boxes."""
        mine, theirs = self.trashed('Mine', owner=self.caller), self.trashed('Theirs', owner=self.other)
        d = self.restore([mine.pk, theirs.pk], user=self.caller).json()
        self.assertEqual(d['skipped'], [theirs.pk])
        self.assertIn('no longer in your Trash', d['message'])

    def test_an_admin_reaches_the_whole_trash(self):
        a, b = self.trashed('A', owner=self.caller), self.trashed('B', owner=self.other)
        self.assertEqual(self.restore([a.pk, b.pk]).json()['restored'], 2)

    # ── Edges ──
    def test_an_empty_list_is_refused(self):
        self.assertEqual(self.restore([]).status_code, 400)

    def test_a_lead_that_is_not_in_the_trash_is_skipped(self):
        alive = Lead.objects.create(first_name='Alive', phone='9895111222')
        d = self.restore([alive.pk]).json()
        self.assertEqual(d['restored'], 0)
        self.assertEqual(d['skipped'], [alive.pk])

    def test_an_unknown_id_does_not_break_the_batch(self):
        a = self.trashed('A')
        d = self.restore([a.pk, 99999999]).json()
        self.assertEqual(d['restored'], 1)
        self.assertTrue(self.live(a))

    def test_rubbish_ids_are_ignored_rather_than_crashing(self):
        a = self.trashed('A')
        r = self.restore([a.pk, 'abc', None])
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['restored'], 1)

    def test_a_stranger_cannot_restore_anything(self):
        a = self.trashed('A')
        r = self.client.post('/api/leads/bulk-restore-trash/',
                             data={'ids': [a.pk]}, content_type='application/json')
        self.assertIn(r.status_code, (401, 403))
        self.assertFalse(self.live(a))

    def test_a_restored_lead_is_back_on_the_leads_list(self):
        a = self.trashed('A')
        self.restore([a.pk])
        r = self.client.get('/api/leads/', **self.auth())
        rows = r.json()
        rows = rows.get('results', rows) if isinstance(rows, dict) else rows
        self.assertIn(a.pk, [x['id'] for x in rows])


class DistrictIsAlwaysOneWeConfiguredTests(TestCase):
    """A lead's district is one from Settings, or none at all.

    Both importers already matched against the configured list, but every other
    way in could file any text — and a Meta lead arrived reading
    "Payyanur.kannur", a place and a district run together, naming no district
    anybody set up. The rule is enforced on the model now, so it holds however
    the lead is written.
    """

    def setUp(self):
        from .models import District
        self.District = District
        District.objects.get_or_create(name='Kannur', defaults={'is_active': True})
        District.objects.get_or_create(name='Ernakulam', defaults={'is_active': True})
        self.caller = mk('dist_caller', 'tele_caller')

    def make(self, district):
        lead = Lead.objects.create(first_name='D', phone='9895900001', district=district)
        lead.refresh_from_db()
        return lead.district

    # ── Writing ──
    def test_an_unconfigured_district_is_dropped(self):
        self.assertEqual(self.make('Payyanur.kannur'), '')

    def test_a_configured_district_is_kept(self):
        self.assertEqual(self.make('Ernakulam'), 'Ernakulam')

    def test_capitalisation_settles_on_the_configured_spelling(self):
        self.assertEqual(self.make('kAnNuR'), 'Kannur')

    def test_surrounding_space_does_not_defeat_the_match(self):
        self.assertEqual(self.make('  kannur '), 'Kannur')

    def test_blank_stays_blank(self):
        self.assertEqual(self.make(''), '')

    def test_editing_to_an_unconfigured_district_clears_it(self):
        lead = Lead.objects.create(first_name='D', phone='9895900002', district='Kannur')
        lead.district = 'Payyanur.kannur'
        lead.save()
        lead.refresh_from_db()
        self.assertEqual(lead.district, '')

    def test_a_retired_district_is_no_longer_accepted(self):
        """Inactive districts stop being offered, so they stop being filed."""
        self.District.objects.filter(name='Kannur').update(is_active=False)
        self.assertEqual(self.make('Kannur'), '')

    def test_saving_an_untouched_lead_leaves_its_district_alone(self):
        """A lead already filed under a district that was later retired keeps it
        — the model only re-checks a district that is being written."""
        lead = Lead.objects.create(first_name='D', phone='9895900003', district='Kannur')
        self.District.objects.filter(name='Kannur').update(is_active=False)
        lead.first_name = 'Renamed'
        lead.save()
        lead.refresh_from_db()
        self.assertEqual(lead.district, 'Kannur')

    # ── Through the API, which is the path that had no guard ──
    def test_the_api_cannot_file_an_unconfigured_district(self):
        r = self.client.post('/api/leads/',
                             data={'first_name': 'ApiLead', 'phone': '9895900004',
                                   'district': 'Payyanur.kannur'},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 201, r.content[:200])
        self.assertEqual(Lead.objects.get(pk=r.json()['id']).district, '')

    def test_the_api_keeps_a_configured_district(self):
        r = self.client.post('/api/leads/',
                             data={'first_name': 'ApiLead2', 'phone': '9895900005',
                                   'district': 'ernakulam'},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(Lead.objects.get(pk=r.json()['id']).district, 'Ernakulam')

    # ── Through Meta, which is where the reported lead came from ──
    def test_a_meta_lead_with_a_stray_district_is_filed_without_one(self):
        from .meta_integration import match_district
        self.assertEqual(match_district('Payyanur.kannur'), '')
        self.assertEqual(match_district('kannur'), 'Kannur')


class CustomerTrackingLinkTests(TestCase):
    """The link documentation hands the customer, and the page it opens.

    The token in the URL is the whole of the security, so these tests care about
    two things above all: that the page opens with no login, and that nothing
    internal travels with it.
    """

    def setUp(self):
        from django.core.cache import cache
        from .models import DocumentationStage1, TrackingLink
        cache.clear()  # see TrackingStagesTests.setUp — one shared anon budget
        self.TrackingLink = TrackingLink
        self.docstaff = mk('trk_doc', 'documentation_staff')
        self.bde = mk('trk_bde', 'bde')
        self.lead = Lead.objects.create(first_name='Meera', last_name='Nair',
                                        phone='9895700001', email='meera@example.com',
                                        value=Decimal('320000'), bde=self.bde)
        self.s1 = DocumentationStage1.objects.create(
            lead=self.lead, is_complete=True, completed_at=timezone.now())

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.docstaff)}

    def generate(self, user=None):
        return self.client.post(f'/api/leads/{self.lead.id}/tracking-link/',
                                data={}, content_type='application/json',
                                **self.auth(user))

    def track(self, token):
        """Fetched with no credentials at all — the customer has none."""
        return self.client.get(f'/api/track/{token}/')

    # ── Generating ──
    def test_documentation_can_generate_a_link(self):
        r = self.generate()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(r.json()['token'])

    def test_the_token_is_long_and_random(self):
        """It is the only thing protecting the page, so it must not be guessable."""
        a = self.generate().json()['token']
        self.TrackingLink.objects.all().delete()
        b = self.generate().json()['token']
        self.assertGreaterEqual(len(a), 32)
        self.assertNotEqual(a, b)

    def test_the_url_contains_the_token(self):
        d = self.generate().json()
        self.assertIn(d['token'], d['url'])
        self.assertIn('/track/', d['url'])

    def test_generating_twice_keeps_the_same_link(self):
        """The one already sitting in the customer's inbox has to keep working."""
        first = self.generate().json()['token']
        self.assertEqual(self.generate().json()['token'], first)

    def test_a_link_cannot_be_made_before_documentation_is_done(self):
        """Otherwise the customer opens a tracker with nothing on it."""
        self.s1.is_complete = False
        self.s1.save(update_fields=['is_complete'])
        r = self.generate()
        self.assertEqual(r.status_code, 400)
        self.assertIn('Documentation Stage 1', r.json()['error'])

    def test_a_bde_cannot_generate_one(self):
        self.assertEqual(self.generate(user=self.bde).status_code, 403)

    def test_a_spectator_cannot_generate_one(self):
        spectator = mk('trk_spec', 'spectator')
        self.assertEqual(self.generate(user=spectator).status_code, 403)

    def test_reading_it_says_so_when_there_is_none(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/tracking-link/', **self.auth())
        self.assertFalse(r.json()['exists'])

    # ── The customer's page: open to anyone holding the link ──
    def test_the_page_opens_with_no_login(self):
        token = self.generate().json()['token']
        r = self.track(token)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['customer'], 'Meera')

    def test_nothing_internal_travels_with_it(self):
        """Anyone holding the link sees this, so it must carry only what the
        customer would be told on the phone."""
        token = self.generate().json()['token']
        body = self.track(token).content.decode().lower()
        for secret in ('320000', 'trk_doc', 'trk_bde', '9895700001',
                       'meera@example.com', 'revenue', 'lead_id'):
            self.assertNotIn(secret.lower(), body, secret)

    def test_only_the_first_name_is_shown(self):
        token = self.generate().json()['token']
        self.assertNotIn('Nair', self.track(token).content.decode())

    def test_the_stages_are_named_for_the_customer(self):
        token = self.generate().json()['token']
        titles = [s['title'] for s in self.track(token).json()['stages']]
        self.assertEqual(titles[0], 'Documents verified')
        self.assertEqual(titles[-1], 'Warranty issued')
        self.assertIn('Installation complete', titles)

    def test_the_first_unfinished_stage_is_the_current_one(self):
        token = self.generate().json()['token']
        stages = self.track(token).json()['stages']
        current = [s for s in stages if s['current']]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]['key'], 'feasibility')

    def test_the_journey_only_runs_forwards(self):
        """A job installed while an earlier record is still open must not show
        the customer a finished step above an unfinished one."""
        from .models import Project
        Project.objects.create(lead=self.lead, is_complete=True,
                               completed_at=timezone.now())
        token = self.generate().json()['token']
        stages = self.track(token).json()['stages']
        spine = stages[:stages.index(next(s for s in stages if s['key'] == 'installation')) + 1]
        self.assertTrue(all(s['done'] for s in spine))
        materials = next(s for s in stages if s['key'] == 'materials')
        self.assertTrue(materials['inferred'])
        # An inferred step must not borrow a date it was never given.
        self.assertIsNone(materials['on'])

    def test_dates_are_shown_in_the_company_timezone(self):
        """Stamps are stored as UTC. A job finished at 2am IST falls on the
        previous UTC day, and the customer must not be shown a date a day behind
        the one they were told."""
        from datetime import datetime, timezone as dt_timezone
        from .models import Project
        # 20:30 UTC on the 8th is 02:00 IST on the 9th.
        Project.objects.create(
            lead=self.lead, is_complete=True,
            completed_at=datetime(2026, 9, 8, 20, 30, tzinfo=dt_timezone.utc))
        token = self.generate().json()['token']
        step = next(s for s in self.track(token).json()['stages']
                    if s['key'] == 'installation')
        self.assertEqual(step['on'], '2026-09-09')

    def test_opening_the_page_is_counted(self):
        """The only evidence the address was right and the mail arrived."""
        token = self.generate().json()['token']
        self.track(token)
        self.track(token)
        self.assertEqual(self.TrackingLink.objects.get(token=token).view_count, 2)

    # ── When it should not open ──
    def test_an_unknown_token_is_not_found(self):
        self.assertEqual(self.track('nothing-like-a-real-token').status_code, 404)

    def test_a_revoked_link_stops_working(self):
        token = self.generate().json()['token']
        self.TrackingLink.objects.filter(token=token).update(revoked=True)
        self.assertEqual(self.track(token).status_code, 404)

    def test_a_trashed_lead_takes_its_link_with_it(self):
        token = self.generate().json()['token']
        Lead.objects.filter(pk=self.lead.pk).update(is_trashed=True)
        self.assertEqual(self.track(token).status_code, 404)

    def test_a_link_expires_after_the_job_is_finished(self):
        """And says so, rather than 404-ing, because the customer can act on it."""
        from .models import Project, TrackingLink
        Project.objects.create(
            lead=self.lead, is_complete=True,
            completed_at=timezone.now() - timedelta(
                days=TrackingLink.LIVES_FOR_DAYS_AFTER_COMPLETION + 1))
        token = self.generate().json()['token']
        r = self.track(token)
        self.assertEqual(r.status_code, 410)
        self.assertEqual(r.json()['error'], 'expired')

    def test_a_link_does_not_expire_while_the_job_is_running(self):
        """A job taking eight months must not go dark halfway through."""
        token = self.generate().json()['token']
        link = self.TrackingLink.objects.get(token=token)
        self.assertIsNone(link.expires_at)
        self.assertTrue(link.is_live)

    # ── Revoking ──
    def test_a_link_can_be_switched_off_and_back_on(self):
        self.generate()
        off = self.client.post(f'/api/leads/{self.lead.id}/tracking-link/revoke/',
                               data={}, content_type='application/json', **self.auth())
        self.assertTrue(off.json()['revoked'])
        on = self.client.post(f'/api/leads/{self.lead.id}/tracking-link/revoke/',
                              data={}, content_type='application/json', **self.auth())
        self.assertFalse(on.json()['revoked'])

    # ── Emailing ──
    def test_generating_the_link_emails_it(self):
        """The point of making one is that the customer gets it. A link that
        only ever sat in the CRM helped nobody."""
        from django.core import mail
        r = self.generate()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(r.json()['sent'])
        self.assertEqual(r.json()['sent_to'], 'meera@example.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/track/', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['meera@example.com'])

    def test_generating_twice_does_not_email_twice(self):
        """The endpoint is idempotent, so a repeat call must not put a second
        copy in the customer's inbox."""
        from django.core import mail
        self.generate()
        again = self.generate()
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(again.json()['sent'])

    def test_a_customer_with_no_address_still_gets_a_working_link(self):
        """The link is what was asked for; the email is how it travels. A
        missing address must not cost the desk the link itself."""
        from django.core import mail
        Lead.objects.filter(pk=self.lead.pk).update(email='')
        r = self.generate()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(r.json()['token'])
        self.assertFalse(r.json()['sent'])
        self.assertIn('no email address', r.json()['send_error'])
        self.assertEqual(len(mail.outbox), 0)
        # And it opens, which is the part that matters.
        self.assertEqual(self.track(r.json()['token']).status_code, 200)

    def test_a_mail_server_failure_does_not_cost_the_link(self):
        from unittest import mock
        from django.core import mail
        with mock.patch('messaging.email.send_and_log') as send:
            send.return_value = mock.Mock(status='failed', error='SMTP refused')
            r = self.generate()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(r.json()['token'])
        self.assertFalse(r.json()['sent'])
        self.assertIn('SMTP refused', r.json()['send_error'])
        self.assertEqual(self.track(r.json()['token']).status_code, 200)

    def test_the_link_can_be_re_sent_by_hand(self):
        """For a corrected address, or a customer who lost the message."""
        from django.core import mail
        self.generate()
        r = self.client.post(f'/api/leads/{self.lead.id}/tracking-link/send/',
                             data={}, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(r.json()['sent'])
        self.assertEqual(len(mail.outbox), 2)      # the automatic one, then this
        self.assertEqual(mail.outbox[1].to, ['meera@example.com'])

    def test_sending_without_an_address_is_refused_clearly(self):
        Lead.objects.filter(pk=self.lead.pk).update(email='')
        self.generate()
        r = self.client.post(f'/api/leads/{self.lead.id}/tracking-link/send/',
                             data={}, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertIn('no email address', r.json()['error'])

    def test_sending_before_generating_is_refused(self):
        r = self.client.post(f'/api/leads/{self.lead.id}/tracking-link/send/',
                             data={}, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 400)



class TrackingStagesTests(TestCase):
    """Which steps the customer is shown, and when each one lights up.

    Two of them are conditional, and getting that wrong is not cosmetic: a
    subsidy row shown to a customer who will never get one, or a loan row on a
    job nobody borrowed for, is the company promising something in writing.
    """

    def setUp(self):
        from django.core.cache import cache
        from .models import DocumentationStage1, SiteVisit
        # The customer's page is anonymous, so every test in this file draws on
        # one shared anon throttle budget and a long class would start 429ing
        # tests that had done nothing wrong.
        cache.clear()
        self.docstaff = mk('stg_doc', 'documentation_staff')
        self.bde = mk('stg_bde', 'bde')
        self.lead = Lead.objects.create(
            first_name='Anil', last_name='Kumar', phone='9895700002',
            email='anil@example.com', value=Decimal('280000'), bde=self.bde,
            pushed_to_documentation=True, documentation_staff=self.docstaff)
        self.sv = SiteVisit.objects.create(lead=self.lead, loan='no')
        self.s1 = DocumentationStage1.objects.create(
            lead=self.lead, is_complete=True, completed_at=timezone.now())

    # ── helpers ──
    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.docstaff)}

    def stages(self):
        r = self.client.post(f'/api/leads/{self.lead.id}/tracking-link/',
                             data={}, content_type='application/json', **self.auth())
        token = r.json()['token']
        return self.client.get(f'/api/track/{token}/').json()['stages']

    def keys(self):
        return [s['key'] for s in self.stages()]

    def step(self, key):
        return next((s for s in self.stages() if s['key'] == key), None)

    def with_loan(self):
        self.sv.loan = 'yes'
        self.sv.save(update_fields=['loan'])

    def sanction(self, user=None, sanctioned=True):
        return self.client.post(f'/api/leads/{self.lead.id}/loan-sanctioned/',
                                data={'sanctioned': sanctioned},
                                content_type='application/json', **self.auth(user))

    def stage2(self, **kw):
        """Put the lead into Stage 2, which is what makes its record writable."""
        from .models import DocumentationStage2
        Lead.objects.filter(pk=self.lead.pk).update(
            pushed_to_doc_stage2=True, doc_stage2_staff=self.docstaff)
        self.lead.refresh_from_db()
        return DocumentationStage2.objects.create(lead=self.lead, **kw)

    def claim_subsidy(self, requested=True):
        return self.client.patch(
            f'/api/leads/{self.lead.id}/documentation-stage2-record/',
            data={'subsidy_requested': requested},
            content_type='application/json', **self.auth())

    def approve_discom(self, answer='yes'):
        """Through Documentation Stage 2's own endpoint, which is where the
        approval is recorded and where its date is stamped."""
        Lead.objects.filter(pk=self.lead.pk).update(
            pushed_to_doc_stage2=True, doc_stage2_staff=self.docstaff)
        self.lead.refresh_from_db()
        r = self.client.patch(
            f'/api/leads/{self.lead.id}/documentation-stage2-record/',
            data={'discom_approval': answer}, content_type='application/json',
            **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r

    def officer(self):
        """The liasoning officer, with the lead sitting in their module."""
        from .models import LiasoningService
        user = (User.objects.filter(username='stg_lia').first()
                or mk('stg_lia', 'liasoning_officer'))
        Lead.objects.filter(pk=self.lead.pk).update(
            pushed_to_liasoning=True, pushed_to_liasoning_at=timezone.now())
        LiasoningService.objects.get_or_create(lead=self.lead)
        return user

    def upload_photo(self, slot):
        r = self.client.post(
            f'/api/leads/{self.lead.id}/liasoning/documents/',
            data={'file': SimpleUploadedFile('photo.jpg', b'jpeg bytes',
                                             content_type='image/jpeg'),
                  'doc_type': slot},
            HTTP_AUTHORIZATION=token_for(self.officer()))
        self.assertEqual(r.status_code, 201, r.content[:200])
        return r

    def upload_rf(self):
        """Through the officer's own endpoint, since it is the upload itself —
        not a second tick beside it — that registers the customer."""
        from .models import LiasoningService
        return self.upload_photo(LiasoningService.RF_IMAGE)

    def sign_off_liasoning(self):
        """What the Completed tick does on the liasoning list: it saves the
        Annexure 3 flag, then signs the record off — which the server allows
        only once both photos are in."""
        from .models import LiasoningService
        self.upload_photo(LiasoningService.PLANT_PHOTO)
        self.upload_photo(LiasoningService.RF_IMAGE)
        r = self.client.patch(
            f'/api/leads/{self.lead.id}/liasoning-record/',
            data={'annexure3_completed': True}, content_type='application/json',
            HTTP_AUTHORIZATION=token_for(self.officer()))
        self.assertEqual(r.status_code, 200, r.content[:200])
        r = self.client.post(f'/api/leads/{self.lead.id}/complete-liasoning/',
                             HTTP_AUTHORIZATION=token_for(self.officer()))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r

    # ── What replaced the approvals step ──
    def test_the_approvals_step_is_gone(self):
        self.assertNotIn('approvals', self.keys())

    def test_a_customer_without_a_loan_is_not_shown_a_loan_step(self):
        self.assertNotIn('loan', self.keys())

    def test_a_customer_with_a_loan_is_shown_one(self):
        self.with_loan()
        self.assertIn('loan', self.keys())

    def test_the_loan_step_sits_between_feasibility_and_materials(self):
        """Because the money has to be there before anything is bought."""
        self.with_loan()
        keys = self.keys()
        self.assertLess(keys.index('feasibility'), keys.index('loan'))
        self.assertLess(keys.index('loan'), keys.index('materials'))

    def test_the_loan_step_lights_up_when_the_bank_says_yes(self):
        self.with_loan()
        self.assertFalse(self.step('loan')['done'])
        self.sanction()
        step = self.step('loan')
        self.assertTrue(step['done'])
        self.assertEqual(step['on'], timezone.localdate().isoformat())

    # ── Recording the bank's decision ──
    def test_the_decision_can_be_recorded_after_stage_1_is_locked(self):
        """The whole reason it has its own endpoint: the sanction letter arrives
        after documentation has signed off, and a PATCH would be refused."""
        self.with_loan()
        self.assertTrue(self.s1.is_complete)
        locked = self.client.patch(
            f'/api/leads/{self.lead.id}/documentation-stage1/',
            data={'loan_sanctioned': True}, content_type='application/json', **self.auth())
        self.assertEqual(locked.status_code, 400)             # the stage is shut
        self.assertEqual(self.sanction().status_code, 200)    # this still works
        self.s1.refresh_from_db()
        self.assertTrue(self.s1.loan_sanctioned)

    def test_it_can_be_undone_and_takes_its_date_with_it(self):
        """A wrong date on the customer's page is worse than no date."""
        self.with_loan()
        self.sanction()
        self.sanction(sanctioned=False)
        self.s1.refresh_from_db()
        self.assertFalse(self.s1.loan_sanctioned)
        self.assertIsNone(self.s1.loan_sanctioned_at)

    def test_a_job_with_no_loan_cannot_be_marked_sanctioned(self):
        r = self.sanction()
        self.assertEqual(r.status_code, 400)
        self.assertIn('not taking a loan', r.json()['error'])

    def test_a_bde_cannot_record_the_bank_decision(self):
        self.with_loan()
        self.assertEqual(self.sanction(user=self.bde).status_code, 403)

    def test_a_spectator_cannot_record_it(self):
        self.with_loan()
        self.assertEqual(self.sanction(user=mk('stg_spec', 'spectator')).status_code, 403)

    # ── KSEB approval ──
    def test_the_approval_comes_straight_after_commissioning(self):
        keys = self.keys()
        self.assertEqual(keys[keys.index('commissioning') + 1], 'discom_approval')

    def test_every_customer_sees_the_approval_step(self):
        """Unlike the subsidy below it, which only appears once the answer is
        yes, the approval itself is a step every customer waits on."""
        self.assertIn('discom_approval', self.keys())

    def test_approving_the_discom_ticks_it(self):
        step = self.step('discom_approval')
        self.assertFalse(step['done'])
        self.assertIsNone(step['on'])
        self.approve_discom()
        step = self.step('discom_approval')
        self.assertTrue(step['done'])
        self.assertEqual(step['on'], timezone.localdate().isoformat())

    def test_a_refusal_is_not_an_approval(self):
        self.approve_discom('no')
        step = self.step('discom_approval')
        self.assertFalse(step['done'])
        self.assertIsNone(step['on'])

    def test_a_reversed_approval_unticks_and_drops_its_date(self):
        """Otherwise a customer keeps a tick, and a date, for an approval the
        board has taken back."""
        from .models import DocumentationStage2
        self.approve_discom()
        self.approve_discom('pending')
        step = self.step('discom_approval')
        self.assertFalse(step['done'])
        self.assertIsNone(step['on'])
        self.assertIsNone(DocumentationStage2.objects.get(lead=self.lead).discom_approval_at)

    def test_the_approval_blurb_claims_nothing_that_has_not_happened(self):
        blurb = self.step('discom_approval')['blurb'].lower()
        self.assertIn('board', blurb)
        for wrong in ('has approved', 'has been', 'approved your'):
            self.assertNotIn(wrong, blurb)

    # ── Subsidy ──
    def test_the_subsidy_is_claimed_after_the_warranty_is_issued(self):
        """The claim goes in last, so it reads in the order the office works."""
        self.stage2(discom_approval='yes')
        keys = self.keys()
        self.assertEqual(keys[-1], 'subsidy')
        self.assertLess(keys.index('warranty'), keys.index('subsidy'))

    def test_no_subsidy_step_before_the_discom_has_decided(self):
        """A maybe is not shown: a step that later vanishes reads as a promise
        withdrawn."""
        self.stage2(discom_approval='pending')
        self.assertNotIn('subsidy', self.keys())

    def test_no_subsidy_step_when_the_discom_said_no(self):
        self.stage2(discom_approval='no')
        self.assertNotIn('subsidy', self.keys())

    def test_the_subsidy_step_appears_once_the_discom_approves(self):
        self.stage2(discom_approval='yes')
        step = self.step('subsidy')
        self.assertIsNotNone(step)
        self.assertFalse(step['done'])

    def test_the_subsidy_step_lights_up_when_the_claim_is_filed(self):
        s2 = self.stage2(discom_approval='yes')
        r = self.claim_subsidy()
        self.assertEqual(r.status_code, 200, r.content[:300])
        s2.refresh_from_db()
        self.assertIsNotNone(s2.subsidy_requested_at)
        step = self.step('subsidy')
        self.assertTrue(step['done'])
        self.assertEqual(step['on'], timezone.localdate().isoformat())

    def test_a_late_claim_can_still_be_filed_on_a_signed_off_stage_2(self):
        """KSEB approves on its own schedule, often after Stage 2 is locked. The
        claim that follows has to get through too, or the customer's subsidy step
        could never light up."""
        s2 = self.stage2(discom_approval='yes', is_complete=True,
                         completed_at=timezone.now())
        self.assertEqual(self.claim_subsidy().status_code, 200)
        s2.refresh_from_db()
        self.assertTrue(s2.subsidy_requested)
        self.assertTrue(self.step('subsidy')['done'])

    def test_the_lock_still_holds_for_everything_else(self):
        self.stage2(discom_approval='yes', is_complete=True, completed_at=timezone.now())
        r = self.client.patch(
            f'/api/leads/{self.lead.id}/documentation-stage2-record/',
            data={'mnre_remark': 'slipped in'}, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 400)

    def test_the_subsidy_step_never_reads_as_money_received(self):
        """Claiming a subsidy and being paid one are months apart. The row must
        not blur them, and must read true while it is still pending."""
        self.stage2(discom_approval='yes')
        pending = self.step('subsidy')
        self.assertFalse(pending['done'])
        blurb = pending['blurb'].lower()
        self.assertIn('subsidy', blurb)
        # Nothing in the past tense on a step that has not happened, and no
        # suggestion the money itself has arrived.
        for wrong in ('has been', 'credited', 'paid', 'received', '₹'):
            self.assertNotIn(wrong, blurb)

    # ── KSEB registration ──
    def test_registration_comes_straight_after_the_installation(self):
        keys = self.keys()
        self.assertEqual(keys[keys.index('installation') + 1], 'kseb_registration')

    def test_every_customer_sees_the_registration_step(self):
        """Unlike the loan and the subsidy, it happens to everyone."""
        self.assertIn('kseb_registration', self.keys())

    def test_the_rf_image_is_what_ticks_it(self):
        step = self.step('kseb_registration')
        self.assertFalse(step['done'])
        self.assertIsNone(step['on'])
        self.upload_rf()
        step = self.step('kseb_registration')
        self.assertTrue(step['done'])
        # localdate, not now().date(): the tracker reports dates in the
        # company's timezone, so comparing against the UTC date fails for the
        # five and a half hours after midnight IST — which is exactly when a
        # long suite run reaches this.
        self.assertEqual(step['on'], timezone.localdate().isoformat())

    def test_the_plant_photo_alone_does_not_tick_it(self):
        """The two slots mean different things; only the RF image is the
        registration."""
        from .models import LiasoningDocument, LiasoningService
        rec, _ = LiasoningService.objects.get_or_create(lead=self.lead)
        LiasoningDocument.objects.create(
            liasoning=rec, doc_type=LiasoningService.PLANT_PHOTO,
            file=SimpleUploadedFile('plant.jpg', b'jpeg bytes',
                                    content_type='image/jpeg'))
        self.assertFalse(self.step('kseb_registration')['done'])

    def test_registration_does_not_imply_the_installation_is_finished(self):
        """A liasoning record can be opened before the project is signed off, so
        an RF image is no evidence the system is up. Saying otherwise would tell
        a customer their installation is complete when it is not."""
        self.upload_rf()
        installation = self.step('installation')
        self.assertFalse(installation['done'])
        self.assertFalse(installation['inferred'])

    def test_a_warranty_does_not_imply_the_registration(self):
        from .models import Project, Warranty
        Project.objects.create(lead=self.lead, is_complete=True, completed_at=timezone.now())
        Warranty.objects.create(lead=self.lead, is_complete=True, completed_at=timezone.now())
        step = self.step('kseb_registration')
        self.assertFalse(step['done'])
        self.assertFalse(step['inferred'])

    def test_the_registration_step_names_both_halves_of_the_job(self):
        """One row covers the registration and the completion filing, so both
        have to be named on it."""
        step = self.step('kseb_registration')
        self.assertEqual(step['title'], 'KSEB registration and completion')
        self.assertIn('register', step['blurb'].lower())
        self.assertIn('completion documents', step['blurb'].lower())

    def test_the_registration_blurb_claims_nothing_that_has_not_happened(self):
        blurb = self.step('kseb_registration')['blurb'].lower()
        self.assertIn('kseb', blurb)
        for wrong in ('has been', 'registered with kseb.', 'approved'):
            self.assertNotIn(wrong, blurb)

    # ── Commissioning ──
    def test_commissioning_comes_straight_after_the_registration(self):
        keys = self.keys()
        self.assertEqual(keys[keys.index('kseb_registration') + 1], 'commissioning')

    def test_every_customer_sees_the_commissioning_step(self):
        self.assertIn('commissioning', self.keys())

    def test_the_completed_tick_is_what_ticks_it(self):
        step = self.step('commissioning')
        self.assertFalse(step['done'])
        self.assertIsNone(step['on'])
        self.sign_off_liasoning()
        step = self.step('commissioning')
        self.assertTrue(step['done'])
        # localdate, not now().date(): the tracker reports dates in the
        # company's timezone, so comparing against the UTC date fails for the
        # five and a half hours after midnight IST — which is exactly when a
        # long suite run reaches this.
        self.assertEqual(step['on'], timezone.localdate().isoformat())

    def test_the_photos_alone_do_not_commission_the_system(self):
        """They are what the tick waits on, not the tick itself."""
        from .models import LiasoningService
        self.upload_photo(LiasoningService.PLANT_PHOTO)
        self.upload_photo(LiasoningService.RF_IMAGE)
        self.assertFalse(self.step('commissioning')['done'])
        # The registration, which is the picture on its own, is done by now.
        self.assertTrue(self.step('kseb_registration')['done'])

    def test_a_row_ticked_before_the_photo_rule_still_counts(self):
        """Those rows carry the tick without the sign-off behind it. The office
        says the completion doc went in, so the customer is told so — with no
        date, since none was ever stamped."""
        from .models import LiasoningService
        self.officer()
        LiasoningService.objects.filter(lead=self.lead).update(annexure3_completed=True)
        step = self.step('commissioning')
        self.assertTrue(step['done'])
        self.assertIsNone(step['on'])

    def test_commissioning_does_not_imply_the_installation_is_finished(self):
        self.sign_off_liasoning()
        installation = self.step('installation')
        self.assertFalse(installation['done'])
        self.assertFalse(installation['inferred'])

    def test_the_commissioning_row_announces_the_plant_is_running(self):
        """This row is deliberately written as the finished state, the way
        'Installation complete' is — it is the moment the customer is waiting
        for, and the row is greyed out until it arrives. The paperwork that
        gets there is described on the registration row, not repeated here."""
        blurb = self.step('commissioning')['blurb'].lower()
        self.assertIn('generating', blurb)
        self.assertNotIn('completion documents', blurb)

    # ── Warranty ──
    def test_the_warranty_is_always_shown_and_ends_a_journey_with_no_subsidy(self):
        self.assertIn('warranty', self.keys())
        self.assertEqual(self.keys()[-1], 'warranty')

    def test_the_warranty_step_lights_up_when_it_is_issued(self):
        from .models import Warranty
        self.assertFalse(self.step('warranty')['done'])
        Warranty.objects.create(lead=self.lead, is_complete=True,
                                completed_at=timezone.now())
        self.assertTrue(self.step('warranty')['done'])

    def test_a_warranty_does_not_imply_the_subsidy_was_claimed(self):
        """The two run side by side, so neither is evidence of the other. The
        forwards-only rule must not tell a customer their claim went in."""
        from .models import Project, Warranty
        self.stage2(discom_approval='yes', subsidy_requested=False)
        Project.objects.create(lead=self.lead, is_complete=True, completed_at=timezone.now())
        Warranty.objects.create(lead=self.lead, is_complete=True, completed_at=timezone.now())
        subsidy = self.step('subsidy')
        self.assertFalse(subsidy['done'])
        self.assertFalse(subsidy['inferred'])
        self.assertTrue(self.step('warranty')['done'])

    def test_the_job_is_only_finished_when_every_step_is(self):
        from .models import Project, Warranty
        Project.objects.create(lead=self.lead, is_complete=True, completed_at=timezone.now())
        r = self.client.post(f'/api/leads/{self.lead.id}/tracking-link/',
                             data={}, content_type='application/json', **self.auth())
        token = r.json()['token']
        self.assertFalse(self.client.get(f'/api/track/{token}/').json()['complete'])
        Warranty.objects.create(lead=self.lead, is_complete=True, completed_at=timezone.now())
        # Registration, commissioning and the board's approval are steps now, so
        # a warranty no longer finishes the journey on its own.
        done = lambda: self.client.get(f'/api/track/{token}/').json()['complete']
        self.assertFalse(done())
        self.sign_off_liasoning()
        self.assertFalse(done())
        # Approving brings the subsidy row with it, so the journey grows a step
        # at the same moment it finishes one.
        self.approve_discom()
        self.assertFalse(done())
        self.claim_subsidy()
        self.assertTrue(done())

    # ── The link has to outlive the steps that come after the installation ──
    def test_the_link_stays_open_until_the_last_step_is_done(self):
        """Timed from the installation it could shut while the warranty was still
        outstanding, losing the customer the record they most want."""
        from .models import Project, TrackingLink, Warranty
        days = TrackingLink.LIVES_FOR_DAYS_AFTER_COMPLETION
        Project.objects.create(lead=self.lead, is_complete=True,
                               completed_at=timezone.now() - timedelta(days=days + 5))
        Warranty.objects.create(lead=self.lead, is_complete=True,
                                completed_at=timezone.now() - timedelta(days=2))
        self.client.post(f'/api/leads/{self.lead.id}/tracking-link/',
                         data={}, content_type='application/json', **self.auth())
        self.assertTrue(TrackingLink.objects.get(lead=self.lead).is_live)


class MetaImportDeduplicationTests(TestCase):
    """A customer who submits the form twice is one lead, not two.

    Meta issues a fresh lead id for every submission, so matching on that alone
    only catches the same *submission* arriving twice. Someone who fills the
    form on Monday and again on Thursday is two ids and one person, and that is
    where the lead book filled up with copies.

    The lead already on the books is the one kept: it carries the calls, the
    notes and the owner it was assigned to, and the arriving copy carries none
    of that.
    """

    def payload(self, meta_id, phone_number='', email='', name='Anil Kumar'):
        """A Meta payload shaped the way Meta sends one.

        The contact details live in `field_data`, not at the top level — a
        top-level `phone_number` is never read, so a payload built that way
        would test nothing.
        """
        fields = [{'name': 'full_name', 'values': [name]}]
        if phone_number:
            fields.append({'name': 'phone_number', 'values': [phone_number]})
        if email:
            fields.append({'name': 'email', 'values': [email]})
        return {'id': meta_id, 'created_time': '2026-09-01T10:00:00+0000',
                'field_data': fields}

    def test_the_same_customer_twice_is_filed_once(self):
        first, dup = create_lead_from_meta_payload(
            self.payload('1001', phone_number='+919895700001'))
        self.assertFalse(dup)
        second, dup = create_lead_from_meta_payload(
            self.payload('1002', phone_number='+919895700001'))
        self.assertIsNone(second)
        self.assertTrue(dup)
        self.assertEqual(Lead.objects.filter(phone__contains='9895700001').count(), 1)

    def test_the_lead_that_was_there_first_is_the_one_kept(self):
        """It holds the work; the copy holds nothing."""
        first, _ = create_lead_from_meta_payload(
            self.payload('2001', phone_number='9895700002'))
        first.notes = 'Called; wants a site visit on Friday.'
        first.save(update_fields=['notes'])

        create_lead_from_meta_payload(self.payload('2002', phone_number='9895700002'))
        first.refresh_from_db()
        self.assertEqual(Lead.objects.filter(phone__contains='9895700002').count(), 1)
        self.assertIn('site visit', first.notes)
        self.assertEqual(first.meta_lead_id, '2001')       # still the first one

    def test_a_different_way_of_writing_the_number_is_still_the_same_customer(self):
        """+91 on one and not the other is how the copies got in."""
        create_lead_from_meta_payload(self.payload('3001', phone_number='+917902817610'))
        lead, dup = create_lead_from_meta_payload(
            self.payload('3002', phone_number='7902817610'))
        self.assertIsNone(lead)
        self.assertTrue(dup)

    def test_the_email_catches_it_when_the_number_differs(self):
        create_lead_from_meta_payload(
            self.payload('4001', phone_number='9895700003', email='same@example.com'))
        lead, dup = create_lead_from_meta_payload(
            self.payload('4002', phone_number='9895700004', email='SAME@example.com'))
        self.assertIsNone(lead)
        self.assertTrue(dup)

    def test_a_different_customer_still_gets_in(self):
        """The rule must not swallow real leads."""
        create_lead_from_meta_payload(self.payload('5001', phone_number='9895700005'))
        lead, dup = create_lead_from_meta_payload(
            self.payload('5002', phone_number='9895700006'))
        self.assertFalse(dup)
        self.assertIsNotNone(lead)

    def test_the_skip_is_written_on_the_lead_that_was_kept(self):
        """So the desk can see the customer asked twice, which is worth knowing."""
        first, _ = create_lead_from_meta_payload(
            self.payload('6001', phone_number='9895700007'))
        create_lead_from_meta_payload(self.payload('6002', phone_number='9895700007'))
        from .models import ActivityLog
        note = ActivityLog.objects.filter(
            lead=first, extra__duplicate_skipped=True).first()
        self.assertIsNotNone(note)
        self.assertIn('again', note.description)

    def test_a_trashed_lead_does_not_block_the_customer_coming_back(self):
        """`live_leads` is what is matched against, so a customer whose old lead
        was thrown away can be filed afresh."""
        first, _ = create_lead_from_meta_payload(
            self.payload('7001', phone_number='9895700008'))
        Lead.objects.filter(pk=first.pk).update(is_trashed=True)
        lead, dup = create_lead_from_meta_payload(
            self.payload('7002', phone_number='9895700008'))
        self.assertFalse(dup)
        self.assertIsNotNone(lead)


class DocumentationRemarkTests(TestCase):
    """Remarks on a customer's documentation — why it is held up.

    Each stage keeps its own dated log; the lists show the latest one. Who can
    see and add them is whoever can open that stage for that customer, and
    changing one follows the lead-notes rule: your own, or an admin's override.
    """

    def setUp(self):
        self.admin = mk('dr_admin', 'admin')
        self.manager = mk('dr_manager', 'documentation_manager')
        self.staff1 = mk('dr_staff1', 'documentation_staff')   # has Stage 1
        self.staff2 = mk('dr_staff2', 'documentation_staff')   # has Stage 2
        self.bde = mk('dr_bde', 'bde')
        self.spectator = mk('dr_spectator', 'spectator')
        self.lead = Lead.objects.create(
            first_name='Sreeja', last_name='Menon', phone='9847012345', status='converted',
            bde=self.bde,
            pushed_to_documentation=True, pushed_to_documentation_at=timezone.now(),
            documentation_staff=self.staff1,
            pushed_to_doc_stage2=True, pushed_to_doc_stage2_at=timezone.now(),
            doc_stage2_staff=self.staff2)

    def url(self, lead=None, suffix=''):
        return f'/api/leads/{(lead or self.lead).id}/documentation-remarks/{suffix}'

    def add(self, user, body, stage='stage1', lead=None):
        return self.client.post(self.url(lead), data={'stage': stage, 'body': body},
                                content_type='application/json', HTTP_AUTHORIZATION=token_for(user))

    def read(self, user, stage='stage1', lead=None):
        return self.client.get(self.url(lead) + f'?stage={stage}', HTTP_AUTHORIZATION=token_for(user))

    def patch(self, user, remark_id, body):
        return self.client.patch(self.url(suffix=f'{remark_id}/'), data={'body': body},
                                 content_type='application/json', HTTP_AUTHORIZATION=token_for(user))

    def delete(self, user, remark_id):
        return self.client.delete(self.url(suffix=f'{remark_id}/'), HTTP_AUTHORIZATION=token_for(user))

    # ── Adding and reading ──
    def test_the_assigned_staff_can_note_why_it_is_held_up(self):
        r = self.add(self.staff1, "  Waiting for the customer's Aadhaar  ")
        self.assertEqual(r.status_code, 201, r.content[:200])
        body = r.json()
        self.assertEqual(body['body'], "Waiting for the customer's Aadhaar")
        self.assertEqual(body['author'], self.staff1.id)
        self.assertTrue(body['can_edit'])

    def test_the_latest_remark_comes_first(self):
        self.add(self.staff1, 'Waiting for the Aadhaar')
        self.add(self.staff1, 'Aadhaar in, waiting on the bank')
        rows = self.read(self.staff1).json()['remarks']
        self.assertEqual([r['body'] for r in rows],
                         ['Aadhaar in, waiting on the bank', 'Waiting for the Aadhaar'])

    def test_the_two_stages_keep_separate_logs(self):
        self.add(self.staff1, 'Stage 1 reason', stage='stage1')
        self.add(self.staff2, 'Stage 2 reason', stage='stage2')
        self.assertEqual([r['body'] for r in self.read(self.admin, 'stage1').json()['remarks']],
                         ['Stage 1 reason'])
        self.assertEqual([r['body'] for r in self.read(self.admin, 'stage2').json()['remarks']],
                         ['Stage 2 reason'])

    def test_a_completed_stage_still_takes_remarks(self):
        """A remark is a note, not stage data — the lock protects the paperwork."""
        from .models import DocumentationStage1
        DocumentationStage1.objects.create(lead=self.lead, is_complete=True)
        DocumentationStage2.objects.create(lead=self.lead, is_complete=True)
        self.assertEqual(self.add(self.staff1, 'Signed off; bank copy still to file').status_code, 201)
        self.assertEqual(self.add(self.staff2, 'Subsidy portal down', stage='stage2').status_code, 201)

    def test_adding_a_remark_is_on_the_timeline(self):
        from .models import ActivityLog
        self.add(self.staff1, 'Waiting for the Aadhaar')
        self.assertTrue(ActivityLog.objects.filter(
            lead=self.lead, description='Documentation Stage 1 remark: Waiting for the Aadhaar').exists())

    # ── Refusals ──
    def test_an_empty_remark_is_refused(self):
        self.assertEqual(self.add(self.staff1, '   ').status_code, 400)

    def test_a_runaway_remark_is_refused(self):
        self.assertEqual(self.add(self.staff1, 'x' * 2001).status_code, 400)

    def test_an_unknown_stage_is_refused(self):
        self.assertEqual(self.add(self.staff1, 'Hello', stage='stage3').status_code, 400)
        self.assertEqual(self.read(self.staff1, stage='').status_code, 400)

    # ── Who ──
    def test_staff_see_only_the_customers_assigned_to_them(self):
        """staff2 has this customer's Stage 2, not its Stage 1 — and the other
        way round for staff1."""
        self.assertEqual(self.read(self.staff2, 'stage1').status_code, 403)
        self.assertEqual(self.add(self.staff2, 'Not mine', 'stage1').status_code, 403)
        self.assertEqual(self.add(self.staff1, 'Not mine', 'stage2').status_code, 403)
        self.assertEqual(self.add(self.staff2, 'Mine', 'stage2').status_code, 201)

    def test_managers_and_admins_can_add_on_any_customer(self):
        self.assertEqual(self.add(self.manager, 'Chased the customer').status_code, 201)
        self.assertEqual(self.add(self.admin, 'Escalated', 'stage2').status_code, 201)

    def test_outside_documentation_there_is_no_access(self):
        self.assertEqual(self.read(self.bde).status_code, 403)
        self.assertEqual(self.add(self.bde, 'Hello').status_code, 403)

    def test_a_view_only_account_reads_but_cannot_add(self):
        r = self.read(self.spectator)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['can_add'])
        self.assertEqual(self.add(self.spectator, 'Watching').status_code, 403)
        self.assertTrue(self.read(self.staff1).json()['can_add'])

    def test_a_customer_not_yet_in_the_stage_has_no_remarks_to_take(self):
        early = Lead.objects.create(first_name='Early', phone='9847000001', status='converted',
                                    pushed_to_documentation=True, documentation_staff=self.staff1)
        self.assertEqual(self.add(self.admin, 'Too soon', 'stage2', lead=early).status_code, 404)
        self.assertEqual(self.add(self.admin, 'Fine', 'stage1', lead=early).status_code, 201)

    # ── Changing a remark ──
    def test_the_author_can_correct_their_remark(self):
        rid = self.add(self.staff1, 'Waiting for the Aadhar').json()['id']
        r = self.patch(self.staff1, rid, 'Waiting for the Aadhaar')
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['body'], 'Waiting for the Aadhaar')
        self.assertIsNotNone(r.json()['edited_at'])

    def test_a_colleague_cannot_rewrite_it(self):
        """The reason stays in the words of the person who gave it: the staff
        member working the customer can read the manager's remark, not change
        it."""
        rid = self.add(self.manager, 'Customer asked us to hold until October').json()['id']
        self.assertEqual(self.patch(self.staff1, rid, 'Something else').status_code, 403)
        self.assertEqual(self.delete(self.staff1, rid).status_code, 403)
        self.assertFalse(self.read(self.staff1).json()['remarks'][0]['can_edit'])

    def test_the_documentation_manager_can_correct_the_team(self):
        """The manager carries the general-manager flag, which is the admin
        tier for anything written in someone's name — the same as lead notes."""
        rid = self.add(self.staff1, 'Waiting for the Aadhar').json()['id']
        self.assertEqual(self.patch(self.manager, rid, 'Waiting for the Aadhaar').status_code, 200)
        self.assertEqual(self.delete(self.manager, rid).status_code, 204)

    def test_an_admin_can_remove_any_remark(self):
        from .models import DocumentationRemark
        rid = self.add(self.staff1, 'Should not have been written').json()['id']
        self.assertEqual(self.delete(self.admin, rid).status_code, 204)
        self.assertFalse(DocumentationRemark.objects.filter(pk=rid).exists())

    def test_a_remark_cannot_be_emptied(self):
        rid = self.add(self.staff1, 'Waiting').json()['id']
        self.assertEqual(self.patch(self.staff1, rid, '  ').status_code, 400)

    def test_a_remark_is_reached_only_through_its_own_customer(self):
        other = Lead.objects.create(first_name='Other', phone='9847000002', status='converted',
                                    pushed_to_documentation=True, documentation_staff=self.staff1)
        rid = self.add(self.staff1, 'On the other customer', lead=other).json()['id']
        self.assertEqual(self.patch(self.staff1, rid, 'Moved').status_code, 404)

    def test_losing_the_assignment_loses_the_remark(self):
        """Reassigned away from the customer, the author can no longer reach
        what they wrote on it — the stage's door, not authorship, comes first."""
        rid = self.add(self.staff1, 'Waiting').json()['id']
        Lead.objects.filter(pk=self.lead.pk).update(documentation_staff=self.staff2)
        self.assertEqual(self.patch(self.staff1, rid, 'Still waiting').status_code, 403)

    # ── What the lists show ──
    def test_the_stage1_list_shows_the_latest_remark(self):
        self.add(self.staff1, 'Waiting for the Aadhaar')
        self.add(self.staff1, 'Waiting on the bank')
        rows = self.client.get('/api/leads/documentation/',
                               HTTP_AUTHORIZATION=token_for(self.admin)).json()
        row = next(r for r in rows if r['id'] == self.lead.id)
        self.assertEqual(row['latest_remark']['body'], 'Waiting on the bank')
        self.assertEqual(row['latest_remark']['author_name'], 'dr_staff1')
        self.assertEqual(row['remark_count'], 2)

    def test_the_stage2_list_shows_its_own_latest_remark(self):
        self.add(self.staff1, 'A stage 1 remark')
        rows = self.client.get('/api/leads/documentation-stage2/',
                               HTTP_AUTHORIZATION=token_for(self.admin)).json()
        row = next(r for r in rows if r['id'] == self.lead.id)
        self.assertIsNone(row['latest_remark'])
        self.assertEqual(row['remark_count'], 0)
        self.add(self.staff2, 'Portal down', 'stage2')
        rows = self.client.get('/api/leads/documentation-stage2/',
                               HTTP_AUTHORIZATION=token_for(self.admin)).json()
        row = next(r for r in rows if r['id'] == self.lead.id)
        self.assertEqual(row['latest_remark']['body'], 'Portal down')

    def test_the_detail_pages_carry_the_summary_too(self):
        self.add(self.staff2, 'Portal down', 'stage2')
        r = self.client.get(f'/api/leads/{self.lead.id}/documentation-stage2-detail/',
                            HTTP_AUTHORIZATION=token_for(self.staff2))
        self.assertEqual(r.json()['latest_remark']['body'], 'Portal down')
