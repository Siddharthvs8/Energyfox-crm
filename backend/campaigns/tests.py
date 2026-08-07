"""Who can read campaigns, and how much of one.

A tele caller filters their lead list by campaign, so they need the names. The
campaign record itself carries budget, spend and expected revenue, which is not
theirs to see — so the names come from their own endpoint and the full one stays
with admins and managers.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from leads.models import Lead
from users.models import User

from .models import Campaign


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456')
    u.role = role
    u.save()
    return u


class CampaignOptionsAccessTests(TestCase):
    MONEY_FIELDS = ('expected_revenue', 'budgeted_cost', 'actual_cost',
                    'expected_response', 'number_sent')

    def setUp(self):
        self.caller = mk('co_caller', 'tele_caller')
        self.bde = mk('co_bde', 'bde')
        self.admin = mk('co_admin', 'superadmin')
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save()

        self.campaign = Campaign.objects.create(
            name='TVM_Kollam AD(29_07_2026)', campaign_type='advertisement',
            status='active', budgeted_cost=Decimal('50000'),
            expected_revenue=Decimal('900000'))
        self.other = Campaign.objects.create(name='Alappuzha ad',
                                             campaign_type='advertisement', status='active')

    def options(self, user):
        return self.client.get('/api/campaigns/options/', HTTP_AUTHORIZATION=token_for(user))

    # ── The names are readable by the people who filter on them ──
    def test_a_tele_caller_can_read_the_campaign_names(self):
        r = self.options(self.caller)
        self.assertEqual(r.status_code, 200, r.content[:200])
        names = [row['name'] for row in r.json()]
        self.assertIn('TVM_Kollam AD(29_07_2026)', names)

    def test_a_bde_can_read_them_too(self):
        self.assertEqual(self.options(self.bde).status_code, 200)

    def test_the_options_are_sorted_by_name(self):
        names = [row['name'] for row in self.options(self.caller).json()]
        self.assertEqual(names, sorted(names))

    def test_only_the_id_and_the_name_come_back(self):
        """The commercial figures are not a tele caller's business."""
        row = self.options(self.caller).json()[0]
        self.assertEqual(set(row), {'id', 'name'})
        for field in self.MONEY_FIELDS:
            self.assertNotIn(field, row)

    def test_an_anonymous_request_is_refused(self):
        self.assertIn(self.client.get('/api/campaigns/options/').status_code, (401, 403))

    # ── The full endpoint is unchanged ──
    def test_a_tele_caller_still_cannot_list_the_campaigns_themselves(self):
        r = self.client.get('/api/campaigns/', HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 403)

    def test_a_tele_caller_still_cannot_open_one(self):
        """This is what made the campaign chip lead to "Campaign not found"."""
        r = self.client.get(f'/api/campaigns/{self.campaign.id}/',
                            HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 403)

    def test_a_tele_caller_cannot_create_one(self):
        r = self.client.post('/api/campaigns/', data={'name': 'Mine', 'campaign_type': 'advertisement'},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Campaign.objects.filter(name='Mine').exists())

    def test_an_admin_still_gets_the_whole_record(self):
        r = self.client.get(f'/api/campaigns/{self.campaign.id}/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['budgeted_cost'], '50000.00')


class LeadCampaignFilterTests(TestCase):
    """Filtering the lead list by campaign, as the tele caller does it."""

    def setUp(self):
        self.caller = mk('lcf_caller', 'tele_caller')
        self.campaign = Campaign.objects.create(name='TVM ad', campaign_type='advertisement',
                                                status='active')
        self.in_campaign = Lead.objects.create(first_name='Ajeet', last_name='kurup',
                                               phone='9744159401', assigned_to=self.caller)
        self.out_of_it = Lead.objects.create(first_name='Muhammad', last_name='Vk',
                                             phone='9562129236', assigned_to=self.caller)
        self.campaign.leads.add(self.in_campaign)

    def names(self, query=''):
        r = self.client.get(f'/api/leads/{query}', HTTP_AUTHORIZATION=token_for(self.caller))
        self.assertEqual(r.status_code, 200, r.content[:200])
        body = r.json()
        rows = body if isinstance(body, list) else body.get('results', [])
        return {row['first_name'] for row in rows}

    def test_filtering_by_a_campaign_narrows_the_list(self):
        self.assertEqual(self.names(f'?campaign={self.campaign.id}'), {'Ajeet'})

    def test_no_campaign_finds_the_ones_outside_every_campaign(self):
        self.assertEqual(self.names('?campaign=none'), {'Muhammad'})

    def test_without_the_filter_both_are_listed(self):
        self.assertEqual(self.names(), {'Ajeet', 'Muhammad'})
