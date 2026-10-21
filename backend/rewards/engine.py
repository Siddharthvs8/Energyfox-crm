"""How the game is scored.

Everything starts from money received. One point per rupee, dated by the day
the payment came in, so a deal worth a lakh with half of it paid has earned
half its points — the rest arrive with the rest of the money. A payment's
points go to the deal's owners: all of it to a BDE who sold alone, and split
(75/25 unless the admins say otherwise) when a tele caller found the lead and
a BDE closed it.

Incentives are separate: rupees, not points, paid per project to the deal's
BDE and tele caller in the month the customer finishes paying.
"""
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Min, Q, Sum
from django.utils import timezone

from .models import (PARTICIPANT_ROLES, ContestResult, RewardMonth, RewardSettings,
                     RewardStanding, RewardTier)

ZERO = Decimal('0')
CENT = Decimal('0.01')
MEDALS = ('gold', 'silver', 'bronze')


# ─── Calendar ────────────────────────────────────────────────────────────────
def month_bounds(first):
    return first, first.replace(day=monthrange(first.year, first.month)[1])


def next_month(first):
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1)


def previous_month(first):
    return (first - timedelta(days=1)).replace(day=1)


def _day(dt):
    return timezone.localtime(dt).date() if dt else None


# ─── The ledger ──────────────────────────────────────────────────────────────
# The note LeadViewSet.complete_payment_verification leaves on a lead every time
# accounts verify its payment. The earliest is when the payment was first
# verified, whatever happened to the verification afterwards.
VERIFIED_NOTE = 'Payment verification completed by'


@dataclass(frozen=True)
class Payment:
    """One payment received.

    `on` is the day it counts on and `booked` the day accounts verified or
    recorded it: the same day, unless the payment was verified again later.
    """
    lead_id: int
    on: date
    amount: Decimal
    kind: str = 'balance'               # 'first' — taken at verification — or 'balance'
    ref: int | None = None              # the balance payment's id
    receipt: str = ''                   # the number on its money receipt
    booked: date | None = None
    receipt_amount: Decimal | None = None   # what its receipt says, when that is not what counts

    @property
    def key(self):
        """Names the payment for an admin taking it out of the game."""
        return f'first:{self.lead_id}' if self.kind == 'first' else f'balance:{self.ref}'


