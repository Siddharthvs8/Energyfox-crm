"""The dashboard's person and team rows read the same figures as the
performance popup each row opens.

They used to count different leads: the rows only the ones a person *owned*,
the popups every lead they worked — as owner, BDE or tele caller. A tele caller
whose leads were handed to BDEs then showed one deal on the dashboard and
dozens in the popup the card opened.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User, WorkspaceTeam
from .models import Lead, PaymentVerification


def mk(username, role, team=None):
    u = User.objects.create_user(username=username, password='Pw@123456', first_name=username)
    u.role = role
    u.team = team
    u.save()
    return u


def bearer(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


class DashboardFiguresTests(TestCase):
    def setUp(self):
        self.callers = WorkspaceTeam.objects.create(name='Telecallers')
        self.sales = WorkspaceTeam.objects.create(name='Sales')
        self.boss = mk('d_boss', 'superadmin')
        self.caller = mk('d_caller', 'tele_caller', self.callers)
        self.bde = mk('d_bde', 'bde', self.sales)
        # The usual shape: the tele caller found it, the BDE now owns and closed it.
        self.won(500000, owner=self.bde, bde=self.bde, caller=self.caller)
        # One the tele caller still owns.
        self.won(225000, owner=self.caller, caller=self.caller)
        Lead.objects.create(first_name='Open', phone='9700000003', status='interested',
                            assigned_to=self.caller, tele_caller=self.caller, value=Decimal(100000))

    def won(self, value, owner, bde=None, caller=None):
        lead = Lead.objects.create(
            first_name='Won', last_name=str(value), phone=f'97{value:08d}', status='converted',
            is_lost=False, pushed_to_accounts=True, value=Decimal(value),
            assigned_to=owner, bde=bde, tele_caller=caller)
        PaymentVerification.objects.create(lead=lead, amount_received=Decimal(value))
        return lead

    def get(self, url):
        r = self.client.get(url, HTTP_AUTHORIZATION=bearer(self.boss))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def dashboard(self, key):
        return {row['id']: row for row in self.get('/api/dashboard-stats/')[key]}

    def assertSameAsPopup(self, row, summary):
        self.assertEqual(
            (row['won_count'], row['won_value'], row['leads_count'], row['pipeline_value']),
            (summary['won_count'], summary['won_value'], summary['total_leads'], summary['pipeline_value']))

    def test_a_team_card_counts_the_deals_its_members_worked(self):
        teams = self.dashboard('team_stats')
        self.assertEqual((teams[self.callers.id]['won_count'], teams[self.callers.id]['won_value']),
                         (2, 725000.0))
        self.assertEqual((teams[self.sales.id]['won_count'], teams[self.sales.id]['won_value']),
                         (1, 500000.0))

    def test_and_says_what_its_popup_says(self):
        teams = self.dashboard('team_stats')
        for team in (self.callers, self.sales):
            popup = self.get(f'/api/teams/{team.id}/performance/')['summary']
            self.assertSameAsPopup(teams[team.id], popup)

    def test_so_does_each_persons_row(self):
        people = self.dashboard('performance_stats')
        self.assertEqual((people[self.caller.id]['won_count'], people[self.caller.id]['won_value']),
                         (2, 725000.0))
        for person in (self.caller, self.bde):
            popup = self.get(f'/api/users/{person.id}/performance/')['summary']
            self.assertSameAsPopup(people[person.id], popup)

    def test_a_lead_two_members_share_counts_once(self):
        self.bde.team = self.callers
        self.bde.save()
        team = self.dashboard('team_stats')[self.callers.id]
        self.assertEqual((team['won_count'], team['won_value'], team['leads_count']), (2, 725000.0, 3))
