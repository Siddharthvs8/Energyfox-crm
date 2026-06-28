from django.contrib import admin
from .models import OrgSettings


@admin.register(OrgSettings)
class OrgSettingsAdmin(admin.ModelAdmin):
    list_display = ('name', 'telephony_provider', 'updated_at')

    def has_add_permission(self, request):
        # Singleton — never allow creating a second row from the admin.
        return not OrgSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
