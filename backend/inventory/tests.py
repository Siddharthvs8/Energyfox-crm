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
                     DispatchPayment, DocumentNumberSeries, series_key)


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

    def test_it_holds_for_proformas_and_invoices_too(self):
        q = StockQuote.objects.create(customer=self.customer, quote_date=date(2026, 8, 3))
        d = StockDispatch.objects.create(item=self.item, customer=self.customer,
                                         date=date(2026, 8, 3), quantity=1, rate=Decimal('10'))
        self.assertEqual((q.number, d.invoice_no), ('REN2627-PI001', 'REN2627-IN001'))
        q.delete(); d.delete()
        q2 = StockQuote.objects.create(customer=self.customer, quote_date=date(2026, 8, 3))
        d2 = StockDispatch.objects.create(item=self.item, customer=self.customer,
                                          date=date(2026, 8, 3), quantity=1, rate=Decimal('10'))
        self.assertEqual((q2.number, d2.invoice_no), ('REN2627-PI002', 'REN2627-IN002'))

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

    def test_a_deleted_number_is_not_handed_out_again(self):
        """It went to a customer; deleting our copy does not unspend it."""
        first = self.dispatch()
        first.delete()
        self.assertTrue(self.dispatch().invoice_no.endswith('IN002'))

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
