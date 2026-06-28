from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CallLogViewSet
from .webhooks import airtel_status_callback, airtel_bridge_callback, voxbay_webhook, voxbay_webhook_debug, exotel_webhook

router = DefaultRouter()
router.register(r'', CallLogViewSet, basename='calls')

urlpatterns = [
    path('webhook/', airtel_status_callback, name='airtel_webhook'),
    path('webhook/bridge/', airtel_bridge_callback, name='airtel_bridge'),
    path('webhook/voxbay/', voxbay_webhook, name='voxbay_webhook'),
    path('webhook/voxbay', voxbay_webhook, name='voxbay_webhook_no_slash'),
    path('webhook/voxbay/debug/', voxbay_webhook_debug, name='voxbay_webhook_debug'),
    path('webhook/exotel/', exotel_webhook, name='exotel_webhook'),
    path('webhook/exotel', exotel_webhook, name='exotel_webhook_no_slash'),
    path('', include(router.urls)),
]
