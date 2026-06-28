from django.db import models

class CallLog(models.Model):
    OUTCOME_CHOICES = [
        ('initiated', 'Initiated'),
        ('connected', 'Connected'),
        ('rnr', 'RNR'),
        ('busy', 'Busy'),
        ('cancelled', 'Cancelled'),
    ]

    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='calls')
    user = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='calls')
    
    airtel_session_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    voxbay_uuid = models.CharField(max_length=100, unique=True, null=True, blank=True)
    exotel_sid = models.CharField(max_length=100, unique=True, null=True, blank=True)
    duration_seconds = models.IntegerField(default=0)
    outcome = models.CharField(max_length=50, choices=OUTCOME_CHOICES, default='completed')
    direction = models.CharField(
        max_length=20,
        choices=[('inbound', 'Inbound'), ('outbound', 'Outbound')],
        default='outbound',
        db_index=True
    )

    
    recording_url = models.CharField(max_length=1000, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Call for {self.lead} at {self.created_at}"


class WebhookLog(models.Model):
    """Stores every raw webhook payload for debugging."""
    source = models.CharField(max_length=50, default='voxbay')
    method = models.CharField(max_length=10, default='POST')
    host = models.CharField(max_length=255, blank=True, default='')
    raw_payload = models.TextField(blank=True, default='')
    raw_headers = models.TextField(blank=True, default='')
    matched_call_id = models.IntegerField(null=True, blank=True)
    processing_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"WebhookLog {self.source} at {self.created_at}"


# ─── Signals to sync CallLog metrics with DailyTarget input parameters ────────

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

@receiver(post_save, sender=CallLog)
@receiver(post_delete, sender=CallLog)
def update_daily_target_metrics(sender, instance, **kwargs):
    if not instance.user:
        return
    
    # Calculate local date of the call log to match daily targets timezone
    call_date = timezone.localtime(instance.created_at).date()
    
    from ai_manager.models import MonthlyTarget, DailyTarget
    
    # Sum all connected calls for this user on this day
    connected_calls = CallLog.objects.filter(
        user=instance.user,
        created_at__date=call_date,
        outcome='connected'
    )
    
    total_calls = connected_calls.count()
    total_seconds = sum(c.duration_seconds or 0 for c in connected_calls)
    total_minutes = int(round(total_seconds / 60.0))
    
    # Find monthly target
    mt = MonthlyTarget.objects.filter(
        agent=instance.user,
        month=call_date.month,
        year=call_date.year
    ).first()
    
    if mt:
        # Get or create the DailyTarget for this date
        dt, created = DailyTarget.objects.get_or_create(
            agent=instance.user,
            date=call_date,
            defaults={
                'monthly_target': mt,
                'target_leads': 0,
                'target_amount': 0,
                'target_dialed_calls': 0,
                'target_call_time': 0,
            }
        )
        dt.achieved_dialed_calls = total_calls
        dt.achieved_call_time = total_minutes
        dt.save()


def _call_activity_description(call):
    """Human-readable activity line for a call, e.g.
    'Outbound call to John Doe · Connected · 2m 05s'."""
    name = f"{call.lead.first_name} {call.lead.last_name}".strip() or "lead"
    phrase = f"Inbound call from {name}" if call.direction == 'inbound' else f"Outbound call to {name}"
    outcome_label = dict(CallLog.OUTCOME_CHOICES).get(
        call.outcome, (call.outcome or 'logged').replace('_', ' ').title()
    )
    parts = [phrase, outcome_label]
    if call.outcome == 'connected' and call.duration_seconds:
        minutes, seconds = divmod(int(call.duration_seconds), 60)
        parts.append(f"{minutes}m {seconds:02d}s")
    return " · ".join(parts)


@receiver(post_save, sender=CallLog)
def log_call_activity(sender, instance, created, **kwargs):
    """Mirror every call into the lead's activity timeline.

    One ActivityLog per call: created when the call is logged, then kept in
    sync as the outcome/duration are finalized (e.g. an 'initiated' outbound
    call updated to 'connected' by a telephony webhook).
    """
    if not instance.lead_id:
        return

    from leads.models import ActivityLog

    description = _call_activity_description(instance)
    extra = {
        'call_log_id': instance.id,
        'direction': instance.direction,
        'outcome': instance.outcome,
        'duration_seconds': instance.duration_seconds or 0,
        'recording_url': instance.recording_url or '',
    }

    if created:
        ActivityLog.objects.create(
            activity_type='call_logged',
            description=description,
            actor=instance.user,
            lead_id=instance.lead_id,
            extra=extra,
        )
        return

    # Update the existing activity in place (keeps timestamp at call time).
    log = ActivityLog.objects.filter(
        activity_type='call_logged',
        lead_id=instance.lead_id,
        extra__call_log_id=instance.id,
    ).first()
    if log:
        log.description = description
        log.extra = extra
        if instance.user_id:
            log.actor = instance.user
        log.save(update_fields=['description', 'extra', 'actor'])
    else:
        ActivityLog.objects.create(
            activity_type='call_logged',
            description=description,
            actor=instance.user,
            lead_id=instance.lead_id,
            extra=extra,
        )


# ─── Fire the 'call_logged' automation trigger when a call reaches a final outcome ───

_TERMINAL_CALL_OUTCOMES = {'connected', 'rnr', 'busy', 'cancelled'}


@receiver(pre_save, sender=CallLog)
def _capture_old_call_outcome(sender, instance, **kwargs):
    if instance.pk:
        instance._old_outcome = (
            CallLog.objects.filter(pk=instance.pk).values_list('outcome', flat=True).first()
        )
    else:
        instance._old_outcome = None


@receiver(post_save, sender=CallLog)
def fire_call_automation(sender, instance, created, **kwargs):
    """Fire the automation engine once a call settles on a terminal outcome."""
    if not instance.lead_id:
        return
    old = getattr(instance, '_old_outcome', None)
    outcome = instance.outcome
    if outcome not in _TERMINAL_CALL_OUTCOMES:
        return
    # Fire once: on creation with a terminal outcome, or when it transitions into one.
    if not created and old == outcome:
        return
    try:
        from automations.engine import fire_trigger
        fire_trigger('call_logged', instance.lead, context={
            'call_outcome': outcome,
            'direction': instance.direction,
            'duration_seconds': instance.duration_seconds or 0,
        })
    except Exception:
        # Automations must never break call logging.
        pass

