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
