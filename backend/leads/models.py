from django.db import models
from django.utils import timezone

class Product(models.Model):
    name = models.CharField(max_length=255)
    default_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    # Inventory / stock tracking
    sku = models.CharField(max_length=60, blank=True, default='', db_index=True)
    unit = models.CharField(max_length=20, blank=True, default='unit')
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    stock_quantity = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def low_stock(self):
        return self.stock_quantity <= self.reorder_level

    def __str__(self):
        return self.name

class Lead(models.Model):
    # standard python syntax
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    company = models.CharField(max_length=200, blank=True, null=True)  # customer location
    installation_location = models.CharField(max_length=255, blank=True, default='', help_text="Where the solar system will be installed")

    # Meta Integration
    source = models.CharField(max_length=50, default='manual', db_index=True) # e.g. "meta_ads"
    meta_lead_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    meta_campaign_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="Meta Ads campaign ID")
    meta_campaign_name = models.CharField(max_length=255, blank=True, null=True, db_index=True, help_text="Meta Ads campaign name")
    meta_integration = models.ForeignKey(
        'IntegrationSettings',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leads',
        help_text="Which Meta integration (branch account) this lead came from",
    )
    assigned_to = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_leads',
        help_text="Tele caller handling this lead",
    )
    bde = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bde_leads',
        help_text="BDE assigned for the site visit",
    )
    # ── Documentation handoff ──
    pushed_to_documentation = models.BooleanField(default=False, db_index=True)
    pushed_to_documentation_at = models.DateTimeField(null=True, blank=True)
    documentation_staff = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documentation_leads',
        help_text="Documentation staff handling this lead's paperwork",
    )
    # ── Accounts handoff (after Documentation Stage 1 completes) ──
    pushed_to_accounts = models.BooleanField(default=False, db_index=True)
    pushed_to_accounts_at = models.DateTimeField(null=True, blank=True)
    accounts_staff = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accounts_leads',
        help_text="Accounts staff verifying this lead's payment",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leads'
    )
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True, null=True)
    
    status_choices = [
        ('new', 'New'),
        ('follow_up', 'Follow up'),
        ('positive', 'Positive'),
        ('enrolled', 'Enrolled'),
        ('not_interested', 'Not Interested'),
        ('disqualified', 'Disqualified'),
        ('prospect', 'Prospect'),
        ('interested_to_join', 'Interested to Join'),
        ('may_buy_later', 'MayBuyLater'),
        ('demo_booked', 'Demo Booked'),
        ('demo_done', 'Demo Done'),
        ('demo_rescheduled', 'Demo Rescheduled'),
        ('demo_canceled', 'Demo Canceled'),
        ('dnp', 'DNP'),
        ('partially_paid', 'Partially Paid'),
    ]
    status = models.CharField(max_length=30, choices=status_choices, default='new', db_index=True)
    status_changed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    invoice = models.FileField(upload_to='invoices/', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class SiteVisit(models.Model):
    """Solar site-survey details captured for a lead during a site visit."""

    YES_NO = [('yes', 'Yes'), ('no', 'No')]

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='site_visit')
    site_visit_complete = models.BooleanField(default=False)

    # ── Roof ──
    ROOF_TYPES = [('rcc', 'RCC'), ('sheet', 'Sheet'), ('mixed', 'Mixed')]
    roof_type = models.CharField(max_length=10, choices=ROOF_TYPES, blank=True, default='')
    # Sub-types shown when roof_type is RCC — multiple allowed.
    # Values from: flat, slope, tiled, non_linear
    rcc_roof_types = models.JSONField(default=list, blank=True)

    # ── Electrical / supply ──
    connection_type = models.CharField(max_length=120, blank=True, default='')  # commercial / residential
    connected_load = models.CharField(max_length=120, blank=True, default='')
    consumer_number = models.CharField(max_length=120, blank=True, default='')
    current_bill = models.CharField(max_length=120, blank=True, default='')
    phase = models.CharField(max_length=10, choices=[('1ph', '1 Phase'), ('3ph', '3 Phase')], blank=True, default='')
    building_height = models.CharField(max_length=120, blank=True, default='')
    panel_to_inverter_distance = models.CharField(max_length=120, blank=True, default='')
    earthing = models.CharField(max_length=120, blank=True, default='')
    kseb_bill = models.CharField(max_length=120, blank=True, default='')
    kseb_section = models.CharField(max_length=120, blank=True, default='')
    feasible_capacity = models.CharField(max_length=120, blank=True, default='')
    transformer_feasibility = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    neutral_link = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')

    # ── Roof access / structure ──
    roof_access = models.CharField(max_length=120, blank=True, default='')
    parapet_height = models.CharField(max_length=120, blank=True, default='')
    structure_type = models.CharField(max_length=20, choices=[('table_top', 'Table top'), ('custom', 'Custom')], blank=True, default='')
    custom_structure_height = models.CharField(max_length=120, blank=True, default='')

    # ── Cabling requirements (in meters) ──
    cable_panel_to_dc_db = models.CharField(max_length=60, blank=True, default='')
    cable_inverter_to_ac_db = models.CharField(max_length=60, blank=True, default='')
    earthing_cable_length = models.CharField(max_length=60, blank=True, default='')

    # ── Earthing / anchoring ──
    earthing_surface = models.CharField(max_length=120, blank=True, default='')
    anchoring_allowed = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')

    # ── Customer documents (yes/no flags + uploads) ──
    name_change = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    loan = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    load_enhancement = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    email_linked_to_itr = models.CharField(max_length=254, blank=True, default='')

    # Document & photo uploads now live in the related SiteVisitDocument model
    # (multiple files per slot, keyed by doc_type).

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Site visit — {self.lead}"


