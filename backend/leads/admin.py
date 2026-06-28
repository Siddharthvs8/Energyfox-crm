from django.contrib import admin
from .models import Lead, SiteVisit

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'email', 'source', 'status', 'created_at']
    list_filter = ['status', 'source']
    search_fields = ['first_name', 'last_name', 'email']

@admin.register(SiteVisit)
class SiteVisitAdmin(admin.ModelAdmin):
    list_display = ['lead', 'roof_type', 'phase', 'feasible_capacity', 'updated_at']
    list_filter = ['roof_type', 'phase', 'structure_type']
    search_fields = ['lead__first_name', 'lead__last_name', 'lead__phone']