def ledger(start=None, end=None, lead_ids=None):
    """Every payment received, optionally within [start, end] (IST days) and
    for some leads only.

    The same ledger the Accounts screen shows (LeadViewSet._payment_ledger):
    the first payment is taken at verification and dated by its money receipt
    — or, on leads older than receipts, by when the verification was
    completed — and each balance payment after it is its own entry. A first
    payment accounts have not verified is not counted: until they do, it is a
    figure someone typed rather than money in the bank.

    Two things accounts do to a verification afterwards would otherwise put
    money in the wrong month or count it twice, so the first payment is
    guarded against both:

    * Verifying it again. Reopening a verification and completing it again
      stamps it with that day — and on a lead verified before receipts
      existed, issues a receipt dated that day for everything received so
      far, balance payments included. So the first payment counts on the day
      the lead was first verified, and never later than a balance payment
      that came after it.
    * Correcting it. A receipt is never reissued, so a figure corrected after
      the receipt was printed stays wrong on the receipt. The first payment
      counts as what the verification says now — everything received less the
      balance payments — and never more than its receipt.
    """
    from leads.models import ActivityLog, BalancePayment, PaymentVerification, ReceiptVoucher

    def in_window(day):
        return day is not None and (start is None or day >= start) and (end is None or day <= end)

    out = []
    verified = PaymentVerification.objects.filter(is_complete=True)
    if lead_ids is not None:
        verified = verified.filter(lead_id__in=lead_ids)
    if start is not None:
        # A first payment never counts later than the day it was booked, so one
        # booked before the window cannot fall in it.
        initial = ReceiptVoucher.objects.filter(is_initial=True)
        verified = verified.filter(
            Q(lead_id__in=initial.filter(date__gte=start).values('lead_id'))
            | (~Q(lead_id__in=initial.values('lead_id'))
               & (Q(completed_at__date__gte=start)
                  | Q(completed_at__isnull=True, created_at__date__gte=start))))
    verified = list(verified.only('lead_id', 'amount_received', 'completed_at', 'created_at'))

    ids = [pv.lead_id for pv in verified]
    receipts = {}
    # If a lead somehow has two first receipts, the earliest is the real one.
    for r in (ReceiptVoucher.objects.filter(is_initial=True, lead_id__in=ids)
              .order_by('lead_id', 'created_at', 'id')):
        receipts.setdefault(r.lead_id, r)
    balances = {row['lead_id']: row for row in
                BalancePayment.objects.filter(lead_id__in=ids).order_by()
                .values('lead_id').annotate(total=Sum('amount'), first=Min('created_at'))}
    first_verified = dict(ActivityLog.objects.filter(lead_id__in=ids, description__startswith=VERIFIED_NOTE)
                          .order_by().values('lead_id').annotate(first=Min('created_at'))
                          .values_list('lead_id', 'first'))

    for pv in verified:
        receipt = receipts.get(pv.lead_id)
        balance = balances.get(pv.lead_id) or {}
        amount = (pv.amount_received or ZERO) - (balance.get('total') or ZERO)
        if receipt is not None:
            booked = receipt.date
            amount = min(amount, receipt.amount)
        else:
            booked = _day(pv.completed_at or pv.created_at)
        on = min(d for d in (booked, _day(first_verified.get(pv.lead_id)), _day(balance.get('first'))) if d)
        if amount > 0 and in_window(on):
            out.append(Payment(
                pv.lead_id, on, amount, kind='first', booked=booked,
                receipt=receipt.number if receipt else '',
                receipt_amount=receipt.amount if receipt is not None and receipt.amount != amount else None))

    later = BalancePayment.objects.select_related('receipt')
    if lead_ids is not None:
        later = later.filter(lead_id__in=lead_ids)
    if start is not None:
        later = later.filter(created_at__date__gte=start)
    if end is not None:
        later = later.filter(created_at__date__lte=end)
    for bp in later:
        if bp.amount and bp.amount > 0:
            receipt = getattr(bp, 'receipt', None)
            day = _day(bp.created_at)
            out.append(Payment(bp.lead_id, day, bp.amount, ref=bp.id, booked=day,
                               receipt=receipt.number if receipt else ''))
    return out


def counting_deals(lead_ids):
    """The deals behind some payments that still count: not lost, not deleted."""
    from leads.models import Lead
    ids = set(lead_ids)
    if not ids:
        return {}
    return {lead.id: lead for lead in Lead.objects.filter(id__in=ids, is_trashed=False, is_lost=False)}


def taken_out():
    """The payments admins have taken out of the game: {key: ExcludedPayment}."""
    from .models import ExcludedPayment
    return {e.key: e for e in ExcludedPayment.objects.select_related('excluded_by')}


def payment_lead(key):
    """The lead a payment key belongs to, or None if it names no payment."""
    from leads.models import BalancePayment, Lead
    kind, _, ref = str(key or '').partition(':')
    if not ref.isdigit():
        return None
    if kind == 'first':
        return Lead.objects.filter(pk=int(ref), payment_verification__is_complete=True).first()
    if kind == 'balance':
        bp = BalancePayment.objects.select_related('lead').filter(pk=int(ref)).first()
        return bp.lead if bp else None
    return None


def shares(lead, amount, bde_share):
    """Who earns a payment: [(user_id, points)].

    Two owners — a tele caller who found the customer and a BDE who closed
    them — split it. One owner takes all of it; that is a BDE who sold on their
    own, or the odd lead nobody handed to a BDE.
    """
    bde, caller = lead.bde_id, lead.tele_caller_id
    if bde and caller and bde != caller:
        to_bde = (amount * (bde_share or ZERO) / Decimal('100')).quantize(CENT)
        return [(bde, to_bde), (caller, amount - to_bde)]
    if bde:
        return [(bde, amount)]
    if caller:
        return [(caller, amount)]
    return []


