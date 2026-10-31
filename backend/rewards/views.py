"""Rewards API.

    GET /api/rewards/            the game as the viewer sees it. An admin may add
                                 ?user=<id> to open one player's card.
    GET /api/rewards/referrals/  the Referral Rewards page — everyone on the
                                 staff; admins may add ?month=YYYY-MM.
    GET /api/rewards/settings/   the rules — admins.
    PUT /api/rewards/settings/   change them — admins.
    POST   /api/rewards/exclusions/            take a payment out of the game — admins.
    DELETE /api/rewards/exclusions/?key=<key>  put it back — admins.
    POST   /api/rewards/gift-images/           upload a gift's picture — admins.

The sales team (BDEs and tele callers) play; admins and super admins run it.
Everyone sees the table's points and ranks — that is the game — but a person's
incentives are money, and only they and the admins see theirs.
"""
import os
import re
import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework import parsers, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import engine
from .models import (GIFT_DIR, PARTICIPANT_ROLES, ContestResult, ExcludedPayment, RewardMonth,
                     RewardSettings, RewardStanding, RewardTier)
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


def role_label(user):
    if user.role == 'custom' and user.custom_role:
        return user.custom_role.name
    return user.get_role_display()


def referral_month(first, earned=None):
    """Referral rewards earned in the month beginning `first`, by person.

    Anyone on the staff can refer a customer, so this lists everyone who earned
    one, not only the players. `earned` is referral_rewards_between for the
    month, for a caller that already has it.
    """
    if earned is None:
        earned = engine.referral_rewards_between(*engine.month_bounds(first))
    people = {u.id: u for u in get_user_model().objects
              .filter(id__in=list(earned)).select_related('custom_role')}
    rows = [{
        'user': user_id, 'name': engine.display_name(people[user_id]),
        'role': role_label(people[user_id]),
        'total': money(mine['total']), 'deals': mine['deals'],
    } for user_id, mine in earned.items() if user_id in people]
    rows.sort(key=lambda r: (-Decimal(r['total']), r['name'].lower()))
    return {'key': first.strftime('%Y-%m'), 'label': first.strftime('%B %Y'),
            'total': money(sum((m['total'] for m in earned.values()), Decimal('0'))),
            'people': rows}


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
        referrals = engine.referral_rewards_between(start, end)
        rows = engine.standings(start, end, rules, rungs, referrals)
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
            'tiers': [self._tier(t) for t in rungs],
            'board': [self._board_row(r, admin or r['user'] == viewer.id, viewer, subject)
                      for r in rows],
            'me': self._me(subject, mine, rows, rules, start, end, referrals) if mine else None,
            'last_month': self._last_month(first),
            'hall_of_fame': self._hall_of_fame(),
            'contest': self._contest(rules, today, subject),
            'kpis': self._kpis(rows) if admin else None,
            'referrals': self._referrals(first, referrals) if admin else None,
        })

    # ── Pieces ──
    @staticmethod
    def _tier(tier):
        gift = tier.reward_type == RewardTier.GIFT
        return {
            'id': tier.id, 'name': tier.name,
            'reward': tier.reward_label,          # in words, wherever text goes
            'reward_type': tier.reward_type,
            'reward_amount': money(tier.reward_amount) if tier.reward_amount is not None else None,
            # A path under /media, or a full address when media is on S3.
            'image': tier.reward_image.url if gift and tier.reward_image else None,
            'target': money(tier.target),
            'target_telecaller': money(tier.target_telecaller) if tier.target_telecaller is not None else None,
        }

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
            out['referrals'] = money(row['referrals'])
        return out

    @staticmethod
    def _referrals(first, this_month):
        """Referral rewards earned, by person, this month and last. Last month
        is here because rewards are paid after a month ends, and on the 1st
        this month's list is empty."""
        return {'this_month': referral_month(first, this_month),
                'last_month': referral_month(engine.previous_month(first))}

    def _me(self, subject, mine, rows, rules, start, end, referrals):
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
            # Kept apart from the incentives: those come with selling, this
            # comes with sending a customer our way, which anyone can do.
            'referrals': {'total': money((referrals.get(subject.id) or {}).get('total')),
                          'deals': (referrals.get(subject.id) or {}).get('deals', [])},
            'coins': coins,
            'rewards_total': won_before + len(mine['tier']['rewards']),
            'history': history,
            'contest_wins': contest_wins,
            # Every payment behind this month's points, so the figure above it
            # can be checked against the money.
            'statement': engine.statement(subject, start, end, rules),
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


