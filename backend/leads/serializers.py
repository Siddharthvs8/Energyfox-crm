from rest_framework import serializers
from django.utils import timezone
from .models import Lead, District, IntegrationSettings, LeadAttachment, Product, SiteVisit, DocumentationStage1, SiteVisitDocument, DocumentationStage1Document, PaymentVerification, PurchaseLogistics, Project, ProjectDocument, ServiceEntry, TeamStatsConfig, BalancePayment, DocumentationStage2, DocumentationStage2Document, LiasoningService, LiasoningDocument, Warranty, WarrantyDocument, EmergencyService, EmergencyServiceDocument, PeriodicMaintenance, MaintenanceVisit, MaintenanceVisitDocument
from .document_kinds import SLOT_TO_KIND, SITE_VISIT_SHARED_SLOTS, DOC_STAGE1_SHARED_SLOTS, shared_doc_entries

from users.serializers import UserSerializer


def _merge_documents(stage_obj, shared_slots):
    """Documents shown for a stage: its own stage-local files + the lead's shared
    customer documents projected onto every matching slot of that stage."""
    local = [
        {'id': d.id, 'doc_type': d.doc_type,
         'file': d.file.url if d.file else None,
         'uploaded_at': d.uploaded_at, 'shared': False}
        for d in stage_obj.documents.all() if d.doc_type not in SLOT_TO_KIND
    ]
    return local + shared_doc_entries(stage_obj.lead, shared_slots)

class LeadAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_size_kb = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = LeadAttachment
        fields = ['id', 'file', 'file_url', 'file_name', 'uploaded_by_name', 'uploaded_at', 'file_size_kb']
        
    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip() or obj.uploaded_by.username
        return "Unknown"
        
    def get_file_size_kb(self, obj):
        try:
            return round(obj.file.size / 1024, 1)
        except Exception:
            return 0
            
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'


class DistrictSerializer(serializers.ModelSerializer):
    lead_count = serializers.SerializerMethodField()

    class Meta:
        model = District
        fields = ['id', 'name', 'is_active', 'lead_count', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_lead_count(self, obj):
        """Leads filed under this district, so Settings can show what a rename or
        a deactivation would affect."""
        from .models import Lead
        return Lead.objects.filter(district__iexact=obj.name, is_trashed=False).count()

    def validate_name(self, value):
        name = (value or '').strip()
        if not name:
            raise serializers.ValidationError('Enter a district name.')
        # The database constraint is case-insensitive; catching it here turns a
        # 500 into the sentence that explains the clash.
        clash = District.objects.filter(name__iexact=name)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        existing = clash.first()
        if existing:
            raise serializers.ValidationError(
                f'"{existing.name}" is already on the list.'
                if existing.name != name else 'That district is already on the list.')
        return name

class SiteVisitDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteVisitDocument
        fields = ['id', 'doc_type', 'file', 'uploaded_at']


class SiteVisitSerializer(serializers.ModelSerializer):
    documents = serializers.SerializerMethodField()
    kseb_feasibility_due_date = serializers.SerializerMethodField()

    class Meta:
        model = SiteVisit
        fields = '__all__'
        read_only_fields = ['lead', 'created_at', 'updated_at']

    def get_documents(self, obj):
        return _merge_documents(obj, SITE_VISIT_SHARED_SLOTS)

    def get_kseb_feasibility_due_date(self, obj):
        d = obj.kseb_feasibility_due_date
        return d.isoformat() if d else None

    # The site-visit form posts every scalar it holds, and a cleared date arrives
    # as "". That's fine for the CharFields but a DateField rejects it outright,
    # which would fail the whole save over a field the user never touched.
    DATE_FIELDS = ('po_signed_date', 'kseb_feasibility_date')

    def to_internal_value(self, data):
        if hasattr(data, 'get'):
            blanks = [f for f in self.DATE_FIELDS if data.get(f) == '']
            if blanks:
                data = data.copy()
                for f in blanks:
                    data[f] = None
        return super().to_internal_value(data)

    def validate_rcc_roof_types(self, value):
        allowed = {'flat', 'slope', 'tiled', 'non_linear'}
        if not isinstance(value, list):
            raise serializers.ValidationError("Expected a list of roof sub-types.")
        cleaned = [str(v).strip().lower().replace(' ', '_') for v in value if str(v).strip()]
        invalid = [v for v in cleaned if v not in allowed]
        if invalid:
            raise serializers.ValidationError(f"Invalid roof sub-type(s): {', '.join(invalid)}")
        return cleaned


class DocumentationStage1DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentationStage1Document
        fields = ['id', 'doc_type', 'file', 'uploaded_at']


class DocumentationStage1Serializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    def get_documents(self, obj):
        return _merge_documents(obj, DOC_STAGE1_SHARED_SLOTS)

    class Meta:
        model = DocumentationStage1
        fields = '__all__'
        # Completion is driven only by the dedicated complete-* action, never a plain PATCH.
        # The section sign-off timestamps are stamped here, not sent by the client.
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete', 'completed_at', 'completed_by',
                            'name_change_completed_at', 'load_enhancement_completed_at']

    def update(self, instance, validated_data):
        """Stamp the section sign-off time whenever its flag flips."""
        for flag, stamp in (('name_change_completed', 'name_change_completed_at'),
                            ('load_enhancement_completed', 'load_enhancement_completed_at')):
            if flag in validated_data and validated_data[flag] != getattr(instance, flag):
                validated_data[stamp] = timezone.now() if validated_data[flag] else None
        return super().update(instance, validated_data)

    def get_completed_by_name(self, obj):
        if obj.completed_by:
            u = obj.completed_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None


class PaymentVerificationSerializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()
    deal_value = serializers.SerializerMethodField()
    balance_amount = serializers.SerializerMethodField()
    rf_due_date = serializers.SerializerMethodField()

    class Meta:
        model = PaymentVerification
        fields = '__all__'
        # Completion + RF push are driven by dedicated actions, never a plain PATCH.
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete', 'completed_at',
                            'completed_by', 'rf_pushed_to_service', 'rf_pushed_at']

    def get_rf_due_date(self, obj):
        d = obj.rf_due_date
        return d.isoformat() if d else None

    def get_completed_by_name(self, obj):
        if obj.completed_by:
            u = obj.completed_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None

    def get_deal_value(self, obj):
        return obj.deal_value

    def get_balance_amount(self, obj):
        return obj.balance_amount


class DocumentationStage2DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentationStage2Document
        fields = ['id', 'doc_type', 'file', 'uploaded_at']


class WarrantyDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WarrantyDocument
        fields = ['id', 'doc_type', 'file', 'uploaded_at']


class WarrantySerializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()
    documents = WarrantyDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Warranty
        fields = '__all__'
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete', 'completed_at', 'completed_by']

    def get_completed_by_name(self, obj):
        if obj.completed_by:
            u = obj.completed_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None


class DocumentationStage2Serializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()
    documents = DocumentationStage2DocumentSerializer(many=True, read_only=True)
    mnre_portal_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentationStage2
        fields = '__all__'
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete', 'completed_at', 'completed_by']

    def get_completed_by_name(self, obj):
        if obj.completed_by:
            u = obj.completed_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None

    def get_mnre_portal_url(self, obj):
        return DocumentationStage2.MNRE_PORTAL_URL


class LiasoningDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiasoningDocument
        fields = ['id', 'doc_type', 'file', 'uploaded_at']


class LiasoningServiceSerializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()
    documents = LiasoningDocumentSerializer(many=True, read_only=True)
    # Liasoning cannot be signed off until the commissioned plant is photographed.
    has_plant_photo = serializers.BooleanField(read_only=True)

    class Meta:
        model = LiasoningService
        fields = '__all__'
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete', 'completed_at', 'completed_by']

    def get_completed_by_name(self, obj):
        if obj.completed_by:
            u = obj.completed_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None


class BalancePaymentSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()
    receipt_id = serializers.SerializerMethodField()
    receipt_number = serializers.SerializerMethodField()

    class Meta:
        model = BalancePayment
        fields = ['id', 'amount', 'payment_mode', 'utr_details', 'on_account_of', 'note',
                  'recorded_by_name', 'created_at', 'receipt_id', 'receipt_number']

    def get_recorded_by_name(self, obj):
        if obj.recorded_by:
            u = obj.recorded_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None

    def get_receipt_id(self, obj):
        rec = getattr(obj, 'receipt', None)
        return rec.id if rec else None

    def get_receipt_number(self, obj):
        rec = getattr(obj, 'receipt', None)
        return rec.number if rec else None


class ReceiptVoucherSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import ReceiptVoucher
        model = ReceiptVoucher
        fields = ['id', 'number', 'date', 'amount', 'amount_in_words', 'on_account_of',
                  'payment_mode', 'received_from', 'address', 'is_initial', 'created_at']


class PurchaseLogisticsSerializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseLogistics
        fields = '__all__'
        # The override flags are written by the completion action, never by a PATCH.
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete',
                            'completed_at', 'completed_by',
                            'completed_with_override', 'override_reason']

    def get_completed_by_name(self, obj):
        if obj.completed_by:
            u = obj.completed_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None


class ProjectDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDocument
        fields = ['id', 'doc_type', 'file', 'uploaded_at']


class ProjectSerializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()
    documents = ProjectDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = '__all__'
        # The release fields are set only by the super admin's release endpoint.
        # Left writable, a project manager could PATCH themselves a new deadline
        # before the current one runs out and never appear in Overdue at all.
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete', 'completed_at',
                            'completed_by', 'extended_deadline', 'released_at', 'released_by',
                            'release_reason']

    def get_completed_by_name(self, obj):
        if obj.completed_by:
            u = obj.completed_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None


class ServiceEntrySerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ServiceEntry
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            u = obj.created_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None

class MaintenanceVisitDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceVisitDocument
        fields = ['id', 'doc_type', 'file', 'uploaded_at']


class MaintenanceVisitSerializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()
    is_rescheduled = serializers.BooleanField(read_only=True)
    documents = MaintenanceVisitDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = MaintenanceVisit
        fields = '__all__'
        # Photos go through the dedicated upload endpoint, the due date through
        # the reschedule action, and completion is stamped by the view.
        read_only_fields = ['plan', 'sequence', 'due_date', 'original_due_date',
                            'reschedule_reason', 'completed_at', 'completed_by', 'updated_at']

    def get_completed_by_name(self, obj):
        if obj.completed_by:
            u = obj.completed_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None


class PeriodicMaintenanceSerializer(serializers.ModelSerializer):
    visits = MaintenanceVisitSerializer(many=True, read_only=True)

    class Meta:
        model = PeriodicMaintenance
        fields = '__all__'
        read_only_fields = ['lead', 'created_by', 'created_at']


class EmergencyServiceDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyServiceDocument
        fields = ['id', 'doc_type', 'file', 'uploaded_at']


class EmergencyServiceSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    documents = EmergencyServiceDocumentSerializer(many=True, read_only=True)
    # Readable labels for the service-condition picks, so the list does not have
    # to keep its own copy of the choice text.
    dc_side_condition_label = serializers.CharField(source='get_dc_side_condition_display', read_only=True)
    ac_side_condition_label = serializers.CharField(source='get_ac_side_condition_display', read_only=True)
    replacement_label = serializers.CharField(source='get_replacement_display', read_only=True)

    class Meta:
        model = EmergencyService
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            u = obj.created_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None


