from django.urls import path

from .views import RewardSettingsView, RewardsView

urlpatterns = [
    path('', RewardsView.as_view(), name='rewards'),
    path('settings/', RewardSettingsView.as_view(), name='rewards-settings'),
]
