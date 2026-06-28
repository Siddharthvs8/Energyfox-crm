from django.contrib import admin
from .models import MonthlyTarget, DailyTarget, Holiday, Meeting, ManagerConfig, Notification

admin.site.register(MonthlyTarget)
admin.site.register(DailyTarget)
admin.site.register(Holiday)
admin.site.register(Meeting)
@admin.register(ManagerConfig)
class ManagerConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'assignment_strategy', 'auto_assign_enabled', 'meeting_enabled', 'meeting_language', 'updated_at')
    list_filter = ('meeting_enabled', 'meeting_language')

admin.site.register(Notification)