def points_between(start, end, rules):
    """{user_id: {'points': Decimal, 'leads': set}} for payments in the window."""
    payments = ledger(start, end)
    deals = counting_deals(p.lead_id for p in payments)
    out_of_game = taken_out()
    tally = defaultdict(lambda: {'points': ZERO, 'leads': set()})
    for p in payments:
        lead = deals.get(p.lead_id)
        if lead is None or p.key in out_of_game:
            continue
        for user_id, points in shares(lead, p.amount, rules.bde_share):
            if points > 0:
                tally[user_id]['points'] += points
                tally[user_id]['leads'].add(lead.id)
    return tally


def statement(user, start, end, rules):
    """The payments behind someone's points in a window, newest first.

    What each payment was, how it was shared and whether it counts, so that
    any figure on the board can be traced to the money behind it — and a
    payment that should not be there can be found and taken out. Payments that
    do not count are listed too, with the reason, so nothing is missing
    without an explanation.
    """
    from leads.models import BalancePayment, Lead

    def money(value):
        return str((value or ZERO).quantize(CENT))

    payments = ledger(start, end)
    leads = {lead.id: lead for lead in
             Lead.objects.filter(id__in={p.lead_id for p in payments})
             .select_related('bde', 'tele_caller', 'site_visit', 'payment_verification__completed_by')}
    recorded = {bp.id: bp for bp in BalancePayment.objects
                .filter(id__in=[p.ref for p in payments if p.kind == 'balance'])
                .select_related('recorded_by')}
    out_of_game = taken_out()

    lines = []
    for p in payments:
        lead = leads.get(p.lead_id)
        if lead is None:
            continue
        points = next((share for uid, share in shares(lead, p.amount, rules.bde_share)
                       if uid == user.id), ZERO)
        if points <= 0:
            continue
        as_bde = lead.bde_id == user.id
        shared = bool(lead.bde_id and lead.tele_caller_id and lead.bde_id != lead.tele_caller_id)
        partner = (lead.tele_caller if as_bde else lead.bde) if shared else None
        percent = (rules.bde_share if as_bde else rules.telecaller_share) if shared else Decimal('100')

        if p.kind == 'first':
            pv = getattr(lead, 'payment_verification', None)
            by = pv.completed_by if pv else None
            site_visit = getattr(lead, 'site_visit', None)
            po_signed = site_visit.po_signed_date if site_visit else None
        else:
            bp = recorded.get(p.ref)
            by, po_signed = (bp.recorded_by if bp else None), None

        exclusion = None
        if lead.is_trashed:
            status, reason = 'deleted', 'The lead was deleted.'
        elif lead.is_lost:
            status, reason = 'lost', 'The deal was marked lost.'
        elif p.key in out_of_game:
            exclusion = out_of_game[p.key]
            status, reason = 'excluded', exclusion.reason
        else:
            status, reason = 'counted', ''

        lines.append({
            'key': p.key, 'kind': p.kind, 'on': p.on.isoformat(),
            # Only when it differs: the payment was verified again on this day.
            'booked': p.booked.isoformat() if p.booked and p.booked != p.on else None,
            'receipt': p.receipt,
            'receipt_amount': money(p.receipt_amount) if p.receipt_amount is not None else None,
            'lead': lead.id, 'customer': _customer(lead), 'deal_value': money(lead.value),
            'amount': money(p.amount), 'share': money(percent),
            'as': 'bde' if as_bde else 'tele_caller',
            'partner': display_name(partner) if partner else None,
            'points': money(points),
            'by': display_name(by) if by else None,
            'po_signed': po_signed.isoformat() if po_signed else None,
            'status': status, 'reason': reason,
            'excluded_by': (display_name(exclusion.excluded_by)
                            if exclusion is not None and exclusion.excluded_by else None),
            'excluded_on': (_day(exclusion.excluded_at).isoformat()
                            if exclusion is not None else None),
        })
    lines.sort(key=lambda line: (line['on'], line['key']), reverse=True)
    return lines


