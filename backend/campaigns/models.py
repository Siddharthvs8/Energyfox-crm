from django.db import models
from django.utils import timezone

class Campaign(models.Model):
    TYPE_CHOICES = [
        ('conference', 'Conference'),
        ('webinar', 'Webinar'),
        ('trade_show', 'Trade Show'),
        ('public_relations', 'Public Relations'),
        ('partners', 'Partners'),
        ('referral_program', 'Referral Program'),
        ('advertisement', 'Advertisement'),
        ('banner_ads', 'Banner Ads'),
        ('direct_mail', 'Direct Mail'),
        ('email', 'Email'),
        ('telemarketing', 'Telemarketing'),
        ('others', 'Others'),
    ]

    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('completed', 'Completed'),
    ]

    name = models.CharField(max_length=255)
    campaign_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default='email')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='planning')
    
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    expected_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    budgeted_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    actual_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    expected_response = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Percentage")
    number_sent = models.IntegerField(default=0)
    
    description = models.TextField(blank=True, null=True)
    
    leads = models.ManyToManyField(
        'leads.Lead',
        related_name='campaigns_set',
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']
