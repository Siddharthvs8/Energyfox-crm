from django.db import models
from django.utils import timezone


class AutomationRule(models.Model):
    """
    A trigger → condition → action rule.
    
    `conditions` JSON schema:
        [
            {"field": "source", "operator": "equals", "value": "meta"},
            {"field": "value", "operator": "greater_than", "value": "50000"},
        ]
    
    `actions` JSON schema:
        [
            {"type": "assign_lead", "params": {"user_id": 3}},
            {"type": "change_status", "params": {"status": "positive"}},
            {"type": "create_task", "params": {"title": "Follow up", "priority": "high", "due_days": 2}},
            {"type": "add_to_campaign", "params": {"campaign_id": 1}},
            {"type": "send_webhook", "params": {"url": "https://hooks.slack.com/...", "method": "POST"}},
            {"type": "send_notification", "params": {"user_id": 1, "message": "New high-value lead!"}},
            {"type": "update_field", "params": {"field": "notes", "value": "Auto-qualified"}},
            {"type": "add_note", "params": {"note": "Auto-processed by automation"}},
            {"type": "duplicate_check", "params": {"fields": ["email", "phone"]}},
        ]
    """

    TRIGGER_CHOICES = [
        ('lead_created', 'Lead Created'),
        ('lead_status_changed', 'Lead Status Changed'),
        ('lead_updated', 'Lead Updated'),
        ('task_created', 'Task Created'),
        ('task_completed', 'Task Completed'),
        ('campaign_lead_added', 'Lead Added to Campaign'),
        ('call_logged', 'Call Logged'),
        ('lead_inactive', 'Lead Inactive (no activity)'),
        ('whatsapp_received', 'WhatsApp Reply Received'),
    ]

    LOGIC_CHOICES = [
        ('all', 'ALL conditions must match (AND)'),
        ('any', 'ANY condition must match (OR)'),
    ]

    PRIORITY_CHOICES = [
        (1, 'Critical'),
        (2, 'High'),
        (3, 'Normal'),
        (4, 'Low'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=3)

    trigger_event = models.CharField(max_length=50, choices=TRIGGER_CHOICES)
    # For status-change triggers: optional from/to filter
    trigger_config = models.JSONField(default=dict, blank=True,
        help_text='Extra trigger config, e.g. {"from_status": "new", "to_status": "follow_up"}')

    condition_logic = models.CharField(max_length=5, choices=LOGIC_CHOICES, default='all')
    conditions = models.JSONField(default=list, blank=True)
    actions = models.JSONField(default=list, blank=True)

    # Rate limiting / anti-loop
    max_executions_per_hour = models.IntegerField(default=100,
        help_text='Max times this rule can fire per hour (anti-loop protection)')
    cooldown_seconds = models.IntegerField(default=0,
        help_text='Min seconds between consecutive executions for the same object')

    # Stats
    execution_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)
    last_executed_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='automation_rules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', '-created_at']

    def __str__(self):
        return f"[{'ON' if self.is_active else 'OFF'}] {self.name}"


class AutomationLog(models.Model):
    """Immutable audit log of every automation execution."""

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('partial', 'Partial Success'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped (cooldown/rate-limit)'),
    ]

    rule = models.ForeignKey(AutomationRule, on_delete=models.CASCADE, related_name='logs')
    trigger_event = models.CharField(max_length=50)
    trigger_object_type = models.CharField(max_length=50, default='lead')
    trigger_object_id = models.IntegerField(null=True, blank=True)
    trigger_data = models.JSONField(default=dict, blank=True,
        help_text='Snapshot of the object that triggered the rule')

    conditions_matched = models.BooleanField(default=False)
    actions_executed = models.JSONField(default=list, blank=True,
        help_text='List of {action_type, status, detail}')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    error_message = models.TextField(blank=True, default='')
    execution_time_ms = models.IntegerField(default=0,
        help_text='How long the execution took in milliseconds')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Log #{self.id} — {self.rule.name} — {self.status}"


class ScheduledAction(models.Model):
    """A deferred chunk of a rule's action list, queued by a `wait` step.

    Enables timed multi-step sequences: when the engine hits a `wait` action it
    persists the remaining actions here with a `run_at`, and a periodic command
    (`process_automation_queue`) resumes them once due.
    """
    rule = models.ForeignKey(AutomationRule, on_delete=models.CASCADE, related_name='scheduled_actions')
    trigger_event = models.CharField(max_length=50, default='')
    object_type = models.CharField(max_length=50, default='lead')
    object_id = models.IntegerField()
    remaining_actions = models.JSONField(default=list, help_text='Actions still to run after the wait')
    context = models.JSONField(default=dict, blank=True)

    run_at = models.DateTimeField(db_index=True)
    processed = models.BooleanField(default=False, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['run_at']
        indexes = [models.Index(fields=['processed', 'run_at'])]

    def __str__(self):
        return f"ScheduledAction #{self.id} — rule {self.rule_id} @ {self.run_at:%Y-%m-%d %H:%M}"
