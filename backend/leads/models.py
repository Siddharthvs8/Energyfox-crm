from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

class Product(models.Model):
    name = models.CharField(max_length=255)
    default_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    # Inventory / stock tracking
    sku = models.CharField(max_length=60, blank=True, default='', db_index=True)
    unit = models.CharField(max_length=20, blank=True, default='unit')
    hsn = models.CharField(max_length=20, blank=True, default='', verbose_name='HSN / SAC',
                           help_text='Printed against this product on the proforma invoice')
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    # Decimal, not integer: stock is counted in metres of cable and fractions of
    # a set as often as in whole panels, and an integer field silently truncated
    # every fraction that passed through it.
    stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
    # The tele caller who worked this lead, remembered separately from the current
    # owner. Handing a lead to a BDE moves `assigned_to`, and without this the
    # lead would vanish from the tele caller's list the moment they passed it on.
    tele_caller = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tele_caller_leads',
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
    # ── Purchase & Logistics handoff (after payment verification completes) ──
    pushed_to_purchase = models.BooleanField(default=False, db_index=True)
    pushed_to_purchase_at = models.DateTimeField(null=True, blank=True)
    purchase_staff = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_leads',
        help_text="Purchase & logistics staff handling this lead's procurement",
    )
    # ── Project / installation handoff (after purchase & logistics completes) ──
    pushed_to_project = models.BooleanField(default=False, db_index=True)
    pushed_to_project_at = models.DateTimeField(null=True, blank=True)
    project_manager = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_leads',
        help_text="Project manager handling this lead's installation",
    )
    # ── Post-installation fan-out (set in parallel when the project completes) ──
    # Documentation Stage 2 (documentation team) and the Liasoning & Service module
    # (liasoning officer) both receive the lead at the same time.
    pushed_to_doc_stage2 = models.BooleanField(default=False, db_index=True)
    pushed_to_doc_stage2_at = models.DateTimeField(null=True, blank=True)
    # Stage 2 lands with the documentation manager, who assigns it to a staff
    # member — separately from Stage 1, so the two stages can be split up.
    doc_stage2_staff = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='doc_stage2_leads',
        help_text="Documentation staff handling this lead's Stage 2 paperwork",
    )
    pushed_to_liasoning = models.BooleanField(default=False, db_index=True)
    pushed_to_liasoning_at = models.DateTimeField(null=True, blank=True)
    pushed_to_warranty = models.BooleanField(default=False, db_index=True)
    pushed_to_warranty_at = models.DateTimeField(null=True, blank=True)
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
        ('interested', 'Interested'),
        ('not_interested', 'Not Interested'),
        ('converted', 'Converted'),
    ]
    status = models.CharField(max_length=30, choices=status_choices, default='new', db_index=True)
    status_changed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    invoice = models.FileField(upload_to='invoices/', null=True, blank=True)

    # ── Lost (a converted deal that fell through — customer skipped/backed out) ──
    is_lost = models.BooleanField(default=False, db_index=True)
    lost_at = models.DateTimeField(null=True, blank=True)
    lost_reason = models.CharField(max_length=255, blank=True, default='')
    lost_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='marked_lost_leads')

    # ── Trash (soft delete) — deleting a lead moves it here; anything trashed
    #    longer than TRASH_RETENTION_DAYS is purged permanently. ──
    TRASH_RETENTION_DAYS = 7
    is_trashed = models.BooleanField(default=False, db_index=True)
    trashed_at = models.DateTimeField(null=True, blank=True)
    trashed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='trashed_leads')

    # ── Archive — terminal, old leads (lost / not interested / fully completed)
    #    are moved out of the hot working set so the active lists and dashboards
    #    stay fast as history accumulates. Archived leads are never deleted; they
    #    are viewable via the Archived filter. Auto-archived by the
    #    `archive_old_leads` command; see Lead.ARCHIVE_AFTER_MONTHS. ──
    ARCHIVE_AFTER_MONTHS = 3
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Composite indexes for the hot query paths — the active leads list
        # (exclude trashed/archived, order by created) and the per-owner and
        # per-status filters. Keeps new-data queries fast as the table grows.
        indexes = [
            models.Index(fields=['is_trashed', 'is_archived', '-created_at'],
                         name='lead_active_recent_idx'),
            models.Index(fields=['is_archived', 'status', '-created_at'],
                         name='lead_status_recent_idx'),
            models.Index(fields=['assigned_to', 'is_archived'],
                         name='lead_owner_active_idx'),
            models.Index(fields=['bde', 'is_archived'],
                         name='lead_bde_active_idx'),
        ]

    # Fulfilment pipeline stages (the module a lead is currently in), most-advanced
    # first. Derived from the pushed_to_* handoff flags.
    PIPELINE_STAGES = [
        ('project', 'Project'),
        ('purchase', 'Purchase & Logistics'),
        ('accounts', 'Accounts'),
        ('documentation', 'Documentation S1'),
        ('site_visit', 'Site Visit'),
        ('tele_caller', 'Tele Caller'),
    ]
    PIPELINE_STAGE_LABELS = dict(PIPELINE_STAGES)

    @property
    def pipeline_stage(self):
        """The module/stage this lead is currently in (furthest reached)."""
        if self.pushed_to_project:
            return 'project'
        if self.pushed_to_purchase:
            return 'purchase'
        if self.pushed_to_accounts:
            return 'accounts'
        if self.pushed_to_documentation:
            return 'documentation'
        if self.bde_id:
            return 'site_visit'
        return 'tele_caller'

    # Owner as it was when this row was loaded, so save() can tell a hand-off
    # from any other edit. None on a row built in memory.
    _loaded_assigned_to_id = None

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        obj._loaded_assigned_to_id = obj.assigned_to_id
        return obj

    def save(self, *args, **kwargs):
        """Keep the two ownership roles in step with the current owner.

        Handing a lead to someone *is* the assignment: giving it to a tele caller
        records them as the tele caller, giving it to a BDE records them as the
        BDE. Without the BDE half, a lead assigned to a BDE through the owner
        field left `bde` empty and could never be marked Converted.

        The tele caller stamp is sticky, so ownership ends up shared: the tele
        caller who worked the lead keeps sight of it after handing it on.

        The BDE stamp is not sticky — it names whoever is working the lead now.
        Handing a lead from one BDE to another has to take it out of the first
        one's list, and a sticky stamp left it visible to both of them.

        That re-stamp only fires when the owner actually changes. The lead list
        matches on `bde`, so the field has to follow a hand-off, but re-stamping
        on every save would undo `assign-bde`, which deliberately names a BDE
        other than the owner.

        Bulk paths use queryset.update() and skip save(), so they stamp these
        themselves — see LeadViewSet._stamp_owner_role.
        """
        owner = self.assigned_to if self.assigned_to_id else None
        role = getattr(owner, 'role', '') if owner else ''
        owner_changed = self._state.adding or self.assigned_to_id != self._loaded_assigned_to_id
        stamped = []
        if role == 'tele_caller' and not self.tele_caller_id:
            self.tele_caller_id = owner.id
            stamped.append('tele_caller')
        elif role == 'bde' and (owner_changed or not self.bde_id) and self.bde_id != owner.id:
            self.bde_id = owner.id
            stamped.append('bde')
        if stamped:
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = list(update_fields) + stamped
        super().save(*args, **kwargs)
        self._loaded_assigned_to_id = self.assigned_to_id

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
    # KSEB consumer numbers are digits and never run past 15 of them; the
    # length is capped here so a mistyped meter reading can't be saved as one.
    consumer_number = models.CharField(
        max_length=15, blank=True, default='',
        validators=[RegexValidator(r'^\d{0,15}$',
                                   'Consumer number must be digits only, up to 15.')])
    current_bill = models.CharField(max_length=120, blank=True, default='')
    phase = models.CharField(max_length=10, choices=[('1ph', '1 Phase'), ('3ph', '3 Phase')], blank=True, default='')
    building_height = models.CharField(max_length=120, blank=True, default='')
    panel_to_inverter_distance = models.CharField(max_length=120, blank=True, default='')
    earthing = models.CharField(max_length=120, blank=True, default='')
    kseb_bill = models.CharField(max_length=120, blank=True, default='')
    kseb_section = models.CharField(max_length=120, blank=True, default='')
    feasible_capacity = models.CharField(max_length=120, blank=True, default='')
    # Capacity of the plant to be installed. Flows on to Documentation Stage 1's
    # MNRE plant capacity and from there into the generated documents.
    plant_capacity = models.CharField(max_length=120, blank=True, default='')
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
    lightning_conductor_length = models.CharField(max_length=60, blank=True, default='')

    # ── Earthing / anchoring ──
    EARTHING_SURFACES = [('soil', 'Soil'), ('concrete', 'Concrete'),
                         ('tile', 'Tile'), ('interlock', 'Interlock')]
    earthing_surface = models.CharField(max_length=20, choices=EARTHING_SURFACES,
                                        blank=True, default='')
    anchoring_allowed = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')

    # ── Customer documents (yes/no flags + uploads) ──
    name_change = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    loan = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    # Loan amount the customer needs. Above ₹2 lakh an ITR report is required.
    loan_amount = models.CharField(max_length=60, blank=True, default='')
    load_enhancement = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    email_linked_to_itr = models.CharField(max_length=254, blank=True, default='')

    # ── Purchase order & KSEB feasibility (BDE, handled after push to documentation) ──
    # Once the PO is signed, KSEB feasibility must be taken; if not, it's due 2 days
    # after PO signing and the BDE gets a reminder notification. On completion the
    # PO + feasibility dates reflect into the lead's accounts payment verification.
    po_signed_date = models.DateField(null=True, blank=True, help_text="Date the purchase order was signed")
    kseb_feasibility_taken = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    kseb_feasibility_date = models.DateField(null=True, blank=True, help_text="Date KSEB feasibility was taken")
    kseb_feasibility_complete = models.BooleanField(default=False)

    # Document & photo uploads now live in the related SiteVisitDocument model
    # (multiple files per slot, keyed by doc_type).

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def kseb_feasibility_due_date(self):
        """If the PO is signed, KSEB feasibility is due 2 days after signing."""
        if self.po_signed_date:
            from datetime import timedelta
            return self.po_signed_date + timedelta(days=2)
        return None

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

    # ── Loan Enhancement checkboxes (superseded by the file slots of the same
    #    name; kept so historical records keep their answers) ──
    le_test_cum_completion_report = models.BooleanField(default=False)
    le_sketch = models.BooleanField(default=False)

    # ── Section sign-off ──
    # The Name Change and Load Enhancement sections are completed first; the
    # MNRE / Loan sections only open once the applicable ones are signed off.
    name_change_completed = models.BooleanField(default=False)
    name_change_completed_at = models.DateTimeField(null=True, blank=True)
    load_enhancement_completed = models.BooleanField(default=False)
    load_enhancement_completed_at = models.DateTimeField(null=True, blank=True)

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
        ('loan', 'Loan'),
    ]
    # Modes that need a UTR / transaction reference. Cash has none, and a loan
    # disbursement is evidenced by the sanction rather than a transaction id.
    UTR_MODES = ('cheque', 'card', 'upi')

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='payment_verification')
    amount_received = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODES, blank=True, default='')
    utr_details = models.CharField(max_length=255, blank=True, default='')
    on_account_of = models.CharField(
        max_length=255, blank=True, default='',
        help_text="What the payment is for — printed on the receipt (e.g. '10 kW Margin Money')")
    discount_given_by = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Authorised personnel who approved the discount")
    remarks = models.TextField(blank=True, default='',
                               help_text="Free notes on this payment, for accounts' own record")

    # ── Registration fee (RF) tracking ──
    # RF is due 30 days from the KSEB feasibility date; a reminder fires on day 29,
    # and accounts can push the remittance task to the service department.
    po_date = models.DateField(null=True, blank=True)
    kseb_feasibility_date = models.DateField(null=True, blank=True)
    rf_pushed_to_service = models.BooleanField(default=False)
    rf_pushed_at = models.DateTimeField(null=True, blank=True)

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

    @property
    def rf_due_date(self):
        """Registration fee is due 30 days from the KSEB feasibility date."""
        if self.kseb_feasibility_date:
            from datetime import timedelta
            return self.kseb_feasibility_date + timedelta(days=30)
        return None

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


