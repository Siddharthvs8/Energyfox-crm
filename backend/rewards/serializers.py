from decimal import Decimal

from rest_framework import serializers

from .models import RewardSettings, RewardTier

MAX_TIERS = 10


class TierSerializer(serializers.ModelSerializer):
    class Meta:
        model = RewardTier
        fields = ['id', 'position', 'name', 'reward', 'target', 'target_telecaller']
        read_only_fields = ['id', 'position']

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Give the tier a name.')
        return value

    def validate_target(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError('The target must be more than zero.')
        return value

    def validate_target_telecaller(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError('Leave it blank, or make it more than zero.')
        return value


class RewardSettingsSerializer(serializers.ModelSerializer):
    tiers = TierSerializer(many=True, required=False)
    telecaller_share = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = RewardSettings
        fields = ['bde_share', 'telecaller_share',
                  'gold_prize', 'silver_prize', 'bronze_prize',
                  'gold_coins', 'silver_coins', 'bronze_coins',
                  'program_start',
                  'contest_name', 'contest_start', 'contest_end', 'contest_target',
                  'bumper_first', 'bumper_second', 'bumper_third', 'coin_champion_prize',
                  'tiers', 'updated_at']
        read_only_fields = ['program_start', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['tiers'] = TierSerializer(RewardTier.objects.all(), many=True).data
        return data

    def validate_bde_share(self, value):
        if value is None or not (Decimal('0') <= value <= Decimal('100')):
            raise serializers.ValidationError('The BDE share is a percentage from 0 to 100.')
        return value

    def validate_contest_target(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError('Leave it blank, or make it more than zero.')
        return value

    def validate_tiers(self, tiers):
        if len(tiers) > MAX_TIERS:
            raise serializers.ValidationError(f'Keep it to {MAX_TIERS} tiers or fewer.')
        # Each rung has to be higher than the one below it, for BDEs and for
        # tele callers alike — a ladder that dips is a reward nobody can tell
        # whether they have earned.
        for role, label in (('bde', 'BDE'), ('tele_caller', 'tele caller')):
            previous = None
            for n, tier in enumerate(tiers, 1):
                target = (tier.get('target_telecaller') if role == 'tele_caller'
                          and tier.get('target_telecaller') is not None else tier['target'])
                if previous is not None and target <= previous:
                    raise serializers.ValidationError(
                        f"Tier {n} ({tier['name']}) needs a higher {label} target than tier {n - 1}.")
                previous = target
        return tiers

    def validate(self, attrs):
        start = attrs.get('contest_start', getattr(self.instance, 'contest_start', None))
        end = attrs.get('contest_end', getattr(self.instance, 'contest_end', None))
        if bool(start) != bool(end):
            raise serializers.ValidationError({'contest_end': 'Set both the start and the end of the contest.'})
        if start and end and end < start:
            raise serializers.ValidationError({'contest_end': 'The contest has to end after it starts.'})
        return attrs

    def update(self, instance, validated_data):
        tiers = validated_data.pop('tiers', None)
        instance = super().update(instance, validated_data)
        if tiers is not None:
            # The ladder is saved whole, in the order it was sent.
            RewardTier.objects.all().delete()
            RewardTier.objects.bulk_create([
                RewardTier(position=n, name=t['name'], reward=t.get('reward', '') or '',
                           target=t['target'], target_telecaller=t.get('target_telecaller'))
                for n, t in enumerate(tiers)])
        return instance