class SiteVisitDocument(models.Model):
    """A single uploaded file for a site-visit document/photo slot.

    Replaces the old one-FileField-per-slot design so each slot (KSEB Bill,
    Aadhaar, Meter Box photo, …) can hold multiple files. ``doc_type`` matches
    the legacy field name (e.g. 'aadhaar_card', 'photo_meterbox') so the
    documentation team's labels carry over unchanged.
    """
    site_visit = models.ForeignKey(SiteVisit, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=40, db_index=True)
    file = models.FileField(upload_to='site_visit/docs/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return f"{self.doc_type} — {self.site_visit_id}"


class LeadDocument(models.Model):
    """A customer document shared across every stage of a lead.

    Entered once (typically by the BDE during the site visit) and inherited by
    every same-``kind`` slot in later stages (e.g. Documentation Stage 1's MNRE
    and Loan Aadhaar slots). There is a single underlying file, so anyone with
    edit access to a stage that shows the slot can view / change / delete it —
    letting a wrong upload be corrected downstream. ``kind`` is a canonical value
    from ``document_kinds.SHARED_KIND_LABELS`` (e.g. 'aadhaar', 'pan').
    """
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='shared_documents')
    kind = models.CharField(max_length=40, db_index=True)
    file = models.FileField(upload_to='lead_documents/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return f"{self.kind} — lead {self.lead_id}"


class IntegrationSettings(models.Model):
    """A named Meta (Facebook/Instagram) Lead Ads integration.

    EnergyFox runs multiple Meta accounts (one per branch), so there can be
    many of these — each with its own name, page, and credentials. Incoming
    webhook leads are routed to an integration by Facebook Page ID.
    """
    name = models.CharField(max_length=120, blank=True, default='', help_text="Friendly name, e.g. the branch this Meta account belongs to")

    # Meta (Facebook/Instagram) Integration
    meta_verify_token = models.CharField(max_length=255, blank=True, null=True, help_text="Token expected from Meta webhook validation")
    meta_access_token = models.TextField(blank=True, null=True, help_text="Page Access Token for retrieving lead data")
    meta_page_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="Facebook Page ID — used to route incoming webhook leads to this integration")
    meta_form_id = models.CharField(max_length=100, blank=True, null=True, help_text="Optional Lead Form ID used for manual Meta lead sync")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Meta Integration"
        verbose_name_plural = "Meta Integrations"
        ordering = ['name', 'id']

    def __str__(self):
        return self.name or f"Meta Integration #{self.pk}"


class ActivityLog(models.Model):
    ACTIVITY_TYPES = [
        ('lead_created', 'Lead Created'),
        ('lead_status_change', 'Lead Status Changed'),
        ('note_added', 'Note Added'),
        ('task_created', 'Task Created'),
        ('task_stage_change', 'Task Stage Changed'),
        ('task_completed', 'Task Completed'),
        ('meta_import', 'Meta Import'),
        ('user_joined', 'User Joined'),
        ('call_logged', 'Call Logged'),
    ]

    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES, db_index=True)
    description = models.TextField()
    actor = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs'
    )
    lead = models.ForeignKey(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs'
    )
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.activity_type} at {self.created_at}"

class LeadAttachment(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='lead_attachments/')
    file_name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file_name or self.file.name


