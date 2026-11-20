"""The site's Google Maps location, pinned by the BDE on the site visit and read
by the stages that go out to the site (purchase & logistics, project)."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .models import ActivityLog, Lead, Project, SiteVisit
from .tests import mk, token_for


class SiteLocationTests(TestCase):

    def setUp(self):
        self.bde = mk('svl_bde', 'bde')
        self.bde.first_name, self.bde.last_name = 'Anandu', 'K'
        self.bde.save()
        self.other_bde = mk('svl_bde2', 'bde')
        self.purchase = mk('svl_purchase', 'purchase_staff')
        self.pm = mk('svl_pm', 'project_manager')
        self.lead = Lead.objects.create(
            first_name='Anitha', last_name='VR', phone='9496418300', status='converted', bde=self.bde,
            pushed_to_purchase=True, pushed_to_purchase_at=timezone.now(), purchase_staff=self.purchase,
            pushed_to_project=True, pushed_to_project_at=timezone.now(), project_manager=self.pm)
        Project.objects.create(lead=self.lead)
        self.sv = SiteVisit.objects.create(lead=self.lead, roof_type='rcc', plant_capacity='5 kW')
        self.url = f'/api/leads/{self.lead.id}/site-visit/'

    def patch(self, body, user=None):
        return self.client.patch(self.url, body, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(user or self.bde))

    def pin(self, lat=10.0167891234, lng=76.3456789012, accuracy=12.7, source='gps', user=None):
        return self.patch({'site_latitude': lat, 'site_longitude': lng,
                           'site_location_accuracy': accuracy, 'site_location_source': source}, user)

    def location_lines(self):
        return list(ActivityLog.objects.filter(lead=self.lead, description__startswith='Site location')
                    .order_by('id').values_list('description', flat=True))

    def test_the_bde_pins_the_site_from_the_device(self):
        r = self.pin()
        self.assertEqual(r.status_code, 200, r.content[:300])
        d = r.json()
        # Rounded to the six places the columns keep, and whole metres.
        self.assertEqual((d['site_latitude'], d['site_longitude']), ('10.016789', '76.345679'))
        self.assertEqual((d['site_location_accuracy'], d['site_location_source']), (13, 'gps'))
        self.assertEqual(d['site_location_captured_by'], self.bde.id)
        self.assertEqual(d['site_location_captured_by_name'], 'Anandu K')
        self.assertIsNotNone(d['site_location_captured_at'])
        self.sv.refresh_from_db()
        self.assertEqual((self.sv.site_latitude, self.sv.site_longitude),
                         (Decimal('10.016789'), Decimal('76.345679')))

    def test_the_pin_goes_on_the_lead_timeline(self):
        self.pin()
        self.assertEqual(self.location_lines(), [
            "Site location pinned from the device's location (±13 m): 10.016789, 76.345679."])

    def test_entered_by_hand(self):
        r = self.pin(lat='9.9312', lng='76.2673', accuracy=None, source='manual')
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertIsNone(r.json()['site_location_accuracy'])
        self.assertEqual(self.location_lines(), ["Site location pinned by hand: 9.931200, 76.267300."])

    def test_saving_the_rest_of_the_form_leaves_the_pin_alone(self):
        self.pin()
        self.sv.refresh_from_db()
        pinned_at = self.sv.site_location_captured_at
        r = self.patch({'roof_type': 'sheet', 'plant_capacity': '6 kW', 'product_price': '0', 'discount': '0'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.sv.refresh_from_db()
        self.assertEqual(self.sv.roof_type, 'sheet')
        self.assertEqual((self.sv.site_latitude, self.sv.site_location_captured_at),
                         (Decimal('10.016789'), pinned_at))
        self.assertEqual(len(self.location_lines()), 1)

    def test_pinning_again_moves_it(self):
        self.pin()
        r = self.pin(lat=10.02, lng=76.35, accuracy=5)
        self.assertEqual((r.json()['site_latitude'], r.json()['site_location_accuracy']), ('10.020000', 5))
        self.assertEqual(self.location_lines()[-1],
                         "Site location updated from the device's location (±5 m): 10.020000, 76.350000.")

    def test_removing_the_pin_clears_who_and_when(self):
        self.pin()
        # Cleared boxes arrive as "" as readily as null.
        r = self.patch({'site_latitude': '', 'site_longitude': ''})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.sv.refresh_from_db()
        self.assertEqual((self.sv.site_latitude, self.sv.site_longitude, self.sv.site_location_accuracy,
                          self.sv.site_location_source, self.sv.site_location_captured_at,
                          self.sv.site_location_captured_by), (None, None, None, '', None, None))
        self.assertEqual(self.location_lines()[-1], "Site location removed.")

    def test_removing_a_pin_that_is_not_there_says_nothing(self):
        r = self.patch({'site_latitude': None, 'site_longitude': None})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(self.location_lines(), [])

    def test_who_and_when_cannot_be_sent(self):
        r = self.patch({'site_latitude': 10.5, 'site_longitude': 76.5, 'site_location_source': 'manual',
                        'site_location_captured_by': self.other_bde.id,
                        'site_location_captured_at': '2020-01-01T00:00:00Z'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.sv.refresh_from_db()
        self.assertEqual(self.sv.site_location_captured_by, self.bde)
        self.assertGreater(self.sv.site_location_captured_at.year, 2020)

    def test_a_pin_needs_both_halves(self):
        r = self.patch({'site_latitude': 10.5})
        self.assertEqual(r.status_code, 400)
        self.assertIn('site_latitude', r.json())
        self.sv.refresh_from_db()
        self.assertIsNone(self.sv.site_latitude)

    def test_it_has_to_be_on_the_globe(self):
        self.assertIn('site_latitude', self.pin(lat=95, lng=76).json())
        self.assertIn('site_longitude', self.pin(lat=10, lng=200).json())
        self.assertEqual(self.pin(lat='north', lng=76).status_code, 400)
        self.sv.refresh_from_db()
        self.assertIsNone(self.sv.site_latitude)

    def test_zero_zero_is_refused(self):
        # What a device can report with no fix at all — a point in the Atlantic.
        r = self.pin(lat=0, lng=0)
        self.assertEqual(r.status_code, 400)
        self.assertIn('site_latitude', r.json())

    def test_only_those_who_may_edit_the_site_visit(self):
        # can_edit_site_visit, unchanged: another BDE or a tele caller off the
        # lead is refused outright, or does not even find it. (The roles that
        # see every lead — project managers among them — may correct it.)
        caller = mk('svl_caller', 'tele_caller')
        self.assertIn(self.pin(user=self.other_bde).status_code, (403, 404))
        self.assertIn(self.pin(user=caller).status_code, (403, 404))
        self.sv.refresh_from_db()
        self.assertIsNone(self.sv.site_latitude)

    def test_the_pages_carry_what_copy_customer_details_needs(self):
        # The address falls back to the place and district when no
        # installation location was written down.
        self.lead.company, self.lead.district = 'Kakkanad', 'Ernakulam'
        self.lead.save()
        self.lead.refresh_from_db()
        for path, user in (('project-detail', self.pm), ('purchase-detail', self.purchase)):
            r = self.client.get(f'/api/leads/{self.lead.id}/{path}/', HTTP_AUTHORIZATION=token_for(user))
            self.assertEqual(r.status_code, 200, (path, r.content[:300]))
            d = r.json()
            self.assertEqual((d['phone'], d['location'], d['district'], d['installation_location']),
                             ('9496418300', 'Kakkanad', self.lead.district, ''), path)
            self.assertEqual((d['site_visit']['plant_capacity'], d['site_visit']['roof_type']), ('5 kW', 'rcc'), path)

    def test_it_reaches_the_project_and_purchase_pages(self):
        self.pin()
        for path, user in (('project-detail', self.pm), ('purchase-detail', self.purchase)):
            r = self.client.get(f'/api/leads/{self.lead.id}/{path}/', HTTP_AUTHORIZATION=token_for(user))
            self.assertEqual(r.status_code, 200, (path, r.content[:300]))
            sv = r.json()['site_visit']
            self.assertEqual((sv['site_latitude'], sv['site_longitude'], sv['site_location_accuracy'],
                              sv['site_location_source'], sv['site_location_captured_by_name']),
                             ('10.016789', '76.345679', 13, 'gps', 'Anandu K'), path)