class ReferralRewardsView(APIView):
    """The Referral Rewards page.

    Anyone on the staff can refer a customer, so unlike the rest of the Rewards
    API this is open to every role. Each person sees the customers they
    referred and what those earned them; the admins who pay the rewards also
    see everyone's, a month at a time (?month=YYYY-MM, this month by default).
    """
    permission_classes = [permissions.IsAuthenticated]
    MONTHS_OFFERED = 12

    def get(self, request):
        user = request.user
        admin = is_admin(user)
        first = timezone.localdate().replace(day=1)

        chosen = first
        asked = (request.query_params.get('month') or '').strip()
        if asked and admin:
            m = re.fullmatch(r'(\d{4})-(\d{2})', asked)
            try:
                chosen = date(int(m.group(1)), int(m.group(2)), 1) if m else None
            except ValueError:          # a month that does not exist, such as 13
                chosen = None
            if chosen is None:
                return Response({'error': 'Ask for a month as YYYY-MM.'}, status=status.HTTP_400_BAD_REQUEST)
            if chosen > first:
                return Response({'error': 'That month has not happened yet.'},
                                status=status.HTTP_400_BAD_REQUEST)

        rows = engine.referral_statement(user)

        def earned_in(month_first):
            start, end = engine.month_bounds(month_first)
            return {'key': month_first.strftime('%Y-%m'), 'label': month_first.strftime('%B %Y'),
                    'total': money(sum((r['reward'] for r in rows
                                        if r['status'] == 'earned' and start <= r['earned_on'] <= end),
                                       Decimal('0')))}

        months, cursor = [], first
        for _ in range(self.MONTHS_OFFERED):
            months.append({'key': cursor.strftime('%Y-%m'), 'label': cursor.strftime('%B %Y')})
            cursor = engine.previous_month(cursor)

        return Response({
            'is_admin': admin,
            'me': {
                'this_month': earned_in(first),
                'last_month': earned_in(engine.previous_month(first)),
                'earned_total': money(sum((r['reward'] for r in rows if r['status'] == 'earned'),
                                          Decimal('0'))),
                'waiting_total': money(sum((r['reward'] for r in rows if r['status'] == 'waiting'),
                                           Decimal('0'))),
                'referrals': [{
                    **r,
                    'referred_on': r['referred_on'].isoformat() if r['referred_on'] else None,
                    'reward': money(r['reward']) if r['reward'] is not None else None,
                    'earned_on': r['earned_on'].isoformat() if r['earned_on'] else None,
                } for r in rows],
            },
            'months': months if admin else [],
            'month': referral_month(chosen) if admin else None,
        })


