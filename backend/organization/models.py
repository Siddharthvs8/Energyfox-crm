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

    # ── Email (SMTP) ──
    # Configured from Settings like the WhatsApp integration, so email doesn't
    # depend on server env vars. Blank host ⇒ fall back to the EMAIL_* env
    # settings (and then to Django's console backend in dev).
    email_host = models.CharField(max_length=255, blank=True, default='')
    email_port = models.IntegerField(default=587)
    email_use_tls = models.BooleanField(default=True)
    email_use_ssl = models.BooleanField(default=False)
    email_host_user = models.CharField(max_length=255, blank=True, default='')
    email_host_password = models.CharField(max_length=255, blank=True, default='')
    email_from_name = models.CharField(max_length=120, blank=True, default='EnergyFox')
    email_from_address = models.EmailField(blank=True, default='')
    email_signature = models.TextField(
        blank=True, default='',
        help_text="Appended to outgoing emails sent from the CRM")
    # An optional richer signature — logo, links, formatting — used for the HTML
    # part of the message. The plain-text one above is still sent alongside it, so
    # a client that refuses HTML is never left with nothing.
    email_signature_html = models.TextField(
        blank=True, default='',
        help_text="Optional HTML signature; the plain one above is still sent as the text part")

    # ── B2B (wholesale) email + WhatsApp ──
    # The wholesale side trades under its own identity: its proforma invoices and
    # dispatch invoices go out from this account and this number rather than the
    # retail ones. Leave a field blank and that channel falls back to the shared
    # settings above, so switching B2B on is opt-in per credential.
    b2b_email_host = models.CharField(max_length=255, blank=True, default='')
    b2b_email_port = models.IntegerField(default=587)
    b2b_email_use_tls = models.BooleanField(default=True)
    b2b_email_use_ssl = models.BooleanField(default=False)
    b2b_email_host_user = models.CharField(max_length=255, blank=True, default='')
    b2b_email_host_password = models.CharField(max_length=255, blank=True, default='')
    b2b_email_from_name = models.CharField(max_length=120, blank=True, default='')
    b2b_email_from_address = models.EmailField(blank=True, default='')
    b2b_email_signature = models.TextField(
        blank=True, default='',
        help_text="Appended to outgoing B2B emails; blank uses the shared signature")
    b2b_email_signature_html = models.TextField(
        blank=True, default='',
        help_text="Optional HTML signature for B2B mail; blank uses the shared one")

    b2b_whatsapp_phone_number_id = models.CharField(max_length=64, blank=True, default='')
    b2b_whatsapp_access_token = models.TextField(blank=True, default='')
    b2b_whatsapp_business_account_id = models.CharField(max_length=64, blank=True, default='')

    # ── Custom Lead Statuses ──
    custom_lead_statuses = models.JSONField(default=list, blank=True)

    # ── Warranty certificate (fixed details printed on the generated document) ──
    # These are not entered per customer — the warranty form only takes the
    # customer/system details; everything below comes from here.
    warranty_company_name = models.CharField(max_length=120, blank=True, default='Energyfox Consultants Pvt. Ltd.')
    warranty_cin = models.CharField(max_length=40, blank=True, default='U35105KL2023PTC084535')
    warranty_gst = models.CharField(max_length=40, blank=True, default='32AAHCE8716F1ZR')
    warranty_director_name = models.CharField(max_length=80, blank=True, default='AKASH AG')
    warranty_director_designation = models.CharField(max_length=80, blank=True, default='Director')
    warranty_panel_years = models.CharField(max_length=10, blank=True, default='30')
    warranty_inverter_years = models.CharField(max_length=10, blank=True, default='12')
    warranty_service_years = models.CharField(max_length=10, blank=True, default='5')
    warranty_signature = models.ImageField(upload_to='org/', null=True, blank=True)
    warranty_seal = models.ImageField(upload_to='org/', null=True, blank=True)

    # ── Money-receipt voucher (company + bank details printed on receipts) ──
    receipt_address = models.CharField(
        max_length=255, blank=True,
        default='4th Floor, TC Number 15/4257/2, Malankara Avenue, Pattom, Thiruvananthapuram')
    receipt_phone = models.CharField(max_length=40, blank=True, default='9526 396 823')
    receipt_website = models.CharField(max_length=80, blank=True, default='energyfox.in')
    receipt_email = models.CharField(max_length=80, blank=True, default='info@energyfox.in')
    receipt_bank_name = models.CharField(max_length=80, blank=True, default='SBI')
    receipt_bank_account = models.CharField(max_length=40, blank=True, default='44600460447')
    receipt_bank_ifsc = models.CharField(max_length=20, blank=True, default='SBIN0071176')
    receipt_bank_branch = models.CharField(max_length=80, blank=True, default='PULIYARAKONAM')

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


