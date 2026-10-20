"""Rewards — a monthly game for the sales team (BDEs and tele callers).

Points are money received: one point for every rupee a customer actually paid,
in the month it was paid, shared between the people who own the deal. They
climb a ladder of tiers, each unlocking a reward, and the ladder starts again
on the 1st. When a month ends its top three are announced — gold, silver and
bronze — and win prizes and coins. Over a contest the admins date (usually a
year), the top three by points win bumper prizes and whoever collected the
most coins wins the coin champion's prize.

Live figures are worked out from the payments themselves (see engine.py).
What a closed month or a finished contest decided is frozen here, so a payment
edited afterwards cannot take a medal back off someone it was announced for.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

PARTICIPANT_ROLES = ('bde', 'tele_caller')


def first_of_this_month():
    return timezone.localdate().replace(day=1)


class RewardSettings(models.Model):
    """The rules of the game — one row, edited from Rewards → Configuration."""

    # A deal with a BDE and a tele caller: the BDE's share of the money, the
    # tele caller earning the rest. A deal with one owner pays that owner all
    # of it.
    bde_share = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('75'))

    # The month's top three.
    gold_prize = models.CharField(max_length=200, blank=True, default='')
    silver_prize = models.CharField(max_length=200, blank=True, default='')
    bronze_prize = models.CharField(max_length=200, blank=True, default='')
    gold_coins = models.PositiveIntegerField(default=30)
    silver_coins = models.PositiveIntegerField(default=20)
    bronze_coins = models.PositiveIntegerField(default=10)

    # Months before this predate the game: no podium, coins or announcement for
    # them, only the live figures. Defaults to the month the game was set up.
    program_start = models.DateField(default=first_of_this_month)

    # The contest — normally a financial year.
    contest_name = models.CharField(max_length=120, blank=True, default='')
    contest_start = models.DateField(null=True, blank=True)
    contest_end = models.DateField(null=True, blank=True)
    # Optional: a points goal for the contest, shown as everyone's progress.
    contest_target = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    bumper_first = models.CharField(max_length=200, blank=True, default='')
    bumper_second = models.CharField(max_length=200, blank=True, default='')
    bumper_third = models.CharField(max_length=200, blank=True, default='')
    # For whoever holds the most coins when the contest ends.
    coin_champion_prize = models.CharField(max_length=200, blank=True, default='')

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = 'reward settings'
        verbose_name_plural = 'reward settings'

    def __str__(self):
        return 'Reward settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def telecaller_share(self):
        return Decimal('100') - (self.bde_share or Decimal('0'))

    def prize_for(self, rank):
        return {1: self.gold_prize, 2: self.silver_prize, 3: self.bronze_prize}.get(rank, '')

    def coins_for(self, rank):
        return {1: self.gold_coins, 2: self.silver_coins, 3: self.bronze_coins}.get(rank, 0)

    def bumper_for(self, rank):
        return {1: self.bumper_first, 2: self.bumper_second, 3: self.bumper_third}.get(rank, '')


class RewardTier(models.Model):
    """One rung of the monthly ladder: reach the target, unlock the reward.

    The tele caller target is optional. A tele caller earns only their share of
    each deal, so a ladder sized for BDEs would sit out of their reach; setting
    a lower target for them keeps the same rewards within it. Left blank, it is
    the same target for everyone.
    """
    position = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=60)
    reward = models.CharField(max_length=200, blank=True, default='')
    target = models.DecimalField(max_digits=14, decimal_places=2)
    target_telecaller = models.DecimalField(max_digits=14, decimal_places=2,
                                            null=True, blank=True)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return f'{self.name} ({self.target})'

    def target_for(self, role):
        if role == 'tele_caller' and self.target_telecaller is not None:
            return self.target_telecaller
        return self.target


class RewardMonth(models.Model):
    """A month whose results have been decided and announced."""
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    closed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', '-month']
        constraints = [models.UniqueConstraint(fields=['year', 'month'], name='uniq_reward_month')]

    def __str__(self):
        return f'{self.year}-{self.month:02d}'


class RewardStanding(models.Model):
    """One person's month, as it stood when the month closed.

    Name and role are kept alongside the link so the record reads the same
    after someone leaves or changes job.
    """
    MEDALS = [('gold', 'Gold'), ('silver', 'Silver'), ('bronze', 'Bronze')]

    reward_month = models.ForeignKey(RewardMonth, on_delete=models.CASCADE, related_name='standings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             null=True, blank=True, related_name='reward_standings')
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=30)
    rank = models.PositiveIntegerField()
    points = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deals = models.PositiveIntegerField(default=0)
    tier_name = models.CharField(max_length=60, blank=True, default='')
    tiers_reached = models.PositiveIntegerField(default=0)
    rewards = models.JSONField(default=list, blank=True)      # the tier rewards unlocked
    incentives = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    medal = models.CharField(max_length=10, choices=MEDALS, blank=True, default='')
    prize = models.CharField(max_length=200, blank=True, default='')
    coins = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['reward_month', 'rank']

    def __str__(self):
        return f'{self.reward_month} #{self.rank} {self.name}'


class ExcludedPayment(models.Model):
    """A payment an admin has taken out of the game, and why.

    For money that is right in accounts but should not score: paid long before
    and only verified now, or on a deal that was not this person's. Accounts
    keep the payment as it is; only the game stops counting it. A month that
    has already closed keeps what was announced; what is still live — this
    month, the contest — no longer counts it.
    """
    # Names the payment as the statement lists it: 'first:<lead id>' for the
    # one taken at verification, 'balance:<balance payment id>' for the rest.
    key = models.CharField(max_length=40, unique=True)
    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='+')
    reason = models.CharField(max_length=200)
    excluded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='+')
    excluded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-excluded_at']

    def __str__(self):
        return f'{self.key}: {self.reason}'


class ContestResult(models.Model):
    """A finished contest: who won the bumper prizes and the coin champion's."""
    name = models.CharField(max_length=120, blank=True, default='')
    start = models.DateField()
    end = models.DateField()
    winners = models.JSONField(default=list, blank=True)        # [{rank, user, name, points, prize}]
    coin_champion = models.JSONField(default=dict, blank=True)  # {user, name, coins, prize}
    standings = models.JSONField(default=list, blank=True)      # the top of the final table
    closed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-end']
        constraints = [models.UniqueConstraint(fields=['start', 'end'], name='uniq_contest_window')]

    def __str__(self):
        return f'{self.name or "Contest"} {self.start} – {self.end}'
