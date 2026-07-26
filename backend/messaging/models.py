from django.db import models


class WhatsAppMessage(models.Model):
    """Outbox + inbound log for WhatsApp Cloud API messages."""
    DIRECTION = [('out', 'Outbound'), ('in', 'Inbound')]
    KIND = [('text', 'Text'), ('template', 'Template')]
    STATUS = [
        ('pending', 'Pending'),     # queued (bulk) — not yet sent
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),  # webhook delivery receipt
        ('read', 'Read'),            # webhook read receipt
        ('failed', 'Failed'),
        ('received', 'Received'),   # inbound
    ]

    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='whatsapp_messages')
    to_number = models.CharField(max_length=32, blank=True, default='')
    direction = models.CharField(max_length=4, choices=DIRECTION, default='out', db_index=True)
    kind = models.CharField(max_length=10, choices=KIND, default='text')

    text = models.TextField(blank=True, default='')
    template_name = models.CharField(max_length=128, blank=True, default='')
    language = models.CharField(max_length=16, blank=True, default='en_US')
    variables = models.JSONField(default=list, blank=True, help_text='Resolved template body params, in order')

    status = models.CharField(max_length=12, choices=STATUS, default='pending', db_index=True)
    provider_message_id = models.CharField(max_length=128, blank=True, default='')
    error = models.TextField(blank=True, default='')

    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'direction'])]

    def __str__(self):
        return f"WA {self.direction} {self.to_number} ({self.status})"


class EmailMessage(models.Model):
    """Outbox / log for emails the CRM sends.

    Mirrors WhatsAppMessage: every send is recorded with its status so staff can
    see what actually went out to a customer (and why a send failed), instead of
    email being a silent fire-and-forget.
    """
    STATUS = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='email_messages')
    to_email = models.CharField(max_length=254, db_index=True)
    cc = models.CharField(max_length=500, blank=True, default='', help_text="Comma-separated")
    subject = models.CharField(max_length=255, blank=True, default='')
    body = models.TextField(blank=True, default='')

    # What triggered it — a person, an automation rule, or a module action.
    kind = models.CharField(max_length=30, blank=True, default='manual', db_index=True)

    status = models.CharField(max_length=12, choices=STATUS, default='pending', db_index=True)
    error = models.TextField(blank=True, default='')

    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return f"Email to {self.to_email} — {self.subject} ({self.status})"
