from datetime import date, datetime
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from leads.models import ActivityLog, BalancePayment, Lead, PaymentVerification, ReceiptVoucher
from users.models import User

from . import engine
from .models import (ContestResult, ExcludedPayment, RewardMonth, RewardSettings, RewardStanding,
                     RewardTier)

IST = ZoneInfo('Asia/Kolkata')
_seq = count(1)


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role, **extra):
    u = User.objects.create_user(username=username, password='Pw@123456', **extra)
    u.role = role
    u.save()
    return u


def at(day, hour=12):
    return datetime(day.year, day.month, day.day, hour, tzinfo=IST)


class GameTestCase(TestCase):
    """Builds deals and payments the way accounts records them."""

    def setUp(self):
        self.bde = mk('rw_bde', 'bde', first_name='Arun', last_name='BDE')
        self.bde2 = mk('rw_bde2', 'bde', first_name='Bindu', last_name='BDE')
        self.caller = mk('rw_caller', 'tele_caller', first_name='Chitra', last_name='Caller')
        self.rules = RewardSettings.load()

    def deal(self, value='100000', bde=None, caller=None, **flags):
        n = next(_seq)
        return Lead.objects.create(first_name=f'Customer{n}', phone=f'90000{n:05d}',
                                   status='converted', value=Decimal(value),
                                   bde=bde, tele_caller=caller, **flags)

    def paid(self, lead, amount, on, receipt=True):
        """The first payment, verified, with its money receipt."""
        pv, _ = PaymentVerification.objects.get_or_create(lead=lead)
        pv.amount_received = Decimal(amount)
        pv.payment_mode = 'upi'
        pv.is_complete = True
        pv.completed_at = at(on)
        pv.save()
        if receipt:
            n = next(_seq)
            ReceiptVoucher.objects.create(lead=lead, is_initial=True, number=f'ER/T/{n}',
                                          fy='T', seq=n, date=on, amount=Decimal(amount))
        return pv

    def instalment(self, lead, amount, on):
        bp = BalancePayment.objects.create(lead=lead, amount=Decimal(amount), payment_mode='upi')
        BalancePayment.objects.filter(pk=bp.pk).update(created_at=at(on))
        pv = lead.payment_verification
        pv.amount_received = (pv.amount_received or 0) + Decimal(amount)
        pv.save(update_fields=['amount_received'])

    def points(self, start, end):
        tally = engine.points_between(start, end, RewardSettings.load())
        return {uid: t['points'] for uid, t in tally.items()}


class PointsTests(GameTestCase):
    SEPT = (date(2026, 9, 1), date(2026, 9, 30))
    OCT = (date(2026, 10, 1), date(2026, 10, 31))

    def test_points_are_money_received_not_the_deal_value(self):
        lead = self.deal('100000', bde=self.bde)
        self.paid(lead, '50000', date(2026, 9, 10))
        self.assertEqual(self.points(*self.SEPT), {self.bde.id: Decimal('50000')})

    def test_the_rest_arrives_with_the_rest_of_the_money(self):
        lead = self.deal('100000', bde=self.bde)
        self.paid(lead, '50000', date(2026, 9, 10))
        self.instalment(lead, '50000', date(2026, 10, 5))
        self.assertEqual(self.points(*self.SEPT)[self.bde.id], Decimal('50000'))
        self.assertEqual(self.points(*self.OCT)[self.bde.id], Decimal('50000'))

    def test_two_owners_split_75_25(self):
        lead = self.deal('100000', bde=self.bde, caller=self.caller)
        self.paid(lead, '100000', date(2026, 9, 10))
        self.assertEqual(self.points(*self.SEPT),
                         {self.bde.id: Decimal('75000'), self.caller.id: Decimal('25000')})

    def test_the_split_follows_the_settings(self):
        RewardSettings.objects.filter(pk=1).update(bde_share=Decimal('60'))
        lead = self.deal('100000', bde=self.bde, caller=self.caller)
        self.paid(lead, '100000', date(2026, 9, 10))
        self.assertEqual(self.points(*self.SEPT),
                         {self.bde.id: Decimal('60000'), self.caller.id: Decimal('40000')})

    def test_one_owner_takes_it_all(self):
        alone = self.deal('80000', bde=self.bde)
        self.paid(alone, '80000', date(2026, 9, 10))
        both_hats = self.deal('20000', bde=self.bde, caller=self.bde)
        self.paid(both_hats, '20000', date(2026, 9, 11))
        self.assertEqual(self.points(*self.SEPT), {self.bde.id: Decimal('100000')})

    def test_an_unverified_payment_does_not_count(self):
        lead = self.deal('100000', bde=self.bde)
        PaymentVerification.objects.create(lead=lead, amount_received=Decimal('50000'))
        self.assertEqual(self.points(*self.SEPT), {})

    def test_lost_and_deleted_deals_do_not_count(self):
        lost = self.deal('100000', bde=self.bde, is_lost=True)
        self.paid(lost, '50000', date(2026, 9, 10))
        gone = self.deal('100000', bde=self.bde, is_trashed=True)
        self.paid(gone, '50000', date(2026, 9, 10))
        self.assertEqual(self.points(*self.SEPT), {})

    def test_a_deal_verified_before_receipts_existed_still_counts(self):
        lead = self.deal('100000', bde=self.bde)
        self.paid(lead, '70000', date(2026, 9, 10), receipt=False)
        self.instalment(lead, '30000', date(2026, 10, 2))
        self.assertEqual(self.points(*self.SEPT)[self.bde.id], Decimal('70000'))
        self.assertEqual(self.points(*self.OCT)[self.bde.id], Decimal('30000'))


