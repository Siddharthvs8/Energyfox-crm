from django.db import models


class WhatsAppMessage(models.Model):
    """Outbox + inbound log for WhatsApp Cloud API messages."""
    DIRECTION = [('out', 'Outbound'), ('in', 'Inbound')]
    KIND = [('text', 'Text'), ('template', 'Template')]
    STATUS = [
        ('pending', 'Pending'),   # queued (bulk) — not yet sent
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('received', 'Received'),  # inbound
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
