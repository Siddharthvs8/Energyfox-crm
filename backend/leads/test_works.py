"""Works: the pipeline from site visit to finished project, split at a desk's
own stage into upcoming and completed works."""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from users.models import CustomRole
from .models import Lead, Product, Project, SiteVisit
from .tests import mk, token_for


class WorksAccessTests(TestCase):
    """Works is drawn around the viewer's own stage, so only the three desks
    that own one get it."""

    def get(self, user):
        return self.client.get('/api/works/', HTTP_AUTHORIZATION=token_for(user))

    def test_the_three_desks_open_it(self):
        for role, stage in (('documentation_manager', 'documentation'),
                            ('accounts_manager', 'accounts'),
                            ('project_manager', 'project')):
            r = self.get(mk(f'w_{role}', role))
            self.assertEqual(r.status_code, 200, (role, r.content[:200]))
            self.assertEqual(r.json()['desk']['stage'], stage)

    def test_nobody_else_does(self):
        for role in ('superadmin', 'admin', 'coo', 'sales_manager', 'leads_manager',
                     'branch_manager', 'documentation_staff', 'accounts_staff',
                     'purchase_staff', 'liasoning_officer', 'bde', 'tele_caller', 'spectator'):
            self.assertEqual(self.get(mk(f'w_no_{role}', role)).status_code, 403, role)

    def test_not_a_custom_role_either_whatever_it_is_granted(self):
        everything = CustomRole.objects.create(
            name='Ops', permissions=['documentation', 'accounts', 'project', 'leads.view_all'])
        u = mk('w_custom', 'custom')
        u.custom_role = everything
        u.save()
        self.assertEqual(self.get(u).status_code, 403)

    def test_needs_a_login(self):
        self.assertEqual(self.client.get('/api/works/').status_code, 401)


