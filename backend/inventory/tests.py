"""Stock register: the derived ledger, its dashboard figures, and who may use it."""
from datetime import date
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
                     StockPurchaseOrder, StockQuote, StockQuoteItem, Quote)


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
        self.assertEqual(Decimal(d['month_purchases']), Decimal('450'))    # 5 × 90, this month only
        self.assertEqual(Decimal(d['month_sales']), Decimal('450'))        # 3 × 150
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
        for role in ('superadmin', 'coo', 'purchase_staff',
                     'store_manager', 'store_keeper', 'accounts_b2b'):
            self.check(mk(f't_{role}', role), True)

    def test_an_admin_has_no_wholesale_access(self):
        """The B2C/B2B switch is the super admin's and the COO's; the API agrees,
        so an admin cannot reach the register by calling it directly."""
        self.check(mk('t_admin_b2b', 'admin'), False)

    def test_the_other_managers_have_none_either(self):
        for role in ('sales_manager', 'documentation_manager', 'accounts_manager',
                     'branch_manager', 'project_manager', 'liasoning_officer'):
            self.check(mk(f't_mgr_{role}', role), False)

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
        self.assertTrue(d.invoice_no.startswith('REN') and '-IN' in d.invoice_no, d.invoice_no)

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

    def test_a_converted_quote_can_no_longer_be_edited(self):
        """Editing it would diverge from the dispatches already written from it.

        Deleting is a different matter and is allowed — the dispatch stands on
        its own; see StockQuoteDeletionTests.
        """
        qid = self.make_quote().json()['id']
        self.client.post(f'/api/stock-quotes/{qid}/convert/', **self.auth())
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
        self.client.post(f'/api/stock-quotes/{qid}/convert/', **self.auth())
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
        self.client.post(f'/api/stock-quotes/{qid}/convert/', **self.auth())
        d = StockDispatch.objects.get(item=self.item)
        self.assertEqual(d.tax_percent, Decimal('18.00'))
        self.assertEqual(d.total, Decimal('132160'))

    def test_the_dashboard_reports_the_invoiced_value(self):
        self.client.post('/api/stock-dispatches/', data={
            'date': str(timezone.localdate()), 'item': self.item.id,
            'quantity': '10', 'rate': '11200', 'tax_percent': '18',
        }, content_type='application/json', **self.auth())
        r = self.client.get('/api/stock-summary/', **self.auth())
        self.assertEqual(Decimal(r.json()['month_sales']), Decimal('132160'))
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
        r = self.client.post(f'/api/stock-quotes/{q.id}/convert/',
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
        self.client.post(f'/api/stock-quotes/{q.id}/convert/',
                         HTTP_AUTHORIZATION=token_for(self.admin))
        q.refresh_from_db()
        self.assertEqual(q.status, 'converted')
        self.assertEqual(self.delete(q).status_code, 204)

    def test_deleting_it_leaves_the_sale_alone(self):
        """The dispatch keeps its invoice number and its stock movement."""
        q = self.make_quote()
        self.client.post(f'/api/stock-quotes/{q.id}/convert/',
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