# ─── Incentives ──────────────────────────────────────────────────────────────
def deal_project(lead):
    """The project the customer bought.

    Their latest order (an accepted quotation the money turned into one), else
    their latest accepted quotation, else their latest accepted proforma.
    Latest, not all: a customer who was quoted a 3 kW system and then a 5 kW
    one bought one of them.
    """
    from inventory.models import Quotation, Quote
    quotations = Quotation.objects.filter(lead=lead, project__isnull=False).select_related('project')
    picked = (quotations.filter(order_converted_at__isnull=False)
              .order_by('-order_converted_at', '-id').first()
              or quotations.filter(accepted_at__isnull=False, status__in=('accepted', 'converted'))
              .order_by('-accepted_at', '-id').first())
    if picked:
        return picked.project
    proforma = (Quote.objects.filter(lead=lead, project__isnull=False,
                                     status__in=('accepted', 'converted'))
                .select_related('project').order_by('-id').first())
    return proforma.project if proforma else None


def _customer(lead):
    return ' '.join(p for p in (lead.first_name, lead.last_name) if p) or f'Lead #{lead.id}'


def incentives_between(start, end):
    """{user_id: {'total': Decimal, 'deals': [...]}} for deals whose customer
    finished paying in the window.

    Earned on the payment that clears the balance: a deal paid in three
    instalments pays its incentives in the month of the third.
    """
    from leads.models import PaymentVerification
    touched = counting_deals(p.lead_id for p in ledger(start, end))
    if not touched:
        return {}
    verified = {pv.lead_id: pv for pv in PaymentVerification.objects
                .filter(lead_id__in=touched, is_complete=True).select_related('lead')}
    last_paid = {}
    for p in ledger(lead_ids=list(touched)):
        last_paid[p.lead_id] = max(last_paid.get(p.lead_id, p.on), p.on)

    out = defaultdict(lambda: {'total': ZERO, 'deals': []})
    for lead_id, lead in touched.items():
        pv = verified.get(lead_id)
        if pv is None or pv.balance_amount > 0:
            continue
        cleared = last_paid.get(lead_id)
        if cleared is None or not (start <= cleared <= end):
            continue
        project = deal_project(lead)
        if project is None:
            continue
        earners = [(lead.bde_id, project.bde_incentive, 'bde')]
        if lead.tele_caller_id and lead.tele_caller_id != lead.bde_id:
            earners.append((lead.tele_caller_id, project.telecaller_incentive, 'tele_caller'))
        for user_id, amount, as_role in earners:
            if user_id and amount and amount > 0:
                out[user_id]['total'] += amount
                out[user_id]['deals'].append({
                    'lead': lead_id, 'customer': _customer(lead), 'project': project.name,
                    'amount': str(amount), 'as': as_role, 'paid_on': cleared.isoformat(),
                })
    return out


# ─── The ladder ──────────────────────────────────────────────────────────────
def ladder():
    return list(RewardTier.objects.all())


def tier_dict(tier, role):
    if tier is None:
        return None
    return {'id': tier.id, 'name': tier.name, 'reward': tier.reward_label,
            'reward_type': tier.reward_type, 'target': str(tier.target_for(role))}


def climb(points, role, rungs):
    """Where some points stand on the ladder, for someone in `role`."""
    reached = [t for t in rungs if points >= t.target_for(role)]
    upcoming = next((t for t in rungs if points < t.target_for(role)), None)
    current = reached[-1] if reached else None
    out = {
        'reached': len(reached),
        'of': len(rungs),
        'current': tier_dict(current, role),
        'next': tier_dict(upcoming, role),
        'rewards': [t.reward_label for t in reached if t.reward_label],
        'needed': None,
        'progress': 1.0 if rungs and upcoming is None else 0.0,
    }
    if upcoming is not None:
        target = upcoming.target_for(role)
        out['needed'] = str(max(target - points, ZERO))
        out['progress'] = float(min(points / target, Decimal('1'))) if target > 0 else 1.0
    return out


