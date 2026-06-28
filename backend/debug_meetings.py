import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai_manager.models import AIMeetingSession, AIMeetingMessage

sessions = AIMeetingSession.objects.order_by('-started_at')[:5]
for s in sessions:
    print(f"Session ID: {s.id}, Type: {s.session_type}, Status: {s.status}, Started: {s.started_at}")
    messages = AIMeetingMessage.objects.filter(session=s).order_by('timestamp')
    for m in messages:
        print(f"  [{m.sender_type}] {m.content}")
    print("-" * 40)
