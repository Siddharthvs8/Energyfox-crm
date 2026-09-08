from datetime import timedelta

from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
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

class District(models.Model):
    """A district a lead can belong to, maintained from Settings.

    The lead stores the district's *name*, not a foreign key. District arrives as
    free text — a CSV column, a Meta form answer — and has to be matched against
    this list before it means anything; everything downstream (the filter, the
    export, the CSV template) already reads a name.

    Matching is case-insensitive and settles on the spelling configured here, so
    "KOLLAM", "kollam" and "kollaM" all file under "Kollam". A value that matches
    nothing on this list is not filed at all: the lead is still created, with its
    district left empty, rather than inventing a district nobody configured.
    """
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive districts stop being offered for new leads; "
                  "leads already filed under them keep their district.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            # Case-insensitive: the whole point is that one district has one
            # spelling, so "Kollam" and "kollam" must not both be addable.
            models.UniqueConstraint(Lower('name'), name='uniq_district_name_ci'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = (self.name or '').strip()
        super().save(*args, **kwargs)

    @classmethod
    def lookup(cls):
        """``{lowercased name: configured spelling}`` for matching imports.

        Built once per import rather than queried per row — a 5000-row upload
        would otherwise be 5000 queries to answer the same question.
        """
        return {d.name.strip().lower(): d.name
                for d in cls.objects.filter(is_active=True)}

    @classmethod
    def canonical(cls, value):
        """The configured spelling of `value`, or `''` when it is not one of ours.

        Empty is a deliberate answer, not a failure: an unrecognised district is
        dropped and the lead is filed without one.
        """
        name = (value or '').strip()
        if not name:
            return ''
        match = cls.objects.filter(is_active=True, name__iexact=name).first()
        return match.name if match else ''


class Lead(models.Model):
    # standard python syntax
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    company = models.CharField(max_length=200, blank=True, null=True)  # customer location
    # Coarser than `company`, which holds the place/locality. Kept separate so
    # leads can be grouped and routed by district however the locality is written.
    district = models.CharField(max_length=100, blank=True, default='', db_index=True)
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

    # A value that was never read back, told apart from one that was read back
    # as empty: `assigned_to_id` is legitimately None on an unassigned lead, so
    # None cannot also mean "we don't know".
    _UNREAD = object()

    # Owner as it was when this row was loaded, so save() can tell a hand-off
    # from any other edit. Unread on a row built in memory.
    _loaded_assigned_to_id = _UNREAD
    # Same for the district, so the check below runs on a change rather than on
    # every save of every lead.
    _loaded_district = _UNREAD

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        # Taken out of the row that was actually fetched, never off the
        # instance. Reading a deferred attribute here sends Django back to the
        # database for it, which builds another Lead, which lands back in this
        # method — a recursion with no bottom. It took out every query that
        # narrows its columns: the whole of Company Performance answered 500,
        # and the fix elsewhere was to stop using .only(), which treated the
        # symptom. `field_names` is exactly the columns that came back, so a
        # narrowed query simply leaves these unread.
        loaded = dict(zip(field_names, values))
        obj._loaded_assigned_to_id = loaded.get('assigned_to_id', cls._UNREAD)
        obj._loaded_district = loaded.get('district', cls._UNREAD)
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

        The district is settled here too. Both importers already matched it
        against the configured list, but every other way in — the API, the
        admin, a shell, whatever gets written next — could file any text at all,
        and a lead arrived from Meta reading "Payyanur.kannur", which is a place
        and a district run together and names no district anybody set up.
        Doing it here makes the rule true however the lead is written rather
        than true wherever someone remembered to call the helper.
        """
        # An unread value means this row came back without the column, so there
        # is nothing to compare against and nothing to correct.
        district_changed = (self._loaded_district is not self._UNREAD
                            and self.district != self._loaded_district)
        if self.district and (self._state.adding or district_changed):
            # Settles on the configured spelling, and empties anything that is
            # not one of ours — see District.canonical.
            self.district = District.canonical(self.district)

        owner = self.assigned_to if self.assigned_to_id else None
        role = getattr(owner, 'role', '') if owner else ''
        owner_changed = self._state.adding or (
            self._loaded_assigned_to_id is not self._UNREAD
            and self.assigned_to_id != self._loaded_assigned_to_id)
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
        self._loaded_district = self.district

    def __str__(self):
        # `last_name` is nullable, so a customer with only a first name used to
        # print as "Asha None" — on the activity log, in the admin, and in every
        # notification that names a lead.
        return ' '.join(part for part in (self.first_name, self.last_name) if part)


class SiteVisit(models.Model):
    """Solar site-survey details captured for a lead during a site visit."""

    YES_NO = [('yes', 'Yes'), ('no', 'No')]

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='site_visit')
    site_visit_complete = models.BooleanField(default=False)

    # ── Deal ──
    # What the customer is quoted, and what came off it. The lead's `value` — the
    # figure every report and the whole accounts stage read — is derived from
    # these two and never typed directly, so a deal value can always be explained
    # by the price and the discount that produced it. See LeadViewSet.site_visit.
    product_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

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

class LeadNote(models.Model):
    """One note on a lead, carrying who wrote it.

    Notes were one text field the whole team appended to. That made them
    anonymous, and anonymous notes cannot be edited safely: letting someone
    correct their own words would have meant letting them rewrite everyone
    else's. A row per note fixes that — the author is recorded, so a BDE can add
    notes and tidy their own without touching a colleague's.

    `Lead.notes` is kept in step as the joined-up text, because the lead list,
    the CSV export and the edit form all read the lead's notes as one blob. This
    model is the record; that field is the rendering of it.
    """
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='note_entries')
    body = models.TextField()
    # Null for the notes that predate this model — the old blob was split into
    # rows and there is nobody to attribute them to. Only the admin tier may
    # edit those.
    author = models.ForeignKey('users.User', on_delete=models.SET_NULL,
                               null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"note on lead {self.lead_id}"

    def save(self, *args, **kwargs):
        self.body = (self.body or '').strip()
        super().save(*args, **kwargs)

    def may_be_edited_by(self, user):
        """Your own words, or an admin's prerogative.

        A note is a record of what someone said; letting a colleague rewrite it
        would make the timeline untrustworthy. The admin tier keeps the override
        because someone has to be able to remove what should not have been
        written — and because the notes carried over from the old blob have no
        author to claim them.
        """
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_spectator', False):
            return False
        if self.author_id and self.author_id == user.id:
            return True
        return bool(user.is_staff or getattr(user, 'is_general_manager', False))


def resync_lead_notes(lead):
    """Rewrite `Lead.notes` from this lead's note rows.

    One blob, blank-line separated, exactly as the field held before — so every
    screen that reads it (the list, the export, the edit form) carries on
    unchanged while the rows underneath become the real record.
    """
    joined = '\n\n'.join(n.body for n in lead.note_entries.all() if n.body)
    if (lead.notes or '') != joined:
        lead.notes = joined
        lead.save(update_fields=['notes'])
    return joined


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
    # The staff member's own sign-off that the MNRE portal submission is done —
    # the uploads alone don't prove it was filed. Required before Stage 1 can be
    # completed, alongside the documents and the plant capacity.
    mnre_completed = models.BooleanField(default=False)

    # ── For Loan ──
    loan_above_2_lakh = models.BooleanField(default=False)
    # The bank's answer, which lands well after the paperwork goes in — usually
    # after this stage has been signed off and locked. It is therefore written
    # by its own action (`loan-sanctioned`) rather than by the stage form, and
    # is the only thing on a locked Stage 1 that can still change.
    loan_sanctioned = models.BooleanField(default=False)
    loan_sanctioned_at = models.DateTimeField(null=True, blank=True)

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
        if not self.mnre_completed:
            missing.append('mnre_completed')
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
    panel_delivered = models.CharField(max_length=15, choices=DELIVERY, blank=True, default='')
    structure_material = models.CharField(max_length=15, choices=DELIVERY, blank=True, default='')
    bom = models.CharField(max_length=15, choices=DELIVERY, blank=True, default='')
    pending_item = models.CharField(max_length=3, choices=YES_NO, blank=True, default='')
    remark = models.TextField(blank=True, default='')

    is_complete = models.BooleanField(default=False, db_index=True)
    # Set when an admin completed this despite the conditions not being met, so
    # the exception is visible afterwards rather than looking like a clean pass.
    completed_with_override = models.BooleanField(default=False)
    override_reason = models.CharField(max_length=255, blank=True, default='')
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_purchase_logistics')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # What each field has to read before this stage can be signed off. Answering
    # them is not enough — the goods have to have actually arrived.
    COMPLETION_RULES = (
        ('panel_delivered', 'delivered', 'Panel delivered'),
        ('structure_material', 'delivered', 'Structure material delivered'),
        ('bom', 'delivered', 'BOM delivered'),
        ('pending_item', 'no', 'No pending item'),
    )

    def unmet_conditions(self):
        """Which completion conditions this record does not yet satisfy.

        Returns [(field, label)] — empty when everything has arrived and nothing
        is outstanding, which is the only state that completes without an
        admin override.
        """
        return [(field, label) for field, wanted, label in self.COMPLETION_RULES
                if getattr(self, field, '') != wanted]

    def missing_required_fields(self):
        """Kept for callers that only ask "is it ready?"."""
        return [field for field, _label in self.unmet_conditions()]

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

    # ── The 20-day installation deadline ──
    # The clock starts the day accounts first records money against the lead,
    # partial payment or full. Miss it and the project drops out of the pending
    # queue into Overdue, where only a super admin can touch it.
    #
    # A super admin releases it by granting a fresh deadline: the row goes back
    # to the project team with a date to work to, so a release restores the work
    # without discarding the discipline. Overdue is derived from these dates
    # rather than stored, so nothing has to run on a schedule to keep it true.
    DEADLINE_DAYS = 20

    extended_deadline = models.DateField(
        null=True, blank=True,
        help_text="New deadline granted when a super admin released this from Overdue")
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='released_projects')
    release_reason = models.CharField(max_length=255, blank=True, default='')

    @property
    def payment_started_on(self):
        """The date accounts first took money for this lead, or None.

        Whichever came first: the receipt for the verification payment, the
        verification itself for leads predating receipts, or the earliest
        balance payment.
        """
        lead = self.lead
        dates = []
        # ``.all()`` rather than ``.filter()`` so a prefetched list is used as-is;
        # the project queue reads this for every row.
        receipts = [r.date for r in lead.receipt_vouchers.all() if r.is_initial and r.date]
        if receipts:
            dates.append(min(receipts))
        pv = getattr(lead, 'payment_verification', None)
        if pv and (pv.amount_received or 0) > 0:
            when = pv.completed_at or pv.created_at
            if when:
                dates.append(timezone.localdate(when))
        balances = [b.created_at for b in lead.balance_payments.all() if b.created_at]
        if balances:
            dates.append(timezone.localdate(min(balances)))
        return min(dates) if dates else None

    @property
    def deadline_date(self):
        """The day this has to be finished by — None until accounts is paid."""
        if self.extended_deadline:
            return self.extended_deadline
        started = self.payment_started_on
        if not started:
            return None
        from datetime import timedelta
        return started + timedelta(days=self.DEADLINE_DAYS)

    @property
    def days_to_deadline(self):
        """Days left; negative once the deadline has passed. None without one."""
        due = self.deadline_date
        return (due - timezone.localdate()).days if due else None

    @property
    def is_overdue(self):
        """Past its deadline and still unfinished — locked to super admins."""
        if self.is_complete:
            return False
        due = self.deadline_date
        return bool(due and timezone.localdate() > due)

    def default_extension(self):
        """The deadline a release grants unless the super admin names another."""
        from datetime import timedelta
        return timezone.localdate() + timedelta(days=self.DEADLINE_DAYS)

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
    # Stamped when the approval comes in, for the same reason as the subsidy
    # stamp below: the customer's tracking page shows the day the board approved
    # rather than a bare tick. Cleared if the answer later moves off 'yes', so a
    # re-approval is dated when it actually happened.
    discom_approval_at = models.DateTimeField(null=True, blank=True)
    subsidy_requested = models.BooleanField(default=False)   # when discom approved
    # Stamped when the claim is filed, so the customer's tracking page can show
    # the date rather than a bare tick.
    subsidy_requested_at = models.DateTimeField(null=True, blank=True)
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

    # The document slots on this record; see LiasoningDocument. Both are
    # evidence the sign-off rests on, so both are required before it.
    PLANT_PHOTO = 'plant_commissioned'
    RF_IMAGE = 'rf_image'
    PHOTO_SLOTS = [
        (PLANT_PHOTO, 'Plant Photo'),
        (RF_IMAGE, 'RF Image'),
    ]

    is_complete = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_liasoning_service')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def has_plant_photo(self):
        """Whether the commissioned plant has been photographed. Liasoning waits
        on it — the sign-off says the plant is live, so it needs the evidence."""
        return self.documents.filter(doc_type=self.PLANT_PHOTO).exists()

    @property
    def has_rf_image(self):
        """Whether the RF image is on file. Required alongside the plant photo."""
        return self.documents.filter(doc_type=self.RF_IMAGE).exists()

    @property
    def photos_complete(self):
        """Both required photos are in. Until then the record cannot be signed
        off — the sign-off asserts what these two pictures are the evidence
        for, so it must not be possible to give it without them."""
        present = set(self.documents.filter(
            doc_type__in=[self.PLANT_PHOTO, self.RF_IMAGE]
        ).values_list('doc_type', flat=True))
        return present >= {self.PLANT_PHOTO, self.RF_IMAGE}

    def __str__(self):
        return f"Liasoning & Service — {self.lead}"


class LiasoningDocument(models.Model):
    """A photo or file attached to a liasoning record.

    The commissioned-plant photo is the evidence the installation is actually
    live, so liasoning cannot be signed off without one — see
    LiasoningService.PLANT_PHOTO and complete_liasoning.
    """
    liasoning = models.ForeignKey(LiasoningService, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=40, db_index=True)
    file = models.FileField(upload_to='liasoning/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return f"{self.doc_type} — {self.liasoning_id}"


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

    # How far ahead a visit starts calling for attention. The officer is told the
    # day before it is due, not on the day, so the trip can be arranged. Both the
    # sidebar count and the upcoming list read this, so the badge, the pop-up and
    # the list can never disagree about what counts as due.
    REMINDER_LEAD_DAYS = 1

    plan = models.ForeignKey(PeriodicMaintenance, on_delete=models.CASCADE, related_name='visits')
    sequence = models.PositiveIntegerField()
    due_date = models.DateField()
    # A visit can be moved — the customer is away, the weather is against it. The
    # date it was originally due is kept so the slip is visible rather than the
    # schedule quietly rewriting itself; set once, on the first move.
    original_due_date = models.DateField(null=True, blank=True)
    reschedule_reason = models.CharField(max_length=255, blank=True, default='')

    # ── Readings / checks ──
    # Every reading is typed and photographed; the photos live in
    # MaintenanceVisitDocument, several per slot.
    dc_voltage = models.CharField(max_length=60, blank=True, default='')
    dc_floating_voltage = models.CharField(max_length=60, blank=True, default='')
    structure_damage = models.CharField(max_length=255, blank=True, default='',
                                        help_text="Structure damage, deformity or rust")
    inverter_cleaned = models.BooleanField(default=False)
    ac_ne_voltage = models.CharField(max_length=60, blank=True, default='')   # N-E
    ac_pn_voltage = models.CharField(max_length=60, blank=True, default='')   # P-N
    ac_pe_voltage = models.CharField(max_length=60, blank=True, default='')   # P-E
    monthly_production = models.CharField(max_length=60, blank=True, default='')
    error_codes = models.CharField(max_length=255, blank=True, default='')

    # Photo slots (MaintenanceVisitDocument.doc_type), in the order the form
    # lays them out. The picture-only slots are evidence of the wash, of what
    # the plant was producing either side of it, and of the cleaned inverter —
    # there is no number to type for those, only the photograph.
    PICTURE_ONLY_SLOTS = [
        ('panel_before', 'Panel Before'),
        ('panel_after', 'Panel After'),
        ('production_before', 'Production Before Service'),
        ('production_after', 'Production After Service'),
        ('inverter_cleaned', 'Inverter Cleaned'),
    ]
    READING_SLOTS = [
        ('dc_voltage', 'DC Voltage'),
        ('dc_floating_voltage', 'DC Floating Voltages'),
        ('error_codes', 'Error Codes'),
        ('structure_damage', 'Structure Damage'),
        ('monthly_production', 'Monthly Production'),
        ('ac_ne', 'N-E Voltage'),
        ('ac_pn', 'P-N'),
        ('ac_pe', 'P-E'),
    ]
    PHOTO_SLOTS = PICTURE_ONLY_SLOTS + READING_SLOTS

    is_complete = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='completed_maintenance_visits')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence']

    @property
    def is_rescheduled(self):
        return self.original_due_date is not None and self.original_due_date != self.due_date

    def __str__(self):
        return f"Visit {self.sequence} — {self.plan.lead}"


class EmergencyService(models.Model):
    """Emergency Service — urgent service visits logged by the liasoning officer.
    Each entry records the service done plus the electrical readings taken on
    site: DC voltage and floating voltage, inverter error codes, the AC voltages
    (N-E / P-N / P-E) and the plant's monthly production, along with the panel
    wash and production photos taken either side of the visit."""
    customer_name = models.CharField(max_length=255, blank=True, default='')
    service = models.TextField(blank=True, default='')
    remarks = models.CharField(max_length=255, blank=True, default='')
    dc_voltage = models.CharField(max_length=60, blank=True, default='')
    dc_floating_voltage = models.CharField(max_length=60, blank=True, default='')
    error_codes = models.CharField(max_length=255, blank=True, default='')
    # ── AC voltage readings ──
    # Every reading is typed *and* photographed: the number is what gets
    # reported, the meter shots are the evidence. Photos live in
    # EmergencyServiceDocument, several per reading.
    ac_ne_voltage = models.CharField(max_length=60, blank=True, default='')   # N-E
    ac_pn_voltage = models.CharField(max_length=60, blank=True, default='')   # P-N
    ac_pe_voltage = models.CharField(max_length=60, blank=True, default='')   # P-E
    monthly_production = models.CharField(max_length=60, blank=True, default='')

    # ── Service condition ──
    # What was found wrong and what was swapped out. Each is a single pick and
    # optional — plenty of visits find nothing on one side, or replace nothing.
    DC_SIDE_CHOICES = [
        ('inverter_damage', 'Inverter damage'),
        ('dc_fuse_damage', 'DC fuse damage'),
        ('dc_mcb_damage', 'DC MCB damage'),
        ('dc_box_burned', 'DC box burned'),
        ('dc_spd_damage', 'DC SPD damage'),
    ]
    AC_SIDE_CHOICES = [
        ('ac_spd_damage', 'AC SPD damage'),
        ('ac_mcb_isolator_damage', 'AC MCB / isolator damage'),
        ('generation_meter_faulty', 'Generation meter faulty / burned'),
        ('termination_point_damage', 'Termination point damage'),
    ]
    REPLACEMENT_CHOICES = [
        ('inverter', 'Inverter'),
        ('panel', 'Panel'),
        ('dc_db', 'DC DB'),
        ('ac_db', 'AC DB'),
        ('dc_db_components', 'DC DB components'),
        ('ac_db_components', 'AC DB components'),
    ]
    # Photo slots (EmergencyServiceDocument.doc_type), in the order the form
    # lays them out. Every reading on the entry can carry several shots.
    # The picture-only slots are the panel wash and what the plant was making
    # either side of the visit — there is no number to type for those, only the
    # photograph.
    PICTURE_ONLY_SLOTS = [
        ('panel_before', 'Panel Wash — Before'),
        ('panel_after', 'Panel Wash — After'),
        ('production_before', 'Production Before Service'),
        ('production_after', 'Production After Service'),
    ]
    READING_SLOTS = [
        ('dc_voltage', 'DC Voltage'),
        ('dc_floating_voltage', 'DC Floating Voltages'),
        ('error_codes', 'Error Codes'),
        ('monthly_production', 'Monthly Production'),
        ('ac_ne', 'N-E Voltage'),
        ('ac_pn', 'P-N'),
        ('ac_pe', 'P-E'),
    ]
    PHOTO_SLOTS = PICTURE_ONLY_SLOTS + READING_SLOTS

    dc_side_condition = models.CharField(max_length=40, blank=True, default='', choices=DC_SIDE_CHOICES)
    ac_side_condition = models.CharField(max_length=40, blank=True, default='', choices=AC_SIDE_CHOICES)
    replacement = models.CharField(max_length=40, blank=True, default='', choices=REPLACEMENT_CHOICES)

    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_emergency_services')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Emergency service — {self.customer_name}"


class EmergencyServiceDocument(models.Model):
    """A photo attached to one reading on an emergency service entry.

    Several per reading: a meter is often shot twice, and a burned board needs
    more than one angle.
    """
    entry = models.ForeignKey(EmergencyService, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=40, db_index=True)
    file = models.FileField(upload_to='emergency-service/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return f"{self.doc_type} — {self.entry_id}"


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


class MaintenanceVisitDocument(models.Model):
    """A photo attached to one slot on a maintenance visit.

    Several per slot: a panel is photographed from more than one angle, and a
    meter is often shot twice.
    """
    visit = models.ForeignKey(MaintenanceVisit, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=40, db_index=True)
    file = models.FileField(upload_to='maintenance/photos/')
    uploaded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at', 'id']

    def __str__(self):
        return f"{self.doc_type} — {self.visit_id}"


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


class TrackingLink(models.Model):
    """A customer's own view of where their installation has got to.

    Handed out once documentation clears, as a link with an unguessable token in
    it — the customer opens it and sees the stages, the way a parcel is tracked.
    There is no login: asking a homeowner to hold an account for one job would
    mean nobody ever looks, and the link is the credential.

    That makes the token the whole of the security, so it is long and random
    (`secrets.token_urlsafe`, 32 bytes) rather than anything derived from the
    lead — a sequential id in the URL would let anyone walk the customer list.
    What the page shows is deliberately thin: stage names and dates, never
    money, staff names or internal notes. See `TrackingLinkView`.
    """
    # Long enough that guessing is hopeless, short enough to paste into WhatsApp.
    TOKEN_BYTES = 32
    # How long the link keeps working after the journey is finished. The customer
    # may well come back to it for a while — a warranty question, their own
    # records — but a link that lives for ever in an old email is a customer's
    # details reachable for ever.
    LIVES_FOR_DAYS_AFTER_COMPLETION = 90

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name='tracking_link')
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    # Switched off by hand when a link has gone somewhere it should not have.
    revoked = models.BooleanField(default=False)
    # Whether the customer ever opened it, which is the only way to know the
    # address was right and the mail arrived.
    view_count = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'tracking link'

    def __str__(self):
        return f'Tracking for lead #{self.lead_id}'

    @staticmethod
    def new_token():
        import secrets
        return secrets.token_urlsafe(TrackingLink.TOKEN_BYTES)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.new_token()
        super().save(*args, **kwargs)

    @property
    def expires_at(self):
        """When the link stops working, or None while the job is still running.

        Measured from the job being finished rather than from the day the link
        was made: a job that takes eight months should not go dark halfway
        through, which is exactly when the customer is most likely to look.

        "Finished" is the *last* stage the customer is shown, not the
        installation. Their page runs on past it to the subsidy claim and the
        warranty, and a link timed from the installation date could close while
        those were still outstanding — leaving the customer with no way to see
        the two things they most want a record of.
        """
        stamps = [getattr(getattr(self.lead, attr, None), 'completed_at', None)
                  for attr in ('project', 'documentation_stage2', 'warranty')]
        stamps = [s for s in stamps if s]
        # The installation is the gate: nothing after it can finish first, and
        # while it is open the job is plainly still running.
        project_done = getattr(getattr(self.lead, 'project', None), 'completed_at', None)
        if not project_done:
            return None
        return max(stamps) + timedelta(days=self.LIVES_FOR_DAYS_AFTER_COMPLETION)

    @property
    def is_live(self):
        if self.revoked:
            return False
        expires = self.expires_at
        return expires is None or timezone.now() < expires
