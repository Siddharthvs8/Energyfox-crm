import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai_manager.models import MonthlyTarget, DailyTarget
from leads.models import Lead
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum

mt = MonthlyTarget.objects.first()
if mt:
    print(f"Testing for {mt}")
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    
    # 1. Get past actuals
    enrolled_past = Lead.objects.filter(
        assigned_to=mt.agent,
        status='enrolled',
        status_changed_at__year=mt.year,
        status_changed_at__month=mt.month,
        status_changed_at__date__lte=yesterday
    )
    actual_leads_past = enrolled_past.count()
    actual_amount_past = enrolled_past.aggregate(t=Sum('value'))['t'] or 0
    
    print(f"Past Actuals: Leads={actual_leads_past}, Amt={actual_amount_past}")
