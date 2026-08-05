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


class HtmlSignatureTests(TestCase):
    """The signature can be plain, HTML, or both.

    The plain one always goes out as the text part, so a client that refuses HTML
    is never left with nothing. Setting an HTML one adds an HTML part carrying it.
    """

    def setUp(self):
        self.org = OrgSettings.load()
        self.org.email_host = 'smtp.retail.test'
        self.org.email_host_user = 'retail@energyfox.in'
        self.org.email_signature = 'Regards,\nEnergyFox'
        self.org.save()

    def build(self, body='Body line one.', **kwargs):
        """The message send_and_log built, caught instead of sent."""
        caught = {}

        def capture(msg, *a, **kw):
            caught['msg'] = msg

        with patch.object(email, '_connection', return_value=None), \
             patch('django.core.mail.EmailMultiAlternatives.send', new=capture):
            log = email.send_and_log(to='someone@example.com', subject='Hi',
                                     body=body, **kwargs)
        self.assertEqual(log.status, 'sent', log.error)
        return caught['msg']

    # â”€â”€ The text part is untouched â”€â”€
    def test_the_plain_signature_still_lands_in_the_text_part(self):
        msg = self.build()
        self.assertIn('Body line one.', msg.body)
        self.assertTrue(msg.body.rstrip().endswith('EnergyFox'))

    def test_with_no_html_signature_the_mail_stays_plain_text(self):
        """Nothing richer to show, so no HTML part is invented."""
        self.assertEqual(self.build().alternatives, [])

    # â”€â”€ The HTML signature â”€â”€
    def test_an_html_signature_adds_an_html_part(self):
        self.org.email_signature_html = '<b>EnergyFox</b> &middot; <a href="https://x">x</a>'
        self.org.save()
        msg = self.build()
        self.assertEqual(len(msg.alternatives), 1)
        html, mime = msg.alternatives[0]
        self.assertEqual(mime, 'text/html')
        self.assertIn('<b>EnergyFox</b>', html)
        # The body comes into the HTML part too, or the mail would arrive as a
        # signature with no message above it.
        self.assertIn('Body line one.', html)
        # The text part is unchanged, still carrying the plain signature.
        self.assertTrue(msg.body.rstrip().endswith('EnergyFox'))

    def test_the_body_is_escaped_when_it_is_lifted_into_html(self):
        """A plain-text body is not markup â€” angle brackets must not become tags."""
        self.org.email_signature_html = '<b>EnergyFox</b>'
        self.org.save()
        html = self.build(body='5 < 6 & <script>x</script>').alternatives[0][0]
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)

    def test_line_breaks_in_the_body_survive_into_html(self):
        self.org.email_signature_html = '<b>EnergyFox</b>'
        self.org.save()
        html = self.build(body='One\nTwo').alternatives[0][0]
        self.assertIn('One<br>Two', html)

    def test_a_callers_own_html_gets_the_signature_appended(self):
        self.org.email_signature_html = '<b>EnergyFox</b>'
        self.org.save()
        html = self.build(html_body='<p>Invoice attached.</p>').alternatives[0][0]
        self.assertIn('<p>Invoice attached.</p>', html)
        self.assertIn('<b>EnergyFox</b>', html)

    def test_a_callers_html_falls_back_to_the_plain_signature_as_html(self):
        """No HTML signature set, so the plain one is converted rather than lost.

        This was the gap before: mail built with its own HTML arrived with no
        signature at all, because only the text part ever got one.
        """
        html = self.build(html_body='<p>Invoice attached.</p>').alternatives[0][0]
        self.assertIn('<p>Invoice attached.</p>', html)
        self.assertIn('Regards,<br>EnergyFox', html)

    def test_no_signature_at_all_leaves_a_callers_html_alone(self):
        self.org.email_signature = ''
        self.org.save()
        msg = self.build(html_body='<p>Invoice attached.</p>')
        self.assertEqual(msg.alternatives[0][0], '<p>Invoice attached.</p>')

    # â”€â”€ Per-channel â”€â”€
    def test_wholesale_can_have_its_own_html_signature(self):
        self.org.email_signature_html = '<b>Retail</b>'
        self.org.b2b_email_signature_html = '<b>Wholesale</b>'
        self.org.save()
        self.assertIn('<b>Wholesale</b>', email._signature_html('b2b'))
        self.assertIn('<b>Retail</b>', email._signature_html())

    def test_a_blank_b2b_html_signature_falls_back_to_the_shared_one(self):
        self.org.email_signature_html = '<b>Retail</b>'
        self.org.save()
        self.assertIn('<b>Retail</b>', email._signature_html('b2b'))

    # â”€â”€ Settings â”€â”€
    def test_the_html_signature_survives_a_settings_round_trip(self):
        """Admins edit it in Settings, so it has to save and come back intact."""
        admin = User.objects.create_user(username='sig_admin', password='Pw@123456')
        admin.role = 'superadmin'
        admin.is_superuser = True
        admin.is_staff = True
        admin.save()
        markup = '<p style="color:#334155">Regards,<br><b>EnergyFox</b></p>'
        r = self.client.patch('/api/org-settings/',
                              data={'email_signature_html': markup},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(admin).access_token}')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['email_signature_html'], markup)
        self.assertEqual(OrgSettings.load().email_signature_html, markup)

    def test_a_non_admin_cannot_change_the_signature(self):
        staff = User.objects.create_user(username='sig_bde', password='Pw@123456')
        staff.role = 'bde'
        staff.save()
        r = self.client.patch('/api/org-settings/',
                              data={'email_signature_html': '<b>nope</b>'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(staff).access_token}')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(OrgSettings.load().email_signature_html, '')
