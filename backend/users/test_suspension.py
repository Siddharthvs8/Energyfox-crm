"""Suspending an account: the super admin's power, and what it does.

A suspended account is kept — its leads, tasks and history with it — but it is
signed out at once, cannot sign back in, and is handed no new work until a
super admin reactivates it.
"""
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import AuditEntry
from leads.models import Lead
from tasks.models import Task
from .models import User

PASSWORD = 'Pw@123456'


def mk(username, role):
    u = User.objects.create_user(username=username, password=PASSWORD, first_name=username.title())
    u.role = role
    u.save()
    return u


def bearer(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


class SuspensionTests(TestCase):
    def setUp(self):
        self.boss = mk('boss', 'superadmin')
        self.admin = mk('office', 'admin')
        self.bde = mk('ravi', 'bde')
        self.caller = mk('anu', 'tele_caller')

    def send(self, method, url, user, data=None):
        return getattr(self.client, method)(url, data=data or {}, content_type='application/json',
                                            HTTP_AUTHORIZATION=bearer(user))

    def get(self, url, user):
        return self.client.get(url, HTTP_AUTHORIZATION=bearer(user))

    def rows(self, url, user):
        d = self.get(url, user).json()
        return d if isinstance(d, list) else d['results']

    def suspend(self, who, by=None):
        return self.send('post', f'/api/users/{who.id}/suspend/', by or self.boss)

    def login(self, username, password=PASSWORD):
        return self.client.post('/api/token/', {'username': username, 'password': password},
                                content_type='application/json')

    # ── Who may ──
    def test_the_super_admin_suspends(self):
        r = self.suspend(self.bde)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(r.json()['suspended'])
        self.bde.refresh_from_db()
        self.assertFalse(self.bde.is_active)

    def test_and_reactivates_them_as_they_were(self):
        self.suspend(self.bde)
        r = self.send('post', f'/api/users/{self.bde.id}/reactivate/', self.boss)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertFalse(r.json()['suspended'])
        self.bde.refresh_from_db()
        self.assertTrue(self.bde.is_active)
        self.assertEqual(self.bde.role, 'bde')
        self.assertEqual(self.login('ravi').status_code, 200)

    def test_suspending_twice_changes_nothing(self):
        self.suspend(self.bde)
        r = self.suspend(self.bde)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['suspended'])

    def test_nobody_else_may(self):
        r = self.suspend(self.bde, by=self.admin)
        self.assertEqual(r.status_code, 403)
        self.assertIn('Only a Super Admin', r.json()['detail'])
        # A tele caller's directory is their own team, so the account isn't
        # even there to act on.
        self.assertEqual(self.suspend(self.bde, by=self.caller).status_code, 404)
        self.bde.refresh_from_db()
        self.assertTrue(self.bde.is_active)

    def test_not_their_own_account_nor_another_super_admins(self):
        other = mk('boss2', 'superadmin')
        r = self.suspend(self.boss)
        self.assertEqual(r.status_code, 403)
        self.assertIn('your own account', r.json()['detail'])
        self.assertEqual(self.suspend(other).status_code, 403)
        # Every rank below them is theirs to suspend, admins included.
        self.assertEqual(self.suspend(self.admin).status_code, 200)

    def test_the_team_page_is_told_whom_it_may_suspend(self):
        rows = {u['id']: u for u in self.rows('/api/users/', self.boss)}
        self.assertTrue(rows[self.bde.id]['can_suspend'])
        self.assertTrue(rows[self.admin.id]['can_suspend'])
        self.assertFalse(rows[self.boss.id]['can_suspend'])
        self.assertFalse(any(u['can_suspend'] for u in self.rows('/api/users/', self.admin)))

    # ── What it does ──
    def test_they_are_signed_out_at_once(self):
        token = bearer(self.bde)
        self.assertEqual(self.client.get('/api/users/me/', HTTP_AUTHORIZATION=token).status_code, 200)
        self.suspend(self.bde)
        self.assertEqual(self.client.get('/api/users/me/', HTTP_AUTHORIZATION=token).status_code, 401)

    def test_and_cannot_refresh_their_way_back_in(self):
        refresh = str(RefreshToken.for_user(self.bde))
        self.suspend(self.bde)
        r = self.client.post('/api/token/refresh/', {'refresh': refresh}, content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_sign_in_says_suspended_only_to_the_right_password(self):
        self.suspend(self.bde)
        r = self.login('ravi')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()['code'], 'account_suspended')
        self.assertIn('suspended', r.json()['detail'])
        wrong = self.login('ravi', 'not-it')
        self.assertEqual(wrong.status_code, 401)
        self.assertNotIn('suspended', wrong.content.decode())
        # The same answer an account that doesn't exist gets.
        self.assertEqual(wrong.json(), self.login('nobody', 'not-it').json())

    def test_an_active_account_signs_in_as_before(self):
        r = self.login('ravi')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {'access', 'refresh'})
        self.assertEqual(self.login('ravi', 'not-it').status_code, 401)

    def test_their_work_stays_theirs(self):
        lead = Lead.objects.create(first_name='Asha', phone='9895700001', assigned_to=self.bde, bde=self.bde)
        task = Task.objects.create(title='Site visit', assignee=self.bde)
        self.suspend(self.bde)
        lead.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual((lead.assigned_to_id, lead.bde_id, task.assignee_id), (self.bde.id,) * 3)

    def test_it_is_in_the_activity_log(self):
        self.suspend(self.bde)
        entry = AuditEntry.objects.filter(model_label='users.User', object_id=str(self.bde.id)).first()
        self.assertIsNotNone(entry)
        self.assertIn('is_active', entry.changes)
        self.assertEqual(entry.actor_id, self.boss.id)

    # ── Who sees a suspended account ──
    def test_only_the_super_admins_team_page_lists_them(self):
        self.suspend(self.bde)

        def ids(url, user):
            return {u['id'] for u in self.rows(url, user)}
        self.assertIn(self.bde.id, ids('/api/users/?include_suspended=1', self.boss))
        # Not on the plain directory, which the pickers read …
        self.assertNotIn(self.bde.id, ids('/api/users/', self.boss))
        # … and never for anyone else, asked or not.
        self.assertNotIn(self.bde.id, ids('/api/users/?include_suspended=1', self.admin))

    def test_the_super_admin_can_still_open_edit_and_remove_one(self):
        self.suspend(self.bde)
        self.assertEqual(self.get(f'/api/users/{self.bde.id}/', self.boss).status_code, 200)
        r = self.send('patch', f'/api/users/{self.bde.id}/', self.boss, {'first_name': 'Ravi K'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.bde.refresh_from_db()
        self.assertEqual((self.bde.first_name, self.bde.is_active), ('Ravi K', False))
        self.assertEqual(self.get(f'/api/users/{self.bde.id}/', self.admin).status_code, 404)
        self.assertEqual(self.send('delete', f'/api/users/{self.bde.id}/', self.boss).status_code, 204)

    # ── No new work reaches them ──
    def test_out_of_every_picker(self):
        self.suspend(self.bde)
        for url in ('/api/users/bdes/', '/api/users/assignable/', '/api/users/referrers/'):
            self.assertNotIn(self.bde.id, {u['id'] for u in self.get(url, self.admin).json()}, url)

    def test_not_assignable_by_hand(self):
        """The pickers never offer them; a page opened before the suspension
        still can't hand them anything."""
        lead = Lead.objects.create(first_name='Biju', phone='9895700002', assigned_to=self.caller)
        self.suspend(self.bde)
        self.assertEqual(self.send('post', f'/api/leads/{lead.id}/assign-bde/', self.admin,
                                   {'bde': self.bde.id}).status_code, 404)
        self.assertEqual(self.send('post', '/api/leads/bulk_assign/', self.admin,
                                   {'ids': [lead.id], 'user_id': self.bde.id}).status_code, 404)
        r = self.send('patch', f'/api/leads/{lead.id}/', self.admin, {'assigned_to': self.bde.id})
        self.assertEqual(r.status_code, 400)
        self.assertIn('suspended', r.json()['assigned_to'][0])
        lead.refresh_from_db()
        self.assertEqual((lead.assigned_to_id, lead.bde_id), (self.caller.id, None))

    def test_a_lead_still_with_them_goes_on_saving(self):
        lead = Lead.objects.create(first_name='Chitra', phone='9895700003', assigned_to=self.bde)
        self.suspend(self.bde)
        r = self.send('patch', f'/api/leads/{lead.id}/', self.admin,
                      {'assigned_to': self.bde.id, 'notes': 'Called back'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        # And handing it on to someone active is the way out.
        r = self.send('patch', f'/api/leads/{lead.id}/', self.admin, {'assigned_to': self.caller.id})
        self.assertEqual(r.status_code, 200, r.content[:300])

    def test_tasks_too(self):
        task = Task.objects.create(title='Follow up', assignee=self.bde)
        self.suspend(self.bde)
        r = self.send('post', '/api/tasks/', self.admin, {'title': 'New visit', 'assignee': self.bde.id})
        self.assertEqual(r.status_code, 400)
        self.assertIn('suspended', r.json()['assignee'][0])
        r = self.send('patch', f'/api/tasks/{task.id}/', self.admin,
                      {'title': 'Follow up today', 'assignee': self.bde.id})
        self.assertEqual(r.status_code, 200, r.content[:300])

    def test_automations_route_nothing_to_them(self):
        from automations.engine import _action_assign_lead
        lead = Lead.objects.create(first_name='Deepa', phone='9895700004', assigned_to=self.caller)
        self.suspend(self.bde)
        with self.assertRaisesMessage(ValueError, 'suspended'):
            _action_assign_lead({'user_id': self.bde.id}, lead, {})
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to_id, self.caller.id)

    def test_round_robins_pass_them_by(self):
        from leads.views import auto_assign_accounts
        away, here = mk('acc_away', 'accounts_staff'), mk('acc_here', 'accounts_staff')
        self.suspend(away)
        for n in range(3):
            lead = Lead.objects.create(first_name=f'Eapen{n}', phone=f'989570001{n}')
            self.assertEqual(auto_assign_accounts(lead), here)
