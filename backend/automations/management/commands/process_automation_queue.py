"""
Processes time-based automation work. Run periodically
(e.g. every 5–15 minutes) via cron / Windows Task Scheduler:

    python manage.py process_automation_queue

It does two things:
  1. Resumes due ScheduledActions (the remainder of a rule after a `wait` step).
  2. Evaluates `lead_inactive` rules and fires them for stale leads.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone


# Statuses that mean the lead is "closed" — never treated as inactive.
_CLOSED_STATUSES = ['converted', 'not_interested']


class Command(BaseCommand):
    help = 'Resume due scheduled automation actions and evaluate time-based (lead_inactive) rules.'

    def handle(self, *args, **options):
        resumed, inactive, wa = self._process()
        self.stdout.write(self.style.SUCCESS(
            f'Done. Resumed {resumed} scheduled action(s); fired lead_inactive for '
            f'{inactive} lead(s); sent {wa} queued WhatsApp message(s).'
        ))

    def _process(self):
        from automations.models import ScheduledAction, AutomationRule
        from automations.engine import resume_scheduled_action, fire_trigger

        now = timezone.now()

        # 1) Resume due scheduled actions (post-`wait` remainders).
        resumed = 0
        due = ScheduledAction.objects.filter(processed=False, run_at__lte=now)
        for sa in due:
            try:
                resume_scheduled_action(sa)
            except Exception:
                pass
            sa.processed = True
            sa.processed_at = timezone.now()
            sa.save(update_fields=['processed', 'processed_at'])
            resumed += 1

        # 2) Evaluate lead_inactive rules. The engine's per-object cooldown
        #    prevents re-firing the same lead repeatedly (set a cooldown on the rule).
        inactive_fired = 0
        rules = AutomationRule.objects.filter(is_active=True, trigger_event='lead_inactive')
        if rules.exists():
            from leads.models import Lead
            for rule in rules:
                days = int((rule.trigger_config or {}).get('inactive_days', 3) or 3)
                cutoff = now - timedelta(days=days)
                qs = (Lead.objects
                      .exclude(status__in=_CLOSED_STATUSES)
                      .annotate(last_act=Max('activity_logs__created_at')))
                for lead in qs.iterator():
                    last = lead.last_act or lead.created_at
                    if last and last <= cutoff:
                        try:
                            fire_trigger('lead_inactive', lead, context={'inactive_days': days})
                            inactive_fired += 1
                        except Exception:
                            pass

        # 3) Flush queued outbound WhatsApp messages (from bulk send), rate-limited.
        wa_sent = 0
        try:
            from messaging.models import WhatsAppMessage
            from messaging.whatsapp import send_text, send_template, is_configured
            if is_configured():
                pending = list(WhatsAppMessage.objects.filter(direction='out', status='pending')[:200])
                for m in pending:
                    try:
                        if m.kind == 'template':
                            mid = send_template(m.to_number, m.template_name, m.language, m.variables)
                        else:
                            mid = send_text(m.to_number, m.text)
                        m.status = 'sent'
                        m.provider_message_id = mid
                        m.sent_at = timezone.now()
                    except Exception as e:
                        m.status = 'failed'
                        m.error = str(e)[:500]
                    m.save(update_fields=['status', 'provider_message_id', 'sent_at', 'error'])
                    wa_sent += 1
        except Exception:
            pass

        return resumed, inactive_fired, wa_sent