class DocumentationStage1(models.Model):
    """Stage-1 documentation paperwork, filled by the assigned documentation staff.

    Four sections whose visibility is driven by the BDE's site-visit answers
    (``SiteVisit.name_change`` / ``SiteVisit.loan``):
      - Name Change       — shown when name_change == 'yes'
      - Loan Enhancement  — shown when loan == 'yes'
      - For MNRE          — always shown, mandatory before completion
      - For Loan          — shown when loan == 'yes'
    Most fields are document uploads; a few are checkboxes / a text input.
    """

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='documentation_stage1')

    # Document uploads live in the related DocumentationStage1Document model
    # (multiple files per slot, keyed by doc_type). Only the non-file inputs stay here.

    # ── Loan Enhancement checkboxes (visible when site_visit.loan == 'yes') ──
    le_test_cum_completion_report = models.BooleanField(default=False)
    le_sketch = models.BooleanField(default=False)

    # ── For MNRE (always shown, mandatory) ──
    mnre_plant_capacity = models.CharField(max_length=120, blank=True, default='')

    # ── For Loan ──
    loan_above_2_lakh = models.BooleanField(default=False)

    # ── Completion tracking ──
    is_complete = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_documentation_stage1',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Mandatory before completion (the MNRE section). KYC = aadhaar + pan + passbook.
    # Each of these doc_type slots must have at least one uploaded file:
    REQUIRED_DOC_TYPES = [
        'mnre_aadhaar', 'mnre_pan', 'mnre_passbook', 'mnre_purchase_order', 'mnre_kseb_bill',
    ]

    def missing_mandatory_fields(self):
        """Mandatory MNRE doc-type slots (and plant capacity) not yet provided.

        Shared-kind slots (Aadhaar/PAN/Passbook/KSEB bill) are satisfied by the
        lead's shared document pool; only stage-local slots (the purchase-order
        PDF) live on this record's own documents.
        """
        from .document_kinds import SLOT_TO_KIND
        local_present = set(self.documents.values_list('doc_type', flat=True))
        shared_kinds = set(self.lead.shared_documents.values_list('kind', flat=True))
        missing = []
        for dt in self.REQUIRED_DOC_TYPES:
            kind = SLOT_TO_KIND.get(dt)
            present = (kind in shared_kinds) if kind else (dt in local_present)
            if not present:
                missing.append(dt)
        if not (self.mnre_plant_capacity or '').strip():
            missing.append('mnre_plant_capacity')
        return missing

    def __str__(self):
        return f"Documentation Stage 1 — {self.lead}"


class DocumentationStage1Document(models.Model):
    """A single uploaded file for a Documentation Stage 1 slot.

    ``doc_type`` matches the legacy field name (e.g. 'mnre_aadhaar',
    'loan_agreement_purchase_order') so labels and conditional sections carry
    over. Each slot can hold multiple files.
    """
    stage1 = models.ForeignKey(DocumentationStage1, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=40, db_index=True)
    file = models.FileField(upload_to='documentation/stage1/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return f"{self.doc_type} — {self.stage1_id}"


class PaymentVerification(models.Model):
    """Accounts-stage payment verification, filled by accounts staff once a lead's
    Documentation Stage 1 is complete.

    The deal value is the lead's ``value`` (set earlier in the sales/BDE stage).
    Accounts records how much was received, any discount and who authorised it,
    the payment mode, and — for non-cash modes — the UTR / transaction reference.
    The balance still due is derived: deal value − amount received − discount.
    """
    PAYMENT_MODES = [
        ('cash', 'Cash'), ('cheque', 'Cheque'), ('card', 'Card'), ('upi', 'UPI'),
    ]
    # Modes that need a UTR / transaction reference (everything except cash).
    UTR_MODES = ('cheque', 'card', 'upi')

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='payment_verification')
    amount_received = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODES, blank=True, default='')
    utr_details = models.CharField(max_length=255, blank=True, default='')
    discount_given_by = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Authorised personnel who approved the discount")

    is_complete = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_payment_verifications')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def deal_value(self):
        return self.lead.value or 0

    @property
    def balance_amount(self):
        """Deal value − amount received − discount (what's still to be received)."""
        from decimal import Decimal
        deal = self.lead.value or Decimal('0')
        return deal - (self.amount_received or Decimal('0')) - (self.discount_value or Decimal('0'))

    def missing_required_fields(self):
        """What's still needed before this can be marked verified/complete."""
        missing = []
        if not self.payment_mode:
            missing.append('payment_mode')
        if self.payment_mode in self.UTR_MODES and not (self.utr_details or '').strip():
            missing.append('utr_details')
        return missing

    def __str__(self):
        return f"Payment verification — {self.lead}"
