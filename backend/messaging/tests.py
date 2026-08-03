"""Retail and wholesale send from different accounts.

The wholesale side may trade under its own identity, so `channel='b2b'` picks the
B2B credentials. A B2B field left blank falls back to the shared one — turning it
on is opt-in per credential rather than all-or-nothing.
"""
from unittest.mock import patch

from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from organization.models import OrgSettings
from users.models import User

from . import email, whatsapp


class WhatsAppChannelTests(TestCase):
    def setUp(self):
        self.org = OrgSettings.load()
        self.org.whatsapp_phone_number_id = 'retail-pid'
        self.org.whatsapp_access_token = 'retail-token'
        self.org.save()

    def test_without_b2b_credentials_wholesale_uses_the_shared_number(self):
        self.assertEqual(whatsapp._creds('b2b'), ('retail-pid', 'retail-token'))

    def test_b2b_credentials_are_used_when_both_are_set(self):
        self.org.b2b_whatsapp_phone_number_id = 'wholesale-pid'
        self.org.b2b_whatsapp_access_token = 'wholesale-token'
        self.org.save()
        self.assertEqual(whatsapp._creds('b2b'), ('wholesale-pid', 'wholesale-token'))
        # The retail side is untouched by any of this.
        self.assertEqual(whatsapp._creds(), ('retail-pid', 'retail-token'))

    def test_a_half_filled_b2b_number_falls_back_rather_than_sending_broken(self):
        self.org.b2b_whatsapp_phone_number_id = 'wholesale-pid'   # no token
        self.org.save()
        self.assertEqual(whatsapp._creds('b2b'), ('retail-pid', 'retail-token'))

    def test_the_channel_reaches_the_graph_call(self):
        self.org.b2b_whatsapp_phone_number_id = 'wholesale-pid'
        self.org.b2b_whatsapp_access_token = 'wholesale-token'
        self.org.save()
        with patch.object(whatsapp._session, 'post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'messages': [{'id': 'wamid.1'}]}
            whatsapp.send_document('9876543210', 'https://x/y.pdf', channel='b2b')
        url = post.call_args[0][0]
        self.assertIn('wholesale-pid', url)
        self.assertEqual(post.call_args[1]['headers']['Authorization'], 'Bearer wholesale-token')


class EmailChannelTests(TestCase):
    def setUp(self):
        self.org = OrgSettings.load()
        self.org.email_host = 'smtp.retail.test'
        self.org.email_host_user = 'retail@energyfox.in'
        self.org.email_from_address = 'retail@energyfox.in'
        self.org.email_from_name = 'EnergyFox'
        self.org.email_signature = 'Retail team'
        self.org.save()

    def test_without_a_b2b_host_wholesale_uses_the_shared_smtp(self):
        cfg, source = email._config('b2b')
        self.assertEqual(source, 'settings')
        self.assertEqual(cfg['host'], 'smtp.retail.test')
        self.assertEqual(email.from_address('b2b'), 'retail@energyfox.in')

    def test_a_b2b_host_takes_over_the_whole_connection(self):
        self.org.b2b_email_host = 'smtp.wholesale.test'
        self.org.b2b_email_port = 465
        self.org.b2b_email_use_ssl = True
        self.org.b2b_email_use_tls = False
        self.org.b2b_email_host_user = 'trade@energyfox.in'
        self.org.b2b_email_host_password = 'secret'
        self.org.save()
        cfg, _ = email._config('b2b')
        self.assertEqual(cfg['host'], 'smtp.wholesale.test')
        self.assertEqual(cfg['port'], 465)
        self.assertEqual(cfg['username'], 'trade@energyfox.in')
        self.assertTrue(cfg['use_ssl'])
        self.assertFalse(cfg['use_tls'])
        # Retail keeps its own settings.
        self.assertEqual(email._config()[0]['host'], 'smtp.retail.test')

    def test_the_from_header_and_signature_follow_the_channel(self):
        self.org.b2b_email_from_address = 'trade@energyfox.in'
        self.org.b2b_email_from_name = 'EnergyFox Trade'
        self.org.b2b_email_signature = 'Wholesale desk'
        self.org.save()
        self.assertEqual(email._from_header('b2b'), 'EnergyFox Trade <trade@energyfox.in>')
        self.assertEqual(email._from_header(), 'EnergyFox <retail@energyfox.in>')
        self.assertTrue(email._with_signature('Hi', 'b2b').endswith('Wholesale desk'))
        self.assertTrue(email._with_signature('Hi').endswith('Retail team'))

    def test_a_blank_b2b_name_falls_back_but_a_set_one_wins(self):
        self.org.b2b_email_from_address = 'trade@energyfox.in'   # no name
        self.org.save()
        self.assertEqual(email._from_header('b2b'), 'EnergyFox <trade@energyfox.in>')


class EmailStatusEndpointTests(TestCase):
    """Settings asks for the status of whichever side is on screen."""

    def setUp(self):
        self.admin = User.objects.create_user(username='chan_admin', password='Pw@123456')
        self.admin.role = 'admin'
        self.admin.save()
        org = OrgSettings.load()
        org.email_host = 'smtp.retail.test'
        org.email_from_address = 'retail@energyfox.in'
        org.b2b_email_host = 'smtp.wholesale.test'
        org.b2b_email_from_address = 'trade@energyfox.in'
        org.save()

    def auth(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(self.admin).access_token}'}

    def test_the_status_endpoint_reports_the_requested_channel(self):
        r = self.client.get('/api/email/status/', **self.auth())
        self.assertEqual(r.json()['from_address'], 'retail@energyfox.in')
        r = self.client.get('/api/email/status/?channel=b2b', **self.auth())
        self.assertEqual(r.json()['host'], 'smtp.wholesale.test')
        self.assertEqual(r.json()['from_address'], 'trade@energyfox.in')


class B2BSettingsSaveTests(TestCase):
    """Settings can store the wholesale credentials, and never loses a secret to
    the dots it showed on screen."""

    def setUp(self):
        self.admin = User.objects.create_user(username='chan_saver', password='Pw@123456')
        self.admin.role = 'admin'
        self.admin.save()

    def auth(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(self.admin).access_token}'}

    def patch(self, payload):
        return self.client.patch('/api/org-settings/', payload,
                                 content_type='application/json', **self.auth())

    def test_the_wholesale_credentials_round_trip(self):
        self.patch({
            'b2b_email_host': 'smtp.wholesale.test', 'b2b_email_port': '465',
            'b2b_email_use_ssl': 'true', 'b2b_email_use_tls': 'false',
            'b2b_email_host_user': 'trade@energyfox.in',
            'b2b_email_host_password': 'wholesale-secret',
            'b2b_whatsapp_phone_number_id': 'wholesale-pid',
            'b2b_whatsapp_access_token': 'wholesale-token',
        })
        org = OrgSettings.load()
        self.assertEqual(org.b2b_email_host, 'smtp.wholesale.test')
        self.assertEqual(org.b2b_email_port, 465)
        self.assertTrue(org.b2b_email_use_ssl)
        self.assertFalse(org.b2b_email_use_tls)
        self.assertEqual(org.b2b_email_host_password, 'wholesale-secret')
        self.assertEqual(org.b2b_whatsapp_access_token, 'wholesale-token')

        # What the screen gets back is dotted out except the last four.
        body = self.client.get('/api/org-settings/', **self.auth()).json()
        self.assertTrue(body['b2b_email_host_password'].endswith('cret'))
        self.assertNotIn('wholesale-secret', body['b2b_email_host_password'])

    def test_saving_the_form_back_unchanged_keeps_the_real_secrets(self):
        self.patch({'b2b_email_host_password': 'wholesale-secret',
                    'b2b_whatsapp_access_token': 'wholesale-token'})
        body = self.client.get('/api/org-settings/', **self.auth()).json()
        # Re-submit exactly what was displayed, as the UI does on any other edit.
        self.patch({'b2b_email_from_name': 'EnergyFox Trade',
                    'b2b_email_host_password': body['b2b_email_host_password'],
                    'b2b_whatsapp_access_token': body['b2b_whatsapp_access_token']})
        org = OrgSettings.load()
        self.assertEqual(org.b2b_email_host_password, 'wholesale-secret')
        self.assertEqual(org.b2b_whatsapp_access_token, 'wholesale-token')
        self.assertEqual(org.b2b_email_from_name, 'EnergyFox Trade')

    def test_the_retail_side_is_left_alone(self):
        org = OrgSettings.load()
        org.email_host, org.email_host_password = 'smtp.retail.test', 'retail-secret'
        org.save()
        self.patch({'b2b_email_host': 'smtp.wholesale.test',
                    'b2b_email_host_password': 'wholesale-secret'})
        org = OrgSettings.load()
        self.assertEqual(org.email_host, 'smtp.retail.test')
        self.assertEqual(org.email_host_password, 'retail-secret')
