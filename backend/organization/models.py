from django.db import models


class OrgSettings(models.Model):
    """
    Singleton holding EnergyFox's organization-wide configuration.

    Replaces the per-tenant ``customers.Client`` model from the old multi-tenant
    SaaS. There is exactly one row (pk=1); use :func:`organization.utils.get_org_settings`
    to read it everywhere instead of the old ``connection.tenant``.
    """

    name = models.CharField(max_length=100, default='EnergyFox')
    logo = models.ImageField(upload_to='org/', null=True, blank=True)

    # ── Appearance ──
    # Accent-colour theme for the app chrome (sidebar, buttons, focus rings, accents).
    # Set by the super admin under Settings. Applied via CSS variables on the frontend.
    THEME_CHOICES = [
        ('indigo', 'Indigo'),
        ('violet', 'Violet'),
        ('emerald', 'Emerald'),
        ('rose', 'Rose'),
        ('amber', 'Amber'),
        ('sky', 'Sky'),
    ]
    theme = models.CharField(max_length=20, default='indigo', choices=THEME_CHOICES)

    # ── Voxbay Telephony ──
    voxbay_uid = models.CharField(max_length=255, blank=True, default='')
    voxbay_upin = models.CharField(max_length=255, blank=True, default='')
    voxbay_callerid = models.CharField(max_length=255, blank=True, default='')
    voxbay_api_url = models.CharField(max_length=255, blank=True, default='https://x.voxbay.com')
    voxbay_access_token = models.CharField(max_length=255, blank=True, default='')

    # ── Telephony Selection ──
    telephony_provider = models.CharField(
        max_length=20,
        default='voxbay',
        choices=[('voxbay', 'Voxbay'), ('exotel', 'Exotel')],
    )

    # ── Exotel Telephony ──
    exotel_sid = models.CharField(max_length=255, blank=True, default='')
    exotel_api_key = models.CharField(max_length=255, blank=True, default='')
    exotel_api_token = models.CharField(max_length=255, blank=True, default='')
    exotel_callerid = models.CharField(max_length=255, blank=True, default='')
    exotel_subdomain = models.CharField(max_length=255, blank=True, default='api.exotel.com')

    # ── WhatsApp Cloud API (Meta) ──
    whatsapp_phone_number_id = models.CharField(max_length=64, blank=True, default='')
    whatsapp_access_token = models.TextField(blank=True, default='')
    whatsapp_business_account_id = models.CharField(max_length=64, blank=True, default='')
    whatsapp_verify_token = models.CharField(max_length=128, blank=True, default='')

    # ── Custom Lead Statuses ──
    custom_lead_statuses = models.JSONField(default=list, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Organization Settings'
        verbose_name_plural = 'Organization Settings'

    def __str__(self):
        return self.name or 'Organization Settings'

    def save(self, *args, **kwargs):
        # Enforce the singleton: there is only ever one row, at pk=1.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Return the singleton instance, creating it on first access."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
