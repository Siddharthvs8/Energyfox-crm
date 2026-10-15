"""Stock register: the derived ledger, its dashboard figures, and who may use it."""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from leads.models import Lead
from messaging import whatsapp
from organization.models import OrgSettings
from users.models import User
from .models import (Vendor, StockItem, StockCustomer, GoodsReceipt, StockDispatch,
                     StockPurchaseOrder, StockQuote, StockQuoteItem, Quote,
                     DispatchPayment, DocumentNumberSeries, series_key,
                     ProjectSpec, Quotation)


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456')
    u.role = role
    u.save()
    return u


def paid_in_full(quote_or_id):
    """The payment body a convert needs now that dispatching is gated on it.

    Goods leave against a settled invoice, so every convert in these tests
    presents the proforma's own total. See DispatchPaymentGateTests for what
    happens when one doesn't.
    """
    q = (quote_or_id if hasattr(quote_or_id, 'total')
         else StockQuote.objects.get(pk=quote_or_id))
    return {'payment': {'amount_received': str(q.total), 'mode': 'cash',
                        'paid_on': str(timezone.localdate())}}


class StockLedgerTests(TestCase):
    """Closing stock is never stored — it is opening + received − dispatched."""

    def setUp(self):
        self.admin = mk('t_admin', 'superadmin')
        self.supplier = Vendor.objects.create(name='Waaree Energies')
        self.customer = StockCustomer.objects.create(name='Green Fields Resort')
        self.panel = StockItem.objects.create(
            code='SOL-PNL-540', category='Solar Panel', brand='Waaree', model_name='540W',
            unit='Nos', opening_stock=100, unit_cost=Decimal('9800'), reorder_level=20)

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def receive(self, qty, rate='9750'):
        return GoodsReceipt.objects.create(item=self.panel, supplier=self.supplier,
                                           date=timezone.localdate(), quantity=qty, rate=Decimal(rate))

    def dispatch(self, qty, rate='11200'):
        return StockDispatch.objects.create(item=self.panel, customer=self.customer,
                                            date=timezone.localdate(), quantity=qty, rate=Decimal(rate))

    def test_closing_stock_follows_the_movements(self):
        self.receive(50)
        self.dispatch(20)
        self.panel.refresh_from_db()
        self.assertEqual(self.panel.received, 50)
        self.assertEqual(self.panel.dispatched, 20)
        self.assertEqual(self.panel.closing_stock, 130)          # 100 + 50 − 20
        self.assertEqual(self.panel.stock_value, Decimal('1274000'))

    def test_two_receipts_and_two_dispatches_do_not_inflate_each_other(self):
        """Annotating both sums in one query would cross-join and double them."""
        self.receive(10); self.receive(15)
        self.dispatch(4); self.dispatch(6)
        r = self.client.get('/api/stock-items/', **self.auth())
        row = (r.json() if isinstance(r.json(), list) else r.json()['results'])[0]
        self.assertEqual(Decimal(row['received']), 25)
        self.assertEqual(Decimal(row['dispatched']), 10)
        self.assertEqual(Decimal(row['closing_stock']), 115)

    def test_reorder_status(self):
        self.assertEqual(self.panel.needs_reorder, False)
        self.dispatch(85)                                        # 100 − 85 = 15, below 20
        self.panel.refresh_from_db()
        self.assertTrue(self.panel.needs_reorder)
        r = self.client.get('/api/stock-items/', **self.auth())
        row = (r.json() if isinstance(r.json(), list) else r.json()['results'])[0]
        self.assertEqual(row['status'], 'REORDER')

    def test_item_with_movements_cannot_be_deleted(self):
        self.receive(5)
        r = self.client.delete(f'/api/stock-items/{self.panel.id}/', **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertTrue(StockItem.objects.filter(pk=self.panel.pk).exists())
        self.assertTrue(GoodsReceipt.objects.exists())

    def test_unused_item_can_be_deleted(self):
        spare = StockItem.objects.create(code='SOL-CBL-4MM', category='Cable')
        r = self.client.delete(f'/api/stock-items/{spare.id}/', **self.auth())
        self.assertEqual(r.status_code, 204)

    def test_movement_records_who_logged_it(self):
        r = self.client.post('/api/goods-receipts/', data={
            'grn_no': 'GRN-0001', 'date': str(timezone.localdate()),
            'supplier': self.supplier.id, 'item': self.panel.id, 'quantity': '30', 'rate': '9700',
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['created_by'], self.admin.id)
        self.assertEqual(Decimal(r.json()['amount']), Decimal('291000'))


class StockSummaryTests(TestCase):
    def setUp(self):
        self.admin = mk('t_admin', 'superadmin')
        self.panel = StockItem.objects.create(code='P1', category='Solar Panel',
                                              opening_stock=10, unit_cost=Decimal('100'), reorder_level=2)
        self.inverter = StockItem.objects.create(code='I1', category='Inverter',
                                                 opening_stock=1, unit_cost=Decimal('5000'), reorder_level=5)
        today = timezone.localdate()
        GoodsReceipt.objects.create(item=self.panel, date=today, quantity=5, rate=Decimal('90'))
        StockDispatch.objects.create(item=self.panel, date=today, quantity=3, rate=Decimal('150'))
        # Last year's movement must stay out of the month-to-date figures.
        GoodsReceipt.objects.create(item=self.inverter, date=date(today.year - 1, 1, 5),
                                    quantity=1, rate=Decimal('4800'))

    def test_summary_figures(self):
        r = self.client.get('/api/stock-summary/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d['sku_count'], 2)
        # panel: (10+5−3)=12 × 100 = 1200; inverter: (1+1)=2 × 5000 = 10000
        self.assertEqual(Decimal(d['total_value']), Decimal('11200'))
        self.assertEqual(Decimal(d['period_purchases']), Decimal('450'))   # 5 × 90, this month only
        self.assertEqual(Decimal(d['period_sales']), Decimal('450'))       # 3 × 150
        self.assertEqual(d['reorder_count'], 1)                            # inverter: 2 <= 5
        self.assertEqual(d['reorder_alerts'][0]['code'], 'I1')
        by_cat = {c['name']: Decimal(c['value']) for c in d['by_category']}
        self.assertEqual(by_cat, {'Solar Panel': Decimal('1200'), 'Inverter': Decimal('10000')})


class StockAccessTests(TestCase):
    """The warehouse desk: the super admin and the COO who cross between the two
    businesses, purchase staff who buy against it, and the B2B roles whose whole
    job it is. An admin runs the retail CRM and does not see it."""

    ENDPOINTS = ['/api/stock-items/', '/api/stock-customers/', '/api/goods-receipts/',
                 '/api/stock-dispatches/', '/api/stock-summary/']

    def check(self, user, allowed):
        for url in self.ENDPOINTS:
            r = self.client.get(url, HTTP_AUTHORIZATION=token_for(user))
            self.assertEqual(r.status_code, 200 if allowed else 403, f"{user.role} {url}")

    def test_allowed_roles(self):
        """Roles with the whole register. Which modules the *other* B2B roles
        reach is the matrix — see B2BRoleAccessTests."""
        for role in ('superadmin', 'coo', 'purchase_staff', 'accounts_b2b'):
            self.check(mk(f't_{role}', role), True)

    def test_an_admin_has_no_wholesale_access(self):
        """The B2C/B2B switch is the super admin's and the COO's; the API agrees,
        so an admin cannot reach the register by calling it directly."""
        self.check(mk('t_admin_b2b', 'admin'), False)

    def test_the_other_managers_have_none_either(self):
        for role in ('sales_manager', 'documentation_manager', 'accounts_manager',
                     'branch_manager', 'project_manager', 'liasoning_officer'):
            self.check(mk(f't_mgr_{role}', role), False)

    def test_accounts_b2b_runs_the_whole_register(self):
        """The wholesale business is this role's whole job, so it writes anywhere.
        The store manager and store keeper are scoped by the matrix instead."""
        u = mk('w_accounts_b2b', 'accounts_b2b')
        r = self.client.post('/api/stock-items/', data={'code': 'W-ACC'},
                             content_type='application/json', HTTP_AUTHORIZATION=token_for(u))
        self.assertEqual(r.status_code, 201, r.content[:200])

    def test_blocked_roles(self):
        for role in ('bde', 'tele_caller', 'documentation_staff', 'accounts_staff'):
            self.check(mk(f't_{role}', role), False)

    def test_blocked_role_cannot_write_either(self):
        bde = mk('t_bde', 'bde')
        r = self.client.post('/api/stock-items/', data={'code': 'X1'},
                             content_type='application/json', HTTP_AUTHORIZATION=token_for(bde))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(StockItem.objects.filter(code='X1').exists())

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get('/api/stock-summary/').status_code, 401)


class InventoryDashboardTests(TestCase):
    """The retail inventory overview: product stock plus the three document
    pipelines."""

    def setUp(self):
        from leads.models import Product
        from .models import PurchaseOrder, PurchaseOrderItem, Quote, QuoteItem, SalesOrder, SalesOrderItem
        self.admin = mk('d_admin', 'superadmin')
        self.bde = mk('d_bde', 'bde')

        self.panel = Product.objects.create(name='Panel 540W', sku='P-540', unit='Nos',
                                            cost_price=Decimal('9800'), stock_quantity=10, reorder_level=2)
        self.inverter = Product.objects.create(name='Inverter 5kW', sku='I-5K', unit='Nos',
                                               cost_price=Decimal('32000'), stock_quantity=1, reorder_level=5)

        today = timezone.localdate()
        vendor = Vendor.objects.create(name='Waaree')
        po = PurchaseOrder.objects.create(vendor=vendor, status='ordered', order_date=today)
        PurchaseOrderItem.objects.create(purchase_order=po, quantity=2, unit_price=Decimal('9750'))

        q = Quote.objects.create(status='sent', quote_date=today)
        QuoteItem.objects.create(quote=q, quantity=1, unit_price=Decimal('11200'))

        so = SalesOrder.objects.create(status='confirmed', order_date=today, tax_percent=Decimal('10'))
        SalesOrderItem.objects.create(sales_order=so, quantity=1, unit_price=Decimal('20000'))

    def get(self, user):
        r = self.client.get('/api/inventory-dashboard/', HTTP_AUTHORIZATION=token_for(user))
        return r.status_code, (r.json() if r.content else {})

    def test_stock_figures(self):
        code, d = self.get(self.admin)
        self.assertEqual(code, 200)
        self.assertEqual(d['product_count'], 2)
        # 10 × 9800 + 1 × 32000
        self.assertEqual(Decimal(d['stock_value']), Decimal('130000'))
        self.assertEqual(d['low_stock_count'], 1)               # inverter: 1 <= 5
        self.assertEqual(d['low_stock'][0]['sku'], 'I-5K')

    def test_document_pipelines(self):
        code, d = self.get(self.admin)
        self.assertEqual(d['purchase_order_status'], {'ordered': 1})
        self.assertEqual(d['quote_status'], {'sent': 1})
        self.assertEqual(d['sales_order_status'], {'confirmed': 1})
        self.assertEqual(Decimal(d['open_purchase_value']), Decimal('19500'))   # 2 × 9750
        self.assertEqual(Decimal(d['open_quote_value']), Decimal('11200'))
        # Tax lives on the header, line value on the items: 20000 + 10%.
        self.assertEqual(Decimal(d['open_sales_value']), Decimal('22000'))
        self.assertEqual(d['vendor_count'], 1)

    def test_monthly_series_covers_six_months_and_lands_this_month(self):
        code, d = self.get(self.admin)
        self.assertEqual(len(d['monthly']), 6)
        current = d['monthly'][-1]
        self.assertEqual(Decimal(current['purchases']), Decimal('19500'))
        self.assertEqual(Decimal(current['sales']), Decimal('22000'))
        self.assertTrue(all(Decimal(m['purchases']) == 0 for m in d['monthly'][:-1]))

    def test_only_the_inventory_audience_can_read_it(self):
        self.assertEqual(self.get(mk('d_coo', 'coo'))[0], 200)
        self.assertEqual(self.get(self.bde)[0], 403)
        self.assertEqual(self.get(mk('d_caller', 'tele_caller'))[0], 403)
        self.assertEqual(self.client.get('/api/inventory-dashboard/').status_code, 401)

    def test_a_custom_role_with_the_inventory_permission_can_read_it(self):
        from users.models import CustomRole
        role = CustomRole.objects.create(name='Stock Watcher', permissions=['inventory'])
        u = mk('d_custom', 'custom')
        u.custom_role = role
        u.save()
        self.assertEqual(self.get(u)[0], 200)
        role.permissions = ['leads']
        role.save()
        u.refresh_from_db()
        self.assertEqual(self.get(u)[0], 403)


class StockQuoteTests(TestCase):
    """Wholesale quotes: header maths, and converting one writes the dispatches
    that take the goods out of stock."""

    def setUp(self):
        self.admin = mk('q_admin', 'superadmin')
        self.keeper = mk('q_keeper', 'store_keeper')
        self.bde = mk('q_bde', 'bde')
        self.customer = StockCustomer.objects.create(name='Green Fields Resort')
        self.panel = StockItem.objects.create(code='Q-PNL', category='Solar Panel', brand='Waaree',
                                              model_name='540W', opening_stock=100,
                                              unit_cost=Decimal('9800'), reorder_level=10)
        self.cable = StockItem.objects.create(code='Q-CBL', category='Cable', opening_stock=500,
                                              unit_cost=Decimal('45'), reorder_level=50)

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.admin)}

    def make_quote(self, **over):
        payload = {
            'customer': self.customer.id, 'quote_date': str(timezone.localdate()),
            'site': 'Kollam', 'discount_percent': '10', 'tax_percent': '18',
            'items': [
                {'item': self.panel.id, 'quantity': '10', 'unit_price': '11200'},
                {'item': self.cable.id, 'quantity': '100', 'unit_price': '50'},
            ],
        }
        payload.update(over)
        return self.client.post('/api/stock-quotes/', data=payload,
                                content_type='application/json', **self.auth())

    def test_quote_totals(self):
        r = self.make_quote()
        self.assertEqual(r.status_code, 201, r.content[:300])
        d = r.json()
        # 10 × 11200 + 100 × 50 = 117000; −10% = 105300; +18% = 124254
        self.assertEqual(Decimal(d['subtotal']), Decimal('117000'))
        self.assertEqual(Decimal(d['discount_amount']), Decimal('11700'))
        self.assertEqual(Decimal(d['tax_amount']), Decimal('18954'))
        self.assertEqual(Decimal(d['total']), Decimal('124254'))
        self.assertTrue(d['number'].startswith('REN') and '-PI' in d['number'], d['number'])
        self.assertEqual(len(d['items']), 2)

    def test_a_quote_alone_does_not_move_stock(self):
        """It reserves rather than moves: the panels are still on the shelf,
        but they are promised, so they come off what is left to sell.
        See StockReservationTests."""
        self.make_quote()
        self.panel.refresh_from_db()
        self.assertEqual(self.panel.physical_stock, 100)
        self.assertEqual(self.panel.reserved, 10)
        self.assertEqual(self.panel.closing_stock, 90)

    def test_converting_writes_one_dispatch_per_line(self):
        qid = self.make_quote().json()['id']
        r = self.client.post(f'/api/stock-quotes/{qid}/convert/', data=paid_in_full(qid),
                             content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['dispatched_lines'], 2)
        self.assertEqual(r.json()['status'], 'converted')

        self.panel.refresh_from_db(); self.cable.refresh_from_db()
        self.assertEqual(self.panel.closing_stock, 90)      # 100 − 10
        self.assertEqual(self.cable.closing_stock, 400)     # 500 − 100

        d = StockDispatch.objects.get(item=self.panel)
        self.assertEqual(d.customer_id, self.customer.id)
        self.assertEqual(d.site, 'Kollam')
        self.assertEqual(d.rate, Decimal('11200'))
        self.assertTrue(d.invoice_no.startswith('REN') and '-IN' in d.invoice_no, d.invoice_no)

    def test_converting_twice_is_refused(self):
        """A second convert would take the same goods out of stock again."""
        qid = self.make_quote().json()['id']
        body = paid_in_full(qid)
        self.client.post(f'/api/stock-quotes/{qid}/convert/', data=body,
                         content_type='application/json', **self.auth())
        r = self.client.post(f'/api/stock-quotes/{qid}/convert/', data=body,
                             content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertIn('already been dispatched', str(r.json()))
        self.assertEqual(StockDispatch.objects.count(), 2)

    def test_an_empty_quote_cannot_be_dispatched(self):
        r = self.make_quote(items=[])
        qid = r.json()['id']
        r = self.client.post(f'/api/stock-quotes/{qid}/convert/', **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertEqual(StockDispatch.objects.count(), 0)

    def test_status_cannot_be_set_to_converted_by_hand(self):
        """That would skip the stock move entirely."""
        qid = self.make_quote().json()['id']
        r = self.client.patch(f'/api/stock-quotes/{qid}/', data={'status': 'converted'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertEqual(StockDispatch.objects.count(), 0)

    def test_a_converted_quote_can_no_longer_be_edited(self):
        """Editing it would diverge from the dispatches already written from it.

        Deleting is a different matter and is allowed — the dispatch stands on
        its own; see StockQuoteDeletionTests.
        """
        qid = self.make_quote().json()['id']
        self.client.post(f'/api/stock-quotes/{qid}/convert/', data=paid_in_full(qid),
                         content_type='application/json', **self.auth())
        r = self.client.patch(f'/api/stock-quotes/{qid}/', data={'tax_percent': '0'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.delete(f'/api/stock-quotes/{qid}/', **self.auth()).status_code, 204)

    def test_an_open_quote_can_be_edited_and_deleted(self):
        qid = self.make_quote().json()['id']
        r = self.client.patch(f'/api/stock-quotes/{qid}/', data={'status': 'sent'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'sent')
        self.assertEqual(self.client.delete(f'/api/stock-quotes/{qid}/', **self.auth()).status_code, 204)

    def test_store_keeper_can_quote_but_a_bde_cannot(self):
        self.assertEqual(self.client.get('/api/stock-quotes/', **self.auth(self.keeper)).status_code, 200)
        self.assertEqual(self.client.get('/api/stock-quotes/', **self.auth(self.bde)).status_code, 403)

    def test_editing_lines_replaces_them(self):
        qid = self.make_quote().json()['id']
        r = self.client.patch(f'/api/stock-quotes/{qid}/', data={
            'items': [{'item': self.panel.id, 'quantity': '5', 'unit_price': '11000'}]},
            content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['items']), 1)
        self.assertEqual(Decimal(r.json()['subtotal']), Decimal('55000'))


class StockSummaryShapeTests(TestCase):
    """The wholesale dashboard reports the same shape as the retail one, so the
    two screens can be laid out identically."""

    def setUp(self):
        self.admin = mk('s_admin', 'superadmin')
        self.item = StockItem.objects.create(code='S1', category='Solar Panel', opening_stock=20,
                                             unit_cost=Decimal('100'), reorder_level=2)
        today = timezone.localdate()
        GoodsReceipt.objects.create(item=self.item, date=today, quantity=5, rate=Decimal('90'))
        StockDispatch.objects.create(item=self.item, date=today, quantity=2, rate=Decimal('150'))
        Vendor.objects.create(name='S Supplier')
        StockCustomer.objects.create(name='S Customer')

    def get(self):
        r = self.client.get('/api/stock-summary/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_the_series_covers_the_period_a_bar_a_day(self):
        """The chart follows the window the figures do. This month is short
        enough to read a day at a time — as one monthly bar it would say
        nothing. Today carries the movement; the rest of the month is quiet.
        """
        d = self.get()
        today = timezone.localdate()
        self.assertEqual(len(d['monthly']), today.day)
        last = d['monthly'][-1]
        self.assertEqual(last['name'], today.strftime('%d %b'))
        self.assertEqual(Decimal(last['purchases']), Decimal('450'))    # 5 x 90
        self.assertEqual(Decimal(last['sales']), Decimal('300'))        # 2 x 150
        self.assertTrue(all(Decimal(m['purchases']) == 0 and Decimal(m['sales']) == 0
                            for m in d['monthly'][:-1]))

    def test_counts_for_the_pipeline_cards(self):
        d = self.get()
        self.assertEqual(d['receipt_count'], 1)
        self.assertEqual(d['dispatch_count'], 1)
        self.assertEqual(d['supplier_count'], 1)
        self.assertEqual(d['customer_count'], 1)
        self.assertEqual(d['quote_count'], 0)
        self.assertEqual(d['quote_status'], {})
        self.assertEqual(Decimal(d['open_quote_value']), Decimal('0'))

    def test_quote_pipeline_counts_open_value_only(self):
        from .models import StockQuote, StockQuoteItem
        for status, qty in (('sent', 2), ('accepted', 1), ('declined', 5)):
            q = StockQuote.objects.create(status=status, quote_date=timezone.localdate())
            StockQuoteItem.objects.create(quote=q, item=self.item, quantity=qty, unit_price=Decimal('100'))
        d = self.get()
        self.assertEqual(d['quote_count'], 3)
        self.assertEqual(d['quote_status'], {'sent': 1, 'accepted': 1, 'declined': 1})
        # Declined is excluded: 2×100 + 1×100
        self.assertEqual(Decimal(d['open_quote_value']), Decimal('300'))

    def test_existing_fields_are_untouched(self):
        """The old keys still drive the low-stock panel and KPI cards."""
        d = self.get()
        for key in ('sku_count', 'total_value', 'reorder_count', 'period_purchases',
                    'period_sales', 'by_category', 'reorder_alerts', 'stock_levels'):
            self.assertIn(key, d)
        self.assertEqual(d['sku_count'], 1)
        self.assertEqual(Decimal(d['total_value']), Decimal('2300'))   # (20+5−2) × 100


class FractionalQuantityTests(TestCase):
    """Fractions must survive: cable is bought in metres, structures in part
    sets. Nothing in the inventory path may round or truncate them."""

    def setUp(self):
        self.admin = mk('fq_admin', 'superadmin')

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    # ── Wholesale (stock register) ──
    def test_stock_movements_keep_their_fractions(self):
        item = StockItem.objects.create(code='FQ-CBL', category='Cable', unit='Mtr',
                                        opening_stock=Decimal('10.5'), unit_cost=Decimal('45.25'))
        GoodsReceipt.objects.create(item=item, date=timezone.localdate(),
                                    quantity=Decimal('4.5'), rate=Decimal('500.50'))
        StockDispatch.objects.create(item=item, date=timezone.localdate(),
                                     quantity=Decimal('2.25'), rate=Decimal('600.75'))
        item.refresh_from_db()
        self.assertEqual(item.received, Decimal('4.50'))
        self.assertEqual(item.dispatched, Decimal('2.25'))
        self.assertEqual(item.closing_stock, Decimal('12.75'))       # 10.5 + 4.5 − 2.25
        self.assertEqual(item.stock_value, Decimal('576.9375'))      # 12.75 × 45.25

    def test_a_fractional_movement_survives_the_api(self):
        item = StockItem.objects.create(code='FQ-API', category='Cable', unit='Mtr')
        r = self.client.post('/api/stock-dispatches/', data={
            'date': str(timezone.localdate()), 'item': item.id,
            'quantity': '4.5', 'rate': '500.50',
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:200])
        self.assertEqual(Decimal(r.json()['quantity']), Decimal('4.50'))
        self.assertEqual(Decimal(r.json()['rate']), Decimal('500.50'))
        self.assertEqual(Decimal(r.json()['amount']), Decimal('2252.25'))   # not 2252

    def test_a_fractional_quote_line_survives(self):
        from .models import StockQuote
        item = StockItem.objects.create(code='FQ-QT', category='Cable', unit='Mtr')
        r = self.client.post('/api/stock-quotes/', data={
            'quote_date': str(timezone.localdate()),
            'items': [{'item': item.id, 'quantity': '4.5', 'unit_price': '500.50'}],
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:200])
        self.assertEqual(Decimal(r.json()['subtotal']), Decimal('2252.25'))

        qid = r.json()['id']
        self.client.post(f'/api/stock-quotes/{qid}/convert/', data=paid_in_full(qid),
                         content_type='application/json', **self.auth())
        d = StockDispatch.objects.get(item=item)
        self.assertEqual(d.quantity, Decimal('4.50'))
        self.assertEqual(d.rate, Decimal('500.50'))

    # ── Retail (product catalogue) ──
    def test_a_product_can_hold_fractional_stock(self):
        from leads.models import Product
        r = self.client.post('/api/products/', data={
            'name': 'DC Cable', 'sku': 'FQ-P', 'unit': 'Mtr',
            'default_price': '55.75', 'cost_price': '45.25',
            'stock_quantity': '120.5', 'reorder_level': '10.5',
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:200])
        p = Product.objects.get(sku='FQ-P')
        self.assertEqual(p.stock_quantity, Decimal('120.50'))
        self.assertEqual(p.reorder_level, Decimal('10.50'))

    def test_receiving_a_purchase_order_adds_the_whole_fraction(self):
        """int() used to truncate this: receiving 4.5 added only 4."""
        from leads.models import Product
        from .models import PurchaseOrder, PurchaseOrderItem
        p = Product.objects.create(name='Cable', sku='FQ-PO', unit='Mtr',
                                   stock_quantity=Decimal('10'), cost_price=Decimal('45'))
        po = PurchaseOrder.objects.create(status='draft')
        PurchaseOrderItem.objects.create(purchase_order=po, product=p,
                                         quantity=Decimal('4.5'), unit_price=Decimal('45'))
        r = self.client.patch(f'/api/purchase-orders/{po.id}/', data={'status': 'received'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        p.refresh_from_db()
        self.assertEqual(p.stock_quantity, Decimal('14.50'))     # not 14

    def test_low_stock_still_compares_correctly_with_fractions(self):
        from leads.models import Product
        p = Product.objects.create(name='Cable', sku='FQ-LOW', unit='Mtr',
                                   stock_quantity=Decimal('10.4'), reorder_level=Decimal('10.5'))
        self.assertTrue(p.low_stock)
        p.stock_quantity = Decimal('10.6')
        self.assertFalse(p.low_stock)

    def test_the_retail_dashboard_values_a_fractional_stock(self):
        from leads.models import Product
        Product.objects.create(name='Cable', sku='FQ-DASH', unit='Mtr',
                               stock_quantity=Decimal('120.5'), cost_price=Decimal('45.25'))
        r = self.client.get('/api/inventory-dashboard/', **self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Decimal(r.json()['stock_value']), Decimal('5452.625'))  # 120.5 × 45.25


class DispatchTaxTests(TestCase):
    """Tax on a dispatch line: `amount` stays the goods value, `total` is what
    the customer is invoiced."""

    def setUp(self):
        self.admin = mk('dt_admin', 'superadmin')
        self.item = StockItem.objects.create(code='DT-PNL', category='Solar Panel',
                                             opening_stock=Decimal('100'), unit_cost=Decimal('9800'))

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def test_tax_splits_goods_value_from_the_invoiced_total(self):
        r = self.client.post('/api/stock-dispatches/', data={
            'date': str(timezone.localdate()), 'item': self.item.id,
            'quantity': '10', 'rate': '11200', 'tax_percent': '18',
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:200])
        d = r.json()
        self.assertEqual(Decimal(d['amount']), Decimal('112000'))       # goods
        self.assertEqual(Decimal(d['tax_amount']), Decimal('20160'))    # 18%
        self.assertEqual(Decimal(d['total']), Decimal('132160'))

    def test_tax_defaults_to_zero(self):
        r = self.client.post('/api/stock-dispatches/', data={
            'date': str(timezone.localdate()), 'item': self.item.id,
            'quantity': '2', 'rate': '100',
        }, content_type='application/json', **self.auth())
        d = r.json()
        self.assertEqual(Decimal(d['tax_percent']), Decimal('0'))
        self.assertEqual(Decimal(d['total']), Decimal('200'))

    def test_tax_keeps_its_fraction(self):
        """Entered figures are never rounded away; a *derived* tax is carried to
        the paisa, like every other money field here — ₹56.30625 isn't payable."""
        r = self.client.post('/api/stock-dispatches/', data={
            'date': str(timezone.localdate()), 'item': self.item.id,
            'quantity': '4.5', 'rate': '500.50', 'tax_percent': '2.5',
        }, content_type='application/json', **self.auth())
        d = r.json()
        self.assertEqual(Decimal(d['quantity']), Decimal('4.50'))       # as entered
        self.assertEqual(Decimal(d['rate']), Decimal('500.50'))         # as entered
        self.assertEqual(Decimal(d['amount']), Decimal('2252.25'))      # exact
        self.assertEqual(Decimal(d['tax_amount']), Decimal('56.31'))    # 56.30625 → paise
        self.assertEqual(Decimal(d['total']), Decimal('2308.56'))
        # The paise figures still add up.
        self.assertEqual(Decimal(d['amount']) + Decimal(d['tax_amount']), Decimal(d['total']))

    def test_tax_does_not_touch_the_stock_ledger(self):
        """Stock moves in units; tax is money only."""
        self.client.post('/api/stock-dispatches/', data={
            'date': str(timezone.localdate()), 'item': self.item.id,
            'quantity': '10', 'rate': '11200', 'tax_percent': '18',
        }, content_type='application/json', **self.auth())
        self.item.refresh_from_db()
        self.assertEqual(self.item.closing_stock, Decimal('90'))

    def test_a_converted_quote_carries_its_tax_onto_the_dispatch(self):
        r = self.client.post('/api/stock-quotes/', data={
            'quote_date': str(timezone.localdate()), 'tax_percent': '18',
            'items': [{'item': self.item.id, 'quantity': '10', 'unit_price': '11200'}],
        }, content_type='application/json', **self.auth())
        qid = r.json()['id']
        self.client.post(f'/api/stock-quotes/{qid}/convert/', data=paid_in_full(qid),
                         content_type='application/json', **self.auth())
        d = StockDispatch.objects.get(item=self.item)
        self.assertEqual(d.tax_percent, Decimal('18.00'))
        self.assertEqual(d.total, Decimal('132160'))

    def test_the_dashboard_reports_the_invoiced_value(self):
        self.client.post('/api/stock-dispatches/', data={
            'date': str(timezone.localdate()), 'item': self.item.id,
            'quantity': '10', 'rate': '11200', 'tax_percent': '18',
        }, content_type='application/json', **self.auth())
        r = self.client.get('/api/stock-summary/', **self.auth())
        self.assertEqual(Decimal(r.json()['period_sales']), Decimal('132160'))
        self.assertEqual(Decimal(r.json()['monthly'][-1]['sales']), Decimal('132160'))

    def test_editing_a_dispatch_can_change_its_tax(self):
        r = self.client.post('/api/stock-dispatches/', data={
            'date': str(timezone.localdate()), 'item': self.item.id,
            'quantity': '10', 'rate': '100', 'tax_percent': '18',
        }, content_type='application/json', **self.auth())
        did = r.json()['id']
        r = self.client.patch(f'/api/stock-dispatches/{did}/', data={'tax_percent': '5'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Decimal(r.json()['total']), Decimal('1050'))


class DocumentSendChannelTests(TestCase):
    """Wholesale documents go out on the B2B account; retail ones don't.

    Driven through the real send endpoints rather than by reading the constant,
    so a future refactor that drops the channel on the way down is caught.
    """

    def setUp(self):
        self.admin = mk('chan_admin', 'superadmin')
        org = OrgSettings.load()
        org.whatsapp_phone_number_id = 'retail-pid'
        org.whatsapp_access_token = 'retail-token'
        org.b2b_whatsapp_phone_number_id = 'wholesale-pid'
        org.b2b_whatsapp_access_token = 'wholesale-token'
        org.save()
        self.customer = StockCustomer.objects.create(name='Green Fields Resort',
                                                     contact_number='9876543210')
        self.item = StockItem.objects.create(code='CH-PNL', category='Solar Panel',
                                             opening_stock=50, unit_cost=Decimal('9800'))

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def send(self, url):
        """POST a one-page PDF at `url` over WhatsApp, and report the number used."""
        pdf = SimpleUploadedFile('doc.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        with patch.object(whatsapp._session, 'post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'messages': [{'id': 'wamid.1'}]}
            r = self.client.post(url, data={'pdf': pdf, 'channels': 'whatsapp'}, **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        return post.call_args[0][0], post.call_args[1]['headers']['Authorization']

    def test_a_wholesale_proforma_uses_the_b2b_number(self):
        r = self.client.post('/api/stock-quotes/', data={
            'customer': self.customer.id, 'quote_date': str(timezone.localdate()),
            'items': [{'item': self.item.id, 'quantity': '2', 'unit_price': '11200'}],
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:300])
        url, token = self.send(f"/api/stock-quotes/{r.json()['id']}/send/")
        self.assertIn('wholesale-pid', url)
        self.assertEqual(token, 'Bearer wholesale-token')

    def test_a_dispatch_invoice_uses_the_b2b_number(self):
        r = self.client.post('/api/stock-dispatches/', data={
            'item': self.item.id, 'customer': self.customer.id,
            'date': str(timezone.localdate()), 'quantity': '2',
            'unit_price': '11200',
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:300])
        url, token = self.send(f"/api/stock-dispatches/{r.json()['id']}/send/")
        self.assertIn('wholesale-pid', url)
        self.assertEqual(token, 'Bearer wholesale-token')

    def test_a_retail_proforma_still_uses_the_shared_number(self):
        lead = Lead.objects.create(first_name='Sidharth', last_name='V', phone='9876500000')
        r = self.client.post('/api/quotes/', data={
            'lead': lead.id, 'quote_date': str(timezone.localdate()),
            'items': [{'description': 'Solar panel', 'quantity': '2', 'unit_price': '11200'}],
        }, content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 201, r.content[:300])
        url, token = self.send(f"/api/quotes/{r.json()['id']}/send/")
        self.assertIn('retail-pid', url)
        self.assertEqual(token, 'Bearer retail-token')


class MultiItemGoodsReceiptTests(TestCase):
    """A supplier delivery of several products is several receipt rows under one
    GRN — that is what the stock ledger values, one movement per item."""

    def setUp(self):
        self.admin = mk('grn_admin', 'superadmin')
        self.supplier = Vendor.objects.create(name='Techclustron')
        self.items = [
            StockItem.objects.create(code=f'MG-{n}', category='Solar Panel', brand='Adani',
                                     model_name=f'{n}00W', opening_stock=0,
                                     unit_cost=Decimal('1000'))
            for n in (1, 2, 3)
        ]

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def receipt(self, item, qty, grn='GRN-0007'):
        return self.client.post('/api/goods-receipts/', data={
            'grn_no': grn, 'date': str(timezone.localdate()), 'supplier': self.supplier.id,
            'item': item.id, 'quantity': str(qty), 'rate': '1000',
        }, content_type='application/json', **self.auth())

    def test_several_items_share_one_grn(self):
        for n, item in enumerate(self.items, start=1):
            self.assertEqual(self.receipt(item, n * 5).status_code, 201)
        rows = GoodsReceipt.objects.filter(grn_no='GRN-0007')
        self.assertEqual(rows.count(), 3)
        self.assertEqual(sum(r.amount for r in rows), Decimal('30000'))

    def test_each_row_moves_its_own_item_into_stock(self):
        for n, item in enumerate(self.items, start=1):
            self.receipt(item, n * 5)
        for n, item in enumerate(self.items, start=1):
            item.refresh_from_db()
            self.assertEqual(item.closing_stock, Decimal(n * 5))

    def test_a_grn_number_is_not_claimed_exclusively(self):
        """Reusing the number is how the rows group; it must not collide."""
        self.assertEqual(self.receipt(self.items[0], 1).status_code, 201)
        self.assertEqual(self.receipt(self.items[1], 1).status_code, 201)

    def test_editing_one_row_leaves_its_siblings_alone(self):
        first = self.receipt(self.items[0], 5).json()['id']
        self.receipt(self.items[1], 5)
        r = self.client.patch(f'/api/goods-receipts/{first}/', data={'quantity': '8'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.items[0].refresh_from_db(); self.items[1].refresh_from_db()
        self.assertEqual(self.items[0].closing_stock, Decimal('8'))
        self.assertEqual(self.items[1].closing_stock, Decimal('5'))


class StockPurchaseOrderTests(TestCase):
    """The purchase order raised on a supplier: its number series, its money, and
    the payload the printed form is drawn from."""

    def setUp(self):
        self.admin = mk('po_admin', 'superadmin')
        self.supplier = Vendor.objects.create(
            name='Texolver Solutions Pvt Ltd',
            address='193, Raghuvir Industrial Estate, Vatva GIDC, A\'bad',
            gst_number='24AAFCT0754L1Z8', pan_number='AAFCT0754L', iec_code='0123456789',
            email='sales@texolver.example')

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def make(self, **over):
        payload = {
            'supplier': self.supplier.id, 'po_date': '2026-04-30',
            'transportation': '800', 'tax_percent': '18', 'tax_label': 'IGST',
            'ship_to_phone': '9074193787',
            'items': [{'description': 'R-KEM-II-300', 'unit_price': '575', 'quantity': '50'}],
        }
        payload.update(over)
        return self.client.post('/api/stock-purchase-orders/', data=payload,
                                content_type='application/json', **self.auth())

    def test_the_money_matches_the_printed_form(self):
        """Freight is taxed with the goods — 28750 + 800, then 18%."""
        r = self.make()
        self.assertEqual(r.status_code, 201, r.content[:300])
        po = StockPurchaseOrder.objects.get(pk=r.json()['id'])
        self.assertEqual(po.goods_amount, Decimal('28750'))
        self.assertEqual(po.taxable_amount, Decimal('29550'))
        self.assertEqual(po.tax_amount, Decimal('5319'))
        self.assertEqual(po.total, Decimal('34869'))

    def test_numbers_run_per_financial_year(self):
        first = StockPurchaseOrder.objects.get(pk=self.make().json()['id'])
        second = StockPurchaseOrder.objects.get(pk=self.make().json()['id'])
        self.assertEqual((first.number, first.fy), ('REN2627-PO001', '26-27'))
        self.assertEqual((second.number, second.fy), ('REN2627-PO002', '26-27'))
        # April starts the next year's series over at 001.
        third = StockPurchaseOrder.objects.get(pk=self.make(po_date='2027-04-01').json()['id'])
        self.assertEqual((third.number, third.fy), ('REN2728-PO001', '27-28'))

    def test_deleting_one_does_not_reissue_its_number(self):
        a = StockPurchaseOrder.objects.get(pk=self.make().json()['id'])
        b = StockPurchaseOrder.objects.get(pk=self.make().json()['id'])
        a.delete()
        c = StockPurchaseOrder.objects.get(pk=self.make().json()['id'])
        self.assertNotEqual(c.number, b.number)
        self.assertEqual(c.number, 'REN2627-PO003')

    def test_the_document_payload_carries_what_the_form_prints(self):
        po_id = self.make().json()['id']
        r = self.client.get(f'/api/stock-purchase-orders/{po_id}/document/', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        d = r.json()
        self.assertEqual(d['title'], 'PURCHASE ORDER')
        self.assertEqual(d['order']['number'], 'REN2627-PO001')
        self.assertEqual(d['supplier']['pan'], 'AAFCT0754L')
        self.assertEqual(d['supplier']['iec'], '0123456789')
        self.assertEqual(d['supplier']['gstin'], '24AAFCT0754L1Z8')
        self.assertEqual(d['lines'][0]['description'], 'R-KEM-II-300')
        self.assertEqual(d['totals']['total'], '34869.00')
        self.assertEqual(d['totals']['in_words'],
                         'Thirty Four Thousand Eight Hundred and Sixty Nine Only')

    def test_ship_to_falls_back_to_the_company_address(self):
        po_id = self.make(ship_to_address='').json()['id']
        d = self.client.get(f'/api/stock-purchase-orders/{po_id}/document/', **self.auth()).json()
        self.assertTrue(d['ship_to']['address'])
        self.assertEqual(d['ship_to']['address'], d['company']['address'])

    def test_a_catalogued_item_fills_the_description_and_part_code(self):
        item = StockItem.objects.create(code='SOL-PNL-540', category='Solar Panel',
                                        brand='Waaree', model_name='540W')
        po_id = self.make(items=[{'item': item.id, 'quantity': '10', 'unit_price': '9800'}]).json()['id']
        d = self.client.get(f'/api/stock-purchase-orders/{po_id}/document/', **self.auth()).json()
        self.assertEqual(d['lines'][0]['description'], 'Waaree 540W')
        self.assertEqual(d['lines'][0]['part_code'], 'SOL-PNL-540')

    def test_sending_it_uses_the_b2b_account_and_leaves_draft(self):
        po_id = self.make().json()['id']
        with patch('messaging.email.send_and_log') as send:
            send.return_value = type('L', (), {'status': 'sent', 'error': ''})()
            r = self.client.post(
                f'/api/stock-purchase-orders/{po_id}/send/',
                data={'channels': 'email', 'email': 'sales@texolver.example',
                      'pdf': SimpleUploadedFile('po.pdf', b'%PDF-1.4 order',
                                                content_type='application/pdf')},
                **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(send.call_args[1]['channel'], 'b2b')
        self.assertEqual(StockPurchaseOrder.objects.get(pk=po_id).status, 'sent')

    def test_the_desk_is_closed_to_everyone_else(self):
        for role in ('bde', 'tele_caller', 'documentation_staff', 'accounts_staff'):
            r = self.client.get('/api/stock-purchase-orders/',
                                HTTP_AUTHORIZATION=token_for(mk(f'po_{role}', role)))
            self.assertEqual(r.status_code, 403, role)


class WholesaleDocumentSeriesTests(TestCase):
    """B2B documents number themselves REN<fy>-<kind><seq>, each kind counting on
    its own and every series restarting on 1 April."""

    def setUp(self):
        self.admin = mk('ser_admin', 'superadmin')
        self.supplier = Vendor.objects.create(name='Ensun')
        self.customer = StockCustomer.objects.create(name='Ananthapuri')
        self.item = StockItem.objects.create(code='SER-1', category='Solar Panel',
                                             brand='Adani', model_name='555wp',
                                             opening_stock=500)

    def quote(self, on=date(2026, 8, 3)):
        return StockQuote.objects.create(customer=self.customer, quote_date=on)

    def dispatch(self, on=date(2026, 8, 3), invoice_no=''):
        return StockDispatch.objects.create(item=self.item, customer=self.customer,
                                            date=on, quantity=1, rate=Decimal('100'),
                                            invoice_no=invoice_no)

    def order(self, on=date(2026, 8, 3)):
        return StockPurchaseOrder.objects.create(supplier=self.supplier, po_date=on)

    def test_each_document_takes_its_own_prefix(self):
        self.assertEqual(self.quote().number, 'REN2627-PI001')
        self.assertEqual(self.dispatch().invoice_no, 'REN2627-IN001')
        self.assertEqual(self.order().number, 'REN2627-PO001')

    def test_each_series_counts_independently(self):
        self.assertEqual([self.quote().number for _ in range(3)][-1], 'REN2627-PI003')
        self.assertEqual(self.dispatch().invoice_no, 'REN2627-IN001')   # unaffected
        self.assertEqual(self.order().number, 'REN2627-PO001')

    def test_the_series_restarts_on_the_first_of_april(self):
        self.assertEqual(self.order(date(2026, 8, 3)).number, 'REN2627-PO001')
        self.assertEqual(self.order(date(2027, 3, 31)).number, 'REN2627-PO002')
        # 1 April is a new financial year, so the count starts over.
        self.assertEqual(self.order(date(2027, 4, 1)).number, 'REN2728-PO001')
        self.assertEqual(self.order(date(2027, 4, 2)).number, 'REN2728-PO002')
        # …and the old year carries on from where it left off.
        self.assertEqual(self.order(date(2027, 3, 30)).number, 'REN2627-PO003')

    def test_a_number_is_never_reissued_after_a_deletion(self):
        first = self.order()
        second = self.order()
        first.delete()
        self.assertEqual(self.order().number, 'REN2627-PO003')
        self.assertEqual(second.number, 'REN2627-PO002')

    def test_two_quotes_cannot_share_a_number(self):
        q = self.quote()
        with self.assertRaises(Exception):
            StockQuote.objects.create(customer=self.customer, quote_date=date(2026, 8, 3),
                                      number=q.number)

    def test_the_rows_of_one_delivery_share_their_invoice_number(self):
        """A dispatch is one row per item; the set is one invoice."""
        first = self.dispatch()
        rest = [self.dispatch(invoice_no=first.invoice_no) for _ in range(2)]
        self.assertEqual({d.invoice_no for d in rest}, {first.invoice_no})
        self.assertEqual(StockDispatch.objects.filter(invoice_no='REN2627-IN001').count(), 3)
        # The next delivery still gets 002, not 004.
        self.assertEqual(self.dispatch().invoice_no, 'REN2627-IN002')

    def test_converting_a_proforma_issues_an_invoice_number(self):
        q = self.quote()
        StockQuoteItem.objects.create(quote=q, item=self.item, quantity=2, unit_price=Decimal('100'))
        r = self.client.post(f'/api/stock-quotes/{q.id}/convert/', data=paid_in_full(q),
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        made = StockDispatch.objects.filter(notes__contains=q.number)
        self.assertEqual(made.count(), 1)
        # The sale gets its own number rather than carrying the proforma's.
        self.assertEqual(made.first().invoice_no, 'REN2627-IN001')

    def test_the_retail_series_is_untouched(self):
        """B2C proforma invoices keep the EF/<fy>/PI series they always had."""
        from leads.models import Lead
        lead = Lead.objects.create(first_name='Retail', last_name='One', phone='9990001234')
        q = Quote.objects.create(lead=lead, quote_date=date(2026, 8, 3))
        self.assertTrue(q.number.startswith('EF/26-27/PI'), q.number)


class DocumentNumbersAreSpentOnceTests(TestCase):
    """A number that has been on a document is never issued again — deleting the
    document does not release it."""

    def setUp(self):
        self.supplier = Vendor.objects.create(name='Ensun')
        self.customer = StockCustomer.objects.create(name='Ananthapuri')
        self.item = StockItem.objects.create(code='SP-1', category='Solar Panel',
                                             opening_stock=100)

    def order(self, on=date(2026, 8, 3)):
        return StockPurchaseOrder.objects.create(supplier=self.supplier, po_date=on)

    def test_deleting_the_newest_does_not_free_its_number(self):
        """The case a count-the-rows scheme gets wrong: nothing sits above the
        deleted number, so counting would hand it straight back."""
        first, second = self.order(), self.order()
        self.assertEqual([first.number, second.number], ['REN2627-PO001', 'REN2627-PO002'])
        second.delete()
        self.assertEqual(self.order().number, 'REN2627-PO003')

    def test_deleting_one_in_the_middle_does_not_free_its_number(self):
        a, b, c = self.order(), self.order(), self.order()
        b.delete()
        self.assertEqual(self.order().number, 'REN2627-PO004')
        self.assertEqual([a.number, c.number], ['REN2627-PO001', 'REN2627-PO003'])

    def test_deleting_every_document_still_moves_the_series_on(self):
        made = [self.order() for _ in range(3)]
        for po in made:
            po.delete()
        self.assertEqual(StockPurchaseOrder.objects.count(), 0)
        self.assertEqual(self.order().number, 'REN2627-PO004')

    def test_it_holds_for_proformas_too(self):
        """Invoices are the exception — they run on without gaps; see
        InvoiceNumbersRunOnTests."""
        q = StockQuote.objects.create(customer=self.customer, quote_date=date(2026, 8, 3))
        self.assertEqual(q.number, 'REN2627-PI001')
        q.delete()
        q2 = StockQuote.objects.create(customer=self.customer, quote_date=date(2026, 8, 3))
        self.assertEqual(q2.number, 'REN2627-PI002')

    def test_the_new_year_still_starts_at_001(self):
        """Spending numbers in one year must not carry into the next."""
        for _ in range(3):
            self.order(date(2026, 8, 3))
        self.assertEqual(self.order(date(2027, 4, 1)).number, 'REN2728-PO001')

    def test_previewing_the_next_number_does_not_spend_it(self):
        from .models import peek_document_number
        self.assertEqual(peek_document_number('PO', on=date(2026, 8, 3)), 'REN2627-PO001')
        self.assertEqual(peek_document_number('PO', on=date(2026, 8, 3)), 'REN2627-PO001')
        self.assertEqual(self.order().number, 'REN2627-PO001')


class StockQuoteDeletionTests(TestCase):
    """A proforma invoice can be deleted at any point in its life, including
    after it has been dispatched."""

    def setUp(self):
        self.admin = mk('del_admin', 'superadmin')
        self.customer = StockCustomer.objects.create(name='Ananthapuri')
        self.item = StockItem.objects.create(code='DEL-1', category='Solar Panel',
                                             opening_stock=100)

    def make_quote(self):
        q = StockQuote.objects.create(customer=self.customer, quote_date=date(2026, 8, 3))
        StockQuoteItem.objects.create(quote=q, item=self.item, quantity=2, unit_price=Decimal('100'))
        return q

    def delete(self, q):
        return self.client.delete(f'/api/stock-quotes/{q.id}/',
                                  HTTP_AUTHORIZATION=token_for(self.admin))

    def test_a_draft_can_be_deleted(self):
        q = self.make_quote()
        self.assertEqual(self.delete(q).status_code, 204)
        self.assertFalse(StockQuote.objects.filter(pk=q.pk).exists())

    def test_a_dispatched_one_can_be_deleted_too(self):
        q = self.make_quote()
        self.client.post(f'/api/stock-quotes/{q.id}/convert/', data=paid_in_full(q),
                         content_type='application/json',
                         HTTP_AUTHORIZATION=token_for(self.admin))
        q.refresh_from_db()
        self.assertEqual(q.status, 'converted')
        self.assertEqual(self.delete(q).status_code, 204)

    def test_deleting_it_leaves_the_sale_alone(self):
        """The dispatch keeps its invoice number and its stock movement."""
        q = self.make_quote()
        self.client.post(f'/api/stock-quotes/{q.id}/convert/', data=paid_in_full(q),
                         content_type='application/json',
                         HTTP_AUTHORIZATION=token_for(self.admin))
        dispatched = list(StockDispatch.objects.values_list('invoice_no', flat=True))
        self.item.refresh_from_db()
        stock_after_dispatch = self.item.closing_stock

        self.delete(q)
        self.assertEqual(list(StockDispatch.objects.values_list('invoice_no', flat=True)), dispatched)
        self.item.refresh_from_db()
        self.assertEqual(self.item.closing_stock, stock_after_dispatch)

    def test_its_number_stays_spent(self):
        q = self.make_quote()
        number = q.number
        self.delete(q)
        nxt = StockQuote.objects.create(customer=self.customer, quote_date=date(2026, 8, 3))
        self.assertNotEqual(nxt.number, number)


class B2BRoleAccessTests(TestCase):
    """The three wholesale roles do different jobs, so the register is not one
    door: Accounts B2B runs it, the store manager keeps the item master and
    watches the rest, the store keeper only looks things up."""

    # module -> (list url, a minimal create body)
    ENDPOINTS = {
        'dashboard': ('/api/stock-summary/', None),
        'items':     ('/api/stock-items/', {'code': 'ACC-1'}),
        'suppliers': ('/api/vendors/', {'name': 'ACC supplier'}),
        'customers': ('/api/stock-customers/', {'name': 'ACC customer'}),
        'proforma':  ('/api/stock-quotes/', {'quote_date': '2026-08-04'}),
        'dispatch':  ('/api/stock-dispatches/', None),
        'purchases': ('/api/stock-purchase-orders/', None),
    }

    # What the matrix promises, spelled out here independently of the code.
    EXPECTED = {
        'accounts_b2b':  {'dashboard': 'rw', 'items': 'rw', 'suppliers': 'rw',
                          'customers': 'rw', 'proforma': 'rw', 'dispatch': 'rw',
                          'purchases': 'rw'},
        'store_manager': {'dashboard': 'r', 'items': 'rw', 'customers': 'r',
                          'proforma': 'r', 'dispatch': 'r'},
        'store_keeper':  {'items': 'r', 'proforma': 'r'},
    }

    def can_read(self, user, url):
        r = self.client.get(url, HTTP_AUTHORIZATION=token_for(user))
        self.assertIn(r.status_code, (200, 403), f'{user.role} GET {url} -> {r.status_code}')
        return r.status_code == 200

    def can_write(self, user, url, body):
        r = self.client.post(url, data=body, content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(user))
        # 400 means it got past the permission layer and failed validation, which
        # is still "allowed to write".
        return r.status_code != 403

    def test_every_role_reaches_exactly_its_own_modules(self):
        for role, expected in self.EXPECTED.items():
            user = mk(f'b2b_{role}', role)
            for module, (url, _) in self.ENDPOINTS.items():
                allowed = module in expected
                self.assertEqual(self.can_read(user, url), allowed,
                                 f'{role} should {"" if allowed else "not "}read {module}')

    def test_read_only_modules_refuse_writes(self):
        for role, expected in self.EXPECTED.items():
            user = mk(f'w_{role}', role)
            for module, level in expected.items():
                url, body = self.ENDPOINTS[module]
                if body is None:
                    continue                      # no simple create body for these
                self.assertEqual(self.can_write(user, url, body), level == 'rw',
                                 f'{role} on {module} ({level})')

    def test_a_store_keeper_cannot_touch_the_item_master(self):
        keeper = mk('sk_only', 'store_keeper')
        item = StockItem.objects.create(code='SK-1', category='Solar Panel')
        self.assertTrue(self.can_read(keeper, '/api/stock-items/'))
        for method, kwargs in ((self.client.post, {'data': {'code': 'SK-2'}}),
                               (self.client.patch, {'data': {'brand': 'X'}})):
            url = '/api/stock-items/' if method is self.client.post else f'/api/stock-items/{item.id}/'
            r = method(url, content_type='application/json',
                       HTTP_AUTHORIZATION=token_for(keeper), **kwargs)
            self.assertEqual(r.status_code, 403, f'{url}')
        self.assertEqual(
            self.client.delete(f'/api/stock-items/{item.id}/',
                               HTTP_AUTHORIZATION=token_for(keeper)).status_code, 403)

    def test_a_store_manager_keeps_the_item_master(self):
        manager = mk('sm_only', 'store_manager')
        r = self.client.post('/api/stock-items/', data={'code': 'SM-1', 'category': 'Solar Panel'},
                             content_type='application/json', HTTP_AUTHORIZATION=token_for(manager))
        self.assertEqual(r.status_code, 201, r.content[:200])

    def test_a_store_manager_cannot_write_a_dispatch(self):
        manager = mk('sm_disp', 'store_manager')
        item = StockItem.objects.create(code='SM-D', category='Solar Panel', opening_stock=10)
        r = self.client.post('/api/stock-dispatches/',
                             data={'item': item.id, 'date': '2026-08-04', 'quantity': '1', 'rate': '10'},
                             content_type='application/json', HTTP_AUTHORIZATION=token_for(manager))
        self.assertEqual(r.status_code, 403)

    def test_the_me_payload_matches_what_the_api_enforces(self):
        """The sidebar is built from this, so it has to agree with the server."""
        for role, expected in self.EXPECTED.items():
            user = mk(f'me_{role}', role)
            r = self.client.get('/api/users/me/', HTTP_AUTHORIZATION=token_for(user))
            self.assertEqual(r.status_code, 200, r.content[:200])
            self.assertEqual(r.json()['b2b_access'], expected, role)

    def test_the_unrestricted_roles_still_have_everything(self):
        for role in ('superadmin', 'coo', 'purchase_staff'):
            user = mk(f'un_{role}', role)
            for module, (url, _) in self.ENDPOINTS.items():
                self.assertTrue(self.can_read(user, url), f'{role} {module}')


class ItemDeleteWithMovementsTests(TestCase):
    """Deleting an item that still has stock movements behind it.

    Goods receipts have no screen of their own, so a refusal that says only
    "receipts or dispatches" sends people to empty the dispatch list and leave
    them still blocked by a GRN they cannot see. The refusal names the counts,
    and an admin can push the delete through and take the movements with it.
    """

    def setUp(self):
        self.superadmin = mk('id_super', 'superadmin')
        self.superadmin.is_superuser = True
        self.superadmin.is_staff = True
        self.superadmin.save()
        self.keeper = mk('id_keeper', 'store_manager')

        self.item = StockItem.objects.create(code='A-555-bi', category='Solar Panel',
                                             unit='Nos', opening_stock=Decimal('72'),
                                             unit_cost=Decimal('14485.50'))
        self.supplier = Vendor.objects.create(name='Adani')

    def receipt(self, qty='5.5'):
        return GoodsReceipt.objects.create(item=self.item, supplier=self.supplier,
                                           date=timezone.localdate(),
                                           quantity=Decimal(qty), rate=Decimal('14485.50'))

    def dispatch(self, qty='2'):
        return StockDispatch.objects.create(item=self.item, date=timezone.localdate(),
                                            quantity=Decimal(qty), rate=Decimal('15000'))

    def delete(self, user=None, force=False):
        url = f'/api/stock-items/{self.item.id}/' + ('?force=1' if force else '')
        return self.client.delete(url, HTTP_AUTHORIZATION=token_for(user or self.superadmin))

    # â”€â”€ The refusal says what is actually blocking â”€â”€
    def test_a_receipt_only_item_names_the_receipt(self):
        """The reported case: dispatches all deleted, a GRN still holding it."""
        self.receipt()
        r = self.delete()
        self.assertEqual(r.status_code, 400)
        body = r.json()
        self.assertIn('1 goods receipt', body['error'])
        self.assertNotIn('dispatch', body['error'].split('logged')[0])
        self.assertEqual((body['receipts'], body['dispatches']), (1, 0))

    def test_both_kinds_are_counted_separately(self):
        self.receipt()
        self.receipt()
        self.dispatch()
        body = self.delete().json()
        self.assertIn('2 goods receipts', body['error'])
        self.assertIn('1 dispatch', body['error'])
        self.assertEqual((body['receipts'], body['dispatches']), (2, 1))

    def test_the_plural_reads_properly_for_several_dispatches(self):
        self.dispatch()
        self.dispatch()
        self.assertIn('2 dispatches', self.delete().json()['error'])

    # â”€â”€ An item with nothing against it still deletes plainly â”€â”€
    def test_an_unused_item_deletes_without_a_force(self):
        r = self.delete()
        self.assertEqual(r.status_code, 204, r.content[:200])
        self.assertFalse(StockItem.objects.filter(pk=self.item.pk).exists())

    # â”€â”€ The way through â”€â”€
    def test_an_admin_is_told_they_can_confirm_again(self):
        self.receipt()
        body = self.delete().json()
        self.assertTrue(body['can_force'])
        self.assertIn('confirm again', body['error'])

    def test_forcing_takes_the_movements_with_it(self):
        self.receipt()
        self.dispatch()
        r = self.delete(force=True)
        self.assertEqual(r.status_code, 204, r.content[:200])
        self.assertFalse(StockItem.objects.filter(pk=self.item.pk).exists())
        self.assertFalse(GoodsReceipt.objects.filter(item_id=self.item.id).exists())
        self.assertFalse(StockDispatch.objects.filter(item_id=self.item.id).exists())

    def test_another_items_movements_are_left_alone(self):
        other = StockItem.objects.create(code='A-620-top', category='Solar Panel')
        GoodsReceipt.objects.create(item=other, date=timezone.localdate(),
                                    quantity=Decimal('108'), rate=Decimal('17000'))
        self.receipt()
        self.assertEqual(self.delete(force=True).status_code, 204)
        self.assertEqual(GoodsReceipt.objects.filter(item=other).count(), 1)

    # â”€â”€ Who may erase stock history â”€â”€
    def test_a_store_manager_cannot_force_it_through(self):
        """Write access to the item master is not licence to erase the ledger."""
        self.receipt()
        r = self.delete(user=self.keeper, force=True)
        self.assertEqual(r.status_code, 400, r.content[:200])
        self.assertFalse(r.json()['can_force'])
        self.assertTrue(StockItem.objects.filter(pk=self.item.pk).exists())
        self.assertTrue(GoodsReceipt.objects.filter(item=self.item).exists())

    def test_the_refusal_tells_a_storekeeper_who_can_do_it(self):
        self.receipt()
        self.assertIn('an admin', self.delete(user=self.keeper).json()['error'])

    # â”€â”€ The non-destructive alternative â”€â”€
    def test_an_item_with_history_can_be_retired_instead(self):
        self.receipt()
        r = self.client.patch(f'/api/stock-items/{self.item.id}/',
                              data={'is_active': False}, content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.superadmin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_active)
        # The history it was keeping is still there.
        self.assertTrue(GoodsReceipt.objects.filter(item=self.item).exists())



class DispatchPaymentGateTests(TestCase):
    """Verifying and dispatching are two acts.

    A delivery is raised first and waits: its goods stay in the warehouse,
    reserved rather than moved. Payment can arrive in instalments and each is
    verified as it comes. Only once the invoice is settled in full can the
    delivery be released, and that is what finally moves the stock.
    """

    def setUp(self):
        self.admin = mk('gate_admin', 'superadmin')
        self.customer = StockCustomer.objects.create(name='Sunrise Solar')
        self.panel = StockItem.objects.create(code='GT-PNL', category='Solar Panel',
                                              opening_stock=Decimal('100'),
                                              unit_cost=Decimal('10000'))
        self.cable = StockItem.objects.create(code='GT-CBL', category='Cable',
                                              opening_stock=Decimal('500'),
                                              unit_cost=Decimal('50'))

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.admin)}

    # goods 112000 + 6000 = 118000; +18% tax = 139240
    FULL = Decimal('139240.00')

    def body(self, payment=None, lines=None, tax='18'):
        rows = lines if lines is not None else [
            {'item': self.panel.id, 'quantity': '10', 'rate': '11200', 'serial_numbers': 'SN1-SN10'},
            {'item': self.cable.id, 'quantity': '100', 'rate': '60'},
        ]
        out = {'date': str(timezone.localdate()), 'customer': self.customer.id,
               'tax_percent': tax, 'site': 'Kochi site', 'lines': rows}
        if payment is not None:
            out['payment'] = payment
        return out

    def pay(self, amount, mode='bank', **extra):
        body = {'amount_received': str(amount), 'mode': mode,
                'reference': 'UTR7781', 'paid_on': str(timezone.localdate())}
        body.update(extra)
        return body

    def raise_dispatch(self, payment=None, **kwargs):
        return self.client.post('/api/stock-dispatches/dispatch/',
                                data=self.body(payment=payment, **kwargs),
                                content_type='application/json', **self.auth())

    def verify(self, invoice_no, payment, user=None):
        return self.client.post('/api/stock-dispatches/verify-payment/',
                                data={'invoice_no': invoice_no, 'payment': payment},
                                content_type='application/json', **self.auth(user))

    def release(self, invoice_no, user=None):
        return self.client.post('/api/stock-dispatches/release/',
                                data={'invoice_no': invoice_no},
                                content_type='application/json', **self.auth(user))

    def stock(self):
        self.panel.refresh_from_db()
        return self.panel

    def new_invoice(self, payment=None):
        r = self.raise_dispatch(payment)
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.json()['invoice_no']

    # ── Raising one ──
    def test_a_delivery_is_raised_pending(self):
        r = self.raise_dispatch()
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.json()['dispatched_lines'], 2)
        self.assertTrue(all(d.status == StockDispatch.PENDING
                            for d in StockDispatch.objects.all()))

    def test_a_pending_delivery_holds_its_stock_rather_than_moving_it(self):
        """The panels are still in the warehouse — spoken for, not gone."""
        self.raise_dispatch()
        item = self.stock()
        self.assertEqual(item.physical_stock, Decimal('100'))
        self.assertEqual(item.reserved, Decimal('10'))
        self.assertEqual(item.closing_stock, Decimal('90'))
        self.assertEqual(item.dispatched, Decimal('0'))

    def test_it_can_be_raised_with_no_payment_at_all(self):
        r = self.raise_dispatch()
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(DispatchPayment.objects.count(), 0)

    def test_it_can_be_raised_with_a_part_payment(self):
        invoice = self.new_invoice(self.pay('40000'))
        self.assertEqual(DispatchPayment.received_for(invoice_no=invoice), Decimal('40000'))

    def test_an_opening_payment_over_the_invoice_is_refused(self):
        r = self.raise_dispatch(self.pay('200000'))
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertEqual(StockDispatch.objects.count(), 0)
        self.assertEqual(DispatchPayment.objects.count(), 0)

    # ── Verifying, in parts ──
    def test_payments_add_up_across_instalments(self):
        invoice = self.new_invoice(self.pay('40000'))
        r = self.verify(invoice, self.pay('60000', mode='cash'))
        self.assertEqual(r.status_code, 201, r.content[:300])
        body = r.json()
        self.assertEqual(Decimal(body['amount_received']), Decimal('100000'))
        self.assertEqual(Decimal(body['balance']), self.FULL - Decimal('100000'))
        self.assertFalse(body['fully_paid'])
        self.assertEqual(len(body['payments']), 2)

    def test_the_last_instalment_settles_it(self):
        invoice = self.new_invoice(self.pay('40000'))
        body = self.verify(invoice, self.pay(self.FULL - Decimal('40000'))).json()
        self.assertTrue(body['fully_paid'])
        self.assertEqual(Decimal(body['balance']), Decimal('0'))

    def test_more_than_the_balance_is_refused(self):
        invoice = self.new_invoice(self.pay('40000'))
        r = self.verify(invoice, self.pay(self.FULL))
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertIn('still owing', r.json()['error'])

    def test_a_payment_of_nothing_is_refused(self):
        invoice = self.new_invoice()
        self.assertEqual(self.verify(invoice, self.pay('0')).status_code, 400)

    def test_a_made_up_mode_is_refused(self):
        invoice = self.new_invoice()
        self.assertEqual(self.verify(invoice, {'amount_received': '100', 'mode': 'iou'}).status_code, 400)

    def test_the_position_can_be_read_back(self):
        invoice = self.new_invoice(self.pay('40000'))
        r = self.client.get(f'/api/stock-dispatches/verify-payment/?invoice_no={invoice}',
                            **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Decimal(r.json()['amount_received']), Decimal('40000'))
        self.assertEqual(r.json()['status'], StockDispatch.PENDING)

    def test_an_unknown_invoice_is_not_found(self):
        self.assertEqual(self.verify('REN9999-IN999', self.pay('1')).status_code, 404)

    # ── Credit settles it ──
    def test_credit_counts_towards_the_invoice(self):
        """Recording the balance as credit is how goods go out on terms."""
        invoice = self.new_invoice(self.pay('40000'))
        body = self.verify(invoice, self.pay(self.FULL - Decimal('40000'), mode='credit')).json()
        self.assertTrue(body['fully_paid'])
        self.assertEqual(self.release(invoice).status_code, 200)

    def test_credit_is_still_recorded_as_credit(self):
        """It settles the invoice without pretending money arrived."""
        invoice = self.new_invoice(self.pay(self.FULL, mode='credit'))
        self.assertEqual(DispatchPayment.objects.get(invoice_no=invoice).mode, 'credit')

    # ── Releasing ──
    def test_it_will_not_release_while_anything_is_owing(self):
        invoice = self.new_invoice(self.pay('40000'))
        r = self.release(invoice)
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertIn('still owing', r.json()['error'])
        self.assertEqual(self.stock().dispatched, Decimal('0'))

    def test_a_settled_invoice_releases(self):
        invoice = self.new_invoice(self.pay(self.FULL))
        r = self.release(invoice)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(all(d.status == StockDispatch.RELEASED
                            for d in StockDispatch.objects.all()))
        self.assertIsNotNone(StockDispatch.objects.first().released_at)

    def test_releasing_is_what_moves_the_stock(self):
        invoice = self.new_invoice(self.pay(self.FULL))
        self.release(invoice)
        item = self.stock()
        self.assertEqual(item.dispatched, Decimal('10'))
        self.assertEqual(item.reserved, Decimal('0'))
        self.assertEqual(item.physical_stock, Decimal('90'))
        self.assertEqual(item.closing_stock, Decimal('90'))

    def test_what_is_left_to_sell_does_not_move_on_release(self):
        """It came off when the delivery was raised; releasing only turns the
        hold into a movement."""
        invoice = self.new_invoice(self.pay(self.FULL))
        before = self.stock().closing_stock
        self.release(invoice)
        self.assertEqual(self.stock().closing_stock, before)

    def test_it_cannot_be_released_twice(self):
        invoice = self.new_invoice(self.pay(self.FULL))
        self.release(invoice)
        r = self.release(invoice)
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertIn('already been dispatched', r.json()['error'])

    def test_a_released_delivery_takes_no_more_payments(self):
        invoice = self.new_invoice(self.pay(self.FULL))
        self.release(invoice)
        self.assertEqual(self.verify(invoice, self.pay('1')).status_code, 400)

    def test_releasing_an_unknown_invoice_is_not_found(self):
        self.assertEqual(self.release('REN9999-IN999').status_code, 404)

    # ── Who may ──
    def test_a_read_only_role_can_neither_verify_nor_release(self):
        watcher = mk('gate_watcher', 'store_manager')       # read on dispatch
        invoice = self.new_invoice(self.pay(self.FULL))
        self.assertEqual(self.verify(invoice, self.pay('1'), user=watcher).status_code, 403)
        self.assertEqual(self.release(invoice, user=watcher).status_code, 403)

    def test_accounts_b2b_may_run_the_whole_flow(self):
        clerk = mk('gate_clerk', 'accounts_b2b')
        r = self.client.post('/api/stock-dispatches/dispatch/',
                             data=self.body(payment=self.pay(self.FULL)),
                             content_type='application/json', **self.auth(clerk))
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(self.release(r.json()['invoice_no'], user=clerk).status_code, 200)

    # ── What the list shows ──
    def test_the_list_reports_where_a_delivery_stands(self):
        self.new_invoice(self.pay('40000'))
        rows = self.client.get('/api/stock-dispatches/', **self.auth()).json()
        rows = rows if isinstance(rows, list) else rows['results']
        self.assertTrue(all(r['status'] == StockDispatch.PENDING for r in rows))


class ProformaDispatchPaymentGateTests(TestCase):
    """The proforma is the other door, and it works the same way: payments are
    verified against it one at a time, and converting — which is what dispatches
    the goods — needs it settled in full."""

    def setUp(self):
        self.admin = mk('pgate_admin', 'superadmin')
        self.item = StockItem.objects.create(code='PG-PNL', category='Solar Panel',
                                             opening_stock=Decimal('100'),
                                             unit_cost=Decimal('10000'))
        self.quote = StockQuote.objects.create(quote_date=timezone.localdate(),
                                               tax_percent=Decimal('18'))
        StockQuoteItem.objects.create(quote=self.quote, item=self.item,
                                      quantity=Decimal('10'), unit_price=Decimal('11200'))
        self.total = Decimal('132160.00')          # 112000 + 18%

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def pay(self, amount, mode='upi'):
        return {'amount_received': str(amount), 'mode': mode,
                'reference': 'TXN44', 'paid_on': str(timezone.localdate())}

    def verify(self, payment):
        return self.client.post(f'/api/stock-quotes/{self.quote.id}/verify-payment/',
                                data={'payment': payment}, content_type='application/json',
                                **self.auth())

    def convert(self, payment=None):
        body = {} if payment is None else {'payment': payment}
        return self.client.post(f'/api/stock-quotes/{self.quote.id}/convert/', data=body,
                                content_type='application/json', **self.auth())

    def fresh(self):
        self.item.refresh_from_db()
        return self.item

    def test_a_part_payment_can_be_verified_against_it(self):
        r = self.verify(self.pay('50000'))
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(Decimal(r.json()['amount_received']), Decimal('50000'))
        self.assertFalse(r.json()['fully_paid'])

    def test_instalments_add_up(self):
        self.verify(self.pay('50000'))
        body = self.verify(self.pay('82160')).json()
        self.assertTrue(body['fully_paid'])
        self.assertEqual(len(body['payments']), 2)

    def test_it_will_not_convert_while_anything_is_owing(self):
        self.verify(self.pay('50000'))
        r = self.convert()
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertIn('still owing', r.json()['error'])
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'draft')
        self.assertEqual(StockDispatch.objects.count(), 0)

    def test_a_refused_convert_keeps_the_payment_already_verified(self):
        """The money did arrive; refusing the dispatch must not discard it."""
        self.verify(self.pay('50000'))
        self.convert()
        self.assertEqual(DispatchPayment.received_for(quote=self.quote), Decimal('50000'))

    def test_it_will_not_convert_with_nothing_paid(self):
        self.assertEqual(self.convert().status_code, 400)

    def test_a_settled_proforma_converts(self):
        self.verify(self.pay(self.total))
        r = self.convert()
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'converted')
        self.assertEqual(StockDispatch.objects.count(), 1)

    def test_the_last_instalment_can_come_with_the_dispatch(self):
        """So the screen can settle and send in one action."""
        self.verify(self.pay('50000'))
        r = self.convert(self.pay('82160'))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(StockDispatch.objects.count(), 1)

    def test_converting_moves_the_stock_for_real(self):
        self.verify(self.pay(self.total))
        self.convert()
        item = self.fresh()
        self.assertEqual(item.dispatched, Decimal('10'))
        self.assertEqual(item.reserved, Decimal('0'))
        self.assertEqual(item.closing_stock, Decimal('90'))

    def test_the_payments_follow_the_goods_onto_the_invoice(self):
        """They paid for a delivery; the delivery should carry its own history."""
        self.verify(self.pay('50000'))
        self.verify(self.pay('82160'))
        invoice_no = self.convert().json()['invoice_no']
        self.assertEqual(DispatchPayment.received_for(invoice_no=invoice_no), self.total)
        self.assertEqual(DispatchPayment.received_for(quote=self.quote), Decimal('0'))

    def test_credit_settles_a_proforma_too(self):
        self.verify(self.pay(self.total, mode='credit'))
        self.assertEqual(self.convert().status_code, 200)

    def test_a_converted_proforma_takes_no_more_payments(self):
        self.verify(self.pay(self.total))
        self.convert()
        self.assertEqual(self.verify(self.pay('1')).status_code, 400)

    def test_more_than_the_balance_is_refused(self):
        self.assertEqual(self.verify(self.pay(self.total + Decimal('1'))).status_code, 400)

    def test_the_position_can_be_read_back(self):
        self.verify(self.pay('50000'))
        r = self.client.get(f'/api/stock-quotes/{self.quote.id}/verify-payment/', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(Decimal(r.json()['balance']), self.total - Decimal('50000'))

    def test_a_discount_lowers_what_has_to_be_paid(self):
        self.quote.discount_percent = Decimal('10')
        self.quote.save()
        self.verify(self.pay(self.quote.total))
        self.assertEqual(self.convert().status_code, 200)


class StockReservationTests(TestCase):
    """Stock on a proforma invoice is reserved, not moved.

    The units stay in the warehouse — so the stock is still valued at them — but
    they come off what is left to sell, because a count that includes goods
    already promised to someone else is how the same panel gets sold twice.

    Nothing is stored: `reserved` is summed from the live proforma lines. That is
    what makes a release free — delete the proforma, decline it, or convert it,
    and the figure follows with nothing to unwind.
    """

    def setUp(self):
        self.admin = mk('res_admin', 'superadmin')
        self.customer = StockCustomer.objects.create(name='Bluebird Energy')
        self.item = StockItem.objects.create(code='RS-PNL', category='Solar Panel',
                                             opening_stock=Decimal('100'),
                                             unit_cost=Decimal('1000'), reorder_level=Decimal('5'))

    def auth(self):
        return {'HTTP_AUTHORIZATION': token_for(self.admin)}

    def quote(self, qty='10', status='draft'):
        q = StockQuote.objects.create(customer=self.customer, status=status,
                                      quote_date=timezone.localdate())
        StockQuoteItem.objects.create(quote=q, item=self.item, quantity=Decimal(qty),
                                      unit_price=Decimal('1200'))
        return q

    def fresh(self):
        self.item.refresh_from_db()
        return self.item

    def row(self):
        """The item as the Item Master screen receives it."""
        body = self.client.get('/api/stock-items/', **self.auth()).json()
        rows = body if isinstance(body, list) else body['results']
        return next(r for r in rows if r['code'] == 'RS-PNL')

    # ── The figure ──
    def test_nothing_is_reserved_to_begin_with(self):
        self.assertEqual(self.fresh().reserved, Decimal('0'))
        self.assertEqual(self.fresh().closing_stock, Decimal('100'))

    def test_a_proforma_reserves_its_lines(self):
        self.quote('10')
        self.assertEqual(self.fresh().reserved, Decimal('10'))

    def test_the_reservation_comes_off_what_is_left_to_sell(self):
        self.quote('10')
        self.assertEqual(self.fresh().closing_stock, Decimal('90'))

    def test_the_goods_are_still_in_the_warehouse(self):
        self.quote('10')
        self.assertEqual(self.fresh().physical_stock, Decimal('100'))

    def test_several_proformas_add_up(self):
        self.quote('10')
        self.quote('25')
        self.assertEqual(self.fresh().reserved, Decimal('35'))
        self.assertEqual(self.fresh().closing_stock, Decimal('65'))

    def test_two_lines_for_the_same_item_on_one_proforma_both_count(self):
        q = self.quote('10')
        StockQuoteItem.objects.create(quote=q, item=self.item, quantity=Decimal('5'),
                                      unit_price=Decimal('1200'))
        self.assertEqual(self.fresh().reserved, Decimal('15'))

    def test_a_sent_proforma_reserves_too(self):
        self.quote('10', status='sent')
        self.assertEqual(self.fresh().reserved, Decimal('10'))

    def test_an_accepted_proforma_reserves_too(self):
        self.quote('10', status='accepted')
        self.assertEqual(self.fresh().reserved, Decimal('10'))

    def test_a_declined_proforma_reserves_nothing(self):
        """The offer is off, so the goods are free again."""
        self.quote('10', status='declined')
        self.assertEqual(self.fresh().reserved, Decimal('0'))
        self.assertEqual(self.fresh().closing_stock, Decimal('100'))

    def test_declining_a_live_proforma_releases_its_hold(self):
        q = self.quote('10')
        self.assertEqual(self.fresh().reserved, Decimal('10'))
        q.status = 'declined'
        q.save(update_fields=['status'])
        self.assertEqual(self.fresh().reserved, Decimal('0'))
        self.assertEqual(self.fresh().closing_stock, Decimal('100'))

    # ── Releasing it ──
    def test_deleting_a_proforma_puts_the_stock_back(self):
        q = self.quote('10')
        self.assertEqual(self.fresh().closing_stock, Decimal('90'))
        r = self.client.delete(f'/api/stock-quotes/{q.id}/', **self.auth())
        self.assertEqual(r.status_code, 204, r.content[:200])
        self.assertEqual(self.fresh().reserved, Decimal('0'))
        self.assertEqual(self.fresh().closing_stock, Decimal('100'))

    def test_deleting_one_of_two_releases_only_its_own(self):
        keep = self.quote('10')
        drop = self.quote('25')
        self.client.delete(f'/api/stock-quotes/{drop.id}/', **self.auth())
        self.assertEqual(self.fresh().reserved, Decimal('10'))
        self.assertEqual(self.fresh().closing_stock, Decimal('90'))
        self.assertTrue(StockQuote.objects.filter(pk=keep.pk).exists())

    def test_removing_a_line_releases_that_line(self):
        q = self.quote('10')
        self.client.patch(f'/api/stock-quotes/{q.id}/',
                          data={'items': [{'item': self.item.id, 'quantity': '4',
                                           'unit_price': '1200'}]},
                          content_type='application/json', **self.auth())
        self.assertEqual(self.fresh().reserved, Decimal('4'))

    # ── The hand-off to a real movement ──
    def test_dispatching_it_turns_the_hold_into_a_movement(self):
        """Converting must not take the goods off twice — the hold is released in
        the same breath as the dispatch is written."""
        q = self.quote('10')
        self.client.post(f'/api/stock-quotes/{q.id}/convert/', data=paid_in_full(q),
                         content_type='application/json', **self.auth())
        item = self.fresh()
        self.assertEqual(item.reserved, Decimal('0'))
        self.assertEqual(item.dispatched, Decimal('10'))
        self.assertEqual(item.physical_stock, Decimal('90'))
        self.assertEqual(item.closing_stock, Decimal('90'))

    def test_what_is_left_to_sell_does_not_move_when_it_is_dispatched(self):
        """It was already deducted when the proforma was raised."""
        q = self.quote('10')
        before = self.fresh().closing_stock
        self.client.post(f'/api/stock-quotes/{q.id}/convert/', data=paid_in_full(q),
                         content_type='application/json', **self.auth())
        self.assertEqual(self.fresh().closing_stock, before)

    def test_a_dispatch_of_its_own_is_not_a_reservation(self):
        StockDispatch.objects.create(item=self.item, date=timezone.localdate(),
                                     quantity=Decimal('10'), rate=Decimal('1000'))
        self.assertEqual(self.fresh().reserved, Decimal('0'))
        self.assertEqual(self.fresh().closing_stock, Decimal('90'))

    # ── What it does and does not touch ──
    def test_the_stock_is_still_valued_at_the_reserved_goods(self):
        """A reserved panel is the company's until it is dispatched."""
        self.quote('10')
        self.assertEqual(self.fresh().stock_value, Decimal('100000'))    # 100 × 1000

    def test_reorder_watches_what_can_still_be_sold(self):
        """A shelf that is entirely promised away needs restocking just as much
        as an empty one."""
        self.assertFalse(self.fresh().needs_reorder)
        self.quote('96')                                 # 100 − 96 = 4, below 5
        self.assertTrue(self.fresh().needs_reorder)

    # ── What the screen receives ──
    def test_the_item_master_row_carries_the_reserved_figure(self):
        self.quote('10')
        row = self.row()
        self.assertEqual(Decimal(row['reserved']), Decimal('10'))
        self.assertEqual(Decimal(row['physical_stock']), Decimal('100'))
        self.assertEqual(Decimal(row['closing_stock']), Decimal('90'))

    def test_the_annotated_and_the_per_row_figures_agree(self):
        """The list annotates; a single item falls back to its own query. The two
        must not disagree, or the Item Master and a detail view would differ."""
        self.quote('10')
        self.assertEqual(Decimal(self.row()['reserved']), self.fresh().reserved)

    def test_the_reserved_figure_is_not_writable(self):
        self.quote('10')
        r = self.client.patch(f'/api/stock-items/{self.item.id}/',
                              data={'reserved': '0', 'closing_stock': '100'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(self.fresh().reserved, Decimal('10'))

    def test_reserving_more_than_the_shelf_holds_reads_as_negative(self):
        """Deliberately not clamped at zero: promising 120 of 100 panels is a
        real problem, and a figure of 0 would hide it."""
        self.quote('120')
        self.assertEqual(self.fresh().closing_stock, Decimal('-20'))
        self.assertTrue(self.fresh().needs_reorder)

    def test_a_proforma_for_another_item_does_not_reserve_this_one(self):
        other = StockItem.objects.create(code='RS-CBL', category='Cable',
                                         opening_stock=Decimal('500'))
        q = StockQuote.objects.create(customer=self.customer, quote_date=timezone.localdate())
        StockQuoteItem.objects.create(quote=q, item=other, quantity=Decimal('50'),
                                      unit_price=Decimal('45'))
        self.assertEqual(self.fresh().reserved, Decimal('0'))
        other.refresh_from_db()
        self.assertEqual(other.reserved, Decimal('50'))


class StockSummaryPeriodTests(TestCase):
    """The dashboard's movement figures answer for a chosen window.

    Stock on hand deliberately does not: items, stock value and the reorder list
    describe the warehouse as it stands, and no date range changes what is on the
    shelf today.
    """

    def setUp(self):
        self.admin = mk('sp_admin', 'superadmin')
        self.item = StockItem.objects.create(code='SP-PNL', category='Solar Panel',
                                             opening_stock=Decimal('1000'),
                                             unit_cost=Decimal('100'), reorder_level=Decimal('1'))
        today = timezone.localdate()
        self.today = today
        self.this_month = today.replace(day=1)
        # One movement in each window, so every period can be told apart.
        last_month_end = self.this_month - timedelta(days=1)
        self.last_year = date(today.year - 1, 6, 15)

        self.mk_dispatch(today, '3', '100')                  # this month
        self.mk_dispatch(last_month_end, '5', '100')         # earlier this year
        self.mk_dispatch(self.last_year, '7', '100')         # a previous year
        self.mk_receipt(today, '2', '50')
        self.mk_receipt(self.last_year, '4', '50')

    def mk_dispatch(self, when, qty, rate):
        return StockDispatch.objects.create(item=self.item, date=when,
                                            quantity=Decimal(qty), rate=Decimal(rate))

    def mk_receipt(self, when, qty, rate):
        return GoodsReceipt.objects.create(item=self.item, date=when,
                                           quantity=Decimal(qty), rate=Decimal(rate))

    def summary(self, query=''):
        r = self.client.get(f'/api/stock-summary/{query}',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()

    def sales(self, query=''):
        return Decimal(self.summary(query)['period_sales'])

    # ── The windows ──
    def test_it_reports_this_month_by_default(self):
        """What the dashboard showed before it could be asked for anything else."""
        d = self.summary()
        self.assertEqual(d['period'], 'this_month')
        self.assertEqual(Decimal(d['period_sales']), Decimal('300'))     # 3 x 100

    def test_all_time_takes_in_every_movement(self):
        d = self.summary('?period=all')
        self.assertEqual(d['period'], 'all')
        self.assertEqual(Decimal(d['period_sales']), Decimal('1500'))    # 3 + 5 + 7, x100
        self.assertIsNone(d['period_from'])

    def test_this_year_leaves_out_last_year(self):
        d = self.summary('?period=this_year')
        self.assertEqual(Decimal(d['period_sales']), Decimal('800'))     # 3 + 5, x100
        self.assertEqual(d['period_from'], date(self.today.year, 1, 1).isoformat())

    def test_a_custom_range_covers_exactly_its_own_days(self):
        d = self.summary(f'?period=custom&from={self.today}&to={self.today}')
        self.assertEqual(Decimal(d['period_sales']), Decimal('300'))

    def test_a_custom_range_can_reach_back_years(self):
        self.assertEqual(
            self.sales(f'?period=custom&from={self.last_year}&to={self.today}'),
            Decimal('1500'))

    def test_a_range_given_backwards_is_read_the_right_way_round(self):
        self.assertEqual(
            self.sales(f'?period=custom&from={self.today}&to={self.last_year}'),
            Decimal('1500'))

    def test_a_to_date_on_its_own_means_everything_up_to_it(self):
        self.assertEqual(self.sales(f'?period=custom&to={self.last_year}'), Decimal('700'))

    def test_a_range_with_nothing_in_it_reports_zero(self):
        far = date(self.today.year - 5, 1, 1)
        self.assertEqual(self.sales(f'?period=custom&from={far}&to={far}'), Decimal('0'))

    def test_an_unknown_period_falls_back_to_this_month(self):
        self.assertEqual(self.summary('?period=fortnight')['period'], 'this_month')

    def test_a_malformed_date_does_not_break_the_page(self):
        d = self.summary('?period=custom&from=not-a-date')
        self.assertEqual(d['period'], 'custom')

    # ── Receipts follow the window too ──
    def test_purchases_are_scoped_the_same_way(self):
        self.assertEqual(Decimal(self.summary()['period_purchases']), Decimal('100'))
        self.assertEqual(Decimal(self.summary('?period=all')['period_purchases']), Decimal('300'))

    def test_the_document_counts_follow_the_window(self):
        self.assertEqual(self.summary()['dispatch_count'], 1)
        self.assertEqual(self.summary('?period=all')['dispatch_count'], 3)
        self.assertEqual(self.summary('?period=all')['receipt_count'], 2)

    def test_proformas_are_counted_by_their_own_date(self):
        StockQuote.objects.create(quote_date=self.today, status='draft')
        StockQuote.objects.create(quote_date=self.last_year, status='draft')
        self.assertEqual(self.summary()['quote_count'], 1)
        self.assertEqual(self.summary('?period=all')['quote_count'], 2)

    # ── Stock on hand stands outside it ──
    def test_stock_on_hand_is_the_same_whatever_the_period(self):
        """It is what is on the shelf now; a date range cannot change that."""
        for query in ('', '?period=all', '?period=this_year',
                      f'?period=custom&from={self.today}&to={self.today}'):
            with self.subTest(query=query):
                d = self.summary(query)
                self.assertEqual(d['sku_count'], 1)
                # opening 1000 + received 6 - dispatched 15 = 991, at 100 each
                self.assertEqual(Decimal(d['total_value']), Decimal('99100'))

    # ── The chart ──
    def test_a_short_window_is_charted_a_day_at_a_time(self):
        """This month as a single monthly bar would say nothing."""
        months = self.summary()['monthly']
        self.assertEqual(len(months), self.today.day)
        self.assertEqual(months[-1]['name'], self.today.strftime('%d %b'))

    def test_a_long_window_falls_back_to_a_bar_a_month_and_is_capped(self):
        """All time here reaches back to last year, so it is charted monthly —
        and never more than a year of bars, which stops being readable."""
        months = self.summary('?period=all')['monthly']
        self.assertLessEqual(len(months), 12)
        self.assertGreater(len(months), 1)
        self.assertEqual(months[-1]['name'], self.today.strftime('%b %y'))

    def test_the_screen_is_told_what_window_it_is_looking_at(self):
        d = self.summary('?period=this_year')
        self.assertIn(str(self.today.year), d['period_label'])


class StockPaymentsModuleTests(TestCase):
    """Inventory → Payments: every document money has been verified against,
    in three sections that do not overlap."""

    URL = '/api/stock-payments/'

    def setUp(self):
        self.admin = mk('pay_admin', 'superadmin')
        self.customer = StockCustomer.objects.create(name='Bluebird Energy')
        self.item = StockItem.objects.create(code='PY-PNL', category='Solar Panel',
                                             opening_stock=Decimal('1000'),
                                             unit_cost=Decimal('100'))

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.admin)}

    def board(self, user=None, expect=200):
        r = self.client.get(self.URL, **self.auth(user))
        self.assertEqual(r.status_code, expect, r.content[:300])
        return r.json() if expect == 200 else None

    def rows(self, section, user=None):
        return self.board(user)['sections'][section]['rows']

    def numbers(self, section, user=None):
        return sorted(r['number'] for r in self.rows(section, user))

    def dispatch(self, invoice_no, qty='10', rate='100', tax='0'):
        StockDispatch.objects.create(invoice_no=invoice_no, date=timezone.localdate(),
                                     customer=self.customer, item=self.item,
                                     quantity=Decimal(qty), rate=Decimal(rate),
                                     tax_percent=Decimal(tax),
                                     status=StockDispatch.PENDING)
        return invoice_no

    def paid(self, amount, *, invoice_no=None, quote=None, mode='cash'):
        return DispatchPayment.objects.create(
            invoice_no=invoice_no or '', quote=quote,
            invoice_total=Decimal('1000'), amount_received=Decimal(amount),
            mode=mode, paid_on=timezone.localdate(), verified_by=self.admin)

    def proforma(self, number_hint='PF'):
        q = StockQuote.objects.create(customer=self.customer, quote_date=timezone.localdate())
        StockQuoteItem.objects.create(quote=q, item=self.item, quantity=Decimal('10'),
                                      unit_price=Decimal('100'))
        return q

    # ── The three sections ──
    def test_a_settled_invoice_reads_as_fully_paid(self):
        self.dispatch('IN-A')
        self.paid('1000', invoice_no='IN-A')
        self.assertEqual(self.numbers('fully_paid'), ['IN-A'])
        self.assertEqual(self.numbers('partially_paid'), [])

    def test_a_part_paid_invoice_reads_as_partially_paid(self):
        self.dispatch('IN-B')
        self.paid('400', invoice_no='IN-B')
        self.assertEqual(self.numbers('partially_paid'), ['IN-B'])
        row = self.rows('partially_paid')[0]
        self.assertEqual(Decimal(row['received']), Decimal('400'))
        self.assertEqual(Decimal(row['balance']), Decimal('600'))

    def test_anything_on_credit_reads_as_credit(self):
        """Credit settles an invoice, so without its own section it would sit
        under fully paid and hide that no money came in."""
        self.dispatch('IN-C')
        self.paid('1000', invoice_no='IN-C', mode='credit')
        self.assertEqual(self.numbers('credit'), ['IN-C'])
        self.assertEqual(self.numbers('fully_paid'), [])

    def test_part_cash_part_credit_counts_as_credit(self):
        self.dispatch('IN-D')
        self.paid('400', invoice_no='IN-D')
        self.paid('600', invoice_no='IN-D', mode='credit')
        self.assertEqual(self.numbers('credit'), ['IN-D'])
        self.assertEqual(self.numbers('fully_paid'), [])
        self.assertEqual(self.numbers('partially_paid'), [])

    def test_a_document_appears_in_exactly_one_section(self):
        for n, mode, amount in (('IN-E', 'cash', '1000'), ('IN-F', 'cash', '300'),
                                ('IN-G', 'credit', '1000')):
            self.dispatch(n)
            self.paid(amount, invoice_no=n, mode=mode)
        seen = [r['number'] for s in ('fully_paid', 'partially_paid', 'credit')
                for r in self.rows(s)]
        self.assertEqual(sorted(seen), ['IN-E', 'IN-F', 'IN-G'])
        self.assertEqual(len(seen), len(set(seen)))

    # ── What is on the board ──
    def test_a_delivery_with_no_payment_is_not_on_it(self):
        """It is a payments board; an unpaid delivery has nothing to show."""
        self.dispatch('IN-H')
        board = self.board()
        self.assertEqual(sum(board['sections'][s]['totals']['count']
                             for s in ('fully_paid', 'partially_paid', 'credit')), 0)

    def test_a_part_paid_proforma_is_on_it_too(self):
        """Its instalments have not moved onto an invoice yet, because there is
        no delivery until it is settled — leaving it out would hide part-paid
        business exactly while it is part-paid."""
        q = self.proforma()
        self.paid('400', quote=q)
        self.assertEqual(self.numbers('partially_paid'), [q.number])
        self.assertEqual(self.rows('partially_paid')[0]['kind'], 'proforma')

    def test_the_rows_carry_the_payments_behind_them(self):
        self.dispatch('IN-I')
        self.paid('400', invoice_no='IN-I')
        self.paid('600', invoice_no='IN-I', mode='upi')
        row = self.rows('fully_paid')[0]
        self.assertEqual(row['payment_count'], 2)
        self.assertEqual(row['modes'], ['cash', 'upi'])
        self.assertEqual(len(row['payments']), 2)
        self.assertEqual(row['payments'][0]['verified_by'], 'pay_admin')

    def test_a_row_says_whether_the_goods_have_gone(self):
        invoice = self.dispatch('IN-J')
        self.paid('1000', invoice_no=invoice)
        self.assertEqual(self.rows('fully_paid')[0]['status'], StockDispatch.PENDING)
        StockDispatch.objects.filter(invoice_no=invoice).update(status=StockDispatch.RELEASED)
        self.assertEqual(self.rows('fully_paid')[0]['status'], StockDispatch.RELEASED)

    def test_tax_is_part_of_what_is_owed(self):
        self.dispatch('IN-K', tax='18')            # 1000 + 18% = 1180
        self.paid('1000', invoice_no='IN-K')
        row = self.rows('partially_paid')[0]
        self.assertEqual(Decimal(row['invoice_total']), Decimal('1180'))
        self.assertEqual(Decimal(row['balance']), Decimal('180'))

    # ── The totals ──
    def test_each_section_totals_its_own_rows(self):
        self.dispatch('IN-L'); self.paid('1000', invoice_no='IN-L')
        self.dispatch('IN-M'); self.paid('250', invoice_no='IN-M')
        board = self.board()
        self.assertEqual(Decimal(board['sections']['fully_paid']['totals']['received']),
                         Decimal('1000'))
        partial = board['sections']['partially_paid']['totals']
        self.assertEqual(Decimal(partial['received']), Decimal('250'))
        self.assertEqual(Decimal(partial['balance']), Decimal('750'))

    def test_the_board_totals_everything_on_it(self):
        self.dispatch('IN-N'); self.paid('1000', invoice_no='IN-N')
        self.dispatch('IN-O'); self.paid('250', invoice_no='IN-O')
        self.assertEqual(Decimal(self.board()['totals']['received']), Decimal('1250'))
        self.assertEqual(self.board()['totals']['count'], 2)

    def test_an_empty_board_still_answers(self):
        board = self.board()
        self.assertEqual(board['totals']['count'], 0)
        for s in ('fully_paid', 'partially_paid', 'credit'):
            self.assertEqual(board['sections'][s]['rows'], [])

    def test_payments_outlive_the_delivery_they_paid_for(self):
        """Deleting the rows does not unmake the money; it still has to be seen."""
        self.dispatch('IN-P')
        self.paid('1000', invoice_no='IN-P')
        StockDispatch.objects.filter(invoice_no='IN-P').delete()
        self.assertEqual(self.numbers('fully_paid'), ['IN-P'])

    # ── Who may look ──
    def test_a_read_only_role_may_read_it(self):
        self.dispatch('IN-Q'); self.paid('1000', invoice_no='IN-Q')
        self.assertEqual(self.numbers('fully_paid', user=mk('pay_watch', 'store_manager')),
                         ['IN-Q'])

    def test_someone_with_no_dispatch_access_may_not(self):
        self.board(user=mk('pay_keeper', 'store_keeper'), expect=403)


class DocumentNumbersAreNeverReusedTests(TestCase):
    """A number, once on a document, must never appear on a second one.

    The counter is the fast path, but it can fall behind: the dispatch form lets
    an invoice number be typed by hand, and that number never passes through it.
    Two things keep the series honest — a supplied number is absorbed as it is
    saved, and issuing skips anything already in use.
    """

    def setUp(self):
        self.item = StockItem.objects.create(code='NUM-PNL', category='Solar Panel',
                                             opening_stock=Decimal('1000'),
                                             unit_cost=Decimal('100'))

    def dispatch(self, invoice_no='', when=None):
        return StockDispatch.objects.create(
            invoice_no=invoice_no, date=when or timezone.localdate(),
            item=self.item, quantity=Decimal('1'), rate=Decimal('100'))

    def numbers(self):
        return list(StockDispatch.objects.values_list('invoice_no', flat=True))

    # ── The ordinary path ──
    def test_numbers_run_in_sequence(self):
        self.assertTrue(self.dispatch().invoice_no.endswith('IN001'))
        self.assertTrue(self.dispatch().invoice_no.endswith('IN002'))

    def test_deleting_the_latest_invoice_hands_its_number_on(self):
        """Invoices run without gaps, so the next one takes the freed number —
        unless payments are still filed under it (InvoiceNumbersRunOnTests)."""
        first = self.dispatch()
        first.delete()
        self.assertTrue(self.dispatch().invoice_no.endswith('IN001'))

    # ── A number typed by hand ──
    def test_a_typed_number_moves_the_counter_past_itself(self):
        key = series_key('IN')
        self.dispatch(invoice_no=f'{key}007')
        self.assertTrue(self.dispatch().invoice_no.endswith('IN008'))

    def test_a_typed_number_is_never_issued_to_someone_else(self):
        """The bug this fixes: a hand-typed number the counter never saw, then
        re-issued to a different delivery weeks later."""
        key = series_key('IN')
        self.dispatch(invoice_no=f'{key}002')
        for _ in range(4):
            self.dispatch()
        self.assertEqual(len(set(self.numbers())), len(self.numbers()))

    def test_a_typed_number_below_the_counter_changes_nothing(self):
        self.dispatch()                       # IN001
        self.dispatch()                       # IN002
        key = series_key('IN')
        self.dispatch(invoice_no=f'{key}001')  # a row joining an existing delivery
        self.assertTrue(self.dispatch().invoice_no.endswith('IN003'))

    def test_a_number_from_another_series_is_left_alone(self):
        self.dispatch(invoice_no='SOMETHING-ELSE-99')
        self.assertTrue(self.dispatch().invoice_no.endswith('IN001'))

    # ── A counter that has already drifted ──
    def test_issuing_skips_a_number_already_in_use(self):
        """Self-healing: even with the counter behind, nothing collides."""
        key = series_key('IN')
        StockDispatch.objects.create(invoice_no=f'{key}001', date=timezone.localdate(),
                                     item=self.item, quantity=Decimal('1'), rate=Decimal('100'))
        # Wind the counter back, as if it had never seen that number.
        DocumentNumberSeries.objects.update_or_create(key=key, defaults={'last_seq': 0})
        self.assertTrue(self.dispatch().invoice_no.endswith('IN002'))
        self.assertEqual(len(set(self.numbers())), 2)

    def test_a_badly_drifted_counter_still_finds_a_free_number(self):
        key = series_key('IN')
        for seq in range(1, 6):
            StockDispatch.objects.create(invoice_no=f'{key}{seq:03d}',
                                         date=timezone.localdate(), item=self.item,
                                         quantity=Decimal('1'), rate=Decimal('100'))
        DocumentNumberSeries.objects.update_or_create(key=key, defaults={'last_seq': 0})
        self.assertTrue(self.dispatch().invoice_no.endswith('IN006'))

    # ── The whole delivery still shares one number ──
    def test_the_rows_of_one_delivery_keep_the_same_number(self):
        first = self.dispatch()
        second = self.dispatch(invoice_no=first.invoice_no)
        self.assertEqual(first.invoice_no, second.invoice_no)
        self.assertEqual(len(set(self.numbers())), 1)

    def test_a_row_never_ends_up_without_a_number(self):
        self.assertTrue(all(self.numbers()))


class InvoiceRoundOffTests(TestCase):
    """Invoices are billed in whole rupees, and that is the figure that settles.

    Nobody hands over 65 paise. The document carries the adjustment as its own
    line, and payment verification reconciles against the rounded total — an
    invoice paid to the rupee has to read as paid in full, or the goods never
    release.
    """

    def test_a_part_rupee_rounds_up_at_half(self):
        from inventory.models import round_off_for
        self.assertEqual(round_off_for(Decimal('95794.65')), (Decimal('95795'), Decimal('0.35')))

    def test_a_part_rupee_rounds_down_below_half(self):
        from inventory.models import round_off_for
        self.assertEqual(round_off_for(Decimal('153430.20')), (Decimal('153430'), Decimal('-0.20')))

    def test_exactly_half_rounds_up_not_to_even(self):
        """Decimal's default is banker's rounding, which is not what an invoice
        does — and the printed document and the payment screen must agree."""
        from inventory.models import round_off_for
        self.assertEqual(round_off_for(Decimal('94794.50'))[0], Decimal('94795'))
        self.assertEqual(round_off_for(Decimal('94795.50'))[0], Decimal('94796'))

    def test_a_whole_rupee_is_left_alone(self):
        from inventory.models import round_off_for
        self.assertEqual(round_off_for(Decimal('96138.00')), (Decimal('96138'), Decimal('0')))

    def test_nothing_rounds_to_nothing(self):
        from inventory.models import round_off_for
        self.assertEqual(round_off_for(Decimal('0'))[0], Decimal('0'))

    def test_the_printed_invoice_and_the_payment_screen_agree(self):
        """The bug this rounding is here to prevent."""
        from inventory.views import payment_state, totals_block
        exact = Decimal('94794.50')
        printed = totals_block(exact, Decimal('0'), Decimal('0'), exact)
        state = payment_state(exact, Decimal('0'))
        self.assertEqual(printed['grand_total'], state['invoice_total'])


class ProformaGrandTotalTests(TestCase):
    """The proforma invoice bills the rounded figure."""

    def setUp(self):
        from inventory.models import StockItem, StockQuote, StockQuoteItem
        self.quote = StockQuote.objects.create(tax_percent=Decimal('18'))
        item = StockItem.objects.create(code='RND-1')
        StockQuoteItem.objects.create(quote=self.quote, item=item,
                                      quantity=Decimal('3'), unit_price=Decimal('271.05'))

    def test_the_exact_total_is_still_the_exact_arithmetic(self):
        """Rounding sits on top; the tax maths underneath must not move."""
        self.assertEqual(self.quote.total, Decimal('959.517'))

    def test_the_grand_total_is_whole_rupees(self):
        self.assertEqual(self.quote.grand_total, Decimal('960'))

    def test_the_round_off_is_the_difference(self):
        self.assertEqual(self.quote.grand_total - self.quote.round_off, self.quote.total)

    def test_the_retail_proforma_rounds_the_same_way(self):
        from inventory.models import Quote, QuoteItem
        q = Quote.objects.create(tax_percent=Decimal('18'))
        QuoteItem.objects.create(quote=q, description='x', quantity=Decimal('3'),
                                 unit_price=Decimal('271.05'))
        self.assertEqual(q.grand_total, Decimal('960'))


class PaymentSettlesOnTheRoundedTotalTests(TestCase):
    """Paying the round rupee settles the invoice."""

    def state(self, total, received):
        from inventory.views import payment_state
        return payment_state(Decimal(total), Decimal(received))

    def test_paying_the_rounded_figure_settles_it(self):
        s = self.state('95794.65', '95795')
        self.assertTrue(s['fully_paid'])
        self.assertEqual(s['balance'], '0.00')

    def test_the_exact_total_is_still_reported(self):
        """The adjustment has to be visible, not silently absorbed."""
        s = self.state('95794.65', '0')
        self.assertEqual(s['invoice_total'], '95795.00')
        self.assertEqual(s['exact_total'], '95794.65')
        self.assertEqual(s['round_off'], '0.35')

    def test_a_rounded_down_invoice_owes_the_rounded_figure(self):
        s = self.state('153430.20', '0')
        self.assertEqual(s['invoice_total'], '153430.00')
        self.assertEqual(s['balance'], '153430.00')

    def test_paying_the_exact_paise_figure_still_settles_a_rounded_down_bill(self):
        s = self.state('153430.20', '153430.20')
        self.assertTrue(s['fully_paid'])

    def test_a_part_payment_is_still_short(self):
        s = self.state('95794.65', '50000')
        self.assertFalse(s['fully_paid'])
        self.assertEqual(s['balance'], '45795.00')

    def test_an_invoice_of_nothing_is_not_paid_in_full(self):
        self.assertFalse(self.state('0', '0')['fully_paid'])


class DispatchInvoiceRoundingTests(TestCase):
    """A delivery of several lines rounds once, on the invoice."""

    def setUp(self):
        from inventory.models import StockItem, StockDispatch
        self.item = StockItem.objects.create(code='RND-2')
        # Three lines that each carry paise: rounding them one by one would land
        # somewhere other than rounding their sum.
        for rate in ('333.33', '333.33', '333.34'):
            StockDispatch.objects.create(
                invoice_no='REN2627-IN001', item=self.item, quantity=Decimal('1'),
                rate=Decimal(rate), tax_percent=Decimal('0'),
                date=timezone.localdate())

    def rows(self):
        from inventory.models import StockDispatch
        from inventory.serializers import StockDispatchSerializer
        qs = StockDispatch.objects.filter(invoice_no='REN2627-IN001')
        return StockDispatchSerializer(qs, many=True).data

    def test_the_invoice_total_is_the_rounded_sum_of_the_lines(self):
        row = self.rows()[0]
        self.assertEqual(row['invoice_total'], '1000.00')

    def test_every_line_reports_the_same_invoice_position(self):
        """The customer pays for the delivery, not for one line of it."""
        totals = {r['invoice_total'] for r in self.rows()}
        self.assertEqual(totals, {'1000.00'})

    def test_the_line_totals_themselves_are_not_rounded(self):
        """The stock ledger values movements at their goods value."""
        self.assertEqual(sorted(r['total'] for r in self.rows()),
                         ['333.33', '333.33', '333.34'])

    def test_paying_the_rounded_invoice_clears_the_balance(self):
        from inventory.models import DispatchPayment
        DispatchPayment.objects.create(invoice_no='REN2627-IN001',
                                       invoice_total=Decimal('1000'),
                                       amount_received=Decimal('1000'), mode='cash',
                                       paid_on=timezone.localdate())
        row = self.rows()[0]
        self.assertEqual(row['balance'], '0.00')
        self.assertTrue(row['fully_paid'])


class RoundingMustNotStrandAnInvoiceTests(TestCase):
    """Either figure on the invoice clears it.

    A customer paid the exact 95,794.65 their copy showed. The bill rounds up to
    95,795, so the balance sat at 35 paise, the Dispatch button stayed dead and
    the goods could not leave — nobody is going to transfer 35 paise. The
    verification dialog meanwhile said the invoice was already settled, because
    it compared against the exact total while the screen compared against the
    rounded one. One rule now, in `settlement`.
    """

    def state(self, total, received):
        from inventory.views import payment_state
        return payment_state(Decimal(total), Decimal(received))

    # ── The reported bug ──
    def test_paying_the_exact_total_settles_an_invoice_that_rounded_up(self):
        s = self.state('95794.65', '95794.65')
        self.assertTrue(s['fully_paid'])
        self.assertEqual(s['balance'], '0.00')

    def test_paying_the_rounded_total_still_settles_it(self):
        s = self.state('95794.65', '95795')
        self.assertTrue(s['fully_paid'])
        self.assertEqual(s['balance'], '0.00')

    def test_the_invoice_is_still_billed_at_the_rounded_figure(self):
        """Settling leniently must not quietly change what was charged."""
        s = self.state('95794.65', '0')
        self.assertEqual(s['invoice_total'], '95795.00')
        self.assertEqual(s['balance'], '95795.00')

    # ── The other direction ──
    def test_paying_the_rounded_total_settles_an_invoice_that_rounded_down(self):
        s = self.state('153430.20', '153430')
        self.assertTrue(s['fully_paid'])

    def test_paying_the_exact_total_settles_a_rounded_down_invoice_too(self):
        self.assertTrue(self.state('153430.20', '153430.20')['fully_paid'])

    # ── What must still be refused ──
    def test_a_rupee_short_is_not_settled(self):
        """The leniency is the rounding adjustment, not a general tolerance."""
        s = self.state('95794.65', '95793.65')
        self.assertFalse(s['fully_paid'])

    def test_a_part_payment_is_still_a_part_payment(self):
        s = self.state('95794.65', '50000')
        self.assertFalse(s['fully_paid'])
        self.assertEqual(s['balance'], '45795.00')

    def test_an_invoice_of_nothing_is_not_settled_by_nothing(self):
        self.assertFalse(self.state('0', '0')['fully_paid'])

    # ── The dialog and the screen must agree ──
    def test_the_intake_guard_agrees_that_it_is_settled(self):
        """The dialog said 'already settled' while the screen showed money
        owing; both now read the same figure."""
        from inventory.views import check_payment, payment_state
        kwargs, error = check_payment({'amount_received': '0.35', 'mode': 'cash'},
                                       Decimal('95794.65'), Decimal('95794.65'))
        self.assertIsNone(kwargs)
        self.assertIn('already been settled', error['error'])
        self.assertTrue(payment_state(Decimal('95794.65'), Decimal('95794.65'))['fully_paid'])

    def test_a_genuine_balance_is_still_collectable(self):
        from inventory.views import check_payment
        kwargs, error = check_payment({'amount_received': '45795', 'mode': 'cash'},
                                       Decimal('95794.65'), Decimal('50000'))
        self.assertIsNone(error)
        self.assertEqual(kwargs['amount_received'], Decimal('45795.00'))

    def test_paying_more_than_is_owed_is_still_refused(self):
        from inventory.views import check_payment
        _kwargs, error = check_payment({'amount_received': '900000', 'mode': 'cash'},
                                        Decimal('95794.65'), Decimal('0'))
        self.assertIn('more than', error['error'])


class SettledDeliveryReleasesTests(TestCase):
    """A settled delivery can actually go out."""

    def setUp(self):
        from inventory.models import StockItem, StockDispatch
        item = StockItem.objects.create(code='RND-3')
        # 3 x 31931.55 = 95794.65, which rounds up to 95795.
        for _ in range(3):
            StockDispatch.objects.create(
                invoice_no='REN2627-IN009', item=item, quantity=Decimal('1'),
                rate=Decimal('31931.55'), tax_percent=Decimal('0'),
                status=StockDispatch.PENDING, date=timezone.localdate())

    def rows(self):
        from inventory.models import StockDispatch
        from inventory.serializers import StockDispatchSerializer
        return StockDispatchSerializer(
            StockDispatch.objects.filter(invoice_no='REN2627-IN009'), many=True).data

    def pay(self, amount):
        from inventory.models import DispatchPayment
        DispatchPayment.objects.create(
            invoice_no='REN2627-IN009', invoice_total=Decimal('95795'),
            amount_received=Decimal(amount), mode='bank_transfer',
            paid_on=timezone.localdate())

    def test_the_exact_payment_marks_the_delivery_paid(self):
        self.pay('95794.65')
        row = self.rows()[0]
        self.assertTrue(row['fully_paid'])
        self.assertEqual(row['balance'], '0.00')

    def test_an_unpaid_delivery_still_shows_its_balance(self):
        row = self.rows()[0]
        self.assertFalse(row['fully_paid'])
        self.assertEqual(row['balance'], '95795.00')

    def test_a_short_payment_leaves_it_owing(self):
        self.pay('90000')
        row = self.rows()[0]
        self.assertFalse(row['fully_paid'])
        self.assertEqual(row['balance'], '5795.00')


class StockItemHistoryTests(TestCase):
    """Where an item's stock came from.

    Goods receipts have no screen of their own, so the Item Master's IN column
    is otherwise a total with nothing behind it.
    """

    def setUp(self):
        from inventory.models import GoodsReceipt, StockItem, Vendor
        self.GoodsReceipt = GoodsReceipt
        # The Item Master is a B2B screen: the plain admin role has no access
        # to it, so the history behind it follows the same gate.
        self.boss = mk('hist_admin', 'superadmin')
        self.item = StockItem.objects.create(code='HIST-1', opening_stock=Decimal('10'),
                                             unit_cost=Decimal('100'), unit='Nos')
        self.vendor = Vendor.objects.create(name='Acme Supplies')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.boss)}

    def add(self, qty, **kw):
        return self.GoodsReceipt.objects.create(
            item=self.item, quantity=Decimal(qty), rate=kw.pop('rate', Decimal('100')),
            date=kw.pop('date', date(2026, 8, 3)), **kw)

    def history(self, user=None):
        r = self.client.get(f'/api/stock-items/{self.item.id}/history/', **self.auth(user))
        return r.status_code, (r.json() if r.status_code == 200 else {})

    def test_opening_stock_leads_the_list(self):
        """It is a quantity the item started with, and leaving it out would make
        the entries fail to add up to the total."""
        _, d = self.history()
        self.assertEqual(d['entries'][-1]['kind'], 'opening')
        self.assertEqual(d['entries'][-1]['quantity'], '10.00')

    def test_an_item_with_no_opening_stock_has_no_opening_entry(self):
        from inventory.models import StockItem
        self.item = StockItem.objects.create(code='HIST-2', opening_stock=Decimal('0'))
        self.add('5')
        _, d = self.history()
        self.assertEqual([e['kind'] for e in d['entries']], ['receipt'])

    def test_every_addition_is_listed(self):
        self.add('1')
        self.add('2')
        _, d = self.history()
        self.assertEqual(len([e for e in d['entries'] if e['kind'] == 'receipt']), 2)

    def test_the_newest_addition_comes_first(self):
        self.add('1', date=date(2026, 8, 1))
        self.add('7', date=date(2026, 8, 9))
        _, d = self.history()
        self.assertEqual(d['entries'][0]['quantity'], '7.00')

    def test_the_running_total_accumulates_in_arrival_order(self):
        """Newest first for reading, but the total was built oldest first."""
        self.add('1', date=date(2026, 8, 1))
        self.add('2', date=date(2026, 8, 2))
        _, d = self.history()
        self.assertEqual([e['running_total'] for e in d['entries']],
                         ['13.00', '11.00', '10.00'])

    def test_the_running_total_is_stock_added_not_stock_left(self):
        """Netting off dispatches here would be wrong on every line."""
        from inventory.models import StockDispatch
        self.add('5')
        StockDispatch.objects.create(item=self.item, quantity=Decimal('4'),
                                     rate=Decimal('100'), date=date(2026, 8, 5))
        _, d = self.history()
        self.assertEqual(d['entries'][0]['running_total'], '15.00')

    def test_the_supplier_and_reference_come_through(self):
        self.add('3', supplier=self.vendor, grn_no='GRN-77')
        _, d = self.history()
        entry = d['entries'][0]
        self.assertEqual(entry['supplier'], 'Acme Supplies')
        self.assertEqual(entry['reference'], 'GRN-77')

    def test_who_added_it_is_recorded_when_known(self):
        self.add('3', created_by=self.boss)
        _, d = self.history()
        self.assertEqual(d['entries'][0]['added_by'], 'hist_admin')

    def test_a_receipt_with_no_supplier_does_not_break_the_list(self):
        self.add('3')
        status_code, d = self.history()
        self.assertEqual(status_code, 200)
        self.assertEqual(d['entries'][0]['supplier'], '')

    def test_the_amount_is_quantity_times_rate(self):
        self.add('3', rate=Decimal('250'))
        _, d = self.history()
        self.assertEqual(d['entries'][0]['amount'], '750.00')

    def test_the_summary_reconciles_with_the_item_row(self):
        """The modal must not appear to contradict the row it opened from."""
        from inventory.models import StockDispatch
        self.add('3')
        StockDispatch.objects.create(item=self.item, quantity=Decimal('4'),
                                     rate=Decimal('100'), date=date(2026, 8, 5))
        _, d = self.history()
        s = d['summary']
        self.assertEqual(s['opening_stock'], '10.00')
        self.assertEqual(s['total_added'], '3.00')
        self.assertEqual(s['total_in'], '13.00')
        self.assertEqual(s['dispatched'], '4.00')
        self.assertEqual(s['physical_stock'], '9.00')

    def test_the_item_is_named_so_the_modal_can_title_itself(self):
        _, d = self.history()
        self.assertEqual(d['item']['code'], 'HIST-1')

    def test_an_item_with_nothing_at_all_returns_an_empty_list(self):
        from inventory.models import StockItem
        self.item = StockItem.objects.create(code='HIST-3', opening_stock=Decimal('0'))
        status_code, d = self.history()
        self.assertEqual(status_code, 200)
        self.assertEqual(d['entries'], [])

    def test_a_stranger_cannot_read_it(self):
        r = self.client.get(f'/api/stock-items/{self.item.id}/history/')
        self.assertIn(r.status_code, (401, 403))


class DeleteVerifiedPaymentTests(TestCase):
    """Undoing a payment that should never have been recorded.

    Super admin only: a verified payment decides whether an invoice is settled,
    whether goods may leave, and what the revenue figures say.
    """

    def setUp(self):
        from inventory.models import DispatchPayment, StockDispatch, StockItem
        self.DispatchPayment, self.StockDispatch = DispatchPayment, StockDispatch
        self.boss = mk('pay_super', 'superadmin')
        self.item = StockItem.objects.create(code='PAYDEL-1')
        self.dispatch = StockDispatch.objects.create(
            invoice_no='REN2627-IN900', item=self.item, quantity=Decimal('1'),
            rate=Decimal('1000'), tax_percent=Decimal('0'), date=date(2026, 8, 20),
            status=StockDispatch.RELEASED)

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.boss)}

    def pay(self, amount='1000', mode='cash'):
        return self.DispatchPayment.objects.create(
            invoice_no='REN2627-IN900', invoice_total=Decimal('1000'),
            amount_received=Decimal(amount), mode=mode, paid_on=date(2026, 8, 20))

    def delete(self, payment, user=None):
        return self.client.delete(f'/api/stock-payments/{payment.pk}/', **self.auth(user))

    # ── Who may ──
    def test_a_super_admin_may_delete_one(self):
        p = self.pay()
        r = self.delete(p)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertFalse(self.DispatchPayment.objects.filter(pk=p.pk).exists())

    def test_an_admin_may_not(self):
        """It sits above the admin tier, not beside it."""
        p = self.pay()
        r = self.delete(p, user=mk('pay_admin', 'admin'))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(self.DispatchPayment.objects.filter(pk=p.pk).exists())

    def test_a_spectator_may_not(self):
        p = self.pay()
        self.assertIn(self.delete(p, user=mk('pay_spec', 'spectator')).status_code, (403,))
        self.assertTrue(self.DispatchPayment.objects.filter(pk=p.pk).exists())

    def test_a_stranger_may_not(self):
        p = self.pay()
        r = self.client.delete(f'/api/stock-payments/{p.pk}/')
        self.assertIn(r.status_code, (401, 403))
        self.assertTrue(self.DispatchPayment.objects.filter(pk=p.pk).exists())

    # ── What it does to the money ──
    def test_the_invoice_stops_being_settled(self):
        p = self.pay('1000')
        r = self.delete(p).json()
        self.assertEqual(r['amount_received'], '0.00')
        self.assertEqual(r['balance'], '1000.00')
        self.assertFalse(r['fully_paid'])

    def test_only_the_one_payment_goes(self):
        keep, drop = self.pay('600'), self.pay('400')
        r = self.delete(drop).json()
        self.assertTrue(self.DispatchPayment.objects.filter(pk=keep.pk).exists())
        self.assertEqual(r['amount_received'], '600.00')

    def test_the_reply_names_the_document_and_the_amount(self):
        r = self.delete(self.pay('250')).json()
        self.assertEqual(r['document'], 'REN2627-IN900')
        self.assertEqual(r['amount_removed'], '250.00')

    # ── What it deliberately does not do ──
    def test_a_released_delivery_is_not_pulled_back(self):
        """The goods physically went out; reverting would put stock back on the
        shelf that is not there."""
        r = self.delete(self.pay()).json()
        self.dispatch.refresh_from_db()
        self.assertEqual(self.dispatch.status, self.StockDispatch.RELEASED)
        self.assertTrue(r['still_released'])
        self.assertIn('delivery stands', r['note'])

    def test_a_pending_delivery_says_nothing_about_release(self):
        self.StockDispatch.objects.filter(pk=self.dispatch.pk).update(
            status=self.StockDispatch.PENDING)
        r = self.delete(self.pay()).json()
        self.assertFalse(r['still_released'])
        self.assertIsNone(r['note'])

    def test_the_stock_movement_itself_survives(self):
        self.delete(self.pay())
        self.assertTrue(self.StockDispatch.objects.filter(pk=self.dispatch.pk).exists())

    # ── Edges ──
    def test_deleting_the_same_payment_twice_is_not_found(self):
        p = self.pay()
        self.assertEqual(self.delete(p).status_code, 200)
        self.assertEqual(self.delete(p).status_code, 404)

    def test_a_proforma_payment_can_be_deleted_too(self):
        from inventory.models import StockQuote, StockQuoteItem
        quote = StockQuote.objects.create(quote_date=date(2026, 8, 20))
        StockQuoteItem.objects.create(quote=quote, item=self.item,
                                      quantity=Decimal('1'), unit_price=Decimal('500'))
        p = self.DispatchPayment.objects.create(
            quote=quote, invoice_total=Decimal('500'), amount_received=Decimal('500'),
            mode='cash', paid_on=date(2026, 8, 20))
        r = self.delete(p)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r.json()['document'], quote.number)
        self.assertEqual(r.json()['amount_received'], '0.00')

    def test_the_payments_module_drops_the_document_once_nothing_is_left(self):
        """It lists documents money has been verified against."""
        p = self.pay()
        before = self.client.get('/api/stock-payments/', **self.auth()).json()
        rows = [r['number'] for s in before['sections'].values() for r in s['rows']]
        self.assertIn('REN2627-IN900', rows)
        self.delete(p)
        after = self.client.get('/api/stock-payments/', **self.auth()).json()
        rows = [r['number'] for s in after['sections'].values() for r in s['rows']]
        self.assertNotIn('REN2627-IN900', rows)


class ProjectTests(TestCase):
    """Projects — the retail side's bundles of products.

    A project is a specification, not a price list, and the point of the whole
    design is that a proforma gets its *own copy* of one. Most of what is worth
    testing here is that the copy stays a copy.
    """

    def setUp(self):
        self.admin = mk('proj_admin', 'admin')
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.admin)}

    def post(self, url, body, user=None):
        return self.client.post(url, data=body, content_type='application/json',
                                **self.auth(user))

    def patch(self, url, body, user=None):
        return self.client.patch(url, data=body, content_type='application/json',
                                 **self.auth(user))

    LINES = [
        {'item_name': 'Topcon Module 545W',
         'brand': 'Adani / Premier / Waaree', 'quantity': '10 Nos', 'position': 0},
        {'item_name': '5kVA Single Phase',
         'brand': 'FOX ESS', 'quantity': '1 Nos', 'position': 0},
        {'item_name': 'GI Structure 16G',
         'brand': '', 'quantity': '1 Set', 'position': 0},
        {'item_name': 'DC Cable',
         'brand': 'POLYCAB, LAPP', 'quantity': '36 M', 'position': 0},
        {'item_name': 'Earthing',
         'brand': 'EXCEL', 'quantity': '10 SWG DC Earthing, 10 SWG AC Earthing', 'position': 1},
    ]

    def make_project(self, name='5kW Single Phase On-Grid', lines=None):
        r = self.post('/api/projects/', {'name': name, 'capacity': '5kVA Single Phase',
                                         'lines': self.LINES if lines is None else lines})
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.json()

    def make_quote(self, project_id=None, **extra):
        body = {'quote_date': '2026-08-31', **extra}
        if project_id is not None:
            body['project'] = project_id
        r = self.post('/api/quotes/', body)
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.json()

    def line(self, doc, item_name):
        key = 'lines' if 'lines' in doc else 'spec_lines'
        return next((l for l in doc[key] if l['item_name'] == item_name), None)

    # ── The project itself ──
    def test_a_project_holds_its_lines(self):
        project = self.make_project()
        self.assertEqual(project['line_count'], 5)
        self.assertEqual(self.line(project, 'DC Cable')['brand'], 'POLYCAB, LAPP')

    def test_every_line_is_kept(self):
        project = self.make_project()
        self.assertEqual([l['item_name'] for l in project['lines']],
                         ['Topcon Module 545W', '5kVA Single Phase', 'GI Structure 16G',
                          'DC Cable', 'Earthing'])

    def test_quantity_keeps_whatever_the_sheet_says(self):
        """A real specification says "1 Each", "36 M" and a sentence about
        earthing in neighbouring rows; a number could not hold the third."""
        project = self.make_project()
        self.assertEqual(self.line(project, 'Earthing')['quantity'],
                         '10 SWG DC Earthing, 10 SWG AC Earthing')

    def test_lines_come_back_in_the_order_they_were_arranged(self):
        project = self.make_project()
        names = [l['item_name'] for l in project['lines']]
        self.assertLess(names.index('DC Cable'), names.index('Earthing'))

    def test_editing_a_project_replaces_its_sheet(self):
        project = self.make_project()
        r = self.patch(f"/api/projects/{project['id']}/",
                       {'lines': [{'item_name': 'Mono PERC 440W',
                                   'brand': 'Waaree', 'quantity': '12 Nos', 'position': 0}]})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['line_count'], 1)

    def test_saving_a_project_without_lines_leaves_them_alone(self):
        """Renaming a project must not empty it."""
        project = self.make_project()
        r = self.patch(f"/api/projects/{project['id']}/", {'name': 'Renamed'})
        self.assertEqual(r.json()['line_count'], 5)

    def test_a_project_can_be_duplicated_with_its_lines(self):
        """Packages differ by one cable length far more often than they differ
        wholly, and retyping thirty lines is how a specification picks up
        mistakes."""
        project = self.make_project()
        r = self.post(f"/api/projects/{project['id']}/duplicate/", {})
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.json()['line_count'], 5)
        self.assertIn('copy', r.json()['name'])
        self.assertNotEqual(r.json()['id'], project['id'])

    def test_retired_projects_are_not_offered(self):
        project = self.make_project()
        self.patch(f"/api/projects/{project['id']}/", {'is_active': False})
        listed = self.client.get('/api/projects/', **self.auth()).json()
        rows = listed if isinstance(listed, list) else listed['results']
        self.assertEqual([p for p in rows if p['id'] == project['id']], [])
        # Still reachable when the whole list is asked for, so it can be revived.
        everything = self.client.get('/api/projects/?all=true', **self.auth()).json()
        rows = everything if isinstance(everything, list) else everything['results']
        self.assertTrue(any(p['id'] == project['id'] for p in rows))

    # ── Picking one on a proforma ──
    def test_choosing_a_project_copies_its_sheet_onto_the_quote(self):
        project = self.make_project()
        quote = self.make_quote(project['id'])
        self.assertEqual(len(quote['spec_lines']), 5)
        self.assertEqual(quote['project_name'], project['name'])

    def test_a_quote_with_no_project_has_no_sheet(self):
        self.assertEqual(self.make_quote()['spec_lines'], [])

    def test_editing_the_quotes_sheet_does_not_touch_the_project(self):
        """The whole reason the quote keeps a copy. Tuning one customer's
        specification must not rewrite every other quote built from the same
        project — including ones already sent."""
        project = self.make_project()
        quote = self.make_quote(project['id'])
        edited = [dict(l, quantity='48 M') if l['item_name'] == 'DC Cable' else dict(l)
                  for l in quote['spec_lines']]
        r = self.patch(f"/api/quotes/{quote['id']}/", {'spec_lines': edited})
        self.assertEqual(self.line(r.json(), 'DC Cable')['quantity'], '48 M')

        back = self.client.get(f"/api/projects/{project['id']}/", **self.auth()).json()
        self.assertEqual(self.line(back, 'DC Cable')['quantity'], '36 M')

    def test_re_saving_a_quote_keeps_the_edits_made_to_its_sheet(self):
        """Changing the status must not silently restore the project's version."""
        project = self.make_project()
        quote = self.make_quote(project['id'])
        edited = [dict(l, quantity='48 M') if l['item_name'] == 'DC Cable' else dict(l)
                  for l in quote['spec_lines']]
        self.patch(f"/api/quotes/{quote['id']}/", {'spec_lines': edited})
        again = self.patch(f"/api/quotes/{quote['id']}/", {'status': 'sent'})
        self.assertEqual(self.line(again.json(), 'DC Cable')['quantity'], '48 M')

    def test_re_saving_with_the_same_project_keeps_the_edits(self):
        """The form sends `project` on every save; only a *change* re-copies."""
        project = self.make_project()
        quote = self.make_quote(project['id'])
        edited = [dict(l, quantity='48 M') if l['item_name'] == 'DC Cable' else dict(l)
                  for l in quote['spec_lines']]
        self.patch(f"/api/quotes/{quote['id']}/", {'spec_lines': edited})
        again = self.patch(f"/api/quotes/{quote['id']}/", {'project': project['id']})
        self.assertEqual(self.line(again.json(), 'DC Cable')['quantity'], '48 M')

    def test_switching_to_another_project_brings_that_sheet_across(self):
        first = self.make_project()
        second = self.make_project(name='3kW On-Grid', lines=[
            {'item_name': 'Mono PERC 440W', 'brand': 'Waaree',
             'quantity': '7 Nos', 'position': 0}])
        quote = self.make_quote(first['id'])
        r = self.patch(f"/api/quotes/{quote['id']}/", {'project': second['id']})
        self.assertEqual(len(r.json()['spec_lines']), 1)
        self.assertIsNotNone(self.line(r.json(), 'Mono PERC 440W'))

    def test_changing_a_project_does_not_reach_into_quotes_already_built(self):
        """A document a customer is holding must not change under them."""
        project = self.make_project()
        quote = self.make_quote(project['id'])
        self.patch(f"/api/projects/{project['id']}/",
                   {'lines': [{'item_name': 'Something else',
                               'brand': '', 'quantity': '1', 'position': 0}]})
        back = self.client.get(f"/api/quotes/{quote['id']}/", **self.auth()).json()
        self.assertEqual(len(back['spec_lines']), 5)
        self.assertIsNotNone(self.line(back, 'DC Cable'))

    def test_deleting_a_project_leaves_the_issued_sheet_standing(self):
        project = self.make_project()
        quote = self.make_quote(project['id'])
        self.client.delete(f"/api/projects/{project['id']}/", **self.auth())
        back = self.client.get(f"/api/quotes/{quote['id']}/", **self.auth()).json()
        self.assertIsNone(back['project'])              # the link is gone
        self.assertEqual(len(back['spec_lines']), 5)    # what was quoted is not

    def test_a_project_counts_the_quotes_built_from_it(self):
        project = self.make_project()
        self.make_quote(project['id'])
        self.make_quote(project['id'])
        back = self.client.get(f"/api/projects/{project['id']}/", **self.auth()).json()
        self.assertEqual(back['quoted_count'], 2)

    # ── Price and tax ──
    def priced(self, price, tax, inclusive, non_dcr=None):
        r = self.post('/api/projects/', {
            'name': f'P {price}/{tax}/{inclusive}',
            'price_dcr': price, 'price_non_dcr': non_dcr if non_dcr is not None else price,
            'tax_percent': tax, 'price_includes_tax': inclusive})
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.json()

    def figures(self, project, variant='dcr'):
        return project['pricing'][variant]

    def test_a_tax_exclusive_price_has_tax_added_to_it(self):
        f = self.figures(self.priced('180000', '18', False))
        self.assertEqual(f['base_amount'], '180000.00')
        self.assertEqual(f['tax_amount'], '32400.00')
        self.assertEqual(f['total'], '212400.00')

    def test_a_tax_inclusive_price_has_the_tax_taken_out_of_it(self):
        """With the box ticked, the price is what the customer was quoted and
        must come back exactly."""
        f = self.figures(self.priced('180000', '18', True))
        self.assertEqual(f['total'], '180000.00')
        self.assertEqual(f['base_amount'], '152542.37')
        self.assertEqual(f['tax_amount'], '27457.63')

    def test_the_parts_always_add_up_to_the_total(self):
        """A proforma that misses by a paisa is the sort of thing a customer
        notices first, so tax is the difference rather than its own rounding."""
        from decimal import Decimal
        for price in ('180000', '99999.99', '1', '123456.78', '7777.77'):
            for tax in ('18', '5', '12.5', '0'):
                for inclusive in (True, False):
                    p = self.priced(price, tax, inclusive)
                    for variant in ('dcr', 'non_dcr'):
                        f = self.figures(p, variant)
                        self.assertEqual(
                            Decimal(f['base_amount']) + Decimal(f['tax_amount']),
                            Decimal(f['total']),
                            f'{price} @ {tax}% inclusive={inclusive} {variant}')

    def test_no_tax_rate_means_the_price_is_the_total_either_way(self):
        for inclusive in (True, False):
            f = self.figures(self.priced('180000', '0', inclusive))
            self.assertEqual(f['total'], '180000.00')
            self.assertEqual(f['tax_amount'], '0.00')

    # ── Picking one prices the invoice ──
    def test_choosing_a_project_prices_the_invoice(self):
        project = self.priced('180000', '18', False)
        quote = self.make_quote(project['id'])
        self.assertEqual(len(quote['items']), 1)
        self.assertEqual(quote['tax_percent'], '18.00')
        self.assertEqual(quote['total'], '212400.00')

    def test_a_tax_inclusive_project_lands_on_the_same_total(self):
        """The line is priced at the base with the rate on the document, so the
        invoice's own arithmetic reaches the figure the project quotes rather
        than taxing a tax-inclusive price a second time."""
        project = self.priced('180000', '18', True)
        quote = self.make_quote(project['id'])
        # grand_total, not total: `total` is the exact arithmetic of the lines,
        # and a tax-inclusive price rarely divides into a 2dp base that taxes
        # back to it exactly. The stray paisa lands in `round_off`, which is
        # what that field is for — see RoundedTotalMixin.
        self.assertEqual(quote['grand_total'], self.figures(project)['total'])

    def test_the_invoice_line_is_named_for_the_project(self):
        project = self.post('/api/projects/', {
            'name': '5kW On-Grid', 'capacity': '5kVA Single Phase',
            'price_dcr': '180000', 'tax_percent': '18'}).json()
        quote = self.make_quote(project['id'])
        self.assertIn('5kW On-Grid', quote['items'][0]['description'])
        self.assertIn('5kVA Single Phase', quote['items'][0]['description'])

    def test_a_project_with_no_price_leaves_the_invoice_alone(self):
        """It is a specification that happens to have no package price, not an
        instruction to zero an invoice someone priced by hand."""
        project = self.make_project()                     # no price set
        quote = self.make_quote(project['id'], items=[
            {'description': 'Priced by hand', 'quantity': '1', 'unit_price': '99000'}])
        self.assertEqual(len(quote['items']), 1)
        self.assertEqual(quote['items'][0]['description'], 'Priced by hand')

    def test_switching_project_reprices_the_invoice(self):
        first = self.priced('180000', '18', False)
        second = self.priced('90000', '18', False)
        quote = self.make_quote(first['id'])
        r = self.patch(f"/api/quotes/{quote['id']}/", {'project': second['id']})
        self.assertEqual(r.json()['total'], '106200.00')

    def test_re_saving_does_not_reprice_the_invoice(self):
        """Someone who adjusted the invoice by hand keeps that adjustment."""
        project = self.priced('180000', '18', False)
        quote = self.make_quote(project['id'])
        self.patch(f"/api/quotes/{quote['id']}/", {'items': [
            {'description': 'Agreed price', 'quantity': '1', 'unit_price': '170000'}]})
        again = self.patch(f"/api/quotes/{quote['id']}/", {'status': 'sent'})
        self.assertEqual(again.json()['items'][0]['unit_price'], '170000.00')

    # ── How the system is wired ──
    def test_a_project_records_its_system_type(self):
        p = self.post('/api/projects/', {
            'name': '5kW Hybrid', 'system_type': 'hybrid'}).json()
        self.assertEqual(p['system_type'], 'hybrid')
        self.assertEqual(p['system_type_display'], 'Hybrid')

    def test_every_arrangement_is_offered(self):
        """Driven off the server's own list, so a type added later is checked
        here rather than quietly working only on the form."""
        from inventory.models import SYSTEM_TYPES
        for value, label in SYSTEM_TYPES:
            p = self.post('/api/projects/', {'name': f'P {value}', 'system_type': value}).json()
            self.assertEqual(p['system_type_display'], label)

    def test_it_may_be_left_unset(self):
        """The projects already on the books predate the field; guessing their
        type would put a wrong answer on a customer's quotation."""
        r = self.post('/api/projects/', {'name': 'Unset'})
        self.assertEqual(r.status_code, 201, r.content[:200])
        self.assertEqual(r.json()['system_type'], '')
        self.assertEqual(r.json()['system_type_display'], '')

    def test_something_that_is_not_one_of_the_three_is_refused(self):
        r = self.post('/api/projects/', {'name': 'Nope', 'system_type': 'off_grid'})
        self.assertEqual(r.status_code, 400)

    def test_a_duplicate_keeps_the_system_type(self):
        """It is the same system, so the copy is the same arrangement."""
        p = self.post('/api/projects/', {'name': 'Dup', 'system_type': 'micro_inverter'}).json()
        copy = self.post(f"/api/projects/{p['id']}/duplicate/", {}).json()
        self.assertEqual(copy['system_type'], 'micro_inverter')

    def test_the_list_can_be_searched_by_it(self):
        self.post('/api/projects/', {'name': 'Searchable', 'system_type': 'hybrid'})
        r = self.client.get('/api/projects/?search=hybrid', **self.auth())
        rows = r.json() if isinstance(r.json(), list) else r.json()['results']
        self.assertTrue(any(p['name'] == 'Searchable' for p in rows))

    def test_the_printed_quotation_names_the_system(self):
        """It is what a customer comparing two quotations reads first."""
        project = self.post('/api/projects/', {
            'name': '5kW Rooftop', 'system_type': 'hybrid', 'capacity': '5kVA Single Phase',
            'price_dcr': '200000', 'tax_percent': '18'}).json()
        quote = self.make_quote(project['id'])
        self.assertIn('Hybrid', quote['items'][0]['description'])

    # ── DCR and non-DCR ──
    def two_priced(self):
        """The same system, differently sourced modules, different money."""
        return self.post('/api/projects/', {
            'name': '5kW On-Grid', 'capacity': '5kVA Single Phase',
            'price_dcr': '200000', 'price_non_dcr': '180000',
            'tax_percent': '18', 'price_includes_tax': True,
            'lines': self.LINES}).json()

    def test_a_project_quotes_both_prices(self):
        p = self.two_priced()
        self.assertEqual(self.figures(p, 'dcr')['total'], '200000.00')
        self.assertEqual(self.figures(p, 'non_dcr')['total'], '180000.00')

    def test_each_price_gets_its_own_tax_split(self):
        p = self.two_priced()
        self.assertEqual(self.figures(p, 'dcr')['base_amount'], '169491.53')
        self.assertEqual(self.figures(p, 'non_dcr')['base_amount'], '152542.37')

    def test_both_splits_reconcile(self):
        from decimal import Decimal
        p = self.two_priced()
        for variant in ('dcr', 'non_dcr'):
            f = self.figures(p, variant)
            self.assertEqual(Decimal(f['base_amount']) + Decimal(f['tax_amount']),
                             Decimal(f['total']), variant)

    def test_an_invoice_is_written_for_one_of_them(self):
        project = self.two_priced()
        quote = self.make_quote(project['id'], price_variant='non_dcr')
        self.assertEqual(quote['price_variant'], 'non_dcr')
        self.assertEqual(quote['grand_total'], '180000.00')

    def test_dcr_is_the_default(self):
        project = self.two_priced()
        quote = self.make_quote(project['id'])
        self.assertEqual(quote['price_variant'], 'dcr')
        self.assertEqual(quote['grand_total'], '200000.00')

    def test_switching_between_them_reprices_the_invoice(self):
        """The point of having two: choosing at quotation time."""
        project = self.two_priced()
        quote = self.make_quote(project['id'])
        self.assertEqual(quote['grand_total'], '200000.00')
        r = self.patch(f"/api/quotes/{quote['id']}/", {'price_variant': 'non_dcr'})
        self.assertEqual(r.json()['grand_total'], '180000.00')
        back = self.patch(f"/api/quotes/{quote['id']}/", {'price_variant': 'dcr'})
        self.assertEqual(back.json()['grand_total'], '200000.00')

    def test_switching_price_does_not_disturb_the_specification(self):
        """It is the same system either way, so re-copying the sheet would throw
        away edits for no reason."""
        project = self.two_priced()
        quote = self.make_quote(project['id'])
        edited = [dict(l, quantity='48 M') if l['item_name'] == 'DC Cable' else dict(l)
                  for l in quote['spec_lines']]
        self.patch(f"/api/quotes/{quote['id']}/", {'spec_lines': edited})
        r = self.patch(f"/api/quotes/{quote['id']}/", {'price_variant': 'non_dcr'})
        self.assertEqual(self.line(r.json(), 'DC Cable')['quantity'], '48 M')

    def test_re_saving_the_same_variant_does_not_reprice(self):
        project = self.two_priced()
        quote = self.make_quote(project['id'])
        self.patch(f"/api/quotes/{quote['id']}/", {'items': [
            {'description': 'Agreed price', 'quantity': '1', 'unit_price': '170000'}]})
        again = self.patch(f"/api/quotes/{quote['id']}/", {'price_variant': 'dcr'})
        self.assertEqual(again.json()['items'][0]['unit_price'], '170000.00')

    def test_the_stray_paisa_is_shown_as_round_off_not_lost(self):
        """A tax-inclusive price rarely divides into a 2-decimal base that taxes
        back to it exactly. The invoice keeps its exact arithmetic and carries
        the difference on its own visible line, so the customer is billed the
        figure they were quoted and the document still adds up."""
        from decimal import Decimal
        project = self.two_priced()
        quote = self.make_quote(project['id'])
        self.assertEqual(quote['grand_total'], '200000.00')
        self.assertEqual(
            Decimal(quote['total']) + Decimal(quote['round_off']),
            Decimal(quote['grand_total']))

    def test_the_invoice_line_says_which_it_is(self):
        """"Why is this quote 20,000 more than that one" has one answer, and it
        should be on the paper."""
        project = self.two_priced()
        dcr = self.make_quote(project['id'])
        non = self.make_quote(project['id'], price_variant='non_dcr')
        self.assertIn('DCR', dcr['items'][0]['description'])
        self.assertIn('Non-DCR', non['items'][0]['description'])

    def test_a_variant_priced_at_nothing_leaves_the_invoice_alone(self):
        """Only one of the two priced is a real case — an importer who does not
        offer DCR at all."""
        project = self.post('/api/projects/', {
            'name': 'Non-DCR only', 'price_dcr': '0', 'price_non_dcr': '180000',
            'tax_percent': '18'}).json()
        quote = self.make_quote(project['id'], price_variant='dcr', items=[
            {'description': 'Priced by hand', 'quantity': '1', 'unit_price': '99000'}])
        self.assertEqual(quote['items'][0]['description'], 'Priced by hand')

    # ── The wholesale side is a different business ──
    def test_projects_are_retail_only(self):
        """B2B has its own item master and stock register; the two do not meet."""
        from .models import StockQuote
        self.assertFalse(hasattr(StockQuote, 'spec_lines'))
        self.assertNotIn('project', [f.name for f in StockQuote._meta.get_fields()])

    def test_a_login_is_required(self):
        self.assertEqual(self.client.get('/api/projects/').status_code, 401)


class QuotationTests(TestCase):
    """What the customer is offered, and how it becomes an invoice.

    A quotation is where the price stops being a list price: items are edited, a
    discount is given, extras are added. Every one of those adjustments has to
    be explained on the document, because the question comes months later from
    someone who was not in the room.
    """

    def setUp(self):
        self.admin = mk('qn_admin', 'admin')
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.admin)}

    def post(self, url, body, user=None):
        return self.client.post(url, data=body, content_type='application/json',
                                **self.auth(user))

    def patch(self, url, body):
        return self.client.patch(url, data=body, content_type='application/json',
                                 **self.auth())

    def get(self, url):
        return self.client.get(url, **self.auth()).json()

    def rows(self, query=''):
        """The quotation list as the module shows it."""
        d = self.get(f'/api/quotations/{query}')
        return d if isinstance(d, list) else d.get('results', [])

    def make_project(self, dcr='200000', non_dcr='180000', tax='18', inclusive=True):
        r = self.post('/api/projects/', {
            'name': '5kW On-Grid', 'capacity': '5kVA Single Phase',
            'price_dcr': dcr, 'price_non_dcr': non_dcr,
            'tax_percent': tax, 'price_includes_tax': inclusive,
            'lines': [
                {'item_name': 'Topcon-Adani', 'brand': '', 'quantity': '', 'position': 0},
                {'item_name': 'DC Cable', 'brand': 'POLYCAB', 'quantity': '36 M', 'position': 0},
            ]})
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.json()

    def make_quotation(self, project_id=None, **extra):
        body = {'quotation_date': '2026-09-01', **extra}
        if project_id is not None:
            body['project'] = project_id
        r = self.post('/api/quotations/', body)
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.json()

    # ── The number is a promise ──
    def test_a_deleted_number_is_never_handed_out_again(self):
        """Delete the latest quotation and the next one must not inherit it.

        The number may already be in a customer's inbox, quoted in an email, or
        written on a cheque; two documents answering to it is the one outcome
        the series exists to prevent.
        """
        project = self.make_project()['id']
        first = self.make_quotation(project)
        self.client.delete(f"/api/quotations/{first['id']}/", **self.auth())
        second = self.make_quotation(project)
        self.assertNotEqual(second['number'], first['number'])

    def test_deleting_several_in_a_row_still_moves_forward(self):
        project = self.make_project()['id']
        made = [self.make_quotation(project) for _ in range(3)]
        for q in made:
            self.client.delete(f"/api/quotations/{q['id']}/", **self.auth())
        nxt = self.make_quotation(project)
        self.assertNotIn(nxt['number'], {q['number'] for q in made})

    def test_numbers_run_in_sequence_while_nothing_is_deleted(self):
        project = self.make_project()['id']
        numbers = [self.make_quotation(project)['number'] for _ in range(3)]
        self.assertEqual(numbers, sorted(numbers))
        self.assertEqual(len(set(numbers)), 3)

    def test_a_new_financial_year_starts_again_at_001(self):
        """April is the boundary: the year is part of the series, so a fresh one
        counts from its own beginning without disturbing the old."""
        project = self.make_project()['id']
        march = self.make_quotation(project, quotation_date='2027-03-31')
        april = self.make_quotation(project, quotation_date='2027-04-01')
        self.assertIn('/26-27/', march['number'])
        self.assertTrue(april['number'].endswith('QT001'), april['number'])
        self.assertIn('/27-28/', april['number'])

    def test_a_new_year_is_not_disturbed_by_deletions_in_the_old_one(self):
        project = self.make_project()['id']
        old = self.make_quotation(project, quotation_date='2027-03-31')
        self.client.delete(f"/api/quotations/{old['id']}/", **self.auth())
        new_year = self.make_quotation(project, quotation_date='2027-04-01')
        self.assertTrue(new_year['number'].endswith('QT001'), new_year['number'])

    def test_the_database_itself_refuses_a_duplicate_number(self):
        """Belt and braces: whatever route a write comes in by."""
        from django.db import IntegrityError, transaction
        from inventory.models import Quotation
        q = self.make_quotation(self.make_project()['id'])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Quotation.objects.create(number=q['number'], quotation_date='2026-09-01')

    def test_the_counter_starts_from_numbers_already_issued(self):
        """A series counted the old way carries on rather than starting over."""
        from inventory.models import DocumentCounter, next_quotation_number, Quotation
        Quotation.objects.create(number='EF/30-31/QT007', quotation_date='2030-09-01')
        DocumentCounter.objects.filter(series='EF/30-31/QT').delete()
        self.assertEqual(next_quotation_number(date(2030, 9, 1)), 'EF/30-31/QT008')

    # ── Built from a project ──
    def test_a_quotation_takes_its_specification_and_price_from_the_project(self):
        project = self.make_project()
        q = self.make_quotation(project['id'])
        self.assertEqual(len(q['spec_lines']), 2)
        self.assertEqual(q['package_amount'], '200000.00')
        self.assertEqual(q['total'], '200000.00')

    def test_it_is_numbered_in_its_own_series(self):
        """A quotation and the invoice it becomes may be in the customer's hands
        at once; the same number on both would make them impossible to tell
        apart in a conversation."""
        q = self.make_quotation()
        self.assertIn('/QT', q['number'])
        self.assertNotIn('/PI', q['number'])

    def test_the_numbers_run_on(self):
        first = self.make_quotation()['number']
        second = self.make_quotation()['number']
        self.assertNotEqual(first, second)

    def test_choosing_the_other_price_refills_it(self):
        project = self.make_project()
        q = self.make_quotation(project['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {'price_variant': 'non_dcr'})
        self.assertEqual(r.json()['package_amount'], '180000.00')

    def test_a_negotiated_price_survives_a_re_save(self):
        """Re-saving with the same project must not restore the list price over
        a figure two people agreed."""
        project = self.make_project()
        q = self.make_quotation(project['id'])
        self.patch(f"/api/quotations/{q['id']}/", {'package_amount': '190000'})
        again = self.patch(f"/api/quotations/{q['id']}/", {'status': 'sent'})
        self.assertEqual(again.json()['package_amount'], '190000.00')

    def test_the_items_can_be_edited_without_touching_the_project(self):
        project = self.make_project()
        q = self.make_quotation(project['id'])
        edited = [dict(l, quantity='48 M') if l['item_name'] == 'DC Cable' else dict(l)
                  for l in q['spec_lines']]
        r = self.patch(f"/api/quotations/{q['id']}/", {'spec_lines': edited})
        cable = next(l for l in r.json()['spec_lines'] if l['item_name'] == 'DC Cable')
        self.assertEqual(cable['quantity'], '48 M')

        back = self.get(f"/api/projects/{project['id']}/")
        self.assertEqual(
            next(l['quantity'] for l in back['lines'] if l['item_name'] == 'DC Cable'),
            '36 M')

    # ── Discount ──
    def test_a_discount_comes_off_the_price(self):
        project = self.make_project()
        q = self.make_quotation(project['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {
            'discount_amount': '15000', 'discount_remark': 'Repeat customer'})
        self.assertEqual(r.json()['net_amount'], '185000.00')
        self.assertEqual(r.json()['total'], '185000.00')

    def test_the_discount_keeps_its_reason(self):
        """Asked months later by someone who was not in the room."""
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {
            'discount_amount': '15000', 'discount_remark': 'Repeat customer'})
        self.assertEqual(r.json()['discount_remark'], 'Repeat customer')

    # ── Additional costs ──
    def test_extras_are_added_with_their_reasons(self):
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {'costs': [
            {'remark': 'Crane hire for 3rd floor', 'amount': '12000', 'position': 0},
            {'remark': 'Extra DC cable, 12 m over standard', 'amount': '1980', 'position': 1},
        ]})
        d = r.json()
        self.assertEqual(d['extras_total'], '13980.00')
        self.assertEqual(d['subtotal'], '213980.00')
        self.assertEqual([c['remark'] for c in d['costs']],
                         ['Crane hire for 3rd floor', 'Extra DC cable, 12 m over standard'])

    def test_each_extra_stands_on_its_own(self):
        """A crane, a cable run and a scaffold are three conversations; one lump
        labelled "extra charges" is the one a customer argues with."""
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {'costs': [
            {'remark': 'Crane', 'amount': '12000', 'position': 0},
            {'remark': 'Scaffold', 'amount': '4500', 'position': 1},
        ]})
        self.assertEqual(len(r.json()['costs']), 2)

    def test_extras_keep_the_order_they_were_entered(self):
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {'costs': [
            {'remark': 'First', 'amount': '1', 'position': 0},
            {'remark': 'Second', 'amount': '2', 'position': 1},
            {'remark': 'Third', 'amount': '3', 'position': 2},
        ]})
        self.assertEqual([c['remark'] for c in r.json()['costs']], ['First', 'Second', 'Third'])

    # ── What it comes to ──
    def test_the_whole_statement_adds_up(self):
        from decimal import Decimal
        project = self.make_project()
        q = self.make_quotation(project['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {
            'costs': [{'remark': 'Crane', 'amount': '12000', 'position': 0},
                      {'remark': 'Cable', 'amount': '1980', 'position': 1}],
            'discount_amount': '15000', 'discount_remark': 'Repeat customer'})
        d = r.json()
        self.assertEqual(Decimal(d['package_amount']) + Decimal(d['extras_total']),
                         Decimal(d['subtotal']))
        self.assertEqual(Decimal(d['subtotal']) - Decimal(d['discount_amount']),
                         Decimal(d['net_amount']))
        self.assertEqual(d['net_amount'], '198980.00')
        self.assertEqual(d['total'], '198980.00')
        self.assertEqual(Decimal(d['base_amount']) + Decimal(d['tax_amount']),
                         Decimal(d['total']))

    def test_extras_sit_on_the_same_side_of_the_tax_as_the_price(self):
        """A tax-exclusive project makes a tax-exclusive quotation, so the extras
        are taxed too. Mixing the two sides on one document is how a quotation
        ends up thousands away from what anybody agreed."""
        project = self.make_project(dcr='200000', tax='18', inclusive=False)
        q = self.make_quotation(project['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {
            'costs': [{'remark': 'Crane', 'amount': '10000', 'position': 0}]})
        d = r.json()
        self.assertEqual(d['net_amount'], '210000.00')
        self.assertEqual(d['tax_amount'], '37800.00')
        self.assertEqual(d['total'], '247800.00')

    # ── Anything that moves the price says why ──
    def test_a_discount_without_a_reason_is_refused(self):
        """An unexplained ₹15,000 off is exactly the number that becomes an
        argument months later."""
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {'discount_amount': '15000'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('discount_remark', r.json())

    def test_whitespace_is_not_a_reason(self):
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/",
                       {'discount_amount': '15000', 'discount_remark': '   '})
        self.assertEqual(r.status_code, 400)

    def test_a_discount_with_a_reason_is_accepted(self):
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/",
                       {'discount_amount': '15000', 'discount_remark': 'Repeat customer'})
        self.assertEqual(r.status_code, 200, r.content[:300])

    def test_no_discount_needs_no_reason(self):
        """The rule is conditional: a quotation without a discount is not asked
        to explain one."""
        r = self.post('/api/quotations/', {'quotation_date': '2026-09-01'})
        self.assertEqual(r.status_code, 201, r.content[:300])

    def test_clearing_the_reason_while_a_discount_stands_is_refused(self):
        """The check reads the state after the write, not just what was sent."""
        q = self.make_quotation(self.make_project()['id'])
        self.patch(f"/api/quotations/{q['id']}/",
                   {'discount_amount': '15000', 'discount_remark': 'Repeat customer'})
        r = self.patch(f"/api/quotations/{q['id']}/", {'discount_remark': ''})
        self.assertEqual(r.status_code, 400)

    def test_an_additional_cost_without_a_reason_is_refused(self):
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {'costs': [
            {'remark': '', 'amount': '12000', 'position': 0}]})
        self.assertEqual(r.status_code, 400)

    def test_the_refusal_says_what_is_wanted(self):
        """"This field may not be blank" is true and useless."""
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {'costs': [
            {'remark': '', 'amount': '12000', 'position': 0}]})
        self.assertIn('what this cost is for', str(r.json()))

    def test_a_cost_with_a_reason_is_accepted(self):
        q = self.make_quotation(self.make_project()['id'])
        r = self.patch(f"/api/quotations/{q['id']}/", {'costs': [
            {'remark': 'Crane hire for 3rd floor', 'amount': '12000', 'position': 0}]})
        self.assertEqual(r.status_code, 200, r.content[:300])

    # ── The branded proposal ──
    def with_template(self):
        """The approved artwork, as a stand-in six-page PDF."""
        import pymupdf
        from django.core.files.base import ContentFile
        from .models import QuotationTemplate
        doc = pymupdf.open()
        for _ in range(6):
            doc.new_page(width=810, height=1012)
        t = QuotationTemplate.objects.create(system_type='on_grid')
        t.pdf.save('t.pdf', ContentFile(doc.tobytes()), save=True)
        doc.close()
        return t

    def priced_project(self, subsidy='78000'):
        return self.post('/api/projects/', {
            'name': '5kW On-Grid', 'system_type': 'on_grid',
            'price_dcr': '200000', 'price_non_dcr': '180000',
            'subsidy_amount': subsidy, 'lines': [
                {'item_name': 'PV module', 'brand': 'Adani / Waaree',
                 'quantity': '10 Nos', 'position': 0},
                {'item_name': 'DC Cable', 'brand': 'POLYCAB',
                 'quantity': '36 M', 'position': 1},
            ]}).json()

    def test_the_subsidy_only_counts_for_dcr(self):
        """Only Indian-made modules qualify for PM Surya Ghar."""
        project = self.priced_project()
        dcr = self.make_quotation(project['id'])
        self.assertEqual(dcr['subsidy_shown'], '78000.00')
        self.assertEqual(dcr['net_effective'], '122000.00')

        non = self.patch(f"/api/quotations/{dcr['id']}/", {'price_variant': 'non_dcr'}).json()
        self.assertEqual(non['subsidy_shown'], '0.00')
        self.assertEqual(non['net_effective'], non['total'])

    def test_the_subsidy_comes_across_from_the_project(self):
        project = self.priced_project()
        q = self.make_quotation(project['id'])
        self.assertEqual(q['subsidy_amount'], '78000.00')

    def test_the_cover_carries_the_consumer_number_from_the_site_visit(self):
        """The third row of the cover table is the KSEB consumer number.

        It is recorded on the site visit, which is where someone reads it off
        the customer's bill — the proposal takes it from there rather than
        asking for it a second time.
        """
        import pymupdf
        from leads.models import Lead, SiteVisit
        self.with_template()
        lead = Lead.objects.create(first_name='Meter', last_name='Reader',
                                   phone='9000123456')
        SiteVisit.objects.create(lead=lead, consumer_number='1234567890123')
        q = self.make_quotation(self.priced_project()['id'], lead=lead.id)
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        doc = pymupdf.open(stream=r.content, filetype='pdf')
        cover = doc[0].get_text()
        doc.close()
        self.assertIn('CONSUMER NUMBER', cover)
        self.assertIn('1234567890123', cover)

    def test_the_cover_no_longer_prints_the_location(self):
        """The row it replaced. A lead with a location on file must not have it
        appear where the consumer number now belongs."""
        import pymupdf
        from leads.models import Lead
        self.with_template()
        lead = Lead.objects.create(first_name='Located', last_name='Elsewhere',
                                   phone='9000123457',
                                   installation_location='Pattom, Trivandrum')
        q = self.make_quotation(self.priced_project()['id'], lead=lead.id)
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        doc = pymupdf.open(stream=r.content, filetype='pdf')
        cover = doc[0].get_text()
        doc.close()
        self.assertNotIn('Pattom', cover)
        self.assertIn('CONSUMER NUMBER', cover)

    def test_the_cover_renders_when_there_is_no_site_visit_yet(self):
        """Quoted before the visit: the row is left empty rather than guessed at."""
        import pymupdf
        from leads.models import Lead
        self.with_template()
        lead = Lead.objects.create(first_name='Not', last_name='Visited',
                                   phone='9000123458')
        q = self.make_quotation(self.priced_project()['id'], lead=lead.id)
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        doc = pymupdf.open(stream=r.content, filetype='pdf')
        self.assertIn('CONSUMER NUMBER', doc[0].get_text())
        doc.close()

    def test_the_proposal_renders_on_the_company_artwork(self):
        self.with_template()
        q = self.make_quotation(self.priced_project()['id'])
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_the_proposal_keeps_every_page_of_the_template(self):
        """The pages nobody edits are the company's own and travel untouched."""
        import pymupdf
        self.with_template()
        q = self.make_quotation(self.priced_project()['id'])
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        doc = pymupdf.open(stream=r.content, filetype='pdf')
        self.assertEqual(doc.page_count, 6)
        doc.close()

    def test_the_pricing_page_carries_only_this_quotation_s_figures(self):
        """A proposal showing two sets of numbers is worse than none."""
        import pymupdf
        self.with_template()
        q = self.make_quotation(self.priced_project()['id'])
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        doc = pymupdf.open(stream=r.content, filetype='pdf')
        amounts = [w.strip() for w in doc[3].get_text().splitlines() if '₹' in w]
        doc.close()
        self.assertEqual(len(amounts), 3)          # paid, subsidy, net
        self.assertIn('2,00,000', ' '.join(amounts))
        self.assertIn('78,000', ' '.join(amounts))
        self.assertIn('1,22,000', ' '.join(amounts))

    def test_a_non_dcr_proposal_shows_one_figure_not_a_zero_subsidy(self):
        """"You get nothing back" is a different claim from "this system is not
        in the scheme"."""
        import pymupdf
        self.with_template()
        q = self.make_quotation(self.priced_project()['id'])
        self.patch(f"/api/quotations/{q['id']}/", {'price_variant': 'non_dcr'})
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        doc = pymupdf.open(stream=r.content, filetype='pdf')
        amounts = [w.strip() for w in doc[3].get_text().splitlines() if '₹' in w]
        doc.close()
        self.assertEqual(len(amounts), 1)
        self.assertIn('1,80,000', amounts[0])

    def test_the_rupee_sign_actually_prints(self):
        """None of the fonts every reader has carries U+20B9; without the
        bundled one the customer receives "? 2,00,000"."""
        import pymupdf
        self.with_template()
        q = self.make_quotation(self.priced_project()['id'])
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        doc = pymupdf.open(stream=r.content, filetype='pdf')
        text = doc[3].get_text()
        doc.close()
        self.assertIn('₹', text)
        self.assertNotIn('?', text.replace('?', '', 0) if False else text.split('₹')[0][-2:])

    def test_the_cover_names_the_customer_and_the_quotation(self):
        import pymupdf
        self.with_template()
        project = self.priced_project()
        q = self.make_quotation(project['id'])
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        doc = pymupdf.open(stream=r.content, filetype='pdf')
        cover = doc[0].get_text()
        doc.close()
        self.assertIn(q['number'], cover)
        self.assertIn('5KW ON-GRID', cover.upper())

    def test_without_a_template_it_says_so(self):
        """Rather than sending a customer the wrong system's document."""
        q = self.make_quotation(self.priced_project()['id'])
        r = self.client.get(f"/api/quotations/{q['id']}/proposal/", **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertIn('template', r.json()['error'].lower())

    # ── Payment turns an accepted offer into an order ──
    _paid = 0

    def paid_lead(self, amount='50000'):
        """A customer sitting in accounts with money against them.

        `pushed_to_accounts` and a payment mode are what the accounts module
        itself requires before anyone may complete a verification — the test
        goes through that gate rather than around it, because the conversion
        hangs off the real completion.
        """
        from leads.models import Lead, PaymentVerification, SiteVisit
        QuotationTests._paid += 1
        lead = Lead.objects.create(
            first_name='Paid', last_name=f'Customer {QuotationTests._paid}',
            phone=f'989560{QuotationTests._paid:04d}', value=200000,
            pushed_to_accounts=True)
        # Completion is also gated on the KSEB sanction, since it is what pushes
        # the customer to purchase. Granted here — the conversion, not the gate,
        # is what these tests are about.
        SiteVisit.objects.create(lead=lead, kseb_feasibility_complete=True)
        PaymentVerification.objects.create(lead=lead, amount_received=amount,
                                           payment_mode='cash')
        return lead

    def complete_payment(self, lead, user=None):
        return self.client.post(
            f'/api/leads/{lead.id}/complete-payment-verification/',
            data={}, content_type='application/json', **self.auth(user))

    def quotation_for(self, lead, status='accepted'):
        q = self.make_quotation(self.make_project()['id'], lead=lead.id)
        self.patch(f"/api/quotations/{q['id']}/", {'status': status})
        return q

    def test_payment_turns_an_accepted_quotation_into_an_order(self):
        lead = self.paid_lead()
        q = self.quotation_for(lead)
        r = self.complete_payment(lead)
        self.assertEqual(r.status_code, 200, r.content[:300])
        back = self.get(f"/api/quotations/{q['id']}/")
        self.assertTrue(back['is_order'])
        self.assertIsNotNone(back['order_converted_at'])

    def test_a_part_payment_is_enough(self):
        """Procurement already starts on a part payment; the order is real from
        the first rupee."""
        lead = self.paid_lead(amount='1')
        q = self.quotation_for(lead)
        self.complete_payment(lead)
        self.assertTrue(self.get(f"/api/quotations/{q['id']}/")['is_order'])

    def test_an_invoiced_quotation_still_becomes_an_order(self):
        """The ordinary path: accept it, raise the proforma, then get paid.

        Raising the invoice overwrites `status` with 'converted', so a check for
        status == 'accepted' at payment time finds nothing and the order is
        never recorded — on the route most orders actually take.
        """
        lead = self.paid_lead()
        q = self.quotation_for(lead)
        self.post(f"/api/quotations/{q['id']}/convert/", {})
        self.assertEqual(self.get(f"/api/quotations/{q['id']}/")['status'], 'converted')
        self.complete_payment(lead)
        self.assertTrue(self.get(f"/api/quotations/{q['id']}/")['is_order'])

    def test_an_invoiced_draft_is_not_an_order(self):
        """Invoiced without ever being agreed to is not the same as accepted."""
        lead = self.paid_lead()
        q = self.quotation_for(lead, status='draft')
        self.post(f"/api/quotations/{q['id']}/convert/", {})
        self.complete_payment(lead)
        self.assertFalse(self.get(f"/api/quotations/{q['id']}/")['is_order'])

    def test_accepting_then_declining_does_not_make_an_order(self):
        """Acceptance is remembered, but the customer's last word still rules."""
        lead = self.paid_lead()
        q = self.quotation_for(lead, status='accepted')
        self.patch(f"/api/quotations/{q['id']}/", {'status': 'declined'})
        self.complete_payment(lead)
        self.assertFalse(self.get(f"/api/quotations/{q['id']}/")['is_order'])

    def test_only_accepted_quotations_move(self):
        """A draft on the same customer is not what they paid against."""
        lead = self.paid_lead()
        draft = self.quotation_for(lead, status='draft')
        declined = self.quotation_for(lead, status='declined')
        accepted = self.quotation_for(lead, status='accepted')
        self.complete_payment(lead)
        self.assertFalse(self.get(f"/api/quotations/{draft['id']}/")['is_order'])
        self.assertFalse(self.get(f"/api/quotations/{declined['id']}/")['is_order'])
        self.assertTrue(self.get(f"/api/quotations/{accepted['id']}/")['is_order'])

    def raised_on(self, days_ago, **kw):
        """A quotation with its creation date moved back — created_at is
        auto_now_add, so it is written afterwards rather than passed in."""
        from django.utils import timezone
        from datetime import timedelta
        from .models import Quotation
        q = self.make_quotation(self.make_project()['id'], **kw)
        Quotation.objects.filter(pk=q['id']).update(
            created_at=timezone.now() - timedelta(days=days_ago))
        return q

    def test_the_list_can_be_filtered_by_the_date_it_was_raised(self):
        from django.utils import timezone
        from datetime import timedelta
        old = self.raised_on(10)
        recent = self.raised_on(1)
        cut = (timezone.localtime() - timedelta(days=5)).date().isoformat()

        since = [r['number'] for r in self.rows(f'?created_from={cut}')]
        self.assertIn(recent['number'], since)
        self.assertNotIn(old['number'], since)

        upto = [r['number'] for r in self.rows(f'?created_to={cut}')]
        self.assertIn(old['number'], upto)
        self.assertNotIn(recent['number'], upto)

    def test_both_ends_of_the_range_are_included(self):
        """A single day as the range must return that day's quotations —
        compared on the date, not the timestamp, or anything raised after
        midnight would fall outside its own day."""
        from django.utils import timezone
        q = self.make_quotation(self.make_project()['id'])
        today = timezone.localtime().date().isoformat()
        numbers = [r['number'] for r in
                   self.rows(f'?created_from={today}&created_to={today}')]
        self.assertIn(q['number'], numbers)

    def test_the_date_range_composes_with_the_status_filter(self):
        from django.utils import timezone
        from datetime import timedelta
        draft = self.raised_on(1)
        accepted = self.raised_on(1, status='accepted')
        cut = (timezone.localtime() - timedelta(days=5)).date().isoformat()
        numbers = [r['number'] for r in
                   self.rows(f'?created_from={cut}&status=accepted')]
        self.assertIn(accepted['number'], numbers)
        self.assertNotIn(draft['number'], numbers)

    def test_an_order_leaves_the_quotation_list(self):
        lead = self.paid_lead()
        q = self.quotation_for(lead)
        self.complete_payment(lead)
        numbers = [r['number'] for r in self.rows()]
        self.assertNotIn(q['number'], numbers)

    def test_a_lead_still_sees_its_order_on_its_own_page(self):
        """The lead panel is the only view a BDE or telecaller has.

        Inventory splits offers from orders across two screens, but neither role
        can open Inventory — if the lead's own panel inherited that split, a
        converted order would simply vanish from the only place they look.
        """
        lead = self.paid_lead()
        q = self.quotation_for(lead)
        self.complete_payment(lead)
        panel = [r['number'] for r in self.rows(f"?lead={lead.id}&scope=all")]
        self.assertIn(q['number'], panel)

    def test_an_order_appears_in_converted_orders(self):
        lead = self.paid_lead()
        q = self.quotation_for(lead)
        self.complete_payment(lead)
        numbers = [r['number'] for r in self.rows('?scope=orders')]
        self.assertIn(q['number'], numbers)

    def test_an_order_cannot_be_edited(self):
        """It is the record of what the customer paid against."""
        lead = self.paid_lead()
        q = self.quotation_for(lead)
        self.complete_payment(lead)
        r = self.patch(f"/api/quotations/{q['id']}/", {'package_amount': '1'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('no longer be edited', str(r.json()))

    def test_an_order_cannot_be_deleted(self):
        lead = self.paid_lead()
        q = self.quotation_for(lead)
        self.complete_payment(lead)
        r = self.client.delete(f"/api/quotations/{q['id']}/", **self.auth())
        self.assertEqual(r.status_code, 400)

    def test_paying_twice_does_not_reconvert(self):
        """The conversion date is when it became an order, not when it was last
        touched by a payment."""
        lead = self.paid_lead()
        q = self.quotation_for(lead)
        self.complete_payment(lead)
        first = self.get(f"/api/quotations/{q['id']}/")['order_converted_at']
        self.complete_payment(lead)          # refused; already complete
        self.assertEqual(self.get(f"/api/quotations/{q['id']}/")['order_converted_at'], first)

    def test_the_quotation_list_can_still_filter_by_status(self):
        lead = self.paid_lead()
        self.quotation_for(lead, status='draft')
        self.quotation_for(lead, status='sent')
        drafts = self.rows('?status=draft')
        self.assertTrue(drafts)
        self.assertTrue(all(r['status'] == 'draft' for r in drafts))

    # ── Becoming an invoice ──
    def test_it_converts_to_a_proforma_for_the_agreed_figure(self):
        project = self.make_project()
        q = self.make_quotation(project['id'])
        q = self.patch(f"/api/quotations/{q['id']}/", {
            'costs': [{'remark': 'Crane', 'amount': '12000', 'position': 0}],
            'discount_amount': '15000', 'discount_remark': 'Repeat customer'}).json()

        r = self.post(f"/api/quotations/{q['id']}/convert/", {})
        self.assertEqual(r.status_code, 201, r.content[:300])
        invoice = r.json()
        self.assertIn('/PI', invoice['number'])
        # What was agreed is what is invoiced.
        self.assertEqual(invoice['grand_total'], q['total'])

    def test_the_specification_travels_onto_the_invoice(self):
        """The invoice should say what the customer was offered, not send them
        back to the quotation for it."""
        q = self.make_quotation(self.make_project()['id'])
        invoice = self.post(f"/api/quotations/{q['id']}/convert/", {}).json()
        self.assertEqual(len(invoice['spec_lines']), 2)

    def test_converting_marks_the_quotation_converted(self):
        q = self.make_quotation(self.make_project()['id'])
        self.post(f"/api/quotations/{q['id']}/convert/", {})
        back = self.get(f"/api/quotations/{q['id']}/")
        self.assertEqual(back['status'], 'converted')
        self.assertIsNotNone(back['converted_quote'])

    def test_converting_twice_does_not_raise_a_second_invoice(self):
        """A customer must never receive two invoices for one job."""
        q = self.make_quotation(self.make_project()['id'])
        first = self.post(f"/api/quotations/{q['id']}/convert/", {}).json()
        again = self.post(f"/api/quotations/{q['id']}/convert/", {})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.json()['quote']['number'], first['number'])

    def test_a_login_is_required(self):
        self.assertEqual(self.client.get('/api/quotations/').status_code, 401)


class ProjectQuotedCountTests(TestCase):
    """How many documents name a bundle.

    Two things read this number: the QUOTED ON column, and the delete
    confirmation that warns what depends on the bundle. It used to count only
    proformas, from when they were the only document a project could appear on.
    The retail side now sells through quotations, so a bundle in daily use on
    quotations reported zero — a dash in the column, and a delete prompt saying
    nothing depended on it.
    """

    def setUp(self):
        self.admin = mk('pqc_admin', 'admin')
        self.project = ProjectSpec.objects.create(name='5kW OnGrid', capacity='5kW')

    def count(self):
        r = self.client.get(f'/api/projects/{self.project.pk}/',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:200])
        return r.json()['quoted_count']

    def test_an_unused_bundle_counts_zero(self):
        self.assertEqual(self.count(), 0)

    def test_quotations_are_counted(self):
        Quotation.objects.create(project=self.project, package_amount=200000)
        Quotation.objects.create(project=self.project, package_amount=250000)
        self.assertEqual(self.count(), 2)

    def test_proformas_are_still_counted(self):
        Quote.objects.create(project=self.project)
        self.assertEqual(self.count(), 1)

    def test_both_document_types_add_up(self):
        Quotation.objects.create(project=self.project, package_amount=200000)
        Quote.objects.create(project=self.project)
        self.assertEqual(self.count(), 2)

    def test_another_bundle_is_not_counted(self):
        other = ProjectSpec.objects.create(name='3kW OnGrid', capacity='3kW')
        Quotation.objects.create(project=other, package_amount=150000)
        self.assertEqual(self.count(), 0)


class RetailInventoryAccessTests(TestCase):
    """Who may reach the retail inventory endpoints, role by role.

    Before this the endpoints answered any authenticated account, so a module
    hidden from someone's sidebar was still one they could fetch — supplier
    costs and purchase orders included. The gate now matches the nav, and this
    enumerates every role so a change to either is visible here rather than in
    production.
    """

    # Every endpoint this gate governs, so none is left open by being forgotten.
    # `/api/vendors/` is deliberately absent: the suppliers list is shared with
    # the wholesale side and answers to SuppliersAccess instead, because people
    # who never see this group still order from those vendors. See
    # test_suppliers_keeps_its_own_rule below.
    ENDPOINTS = ['/api/products/', '/api/quotes/',
                 '/api/sales-orders/', '/api/purchase-orders/',
                 '/api/projects/', '/api/quotations/']

    # The roles the sidebar shows the group to: the admin tier (is_staff), the
    # three that carry is_general_manager, the spectator — and now the BDE.
    ALLOWED = ['superadmin', 'admin', 'coo', 'sales_manager', 'documentation_manager',
               'spectator']
    # Everyone else works a different desk and never had a link to it.
    BLOCKED = ['leads_manager', 'documentation_staff', 'accounts_manager',
               'accounts_staff', 'purchase_staff', 'project_manager',
               'liasoning_officer', 'branch_manager']
    # Not in the module, but they quote from a lead's page — see the two tests
    # at the end. Listed so the coverage guard still accounts for them.
    QUOTING = ['bde', 'tele_caller']
    # The wholesale roles reach the shared lists from their own side; what they
    # may do there is SuppliersAccess's business, not this gate's.
    B2B_ONLY = ['store_manager', 'store_keeper', 'accounts_b2b']

    def setUp(self):
        self._users = {}

    def user(self, role):
        """One account per role, kept — every endpoint is checked for each."""
        if role not in self._users:
            self._users[role] = mk(f'inv_{role}', role)
        return self._users[role]

    def reach(self, role, url):
        return self.client.get(url, HTTP_AUTHORIZATION=token_for(self.user(role))).status_code

    def test_the_roles_the_sidebar_shows_it_to_can_reach_it(self):
        for role in self.ALLOWED:
            for url in self.ENDPOINTS:
                self.assertEqual(self.reach(role, url), 200, f'{role} -> {url}')

    def test_the_roles_that_quote_do_not_get_the_module(self):
        """They raise a quotation from a lead's page; that is not the same as
        being handed suppliers, purchases and the stock lists."""
        for role in self.QUOTING:
            for url in ('/api/products/', '/api/purchase-orders/', '/api/sales-orders/',
                        '/api/quotes/'):
                self.assertEqual(self.reach(role, url), 403, f'{role} -> {url}')

    def test_the_roles_that_quote_can_still_quote(self):
        """The quotation and the projects behind it stay reachable, or the
        panel on a lead's page would be a button that answers 403."""
        for role in self.QUOTING:
            for url in ('/api/quotations/', '/api/projects/'):
                self.assertEqual(self.reach(role, url), 200, f'{role} -> {url}')

    def test_every_other_role_is_turned_away(self):
        for role in self.BLOCKED:
            for url in self.ENDPOINTS:
                self.assertEqual(self.reach(role, url), 403, f'{role} -> {url}')

    def test_purchase_orders_are_no_longer_open_to_the_whole_company(self):
        """The gap this closes, stated on its own so it cannot quietly reopen."""
        self.assertEqual(self.reach('documentation_staff', '/api/purchase-orders/'), 403)
        self.assertEqual(self.reach('documentation_staff', '/api/products/'), 403)

    def test_suppliers_keeps_its_own_rule(self):
        """The shared list is not this gate's business.

        Purchase staff never see the retail inventory group and still order from
        these vendors; gating suppliers on the group took that away. The access
        is theirs by the job they do, not by the menu they are shown — which is
        what SuppliersAccess already said before this gate existed.
        """
        self.assertEqual(self.reach('purchase_staff', '/api/vendors/'), 200)
        self.assertEqual(self.reach('bde', '/api/vendors/'), 200)

    def test_a_spectator_reads_but_does_not_write(self):
        """It keeps its bargain: the whole company, and nothing changed."""
        spectator = self.user('spectator')
        self.assertEqual(
            self.client.get('/api/projects/',
                            HTTP_AUTHORIZATION=token_for(spectator)).status_code, 200)
        r = self.client.post('/api/projects/', data={'name': 'Nope'},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(spectator))
        self.assertEqual(r.status_code, 403)

    def test_a_tele_caller_can_actually_raise_a_quotation(self):
        """Read access alone would be a panel they could open and not use."""
        bde = self.user('tele_caller')
        project = self.client.post(
            '/api/projects/', data={'name': '5kW', 'price_dcr': '200000', 'tax_percent': '18'},
            content_type='application/json', HTTP_AUTHORIZATION=token_for(bde))
        self.assertEqual(project.status_code, 201, project.content[:200])
        r = self.client.post(
            '/api/quotations/',
            data={'quotation_date': '2026-09-01', 'project': project.json()['id']},
            content_type='application/json', HTTP_AUTHORIZATION=token_for(bde))
        self.assertEqual(r.status_code, 201, r.content[:300])

    def test_every_role_is_accounted_for(self):
        """A role added later must be classified here before it ships.

        Without this the safe-looking default — a new role simply not appearing
        in either list — is the one where nobody notices it was never decided.
        """
        from users.models import ROLE_CHOICES, ROLE_CUSTOM
        known = set(self.ALLOWED) | set(self.BLOCKED) | set(self.B2B_ONLY) | set(self.QUOTING)
        # A custom role carries its own permission list, tested separately.
        declared = {r for r, _ in ROLE_CHOICES} - {ROLE_CUSTOM}
        self.assertEqual(declared - known, set(), 'unclassified role(s)')

    def test_a_custom_role_decides_for_itself(self):
        from users.models import CustomRole, User
        role = CustomRole.objects.create(name='Quoting desk', permissions=['inventory'])
        user = mk('inv_custom_yes', 'custom')
        user.custom_role = role
        user.save()
        self.assertEqual(
            self.client.get('/api/projects/',
                            HTTP_AUTHORIZATION=token_for(user)).status_code, 200)

        bare = CustomRole.objects.create(name='No inventory', permissions=['leads'])
        other = mk('inv_custom_no', 'custom')
        other.custom_role = bare
        other.save()
        self.assertEqual(
            self.client.get('/api/projects/',
                            HTTP_AUTHORIZATION=token_for(other)).status_code, 403)

    def test_signed_out_is_still_signed_out(self):
        for url in self.ENDPOINTS:
            self.assertEqual(self.client.get(url).status_code, 401, url)


class PaymentsBoardRoundingTests(TestCase):
    """Inventory → Payments reports the invoice at the rounded figure the
    customer was billed — the one the invoice prints and every other payment
    screen reconciles against (payment_state) — not the exact arithmetic."""

    URL = '/api/stock-payments/'

    def setUp(self):
        self.admin = mk('pr_admin', 'superadmin')
        self.customer = StockCustomer.objects.create(name='Energyfox Consultants Pvt Ltd')
        self.item = StockItem.objects.create(code='PR-PNL', category='Solar Panel',
                                             opening_stock=Decimal('1000'),
                                             unit_cost=Decimal('100'))

    def board(self):
        r = self.client.get(self.URL, HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()['sections']

    def row(self, number):
        for name, section in self.board().items():
            for r in section['rows']:
                if r['number'] == number:
                    return name, r
        self.fail(f'{number} is not on the board')

    def dispatch(self, invoice_no, rate, qty='1'):
        StockDispatch.objects.create(invoice_no=invoice_no, date=timezone.localdate(),
                                     customer=self.customer, item=self.item,
                                     quantity=Decimal(qty), rate=Decimal(rate),
                                     tax_percent=Decimal('0'), status=StockDispatch.PENDING)

    def paid(self, amount, *, invoice_no='', quote=None):
        DispatchPayment.objects.create(invoice_no=invoice_no, quote=quote,
                                       invoice_total=Decimal(amount), amount_received=Decimal(amount),
                                       mode='cash', paid_on=timezone.localdate(),
                                       verified_by=self.admin)

    def test_the_invoice_column_is_the_billed_round_figure(self):
        """The screenshot: 5,000.50 billed and paid as 5,001."""
        self.dispatch('IN-061', '5000.50')
        self.paid('5001', invoice_no='IN-061')
        section, r = self.row('IN-061')
        self.assertEqual(section, 'fully_paid')
        self.assertEqual(r['invoice_total'], '5001.00')
        self.assertEqual(r['received'], '5001.00')
        self.assertEqual(r['balance'], '0.00')

    def test_an_invoice_rounded_down_and_paid_is_fully_paid(self):
        """2,252.25 is billed 2,252. Against the exact total it sat under
        Partially Paid owing 25 paise."""
        self.dispatch('IN-DOWN', '2252.25')
        self.paid('2252', invoice_no='IN-DOWN')
        section, r = self.row('IN-DOWN')
        self.assertEqual(section, 'fully_paid')
        self.assertEqual(r['invoice_total'], '2252.00')
        self.assertEqual(r['balance'], '0.00')

    def test_paying_the_exact_figure_also_settles_it(self):
        """A customer who sent the exact 95,794.65 their copy showed owes nothing —
        nobody transfers 35 paise."""
        self.dispatch('IN-EXACT', '95794.65')
        self.paid('95794.65', invoice_no='IN-EXACT')
        section, r = self.row('IN-EXACT')
        self.assertEqual(section, 'fully_paid')
        self.assertEqual(r['invoice_total'], '95795.00')
        self.assertEqual(r['balance'], '0.00')

    def test_a_part_payment_owes_against_the_billed_figure(self):
        self.dispatch('IN-PART', '5000.50')
        self.paid('2000', invoice_no='IN-PART')
        section, r = self.row('IN-PART')
        self.assertEqual(section, 'partially_paid')
        self.assertEqual(r['balance'], '3001.00')

    def test_a_delivery_of_several_lines_is_rounded_once(self):
        """Rounded on the whole delivery: 1,000.30 + 1,000.30 is billed 2,001,
        not 1,000 + 1,000."""
        self.dispatch('IN-TWO', '1000.30')
        self.dispatch('IN-TWO', '1000.30')
        self.paid('2001', invoice_no='IN-TWO')
        _section, r = self.row('IN-TWO')
        self.assertEqual(r['invoice_total'], '2001.00')

    def test_a_proforma_is_rounded_too(self):
        q = StockQuote.objects.create(customer=self.customer, quote_date=timezone.localdate())
        StockQuoteItem.objects.create(quote=q, item=self.item, quantity=Decimal('1'),
                                      unit_price=Decimal('4999.60'))
        self.paid('1000', quote=q)
        section, r = self.row(q.number)
        self.assertEqual(section, 'partially_paid')
        self.assertEqual(r['invoice_total'], '5000.00')
        self.assertEqual(r['balance'], '4000.00')

    def test_the_section_totals_add_the_billed_figures(self):
        self.dispatch('IN-T1', '5000.50')
        self.dispatch('IN-T2', '2252.25')
        self.paid('5001', invoice_no='IN-T1')
        self.paid('2252', invoice_no='IN-T2')
        totals = self.board()['fully_paid']['totals']
        self.assertEqual(totals['count'], 2)
        self.assertEqual(Decimal(totals['invoice_total']), Decimal('7253'))
        self.assertEqual(Decimal(totals['balance']), Decimal('0'))


class B2BDocumentBugfixTests(TestCase):
    """Regressions in the wholesale proforma → dispatch → payment chain."""

    def setUp(self):
        self.admin = mk('fix_admin', 'superadmin')
        self.accounts = mk('fix_accounts', 'accounts_b2b')
        self.customer = StockCustomer.objects.create(name='Harbour Solar', gstin='32AAAAA0000A1Z5',
                                                     site_address='Kochi', state='Kerala')
        self.other = StockCustomer.objects.create(name='Hill Resorts')
        self.panel = StockItem.objects.create(code='FX-PNL', category='Solar Panel', brand='Waaree',
                                              model_name='540W', opening_stock=Decimal('100'),
                                              hsn='8541')

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': token_for(user or self.admin)}

    def post(self, url, body=None, user=None):
        return self.client.post(url, data=body or {}, content_type='application/json',
                                **self.auth(user))

    def discounted_quote(self, quote_date=None):
        """10 × 11,200 less 10%, plus 18% GST = 1,18,944."""
        q = StockQuote.objects.create(customer=self.customer, site='Kochi',
                                      quote_date=quote_date or timezone.localdate(),
                                      discount_percent=Decimal('10'), tax_percent=Decimal('18'))
        StockQuoteItem.objects.create(quote=q, item=self.panel, quantity=Decimal('10'),
                                      unit_price=Decimal('11200'))
        return q

    def convert_paid(self, q):
        r = self.post(f'/api/stock-quotes/{q.id}/convert/', paid_in_full(q))
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()['invoice_no']

    # ── Converting a discounted proforma ──
    def test_the_invoice_keeps_the_proformas_discount(self):
        q = self.discounted_quote()
        self.assertEqual(q.total, Decimal('118944'))
        invoice_no = self.convert_paid(q)
        rows = list(StockDispatch.objects.filter(invoice_no=invoice_no))
        self.assertEqual(rows[0].discount_percent, Decimal('10'))
        self.assertEqual(sum(r.total for r in rows), Decimal('118944'))

    def test_a_paid_discounted_proforma_is_not_left_owing_once_dispatched(self):
        q = self.discounted_quote()
        invoice_no = self.convert_paid(q)
        r = self.client.get(f'/api/stock-dispatches/verify-payment/?invoice_no={invoice_no}',
                            **self.auth())
        self.assertTrue(r.json()['fully_paid'], r.json())
        self.assertEqual(r.json()['balance'], '0.00')
        board = self.client.get('/api/stock-payments/', **self.auth()).json()['sections']
        self.assertIn(invoice_no, [row['number'] for row in board['fully_paid']['rows']])

    def test_the_printed_invoice_bills_the_discounted_figure(self):
        q = self.discounted_quote()
        invoice_no = self.convert_paid(q)
        d = StockDispatch.objects.get(invoice_no=invoice_no)
        doc = self.client.get(f'/api/stock-dispatches/{d.id}/invoice/', **self.auth()).json()
        self.assertEqual(doc['totals']['grand_total'], '118944.00')
        self.assertEqual(doc['totals']['discount'], '11200.00')
        self.assertEqual(doc['lines'][0]['taxable'], '100800.00')

    def test_the_dashboard_counts_the_sale_at_its_discounted_value(self):
        self.convert_paid(self.discounted_quote())
        r = self.client.get('/api/stock-summary/', **self.auth()).json()
        self.assertEqual(Decimal(r['period_sales']), Decimal('118944'))

    def test_the_invoice_is_dated_the_day_the_goods_leave(self):
        q = self.discounted_quote(quote_date=timezone.localdate() - timedelta(days=40))
        invoice_no = self.convert_paid(q)
        d = StockDispatch.objects.filter(invoice_no=invoice_no).first()
        self.assertEqual(d.date, timezone.localdate())
        self.assertTrue(invoice_no.startswith(series_key('IN', timezone.localdate())), invoice_no)

    # ── The printed proforma ──
    def test_the_proforma_lines_add_up_to_its_total_under_a_discount(self):
        q = self.discounted_quote()
        doc = self.client.get(f'/api/stock-quotes/{q.id}/proforma/', **self.auth()).json()
        lines_total = sum(Decimal(li['total']) for li in doc['lines'])
        self.assertEqual(lines_total, Decimal(doc['totals']['invoice_value']))
        hsn_taxable = sum(Decimal(h['taxable']) for h in doc['hsn_summary'])
        self.assertEqual(hsn_taxable, Decimal(doc['totals']['taxable']))

    def test_the_proforma_email_states_the_billed_figure(self):
        import shutil
        import tempfile
        q = StockQuote.objects.create(customer=self.customer, quote_date=timezone.localdate(),
                                      tax_percent=Decimal('18'))
        StockQuoteItem.objects.create(quote=q, item=self.panel, quantity=Decimal('3'),
                                      unit_price=Decimal('271.05'))     # 959.517 → 960
        media = tempfile.mkdtemp(prefix='fix-test-')
        try:
            with self.settings(MEDIA_ROOT=media), patch('messaging.email.send_and_log') as send:
                send.return_value = type('L', (), {'status': 'sent', 'error': ''})()
                self.client.post(f'/api/stock-quotes/{q.id}/send/', {
                    'pdf': SimpleUploadedFile('pi.pdf', b'%PDF-1.4', content_type='application/pdf'),
                    'channels': 'email', 'email': 'buyer@example.com'}, **self.auth())
        finally:
            shutil.rmtree(media, ignore_errors=True)
        self.assertIn('Rs. 960.00', send.call_args.kwargs['body'])

    # ── Rounding: the document and the payment screen agree ──
    def test_a_sub_paisa_tail_rounds_the_same_everywhere(self):
        from inventory.models import round_off_for
        from inventory.views import payment_state, totals_block
        exact = Decimal('100.495')
        self.assertEqual(round_off_for(exact)[0], Decimal('101'))
        printed = totals_block(exact, Decimal('0'), Decimal('0'), exact)
        self.assertEqual(printed['grand_total'], payment_state(exact, 0)['invoice_total'])
        self.assertEqual(Decimal(printed['invoice_value']) + Decimal(printed['round_off']),
                         Decimal(printed['grand_total']))

    # ── Deleting a proforma that holds payments ──
    def _quote_with_a_payment(self):
        q = self.discounted_quote()
        r = self.post(f'/api/stock-quotes/{q.id}/verify-payment/',
                      {'payment': {'amount_received': '5000', 'mode': 'upi'}})
        self.assertEqual(r.status_code, 201, r.content[:300])
        return q

    def test_a_proforma_holding_payments_is_not_deleted_out_from_under_them(self):
        q = self._quote_with_a_payment()
        r = self.client.delete(f'/api/stock-quotes/{q.id}/', **self.auth(self.accounts))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['can_force'])
        self.assertTrue(StockQuote.objects.filter(pk=q.pk).exists())
        self.assertEqual(DispatchPayment.received_for(quote=q), Decimal('5000'))

    def test_a_super_admin_must_confirm_and_can_then_delete_it(self):
        q = self._quote_with_a_payment()
        r = self.client.delete(f'/api/stock-quotes/{q.id}/', **self.auth())
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()['can_force'])
        r = self.client.delete(f'/api/stock-quotes/{q.id}/?force=1', **self.auth())
        self.assertEqual(r.status_code, 204)

    def test_a_proforma_with_no_payments_still_deletes_at_once(self):
        q = self.discounted_quote()
        self.assertEqual(self.client.delete(f'/api/stock-quotes/{q.id}/',
                                            **self.auth(self.accounts)).status_code, 204)

    # ── Editing a dispatch row ──
    def raise_delivery(self, payment=None):
        body = {'date': str(timezone.localdate()), 'customer': self.customer.id,
                'tax_percent': '18', 'site': 'Kochi',
                'lines': [{'item': self.panel.id, 'quantity': '1', 'rate': '1000'},
                          {'item': self.panel.id, 'quantity': '2', 'rate': '1000'}]}
        if payment:
            body['payment'] = payment
        r = self.post('/api/stock-dispatches/dispatch/', body)
        self.assertEqual(r.status_code, 201, r.content[:300])
        return r.json()['invoice_no']

    def patch_row(self, row, body):
        return self.client.patch(f'/api/stock-dispatches/{row.id}/', data=body,
                                 content_type='application/json', **self.auth())

    def test_editing_a_lines_invoice_details_edits_the_whole_invoice(self):
        invoice_no = self.raise_delivery()
        first = StockDispatch.objects.filter(invoice_no=invoice_no).order_by('id').first()
        r = self.patch_row(first, {'customer': self.other.id, 'tax_percent': '5', 'site': 'Munnar'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        for row in StockDispatch.objects.filter(invoice_no=invoice_no):
            self.assertEqual((row.customer_id, row.tax_percent, row.site),
                             (self.other.id, Decimal('5'), 'Munnar'))

    def test_an_invoice_number_cannot_be_blanked(self):
        invoice_no = self.raise_delivery()
        row = StockDispatch.objects.filter(invoice_no=invoice_no).first()
        self.assertEqual(self.patch_row(row, {'invoice_no': ''}).status_code, 400)
        self.assertEqual(StockDispatch.objects.filter(invoice_no=invoice_no).count(), 2)

    def test_renaming_an_invoice_takes_its_lines_and_payments_with_it(self):
        invoice_no = self.raise_delivery(payment={'amount_received': '1000', 'mode': 'cash'})
        row = StockDispatch.objects.filter(invoice_no=invoice_no).first()
        r = self.patch_row(row, {'invoice_no': 'REN2627-IN950'})
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(StockDispatch.objects.filter(invoice_no='REN2627-IN950').count(), 2)
        self.assertEqual(DispatchPayment.received_for(invoice_no='REN2627-IN950'), Decimal('1000'))
        self.assertFalse(DispatchPayment.objects.filter(invoice_no=invoice_no).exists())

    def test_an_invoice_cannot_be_renamed_onto_another(self):
        a = self.raise_delivery()
        b = self.raise_delivery()
        row = StockDispatch.objects.filter(invoice_no=a).first()
        self.assertEqual(self.patch_row(row, {'invoice_no': b}).status_code, 400)

    # ── Raising a delivery ──
    def test_an_unknown_product_is_a_clear_refusal_not_a_crash(self):
        r = self.post('/api/stock-dispatches/dispatch/', {
            'lines': [{'item': 987654, 'quantity': '1', 'rate': '10'}]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(StockDispatch.objects.count(), 0)

    def test_a_deleted_deliverys_number_does_not_hand_its_payments_on(self):
        invoice_no = self.raise_delivery(payment={'amount_received': '1000', 'mode': 'cash'})
        StockDispatch.objects.filter(invoice_no=invoice_no).delete()
        r = self.post('/api/stock-dispatches/dispatch/', {
            'invoice_no': invoice_no,
            'lines': [{'item': self.panel.id, 'quantity': '1', 'rate': '10'}]})
        self.assertEqual(r.status_code, 400, r.content[:300])


class InvoiceNumbersRunOnTests(TestCase):
    """B2B invoice numbers run on from the last invoice on the books — 24, then
    25, 26, 27 — whatever the proforma series or the old counter says.

    Invoices are filed, so the series has to be continuous. The forward-only
    counter kept every number it ever handed out: deliveries deleted or renamed
    left it far ahead of the books, and the next invoice after IN024 was IN066.
    """

    def setUp(self):
        self.admin = mk('inv_admin', 'superadmin')
        self.customer = StockCustomer.objects.create(name='Energyfox Consultants Pvt Ltd')
        self.item = StockItem.objects.create(code='INV-PNL', category='Solar Panel',
                                             opening_stock=Decimal('1000'),
                                             unit_cost=Decimal('100'))
        self.today = timezone.localdate()
        self.key = series_key('IN', self.today)

    def invoice(self, invoice_no='', on=None):
        return StockDispatch.objects.create(invoice_no=invoice_no, date=on or self.today,
                                            customer=self.customer, item=self.item,
                                            quantity=Decimal('1'), rate=Decimal('100'))

    def books(self, *seqs):
        for seq in seqs:
            self.invoice(f'{self.key}{seq:03d}')

    def payment_on(self, invoice_no):
        DispatchPayment.objects.create(invoice_no=invoice_no, invoice_total=Decimal('100'),
                                       amount_received=Decimal('100'), mode='cash',
                                       paid_on=self.today, verified_by=self.admin)

    def post_dispatch(self, **extra):
        body = {'customer': self.customer.id, 'date': self.today.isoformat(),
                'lines': [{'item': self.item.id, 'quantity': '1', 'rate': '100'}], **extra}
        return self.client.post('/api/stock-dispatches/dispatch/', data=body,
                                content_type='application/json',
                                HTTP_AUTHORIZATION=token_for(self.admin))

    # ── The report ──
    def test_proformas_do_not_move_the_invoice_series(self):
        """60 proformas and 24 invoices: the next invoice is 25, not 61."""
        for _ in range(60):
            StockQuote.objects.create(customer=self.customer, quote_date=self.today)
        self.books(*range(1, 25))
        self.assertEqual(self.invoice().invoice_no, f'{self.key}025')
        self.assertEqual(self.invoice().invoice_no, f'{self.key}026')

    def test_a_counter_that_ran_ahead_of_the_books_is_ignored(self):
        """What production had: the counter at 65 while the books stopped at 24."""
        self.books(*range(1, 25))
        DocumentNumberSeries.objects.update_or_create(key=self.key, defaults={'last_seq': 65})
        self.assertEqual(self.invoice().invoice_no, f'{self.key}025')

    def test_renaming_the_stray_invoice_down_closes_the_gap(self):
        """IN066 renamed to IN025 from the edit form: its payment goes with it,
        and the next invoice is 026."""
        self.books(*range(1, 25))
        stray = self.invoice(f'{self.key}066')
        self.payment_on(stray.invoice_no)
        r = self.client.patch(f'/api/stock-dispatches/{stray.id}/',
                              data={'invoice_no': f'{self.key}025'}, content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(DispatchPayment.objects.filter(invoice_no=f'{self.key}025').exists())
        self.assertEqual(self.invoice().invoice_no, f'{self.key}026')

    # ── Deleting ──
    def test_deleting_the_latest_invoice_frees_its_number(self):
        self.invoice()
        last = self.invoice()
        last.delete()
        self.assertEqual(self.invoice().invoice_no, f'{self.key}002')

    def test_a_gap_in_the_middle_is_not_refilled(self):
        """Filling it would put a later sale between two earlier ones."""
        self.invoice()
        middle = self.invoice()
        self.invoice()
        middle.delete()
        self.assertEqual(self.invoice().invoice_no, f'{self.key}004')

    def test_a_number_with_payments_still_under_it_is_skipped(self):
        """A new invoice under it would inherit the money and read as paid."""
        self.invoice()
        last = self.invoice()
        self.payment_on(last.invoice_no)
        last.delete()
        self.assertEqual(self.invoice().invoice_no, f'{self.key}003')

    # ── Both ways an invoice is raised ──
    def test_new_dispatch_takes_the_next_number_on_the_books(self):
        self.books(*range(1, 25))
        DocumentNumberSeries.objects.update_or_create(key=self.key, defaults={'last_seq': 65})
        r = self.post_dispatch()
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.json()['invoice_no'], f'{self.key}025')

    def test_dispatching_a_proforma_takes_the_next_number_too(self):
        self.books(*range(1, 25))
        q = StockQuote.objects.create(customer=self.customer, quote_date=self.today)
        StockQuoteItem.objects.create(quote=q, item=self.item, quantity=Decimal('1'),
                                      unit_price=Decimal('100'))
        r = self.client.post(f'/api/stock-quotes/{q.id}/convert/', data=paid_in_full(q),
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(r.json()['invoice_no'], f'{self.key}025')

    def test_a_save_that_fails_gives_its_number_back(self):
        """The old counter spent a number even when the delivery was never
        written — one more way the gaps opened."""
        self.books(1)
        r = self.post_dispatch(payment={'amount_received': '0', 'mode': 'cash'})
        self.assertEqual(r.status_code, 400, r.content[:300])
        self.assertEqual(self.post_dispatch().json()['invoice_no'], f'{self.key}002')

    # ── The form's preview ──
    def test_the_form_can_preview_the_next_number_without_spending_it(self):
        self.books(*range(1, 25))
        for _ in range(2):
            r = self.client.get('/api/stock-dispatches/next-number/',
                                HTTP_AUTHORIZATION=token_for(self.admin))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()['number'], f'{self.key}025')
        self.assertEqual(self.invoice().invoice_no, f'{self.key}025')

    def test_the_preview_follows_the_date_into_its_financial_year(self):
        self.invoice(on=date(2026, 8, 3))
        r = self.client.get('/api/stock-dispatches/next-number/?date=2027-04-01',
                            HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.json()['number'], 'REN2728-IN001')

    # ── The year ──
    def test_each_financial_year_runs_on_its_own(self):
        self.assertEqual(self.invoice(on=date(2026, 8, 3)).invoice_no, 'REN2627-IN001')
        self.assertEqual(self.invoice(on=date(2026, 8, 4)).invoice_no, 'REN2627-IN002')
        self.assertEqual(self.invoice(on=date(2027, 4, 1)).invoice_no, 'REN2728-IN001')
        self.assertEqual(self.invoice(on=date(2027, 3, 31)).invoice_no, 'REN2627-IN003')


class InvoiceSeriesReportTests(TestCase):
    """`manage.py invoice_series` — a read-only look at the invoice series, for
    checking the live books before and after tidying them."""

    def setUp(self):
        self.admin = mk('isr_admin', 'superadmin')
        self.customer = StockCustomer.objects.create(name='Energyfox Consultants Pvt Ltd')
        self.item = StockItem.objects.create(code='ISR-PNL', category='Solar Panel',
                                             opening_stock=Decimal('1000'),
                                             unit_cost=Decimal('100'))
        self.today = timezone.localdate()
        self.key = series_key('IN', self.today)

    def report(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('invoice_series', stdout=out)
        return out.getvalue()

    def test_it_shows_what_production_looked_like(self):
        for seq in list(range(1, 25)) + [66]:
            StockDispatch.objects.create(invoice_no=f'{self.key}{seq:03d}', date=self.today,
                                         customer=self.customer, item=self.item,
                                         quantity=Decimal('1'), rate=Decimal('100'))
        for seq, amount in ((54, '95256'), (55, '160256')):
            DispatchPayment.objects.create(invoice_no=f'{self.key}{seq:03d}',
                                           invoice_total=Decimal(amount),
                                           amount_received=Decimal(amount), mode='bank',
                                           paid_on=self.today, verified_by=self.admin)
        text = self.report()
        self.assertIn(f'25 invoice(s) on the books, highest {self.key}066', text)
        self.assertIn('Missing below it: 025-065', text)
        self.assertIn(f'Next invoice: {self.key}067', text)
        self.assertIn(f'{self.key}054: 1 payment(s), Rs. 95,256.00', text)
        self.assertIn(f'{self.key}055: 1 payment(s), Rs. 160,256.00', text)

    def test_it_changes_nothing(self):
        StockDispatch.objects.create(invoice_no='', date=self.today, customer=self.customer,
                                     item=self.item, quantity=Decimal('1'), rate=Decimal('100'))
        before = list(DocumentNumberSeries.objects.values_list('key', 'last_seq'))
        self.report()
        self.report()
        self.assertEqual(list(DocumentNumberSeries.objects.values_list('key', 'last_seq')), before)
        self.assertEqual(StockDispatch.objects.count(), 1)

    def test_an_empty_year_says_so(self):
        text = self.report()
        self.assertIn('no invoices yet', text)
        self.assertIn(f'Next invoice: {self.key}001', text)