class WorksStagesTests(TestCase):

    def setUp(self):
        self.doc_mgr = mk('ws_docmgr', 'documentation_manager')
        self.acc_mgr = mk('ws_accmgr', 'accounts_manager')
        self.pm = mk('ws_pm', 'project_manager')
        self.bde = mk('ws_bde', 'bde')
        self.bde.first_name, self.bde.last_name = 'Rahul', 'K'
        self.bde.save()
        self.doc_staff = mk('ws_docstaff', 'documentation_staff')
        self.acc_staff = mk('ws_accstaff', 'accounts_staff')
        self.buyer = mk('ws_buyer', 'purchase_staff')
        self.kit = Product.objects.create(name='5 kW On-grid')
        now = timezone.now()

        def lead(name, **kw):
            kw.setdefault('status', 'converted')
            kw.setdefault('bde', self.bde)
            return Lead.objects.create(first_name=name, phone=f'94{len(name):08d}',
                                       product=self.kit, value=Decimal('200000'), **kw)

        documented = dict(pushed_to_documentation=True, pushed_to_documentation_at=now,
                          documentation_staff=self.doc_staff)
        accounted = dict(documented, pushed_to_accounts=True, pushed_to_accounts_at=now,
                         accounts_staff=self.acc_staff)
        bought = dict(accounted, pushed_to_purchase=True, pushed_to_purchase_at=now,
                      purchase_staff=self.buyer)
        built = dict(bought, pushed_to_project=True, pushed_to_project_at=now,
                     project_manager=self.pm)

        self.visit = lead('Visit', status='interested')
        self.po = lead('Signed')
        SiteVisit.objects.create(lead=self.po, po_signed_date=date(2026, 10, 1))
        self.doc = lead('Paper', **documented)
        self.acc = lead('Money', **accounted)
        self.pur = lead('Bought', **bought)
        self.proj = lead('Building', **built)
        Project.objects.create(lead=self.proj)
        # Finished and long since archived: still a completed work.
        self.done = lead('Finished', is_archived=True, archived_at=now, **built)
        Project.objects.create(lead=self.done, is_complete=True, completed_at=now, completed_by=self.pm)

        # None of these is a work.
        self.lost = lead('Lost', is_lost=True, **accounted)
        self.cold = lead('Cold', status='not_interested')
        self.binned = lead('Binned', is_trashed=True, **bought)
        self.unvisited = lead('Calling', bde=None, status='follow_up')

    def fetch(self, user, **params):
        r = self.client.get('/api/works/', params, HTTP_AUTHORIZATION=token_for(user))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def listed(self, user, view, **params):
        """{stage: [lead ids]} in the order the groups came back."""
        body = self.fetch(user, view=view, **params)
        return {g['stage']: [w['id'] for w in g['works']] for g in body['groups']}

    def test_accounts_manager_upcoming_is_every_stage_before_accounts(self):
        got = self.listed(self.acc_mgr, 'upcoming')
        self.assertEqual(list(got), ['documentation', 'po_signed', 'site_visit'],
                         'nearest to the accounts stage first')
        self.assertEqual(got, {'documentation': [self.doc.id], 'po_signed': [self.po.id],
                               'site_visit': [self.visit.id]})

    def test_accounts_manager_completed_is_every_stage_past_accounts(self):
        got = self.listed(self.acc_mgr, 'completed')
        self.assertEqual(list(got), ['purchase', 'project', 'completed'])
        self.assertEqual(got, {'purchase': [self.pur.id], 'project': [self.proj.id],
                               'completed': [self.done.id]})

    def test_their_own_stage_is_counted_but_listed_in_neither(self):
        body = self.fetch(self.acc_mgr)
        sides = {s['key']: (s['side'], s['count']) for s in body['stages']}
        self.assertEqual(sides, {
            'site_visit': ('upcoming', 1), 'po_signed': ('upcoming', 1),
            'documentation': ('upcoming', 1), 'accounts': ('mine', 1),
            'purchase': ('completed', 1), 'project': ('completed', 1),
            'completed': ('completed', 1)})
        self.assertEqual(body['desk'], {'stage': 'accounts', 'label': 'Accounts', 'module': '/accounts'})
        everything = [i for view in ('upcoming', 'completed')
                      for ids in self.listed(self.acc_mgr, view).values() for i in ids]
        self.assertNotIn(self.acc.id, everything)

    def test_documentation_manager_splits_at_documentation_stage_1(self):
        self.assertEqual(self.listed(self.doc_mgr, 'upcoming'),
                         {'po_signed': [self.po.id], 'site_visit': [self.visit.id]})
        self.assertEqual(self.listed(self.doc_mgr, 'completed'),
                         {'accounts': [self.acc.id], 'purchase': [self.pur.id],
                          'project': [self.proj.id], 'completed': [self.done.id]})

    def test_project_manager_splits_at_the_project(self):
        upcoming = self.listed(self.pm, 'upcoming')
        self.assertEqual(list(upcoming), ['purchase', 'accounts', 'documentation', 'po_signed', 'site_visit'])
        self.assertEqual(self.listed(self.pm, 'completed'), {'completed': [self.done.id]})
        self.assertEqual(self.fetch(self.pm)['total'], 5)

    def test_lost_cold_trashed_and_pre_visit_leads_are_not_works(self):
        everyone = {i for user in (self.doc_mgr, self.acc_mgr, self.pm)
                    for view in ('upcoming', 'completed')
                    for ids in self.listed(user, view).values() for i in ids}
        for left_out in (self.lost, self.cold, self.binned, self.unvisited):
            self.assertNotIn(left_out.id, everyone, left_out.first_name)
        self.assertEqual(sum(s['count'] for s in self.fetch(self.pm)['stages']), 7)

    def test_a_project_with_no_record_yet_is_in_progress(self):
        Project.objects.filter(lead=self.proj).delete()
        self.assertEqual(self.listed(self.acc_mgr, 'completed')['project'], [self.proj.id])

    def test_search_narrows_the_rows_and_the_counts(self):
        body = self.fetch(self.acc_mgr, view='completed', search='build')
        self.assertEqual({s['key']: s['count'] for s in body['stages'] if s['count']}, {'project': 1})
        self.assertEqual({g['stage']: [w['id'] for w in g['works']] for g in body['groups']},
                         {'purchase': [], 'project': [self.proj.id], 'completed': []})
        # By phone, place and the BDE's name too.
        Lead.objects.filter(pk=self.pur.pk).update(company='Payyanur')
        self.assertEqual(self.listed(self.acc_mgr, 'completed', search='payyan')['purchase'], [self.pur.id])
        self.assertEqual(self.listed(self.acc_mgr, 'upcoming', search=self.po.phone)['po_signed'], [self.po.id])
        self.assertEqual(self.fetch(self.acc_mgr, view='upcoming', search='rahul k')['total'], 3)

    def test_a_stage_comes_a_page_at_a_time(self):
        now = timezone.now()
        extra = [Lead.objects.create(first_name=f'More {n}', bde=self.bde, status='interested')
                 for n in range(4)]
        # save() stamps the BDE's arrival as now; back-date them a day apart.
        for n, l in enumerate(extra):
            Lead.objects.filter(pk=l.pk).update(bde_assigned_at=now - timedelta(days=n + 1))
        newest_first = [self.visit.id] + [l.id for l in extra]

        first = self.fetch(self.acc_mgr, view='upcoming', stage='site_visit', limit=2)
        self.assertEqual([g['stage'] for g in first['groups']], ['site_visit'])
        group = first['groups'][0]
        self.assertEqual(([w['id'] for w in group['works']], group['count'], group['has_more']),
                         (newest_first[:2], 5, True))
        rest = self.fetch(self.acc_mgr, view='upcoming', stage='site_visit', limit=2, offset=4)['groups'][0]
        self.assertEqual(([w['id'] for w in rest['works']], rest['has_more']), (newest_first[4:], False))
        # Without a stage there is nothing to page, so an offset is ignored.
        self.assertEqual(self.listed(self.acc_mgr, 'upcoming', offset=3)['documentation'], [self.doc.id])

    def test_requests_that_make_no_sense_are_refused(self):
        def status(**params):
            return self.client.get('/api/works/', params,
                                   HTTP_AUTHORIZATION=token_for(self.acc_mgr)).status_code
        self.assertEqual(status(view='everything'), 400)
        self.assertEqual(status(view='upcoming', stage='purchase'), 400)
        self.assertEqual(status(view='completed', stage='accounts'), 400, 'their own stage is in neither')
        self.assertEqual(status(view='completed', stage='nonsense'), 400)
        self.assertEqual(status(view='completed', stage='project', limit='lots'), 200)

    def test_each_work_says_where_it_is_and_how_it_got_there(self):
        # 8 pm UTC on the 20th is half past one on the 21st in India: the day
        # the office would give is the 21st.
        late = datetime(2026, 10, 20, 20, 0, tzinfo=dt_timezone.utc)
        Lead.objects.filter(pk=self.done.pk).update(
            pushed_to_purchase_at=late, bde_assigned_at=datetime(2026, 9, 1, 6, 0, tzinfo=dt_timezone.utc))
        Project.objects.filter(lead=self.done).update(
            completed_at=datetime(2026, 10, 25, 5, 0, tzinfo=dt_timezone.utc))
        self.pm.first_name = 'Meera'
        self.pm.save()

        work = self.fetch(self.acc_mgr, view='completed', stage='completed')['groups'][0]['works'][0]
        self.assertEqual({k: work[k] for k in ('id', 'name', 'product', 'value', 'bde_name',
                                               'stage', 'since', 'handler_name')},
                         {'id': self.done.id, 'name': 'Finished', 'product': '5 kW On-grid',
                          'value': '200000.00', 'bde_name': 'Rahul K', 'stage': 'completed',
                          'since': '2026-10-25', 'handler_name': 'Meera'})
        journey = {step['stage']: (step['on'], step['by']) for step in work['journey']}
        self.assertEqual(list(journey), ['site_visit', 'po_signed', 'documentation', 'accounts',
                                         'purchase', 'project', 'completed'])
        self.assertEqual(journey['site_visit'], ('2026-09-01', 'Rahul K'))
        self.assertEqual(journey['po_signed'], (None, 'Rahul K'), 'passed, though no PO date was kept')
        self.assertEqual(journey['purchase'], ('2026-10-21', 'ws_buyer'))
        self.assertEqual(journey['completed'], ('2026-10-25', 'Meera'))

        # A work only carries the road up to where it is now.
        visit = self.fetch(self.acc_mgr, view='upcoming', stage='site_visit')['groups'][0]['works'][0]
        self.assertEqual([s['stage'] for s in visit['journey']], ['site_visit'])
        self.assertEqual(visit['handler_name'], 'Rahul K')
