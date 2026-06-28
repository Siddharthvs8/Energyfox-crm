from django.urls import path
from .views import whatsapp_webhook, WhatsAppBulkView, WhatsAppMessagesView, WhatsAppSendView

urlpatterns = [
    path('webhook/', whatsapp_webhook, name='whatsapp-webhook'),
    path('webhook', whatsapp_webhook),  # no-slash variant (Meta sometimes omits it)
    path('bulk/', WhatsAppBulkView.as_view(), name='whatsapp-bulk'),
    path('send/', WhatsAppSendView.as_view(), name='whatsapp-send'),
    path('messages/', WhatsAppMessagesView.as_view(), name='whatsapp-messages'),
]
