from decimal import Decimal

from django.core.files.storage import default_storage
from rest_framework import serializers

from .models import GIFT_DIR, RewardSettings, RewardTier

MAX_TIERS = 10


class GiftImageField(serializers.Field):
    """A gift's picture, uploaded beforehand (POST /api/rewards/gift-images/):
    sent as the stored name that upload returned, and read back the same way."""

    def to_internal_value(self, data):
        name = str(data or '').strip()
        if not name:
            return ''
        if not name.startswith(GIFT_DIR) or '..' in name or '\\' in name:
            raise serializers.ValidationError('Upload the picture again.')
        if not default_storage.exists(name):
            raise serializers.ValidationError('That picture is no longer there — upload it again.')
        return name

    def to_representation(self, value):
        return value.name if value else None


class TierSerializer(serializers.ModelSerializer):
    reward_image = GiftImageField(required=False, allow_null=True)
    reward_image_url = serializers.SerializerMethodField()

    class Meta:
        model = RewardTier
        fields = ['id', 'position', 'name', 'reward_type', 'reward', 'reward_amount',
                  'reward_image', 'reward_image_url', 'target', 'target_telecaller']
        read_only_fields = ['id', 'position']

    def get_reward_image_url(self, tier):
        return tier.reward_image.url if tier.reward_image else None

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

    def validate(self, attrs):
        """Cash is an amount; a gift is a name, with a picture if there is one.
        Whatever belongs to the other kind is dropped, so a tier switched from
        a gift to cash does not keep the gift's picture."""
        if attrs.get('reward_type', RewardTier.GIFT) == RewardTier.CASH:
            amount = attrs.get('reward_amount')
            if amount is None or amount <= 0:
                raise serializers.ValidationError({'reward_amount': 'Enter the cash amount.'})
            attrs.update(reward='', reward_image='')
        else:
            attrs.update(reward=(attrs.get('reward') or '').strip(), reward_amount=None)
            if attrs.get('reward_image') and not attrs['reward']:
                raise serializers.ValidationError({'reward': 'Name the gift in the picture.'})
        return attrs


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
        data['tiers'] = TierSerializer(RewardTier.objects.all(), many=True, context=self.context).data
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
                RewardTier(position=n, name=t['name'],
                           reward_type=t.get('reward_type', RewardTier.GIFT),
                           reward=t.get('reward', '') or '', reward_amount=t.get('reward_amount'),
                           reward_image=t.get('reward_image') or None,
                           target=t['target'], target_telecaller=t.get('target_telecaller'))
                for n, t in enumerate(tiers)])
        return instance
