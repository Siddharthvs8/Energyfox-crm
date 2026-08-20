"""Company Performance — the whole business in one report.

Every figure here is drawn from the same definitions the rest of the CRM uses,
because a performance board that disagrees with the screens it summarises is
worse than no board at all:

  * won            — `leads.scopes.closed_deals`: a deal is won when the money
    has landed, in accounts with a payment part or full received.
  * revenue        — `leads.scopes.received_value`: money in, not money
    promised. What was invoiced is `net_value`, reported separately as billed,
    and the gap between the two is what is still outstanding.
  * a lead's people — `own_leads_q`: handing a lead to a BDE moves nothing, so
    credit reaches the owner, the BDE and the tele caller alike.
  * deleted leads   — `live_leads`: a lead in the Trash is out of every figure.

The board answers one question per section: how much came in, who brought it,
and where the work is sitting now.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, DurationField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import can_access_company_performance
from .performance_insights import (ai_suggestions, build_comparison, build_findings,
                                   build_growth, build_projections, previous_window)
from .models import Lead, PaymentVerification
from .scopes import (CLOSED_DEAL_FILTER, closed_deal_q, closed_deals, live_leads,
                     net_value, received_value)

_MONEY = DecimalField(max_digits=16, decimal_places=2)
_ZERO = Value(Decimal('0'))


def _to_date(value):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def resolve_period(request, default='this_fy'):
    """The window a screen covers: (start, end, key, label).

    `start` of None means all time. The performance board defaults to this
    financial year, because a company's performance is read against the year it
    is being judged on rather than the calendar month; a working list of deals
    passes `default='all'` instead, so nothing a user already relies on seeing
    disappears behind a filter they did not set.

    Shared so "This FY" means the same date range wherever it is offered.
    """
    today = timezone.localdate()
    key = (request.query_params.get('period') or default).strip().lower()

    if key == 'all':
        return None, None, 'all', 'All time'
    if key == 'this_month':
        return today.replace(day=1), today, 'this_month', f'This month ({today.strftime("%B %Y")})'
    if key == 'this_year':
        return today.replace(month=1, day=1), today, 'this_year', f'This year ({today.year})'
    if key == 'custom':
        start, end = _to_date(request.query_params.get('from')), _to_date(request.query_params.get('to'))
        end = end or today
        if start and end < start:
            start, end = end, start
        if not start:
            return None, end, 'custom', f'Up to {end.strftime("%d %b %Y")}'
        return start, end, 'custom', (f'{start.strftime("%d %b %Y")} – {end.strftime("%d %b %Y")}')

    # The Indian financial year the CRM already numbers its documents by.
    fy_start = today.replace(month=4, day=1) if today.month >= 4 else date(today.year - 1, 4, 1)
    return fy_start, today, 'this_fy', f'FY {fy_start.year % 100:02d}-{(fy_start.year + 1) % 100:02d}'


def _money(value):
    return str(Decimal(value or 0).quantize(Decimal('0.01')))


def _rate(part, whole):
    return round(part * 100.0 / whole, 1) if whole else 0.0


class CompanyPerformanceView(APIView):
    """One report over the whole company, for the people who answer for it.

    The top of the house only — super admin, admin, COO and the read-only
    spectator (`can_access_company_performance`). A manager runs a function or a
    branch and has the Manager module reporting their own people to them; this
    is the view above that.
    """
    permission_classes = [permissions.IsAuthenticated]
    # More than a dozen rows of either is a table, not a ranking.
    TOP_N = 10

    def get(self, request):
        if not can_access_company_performance(request.user):
            return Response({'error': 'Company performance is for super admins, admins and the COO.'},
                            status=status.HTTP_403_FORBIDDEN)

        start, end, period_key, period_label = resolve_period(request)
        today = timezone.localdate()

        def within(qs, field='created_at'):
            """Leads that arrived in the window."""
            if start:
                qs = qs.filter(**{f'{field}__date__gte': start})
            if end:
                qs = qs.filter(**{f'{field}__date__lte': end})
            return qs

        # Two different questions, two different windows. Leads are counted by
        # when they arrived; money by when the deal was won — a lead from last
        # year that closes this month is this month's revenue.
        leads_qs = within(live_leads())
        won_qs = within(closed_deals(live_leads()), 'status_changed_at')
        everyone, bdes, tele_callers = self._employees(start, end)

        payload = {
            'period': period_key,
            'period_label': period_label,
            'period_from': start.isoformat() if start else None,
            'period_to': end.isoformat() if end else None,
            'generated_at': timezone.now().isoformat(),
            'headline': self._headline(leads_qs, won_qs),
            'funnel': self._funnel(leads_qs, won_qs),
            'pipeline': self._pipeline(),
            'monthly': self._monthly(start, end, today),
            'sources': self._by(leads_qs, won_qs, 'source'),
            'districts': self._by(leads_qs, won_qs, 'district', blank_label='No district'),
            'branches': self._branches(start, end),
            'teams': self._teams(start, end),
            'lost': self._lost(start, end),
            'collection': self._collection(won_qs),
            'delivery': self._delivery(won_qs),
            'segments': self._segments(won_qs),
            'employees': everyone,
            'bdes': bdes,
            'tele_callers': tele_callers,
        }

        # Everything below reads the finished figures rather than the querysets,
        # so it cannot disagree with what the board shows.
        head = payload['headline']
        window = previous_window(period_key, start, end)
        payload['comparison'] = build_comparison(head, self._window_figures(window), window)
        # The trailing year, whatever period is selected: growth pace is a fact
        # about the business, and picking "This month" should not make it
        # vanish because one month has nothing before it to grow from.
        payload['growth'] = build_growth(self._monthly(None, today, today))
        payload['projections'] = build_projections(
            start=start, end=end, period_key=period_key,
            revenue=Decimal(head['revenue']), closed=head['closed_deals'],
            leads=head['leads'], close_rate=head['close_rate'],
            avg_deal=Decimal(head['avg_deal_value']))
        payload['findings'] = build_findings(payload)
        payload['ai_suggestions'] = ai_suggestions(
            payload, payload['findings'], payload['projections'])
        return Response(payload)

    def _window_figures(self, window):
        """The same headline figures over any stretch, for comparing against.

        Built from `_headline` rather than its own arithmetic: a comparison that
        counted revenue differently from the tile above it would be worse than
        no comparison at all.
        """
        if window is None:
            return None
        start, end = window
        leads_qs = live_leads().filter(created_at__date__gte=start, created_at__date__lte=end)
        won_qs = closed_deals(live_leads()).filter(
            status_changed_at__date__gte=start, status_changed_at__date__lte=end)
        return self._headline(leads_qs, won_qs)

    # ── Headline ──
    def _headline(self, leads_qs, won_qs):
        leads = leads_qs.count()
        converted = leads_qs.filter(status='converted', is_lost=False).count()
        money = won_qs.aggregate(
            # Revenue is money in. What was charged is `billed`, and it is what
            # the outstanding figure is measured against — without it, "still
            # owed" would have nothing to subtract from and would read zero on
            # a book full of debts.
            revenue=Coalesce(Sum(received_value()), _ZERO, output_field=_MONEY),
            billed=Coalesce(Sum(net_value()), _ZERO, output_field=_MONEY),
            discounts=Coalesce(Sum('payment_verification__discount_value'), _ZERO, output_field=_MONEY),
        )
        closed = won_qs.count()
        revenue = money['revenue']
        # The gap, floored at zero: an overpayment is an accounts matter, not a
        # negative debt on a performance board.
        outstanding = max(money['billed'] - revenue, Decimal('0'))

        pace = won_qs.filter(status_changed_at__isnull=False).annotate(
            took=ExpressionWrapper(F('status_changed_at') - F('created_at'),
                                   output_field=DurationField())
        ).aggregate(avg=Avg('took'))['avg']

        return {
            'leads': leads,
            'converted': converted,
            'closed_deals': closed,
            'lost': leads_qs.filter(is_lost=True).count(),
            'conversion_rate': _rate(converted, leads),
            'close_rate': _rate(closed, leads),
            'revenue': _money(revenue),
            # Kept under its old name so nothing reading `collected` breaks; it
            # is the same figure as revenue now, and the tile that showed it was
            # dropped rather than printing one number twice.
            'collected': _money(revenue),
            'billed': _money(money['billed']),
            'outstanding': _money(outstanding),
            'discounts': _money(money['discounts']),
            # Of what came in, not of what was invoiced — the same money the
            # revenue tile above reports.
            'avg_deal_value': _money(revenue / closed) if closed else '0.00',
            'avg_days_to_close': round(pace.total_seconds() / 86400, 1) if pace else 0.0,
            'completed_projects': Lead.objects.filter(project__is_complete=True).count(),
        }

    # ── Where the business falls away ──
    def _funnel(self, leads_qs, won_qs):
        """Leads in, deals out — each step a subset of the one before it, so the
        drop between them is the thing worth looking at."""
        leads = leads_qs.count()
        converted = leads_qs.filter(status='converted', is_lost=False).count()
        closed = won_qs.count()
        completed = won_qs.filter(project__is_complete=True).count()
        steps = [('Leads', leads), ('Converted', converted),
                 ('Closed deals', closed), ('Projects completed', completed)]
        return [{'stage': name, 'count': n, 'of_leads': _rate(n, leads)} for name, n in steps]

    # ── Where the work is sitting right now ──
    def _pipeline(self):
        """Not period-scoped: this is the state of the book today, and a date
        range cannot change where a customer currently is."""
        counts = {}
        for lead in live_leads().only('id', 'bde', 'pushed_to_documentation',
                                      'pushed_to_accounts', 'pushed_to_purchase',
                                      'pushed_to_project', 'status'):
            stage = lead.pipeline_stage
            counts[stage] = counts.get(stage, 0) + 1
        return [{'stage': s, 'label': Lead.PIPELINE_STAGE_LABELS.get(s, s), 'count': n}
                for s, n in sorted(counts.items(), key=lambda kv: -kv[1])]

    # ── Month by month ──
    def _monthly(self, start, end, today):
        first = start or (live_leads().order_by('created_at')
                          .values_list('created_at', flat=True).first() or timezone.now()).date()
        cursor, last = first.replace(day=1), (end or today)
        out = []
        while cursor <= last:
            nxt = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            stop = min(nxt, last + timedelta(days=1))
            won = closed_deals(live_leads()).filter(status_changed_at__date__gte=cursor,
                                                    status_changed_at__date__lt=stop)
            out.append({
                'name': cursor.strftime('%b %y'),
                'leads': live_leads().filter(created_at__date__gte=cursor,
                                             created_at__date__lt=stop).count(),
                'closed': won.count(),
                'revenue': _money(won.aggregate(t=Coalesce(Sum(received_value()), _ZERO,
                                                           output_field=_MONEY))['t']),
            })
            cursor = nxt
        out = out[-12:]             # a year of bars is as much as reads
        # A running total over the months shown, so the pace of the year reads
        # off the same chart as the months themselves.
        running = Decimal('0')
        for row in out:
            running += Decimal(row['revenue'])
            row['cumulative'] = _money(running)
        return out

    # ── Cut by a column of the lead ──
    def _by(self, leads_qs, won_qs, field, blank_label=None):
        leads = dict(leads_qs.values_list(field).annotate(n=Count('id')).values_list(field, 'n'))
        won = {k: (n, rev) for k, n, rev in
               won_qs.values_list(field).annotate(
                   n=Count('id'), rev=Coalesce(Sum(received_value()), _ZERO, output_field=_MONEY)
               ).values_list(field, 'n', 'rev')}
        rows = []
        for key, count in leads.items():
            closed, revenue = won.get(key, (0, Decimal('0')))
            rows.append({
                'name': (key or blank_label or '—') if key != '' else (blank_label or '—'),
                'leads': count, 'closed_deals': closed,
                'revenue': _money(revenue), 'close_rate': _rate(closed, count),
            })
        rows.sort(key=lambda r: (-Decimal(r['revenue']), -r['leads'], r['name']))
        return rows

    # ── Why business is lost ──
    def _lost(self, start, end):
        """The deals that got away, and how far they got before they did.

        Dated by when they were lost, not when they arrived — a lead from last
        year written off this month is this month's loss. The stage is the
        furthest the lead reached, which is the useful part: losing at tele
        caller is a qualification problem, losing at accounts is a pricing or
        finance one.
        """
        qs = live_leads().filter(is_lost=True).annotate(
            lost_on=Coalesce('lost_at', 'status_changed_at', 'created_at'))
        if start:
            qs = qs.filter(lost_on__date__gte=start)
        if end:
            qs = qs.filter(lost_on__date__lte=end)

        reasons = [
            {'name': (r['lost_reason'] or '').strip() or 'No reason given',
             'count': r['n'], 'value': _money(r['v'])}
            for r in qs.values('lost_reason').annotate(
                n=Count('id'), v=Coalesce(Sum('value'), _ZERO, output_field=_MONEY))
        ]
        # Several blank-ish reasons collapse onto one label, so merge them.
        merged = {}
        for row in reasons:
            hit = merged.setdefault(row['name'], {'name': row['name'], 'count': 0, 'value': Decimal('0')})
            hit['count'] += row['count']
            hit['value'] += Decimal(row['value'])
        reasons = sorted(({'name': r['name'], 'count': r['count'], 'value': _money(r['value'])}
                          for r in merged.values()),
                         key=lambda r: (-r['count'], r['name']))

        stages = {}
        for lead in qs.only('id', 'value', 'bde', 'pushed_to_documentation', 'pushed_to_accounts',
                            'pushed_to_purchase', 'pushed_to_project'):
            hit = stages.setdefault(lead.pipeline_stage, {'count': 0, 'value': Decimal('0')})
            hit['count'] += 1
            hit['value'] += (lead.value or Decimal('0'))

        total = qs.aggregate(n=Count('id'), v=Coalesce(Sum('value'), _ZERO, output_field=_MONEY))
        return {
            'count': total['n'],
            'value': _money(total['v']),
            'reasons': reasons[:8],
            'by_stage': sorted(
                ({'stage': s, 'label': Lead.PIPELINE_STAGE_LABELS.get(s, s),
                  'count': v['count'], 'value': _money(v['value'])}
                 for s, v in stages.items()),
                key=lambda r: -r['count']),
        }

    # ── Whether the money actually comes in ──
    def _collection(self, won_qs):
        """Won is not the same as banked. This is the gap, and how it is paid.

        A deal is fully paid when what accounts received covers the value less
        the discount — the same net figure the revenue tile uses, so a discount
        does not leave a deal looking permanently short.
        """
        rows = won_qs.annotate(net=net_value()).values_list(
            'payment_verification__payment_mode', 'net',
            'payment_verification__amount_received')

        full = part = 0
        billed = banked = Decimal('0')
        modes = {}
        for mode, net, got in rows:
            net = net or Decimal('0')
            got = got or Decimal('0')
            billed += net
            banked += got
            if got >= net:
                full += 1
            else:
                part += 1
            key = mode or 'unrecorded'
            hit = modes.setdefault(key, {'count': 0, 'amount': Decimal('0')})
            hit['count'] += 1
            hit['amount'] += got

        labels = dict(PaymentVerification.PAYMENT_MODES)
        labels['unrecorded'] = 'Not recorded'
        return {
            'fully_paid': full,
            'partially_paid': part,
            'billed': _money(billed),
            'collected': _money(banked),
            'collection_rate': _rate(float(banked), float(billed)) if billed else 0.0,
            'by_mode': sorted(
                ({'mode': k, 'label': labels.get(k, k.title()),
                  'count': v['count'], 'amount': _money(v['amount'])}
                 for k, v in modes.items()),
                key=lambda r: -Decimal(r['amount'])),
        }

    # ── Whether the work gets delivered ──
    def _delivery(self, won_qs):
        """A won deal is a promise; this is how much of it has been kept.

        Only deals won in the window are counted, so the completion share is of
        this window's own business rather than of everything ever sold.
        """
        won = won_qs.count()
        done = won_qs.filter(project__is_complete=True).count()
        started = won_qs.filter(project__isnull=False, project__is_complete=False).count()

        pace = won_qs.filter(project__is_complete=True,
                             project__completed_at__isnull=False,
                             status_changed_at__isnull=False).annotate(
            took=ExpressionWrapper(F('project__completed_at') - F('status_changed_at'),
                                   output_field=DurationField())).aggregate(avg=Avg('took'))['avg']

        return {
            'won': won,
            'completed': done,
            'in_progress': started,
            'not_started': max(won - done - started, 0),
            'completion_rate': _rate(done, won),
            'avg_days_to_complete': round(pace.total_seconds() / 86400, 1) if pace else 0.0,
        }

    # ── What kind of work it is ──
    def _segments(self, won_qs):
        """Residential against commercial, and the roof it goes on — recorded at
        the site visit, so deals that never had one show as not recorded."""
        def group(field, blank):
            out = {}
            for key, net in won_qs.annotate(net=received_value()).values_list(field, 'net'):
                name = (str(key).strip().title() if key else '') or blank
                hit = out.setdefault(name, {'name': name, 'count': 0, 'revenue': Decimal('0')})
                hit['count'] += 1
                hit['revenue'] += (net or Decimal('0'))
            return sorted(({'name': r['name'], 'count': r['count'], 'revenue': _money(r['revenue'])}
                           for r in out.values()),
                          key=lambda r: -Decimal(r['revenue']))

        return {
            'by_connection': group('site_visit__connection_type', 'Not recorded'),
            'by_roof': group('site_visit__roof_type', 'Not recorded'),
        }

    # ── Ranked groups ──
    def _ranked(self, rows):
        """A ranking with its two ends called out, which is what gets asked for
        first. `best` and `worst` are None when there is nothing to compare."""
        rows.sort(key=lambda r: (-Decimal(r['revenue']), -r['closed_deals'], r['name']))
        # Both ends are drawn from the ones that actually earned. A ranking of
        # zeros is a tie nobody can act on, and calling a branch on nothing the
        # "most revenue" branch — which happens when none has earned yet — is
        # simply wrong. The zeros are named separately instead.
        earning = [r for r in rows if Decimal(r['revenue']) > 0]
        return {
            'rows': rows[:self.TOP_N],
            'count': len(rows),
            'best': earning[0] if earning else None,
            'worst': earning[-1] if len(earning) > 1 else None,
            'only_earner': len(earning) == 1,
            'without_revenue': [r['name'] for r in rows if Decimal(r['revenue']) == 0],
        }

    def _group_figures(self, leads_qs, won_qs, extra=None):
        money = won_qs.aggregate(
            revenue=Coalesce(Sum(received_value()), _ZERO, output_field=_MONEY),
            billed=Coalesce(Sum(net_value()), _ZERO, output_field=_MONEY))
        leads = leads_qs.count()
        closed = won_qs.count()
        row = {
            'leads': leads,
            'converted': leads_qs.filter(status='converted', is_lost=False).count(),
            'closed_deals': closed,
            'completed_projects': won_qs.filter(project__is_complete=True).count(),
            'revenue': _money(money['revenue']),
            'billed': _money(money['billed']),
            'close_rate': _rate(closed, leads),
        }
        row.update(extra or {})
        return row

    def _scoped(self, condition, start, end):
        """The leads a group worked, and the deals they won, in the window."""
        leads_qs = live_leads().filter(condition).distinct()
        if start:
            leads_qs = leads_qs.filter(created_at__date__gte=start)
        if end:
            leads_qs = leads_qs.filter(created_at__date__lte=end)

        won_qs = closed_deals(live_leads().filter(condition)).distinct()
        if start:
            won_qs = won_qs.filter(status_changed_at__date__gte=start)
        if end:
            won_qs = won_qs.filter(status_changed_at__date__lte=end)
        return leads_qs, won_qs

    def _branches(self, start, end):
        from users.models import Branch
        rows = []
        for branch in Branch.objects.prefetch_related('members'):
            # A lead belongs to a branch through whoever worked it. One handled
            # by two branches counts for both — that is what happened.
            leads_qs, won_qs = self._scoped(
                Q(assigned_to__branch=branch) | Q(bde__branch=branch)
                | Q(tele_caller__branch=branch), start, end)
            rows.append(self._group_figures(leads_qs, won_qs, {
                'id': branch.id, 'name': branch.name, 'code': branch.code,
                'is_active': branch.is_active, 'staff': branch.members.count(),
            }))
        ranked = self._ranked(rows)
        # These rows will not add up to the company total on their own, and it
        # is better to say why than to let someone chase the difference: a deal
        # closed by people who are not on any branch belongs to no branch.
        _, orphan_won = self._scoped(
            Q(assigned_to__branch__isnull=True) & Q(bde__branch__isnull=True)
            & Q(tele_caller__branch__isnull=True), start, end)
        ranked['unattributed_revenue'] = _money(orphan_won.aggregate(
            t=Coalesce(Sum(received_value()), _ZERO, output_field=_MONEY))['t'])
        ranked['unattributed_deals'] = orphan_won.count()
        return ranked

    def _teams(self, start, end):
        from users.models import WorkspaceTeam
        rows = []
        for team in WorkspaceTeam.objects.prefetch_related('members'):
            members = list(team.members.all())
            leads_qs, won_qs = self._scoped(
                Q(assigned_to__in=members) | Q(bde__in=members) | Q(tele_caller__in=members),
                start, end)
            rows.append(self._group_figures(leads_qs, won_qs, {
                'id': team.id, 'name': team.name, 'staff': len(members),
                'manager_name': (f"{team.manager.first_name} {team.manager.last_name}".strip()
                                 or team.manager.username) if team.manager else None,
            }))
        return self._ranked(rows)

    def _employees(self, start, end):
        """Everyone who worked a lead in the window, and the two front-line roles
        pulled out on their own.

        The BDE and tele caller boards are the same rows filtered by role, not a
        second calculation — a person's figures read the same whichever board
        they appear on, and they match My Performance too.
        """
        from users.models import User
        rows = []
        for user in User.objects.filter(is_active=True).select_related('branch'):
            leads_qs, won_qs = self._scoped(
                Q(assigned_to=user) | Q(bde=user) | Q(tele_caller=user), start, end)
            if not leads_qs.exists():
                continue                    # nothing to report is not a zero row
            rows.append(self._group_figures(leads_qs, won_qs, {
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}".strip() or user.username,
                'role': user.get_role_display(),
                'role_key': user.role,
                'branch': user.branch.name if user.branch else None,
            }))

        def only(role):
            # A fresh list each time: _ranked sorts in place.
            return self._ranked([dict(r) for r in rows if r['role_key'] == role])

        return self._ranked(rows), only('bde'), only('tele_caller')
