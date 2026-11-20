"""Documentation Stage 1 reads the whole site visit — every field the BDE took,
the site's map pin, the photos and the documents — for the documentation staff
and the documentation manager alike."""
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Lead, LeadDocument, Product, SiteVisit, SiteVisitDocument
from .tests import mk, token_for


class DocumentationReadsTheSiteVisitTests(TestCase):

    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        overridden = override_settings(MEDIA_ROOT=media)
        overridden.enable()
        self.addCleanup(overridden.disable)

        self.staff = mk('dsv_staff', 'documentation_staff')
        self.other_staff = mk('dsv_staff2', 'documentation_staff')
        self.manager = mk('dsv_manager', 'documentation_manager')
        self.bde = mk('dsv_bde', 'bde')
        self.bde.first_name = 'Anandu'
        self.bde.save()
        product = Product.objects.create(name='5 kW On-grid', default_price=Decimal('230000'))
        self.lead = Lead.objects.create(
            first_name='Anitha', last_name='VR', phone='9496418301', status='converted', bde=self.bde,
            product=product, value=Decimal('215000'),
            pushed_to_documentation=True, pushed_to_documentation_at=timezone.now(),
            documentation_staff=self.staff)
        sv = SiteVisit.objects.create(
            lead=self.lead, site_visit_complete=True, roof_type='rcc', rcc_roof_types=['flat'],
            connection_type='residential', consumer_number='1156789012345', phase='3ph',
            plant_capacity='5 kW', structure_type='custom', custom_structure_height='2 m',
            earthing_surface='soil', loan='yes', loan_amount='250000', name_change='no',
            product_price=Decimal('230000'), discount=Decimal('15000'), po_signed_date=date(2026, 10, 10),
            kseb_feasibility_taken='yes', kseb_feasibility_date=date(2026, 10, 12),
            site_latitude=Decimal('10.016789'), site_longitude=Decimal('76.345679'),
            site_location_accuracy=12, site_location_source='gps',
            site_location_captured_at=timezone.now(), site_location_captured_by=self.bde)
        SiteVisitDocument.objects.create(
            site_visit=sv, doc_type='photo_meterbox',
            file=SimpleUploadedFile('meter.jpg', b'jpeg-bytes', content_type='image/jpeg'))
        LeadDocument.objects.create(
            lead=self.lead, kind='aadhaar',
            file=SimpleUploadedFile('aadhaar.pdf', b'%PDF-1.4', content_type='application/pdf'))

    def detail(self, user):
        return self.client.get(f'/api/leads/{self.lead.id}/documentation-detail/',
                               HTTP_AUTHORIZATION=token_for(user))

    def assert_whole_visit(self, response):
        self.assertEqual(response.status_code, 200, response.content[:300])
        sv = response.json()['site_visit']
        self.assertEqual(
            (sv['roof_type'], sv['rcc_roof_types'], sv['connection_type'], sv['consumer_number'], sv['phase']),
            ('rcc', ['flat'], 'residential', '1156789012345', '3ph'))
        self.assertEqual((sv['structure_type'], sv['custom_structure_height'], sv['earthing_surface']),
                         ('custom', '2 m', 'soil'))
        self.assertEqual((sv['loan'], sv['loan_amount'], sv['name_change']), ('yes', '250000', 'no'))
        # The deal, as purchase and project read it. (deal_value is the lead's
        # own figure, which the JSON encoder may write as a number or a string.)
        self.assertEqual((sv['product_name'], sv['product_price'], sv['discount']),
                         ('5 kW On-grid', '230000.00', '15000.00'))
        self.assertEqual(Decimal(str(sv['deal_value'])), Decimal('215000'))
        self.assertEqual((sv['po_signed_date'], sv['kseb_feasibility_taken'], sv['kseb_feasibility_date']),
                         ('2026-10-10', 'yes', '2026-10-12'))
        self.assertEqual((sv['site_latitude'], sv['site_longitude'], sv['site_location_accuracy'],
                          sv['site_location_captured_by_name']),
                         ('10.016789', '76.345679', 12, 'Anandu'))
        self.assertTrue(sv['site_visit_complete'])
        # The photos and the customer's documents, shared ones included.
        self.assertEqual(sorted(d['doc_type'] for d in sv['documents']), ['aadhaar_card', 'photo_meterbox'])
        self.assertTrue(all(d['file'] for d in sv['documents']))

    def test_the_documentation_staff_reads_the_whole_visit(self):
        self.assert_whole_visit(self.detail(self.staff))

    def test_the_documentation_manager_reads_it_too(self):
        self.assert_whole_visit(self.detail(self.manager))

    def test_staff_it_is_not_assigned_to_do_not(self):
        self.assertEqual(self.detail(self.other_staff).status_code, 403)

    def test_the_documentation_status_page_has_it_too(self):
        # The tracker the rest of the company reads ("Documentation Status"),
        # here as an admin: the same visit, the map pin and the deal included.
        admin = mk('dsv_admin', 'superadmin')
        admin.is_staff = True
        admin.save()
        r = self.client.get(f'/api/leads/{self.lead.id}/documentation-overview-detail/',
                            HTTP_AUTHORIZATION=token_for(admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        sv = r.json()['site_visit']
        self.assertEqual((sv['site_latitude'], sv['site_longitude'], sv['site_location_accuracy'],
                          sv['site_location_captured_by_name']), ('10.016789', '76.345679', 12, 'Anandu'))
        self.assertEqual((sv['phase'], sv['product_name']), ('3ph', '5 kW On-grid'))
        self.assertEqual(Decimal(str(sv['deal_value'])), Decimal('215000'))

    def test_the_documentation_view_only_reads(self):
        # The copy on Stage 1 is a read: the endpoint behind it takes no writes.
        r = self.client.patch(f'/api/leads/{self.lead.id}/documentation-detail/', {'roof_type': 'sheet'},
                              content_type='application/json', HTTP_AUTHORIZATION=token_for(self.manager))
        self.assertEqual(r.status_code, 405)
        self.assertEqual(SiteVisit.objects.get(lead=self.lead).roof_type, 'rcc')