class ExclusionsView(APIView):
    """Take a payment out of the game, or put it back. Admins and super admins.

    A payment is named as the statement lists it: `first:<lead id>` for the
    one taken at verification, `balance:<id>` for a balance payment. The
    reason is required — the player sees it on their statement.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not is_admin(request.user):
            return Response({'error': 'Only admins can change what counts.'},
                            status=status.HTTP_403_FORBIDDEN)
        key = str(request.data.get('key') or '').strip()
        reason = ' '.join(str(request.data.get('reason') or '').split())
        lead = engine.payment_lead(key)
        if lead is None:
            return Response({'error': 'That payment was not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not reason:
            return Response({'error': 'Say why it should not count — the player sees the reason.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(reason) > 200:
            return Response({'error': 'Keep the reason under 200 characters.'},
                            status=status.HTTP_400_BAD_REQUEST)
        exclusion, _ = ExcludedPayment.objects.update_or_create(
            key=key, defaults={'lead': lead, 'reason': reason, 'excluded_by': request.user})
        return Response({'key': exclusion.key, 'reason': exclusion.reason,
                         'excluded_by': engine.display_name(request.user)},
                        status=status.HTTP_201_CREATED)

    def delete(self, request):
        if not is_admin(request.user):
            return Response({'error': 'Only admins can change what counts.'},
                            status=status.HTTP_403_FORBIDDEN)
        exclusion = ExcludedPayment.objects.filter(key=request.query_params.get('key', '')).first()
        if exclusion is None:
            return Response({'error': 'That payment already counts.'}, status=status.HTTP_404_NOT_FOUND)
        exclusion.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RewardSettingsView(APIView):
    """The rules of the game. Admins and super admins only."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not is_admin(request.user):
            return Response({'error': 'Only admins can see the reward settings.'},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(RewardSettingsSerializer(RewardSettings.load(), context={'request': request}).data)

    def put(self, request):
        if not is_admin(request.user):
            return Response({'error': 'Only admins can change the reward settings.'},
                            status=status.HTTP_403_FORBIDDEN)
        serializer = RewardSettingsSerializer(RewardSettings.load(), data=request.data, partial=True,
                                              context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)


class GiftImageView(APIView):
    """Upload a gift's picture. Admins and super admins.

    The ladder is saved whole, so the picture goes up first: this returns the
    stored name to send as the tier's `reward_image`, and a URL to preview it.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    MAX_BYTES = 5 * 1024 * 1024
    FORMATS = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}
    # A reward card shows the picture a few hundred pixels across.
    LONG_SIDE = 1200
    # A small file can still unpack into an enormous picture.
    MAX_PIXELS = 40_000_000

    def post(self, request):
        if not is_admin(request.user):
            return Response({'error': 'Only admins can add reward pictures.'},
                            status=status.HTTP_403_FORBIDDEN)
        upload = request.FILES.get('image')
        if upload is None:
            return Response({'error': 'Choose a picture to upload.'}, status=status.HTTP_400_BAD_REQUEST)
        ext = os.path.splitext(upload.name or '')[1].lower()
        if ext not in self.FORMATS:
            return Response({'error': 'Use a JPG, PNG or WebP picture.'}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > self.MAX_BYTES:
            return Response({'error': 'Keep the picture under 5 MB.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            serializers.ImageField().run_validation(upload)
            picture = self._fit(upload, ext)
        except (serializers.ValidationError, DjangoValidationError, ValueError, OSError):
            return Response({'error': 'That file is not a picture we can show.'},
                            status=status.HTTP_400_BAD_REQUEST)
        name = default_storage.save(f'{GIFT_DIR}{uuid.uuid4().hex}{ext}', picture)
        return Response({'path': name, 'url': default_storage.url(name)}, status=status.HTTP_201_CREATED)

    def _fit(self, upload, ext):
        """The picture, upright and no larger than a card needs — phone photos
        run to megabytes, and every player downloads it. Saving it afresh also
        drops what the camera wrote into it, such as where it was taken."""
        from PIL import Image, ImageOps
        upload.seek(0)
        image = Image.open(upload)
        if image.width * image.height > self.MAX_PIXELS:
            raise ValueError('picture too large')
        image = ImageOps.exif_transpose(image)
        image.thumbnail((self.LONG_SIDE, self.LONG_SIDE))
        fmt = self.FORMATS[ext]
        if fmt == 'JPEG' and image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        out = BytesIO()
        image.save(out, fmt, **({'quality': 85} if fmt in ('JPEG', 'WEBP') else {'optimize': True}))
        return ContentFile(out.getvalue())
