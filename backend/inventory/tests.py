"""Stock register: the derived ledger, its dashboard figures, and who may use it."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from .models import Vendor, StockItem, StockCustomer, GoodsReceipt, StockDispatch


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456')
    u.role = role
    u.save()
    return u


class StockLedgerTests(TestCase):
    """Closing stock is never stored — it is opening + received − dispatched."""

    def setUp(self):
        self.admin = mk('t_admin', 'admin')
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
        self.admin = mk('t_admin', 'admin')
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
        self.assertEqual(Decimal(d['month_purchases']), Decimal('450'))    # 5 × 90, this month only
        self.assertEqual(Decimal(d['month_sales']), Decimal('450'))        # 3 × 150
        self.assertEqual(d['reorder_count'], 1)                            # inverter: 2 <= 5
        self.assertEqual(d['reorder_alerts'][0]['code'], 'I1')
        by_cat = {c['name']: Decimal(c['value']) for c in d['by_category']}
        self.assertEqual(by_cat, {'Solar Panel': Decimal('1200'), 'Inverter': Decimal('10000')})


class StockAccessTests(TestCase):
    """The warehouse desk only: admins, general managers and purchase staff."""

    ENDPOINTS = ['/api/stock-items/', '/api/stock-customers/', '/api/goods-receipts/',
                 '/api/stock-dispatches/', '/api/stock-summary/']

    def check(self, user, allowed):
        for url in self.ENDPOINTS:
            r = self.client.get(url, HTTP_AUTHORIZATION=token_for(user))
            self.assertEqual(r.status_code, 200 if allowed else 403, f"{user.role} {url}")

    def test_allowed_roles(self):
        for role in ('superadmin', 'admin', 'coo', 'purchase_staff',
                     'store_manager', 'store_keeper', 'accounts_b2b'):
            self.check(mk(f't_{role}', role), True)

    def test_b2b_roles_can_run_the_register(self):
        """The stock register is the whole job for these three."""
        for role in ('store_manager', 'store_keeper', 'accounts_b2b'):
            u = mk(f'w_{role}', role)
            r = self.client.post('/api/stock-items/', data={'code': f'W-{role}'},
                                 content_type='application/json', HTTP_AUTHORIZATION=token_for(u))
            self.assertEqual(r.status_code, 201, role)

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
        self.admin = mk('d_admin', 'admin')
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
        self.admin = mk('q_admin', 'admin')
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
        self.assertTrue(d['number'].startswith('SQ-'))
        self.assertEqual(len(d['items']), 2)

    def test_a_quote_alone_does_not_move_stock(self):
        self.make_quote()
        self.panel.refresh_from_db()
        self.assertEqual(self.panel.closing_stock, 100)

    def test_converting_writes_one_dispatch_per_line(self):
        qid = self.make_quote().json()['id']
        r = self.client.post(f'/api/stock-quotes/{qid}/convert/', **self.auth())
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
        self.assertTrue(d.invoice_no.startswith('SQ-'))

    def test_converting_twice_is_refused(self):
        """A second convert would take the same goods out of stock again."""
        qid = self.make_quote().json()['id']
        self.client.post(f'/api/stock-quotes/{qid}/convert/', **self.auth())
        r = self.client.post(f'/api/stock-quotes/{qid}/convert/', **self.auth())
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

    def test_a_converted_quote_is_locked(self):
        qid = self.make_quote().json()['id']
        self.client.post(f'/api/stock-quotes/{qid}/convert/', **self.auth())
        r = self.client.patch(f'/api/stock-quotes/{qid}/', data={'tax_percent': '0'},
                              content_type='application/json', **self.auth())
        self.assertEqual(r.status_code, 400)
        r = self.client.delete(f'/api/stock-quotes/{qid}/', **self.auth())
        self.assertEqual(r.status_code, 400)

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
        self.admin = mk('s_admin', 'admin')
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

    def test_six_month_series_ends_this_month(self):
        d = self.get()
        self.assertEqual(len(d['monthly']), 6)
        last = d['monthly'][-1]
        self.assertEqual(Decimal(last['purchases']), Decimal('450'))    # 5 × 90
        self.assertEqual(Decimal(last['sales']), Decimal('300'))        # 2 × 150
        # Earlier months have no movement at all.
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
        for key in ('sku_count', 'total_value', 'reorder_count', 'month_purchases',
                    'month_sales', 'by_category', 'reorder_alerts', 'stock_levels'):
            self.assertIn(key, d)
        self.assertEqual(d['sku_count'], 1)
        self.assertEqual(Decimal(d['total_value']), Decimal('2300'))   # (20+5−2) × 100