# ─── Who plays ───────────────────────────────────────────────────────────────
def participants():
    User = get_user_model()
    return list(User.objects.filter(is_active=True, role__in=PARTICIPANT_ROLES)
                .order_by('first_name', 'last_name', 'username'))


def display_name(user):
    return f'{user.first_name} {user.last_name}'.strip() or user.username


def standings(start, end, rules, rungs):
    """The table for a window, best first: everyone who plays, points or not."""
    tally = points_between(start, end, rules)
    earned = incentives_between(start, end)
    rows = []
    for user in participants():
        mine = tally.get(user.id)
        points = mine['points'] if mine else ZERO
        paid = earned.get(user.id) or {'total': ZERO, 'deals': []}
        rows.append({
            'user': user.id, 'name': display_name(user), 'role': user.role,
            'points': points, 'deals': len(mine['leads']) if mine else 0,
            'tier': climb(points, user.role, rungs),
            'incentives': paid['total'], 'incentive_deals': paid['deals'],
        })
    # More points first; level on points, more deals; then by name so the
    # order does not shuffle between two loads of the same page.
    rows.sort(key=lambda r: (-r['points'], -r['deals'], r['name'].lower()))
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank
    return rows


# ─── Closing months and contests ─────────────────────────────────────────────
def close_due(today=None):
    """Decide every month that has ended since the game began, then the
    contest if it is over. Cheap and safe to call on every request: each month
    and each contest is decided exactly once.
    """
    today = today or timezone.localdate()
    rules = RewardSettings.load()
    closed = set(RewardMonth.objects.values_list('year', 'month'))
    month, current = rules.program_start.replace(day=1), today.replace(day=1)
    while month < current:
        if (month.year, month.month) not in closed:
            close_month(month)
        month = next_month(month)
    close_contest_if_over(today)


def _lock_rules():
    RewardSettings.load()
    return RewardSettings.objects.select_for_update().get(pk=1)


def close_month(first):
    """Freeze a finished month and announce its top three. None if it was
    already closed — two requests arriving together decide it once."""
    with transaction.atomic():
        rules = _lock_rules()
        if RewardMonth.objects.filter(year=first.year, month=first.month).exists():
            return None
        start, end = month_bounds(first)
        rows = standings(start, end, rules, ladder())
        record = RewardMonth.objects.create(year=first.year, month=first.month)
        podium = []
        for row in rows:
            medal, prize, coins = '', '', 0
            # A medal needs points: an empty month crowns nobody.
            if row['rank'] <= 3 and row['points'] > 0:
                medal = MEDALS[row['rank'] - 1]
                prize, coins = rules.prize_for(row['rank']), rules.coins_for(row['rank'])
                podium.append({**row, 'medal': medal, 'prize': prize, 'coins': coins})
            RewardStanding.objects.create(
                reward_month=record, user_id=row['user'], name=row['name'], role=row['role'],
                rank=row['rank'], points=row['points'], deals=row['deals'],
                tier_name=(row['tier']['current'] or {}).get('name', ''),
                tiers_reached=row['tier']['reached'], rewards=row['tier']['rewards'],
                incentives=row['incentives'], medal=medal, prize=prize, coins=coins)
        if podium:
            _announce_month(first, podium)
        return record


def _audience():
    User = get_user_model()
    return User.objects.filter(is_active=True).filter(Q(role__in=PARTICIPANT_ROLES) | Q(is_staff=True))


def _notify(users, title, message, extra):
    from ai_manager.models import Notification
    Notification.objects.bulk_create([
        Notification(user=u, title=title, message=message, notification_type='achievement',
                     extra_data=extra) for u in users])