class BalancePayment(models.Model):
    """A balance / installment payment collected against a lead after its initial
    payment verification is complete, until the full deal value is received.

    Each row is a ledger entry; the running total is added to the lead's
    ``PaymentVerification.amount_received`` so the derived balance always reflects
    what's still due. Once the balance reaches zero the lead is 'fully paid'."""
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='balance_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PaymentVerification.PAYMENT_MODES, blank=True, default='')
    utr_details = models.CharField(max_length=255, blank=True, default='')
    on_account_of = models.CharField(
        max_length=255, blank=True, default='',
        help_text="What the payment is for — printed on the receipt")
    note = models.CharField(max_length=255, blank=True, default='')
    recorded_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_balance_payments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"Balance payment {self.amount} — {self.lead}"


class PurchaseLogistics(models.Model):
    """Purchase & logistics stage, filled by purchase staff once a lead's payment
    is verified by the accounts team.

    Tracks delivery of the mounting structure material and the BOM (bill of
    materials), whether any item is still pending, and a free-text remark.
    """
    DELIVERY = [('delivered', 'Delivered'), ('not_delivered', 'Not Delivered')]
    YES_NO = [('yes', 'Yes'), ('no', 'No')]

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='purchase_logistics')
    structure_material = models.CharField(max_length=15, choices=DELIVERY, blank=True, default='')
    bom = models.CharField(max_length=15, choices=DELIVERY, blank=True, default='')
    pending_item = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    remark = models.TextField(blank=True, default='')

    is_complete = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_purchase_logistics')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def missing_required_fields(self):
        """Structure material and BOM delivery status must be answered before
        the purchase & logistics stage can be marked complete."""
        missing = []
        if not self.structure_material:
            missing.append('structure_material')
        if not self.bom:
            missing.append('bom')
        return missing

    def __str__(self):
        return f"Purchase & logistics — {self.lead}"


