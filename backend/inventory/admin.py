from django.contrib import admin

from .models import (Vendor, PurchaseOrder, Quote, SalesOrder,
                     ProjectSpec, Quotation, QuotationTemplate)

admin.site.register(Vendor)
admin.site.register(PurchaseOrder)
admin.site.register(Quote)
admin.site.register(SalesOrder)


@admin.register(QuotationTemplate)
class QuotationTemplateAdmin(admin.ModelAdmin):
    """The approved artwork each system type's proposal is built on.

    Registered here because the file has to be installed on the server it runs
    on — a template uploaded on a laptop is not on production, and without one
    every quotation of that type reports that it has none. This is the way in
    until the CRM grows its own upload screen.
    """
    list_display = ('system_type', 'pdf', 'uploaded_at', 'uploaded_by')
    list_filter = ('system_type',)
    readonly_fields = ('uploaded_at',)

    def save_model(self, request, obj, form, change):
        if not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ProjectSpec)
class ProjectSpecAdmin(admin.ModelAdmin):
    list_display = ('name', 'system_type', 'capacity', 'price_dcr', 'price_non_dcr',
                    'subsidy_amount', 'is_active')
    list_filter = ('system_type', 'is_active')
    search_fields = ('name', 'capacity')


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ('number', 'lead', 'project', 'price_variant', 'status', 'created_at')
    list_filter = ('status', 'price_variant')
    search_fields = ('number',)
