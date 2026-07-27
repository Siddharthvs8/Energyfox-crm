"""Lead-status ownership and the site-visit indicator the Leads list renders."""
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
