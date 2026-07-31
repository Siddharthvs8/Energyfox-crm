"""Proforma invoice: numbering, the printed figures, and sending it out."""
import shutil
import tempfile
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from .models import (Quote, QuoteItem, StockItem, StockCustomer, StockQuote,
                     StockQuoteItem)


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456')
    u.role = role
    u.save()
    return u


class ProformaNumberingTests(TestCase):
    """EF/<financial year>/PI<seq>, matching the printed document."""

    def test_financial_year_runs_april_to_march(self):
        from datetime import date
        self.assertEqual(StockQuote.financial_year(date(2026, 7, 24)), '26-27')
        self.assertEqual(StockQuote.financial_year(date(2026, 3, 31)), '25-26')
        self.assertEqual(StockQuote.financial_year(date(2026, 4, 1)), '26-27')

    def test_numbers_run_in_sequence_within_the_year(self):
        from datetime import date
        a = StockQuote.objects.create(quote_date=date(2026, 7, 24))
        b = StockQuote.objects.create(quote_date=date(2026, 8, 1))
        self.assertEqual(a.number, 'EF/26-27/PI001')
        self.assertEqual(b.number, 'EF/26-27/PI002')

    def test_the_sequence_restarts_each_financial_year(self):
        from datetime import date
        StockQuote.objects.create(quote_date=date(2026, 2, 1))     # FY 25-26
        nxt = StockQuote.objects.create(quote_date=date(2026, 5, 1))  # FY 26-27
        self.assertEqual(nxt.number, 'EF/26-27/PI001')

    def test_retail_and_wholesale_share_one_series(self):
        """Both modules issue proforma invoices; two documents must never carry
        the same number, so the sequence spans both tables."""
        from datetime import date
        a = StockQuote.objects.create(quote_date=date(2026, 7, 1))
        b = Quote.objects.create(quote_date=date(2026, 7, 2))
        c = StockQuote.objects.create(quote_date=date(2026, 7, 3))
        d = Quote.objects.create(quote_date=date(2026, 7, 4))
        self.assertEqual([a.number, b.number, c.number, d.number],
                         ['EF/26-27/PI001', 'EF/26-27/PI002',
                          'EF/26-27/PI003', 'EF/26-27/PI004'])

    def test_deleting_one_does_not_reissue_a_live_number(self):
        """A count alone would hand PI002 out twice after PI001 is deleted."""
        from datetime import date
        first = Quote.objects.create(quote_date=date(2026, 6, 1))
        second = Quote.objects.create(quote_date=date(2026, 6, 2))
        first.delete()
        third = Quote.objects.create(quote_date=date(2026, 6, 3))
        self.assertNotEqual(third.number, second.number)
        self.assertEqual(third.number, 'EF/26-27/PI003')