class LadderTests(GameTestCase):
    def setUp(self):
        super().setUp()
        RewardTier.objects.create(position=0, name='Bronze', reward='Movie tickets',
                                  target=Decimal('100000'), target_telecaller=Decimal('25000'))
        RewardTier.objects.create(position=1, name='Silver', reward='Smartwatch',
                                  target=Decimal('200000'), target_telecaller=Decimal('50000'))

    def test_reaching_a_tier_unlocks_its_reward(self):
        climb = engine.climb(Decimal('150000'), 'bde', engine.ladder())
        self.assertEqual(climb['reached'], 1)
        self.assertEqual(climb['current']['name'], 'Bronze')
        self.assertEqual(climb['next']['name'], 'Silver')
        self.assertEqual(Decimal(climb['needed']), Decimal('50000'))
        self.assertEqual(climb['rewards'], ['Movie tickets'])
        self.assertAlmostEqual(climb['progress'], 0.75)

    def test_tele_callers_climb_their_own_targets(self):
        climb = engine.climb(Decimal('30000'), 'tele_caller', engine.ladder())
        self.assertEqual(climb['current']['name'], 'Bronze')
        self.assertEqual(engine.climb(Decimal('30000'), 'bde', engine.ladder())['reached'], 0)

    def test_the_top_of_the_ladder(self):
        climb = engine.climb(Decimal('500000'), 'bde', engine.ladder())
        self.assertEqual(climb['reached'], 2)
        self.assertIsNone(climb['next'])
        self.assertEqual(climb['progress'], 1.0)

    def test_the_ladder_starts_again_each_month(self):
        lead = self.deal('150000', bde=self.bde)
        self.paid(lead, '150000', date(2026, 9, 10))
        oct_rows = engine.standings(date(2026, 10, 1), date(2026, 10, 31),
                                    RewardSettings.load(), engine.ladder())
        mine = next(r for r in oct_rows if r['user'] == self.bde.id)
        self.assertEqual(mine['tier']['reached'], 0)