class LeadSerializer(serializers.ModelSerializer):
    assigned_to_details = UserSerializer(source='assigned_to', read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    campaigns = serializers.SerializerMethodField()
    product_details = ProductSerializer(source='product', read_only=True)
    recent_activity = serializers.SerializerMethodField()
    next_task = serializers.SerializerMethodField()
    meta_integration_name = serializers.SerializerMethodField()
    bde_name = serializers.SerializerMethodField()
    # The tele caller who worked the lead, which is not the same as the current
    # owner once it has been handed to a BDE — both are shown as its owners.
    tele_caller_name = serializers.SerializerMethodField()
    can_edit_site_visit = serializers.SerializerMethodField()
    can_assign_bde = serializers.SerializerMethodField()
    can_assign_documentation = serializers.SerializerMethodField()
    site_visit_complete = serializers.SerializerMethodField()
    documentation_staff_name = serializers.SerializerMethodField()
    pipeline_stage = serializers.CharField(read_only=True)
    pipeline_stage_label = serializers.SerializerMethodField()
    deal_classification = serializers.SerializerMethodField()
    lost_by_name = serializers.SerializerMethodField()
    can_mark_lost = serializers.SerializerMethodField()
    can_edit_status = serializers.SerializerMethodField()
    is_closed_deal = serializers.SerializerMethodField()
    status = serializers.CharField(required=False)

    class Meta:
        model = Lead
        fields = '__all__'
        # Trash is driven only by the dedicated trash/restore actions, never a plain PATCH.
        read_only_fields = ['is_trashed', 'trashed_at', 'trashed_by']

    def get_pipeline_stage_label(self, obj):
        return Lead.PIPELINE_STAGE_LABELS.get(obj.pipeline_stage, obj.pipeline_stage)

    def get_deal_classification(self, obj):
        """Fulfilment/payment milestone for a converted lead, shown on the
        Converted Leads board. A deal is closed once money has actually arrived
        in accounts — reaching documentation is not a closed deal, it is work in
        progress:
          - 'lost'           — converted deal the customer skipped / backed out of
          - 'fully_paid'     — paid in full (nothing left to receive)
          - 'partially_paid' — part payment received, a balance is still due
          - None             — converted, but no payment received yet
        """
        if obj.status != 'converted':
            return None
        if obj.is_lost:
            return 'lost'
        if not self._payment_received(obj):
            return None
        pv = obj.payment_verification
        balance = pv.balance_amount or 0
        return 'fully_paid' if balance <= 0 else 'partially_paid'

    @staticmethod
    def _payment_received(obj):
        """Has the lead reached accounts and had a payment (part or full) taken?

        `is_complete` alone isn't enough: accounts can verify a record before the
        customer has actually paid, and a part payment can be recorded before the
        verification is signed off. Either one counts as money in.
        """
        from decimal import Decimal
        if not obj.pushed_to_accounts:
            return False
        pv = getattr(obj, 'payment_verification', None)
        if not pv:
            return False
        received = pv.amount_received or Decimal('0')
        return received > 0

    def get_is_closed_deal(self, obj):
        """A closed deal: in accounts with a payment (partial or full) received.
        Drives the Closed Deal chip on the Converted Leads board."""
        return bool(obj.status == 'converted' and not obj.is_lost and self._payment_received(obj))

    def get_lost_by_name(self, obj):
        if obj.lost_by:
            u = obj.lost_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None

    def get_can_mark_lost(self, obj):
        from .access import can_mark_lead_lost
        return can_mark_lead_lost(self._request_user())

    def get_can_edit_status(self, obj):
        from .access import can_edit_lead_status
        return can_edit_lead_status(self._request_user())

    def get_meta_integration_name(self, obj):
        return obj.meta_integration.name if obj.meta_integration else None

    def get_bde_name(self, obj):
        if obj.bde:
            return f"{obj.bde.first_name} {obj.bde.last_name}".strip() or obj.bde.username
        return None

    def get_tele_caller_name(self, obj):
        u = obj.tele_caller
        if u:
            return f"{u.first_name} {u.last_name}".strip() or u.username
        # Older leads predate the field; fall back to the owner when they are one.
        owner = obj.assigned_to
        if owner and getattr(owner, 'role', '') == 'tele_caller':
            return f"{owner.first_name} {owner.last_name}".strip() or owner.username
        return None

    def _request_user(self):
        request = self.context.get('request')
        return request.user if request else None

    def get_can_edit_site_visit(self, obj):
        from .access import can_edit_site_visit
        return can_edit_site_visit(self._request_user(), obj)

    def get_can_assign_bde(self, obj):
        from .access import can_assign_bde
        return can_assign_bde(self._request_user(), obj)

    def get_can_assign_documentation(self, obj):
        from .access import can_assign_documentation
        return can_assign_documentation(self._request_user())

    def get_site_visit_complete(self, obj):
        sv = getattr(obj, 'site_visit', None)
        return bool(sv and sv.site_visit_complete)

    def get_documentation_staff_name(self, obj):
        if obj.documentation_staff:
            u = obj.documentation_staff
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None

    def validate_status(self, value):
        from organization.utils import get_org_settings
        org = get_org_settings()
        valid_statuses = [c[0] for c in Lead.status_choices]
        if org.custom_lead_statuses:
            for item in org.custom_lead_statuses:
                if isinstance(item, dict) and 'value' in item:
                    valid_statuses.append(item['value'])
        if value not in valid_statuses:
            raise serializers.ValidationError(f"'{value}' is not a valid lead status.")
        return value

    def get_recent_activity(self, obj):
        logs = obj.activity_logs.all()
        if logs:
            latest_log = logs[0]
            return {
                'id': latest_log.id,
                'activity_type': latest_log.activity_type,
                'description': latest_log.description,
                'created_at': latest_log.created_at,
            }
        return None

    def get_next_task(self, obj):
        """The lead's next pending (not done) task with a due date, plus an
        urgency state for color-coding the tag (overdue / today / upcoming)."""
        from django.utils import timezone
        pending = [t for t in obj.tasks.all() if t.status != 'done' and t.due_date]
        if not pending:
            return None
        pending.sort(key=lambda t: t.due_date)
        t = pending[0]
        today = timezone.localdate()
        if t.due_date < today:
            state = 'overdue'
        elif t.due_date == today:
            state = 'today'
        else:
            state = 'upcoming'
        return {
            'id': t.id,
            'title': t.title,
            'due_date': t.due_date,
            'status': t.status,
            'state': state,
            'pending_count': len(pending),
        }

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip() or obj.assigned_to.username
        return None

    def get_campaigns(self, obj):
        return obj.campaigns_set.values('id', 'name', 'status')

    def validate(self, data):
        new_status = data.get('status', self.instance.status if self.instance else None)
        # A lead may only be moved to Converted once a BDE has been assigned
        # (the tele-caller hands it to a BDE first). Only gate the transition
        # into Converted, so editing an already-converted lead isn't blocked.
        if new_status == 'converted':
            was_converted = bool(self.instance and self.instance.status == 'converted')
            if not was_converted:
                bde = data.get('bde', getattr(self.instance, 'bde', None) if self.instance else None)
                if not bde:
                    raise serializers.ValidationError(
                        {"status": "Assign a BDE to this lead before marking it Converted."})
        return data

class IntegrationSettingsSerializer(serializers.ModelSerializer):
    lead_count = serializers.SerializerMethodField()
    connected = serializers.SerializerMethodField()

    class Meta:
        model = IntegrationSettings
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

    def get_lead_count(self, obj):
        return obj.leads.count()

    def get_connected(self, obj):
        return bool(obj.meta_access_token)