class Project(models.Model):
    """Installation project stage, handled by the project manager once a lead's
    purchase & logistics is complete.

    Tracks the structure-work and electrical-work dates, the site's pending
    status, and the geotagged installation photos (see ProjectDocument).
    """
    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='project')

    # ── Structure work ──
    structure_work_start_date = models.DateField(null=True, blank=True)
    structure_work_completed_date = models.DateField(null=True, blank=True)
    # ── Electrical work ──
    electrical_work_start_date = models.DateField(null=True, blank=True)
    electrical_work_completed_date = models.DateField(null=True, blank=True)
    # ── Pending site ──
    site_name = models.CharField(max_length=255, blank=True, default='')
    pending_remark = models.TextField(blank=True, default='')

    is_complete = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Geotagged installation photo slots (ProjectDocument.doc_type), in display order.
    PHOTO_SLOTS = [
        ('panel_serial_numbers', 'Panel Serial Numbers'),
        ('inverter_sn', 'Inverter SN'),
        ('generation_meter', 'Generation Meter'),
        ('plant_photo', 'Plant Photo'),
        ('customer_with_inverter', 'Customer with Inverter'),
        ('la', 'LA (Lightning Arrestor)'),
    ]

    def __str__(self):
        return f"Project — {self.lead}"


class ProjectDocument(models.Model):
    """A single geotagged installation photo for a Project slot. ``doc_type`` is
    one of Project.PHOTO_SLOTS; each slot can hold multiple files."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=40, db_index=True)
    file = models.FileField(upload_to='projects/photos/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return f"{self.doc_type} — {self.project_id}"


class DocumentationStage2(models.Model):
    """Documentation Stage 2 — a separate documentation queue the lead enters (in
    parallel with Liasoning & Service) once its installation project is complete.

    Three tasks:
      1. Completion docs / Annexure 3 — the set of documents given to KSEB,
         prepared right after the project uploads the installation photos.
      2. MNRE Stage 2 — the pmsuryaghar portal; the discom approval decides the
         next step (approved → subsidy request; not approved → route to the
         liasoning officer at the concerned section).
      3. Warranty — sent to the customer via mail & WhatsApp.
    """
    MNRE_PORTAL_URL = 'https://consumer.pmsuryaghar.gov.in/consumer/#/login'
    DISCOM_CHOICES = [('pending', 'Pending'), ('yes', 'Approved'), ('no', 'Not Approved')]

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='documentation_stage2')

    # ── 1. Completion docs / Annexure 3 (documents uploaded via DocumentationStage2Document) ──
    annexure3_completed = models.BooleanField(default=False)
    annexure3_remark = models.CharField(max_length=255, blank=True, default='')
    # Completion-doc forms, each filled via a pop-up under the Annexure 3 section.
    completion_letterhead = models.JSONField(default=dict, blank=True)
    customer_details = models.JSONField(default=dict, blank=True)
    inverter_panel_details = models.JSONField(default=dict, blank=True)

    # ── 2. MNRE Stage 2 (discom approval) ──
    discom_approval = models.CharField(max_length=10, choices=DISCOM_CHOICES, blank=True, default='pending')
    subsidy_requested = models.BooleanField(default=False)   # when discom approved
    sent_to_liasoning = models.BooleanField(default=False)   # when not approved → concerned section
    mnre_remark = models.CharField(max_length=255, blank=True, default='')

    is_complete = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_doc_stage2')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Document slots (DocumentationStage2Document.doc_type), in display order.
    DOC_SLOTS = [
        ('annexure3', 'Annexure 3 (KSEB completion docs)'),
    ]

    def __str__(self):
        return f"Documentation Stage 2 — {self.lead}"


class Warranty(models.Model):
    """Warranty — a standalone documentation module the lead enters (in parallel
    with Documentation Stage 2 & Liasoning) once its installation project is
    complete. The warranty is sent to the customer via WhatsApp / email, and the
    warranty document(s) are attached here."""
    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='warranty')

    sent = models.BooleanField(default=False)   # sent to customer (WhatsApp / email)
    remark = models.CharField(max_length=255, blank=True, default='')

    # Warranty certificate form (customer/system details filled per lead; the
    # fixed company details come from organization.OrgSettings). Keys: system_type,
    # capacity_kw, customer_name, panel_make, inverter_make, panel_warranty_years,
    # inverter_warranty_years, installation_date, site_address.
    form_data = models.JSONField(default=dict, blank=True)

    is_complete = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_warranties')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    DOC_SLOTS = [
        ('warranty', 'Warranty Document'),
    ]

    def __str__(self):
        return f"Warranty — {self.lead}"


class WarrantyDocument(models.Model):
    """A single uploaded warranty document. Each slot can hold multiple files."""
    warranty = models.ForeignKey(Warranty, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=40, db_index=True)
    file = models.FileField(upload_to='warranty/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return f"{self.doc_type} — {self.warranty_id}"


class DocumentationStage2Document(models.Model):
    """A single uploaded file for a Documentation Stage 2 slot (e.g. 'annexure3').
    Each slot can hold multiple files."""
    stage2 = models.ForeignKey(DocumentationStage2, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=40, db_index=True)
    file = models.FileField(upload_to='documentation/stage2/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return f"{self.doc_type} — {self.stage2_id}"


class LiasoningService(models.Model):
    """Liasoning & Service — a combined module handled by the liasoning officer.
    The lead enters it (in parallel with Documentation Stage 2) once its
    installation project is complete.

    The Liasoning sub-module tracks two stages per customer:
      1. Feasibility — completed/not + remarks.
      2. Annexure 3 (completion doc submission at KSEB) — completed/not, remarks
         and the discom approval. These write through to Documentation Stage 2,
         whose Annexure 3 status is "fetched from liasoning".
    """
    DISCOM_CHOICES = [('pending', 'Pending'), ('yes', 'Approved'), ('no', 'Not Approved')]

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='liasoning_service')

    # ── Stage 1: Feasibility ──
    feasibility_completed = models.BooleanField(default=False)
    feasibility_remark = models.CharField(max_length=255, blank=True, default='')

    # ── Stage 2: Annexure 3 (completion doc submission) ──
    annexure3_completed = models.BooleanField(default=False)
    annexure3_remark = models.CharField(max_length=255, blank=True, default='')
    discom_approval = models.CharField(max_length=10, choices=DISCOM_CHOICES, blank=True, default='pending')

    is_complete = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_liasoning_service')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Liasoning & Service — {self.lead}"


class ServiceEntry(models.Model):
    """A scheduled service entry, managed by the project manager. A standalone
    list (not tied to a lead) — the customer is referenced by typed name/id."""
    customer_name = models.CharField(max_length=255, blank=True, default='')
    customer_id = models.CharField(max_length=120, blank=True, default='')
    scheduled_date = models.DateField(null=True, blank=True)
    assigned_to = models.CharField(max_length=255, blank=True, default='')
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_service_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_date', '-created_at']

    def __str__(self):
        return f"Service — {self.customer_name} ({self.scheduled_date})"


class PeriodicMaintenance(models.Model):
    """Periodic maintenance plan for a customer — scheduled once their subsidy is
    redeemed / work completed: 5 years of visits with a tenure gap of 6 months
    (10 scheduled visits)."""
    VISIT_COUNT = 10
    GAP_MONTHS = 6

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='periodic_maintenance')
    start_date = models.DateField()
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_maintenance_plans')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Periodic maintenance — {self.lead}"


class MaintenanceVisit(models.Model):
    """A single scheduled maintenance visit with the on-site readings and the
    panel-wash before/after photos."""
    plan = models.ForeignKey(PeriodicMaintenance, on_delete=models.CASCADE, related_name='visits')
    sequence = models.PositiveIntegerField()
    due_date = models.DateField()

    # ── Readings / checks ──
    dc_voltage = models.CharField(max_length=60, blank=True, default='')
    structure_damage = models.CharField(max_length=255, blank=True, default='',
                                        help_text="Structure damage, deformity or rust")
    inverter_cleaned = models.BooleanField(default=False)
    ac_ne_voltage = models.CharField(max_length=60, blank=True, default='')   # N-E
    ac_pn_voltage = models.CharField(max_length=60, blank=True, default='')   # P-N
    ac_pe_voltage = models.CharField(max_length=60, blank=True, default='')   # P-E
    monthly_production = models.CharField(max_length=60, blank=True, default='')
    error_codes = models.CharField(max_length=255, blank=True, default='')

    # ── Photos: panel washed before and after ──
    panel_before = models.FileField(upload_to='maintenance/photos/', null=True, blank=True)
    panel_after = models.FileField(upload_to='maintenance/photos/', null=True, blank=True)

    is_complete = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='completed_maintenance_visits')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"Visit {self.sequence} — {self.plan.lead}"


class EmergencyService(models.Model):
    """Emergency Service — urgent service visits logged by the liasoning officer.
    Each entry records the service done plus the electrical readings taken on
    site: DC voltage, inverter error codes, the AC voltages (N-E / P-N / P-E)
    and the plant's monthly production."""
    customer_name = models.CharField(max_length=255, blank=True, default='')
    service = models.TextField(blank=True, default='')
    remarks = models.CharField(max_length=255, blank=True, default='')
    dc_voltage = models.CharField(max_length=60, blank=True, default='')
    error_codes = models.CharField(max_length=255, blank=True, default='')
    # ── AC voltage readings ──
    ac_ne_voltage = models.CharField(max_length=60, blank=True, default='')   # N-E
    ac_pn_voltage = models.CharField(max_length=60, blank=True, default='')   # P-N
    ac_pe_voltage = models.CharField(max_length=60, blank=True, default='')   # P-E
    monthly_production = models.CharField(max_length=60, blank=True, default='')

    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_emergency_services')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Emergency service — {self.customer_name}"