def _announce_month(first, podium):
    label = first.strftime('%B %Y')
    extra = {'rewards_month': first.strftime('%Y-%m')}
    names = ' · '.join(f"{p['medal'].title()}: {p['name']}" for p in podium)
    _notify(_audience(), f'🏆 {label} champions',
            f'{names}. A new month has started — every tier is open again.', extra)
    User = get_user_model()
    for p in podium:
        winner = User.objects.filter(pk=p['user']).first()
        if winner is None:
            continue
        won = [f"{p['coins']} coins"] if p['coins'] else []
        if p['prize']:
            won.insert(0, p['prize'])
        _notify([winner], f"🥇 You won {p['medal']} for {label}!" if p['medal'] == 'gold'
                else f"🏅 You won {p['medal']} for {label}!",
                'Congratulations! ' + (' and '.join(won) + ' are yours.' if won else ''), extra)


def coins_between(start, end):
    """{user_id: coins} won in months that fall within a contest."""
    months = [m for m in RewardMonth.objects.all()
              if start.replace(day=1) <= date(m.year, m.month, 1) <= end]
    totals = defaultdict(int)
    for user_id, coins in (RewardStanding.objects.filter(reward_month__in=months, coins__gt=0)
                           .values_list('user_id', 'coins')):
        if user_id:
            totals[user_id] += coins
    return totals


def contest_table(rules, today):
    """The contest so far: everyone who plays, ranked by points, with coins."""
    start, end = rules.contest_start, rules.contest_end
    upto = min(end, today)
    tally = points_between(start, upto, rules) if upto >= start else {}
    coins = coins_between(start, end)
    rows = []
    for user in participants():
        mine = tally.get(user.id)
        rows.append({'user': user.id, 'name': display_name(user), 'role': user.role,
                     'points': mine['points'] if mine else ZERO,
                     'deals': len(mine['leads']) if mine else 0,
                     'coins': coins.get(user.id, 0)})
    rows.sort(key=lambda r: (-r['points'], -r['deals'], r['name'].lower()))
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank
    return rows


def coin_leader(rows):
    holders = [r for r in rows if r['coins'] > 0]
    if not holders:
        return None
    return sorted(holders, key=lambda r: (-r['coins'], -r['points'], r['name'].lower()))[0]


def close_contest_if_over(today):
    """Award the contest once it is over and its last month has closed — the
    coins that month hands out count towards the coin champion."""
    rules = RewardSettings.load()
    if not (rules.contest_start and rules.contest_end):
        return None
    if today.replace(day=1) <= rules.contest_end.replace(day=1):
        return None
    if ContestResult.objects.filter(start=rules.contest_start, end=rules.contest_end).exists():
        return None
    with transaction.atomic():
        rules = _lock_rules()
        if ContestResult.objects.filter(start=rules.contest_start, end=rules.contest_end).exists():
            return None
        rows = contest_table(rules, today)
        winners = [{'rank': r['rank'], 'user': r['user'], 'name': r['name'],
                    'points': str(r['points']), 'prize': rules.bumper_for(r['rank'])}
                   for r in rows[:3] if r['points'] > 0]
        leader = coin_leader(rows)
        champion = ({'user': leader['user'], 'name': leader['name'], 'coins': leader['coins'],
                     'prize': rules.coin_champion_prize} if leader else {})
        result = ContestResult.objects.create(
            name=rules.contest_name, start=rules.contest_start, end=rules.contest_end,
            winners=winners, coin_champion=champion,
            standings=[{'rank': r['rank'], 'user': r['user'], 'name': r['name'], 'role': r['role'],
                        'points': str(r['points']), 'coins': r['coins']} for r in rows[:20]])
        if winners or champion:
            title = f"🏆 {rules.contest_name or 'The contest'} — the winners"
            parts = [f"#{w['rank']} {w['name']}" for w in winners]
            if champion:
                parts.append(f"coin champion {champion['name']}")
            _notify(_audience(), title, ' · '.join(parts) + '. Congratulations!',
                    {'rewards_contest': result.id})
        return result
