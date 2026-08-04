"""Proforma invoice: numbering, the printed figures, and sending it out."""
import json
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
    """Retail is EF/<financial year>/PI<seq>; wholesale is its own REN series."""

    def test_financial_year_runs_april_to_march(self):
        from datetime import date
        self.assertEqual(StockQuote.financial_year(date(2026, 7, 24)), '26-27')
        self.assertEqual(StockQuote.financial_year(date(2026, 3, 31)), '25-26')
        self.assertEqual(StockQuote.financial_year(date(2026, 4, 1)), '26-27')

    def test_numbers_run_in_sequence_within_the_year(self):
        from datetime import date
        a = StockQuote.objects.create(quote_date=date(2026, 7, 24))
        b = StockQuote.objects.create(quote_date=date(2026, 8, 1))
        self.assertEqual(a.number, 'REN2627-PI001')
        self.assertEqual(b.number, 'REN2627-PI002')

    def test_the_sequence_restarts_each_financial_year(self):
        from datetime import date
        StockQuote.objects.create(quote_date=date(2026, 2, 1))     # FY 25-26
        nxt = StockQuote.objects.create(quote_date=date(2026, 5, 1))  # FY 26-27
        self.assertEqual(nxt.number, 'REN2627-PI001')

    def test_retail_and_wholesale_number_separately(self):
        """The wholesale documents carry their own REN series, so the two sides
        count independently — the numbers can never collide because the prefixes
        differ."""
        from datetime import date
        a = StockQuote.objects.create(quote_date=date(2026, 7, 1))
        b = Quote.objects.create(quote_date=date(2026, 7, 2))
        c = StockQuote.objects.create(quote_date=date(2026, 7, 3))
        d = Quote.objects.create(quote_date=date(2026, 7, 4))
        self.assertEqual([a.number, c.number], ['REN2627-PI001', 'REN2627-PI002'])
        self.assertEqual([b.number, d.number], ['EF/26-27/PI001', 'EF/26-27/PI002'])

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
        self.admin = mk('pf_admin', 'superadmin')
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

    def test_the_customers_state_and_address_reach_both_blocks(self):
        """Entered once on the customer, printed on Billed To and Shipped to."""
        r = self.client.patch(f'/api/stock-customers/{self.customer.id}/',
                              {'state': 'Tamil Nadu', 'site_address': 'Hosur Road, Salem'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        d = self.get()
        self.assertEqual(d['customer']['state'], 'Tamil Nadu')
        self.assertEqual(d['customer']['address'], 'Hosur Road, Salem')
        self.assertEqual(d['ship_to']['state'], 'Tamil Nadu')
        self.assertEqual(d['ship_to']['address'], 'Hosur Road, Salem')

    def test_ship_to_state_and_gstin_can_be_overridden_per_invoice(self):
        """Goods often go somewhere other than the registered address, so the
        delivery block is captured on the invoice and wins over the customer."""
        r = self.client.patch(f'/api/stock-quotes/{self.quote.id}/', {
            'site': 'Plot 4, Hosur Road', 'ship_to_state': 'Tamil Nadu',
            'ship_to_gstin': '33AAWFD1840P1ZZ',
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        d = self.get()
        self.assertEqual(d['ship_to']['address'], 'Plot 4, Hosur Road')
        self.assertEqual(d['ship_to']['state'], 'Tamil Nadu')
        self.assertEqual(d['ship_to']['gstin'], '33AAWFD1840P1ZZ')
        # Billed To is untouched by the delivery override.
        self.assertEqual(d['customer']['state'], 'Kerala')
        self.assertEqual(d['customer']['gstin'], '32AAWFD1840P1ZZ')

    def test_a_blank_ship_to_falls_back_to_the_customer(self):
        d = self.get()
        self.assertEqual(d['ship_to']['state'], self.customer.state)
        self.assertEqual(d['ship_to']['gstin'], self.customer.gstin)

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
        self.admin = mk('ps_admin', 'superadmin')
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
        self.admin = mk('hsn_admin', 'superadmin')
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


class DispatchInvoiceTests(TestCase):
    """The dispatch invoice is the proforma's form with the wording changed."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='invoice-test-')
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    def setUp(self):
        from .models import StockDispatch
        self.admin = mk('di_admin', 'superadmin')
        self.customer = StockCustomer.objects.create(
            name='Adya Global', gstin='32AAWFD1840P1ZZ', state='Kerala',
            site_address='Kowdiar, Thiruvananthapuram', contact_number='9876543210')
        self.panel = StockItem.objects.create(code='DI-PANEL', category='Solar Panel',
                                              brand='Adani', model_name='545 wp',
                                              unit='NOS', hsn='85414300')
        self.inv = StockItem.objects.create(code='DI-INV', category='Inverter',
                                            brand='Deye', model_name='10kW',
                                            unit='NOS', hsn='85044090')
        # One delivery of two products: two rows sharing an invoice number.
        common = dict(invoice_no='INV-S001', date=timezone.localdate(),
                      customer=self.customer, tax_percent=Decimal('18'), site='Site A')
        self.row1 = StockDispatch.objects.create(
            item=self.panel, quantity=Decimal('2'), rate=Decimal('100'),
            serial_numbers='SN-001, SN-002', **common)
        self.row2 = StockDispatch.objects.create(
            item=self.inv, quantity=Decimal('1'), rate=Decimal('500'), **common)

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def get(self, row=None):
        r = self.client.get(f'/api/stock-dispatches/{(row or self.row1).id}/invoice/', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def test_it_is_titled_invoice_not_proforma(self):
        d = self.get()
        self.assertEqual(d['title'], 'INVOICE')
        self.assertEqual(d['label'], 'Invoice')
        self.assertNotIn('Proforma', json.dumps(d))

    def test_every_product_on_the_invoice_number_is_billed_once(self):
        """Two rows sharing a number are one document, whichever row is asked."""
        for row in (self.row1, self.row2):
            d = self.get(row)
            self.assertEqual(len(d['lines']), 2, f'from row {row.id}')
            self.assertEqual([l['particulars'] for l in d['lines']],
                             ['Adani 545 wp', 'Deye 10kW'])

    def test_serial_numbers_reach_the_printed_line(self):
        d = self.get()
        self.assertEqual(d['lines'][0]['serials'], 'SN-001, SN-002')
        self.assertEqual(d['lines'][1]['serials'], '')

    def test_the_figures_match_the_dispatched_rows(self):
        d = self.get()
        self.assertEqual(Decimal(d['lines'][0]['taxable']), Decimal('200.00'))   # 2 × 100
        self.assertEqual(Decimal(d['lines'][1]['taxable']), Decimal('500.00'))
        self.assertEqual(Decimal(d['totals']['taxable']), Decimal('700.00'))
        self.assertEqual(Decimal(d['totals']['tax']), Decimal('126.00'))         # 18%
        self.assertEqual(Decimal(d['totals']['invoice_value']), Decimal('826.00'))

    def test_the_hsn_summary_splits_per_code(self):
        rows = {r['hsn']: r for r in self.get()['hsn_summary']}
        self.assertEqual(set(rows), {'85414300', '85044090'})
        self.assertEqual(Decimal(rows['85414300']['cgst']), Decimal('18.00'))    # 36 / 2
        self.assertEqual(Decimal(rows['85044090']['cgst']), Decimal('45.00'))    # 90 / 2

    def test_a_row_saved_on_its_own_gets_its_own_invoice(self):
        """Every dispatch is numbered from the invoice series on save, so a row
        saved by itself is a one-line invoice rather than an unnumbered stray."""
        from .models import StockDispatch
        loose = StockDispatch.objects.create(item=self.panel, quantity=Decimal('1'),
                                             rate=Decimal('10'), date=timezone.localdate())
        self.assertTrue(loose.invoice_no.startswith('REN'), loose.invoice_no)
        d = self.get(loose)
        self.assertEqual(len(d['lines']), 1)
        self.assertEqual(d['invoice']['number'], loose.invoice_no)

    def test_the_customer_fills_both_address_blocks(self):
        d = self.get()
        self.assertEqual(d['customer']['name'], 'Adya Global')
        self.assertEqual(d['customer']['state'], 'Kerala')
        self.assertEqual(d['ship_to']['address'], 'Site A')      # the delivery site

    def test_sending_stores_the_invoice_against_the_group(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'sent', 'error': ''})()
            r = self.client.post(f'/api/stock-dispatches/{self.row2.id}/send/', {
                'pdf': SimpleUploadedFile('i.pdf', b'%PDF-1.4 x', content_type='application/pdf'),
                'channels': 'email', 'email': 'buyer@example.com',
            }, **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(send.call_args.kwargs['subject'], 'Invoice INV-S001')
        # Stored on the first row of the group, so either row finds it again.
        self.row1.refresh_from_db()
        self.assertTrue(self.row1.pdf)

    def test_sending_without_an_address_is_reported(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        r = self.client.post(f'/api/stock-dispatches/{self.row1.id}/send/', {
            'pdf': SimpleUploadedFile('i.pdf', b'%PDF', content_type='application/pdf'),
            'channels': 'email', 'email': '',
        }, **self.auth())
        self.assertEqual(r.status_code, 502)
        self.assertIn('No email address', r.json()['error'])


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
        self.admin = mk('rp_admin', 'superadmin')
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

    def test_retail_ship_to_details_are_kept_on_the_invoice(self):
        """A retail lead carries no state or GSTIN, so the delivery block is
        typed on the invoice and has to survive the round trip."""
        r = self.client.patch(f'/api/quotes/{self.quote.id}/', {
            'ship_to_state': 'Kerala', 'ship_to_gstin': '32AAWFD1840P1ZZ',
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        d = self.get()
        self.assertEqual(d['ship_to']['state'], 'Kerala')
        self.assertEqual(d['ship_to']['gstin'], '32AAWFD1840P1ZZ')

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


class InventoryDocumentProfileTests(TestCase):
    """Settings → Inventory Documents: retail and wholesale print their own
    letterhead, and a blank field falls back to the organisation's setting."""

    def setUp(self):
        from organization.models import InventoryDocumentProfile
        from organization.utils import get_org_settings
        self.admin = mk('doc_admin', 'superadmin')
        self.org = get_org_settings()
        self.org.warranty_company_name = 'Energyfox Consultants Pvt. Ltd.'
        self.org.warranty_gst = '32AAHCE8716F1ZR'
        self.org.warranty_cin = 'U35105KL2023PTC084535'
        self.org.receipt_address = '4th Floor, Pattom, Thiruvananthapuram'
        self.org.receipt_phone = '9526 396 823'
        self.org.save()
        self.Profile = InventoryDocumentProfile

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def get_profiles(self):
        r = self.client.get('/api/inventory-documents/', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def test_both_sides_default_to_the_organisation_settings(self):
        d = self.get_profiles()
        for side in ('b2c', 'b2b'):
            eff = d[side]['effective']
            self.assertEqual(eff['name'], 'Energyfox Consultants Pvt. Ltd.')
            self.assertEqual(eff['gst'], '32AAHCE8716F1ZR')
            self.assertEqual(eff['phone'], '9526 396 823')
            # The PAN is the middle ten characters of the GSTIN.
            self.assertEqual(eff['pan'], 'AAHCE8716F')

    def test_a_side_can_be_configured_on_its_own(self):
        r = self.client.patch('/api/inventory-documents/',
                              data={'side': 'b2b', 'company_name': 'Renewfox Wholesale LLP',
                                    'gst': '32XXXXX1111Z1Z9'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        d = self.get_profiles()
        self.assertEqual(d['b2b']['effective']['name'], 'Renewfox Wholesale LLP')
        self.assertEqual(d['b2b']['effective']['pan'], 'XXXXX1111Z')   # from the new GSTIN
        # Retail is untouched.
        self.assertEqual(d['b2c']['effective']['name'], 'Energyfox Consultants Pvt. Ltd.')

    def test_a_blank_field_keeps_falling_back(self):
        self.client.patch('/api/inventory-documents/',
                          data={'side': 'b2b', 'company_name': 'Renewfox Wholesale LLP'},
                          content_type='application/json', **self.auth())
        eff = self.get_profiles()['b2b']['effective']
        self.assertEqual(eff['name'], 'Renewfox Wholesale LLP')   # set
        self.assertEqual(eff['phone'], '9526 396 823')            # not set → org's

    def test_only_an_admin_may_change_them(self):
        staff = mk('doc_staff', 'accounts_staff')
        r = self.client.patch('/api/inventory-documents/',
                              data={'side': 'b2b', 'company_name': 'Nope'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(staff))
        self.assertEqual(r.status_code, 403)

    def test_an_unknown_side_is_refused(self):
        r = self.client.patch('/api/inventory-documents/',
                              data={'side': 'b2x', 'company_name': 'Nope'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 400)

    def test_the_wholesale_documents_print_the_b2b_profile(self):
        """The three B2B documents read the wholesale letterhead; the retail
        proforma keeps the B2C one."""
        from .models import StockQuote, StockQuoteItem, StockCustomer, StockItem, StockPurchaseOrder, Vendor
        self.Profile.objects.update_or_create(side='b2b',
                                              defaults={'company_name': 'Renewfox Wholesale LLP'})
        customer = StockCustomer.objects.create(name='Adya Global')
        item = StockItem.objects.create(code='DP-1', category='Solar Panel', opening_stock=10)
        quote = StockQuote.objects.create(customer=customer, quote_date=timezone.localdate())
        StockQuoteItem.objects.create(quote=quote, item=item, quantity=1, unit_price=Decimal('100'))
        vendor = Vendor.objects.create(name='Ensun')
        po = StockPurchaseOrder.objects.create(supplier=vendor, po_date=timezone.localdate())

        for url in (f'/api/stock-quotes/{quote.id}/proforma/',
                    f'/api/stock-purchase-orders/{po.id}/document/'):
            d = self.client.get(url, **self.auth()).json()
            self.assertEqual(d['company']['name'], 'Renewfox Wholesale LLP', url)

        from leads.models import Lead
        from .models import Quote, QuoteItem
        lead = Lead.objects.create(first_name='Retail', last_name='Buyer', phone='9990004321')
        rq = Quote.objects.create(lead=lead, quote_date=timezone.localdate())
        d = self.client.get(f'/api/quotes/{rq.id}/proforma/', **self.auth()).json()
        self.assertEqual(d['company']['name'], 'Energyfox Consultants Pvt. Ltd.')


class ProformaSendLandsOnTheLeadTimelineTests(TestCase):
    """A retail proforma is raised against a lead, so sending it belongs on that
    customer's Activity Timeline. The wholesale documents have no lead to
    record against — they are raised on a stock customer or a supplier."""

    def setUp(self):
        from leads.models import Lead
        self.admin = mk('pt_admin', 'superadmin')
        self.lead = Lead.objects.create(first_name='Retail', last_name='Buyer',
                                        phone='9990007777', email='buyer@example.com')
        self.quote = Quote.objects.create(lead=self.lead, quote_date=timezone.localdate())
        QuoteItem.objects.create(quote=self.quote, description='5kW system',
                                 quantity=1, unit_price=Decimal('225000'))

    @staticmethod
    def _pdf():
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('q.pdf', b'%PDF-1.4 q', content_type='application/pdf')

    def entries(self):
        r = self.client.get(f'/api/leads/{self.lead.id}/activity-timeline/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return [e['description'] for e in r.json()['entries']]

    def test_an_emailed_proforma_is_recorded(self):
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'sent', 'error': ''})()
            r = self.client.post(f'/api/quotes/{self.quote.id}/send/',
                                 {'pdf': self._pdf(), 'channels': 'email',
                                  'email': 'buyer@example.com'},
                                 HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(any(self.quote.number in e and 'buyer@example.com' in e
                            for e in self.entries()), self.entries())

    def test_a_failed_send_is_not_recorded(self):
        from leads.models import ActivityLog
        before = ActivityLog.objects.filter(lead=self.lead).count()
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'failed', 'error': 'SMTP refused'})()
            self.client.post(f'/api/quotes/{self.quote.id}/send/',
                             {'pdf': self._pdf(), 'channels': 'email',
                              'email': 'buyer@example.com'},
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(ActivityLog.objects.filter(lead=self.lead).count(), before)

    def test_a_wholesale_send_has_no_lead_to_record_against(self):
        """It must not raise looking for one."""
        from .models import StockQuote, StockQuoteItem, StockCustomer, StockItem
        customer = StockCustomer.objects.create(name='Adya Global')
        item = StockItem.objects.create(code='PT-1', category='Solar Panel', opening_stock=5)
        sq = StockQuote.objects.create(customer=customer, quote_date=timezone.localdate())
        StockQuoteItem.objects.create(quote=sq, item=item, quantity=1, unit_price=Decimal('100'))
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'sent', 'error': ''})()
            r = self.client.post(f'/api/stock-quotes/{sq.id}/send/',
                                 {'pdf': self._pdf(), 'channels': 'email',
                                  'email': 'trade@example.com'},
                                 HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
