from rest_framework import serializers
from .models import Lead, IntegrationSettings, LeadAttachment, Product, SiteVisit, DocumentationStage1, SiteVisitDocument, DocumentationStage1Document, PaymentVerification, PurchaseLogistics, Project, ProjectDocument, ServiceEntry, TeamStatsConfig, BalancePayment, DocumentationStage2, DocumentationStage2Document, LiasoningService, Warranty, WarrantyDocument
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
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete', 'completed_at', 'completed_by']

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


class LiasoningServiceSerializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()

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

    class Meta:
        model = BalancePayment
        fields = ['id', 'amount', 'payment_mode', 'utr_details', 'note', 'recorded_by_name', 'created_at']

    def get_recorded_by_name(self, obj):
        if obj.recorded_by:
            u = obj.recorded_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None


class PurchaseLogisticsSerializer(serializers.ModelSerializer):
    completed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseLogistics
        fields = '__all__'
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete', 'completed_at', 'completed_by']

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
        read_only_fields = ['lead', 'created_at', 'updated_at', 'is_complete', 'completed_at', 'completed_by']

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

class LeadSerializer(serializers.ModelSerializer):
    assigned_to_details = UserSerializer(source='assigned_to', read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    campaigns = serializers.SerializerMethodField()
    product_details = ProductSerializer(source='product', read_only=True)
    recent_activity = serializers.SerializerMethodField()
    next_task = serializers.SerializerMethodField()
    meta_integration_name = serializers.SerializerMethodField()
    bde_name = serializers.SerializerMethodField()
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
    status = serializers.CharField(required=False)

    class Meta:
        model = Lead
        fields = '__all__'

    def get_pipeline_stage_label(self, obj):
        return Lead.PIPELINE_STAGE_LABELS.get(obj.pipeline_stage, obj.pipeline_stage)

    def get_deal_classification(self, obj):
        """Fulfilment/payment milestone for a converted lead, shown on the
        Converted Leads board. 'lost' (deal fell through) overrides everything;
        otherwise payment verification outranks the earlier documentation hand-off:
          - 'lost'           — converted deal the customer skipped / backed out of
          - 'fully_paid'     — payment verified with no balance remaining
          - 'partially_paid' — payment verified but a balance is still due
          - 'closed_deal'    — site visit done & pushed to documentation
          - None             — converted but not yet past documentation
        """
        if obj.status != 'converted':
            return None
        if obj.is_lost:
            return 'lost'
        pv = getattr(obj, 'payment_verification', None)
        if pv and pv.is_complete:
            balance = pv.balance_amount or 0
            return 'fully_paid' if balance <= 0 else 'partially_paid'
        if obj.pushed_to_documentation:
            return 'closed_deal'
        return None

    def get_lost_by_name(self, obj):
        if obj.lost_by:
            u = obj.lost_by
            return f"{u.first_name} {u.last_name}".strip() or u.username
        return None

    def get_can_mark_lost(self, obj):
        from .access import can_mark_lead_lost
        return can_mark_lead_lost(self._request_user())

    def get_meta_integration_name(self, obj):
        return obj.meta_integration.name if obj.meta_integration else None

    def get_bde_name(self, obj):
        if obj.bde:
            return f"{obj.bde.first_name} {obj.bde.last_name}".strip() or obj.bde.username
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