class MonthCloseTests(GameTestCase):
    def setUp(self):
        super().setUp()
        RewardSettings.objects.filter(pk=1).update(
            program_start=date(2026, 9, 1), gold_prize='Weekend trip',
            silver_prize='Smartwatch', bronze_prize='Dinner voucher')
        self.admin = mk('rw_admin', 'admin')
        self.accounts = mk('rw_accounts', 'accounts_staff')
        self.bde3 = mk('rw_bde3', 'bde', first_name='Deepa', last_name='BDE')
        for user, amount in ((self.bde, '300000'), (self.bde2, '200000'),
                             (self.bde3, '100000'), (self.caller, '0')):
            if amount != '0':
                self.paid(self.deal(amount, bde=user), amount, date(2026, 9, 15))

    def notifications(self, **filters):
        from ai_manager.models import Notification
        return Notification.objects.filter(notification_type='achievement', **filters)

    def test_a_finished_month_crowns_its_top_three(self):
        engine.close_due(today=date(2026, 10, 2))
        month = RewardMonth.objects.get(year=2026, month=9)
        medals = {s.user_id: (s.medal, s.prize, s.coins) for s in month.standings.exclude(medal='')}
        self.assertEqual(medals, {
            self.bde.id: ('gold', 'Weekend trip', 30),
            self.bde2.id: ('silver', 'Smartwatch', 20),
            self.bde3.id: ('bronze', 'Dinner voucher', 10),
        })
        # Everyone who plays is on the record, points or not.
        self.assertTrue(month.standings.filter(user=self.caller, points=0).exists())

    def test_it_is_announced_to_the_team_and_the_winners(self):
        engine.close_due(today=date(2026, 10, 2))
        self.assertTrue(self.notifications(user=self.caller, title__contains='September 2026').exists())
        self.assertTrue(self.notifications(user=self.admin, title__contains='champions').exists())
        self.assertFalse(self.notifications(user=self.accounts).exists())
        self.assertTrue(self.notifications(user=self.bde, title__contains='You won gold').exists())

    def test_a_month_is_decided_once(self):
        engine.close_due(today=date(2026, 10, 2))
        before = self.notifications().count()
        engine.close_due(today=date(2026, 10, 3))
        self.assertEqual(RewardMonth.objects.filter(year=2026, month=9).count(), 1)
        self.assertEqual(self.notifications().count(), before)

    def test_the_result_stands_after_a_payment_is_changed(self):
        engine.close_due(today=date(2026, 10, 2))
        PaymentVerification.objects.filter(lead__bde=self.bde).update(is_complete=False)
        gold = RewardStanding.objects.get(reward_month__year=2026, reward_month__month=9, medal='gold')
        self.assertEqual(gold.user_id, self.bde.id)

    def test_an_empty_month_crowns_nobody(self):
        engine.close_month(date(2026, 8, 1))
        self.assertFalse(RewardStanding.objects.filter(reward_month__month=8).exclude(medal='').exists())
        self.assertFalse(self.notifications(title__contains='August').exists())

    def test_months_before_the_game_began_are_left_alone(self):
        RewardSettings.objects.filter(pk=1).update(program_start=date(2026, 10, 1))
        engine.close_due(today=date(2026, 10, 20))
        self.assertFalse(RewardMonth.objects.exists())


class IncentiveTests(GameTestCase):
    def setUp(self):
        super().setUp()
        from inventory.models import ProjectSpec
        self.project = ProjectSpec.objects.create(name='5 kW On-grid', bde_incentive=Decimal('2000'),
                                                  telecaller_incentive=Decimal('500'))

    def ordered(self, lead, project=None):
        from inventory.models import Quotation
        q = Quotation.objects.create(lead=lead, project=project or self.project, status='accepted')
        Quotation.objects.filter(pk=q.pk).update(order_converted_at=timezone.now())
        return q

    def incentives(self, start, end):
        return {uid: v['total'] for uid, v in engine.incentives_between(start, end).items()}

    def test_paid_in_the_month_the_customer_finishes_paying(self):
        lead = self.deal('100000', bde=self.bde, caller=self.caller)
        self.ordered(lead)
        self.paid(lead, '50000', date(2026, 9, 10))
        self.instalment(lead, '50000', date(2026, 10, 5))
        self.assertEqual(self.incentives(date(2026, 9, 1), date(2026, 9, 30)), {})
        self.assertEqual(self.incentives(date(2026, 10, 1), date(2026, 10, 31)),
                         {self.bde.id: Decimal('2000'), self.caller.id: Decimal('500')})

    def test_paid_in_full_up_front_pays_at_once(self):
        lead = self.deal('100000', bde=self.bde)
        self.ordered(lead)
        self.paid(lead, '100000', date(2026, 9, 10))
        self.assertEqual(self.incentives(date(2026, 9, 1), date(2026, 9, 30)),
                         {self.bde.id: Decimal('2000')})

    def test_no_project_no_incentive(self):
        lead = self.deal('100000', bde=self.bde)
        self.paid(lead, '100000', date(2026, 9, 10))
        self.assertEqual(self.incentives(date(2026, 9, 1), date(2026, 9, 30)), {})

    def test_the_latest_order_is_the_project_that_was_bought(self):
        from inventory.models import ProjectSpec
        bigger = ProjectSpec.objects.create(name='10 kW', bde_incentive=Decimal('5000'))
        lead = self.deal('100000', bde=self.bde)
        self.ordered(lead)
        self.ordered(lead, bigger)
        self.paid(lead, '100000', date(2026, 9, 10))
        self.assertEqual(self.incentives(date(2026, 9, 1), date(2026, 9, 30)),
                         {self.bde.id: Decimal('5000')})