class TeamStatsConfig(models.Model):
    """Singleton config for the Team Stats module — just the manually-set team
    lead names for the structure and electrical teams. The completion counts
    themselves are derived from Project work dates."""
    structure_team_lead = models.CharField(max_length=255, blank=True, default='')
    electrical_team_lead = models.CharField(max_length=255, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj

    def __str__(self):
        return "Team stats config"


class ReceiptVoucher(models.Model):
    """An auto-generated money receipt for a payment collected by accounts.

    One voucher per payment: the initial amount received (at payment
    verification) and each later balance payment each get their own. The number
    is sequential per financial year — ER/<fy>/<seq>, e.g. ER/26-27/073. Snapshot
    fields (name/address/amount in words) are stored so a reprinted receipt never
    changes even if the lead is later edited.
    """
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='receipt_vouchers')
    # Optional link to the balance payment that produced it (the initial receipt
    # has none — it belongs to the payment verification).
    balance_payment = models.OneToOneField(
        BalancePayment, on_delete=models.CASCADE, null=True, blank=True, related_name='receipt')
    is_initial = models.BooleanField(default=False, help_text="Receipt for the first (verification) payment")

    number = models.CharField(max_length=40, unique=True, db_index=True)   # ER/26-27/073
    fy = models.CharField(max_length=10, db_index=True)                     # 26-27
    seq = models.IntegerField()

    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_in_words = models.CharField(max_length=255, blank=True, default='')
    on_account_of = models.CharField(max_length=255, blank=True, default='')
    payment_mode = models.CharField(max_length=20, blank=True, default='')

    received_from = models.CharField(max_length=255, blank=True, default='')   # snapshot
    address = models.TextField(blank=True, default='')                         # snapshot

    # The rendered receipt, stored when it is first sent so email can attach it
    # and WhatsApp can link to it — the Cloud API fetches documents by URL.
    pdf = models.FileField(upload_to='receipts/', null=True, blank=True)

    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        unique_together = [('fy', 'seq')]

    def __str__(self):
        return f"{self.number} — {self.received_from} ({self.amount})"


class ModuleSeen(models.Model):
    """Which customers a user has already opened in a given module.

    Drives the sidebar badges: a module's count is the work still waiting on the
    user *that they haven't looked at yet*, so opening a customer clears it from
    the indicator. One row per (user, module, lead); `seen_at` is refreshed on
    every visit.
    """
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='module_views')
    module = models.CharField(max_length=40, db_index=True)   # e.g. 'documentation-stage2'
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='module_views')
    seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('user', 'module', 'lead')]
        indexes = [models.Index(fields=['user', 'module'])]

    def __str__(self):
        return f"{self.user_id} saw lead {self.lead_id} in {self.module}"
