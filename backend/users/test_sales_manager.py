"""The sales manager's modules: the sales side of the house, and nothing else.

Dashboard, Leads, Converted Leads, Closed Deals, Calls, Tasks, Inventory (the
quotations to change, the rest to read), Leaderboard, Rewards, Referral Rewards,
Company Performance, Manager, Team (to read) and Branches. Everything behind the
sale — documentation, accounts, purchase, project, liasoning — and the admin
screens are closed, at the API as well as in the sidebar.
"""
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from leads.access import (can_access_accounts, can_access_closed_deals,
                          can_access_company_performance, can_access_doc_stage2,
                          can_access_documentation, can_access_liasoning,
                          can_access_overdue_projects, can_access_project, can_access_purchase,
                          can_access_warranty, can_add_leads, can_assign_accounts,
                          can_assign_leads, can_assign_project, can_assign_purchase,
                          can_edit_leads)
from leads.models import Lead
from .models import User, Branch, WorkspaceTeam


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456', first_name=username)
    u.role = role
    u.save()
    return u


class SalesManagerModulesTests(TestCase):
    def setUp(self):
        self.sm = mk('sm', 'sales_manager')
        self.admin = mk('sm_admin', 'admin')
        self.bde = mk('sm_bde', 'bde')
        Lead.objects.create(first_name='Asha', phone='9895711001', assigned_to=self.bde)
        Lead.objects.create(first_name='Biju', phone='9895711002')

    def get(self, url, user=None):
        return self.client.get(url, HTTP_AUTHORIZATION=token_for(user or self.sm))

    def send(self, method, url, data, user=None):
        return getattr(self.client, method)(url, data=data, content_type='application/json',
                                            HTTP_AUTHORIZATION=token_for(user or self.sm))

    # ── The modules behind the sale are closed ──
    def test_the_desks_behind_the_sale_are_closed(self):
        for gate in (can_access_documentation, can_access_doc_stage2, can_access_warranty,
                     can_access_accounts, can_access_purchase, can_access_project,
                     can_access_overdue_projects, can_access_liasoning,
                     can_assign_accounts, can_assign_purchase, can_assign_project):
            self.assertFalse(gate(self.sm), gate.__name__)

    def test_the_api_agrees(self):
        for path in ('documentation', 'accounts', 'purchase', 'project', 'liasoning', 'warranty',
                     'documentation-overview', 'bde-feasibility', 'periodic-maintenance',
                     'team-stats'):
            self.assertEqual(self.get(f'/api/leads/{path}/').status_code, 403, path)
        self.assertEqual(self.get('/api/campaigns/').status_code, 403)
        self.assertEqual(self.send('patch', '/api/ai-manager/meeting-config/', {}).status_code, 403)

    def test_no_new_work_is_announced_from_them(self):
        """The sidebar badges and the "new work" popup read these counts."""
        counts = self.get('/api/leads/module-counts/').json()['counts']
        self.assertEqual(set(counts), {'leads'})

    # ── Its own modules work as they did ──
    def test_the_lead_book_is_still_the_whole_company(self):
        self.assertTrue(self.sm.sees_all_leads)
        for gate in (can_add_leads, can_assign_leads, can_edit_leads):
            self.assertTrue(gate(self.sm), gate.__name__)
        d = self.get('/api/leads/').json()
        rows = d if isinstance(d, list) else d['results']
        self.assertEqual({r['first_name'] for r in rows}, {'Asha', 'Biju'})

    def test_its_own_modules_open(self):
        self.assertTrue(can_access_closed_deals(self.sm))
        self.assertTrue(can_access_company_performance(self.sm))
        for url in ('/api/leads/closed-deals/', '/api/company-performance/',
                    '/api/campaigns/options/', '/api/users/', '/api/branches/'):
            self.assertEqual(self.get(url).status_code, 200, url)

    # ── Inventory: quotations to change, the rest to read ──
    def test_inventory_reads_everything_and_writes_only_quotations(self):
        project = self.send('post', '/api/projects/', {'name': '3kW On-Grid', 'price_dcr': '150000'},
                            user=self.admin)
        self.assertEqual(project.status_code, 201, project.content[:200])
        project = project.json()
        for url in ('/api/projects/', '/api/products/', '/api/quotations/',
                    '/api/purchase-orders/', '/api/inventory-dashboard/'):
            self.assertEqual(self.get(url).status_code, 200, url)

        quotation = self.send('post', '/api/quotations/',
                              {'quotation_date': '2026-11-14', 'project': project['id']})
        self.assertEqual(quotation.status_code, 201, quotation.content[:200])
        r = self.send('patch', f"/api/quotations/{quotation.json()['id']}/", {'status': 'accepted'})
        self.assertEqual(r.status_code, 200, r.content[:200])

        for method, url in (('post', '/api/projects/'), ('patch', f"/api/projects/{project['id']}/"),
                            ('delete', f"/api/projects/{project['id']}/"), ('post', '/api/products/'),
                            ('post', '/api/purchase-orders/')):
            self.assertEqual(self.send(method, url, {'name': 'Changed'}).status_code, 403,
                             f'{method} {url}')

    # ── Team: to read ──
    def test_team_is_read_only(self):
        r = self.send('patch', f'/api/users/{self.bde.id}/', {'first_name': 'Renamed'})
        self.assertEqual(r.status_code, 403)
        self.bde.refresh_from_db()
        self.assertEqual(self.bde.first_name, 'sm_bde')
        self.assertEqual(self.send('post', '/api/teams/', {'name': 'North'}).status_code, 403)
        team = WorkspaceTeam.objects.create(name='South')
        self.assertEqual(self.send('patch', f'/api/teams/{team.id}/', {'name': 'X'}).status_code, 403)
        self.assertEqual(self.send('delete', f'/api/teams/{team.id}/', {}).status_code, 403)

    def test_their_own_profile_is_still_theirs(self):
        r = self.send('patch', f'/api/users/{self.sm.id}/', {'first_name': 'Meera'})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.sm.refresh_from_db()
        self.assertEqual(self.sm.first_name, 'Meera')

    def test_but_not_which_team_or_branch_they_are_in(self):
        team = WorkspaceTeam.objects.create(name='South')
        branch = Branch.objects.create(name='Kochi')
        r = self.send('patch', f'/api/users/{self.sm.id}/',
                      {'first_name': 'Meera', 'team': team.id, 'branch': branch.id})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.sm.refresh_from_db()
        self.assertEqual(self.sm.first_name, 'Meera')
        self.assertIsNone(self.sm.team_id)
        self.assertIsNone(self.sm.branch_id)

    def test_only_their_own_card_offers_edit(self):
        d = self.get('/api/users/').json()
        rows = {u['id']: u for u in (d if isinstance(d, list) else d['results'])}
        self.assertTrue(rows[self.sm.id]['can_manage'])
        self.assertFalse(rows[self.bde.id]['can_manage'])

    # ── Branches: the page no longer sends them to the dashboard ──
    def test_branches_open_to_them(self):
        self.assertEqual(self.get('/api/branches/performance/').status_code, 200)
        r = self.send('post', '/api/branches/', {'name': 'Kollam'})
        self.assertEqual(r.status_code, 201, r.content[:200])
        branch = Branch.objects.get(name='Kollam')
        self.assertEqual(self.send('patch', f'/api/branches/{branch.id}/', {'code': 'KLM'}).status_code, 200)

    def test_branches_stay_closed_to_the_floor(self):
        self.assertEqual(self.get('/api/branches/performance/', user=self.bde).status_code, 403)
        self.assertEqual(self.send('post', '/api/branches/', {'name': 'Kochi'}, user=self.bde).status_code, 403)

    # ── Rewards: the whole team's view, none of the controls ──
    def test_rewards_are_watched_not_run(self):
        r = self.get('/api/rewards/')
        self.assertEqual(r.status_code, 200, r.content[:200])
        d = r.json()
        self.assertTrue(d['oversees'])
        self.assertFalse(d['is_admin'])
        self.assertIsNotNone(d['kpis'])
        self.assertEqual(self.get('/api/rewards/settings/').status_code, 403)
        self.assertEqual(self.send('post', '/api/rewards/exclusions/', {'key': 'first:1', 'reason': 'x'})
                         .status_code, 403)

    def test_a_player_still_sees_only_their_own_view(self):
        d = self.get('/api/rewards/', user=self.bde).json()
        self.assertFalse(d['oversees'])
        self.assertIsNone(d['kpis'])

    # ── Nobody else changes ──
    def test_the_coo_keeps_every_module(self):
        coo = mk('sm_coo', 'coo')
        self.assertFalse(coo.kept_out_of('documentation'))
        self.assertTrue(can_access_documentation(coo))
        self.assertTrue(can_assign_accounts(coo))
        self.assertEqual(self.get('/api/campaigns/', user=coo).status_code, 200)
        self.assertEqual(self.get('/api/leads/documentation-overview/', user=coo).status_code, 200)