class ContestTests(GameTestCase):
    def setUp(self):
        super().setUp()
        RewardSettings.objects.filter(pk=1).update(
            program_start=date(2026, 9, 1), contest_name='FY Championship',
            contest_start=date(2026, 9, 1), contest_end=date(2026, 9, 30),
            bumper_first='Goa trip', bumper_second='iPad', bumper_third='Headphones',
            coin_champion_prize='Gold coin')
        self.paid(self.deal('300000', bde=self.bde), '300000', date(2026, 9, 10))
        self.paid(self.deal('200000', bde=self.bde2), '200000', date(2026, 9, 12))

    def test_it_is_awarded_once_it_is_over_and_its_last_month_has_closed(self):
        engine.close_due(today=date(2026, 9, 30))
        self.assertFalse(ContestResult.objects.exists())
        engine.close_due(today=date(2026, 10, 1))
        result = ContestResult.objects.get()
        self.assertEqual([(w['user'], w['prize']) for w in result.winners],
                         [(self.bde.id, 'Goa trip'), (self.bde2.id, 'iPad')])
        # September's gold brought 30 coins, the most anyone holds.
        self.assertEqual(result.coin_champion['user'], self.bde.id)
        self.assertEqual(result.coin_champion['coins'], 30)
        self.assertEqual(result.coin_champion['prize'], 'Gold coin')

    def test_the_table_counts_points_inside_the_window_only(self):
        self.paid(self.deal('900000', bde=self.bde2), '900000', date(2026, 10, 3))
        rows = engine.contest_table(RewardSettings.load(), date(2026, 10, 5))
        self.assertEqual(rows[0]['user'], self.bde.id)


