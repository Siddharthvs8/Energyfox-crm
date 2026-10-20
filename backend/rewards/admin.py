from django.contrib import admin

from .models import (ContestResult, ExcludedPayment, RewardMonth, RewardSettings, RewardStanding,
                     RewardTier)

admin.site.register(RewardSettings)
admin.site.register(RewardTier)
admin.site.register(RewardMonth)
admin.site.register(RewardStanding)
admin.site.register(ContestResult)
admin.site.register(ExcludedPayment)
