"""Email endpoints, mounted at /api/email/ (see config/urls.py)."""
from django.urls import path

from .views import EmailSendView, EmailMessagesView, EmailStatusView, EmailTestView

urlpatterns = [
    path('status/', EmailStatusView.as_view(), name='email-status'),
    path('send/', EmailSendView.as_view(), name='email-send'),
    path('test/', EmailTestView.as_view(), name='email-test'),
    path('messages/', EmailMessagesView.as_view(), name='email-messages'),
]