class RewardsApiTests(GameTestCase):
    URL = '/api/rewards/'

    def setUp(self):
        super().setUp()
        self.admin = mk('rw_api_admin', 'admin')
        today = timezone.localdate()
        RewardTier.objects.create(position=0, name='Bronze', reward='Movie tickets',
                                  target=Decimal('50000'), target_telecaller=Decimal('10000'))
        from inventory.models import ProjectSpec, Quotation
        project = ProjectSpec.objects.create(name='3 kW', bde_incentive=Decimal('1500'),
                                             telecaller_incentive=Decimal('300'))
        lead = self.deal('100000', bde=self.bde, caller=self.caller)
        q = Quotation.objects.create(lead=lead, project=project, status='accepted')
        Quotation.objects.filter(pk=q.pk).update(order_converted_at=timezone.now())
        self.paid(lead, '100000', today)

    def get(self, user, query=''):
        return self.client.get(self.URL + query, HTTP_AUTHORIZATION=token_for(user))

    def test_a_bde_sees_their_own_card(self):
        r = self.get(self.bde)
        self.assertEqual(r.status_code, 200, r.content[:300])
        me = r.json()['me']
        self.assertEqual(Decimal(me['points']), Decimal('75000'))
        self.assertEqual(me['rank'], 1)
        self.assertEqual(me['tier']['current']['name'], 'Bronze')
        self.assertEqual(Decimal(me['incentives']['total']), Decimal('1500'))

    def test_the_table_shows_points_but_only_your_own_incentives(self):
        board = self.get(self.caller).json()['board']
        bde_row = next(r for r in board if r['user'] == self.bde.id)
        caller_row = next(r for r in board if r['user'] == self.caller.id)
        self.assertEqual(Decimal(bde_row['points']), Decimal('75000'))
        self.assertNotIn('incentives', bde_row)
        self.assertEqual(Decimal(caller_row['incentives']), Decimal('300'))

    def test_an_admin_sees_the_whole_picture_and_can_open_a_card(self):
        r = self.get(self.admin, f'?user={self.caller.id}').json()
        self.assertTrue(r['is_admin'])
        self.assertEqual(r['me']['user'], self.caller.id)
        self.assertEqual(Decimal(r['me']['points']), Decimal('25000'))
        self.assertIn('incentives', r['board'][0])
        self.assertEqual(r['kpis']['scoring'], 2)

    def test_it_is_for_the_sales_team_and_its_admins(self):
        for role in ('accounts_staff', 'documentation_manager', 'project_manager'):
            self.assertEqual(self.get(mk(f'rw_{role}', role)).status_code, 403, role)

    def test_settings_are_for_admins(self):
        self.assertEqual(self.client.get(self.URL + 'settings/',
                                         HTTP_AUTHORIZATION=token_for(self.bde)).status_code, 403)
        r = self.client.put(self.URL + 'settings/', data={'bde_share': '50'},
                            content_type='application/json', HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403)

    def put_settings(self, body, user=None):
        return self.client.put(self.URL + 'settings/', data=body, content_type='application/json',
                               HTTP_AUTHORIZATION=token_for(user or self.admin))

    def test_an_admin_sets_the_rules_and_the_ladder(self):
        r = self.put_settings({
            'bde_share': '70', 'gold_prize': 'Trip', 'gold_coins': 40,
            'tiers': [{'name': 'Starter', 'reward': 'Lunch', 'target': '100000',
                       'target_telecaller': '30000'},
                      {'name': 'Pro', 'reward': 'Watch', 'target': '300000', 'target_telecaller': '90000'}],
        })
        self.assertEqual(r.status_code, 200, r.content[:300])
        rules = RewardSettings.load()
        self.assertEqual(rules.bde_share, Decimal('70'))
        self.assertEqual(rules.gold_coins, 40)
        self.assertEqual([t.name for t in RewardTier.objects.all()], ['Starter', 'Pro'])
        self.assertEqual(r.json()['tiers'][1]['target_telecaller'], '90000.00')

    def test_a_super_admin_can_too(self):
        boss = mk('rw_super', 'superadmin')
        self.assertEqual(self.put_settings({'silver_coins': 25}, boss).status_code, 200)

    def test_tiers_have_to_climb(self):
        r = self.put_settings({'tiers': [{'name': 'A', 'target': '200000'},
                                         {'name': 'B', 'target': '100000'}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn('higher', str(r.json()))

    def test_tele_caller_targets_have_to_climb_too(self):
        r = self.put_settings({'tiers': [
            {'name': 'A', 'target': '100000', 'target_telecaller': '50000'},
            {'name': 'B', 'target': '200000', 'target_telecaller': '40000'}]})
        self.assertEqual(r.status_code, 400)

    def test_a_contest_needs_both_dates_in_order(self):
        self.assertEqual(self.put_settings({'contest_start': '2026-04-01'}).status_code, 400)
        self.assertEqual(self.put_settings({'contest_start': '2027-04-01',
                                            'contest_end': '2026-04-01'}).status_code, 400)
        self.assertEqual(self.put_settings({'contest_start': '2026-04-01',
                                            'contest_end': '2027-03-31'}).status_code, 200)

    def test_the_share_is_a_percentage(self):
        self.assertEqual(self.put_settings({'bde_share': '120'}).status_code, 400)

    def test_the_card_shows_the_contest(self):
        today = timezone.localdate()
        RewardSettings.objects.filter(pk=1).update(
            contest_name='Championship', contest_start=today.replace(day=1),
            contest_end=today.replace(year=today.year + 1), bumper_first='Car')
        contest = self.get(self.bde).json()['contest']
        self.assertEqual(contest['status'], 'running')
        self.assertEqual(contest['board'][0]['user'], self.bde.id)
        self.assertEqual(contest['bumpers'][0]['prize'], 'Car')


class LedgerSafeguardTests(GameTestCase):
    """Money lands in the month it came in, whatever accounts did afterwards."""
    JULY = (date(2026, 7, 1), date(2026, 7, 31))
    AUG = (date(2026, 8, 1), date(2026, 8, 31))
    OCT = (date(2026, 10, 1), date(2026, 10, 31))

    def note_verified(self, lead, on):
        log = ActivityLog.objects.create(activity_type='note_added', lead=lead,
                                         description=f'{engine.VERIFIED_NOTE} Anu.')
        ActivityLog.objects.filter(pk=log.pk).update(created_at=at(on))

    def verify_again(self, lead, on):
        """Reopen and complete again: the verification takes the new day, and a
        lead verified before receipts existed gets a first receipt dated that
        day for everything received so far."""
        pv = PaymentVerification.objects.get(lead=lead)
        pv.completed_at = at(on)
        pv.save(update_fields=['completed_at'])
        if not ReceiptVoucher.objects.filter(lead=lead, is_initial=True).exists():
            n = next(_seq)
            ReceiptVoucher.objects.create(lead=lead, is_initial=True, number=f'ER/T/{n}', fy='T',
                                          seq=n, date=on, amount=pv.amount_received)

    def test_verifying_again_leaves_the_first_payment_where_it_was(self):
        lead = self.deal('300000', bde=self.bde)
        self.paid(lead, '100000', date(2026, 7, 10), receipt=False)
        self.note_verified(lead, date(2026, 7, 10))
        self.instalment(lead, '50000', date(2026, 8, 5))
        self.verify_again(lead, date(2026, 10, 17))
        self.assertEqual(self.points(*self.OCT), {})
        self.assertEqual(self.points(*self.JULY), {self.bde.id: Decimal('100000')})
        self.assertEqual(self.points(*self.AUG), {self.bde.id: Decimal('50000')})

    def test_with_no_note_it_counts_no_later_than_the_balance_payment_after_it(self):
        lead = self.deal('300000', bde=self.bde)
        self.paid(lead, '100000', date(2026, 7, 10), receipt=False)
        self.instalment(lead, '50000', date(2026, 8, 5))
        self.verify_again(lead, date(2026, 10, 17))
        self.assertEqual(self.points(*self.OCT), {})
        # Counted once each: the receipt for 1,50,000 is not counted on top.
        self.assertEqual(self.points(*self.AUG), {self.bde.id: Decimal('150000')})

    def test_a_corrected_first_payment_counts_as_corrected(self):
        lead = self.deal('300000', bde=self.bde)
        pv = self.paid(lead, '500000', date(2026, 10, 3))   # typed a zero too many
        pv.amount_received = Decimal('50000')
        pv.save(update_fields=['amount_received'])
        self.assertEqual(self.points(*self.OCT), {self.bde.id: Decimal('50000')})

    def test_never_more_than_the_receipt(self):
        lead = self.deal('300000', bde=self.bde)
        pv = self.paid(lead, '50000', date(2026, 10, 3))
        pv.amount_received = Decimal('80000')
        pv.save(update_fields=['amount_received'])
        self.assertEqual(self.points(*self.OCT), {self.bde.id: Decimal('50000')})

    def test_the_note_read_here_is_the_one_accounts_leave(self):
        admin = mk('rw_acc_admin', 'admin')
        lead = self.deal('300000', bde=self.bde, pushed_to_accounts=True)
        PaymentVerification.objects.create(lead=lead, amount_received=Decimal('100000'),
                                           payment_mode='cash')
        r = self.client.post(f'/api/leads/{lead.id}/complete-payment-verification/',
                             HTTP_AUTHORIZATION=token_for(admin))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertTrue(ActivityLog.objects.filter(
            lead=lead, description__startswith=engine.VERIFIED_NOTE).exists())


class StatementTests(GameTestCase):
    OCT = (date(2026, 10, 1), date(2026, 10, 31))

    def lines(self, user):
        return engine.statement(user, *self.OCT, RewardSettings.load())

    def test_every_payment_behind_the_points(self):
        shared = self.deal('200000', bde=self.bde, caller=self.caller)
        self.paid(shared, '100000', date(2026, 10, 3))
        self.instalment(shared, '40000', date(2026, 10, 9))
        alone = self.deal('80000', bde=self.bde)
        self.paid(alone, '80000', date(2026, 10, 5))

        lines = self.lines(self.bde)
        self.assertEqual([(l['kind'], l['on'], l['points'], l['share']) for l in lines], [
            ('balance', '2026-10-09', '30000.00', '75.00'),
            ('first', '2026-10-05', '80000.00', '100.00'),
            ('first', '2026-10-03', '75000.00', '75.00'),
        ])
        self.assertEqual(lines[2]['partner'], 'Chitra Caller')
        self.assertEqual(lines[2]['deal_value'], '200000.00')
        self.assertTrue(lines[2]['receipt'])
        counted = sum(Decimal(l['points']) for l in lines if l['status'] == 'counted')
        self.assertEqual(counted, self.points(*self.OCT)[self.bde.id])

    def test_a_tele_caller_sees_their_share(self):
        lead = self.deal('100000', bde=self.bde, caller=self.caller)
        self.paid(lead, '100000', date(2026, 10, 3))
        [line] = self.lines(self.caller)
        self.assertEqual((line['as'], line['share'], line['points'], line['partner']),
                         ('tele_caller', '25.00', '25000.00', 'Arun BDE'))

    def test_what_does_not_count_is_listed_with_the_reason(self):
        lead = self.deal('100000', bde=self.bde, is_lost=True)
        self.paid(lead, '50000', date(2026, 10, 3))
        [line] = self.lines(self.bde)
        self.assertEqual((line['status'], line['reason']), ('lost', 'The deal was marked lost.'))

    def test_it_shows_when_the_po_was_signed(self):
        from leads.models import SiteVisit
        lead = self.deal('100000', bde=self.bde)
        SiteVisit.objects.create(lead=lead, po_signed_date=date(2026, 8, 20))
        self.paid(lead, '100000', date(2026, 10, 3))
        self.assertEqual(self.lines(self.bde)[0]['po_signed'], '2026-08-20')


class ExclusionTests(GameTestCase):
    URL = '/api/rewards/exclusions/'

    def setUp(self):
        super().setUp()
        self.admin = mk('rw_ex_admin', 'admin')
        self.today = timezone.localdate()
        self.lead = self.deal('300000', bde=self.bde)
        self.paid(self.lead, '200000', self.today)
        self.key = f'first:{self.lead.id}'

    def month_points(self):
        start, end = engine.month_bounds(self.today.replace(day=1))
        return self.points(start, end)

    def take_out(self, user=None, **body):
        return self.client.post(self.URL, data={'key': self.key, 'reason': 'Paid in August', **body},
                                content_type='application/json',
                                HTTP_AUTHORIZATION=token_for(user or self.admin))

    def test_an_admin_takes_a_payment_out_and_puts_it_back(self):
        self.assertEqual(self.take_out().status_code, 201)
        self.assertEqual(self.month_points(), {})
        me = self.client.get('/api/rewards/', HTTP_AUTHORIZATION=token_for(self.bde)).json()['me']
        self.assertEqual(Decimal(me['points']), 0)
        [line] = me['statement']
        self.assertEqual((line['status'], line['reason'], line['excluded_by']),
                         ('excluded', 'Paid in August', engine.display_name(self.admin)))

        r = self.client.delete(f'{self.URL}?key={self.key}', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.month_points(), {self.bde.id: Decimal('200000')})

    def test_the_contest_stops_counting_it_too(self):
        RewardSettings.objects.filter(pk=1).update(
            contest_start=self.today.replace(day=1),
            contest_end=self.today.replace(year=self.today.year + 1))
        self.take_out()
        rows = engine.contest_table(RewardSettings.load(), self.today)
        self.assertEqual(next(r for r in rows if r['user'] == self.bde.id)['points'], 0)

    def test_only_admins(self):
        self.assertEqual(self.take_out(user=self.bde).status_code, 403)
        self.assertFalse(ExcludedPayment.objects.exists())

    def test_it_needs_a_reason_and_a_real_payment(self):
        self.assertEqual(self.take_out(reason='  ').status_code, 400)
        self.assertEqual(self.take_out(key='first:999999').status_code, 404)
        self.assertEqual(self.take_out(key='nonsense').status_code, 404)

    def test_a_balance_payment_can_be_taken_out_on_its_own(self):
        self.instalment(self.lead, '50000', self.today)
        bp = BalancePayment.objects.get(lead=self.lead)
        self.assertEqual(self.take_out(key=f'balance:{bp.id}').status_code, 201)
        self.assertEqual(self.month_points(), {self.bde.id: Decimal('200000')})
