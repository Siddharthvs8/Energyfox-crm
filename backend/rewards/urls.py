from django.urls import path

from .views import ExclusionsView, GiftImageView, ReferralRewardsView, RewardSettingsView, RewardsView

urlpatterns = [
    path('', RewardsView.as_view(), name='rewards'),
    path('referrals/', ReferralRewardsView.as_view(), name='rewards-referrals'),
    path('settings/', RewardSettingsView.as_view(), name='rewards-settings'),
    path('exclusions/', ExclusionsView.as_view(), name='rewards-exclusions'),
    path('gift-images/', GiftImageView.as_view(), name='rewards-gift-images'),
]
