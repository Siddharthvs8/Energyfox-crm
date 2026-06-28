from django.db import models
from django.utils import timezone


class ManagerConfig(models.Model):
    """Singleton per tenant — AI Manager configuration."""
    STRATEGY_CHOICES = [
        ('round_robin', 'Round Robin'),
        ('workload_balanced', 'Workload Balanced'),
        ('manual', 'Manual'),
    ]

    assignment_strategy = models.CharField(
        max_length=30, choices=STRATEGY_CHOICES, default='workload_balanced'
    )
    auto_assign_enabled = models.BooleanField(default=True)
    reminder_hour = models.IntegerField(
        default=9,
        help_text="Hour of day (0-23) when daily target reminders are generated"
    )
    morning_meeting_time = models.TimeField(
        default='09:00',
        help_text="Time for the daily morning AI meeting (HH:MM)"
    )
    evening_meeting_time = models.TimeField(
        default='17:30',
        help_text="Time for the daily evening AI meeting (HH:MM)"
    )
    meeting_enabled = models.BooleanField(
        default=True,
        help_text="Enable or disable automated AI meetings"
    )

    LANGUAGE_CHOICES = [
        ('en-US', 'English (United States)'),
        ('en-GB', 'English (United Kingdom)'),
        ('en-IN', 'English (India)'),
        ('es-ES', 'Spanish'),
        ('fr-FR', 'French'),
        ('de-DE', 'German'),
        ('it-IT', 'Italian'),
        ('pt-BR', 'Portuguese (Brazil)'),
        ('hi-IN', 'Hindi'),
        ('ml-IN', 'Malayalam'),
        ('zh-CN', 'Chinese (Simplified)'),
        ('ja-JP', 'Japanese'),
        ('ko-KR', 'Korean'),
        ('ru-RU', 'Russian'),
        ('ar-SA', 'Arabic'),
        ('nl-NL', 'Dutch'),
    ]

    meeting_language = models.CharField(
        max_length=50,
        choices=LANGUAGE_CHOICES,
        default='en-US',
        help_text="Language code for AI meeting STT and TTS (e.g. en-US, es-ES, fr-FR)"
    )
    monthly_popup_interval_hours = models.IntegerField(
        default=24,
        help_text="Interval in hours for monthly target popups"
    )
    daily_popup_interval_hours = models.IntegerField(
        default=3,
        help_text="Interval in hours for daily target popups"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Manager Configuration"
        verbose_name_plural = "AI Manager Configuration"

    def __str__(self):
        return f"AI Manager Config (strategy={self.assignment_strategy})"


class MonthlyTarget(models.Model):
    """Per-agent monthly target set by manager/admin."""
    agent = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='monthly_targets'
    )
    month = models.IntegerField(help_text="1-12")
    year = models.IntegerField()
    target_leads = models.IntegerField(default=0, help_text="Number of leads to convert")
    target_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Revenue target amount"
    )
    target_dialed_calls = models.IntegerField(default=0, help_text="Number of dialed calls target")
    target_call_time = models.IntegerField(default=0, help_text="Call time target in minutes")
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_monthly_targets'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['agent', 'month', 'year']
        ordering = ['-year', '-month']

    def __str__(self):
        return f"{self.agent} — {self.month}/{self.year} (Leads: {self.target_leads}, Amt: {self.target_amount})"


class DailyTarget(models.Model):
    """Auto-generated daily breakdown from MonthlyTarget, excluding holidays."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('achieved', 'Achieved'),
        ('missed', 'Missed'),
    ]

    monthly_target = models.ForeignKey(
        MonthlyTarget, on_delete=models.CASCADE, related_name='daily_targets'
    )
    agent = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='daily_targets'
    )
    date = models.DateField()
    target_leads = models.IntegerField(default=0)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    target_dialed_calls = models.IntegerField(default=0)
    target_call_time = models.IntegerField(default=0)
    
    achieved_dialed_calls = models.IntegerField(default=0)
    achieved_call_time = models.IntegerField(default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_manual = models.BooleanField(default=False, help_text="True if modified manually by a manager")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['agent', 'date']
        ordering = ['date']

    def __str__(self):
        return f"{self.agent} — {self.date} (Leads: {self.target_leads})"


class DailyTargetProof(models.Model):
    """Multiple screenshot proofs uploaded by the employee for a daily target."""
    daily_target = models.ForeignKey(
        DailyTarget, on_delete=models.CASCADE, related_name='proofs'
    )
    file = models.FileField(upload_to='performance_proofs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Proof for {self.daily_target.agent} on {self.daily_target.date}"


class Holiday(models.Model):
    """Manager-defined holidays excluded from daily target splits."""
    date = models.DateField(unique=True)
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.name} ({self.date})"


class Meeting(models.Model):
    """Manager-scheduled meetings with agents."""
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    scheduled_at = models.DateTimeField()
    duration_minutes = models.IntegerField(default=30)
    attendees = models.ManyToManyField(
        'users.User', related_name='ai_meetings', blank=True
    )
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_meetings'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_at']

    def __str__(self):
        return f"{self.title} @ {self.scheduled_at}"


class Notification(models.Model):
    """In-app notifications for agents."""
    TYPE_CHOICES = [
        ('daily_target', 'Daily Target Reminder'),
        ('monthly_target', 'Monthly Target Update'),
        ('meeting', 'Meeting Reminder'),
        ('achievement', 'Achievement'),
        ('general', 'General'),
    ]

    user = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='ai_notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='general')
    is_read = models.BooleanField(default=False)
    is_popup = models.BooleanField(default=False, help_text="True if this notification should block the screen as a popup.")
    popup_shown = models.BooleanField(default=False, help_text="True if the popup has been rendered to the user.")
    extra_data = models.JSONField(default=dict, blank=True, help_text="Stores data for drawing conditional graphics.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.user}"


class AIMeetingSession(models.Model):
    """An individual 1-on-1 AI meeting session between the AI Manager and one agent."""
    SESSION_TYPE_CHOICES = [
        ('morning', 'Morning Meeting'),
        ('evening', 'Evening Meeting'),
        ('ad_hoc', 'Ad-hoc Meet'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
    ]

    agent = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='ai_meeting_sessions'
    )
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    mom = models.TextField(blank=True, default='', help_text="Minutes of Meeting generated by AI")
    mom_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"[{self.session_type}] Meeting with {self.agent} — {self.started_at.date()}"


class AIMeetingMessage(models.Model):
    """A single message in an AI meeting session."""
    SENDER_TYPE_CHOICES = [
        ('ai', 'AI Manager'),
        ('user', 'User'),
    ]

    session = models.ForeignKey(
        AIMeetingSession, on_delete=models.CASCADE, related_name='messages'
    )
    sender_type = models.CharField(max_length=10, choices=SENDER_TYPE_CHOICES)
    sender = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ai_meeting_messages'
    )
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.sender_type}] {self.content[:60]}"
