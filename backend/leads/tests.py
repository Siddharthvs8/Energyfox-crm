"""Lead-status ownership and the site-visit indicator the Leads list renders."""
from decimal import Decimal

from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from .models import Lead, SiteVisit


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

    def test_bde_keeps_every_other_edit(self):
        """The edit form posts the current status back; that must still save."""
        r = self.patch_lead(self.bde, {'status': 'new', 'notes': 'Visit booked'})
        self.assertEqual(r.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.notes, 'Visit booked')

        r = self.post('/api/leads/bulk_update/', self.bde,
                      {'ids': [self.lead.id], 'data': {'source': 'referral'}})
        self.assertEqual(r.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.source, 'referral')

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

    def test_bde_editing_a_lead_does_not_trip_the_assign_guard(self):
        """The edit form posts assigned_to back unchanged — that must still save."""
        r = self.patch_lead(self.bde, {'assigned_to': self.caller.id, 'notes': 'Reached site'})
        self.assertEqual(r.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.notes, 'Reached site')

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
        'documentation_staff': ['documentation', 'documentation-stage2', 'discom-followup', 'warranty'],
        'documentation_manager': ['documentation', 'documentation-stage2', 'discom-followup', 'warranty'],
        'accounts_staff': ['accounts', 'accounts/partially-paid', 'accounts/fully-paid', 'accounts/completed'],
        'purchase_staff': ['purchase'],
        'project_manager': ['project'],
        'liasoning_officer': ['liasoning', 'periodic-maintenance'],
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
        body = self.counts(mk('s_doc', 'documentation_staff'))
        for module in ('warranty', 'discom-followup'):
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

    def test_an_existing_bde_is_not_overwritten(self):
        """The dedicated hand-off stays authoritative over the owner field."""
        self.client.post(f'/api/leads/{self.lead.id}/assign-bde/', data={'bde': self.bde2.id},
                         content_type='application/json', HTTP_AUTHORIZATION=token_for(self.caller))
        self.patch(self.caller, {'assigned_to': self.bde.id})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.bde_id, self.bde2.id)
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

