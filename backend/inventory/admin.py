from django.contrib import admin
from .models import Vendor, PurchaseOrder, Quote, SalesOrder

admin.site.register(Vendor)
admin.site.register(PurchaseOrder)
admin.site.register(Quote)
admin.site.register(SalesOrder)
