"""Projections, comparisons, growth pace and suggestions for Company Performance.

Four things sit on top of the raw figures: where the period is heading, how it
compares with the one before, how fast the business is moving, and what is worth
doing about it.

All of it is computed here from the CRM's own numbers. The language model, when
one is configured, is handed those findings and asked to prioritise and phrase
them — it is never asked what the numbers are. A performance board that quietly
invented a revenue figure would be worse than useless, and a reader cannot tell
an invented number from a real one once it is on the screen. So: arithmetic from
the database, wording from the model, and the board says which is which.
"""
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .scopes import live_leads, net_value

logger = logging.getLogger(__name__)


def _money(value):
    return str(Decimal(value or 0).quantize(Decimal('0.01')))


def _days_in(start, end):
    return max((end - start).days + 1, 1)


# ─── Projection ─────────────────────────────────────────────────────────────
def period_end_for(period_key, start, end):
    """The date this period actually runs to, which is not where the data stops.

    `resolve_period` caps its end at today so no figure counts tomorrow's
    business — right for filtering, wrong for a forecast. A financial year still
    ends on 31 March whether or not it is March yet, and projecting to today
    would report every period as already complete.
    """
    if period_key == 'this_month':
        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return nxt - timedelta(days=1)
    if period_key == 'this_year':
        return date(start.year, 12, 31)
    if period_key == 'this_fy':
        return date(start.year + 1, 3, 31)
    return end                       # a custom range ends where the user said


def build_projections(*, start, end, period_key, revenue, closed, leads, close_rate,
                      avg_deal):
    """Where this period lands if the rest of it looks like the part already run.

    A straight run rate: what has come in, divided by the days gone, times the
    days in the period. Deliberately simple, because a forecast nobody can check
    by hand is a forecast nobody will trust — and the board states its assumption
    rather than presenting the figure as a fact.
    """
    today = timezone.localdate()
    if period_key == 'all' or not start or not end:
        return None

    finishes = period_end_for(period_key, start, end)
    total_days = _days_in(start, finishes)
    elapsed = max(min((today - start).days + 1, total_days), 1)
    remaining = max(total_days - elapsed, 0)
    complete = remaining == 0

    revenue = Decimal(revenue or 0)
    per_day = revenue / elapsed if elapsed else Decimal('0')
    projected = per_day * total_days

    # Still in play: defined by what it is not, so a status added later counts
    # as open rather than quietly dropping out of the pipeline figure.
    #
    # Valued at what it would be billed, not at revenue: nothing has been paid
    # on an open lead, so `received_value` would report the whole pipeline as
    # worth nothing.
    open_leads = live_leads().filter(is_lost=False).exclude(
        status__in=['converted', 'not_interested'],
    ).aggregate(n=Count('id'), value=Coalesce(Sum(net_value()), Decimal('0')))

    # What the open book is worth once the close rate is applied. The historical
    # rate is the only honest multiplier available — a weighting, not a promise
    # about any particular deal.
    weighted = (Decimal(open_leads['value'] or 0) * Decimal(str(close_rate))) / Decimal('100')

    return {
        'basis': 'run_rate',
        'complete': complete,
        'period_ends': finishes.isoformat(),
        'days_elapsed': elapsed,
        'days_total': total_days,
        'days_remaining': remaining,
        'revenue_so_far': _money(revenue),
        'revenue_per_day': _money(per_day),
        'projected_revenue': _money(projected),
        'projected_closed_deals': int(round((closed / elapsed) * total_days)) if elapsed else 0,
        'projected_leads': int(round((leads / elapsed) * total_days)) if elapsed else 0,
        'open_leads': open_leads['n'],
        'open_pipeline_value': _money(open_leads['value']),
        'pipeline_weighted_value': _money(weighted),
        'avg_deal_value': _money(avg_deal),
        'assumption': (
            f'The remaining {remaining} day(s) go the way the first {elapsed} did.'
            if not complete else 'The period is complete; this is what it did.'),
    }