class InventoryDocumentProfile(models.Model):
    """The letterhead and sign-off printed on the inventory documents.

    Retail and wholesale trade under their own identity — different address,
    registration numbers, bank and seal — so each side keeps its own profile and
    the documents read from the one that raised them: the B2C proforma from
    'b2c', and the wholesale proforma, dispatch invoice and purchase order from
    'b2b'.

    A blank field falls back to the organisation's own settings, so a side that
    has not been filled in still prints exactly what it printed before.
    """
    B2C, B2B = 'b2c', 'b2b'
    SIDE_CHOICES = [(B2C, 'B2C (retail)'), (B2B, 'B2B (wholesale)')]

    side = models.CharField(max_length=3, choices=SIDE_CHOICES, unique=True, db_index=True)

    # ── Letterhead ──
    company_name = models.CharField(max_length=120, blank=True, default='')
    address = models.CharField(max_length=255, blank=True, default='')
    phone = models.CharField(max_length=40, blank=True, default='')
    email = models.CharField(max_length=80, blank=True, default='')
    gst = models.CharField(max_length=40, blank=True, default='')
    cin = models.CharField(max_length=40, blank=True, default='')
    # Blank derives it from the GSTIN, whose middle ten characters are the PAN.
    pan = models.CharField(max_length=20, blank=True, default='')

    # ── Artwork ──
    logo = models.ImageField(upload_to='documents/', null=True, blank=True)
    signature = models.ImageField(upload_to='documents/', null=True, blank=True)
    seal = models.ImageField(upload_to='documents/', null=True, blank=True)

    # ── Bank block (printed on the proforma / invoice) ──
    bank_name = models.CharField(max_length=80, blank=True, default='')
    bank_account_name = models.CharField(max_length=120, blank=True, default='')
    bank_account_number = models.CharField(max_length=40, blank=True, default='')
    bank_ifsc = models.CharField(max_length=20, blank=True, default='')
    bank_branch = models.CharField(max_length=80, blank=True, default='')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['side']
        verbose_name = 'Inventory Document Profile'

    def __str__(self):
        return f"{self.get_side_display()} document profile"

    @classmethod
    def load(cls, side):
        """The profile for a side, created on first access."""
        obj, _ = cls.objects.get_or_create(side=side)
        return obj

    def resolved(self, org):
        """What the document actually prints: this profile's value where it has one,
        the organisation's own settings where it doesn't."""
        gst = self.gst or org.warranty_gst or ''
        return {
            'name': self.company_name or org.warranty_company_name,
            'address': self.address or org.receipt_address,
            'phone': self.phone or org.receipt_phone,
            'email': self.email or org.receipt_email,
            'gst': gst,
            'cin': self.cin or org.warranty_cin,
            'pan': self.pan or gst[2:12],
            'logo': self.logo or org.logo,
            'signature': self.signature or org.warranty_signature,
            'seal': self.seal or org.warranty_seal,
            'bank': {
                'name': self.bank_name or org.receipt_bank_name,
                'account_name': self.bank_account_name or org.warranty_company_name,
                'account_number': self.bank_account_number or org.receipt_bank_account,
                'ifsc': self.bank_ifsc or org.receipt_bank_ifsc,
                'branch': self.bank_branch or org.receipt_bank_branch,
            },
        }