class ProformaDocumentTests(TestCase):
    """The figures the PDF prints come from the server, so they can't drift."""

    @classmethod
    def setUpClass(cls):
        # This class writes a logo onto the org record; keep it out of the
        # project's media directory.
        cls._media = tempfile.mkdtemp(prefix='proforma-doc-')
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    def setUp(self):
        self.admin = mk('pf_admin', 'admin')
        self.customer = StockCustomer.objects.create(
            name='DAYLIGHT ENERGIES', gstin='32AAWFD1840P1ZZ', state='Kerala',
            site_address='Indira Nagar Main Road, Vazhayila, Thiruvananthapuram - 695005',
            contact_number='9876543210')
        self.item = StockItem.objects.create(code='ADANI-545', category='Solar Panel',
                                             brand='Adani', model_name='545 wp',
                                             unit='NOS', hsn='85414300')
        # The worked example from the printed invoice: 13 × 15,260 @ 5% GST.
        self.quote = StockQuote.objects.create(customer=self.customer, tax_percent=Decimal('5'),
                                               quote_date=timezone.localdate(),
                                               efc_ref_no='REF-1')
        StockQuoteItem.objects.create(quote=self.quote, item=self.item,
                                      description='Adani 545 wp',
                                      quantity=Decimal('13'), unit_price=Decimal('15260'))

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def get(self):
        r = self.client.get(f'/api/stock-quotes/{self.quote.id}/proforma/', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def test_line_carries_hsn_unit_and_its_own_tax(self):
        d = self.get()
        line = d['lines'][0]
        self.assertEqual(line['hsn'], '85414300')
        self.assertEqual(line['unit'], 'NOS')
        self.assertEqual(line['particulars'], 'Adani 545 wp')
        self.assertEqual(Decimal(line['taxable']), Decimal('198380.00'))   # 13 × 15,260
        self.assertEqual(Decimal(line['tax']), Decimal('9919.00'))         # 5%
        self.assertEqual(Decimal(line['total']), Decimal('208299.00'))

    def test_hsn_summary_splits_gst_into_cgst_and_sgst(self):
        d = self.get()
        row = d['hsn_summary'][0]
        self.assertEqual(row['hsn'], '85414300')
        self.assertEqual(Decimal(row['taxable']), Decimal('198380.00'))
        self.assertEqual(Decimal(row['cgst']), Decimal('4959.50'))
        self.assertEqual(Decimal(row['sgst']), Decimal('4959.50'))
        # The two halves add back to the line's tax.
        self.assertEqual(Decimal(row['cgst']) + Decimal(row['sgst']), Decimal('9919.00'))

    def test_totals_and_amount_in_words(self):
        d = self.get()
        self.assertEqual(Decimal(d['totals']['grand_total']), Decimal('208299'))
        self.assertIn('Two Lakh', d['totals']['in_words'])
        self.assertIn('Rupees', d['totals']['in_words'])

    def test_both_address_blocks_are_filled(self):
        d = self.get()
        self.assertEqual(d['customer']['name'], 'DAYLIGHT ENERGIES')
        self.assertEqual(d['customer']['gstin'], '32AAWFD1840P1ZZ')
        self.assertEqual(d['customer']['state'], 'Kerala')
        # Ship-to falls back to the billing address when no site is given.
        self.assertEqual(d['ship_to']['address'], self.customer.site_address)
        self.quote.site = 'Site B, Kollam'
        self.quote.save(update_fields=['site'])
        self.assertEqual(self.get()['ship_to']['address'], 'Site B, Kollam')

    def test_company_and_bank_blocks_come_from_settings(self):
        d = self.get()
        self.assertTrue(d['company']['name'])
        self.assertTrue(d['company']['gst'])
        # PAN is the middle ten characters of the GSTIN.
        self.assertEqual(d['company']['pan'], d['company']['gst'][2:12])
        self.assertTrue(d['bank']['ifsc'])
        self.assertEqual(d['invoice']['efc_ref_no'], 'REF-1')

    def test_artwork_is_inlined_not_linked(self):
        """The PDF is drawn in the browser, so a media URL would be a
        cross-origin fetch once hosted — and the logo would vanish."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from organization.utils import get_org_settings
        png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
               b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00'
               b'\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
        org = get_org_settings()
        org.logo.save('logo.png', SimpleUploadedFile('logo.png', png, content_type='image/png'),
                      save=True)
        try:
            logo = self.get()['company']['logo']
            self.assertTrue(logo.startswith('data:image/png;base64,'), logo[:40])
        finally:
            org.logo.delete(save=True)

    def test_a_missing_logo_file_does_not_break_the_document(self):
        """A record pointing at a file that isn't there must still render."""
        from organization.utils import get_org_settings
        org = get_org_settings()
        org.logo.name = 'org/does-not-exist.png'
        org.save(update_fields=['logo'])
        try:
            r = self.client.get(f'/api/stock-quotes/{self.quote.id}/proforma/', **self.auth())
            self.assertEqual(r.status_code, 200)
        finally:
            org.logo.name = ''
            org.save(update_fields=['logo'])

    def test_a_blank_document_still_renders(self):
        """An invoice with no lines must not 500 — the PDF draws empty rows."""
        empty = StockQuote.objects.create(quote_date=timezone.localdate())
        r = self.client.get(f'/api/stock-quotes/{empty.id}/proforma/', **self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['lines'], [])
        self.assertEqual(Decimal(r.json()['totals']['grand_total']), Decimal('0'))


class ProformaSendTests(TestCase):
    """Sending stores the PDF, so keep the uploads out of the project's media dir."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='proforma-test-')
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    def setUp(self):
        self.admin = mk('ps_admin', 'admin')
        self.bde = mk('ps_bde', 'bde')
        self.customer = StockCustomer.objects.create(name='Daylight', contact_number='9876543210')
        self.item = StockItem.objects.create(code='PS-1', category='Solar Panel', unit='NOS')
        self.quote = StockQuote.objects.create(customer=self.customer, quote_date=timezone.localdate())
        StockQuoteItem.objects.create(quote=self.quote, item=self.item,
                                      quantity=Decimal('1'), unit_price=Decimal('100'))

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.admin)}

    @staticmethod
    def pdf_file():
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('pi.pdf', b'%PDF-1.4 fake', content_type='application/pdf')

    def test_sending_by_email_stores_the_pdf_and_marks_it_sent(self):
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'sent', 'error': ''})()
            r = self.client.post(f'/api/stock-quotes/{self.quote.id}/send/', {
                'pdf': self.pdf_file(), 'channels': 'email', 'email': 'buyer@example.com',
            }, **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['sent']['email'], 'sent')
        self.quote.refresh_from_db()
        self.assertTrue(self.quote.pdf)
        self.assertEqual(self.quote.status, 'sent')          # draft → sent
        # The stored filename can't contain the number's slashes.
        self.assertNotIn('/', self.quote.pdf.name.split('/')[-1].replace('.pdf', '').replace('-', ''))

    def test_sending_by_whatsapp_sends_a_document_link(self):
        with patch('messaging.whatsapp.send_document') as send:
            send.return_value = 'wamid.1'
            r = self.client.post(f'/api/stock-quotes/{self.quote.id}/send/', {
                'pdf': self.pdf_file(), 'channels': 'whatsapp', 'phone': '9876543210',
            }, **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['sent']['whatsapp'], 'sent')
        kwargs = send.call_args.kwargs
        self.assertEqual(kwargs['to'], '9876543210')
        self.assertTrue(kwargs['link'].startswith('http'))
        self.assertTrue(kwargs['filename'].endswith('.pdf'))

    def test_a_missing_address_is_reported_not_silently_skipped(self):
        r = self.client.post(f'/api/stock-quotes/{self.quote.id}/send/', {
            'pdf': self.pdf_file(), 'channels': 'email', 'email': '',
        }, **self.auth())
        self.assertEqual(r.status_code, 502)
        self.assertIn('No email address', r.json()['error'])
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'draft')         # not marked sent

    def test_sending_without_a_document_is_refused(self):
        r = self.client.post(f'/api/stock-quotes/{self.quote.id}/send/',
                             {'channels': 'email', 'email': 'a@b.com'}, **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertIn('No document', r.json()['error'])

    def test_the_stock_audience_still_gates_it(self):
        r = self.client.get(f'/api/stock-quotes/{self.quote.id}/proforma/', **self.auth(self.bde))
        self.assertEqual(r.status_code, 403)


class HsnPlumbingTests(TestCase):
    """HSN is entered once in Item Master and has to reach every document."""

    def setUp(self):
        from leads.models import Product
        self.admin = mk('hsn_admin', 'admin')
        self.product = Product.objects.create(name='Waaree 540w', unit='Nos', hsn='85414300')
        self.item = StockItem.objects.create(code='HSN-1', category='Solar Panel',
                                             unit='NOS', hsn='85414300')

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def test_item_master_round_trips_hsn(self):
        """Both catalogues accept and return it, so the field is editable."""
        r = self.client.patch(f'/api/stock-items/{self.item.id}/',
                              {'hsn': '85044090'}, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['hsn'], '85044090')

        r = self.client.patch(f'/api/products/{self.product.id}/',
                              {'hsn': '85044090'}, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['hsn'], '85044090')

    def test_purchase_order_lines_carry_hsn_and_unit(self):
        """The PO print-out is a GST document, so its lines need them too."""
        from .models import PurchaseOrder, PurchaseOrderItem
        po = PurchaseOrder.objects.create()
        PurchaseOrderItem.objects.create(purchase_order=po, product=self.product,
                                         quantity=Decimal('2'), unit_price=Decimal('100'))
        r = self.client.get(f'/api/purchase-orders/{po.id}/', **self.auth())
        self.assertEqual(r.status_code, 200)
        line = r.json()['items'][0]
        self.assertEqual(line['product_hsn'], '85414300')
        self.assertEqual(line['product_unit'], 'Nos')

    def test_a_line_with_no_catalogue_product_still_serialises(self):
        """Free-text lines have no product behind them; that must not 500."""
        from .models import PurchaseOrder, PurchaseOrderItem
        po = PurchaseOrder.objects.create()
        PurchaseOrderItem.objects.create(purchase_order=po, product=None,
                                         description='Site labour', quantity=Decimal('1'))
        r = self.client.get(f'/api/purchase-orders/{po.id}/', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['items'][0]['product_hsn'], '')

    def test_stock_movements_expose_the_item_hsn(self):
        from .models import StockDispatch
        d = StockDispatch.objects.create(item=self.item, quantity=Decimal('1'),
                                         rate=Decimal('10'), date=timezone.localdate())
        r = self.client.get(f'/api/stock-dispatches/{d.id}/', **self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['item_hsn'], '85414300')


class RetailProformaTests(TestCase):
    """The B2C module prints the same document off the product catalogue."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='proforma-retail-')
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    def setUp(self):
        from leads.models import Lead, Product
        self.admin = mk('rp_admin', 'admin')
        self.lead = Lead.objects.create(
            first_name='Anil', last_name='Kumar', email='anil@example.com',
            phone='9876500000', installation_location='Kowdiar, Thiruvananthapuram')
        self.product = Product.objects.create(name='Waaree 540w', unit='Nos',
                                              hsn='85414300', default_price=Decimal('20000'))
        self.quote = Quote.objects.create(lead=self.lead, tax_percent=Decimal('18'),
                                          quote_date=timezone.localdate(), efc_ref_no='R-1')
        QuoteItem.objects.create(quote=self.quote, product=self.product,
                                 quantity=Decimal('10'), unit_price=Decimal('20000'))

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def get(self):
        r = self.client.get(f'/api/quotes/{self.quote.id}/proforma/', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def test_it_numbers_in_the_proforma_series(self):
        self.assertTrue(self.quote.number.startswith('EF/'), self.quote.number)
        self.assertIn('/PI', self.quote.number)

    def test_the_lead_becomes_the_billed_party(self):
        d = self.get()
        self.assertEqual(d['customer']['name'], 'Anil Kumar')
        self.assertEqual(d['customer']['contact_number'], '9876500000')
        self.assertEqual(d['customer']['address'], 'Kowdiar, Thiruvananthapuram')
        self.assertEqual(d['ship_to']['address'], 'Kowdiar, Thiruvananthapuram')

    def test_lines_carry_the_product_hsn_and_unit(self):
        d = self.get()
        line = d['lines'][0]
        self.assertEqual(line['particulars'], 'Waaree 540w')
        self.assertEqual(line['hsn'], '85414300')
        self.assertEqual(line['unit'], 'Nos')
        self.assertEqual(Decimal(line['taxable']), Decimal('200000.00'))
        self.assertEqual(Decimal(line['tax']), Decimal('36000.00'))

    def test_the_gst_split_matches_the_wholesale_document(self):
        row = self.get()['hsn_summary'][0]
        self.assertEqual(Decimal(row['cgst']), Decimal('18000.00'))
        self.assertEqual(Decimal(row['sgst']), Decimal('18000.00'))

    def test_totals_and_words(self):
        d = self.get()
        self.assertEqual(Decimal(d['totals']['grand_total']), Decimal('236000'))
        self.assertIn('Two Lakh Thirty Six Thousand', d['totals']['in_words'])

    def test_a_quote_with_no_lead_still_renders(self):
        orphan = Quote.objects.create(quote_date=timezone.localdate())
        r = self.client.get(f'/api/quotes/{orphan.id}/proforma/', **self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['customer']['name'], '')

    def test_sending_falls_back_to_the_leads_email(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'sent', 'error': ''})()
            r = self.client.post(f'/api/quotes/{self.quote.id}/send/', {
                'pdf': SimpleUploadedFile('pi.pdf', b'%PDF-1.4 x', content_type='application/pdf'),
                'channels': 'email',
            }, **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(send.call_args.kwargs['to'], ['anil@example.com'])
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'sent')