# ─── Comparison with the period before ──────────────────────────────────────
def _shift_year(day, years):
    """The same date some years back, tolerating 29 February."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def previous_window(period_key, start, end):
    """The stretch this one should be judged against.

    Like for like, which for a period still running means the *same part* of the
    one before: thirteen days into August is compared with the first thirteen
    days of July, not with the whole of July. Comparing a fortnight against a
    full month would show a collapse in business every month.
    """
    if not start or not end or period_key == 'all':
        return None

    span = (end - start).days                       # days after the first

    if period_key == 'this_month':
        prev_month_end = start - timedelta(days=1)       # last day of last month
        prev_start = prev_month_end.replace(day=1)
        return prev_start, min(prev_start + timedelta(days=span), prev_month_end)

    if period_key in ('this_year', 'this_fy'):
        return _shift_year(start, 1), _shift_year(end, 1)

    # A custom range is compared with the stretch of equal length before it.
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=span), prev_end


def _change(now, before):
    """The move from one figure to the next, as a number and as a share.

    `change_pct` is None when there is nothing to divide by: going from zero to
    anything is not a percentage rise, it is a start, and printing "+100%" there
    would be inventing a rate nobody can act on.
    """
    now, before = Decimal(now or 0), Decimal(before or 0)
    delta = now - before
    pct = round(float(delta / before * 100), 1) if before > 0 else None
    return {
        'now': str(now), 'before': str(before), 'change': str(delta),
        'change_pct': pct,
        'direction': 'up' if delta > 0 else ('down' if delta < 0 else 'flat'),
        'from_nothing': before == 0 and now > 0,
    }


COMPARED_METRICS = (
    ('revenue', 'Revenue', True),
    ('closed_deals', 'Closed deals', False),
    ('leads', 'Leads', False),
    ('converted', 'Converted', False),
    ('billed', 'Billed', True),
    ('lost', 'Lost', False),
)


def build_comparison(current, previous, window):
    """This period against the last, metric by metric."""
    if previous is None or window is None:
        return None
    return {
        'from': window[0].isoformat(),
        'to': window[1].isoformat(),
        'label': f"{window[0].strftime('%d %b %Y')} – {window[1].strftime('%d %b %Y')}",
        'metrics': [{
            'key': key, 'label': label, 'is_money': money,
            **_change(current.get(key), previous.get(key)),
        } for key, label, money in COMPARED_METRICS],
    }


# ─── Growth pace ────────────────────────────────────────────────────────────
def build_growth(monthly):
    """How fast the business is moving, month on month.

    The pace is the average of the month-on-month changes, which says something
    a total cannot: two years flat and two years doubling look identical in a
    sum. Months with nothing before them to grow from are left out of the
    average rather than counted as a leap from zero.
    """
    series = list(monthly or [])
    if len(series) < 2:
        return None

    points, rates = [], []
    for i, row in enumerate(series):
        revenue = Decimal(row.get('revenue') or 0)
        pct = None
        if i > 0:
            before = Decimal(series[i - 1].get('revenue') or 0)
            if before > 0:
                pct = round(float((revenue - before) / before * 100), 1)
                rates.append(pct)
        points.append({'name': row.get('name'), 'revenue': str(revenue),
                       'growth_pct': pct, 'closed': row.get('closed', 0)})

    earning = [p for p in points if Decimal(p['revenue']) > 0]
    best = max(earning, key=lambda p: Decimal(p['revenue'])) if earning else None
    worst = min(earning, key=lambda p: Decimal(p['revenue'])) if earning else None

    # Recent against the stretch before it: the direction of travel, which one
    # good month can hide and one bad month can fake.
    half = max(len(series) // 2, 1)
    early = sum((Decimal(r.get('revenue') or 0) for r in series[:half]), Decimal('0'))
    late = sum((Decimal(r.get('revenue') or 0) for r in series[half:]), Decimal('0'))
    swing = round(float((late - early) / early * 100), 1) if early > 0 else None

    return {
        'points': points,
        'average_pace': round(sum(rates) / len(rates), 1) if rates else None,
        'months_measured': len(rates),
        'best_month': best,
        'worst_month': worst,
        'recent_vs_earlier_pct': swing,
        'trend': (('up' if swing > 5 else 'down' if swing < -5 else 'steady')
                  if swing is not None else None),
    }


# ─── Findings ───────────────────────────────────────────────────────────────
def build_findings(payload):
    """What the figures say, in plain observations.

    Each finding is a fact with a number attached, so a reader can check it
    against the tables on the same page. Nothing here is a guess.
    """
    head = payload.get('headline') or {}
    findings = []

    def add(kind, text, weight):
        findings.append({'kind': kind, 'text': text, 'weight': weight})

    leads = head.get('leads') or 0
    closed = head.get('closed_deals') or 0
    converted = head.get('converted') or 0
    revenue = Decimal(head.get('revenue') or 0)
    outstanding = Decimal(head.get('outstanding') or 0)

    if outstanding > 0 and revenue > 0:
        share = (outstanding / revenue) * 100
        if share >= 20:
            add('risk', f'{_money(outstanding)} of {_money(revenue)} won '
                        f'({share:.0f}%) has still not been collected.', 90)

    if leads >= 10 and converted and closed < converted:
        add('risk', f'{converted - closed} converted deal(s) have no money against them '
                    f'yet — won by the sales team but not by accounts.', 80)
    if leads >= 20 and head.get('close_rate', 0) < 10:
        add('risk', f'Only {head.get("close_rate")}% of leads closed.', 70)

    # ── Direction of travel ──
    comparison = payload.get('comparison') or {}
    for metric in comparison.get('metrics', []):
        if metric['key'] == 'revenue' and metric['change_pct'] is not None:
            if metric['change_pct'] <= -20:
                add('risk', f'Revenue is {abs(metric["change_pct"])}% below the same '
                            f'stretch last period.', 85)
            elif metric['change_pct'] >= 20:
                add('opportunity', f'Revenue is {metric["change_pct"]}% up on the same '
                                   f'stretch last period.', 60)
    growth = payload.get('growth') or {}
    if growth.get('trend') == 'down' and growth.get('recent_vs_earlier_pct') is not None:
        add('risk', f'Recent months are {abs(growth["recent_vs_earlier_pct"])}% below '
                    f'the earlier ones.', 75)

    lost = payload.get('lost') or {}
    reasons = lost.get('reasons') or []
    if reasons and (lost.get('count') or 0) >= 3:
        top = reasons[0]
        add('opportunity', f'The commonest reason for losing is "{top["name"]}" '
                           f'({top["count"]} deal(s)).', 75)
    stages = lost.get('by_stage') or []
    if stages and (lost.get('count') or 0) >= 3:
        add('opportunity', f'Most losses happen at {stages[0]["label"]} '
                           f'({stages[0]["count"]} deal(s)).', 65)

    delivery = payload.get('delivery') or {}
    if (delivery.get('won') or 0) >= 3 and (delivery.get('not_started') or 0):
        add('risk', f'{delivery["not_started"]} won deal(s) have no project started.', 70)

    for group, noun in (('branches', 'branch'), ('teams', 'team')):
        block = payload.get(group) or {}
        if block.get('best') and block.get('worst'):
            best, worst = block['best'], block['worst']
            if Decimal(worst['revenue']) > 0:
                ratio = Decimal(best['revenue']) / Decimal(worst['revenue'])
                if ratio >= 3:
                    add('spread', f'{best["name"]} brought in {ratio:.1f}x what '
                                  f'{worst["name"]} did.', 60)
        if block.get('without_revenue'):
            add('spread', f'{len(block["without_revenue"])} {noun}(s) brought in nothing: '
                          f'{", ".join(block["without_revenue"][:4])}.', 55)

    people = (payload.get('employees') or {}).get('rows') or []
    if len(people) >= 3:
        earners = [p for p in people if Decimal(p['revenue']) > 0]
        if earners and len(earners) < len(people):
            add('spread', f'{len(earners)} of {len(people)} people closed anything.', 60)
        if len(earners) >= 2:
            top_share = Decimal(earners[0]['revenue']) / max(revenue, Decimal('1')) * 100
            if top_share >= 50:
                add('risk', f'{earners[0]["name"]} alone accounts for '
                            f'{top_share:.0f}% of revenue.', 65)

    pipeline = payload.get('pipeline') or []
    if pipeline and leads and pipeline[0]['count'] / max(leads, 1) >= 0.4:
        add('opportunity', f'{pipeline[0]["count"]} leads are sitting at '
                           f'{pipeline[0]["label"]}.', 50)

    findings.sort(key=lambda f: -f['weight'])
    return findings[:8]


# ─── Suggestions ────────────────────────────────────────────────────────────
AI_SYSTEM = (
    "You advise the management of a solar installation company in Kerala, India, on "
    "sales performance. You will be given verified figures from their CRM and a list "
    "of findings already computed from those figures.\n\n"
    "Rules you must follow:\n"
    "- Never state a number that is not in the data given to you. Do not estimate, "
    "extrapolate or round differently.\n"
    "- Give at most 4 suggestions, each one action someone could start this week.\n"
    "- Each suggestion: one sentence of what to do, then one short sentence of why, "
    "citing the figure it rests on.\n"
    "- Be direct. No preamble, no encouragement, no restating the question.\n"
    "- If the data is too thin to advise on, say exactly that instead of inventing "
    "advice.\n"
    "- Reply as a numbered list, nothing else."
)


def ai_suggestions(payload, findings, projections):
    """Advice from the model, or None when there is none to be had.

    Returns None rather than a placeholder if no key is configured or the call
    fails: the board shows the computed findings on their own, which is a
    smaller loss than a suggestion nobody can trace back to the data.
    """
    if not getattr(settings, 'GEMINI_API_KEY', '') or not findings:
        return None

    head = payload.get('headline') or {}
    lines = [
        f"Period: {payload.get('period_label')}",
        f"Leads: {head.get('leads')}, converted: {head.get('converted')}, "
        f"closed deals: {head.get('closed_deals')}, lost: {head.get('lost')}",
        f"Revenue (net of discount): {head.get('revenue')}, "
        f"collected: {head.get('collected')}, outstanding: {head.get('outstanding')}",
        f"Close rate: {head.get('close_rate')}%, "
        f"average deal: {head.get('avg_deal_value')}, "
        f"average days to close: {head.get('avg_days_to_close')}",
    ]
    comparison = payload.get('comparison')
    if comparison:
        lines.append(f"Against {comparison['label']}: " + ', '.join(
            f"{m['label']} {m['now']} vs {m['before']}"
            + (f" ({m['change_pct']:+}%)" if m['change_pct'] is not None else '')
            for m in comparison['metrics']))
    growth = payload.get('growth')
    if growth and growth.get('average_pace') is not None:
        lines.append(f"Average month-on-month growth: {growth['average_pace']}% "
                     f"over {growth['months_measured']} month(s).")
    if projections:
        lines.append(
            f"Run-rate projection for the period: {projections['projected_revenue']} "
            f"({projections['days_remaining']} of {projections['days_total']} days left). "
            f"Open pipeline: {projections['open_leads']} leads worth "
            f"{projections['open_pipeline_value']}.")
    lines.append("Findings:")
    lines += [f"- {f['text']}" for f in findings]

    try:
        from ai_manager.ai_meeting import _call_gemini
        text = _call_gemini('\n'.join(lines), AI_SYSTEM)
        return (text or '').strip() or None
    except Exception as exc:                      # the board is not worth a 500
        logger.warning('Company performance AI suggestions unavailable: %s', exc)
        return None
