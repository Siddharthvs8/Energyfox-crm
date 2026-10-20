"""Rewards API.

    GET /api/rewards/            the game as the viewer sees it. An admin may add
                                 ?user=<id> to open one player's card.
    GET /api/rewards/settings/   the rules — admins.
    PUT /api/rewards/settings/   change them — admins.

The sales team (BDEs and tele callers) play; admins and super admins run it.
Everyone sees the table's points and ranks — that is the game — but a person's
incentives are money, and only they and the admins see theirs.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import engine
from .models import PARTICIPANT_ROLES, ContestResult, RewardMonth, RewardSettings, RewardStanding
from .serializers import RewardSettingsSerializer

HALL_OF_FAME_MONTHS = 6
CONTEST_BOARD_SIZE = 10


def is_admin(user):
    return bool(user and user.is_authenticated and user.is_staff)


def plays(user):
    return bool(user and user.is_authenticated and user.is_active
                and getattr(user, 'role', '') in PARTICIPANT_ROLES)


def money(value):
    return str((value or Decimal('0')).quantize(Decimal('0.01')))


def initials(name):
    parts = [p for p in (name or '').split() if p]
    return ''.join(p[0] for p in parts[:2]).upper() or '?'


def month_label(year, month):
    return date(year, month, 1).strftime('%B %Y')


class RewardsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        viewer = request.user
        admin = is_admin(viewer)
        if not (admin or plays(viewer)):
            return Response({'error': 'Rewards are for the sales team.'},
                            status=status.HTTP_403_FORBIDDEN)

        subject = viewer
        asked = request.query_params.get('user')
        if asked and admin:
            subject = (get_user_model().objects
                       .filter(pk=asked if str(asked).isdigit() else None,
                               role__in=PARTICIPANT_ROLES).first())
            if subject is None:
                return Response({'error': 'That person is not on the sales team.'},
                                status=status.HTTP_404_NOT_FOUND)

        engine.close_due()
        today = timezone.localdate()
        rules = RewardSettings.load()
        rungs = engine.ladder()
        first = today.replace(day=1)
        start, end = engine.month_bounds(first)
        rows = engine.standings(start, end, rules, rungs)
        mine = next((r for r in rows if r['user'] == subject.id), None) if plays(subject) else None

        return Response({
            'is_admin': admin,
            'viewer': {'id': viewer.id, 'name': engine.display_name(viewer),
                       'role': getattr(viewer, 'role', '')},
            'month': {
                'key': first.strftime('%Y-%m'), 'label': first.strftime('%B %Y'),
                'start': start.isoformat(), 'end': end.isoformat(),
                'days_left': (end - today).days + 1,
            },
            'rules': self._rules(rules),
            'tiers': [{'id': t.id, 'name': t.name, 'reward': t.reward, 'target': money(t.target),
                       'target_telecaller': money(t.target_telecaller)
                       if t.target_telecaller is not None else None} for t in rungs],
            'board': [self._board_row(r, admin or r['user'] == viewer.id, viewer, subject)
                      for r in rows],
            'me': self._me(subject, mine, rows, rules, today) if mine else None,
            'last_month': self._last_month(first),
            'hall_of_fame': self._hall_of_fame(),
            'contest': self._contest(rules, today, subject),
            'kpis': self._kpis(rows) if admin else None,
        })

    # ── Pieces ──
    @staticmethod
    def _rules(rules):
        return {
            'bde_share': money(rules.bde_share), 'telecaller_share': money(rules.telecaller_share),
            'prizes': [{'rank': n, 'medal': engine.MEDALS[n - 1], 'prize': rules.prize_for(n),
                        'coins': rules.coins_for(n)} for n in (1, 2, 3)],
            'coin_champion_prize': rules.coin_champion_prize,
        }

    @staticmethod
    def _board_row(row, show_money, viewer, subject):
        out = {
            'rank': row['rank'], 'user': row['user'], 'name': row['name'],
            'initials': initials(row['name']), 'role': row['role'],
            'points': money(row['points']), 'deals': row['deals'],
            'tier': (row['tier']['current'] or {}).get('name'),
            'tiers_reached': row['tier']['reached'],
            'is_me': row['user'] == viewer.id, 'is_subject': row['user'] == subject.id,
        }
        if show_money:
            out['incentives'] = money(row['incentives'])
        return out

    def _me(self, subject, mine, rows, rules, today):
        past = list(RewardStanding.objects.filter(user=subject)
                    .select_related('reward_month')
                    .order_by('-reward_month__year', '-reward_month__month'))
        history = [{
            'key': f'{s.reward_month.year}-{s.reward_month.month:02d}',
            'label': month_label(s.reward_month.year, s.reward_month.month),
            'rank': s.rank, 'points': money(s.points), 'medal': s.medal, 'prize': s.prize,
            'coins': s.coins, 'rewards': s.rewards, 'tier': s.tier_name,
        } for s in past if s.medal or s.rewards][:12]

        contest_wins = []
        for result in ContestResult.objects.all():
            for w in result.winners:
                if w.get('user') == subject.id:
                    contest_wins.append({'contest': result.name, 'rank': w['rank'], 'prize': w['prize']})
            if (result.coin_champion or {}).get('user') == subject.id:
                contest_wins.append({'contest': result.name, 'rank': None,
                                     'prize': result.coin_champion.get('prize', ''),
                                     'coin_champion': True})

        won_before = (sum(len(s.rewards or []) for s in past)
                      + sum(1 for s in past if s.medal) + len(contest_wins))
        if rules.contest_start and rules.contest_end:
            coins = engine.coins_between(rules.contest_start, rules.contest_end).get(subject.id, 0)
        else:
            coins = sum(s.coins for s in past)
        return {
            'user': subject.id, 'name': engine.display_name(subject), 'role': subject.role,
            'rank': mine['rank'], 'of': len(rows),
            'points': money(mine['points']), 'deals': mine['deals'],
            'tier': mine['tier'],
            'incentives': {'total': money(mine['incentives']), 'deals': mine['incentive_deals']},
            'coins': coins,
            'rewards_total': won_before + len(mine['tier']['rewards']),
            'history': history,
            'contest_wins': contest_wins,
        }

    @staticmethod
    def _podium(record):
        return [{'medal': s.medal, 'rank': s.rank, 'user': s.user_id, 'name': s.name,
                 'initials': initials(s.name), 'role': s.role, 'points': money(s.points),
                 'prize': s.prize, 'coins': s.coins}
                for s in record.standings.exclude(medal='').order_by('rank')]

    def _last_month(self, first):
        before = engine.previous_month(first)
        record = RewardMonth.objects.filter(year=before.year, month=before.month).first()
        if record is None:
            return None
        return {'key': before.strftime('%Y-%m'), 'label': before.strftime('%B %Y'),
                'podium': self._podium(record)}

    def _hall_of_fame(self):
        out = []
        for record in RewardMonth.objects.prefetch_related('standings')[:HALL_OF_FAME_MONTHS]:
            podium = self._podium(record)
            if podium:
                out.append({'key': f'{record.year}-{record.month:02d}',
                            'label': month_label(record.year, record.month), 'podium': podium})
        return out

    def _contest(self, rules, today, subject):
        if not (rules.contest_start and rules.contest_end):
            return None
        start, end = rules.contest_start, rules.contest_end
        rows = engine.contest_table(rules, today)

        def row(r):
            return {'rank': r['rank'], 'user': r['user'], 'name': r['name'],
                    'initials': initials(r['name']), 'role': r['role'],
                    'points': money(r['points']), 'coins': r['coins'],
                    'is_subject': r['user'] == subject.id}

        board = [row(r) for r in rows[:CONTEST_BOARD_SIZE]]
        mine = next((r for r in rows if r['user'] == subject.id), None)
        if mine and mine['rank'] > CONTEST_BOARD_SIZE:
            board.append(row(mine))
        coin_rows = sorted([r for r in rows if r['coins'] > 0],
                           key=lambda r: (-r['coins'], -r['points'], r['name'].lower()))[:5]
        result = ContestResult.objects.filter(start=start, end=end).first()
        status_ = ('awarded' if result else 'upcoming' if today < start
                   else 'finished' if today > end else 'running')
        me = None
        if mine:
            progress = None
            if rules.contest_target:
                progress = float(min(mine['points'] / rules.contest_target, Decimal('1')))
            me = {'rank': mine['rank'], 'points': money(mine['points']), 'coins': mine['coins'],
                  'progress': progress}
        return {
            'name': rules.contest_name or 'Yearly contest',
            'start': start.isoformat(), 'end': end.isoformat(), 'status': status_,
            'days_left': max((end - today).days + 1, 0) if today <= end else 0,
            'starts_in': max((start - today).days, 0),
            'target': money(rules.contest_target) if rules.contest_target else None,
            'bumpers': [{'rank': n, 'prize': rules.bumper_for(n)} for n in (1, 2, 3)],
            'coin_champion_prize': rules.coin_champion_prize,
            'board': board,
            'coin_board': [row(r) for r in coin_rows],
            'me': me,
            'result': ({'winners': result.winners, 'coin_champion': result.coin_champion}
                       if result else None),
        }

    @staticmethod
    def _kpis(rows):
        return {
            'players': len(rows),
            'scoring': sum(1 for r in rows if r['points'] > 0),
            'points': money(sum((r['points'] for r in rows), Decimal('0'))),
            'tiers_unlocked': sum(r['tier']['reached'] for r in rows),
            'incentives': money(sum((r['incentives'] for r in rows), Decimal('0'))),
        }


class RewardSettingsView(APIView):
    """The rules of the game. Admins and super admins only."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not is_admin(request.user):
            return Response({'error': 'Only admins can see the reward settings.'},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(RewardSettingsSerializer(RewardSettings.load()).data)

    def put(self, request):
        if not is_admin(request.user):
            return Response({'error': 'Only admins can change the reward settings.'},
                            status=status.HTTP_403_FORBIDDEN)
        serializer = RewardSettingsSerializer(RewardSettings.load(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)
