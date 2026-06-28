from rest_framework import viewsets, status, permissions
from core.permissions import IsAdminOnly
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import HttpResponse
import csv
import io
import logging
from .models import Lead, IntegrationSettings, ActivityLog, LeadAttachment, Product, SiteVisit, DocumentationStage1, SiteVisitDocument, DocumentationStage1Document, LeadDocument, PaymentVerification
from .serializers import LeadSerializer, IntegrationSettingsSerializer, LeadAttachmentSerializer, ProductSerializer, SiteVisitSerializer, DocumentationStage1Serializer, SiteVisitDocumentSerializer, DocumentationStage1DocumentSerializer, PaymentVerificationSerializer
from .document_kinds import SHARED_KIND_LABELS, kind_for
from django.utils import timezone

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    'new': 'New', 'follow_up': 'Follow Up', 'positive': 'Positive',
    'enrolled': 'Enrolled', 'not_interested': 'Not Interested',
    'disqualified': 'Disqualified', 'prospect': 'Prospect',
    'interested_to_join': 'Interested to Join', 'may_buy_later': 'May Buy Later',
    'demo_booked': 'Demo Booked', 'demo_done': 'Demo Done',
    'demo_rescheduled': 'Demo Rescheduled', 'demo_canceled': 'Demo Canceled',
    'dnp': 'DNP',
}

# SiteVisit file fields exposed to the documentation team, in display order.
SITE_VISIT_ATTACHMENTS = [
    ('kseb_bill_file', 'KSEB Bill'),
    ('aadhaar_card', 'Aadhaar Card'),
    ('pan_card', 'PAN Card'),
    ('passbook', 'Passbook'),
    ('land_tax', 'Land Tax'),
    ('ownership_certificate', 'Ownership Certificate'),
    ('customer_passport_photo', 'Customer Passport Photo'),
    ('building_certificate', 'Building Certificate'),
    ('loan_document', 'Loan Document'),
    ('itr_report', 'ITR Report'),
    ('photo_meterbox', 'Meter Box'),
    ('photo_earthing_1', 'Earthing 1'),
    ('photo_earthing_2', 'Earthing 2'),
    ('photo_earthing_3', 'Earthing 3'),
    ('photo_directional', 'Directional Photo'),
    ('photo_hand_sketch', 'Hand Sketch'),
    ('photo_feasibility_report', 'Feasibility Report'),
]
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')

# Documentation Stage 1 document slots (doc_type -> label). Each slot can hold many files.
DOC_STAGE1_ATTACHMENTS = [
    ('nc_ownership', 'Ownership'), ('nc_building_certificate', 'Building Certificate'),
    ('nc_landtax', 'Land Tax'), ('nc_customer_photo', 'Customer Photo'),
    ('nc_aadhaar', 'Aadhaar'), ('nc_kseb_bill', 'KSEB Bill'),
    ('le_aadhaar', 'Aadhaar'),
    ('mnre_aadhaar', 'Aadhaar'), ('mnre_pan', 'PAN'), ('mnre_passbook', 'Passbook'),
    ('mnre_purchase_order', 'Purchase Order'), ('mnre_kseb_bill', 'KSEB Bill'),
    ('loan_aadhaar', 'Aadhaar'), ('loan_pan', 'PAN'), ('loan_passbook', 'Passbook'),
    ('loan_land_tax', 'Land Tax'), ('loan_passbook_copy', 'Passbook Copy'), ('loan_itr', 'ITR'),
    ('loan_agreement_purchase_order', 'Agreement / Purchase Order'),
]


def _shared_doc_dict(doc):
    """Serialize a LeadDocument for an upload response (same shape the stage
    serializers emit for shared documents)."""
    return {
        'id': doc.id,
        'kind': doc.kind,
        'file': doc.file.url if doc.file else None,
        'uploaded_at': doc.uploaded_at,
        'shared': True,
    }


def build_process_overview(lead, completed_by=None):
    """Build a short, human-readable summary of a lead's journey so far.

    Used for the note auto-added to lead history when Documentation Stage 1 is
    completed — it captures the moves the lead went through (tele caller → BDE →
    documentation) using the timestamps/owners already stored on the lead.
    """
    def name(user):
        if not user:
            return '—'
        return f"{user.first_name} {user.last_name}".strip() or user.username

    def when(dt):
        return timezone.localtime(dt).strftime('%d %b %Y') if dt else None

    steps = []
    created = when(lead.created_at)
    steps.append(f"Lead created{f' on {created}' if created else ''} (source: {lead.source or 'manual'})")
    steps.append(f"Tele caller: {name(lead.assigned_to)}")
    steps.append(f"BDE: {name(lead.bde)}")
    pushed = when(lead.pushed_to_documentation_at)
    steps.append(f"Pushed to documentation{f' on {pushed}' if pushed else ''}")
    steps.append(f"Documentation staff: {name(lead.documentation_staff)}")

    overview = " → ".join(steps)
    actor = name(completed_by) if completed_by else "documentation staff"
    return f"Documentation Stage 1 completed by {actor}. Process overview: {overview}."


def _least_recently_assigned_doc(candidates):
    """Round-robin pick: the handler assigned a documentation lead least recently.

    Mirrors ai_manager.engine._round_robin_assign so distribution is even — the
    person who hasn't received a pushed lead for the longest goes next.
    """
    best, best_time = None, None
    floor = timezone.datetime.min.replace(tzinfo=timezone.utc)
    for u in candidates:
        last = (Lead.objects.filter(documentation_staff=u)
                .order_by('-pushed_to_documentation_at').first())
        t = last.pushed_to_documentation_at if (last and last.pushed_to_documentation_at) else floor
        if best is None or t < best_time:
            best, best_time = u, t
    return best


def auto_assign_documentation(lead):
    """On push-to-documentation, auto-assign a handler:

    - round-robin among the BDE's team's documentation_staff, else
    - the documentation_manager (the BDE's team's, else any in the org).

    Respects an existing assignment (won't override a manual one). Returns the
    assigned user or None.
    """
    from users.models import User, ROLE_DOC_STAFF, ROLE_DOC_MANAGER
    if lead.documentation_staff_id:
        return None
    team = lead.bde.team if (lead.bde and lead.bde.team_id) else None

    assignee = None
    if team:
        staff = list(team.members.filter(role=ROLE_DOC_STAFF, is_active=True))
        if staff:
            assignee = _least_recently_assigned_doc(staff)

    if assignee is None:
        managers = list(team.members.filter(role=ROLE_DOC_MANAGER, is_active=True)) if team else []
        if not managers:
            managers = list(User.objects.filter(role=ROLE_DOC_MANAGER, is_active=True))
        if managers:
            assignee = _least_recently_assigned_doc(managers)

    if assignee:
        lead.documentation_staff = assignee
        lead.save(update_fields=['documentation_staff'])
    return assignee


def _least_recently_assigned_accounts(candidates):
    """Round-robin pick among accounts staff (least recently assigned goes next)."""
    best, best_time = None, None
    floor = timezone.datetime.min.replace(tzinfo=timezone.utc)
    for u in candidates:
        last = (Lead.objects.filter(accounts_staff=u)
                .order_by('-pushed_to_accounts_at').first())
        t = last.pushed_to_accounts_at if (last and last.pushed_to_accounts_at) else floor
        if best is None or t < best_time:
            best, best_time = u, t
    return best


def auto_assign_accounts(lead):
    """On handoff to accounts, round-robin assign an accounts_staff member:
    prefer the BDE's team's accounts staff, else any active accounts staff in the
    org. Respects an existing assignment. Returns the assignee or None."""
    from users.models import User, ROLE_ACCOUNTS_STAFF
    if lead.accounts_staff_id:
        return None
    team = lead.bde.team if (lead.bde and lead.bde.team_id) else None
    candidates = list(team.members.filter(role=ROLE_ACCOUNTS_STAFF, is_active=True)) if team else []
    if not candidates:
        candidates = list(User.objects.filter(role=ROLE_ACCOUNTS_STAFF, is_active=True))
    assignee = _least_recently_assigned_accounts(candidates) if candidates else None
    if assignee:
        lead.accounts_staff = assignee
        lead.save(update_fields=['accounts_staff'])
    return assignee


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def paginate_queryset(self, queryset):
        if self.request.query_params.get('all') == 'true':
            return None
        return super().paginate_queryset(queryset)

    @action(detail=False, methods=['get'])
    def statuses(self, request):
        from organization.utils import get_org_settings
        org = get_org_settings()

        # Standard statuses
        statuses = [
            {"value": "new", "label": "New", "bg": "bg-indigo-50", "text": "text-indigo-700", "dot": "bg-indigo-400", "color": "#6366f1"},
            {"value": "follow_up", "label": "Follow up", "bg": "bg-amber-50", "text": "text-amber-700", "dot": "bg-amber-400", "color": "#f59e0b"},
            {"value": "positive", "label": "Positive", "bg": "bg-cyan-50", "text": "text-cyan-700", "dot": "bg-cyan-500", "color": "#06b6d4"},
            {"value": "enrolled", "label": "Enrolled", "bg": "bg-emerald-50", "text": "text-emerald-700", "dot": "bg-emerald-500", "color": "#10b981"},
            {"value": "not_interested", "label": "Not Interested", "bg": "bg-rose-50", "text": "text-rose-700", "dot": "bg-rose-500", "color": "#f43f5e"},
            {"value": "disqualified", "label": "Disqualified", "bg": "bg-red-50", "text": "text-red-700", "dot": "bg-red-500", "color": "#ef4444"},
            {"value": "prospect", "label": "Prospect", "bg": "bg-violet-50", "text": "text-violet-700", "dot": "bg-violet-400", "color": "#8b5cf6"},
            {"value": "interested_to_join", "label": "Interested to Join", "bg": "bg-lime-50", "text": "text-lime-700", "dot": "bg-lime-500", "color": "#84cc16"},
            {"value": "may_buy_later", "label": "May Buy Later", "bg": "bg-orange-50", "text": "text-orange-700", "dot": "bg-orange-400", "color": "#f97316"},
            {"value": "demo_booked", "label": "Demo Booked", "bg": "bg-sky-50", "text": "text-sky-700", "dot": "bg-sky-500", "color": "#0ea5e9"},
            {"value": "demo_done", "label": "Demo Done", "bg": "bg-teal-50", "text": "text-teal-700", "dot": "bg-teal-500", "color": "#14b8a6"},
            {"value": "demo_rescheduled", "label": "Demo Rescheduled", "bg": "bg-yellow-50", "text": "text-yellow-700", "dot": "bg-yellow-500", "color": "#eab308"},
            {"value": "demo_canceled", "label": "Demo Canceled", "bg": "bg-pink-50", "text": "text-pink-700", "dot": "bg-pink-500", "color": "#ec4899"},
            {"value": "dnp", "label": "DNP", "bg": "bg-slate-100", "text": "text-slate-600", "dot": "bg-slate-400", "color": "#94a3b8"},
            {"value": "partially_paid", "label": "Partially Paid", "bg": "bg-fuchsia-50", "text": "text-fuchsia-700", "dot": "bg-fuchsia-500", "color": "#d946ef"},
        ]
        
        custom_statuses = []
        if org.custom_lead_statuses:
            custom_statuses = org.custom_lead_statuses
            
        merged_statuses = list(statuses)
        for cs in custom_statuses:
            if isinstance(cs, dict) and 'value' in cs and 'label' in cs:
                if not any(item['value'] == cs['value'] for item in merged_statuses):
                    merged_statuses.append({
                        "value": cs['value'],
                        "label": cs['label'],
                        "bg": cs.get("bg", "bg-purple-50"),
                        "text": cs.get("text", "text-purple-700"),
                        "dot": cs.get("dot", "bg-purple-500"),
                        "color": cs.get("color", "#a855f7")
                    })
        
        return Response(merged_statuses)

    @action(detail=True, methods=['get', 'patch', 'put'], url_path='site-visit')
    def site_visit(self, request, pk=None):
        """Get or update the solar site-survey details for a lead."""
        from .access import can_edit_site_visit
        lead = self.get_object()
        sv, _ = SiteVisit.objects.get_or_create(lead=lead)
        if request.method == 'GET':
            data = SiteVisitSerializer(sv).data
            data['deal_value'] = lead.value  # deal value is entered here by the BDE
            return Response(data)
        if not can_edit_site_visit(request.user, lead):
            return Response({'error': 'You do not have permission to edit this site visit.'},
                            status=status.HTTP_403_FORBIDDEN)
        serializer = SiteVisitSerializer(sv, data=request.data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # The deal value lives on the Lead but is now entered by the BDE during the
        # site visit (no longer by the tele caller). Persist it when provided.
        if 'deal_value' in request.data:
            from decimal import Decimal, InvalidOperation
            try:
                lead.value = Decimal(str(request.data.get('deal_value') or 0))
                lead.save(update_fields=['value'])
            except (InvalidOperation, TypeError, ValueError):
                pass
        data = serializer.data
        data['deal_value'] = lead.value
        return Response(data)

    @action(detail=True, methods=['post'], url_path='site-visit/documents')
    def site_visit_add_document(self, request, pk=None):
        """Upload one file to a site-visit document/photo slot (multiple allowed per slot)."""
        from .access import can_edit_site_visit
        lead = self.get_object()
        sv, _ = SiteVisit.objects.get_or_create(lead=lead)
        if not can_edit_site_visit(request.user, lead):
            return Response({'error': 'You do not have permission to edit this site visit.'},
                            status=status.HTTP_403_FORBIDDEN)
        doc_type = request.data.get('doc_type')
        file = request.FILES.get('file')
        if not doc_type or not file:
            return Response({'error': 'doc_type and file are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if doc_type not in {k for k, _ in SITE_VISIT_ATTACHMENTS}:
            return Response({'error': 'Unknown document type.'}, status=status.HTTP_400_BAD_REQUEST)
        # Shared customer documents (Aadhaar/PAN/…) live in the lead-level pool so
        # they're inherited by later stages — route them there even if posted here.
        kind = kind_for(doc_type)
        if kind:
            doc = LeadDocument.objects.create(
                lead=lead, kind=kind, file=file,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )
            return Response(_shared_doc_dict(doc), status=status.HTTP_201_CREATED)
        doc = SiteVisitDocument.objects.create(
            site_visit=sv, doc_type=doc_type, file=file,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )
        return Response(SiteVisitDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='site-visit/documents/(?P<doc_id>[0-9]+)')
    def site_visit_delete_document(self, request, pk=None, doc_id=None):
        """Delete a single site-visit document (mistaken upload)."""
        from .access import can_edit_site_visit
        lead = self.get_object()
        if not can_edit_site_visit(request.user, lead):
            return Response({'error': 'You do not have permission to edit this site visit.'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            doc = SiteVisitDocument.objects.get(pk=doc_id, site_visit__lead=lead)
        except SiteVisitDocument.DoesNotExist:
            return Response({'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='assign-bde')
    def assign_bde(self, request, pk=None):
        """Tele caller hands the lead off to a BDE for the site visit."""
        from users.models import User
        from .access import can_assign_bde
        lead = self.get_object()
        if not can_assign_bde(request.user, lead):
            return Response({'error': 'You do not have permission to assign a BDE for this lead.'},
                            status=status.HTTP_403_FORBIDDEN)
        bde_id = request.data.get('bde')
        if not bde_id:
            lead.bde = None
        else:
            try:
                lead.bde = User.objects.get(pk=bde_id)
            except User.DoesNotExist:
                return Response({'error': 'BDE not found.'}, status=status.HTTP_404_NOT_FOUND)
        lead.save(update_fields=['bde'])
        if lead.bde:
            ActivityLog.objects.create(
                activity_type='note_added',
                description=f"Assigned to BDE: {lead.bde.first_name} {lead.bde.last_name}".strip(),
                actor=request.user if request.user.is_authenticated else None,
                lead=lead,
            )
        return Response(self.get_serializer(lead).data)

    @action(detail=True, methods=['post'], url_path='push-to-documentation')
    def push_to_documentation(self, request, pk=None):
        """BDE pushes a completed site visit to the documentation team."""
        from .access import can_push_to_documentation
        lead = self.get_object()
        if not can_push_to_documentation(request.user, lead):
            return Response({'error': 'You do not have permission to push this lead to documentation.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead.pushed_to_documentation = True
        lead.pushed_to_documentation_at = timezone.now()
        lead.save(update_fields=['pushed_to_documentation', 'pushed_to_documentation_at'])
        ActivityLog.objects.create(
            activity_type='note_added',
            description="Pushed to documentation",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead,
        )
        # Auto-assign a documentation handler (team's doc staff round-robin, else doc manager).
        assignee = auto_assign_documentation(lead)
        if assignee:
            name = f"{assignee.first_name} {assignee.last_name}".strip() or assignee.username
            ActivityLog.objects.create(
                activity_type='note_added',
                description=f"Auto-assigned to documentation: {name}",
                actor=request.user if request.user.is_authenticated else None,
                lead=lead,
                extra={'auto_generated': True},
            )
        return Response(self.get_serializer(lead).data)

    @action(detail=True, methods=['post'], url_path='assign-documentation')
    def assign_documentation(self, request, pk=None):
        """Documentation manager assigns the lead to a documentation staff member."""
        from users.models import User
        from .access import can_assign_documentation
        lead = self.get_object()
        if not can_assign_documentation(request.user):
            return Response({'error': 'Only documentation managers can assign documentation staff.'},
                            status=status.HTTP_403_FORBIDDEN)
        staff_id = request.data.get('staff')
        if not staff_id:
            lead.documentation_staff = None
        else:
            try:
                lead.documentation_staff = User.objects.get(pk=staff_id)
            except User.DoesNotExist:
                return Response({'error': 'Staff not found.'}, status=status.HTTP_404_NOT_FOUND)
        lead.save(update_fields=['documentation_staff'])
        if lead.documentation_staff:
            ActivityLog.objects.create(
                activity_type='note_added',
                description=f"Documentation assigned to: {lead.documentation_staff.first_name} {lead.documentation_staff.last_name}".strip(),
                actor=request.user if request.user.is_authenticated else None,
                lead=lead,
            )
        return Response(self.get_serializer(lead).data)

    def _documentation_payload(self, lead, request):
        from .access import can_assign_documentation, can_edit_documentation_stage1
        sv = getattr(lead, 'site_visit', None)
        stage1 = getattr(lead, 'documentation_stage1', None)
        attachments = []

        def add(file_field, label):
            if not file_field:
                return
            try:
                url = request.build_absolute_uri(file_field.url)
            except Exception:
                return
            is_image = url.lower().split('?')[0].endswith(IMAGE_EXTS)
            attachments.append({'label': label, 'url': url, 'is_image': is_image})

        add(lead.invoice, 'Invoice')
        if sv:
            labels = dict(SITE_VISIT_ATTACHMENTS)
            for doc in sv.documents.all():
                add(doc.file, labels.get(doc.doc_type, doc.doc_type))
        # Shared customer documents (entered once, inherited across stages).
        for doc in lead.shared_documents.all():
            add(doc.file, SHARED_KIND_LABELS.get(doc.kind, doc.kind))

        return {
            'id': lead.id,
            'first_name': lead.first_name,
            'last_name': lead.last_name,
            'phone': lead.phone,
            'email': lead.email,
            'location': lead.company,
            'installation_location': lead.installation_location,
            'product_name': lead.product.name if lead.product else None,
            'value': lead.value,
            'status': lead.status,
            'bde_name': f"{lead.bde.first_name} {lead.bde.last_name}".strip() if lead.bde else None,
            'documentation_staff': lead.documentation_staff_id,
            'documentation_staff_name': f"{lead.documentation_staff.first_name} {lead.documentation_staff.last_name}".strip() if lead.documentation_staff else None,
            'pushed_at': lead.pushed_to_documentation_at,
            'site_visit': SiteVisitSerializer(sv, context={'request': request}).data if sv else None,
            'documentation_stage1': DocumentationStage1Serializer(stage1, context={'request': request}).data if stage1 else None,
            'stage1_complete': bool(stage1 and stage1.is_complete),
            'can_edit_stage1': can_edit_documentation_stage1(request.user, lead),
            'can_reopen_stage1': can_assign_documentation(request.user),
            'attachments': attachments,
            'can_assign': can_assign_documentation(request.user),
        }

    @action(detail=False, methods=['get'], url_path='documentation-overview')
    def documentation_overview(self, request):
        """Read-only tracker of leads in the documentation process.

        For everyone EXCEPT the documentation team (staff/managers have their own
        work queue). Lead visibility is role-scoped exactly like the lead list.
        """
        from django.db.models import Q
        user = request.user
        if getattr(user, 'role', '') in ('documentation_staff', 'documentation_manager'):
            return Response({'error': 'The documentation work queue is your view.'},
                            status=status.HTTP_403_FORBIDDEN)

        base = (Lead.objects.filter(pushed_to_documentation=True)
                .select_related('product', 'bde', 'documentation_staff', 'documentation_stage1')
                .prefetch_related('documentation_stage1__documents'))
        if getattr(user, 'sees_all_leads', False):
            qs = base
        elif getattr(user, 'branch_scoped', False) and user.branch_id:
            qs = base.filter(Q(assigned_to=user) | Q(assigned_to__isnull=True) | Q(assigned_to__branch=user.branch))
        else:
            qs = base.filter(Q(assigned_to=user) | Q(bde=user))
        qs = qs.distinct().order_by('-pushed_to_documentation_at')

        def stage1_status(s1):
            if not s1:
                return 'not_started'
            if s1.is_complete:
                return 'completed'
            started = (s1.documents.exists() or bool((s1.mnre_plant_capacity or '').strip())
                       or s1.le_test_cum_completion_report or s1.le_sketch or s1.loan_above_2_lakh)
            return 'in_progress' if started else 'not_started'

        def name(u):
            return f"{u.first_name} {u.last_name}".strip() or u.username if u else None

        rows = []
        for lead in qs:
            s1 = getattr(lead, 'documentation_stage1', None)
            rows.append({
                'id': lead.id,
                'name': f"{lead.first_name} {lead.last_name or ''}".strip(),
                'phone': lead.phone,
                'location': lead.company,
                'product_name': lead.product.name if lead.product else None,
                'value': lead.value,
                'status': lead.status,
                'bde_name': name(lead.bde),
                'documentation_staff_name': name(lead.documentation_staff),
                'pushed_at': lead.pushed_to_documentation_at,
                'stage1_status': stage1_status(s1),
                'stage1_completed_at': s1.completed_at if s1 else None,
                'stage1_completed_by': name(s1.completed_by) if s1 else None,
                'stage2_status': 'pending',  # placeholder until Stage 2 is built
            })
        return Response(rows)

    @action(detail=True, methods=['get'], url_path='documentation-overview-detail')
    def documentation_overview_detail(self, request, pk=None):
        """Customer details + per-stage status + full activity history for one lead
        in documentation. For the tracker audience (not the documentation team);
        lead visibility is enforced by get_object()/get_queryset scoping."""
        user = request.user
        if getattr(user, 'role', '') in ('documentation_staff', 'documentation_manager'):
            return Response({'error': 'The documentation work queue is your view.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()  # 404 if not in this user's scoped queryset
        if not lead.pushed_to_documentation:
            return Response({'error': 'This lead is not in documentation.'},
                            status=status.HTTP_404_NOT_FOUND)

        def name(u):
            return (f"{u.first_name} {u.last_name}".strip() or u.username) if u else None

        s1 = getattr(lead, 'documentation_stage1', None)
        if not s1:
            stage1_status = 'not_started'
        elif s1.is_complete:
            stage1_status = 'completed'
        else:
            started = (s1.documents.exists() or bool((s1.mnre_plant_capacity or '').strip())
                       or s1.le_test_cum_completion_report or s1.le_sketch or s1.loan_above_2_lakh)
            stage1_status = 'in_progress' if started else 'not_started'

        logs = ActivityLog.objects.filter(lead=lead).select_related('actor').order_by('-created_at')
        # System-composed notes show "Auto generated" as the author. Detected by the
        # flag on new notes, and by description prefix for ones created before the flag.
        auto_prefixes = ('Documentation Stage 1 completed by', 'Auto-assigned to documentation:')

        def is_auto(log):
            return bool((log.extra or {}).get('auto_generated')) or (log.description or '').startswith(auto_prefixes)

        history = [{
            'id': log.id,
            'type': log.activity_type,
            'description': log.description,
            'actor': name(log.actor),
            'auto_generated': is_auto(log),
            'timestamp': timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S"),
        } for log in logs]

        # Site-visit (BDE) data + every uploaded file across site visit, Stage 1, and the invoice.
        sv = getattr(lead, 'site_visit', None)
        attachments = []

        def add(file_field, label):
            if not file_field:
                return
            try:
                url = request.build_absolute_uri(file_field.url)
            except Exception:
                return
            is_image = url.lower().split('?')[0].endswith(IMAGE_EXTS)
            attachments.append({'label': label, 'url': url, 'is_image': is_image})

        add(lead.invoice, 'Invoice')
        if sv:
            sv_labels = dict(SITE_VISIT_ATTACHMENTS)
            for doc in sv.documents.all():
                add(doc.file, sv_labels.get(doc.doc_type, doc.doc_type))
        if s1:
            s1_labels = dict(DOC_STAGE1_ATTACHMENTS)
            for doc in s1.documents.all():
                add(doc.file, s1_labels.get(doc.doc_type, doc.doc_type))
        # Shared customer documents (entered once, inherited across stages).
        for doc in lead.shared_documents.all():
            add(doc.file, SHARED_KIND_LABELS.get(doc.kind, doc.kind))

        stage1_data = None
        if s1:
            stage1_data = {
                'plant_capacity': s1.mnre_plant_capacity,
                'test_cum_completion_report': s1.le_test_cum_completion_report,
                'sketch': s1.le_sketch,
                'loan_above_2_lakh': s1.loan_above_2_lakh,
                'is_complete': s1.is_complete,
            }

        return Response({
            'id': lead.id,
            'name': f"{lead.first_name} {lead.last_name or ''}".strip(),
            'phone': lead.phone,
            'email': lead.email,
            'location': lead.company,
            'installation_location': lead.installation_location,
            'product_name': lead.product.name if lead.product else None,
            'value': lead.value,
            'status': lead.status,
            'source': lead.source,
            'created_at': lead.created_at,
            'tele_caller_name': name(lead.assigned_to),
            'bde_name': name(lead.bde),
            'documentation_staff_name': name(lead.documentation_staff),
            'pushed_at': lead.pushed_to_documentation_at,
            'stage1_status': stage1_status,
            'stage1_completed_at': s1.completed_at if s1 else None,
            'stage1_completed_by': name(s1.completed_by) if s1 else None,
            'stage2_status': 'pending',
            'site_visit': SiteVisitSerializer(sv, context={'request': request}).data if sv else None,
            'stage1': stage1_data,
            'attachments': attachments,
            'history': history,
        })

    @action(detail=False, methods=['get'], url_path='documentation')
    def documentation(self, request):
        """Documentation team's dedicated view: pushed customers + their attachments."""
        from .access import can_access_documentation
        user = request.user
        if not can_access_documentation(user):
            return Response({'error': 'You do not have access to documentation.'},
                            status=status.HTTP_403_FORBIDDEN)
        qs = (Lead.objects.filter(pushed_to_documentation=True)
              .select_related('product', 'bde', 'documentation_staff', 'site_visit', 'documentation_stage1')
              .prefetch_related('site_visit__documents', 'shared_documents')
              .order_by('-pushed_to_documentation_at'))
        # Documentation staff see only the leads assigned to them; managers/admins see all pushed.
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'documentation_staff'):
            qs = qs.filter(documentation_staff=user)
        return Response([self._documentation_payload(lead, request) for lead in qs])

    @action(detail=True, methods=['get'], url_path='documentation-detail')
    def documentation_detail(self, request, pk=None):
        """Full documentation view for one pushed customer (data + attachments)."""
        from .access import can_access_documentation
        user = request.user
        if not can_access_documentation(user):
            return Response({'error': 'You do not have access to documentation.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_documentation:
            return Response({'error': 'This lead has not been pushed to documentation.'},
                            status=status.HTTP_404_NOT_FOUND)
        # Documentation staff may only open the leads assigned to them.
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'documentation_staff'
                and lead.documentation_staff_id != user.id):
            return Response({'error': 'This lead is not assigned to you.'},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(self._documentation_payload(lead, request))

    @action(detail=True, methods=['get', 'patch'], url_path='documentation-stage1')
    def documentation_stage1(self, request, pk=None):
        """Get or update a lead's Documentation Stage 1 paperwork."""
        from .access import can_access_documentation, can_edit_documentation_stage1
        lead = self.get_object()
        if not can_access_documentation(request.user):
            return Response({'error': 'You do not have access to documentation.'},
                            status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_documentation:
            return Response({'error': 'This lead has not been pushed to documentation.'},
                            status=status.HTTP_404_NOT_FOUND)
        stage1, _ = DocumentationStage1.objects.get_or_create(lead=lead)
        if request.method == 'GET':
            return Response(DocumentationStage1Serializer(stage1, context={'request': request}).data)
        if not can_edit_documentation_stage1(request.user, lead):
            return Response({'error': 'You do not have permission to edit this documentation.'},
                            status=status.HTTP_403_FORBIDDEN)
        if stage1.is_complete:
            return Response({'error': 'Documentation Stage 1 is already completed and locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = DocumentationStage1Serializer(stage1, data=request.data, partial=True,
                                                    context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='complete-documentation-stage1')
    def complete_documentation_stage1(self, request, pk=None):
        """Mark Documentation Stage 1 complete and write a process-overview note."""
        from .access import can_edit_documentation_stage1
        lead = self.get_object()
        if not can_edit_documentation_stage1(request.user, lead):
            return Response({'error': 'You do not have permission to complete this documentation.'},
                            status=status.HTTP_403_FORBIDDEN)
        stage1, _ = DocumentationStage1.objects.get_or_create(lead=lead)
        if stage1.is_complete:
            return Response({'error': 'Documentation Stage 1 is already completed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        missing = stage1.missing_mandatory_fields()
        if missing:
            return Response(
                {'error': 'Complete the mandatory MNRE section first.', 'missing': missing},
                status=status.HTTP_400_BAD_REQUEST)
        stage1.is_complete = True
        stage1.completed_at = timezone.now()
        stage1.completed_by = request.user if request.user.is_authenticated else None
        stage1.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        ActivityLog.objects.create(
            activity_type='note_added',
            description=build_process_overview(lead, stage1.completed_by),
            actor=request.user if request.user.is_authenticated else None,
            lead=lead,
            extra={'auto_generated': True},
        )
        # Hand the lead off to the accounts team for payment verification.
        if not lead.pushed_to_accounts:
            lead.pushed_to_accounts = True
            lead.pushed_to_accounts_at = timezone.now()
            lead.save(update_fields=['pushed_to_accounts', 'pushed_to_accounts_at'])
            assignee = auto_assign_accounts(lead)
            if assignee:
                name = f"{assignee.first_name} {assignee.last_name}".strip() or assignee.username
                desc = f"Moved to accounts for payment verification. Auto-assigned to {name}."
            else:
                desc = "Moved to accounts for payment verification."
            ActivityLog.objects.create(
                activity_type='note_added',
                description=desc,
                actor=request.user if request.user.is_authenticated else None,
                lead=lead,
                extra={'auto_generated': True},
            )
        return Response(self._documentation_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='reopen-documentation-stage1')
    def reopen_documentation_stage1(self, request, pk=None):
        """Documentation manager re-opens a completed Stage 1 for further editing."""
        from .access import can_assign_documentation
        lead = self.get_object()
        if not can_assign_documentation(request.user):
            return Response({'error': 'Only documentation managers can reopen completed documentation.'},
                            status=status.HTTP_403_FORBIDDEN)
        stage1 = getattr(lead, 'documentation_stage1', None)
        if not stage1 or not stage1.is_complete:
            return Response({'error': 'Documentation Stage 1 is not completed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        stage1.is_complete = False
        stage1.completed_at = None
        stage1.completed_by = None
        stage1.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        actor = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        ActivityLog.objects.create(
            activity_type='note_added',
            description=f"Documentation Stage 1 reopened for editing by {actor}.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead,
        )
        return Response(self._documentation_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='documentation-stage1/documents')
    def documentation_stage1_add_document(self, request, pk=None):
        """Upload one file to a Documentation Stage 1 slot (multiple allowed per slot)."""
        from .access import can_edit_documentation_stage1
        lead = self.get_object()
        if not can_edit_documentation_stage1(request.user, lead):
            return Response({'error': 'You do not have permission to edit this documentation.'},
                            status=status.HTTP_403_FORBIDDEN)
        stage1, _ = DocumentationStage1.objects.get_or_create(lead=lead)
        if stage1.is_complete:
            return Response({'error': 'Documentation Stage 1 is completed and locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        doc_type = request.data.get('doc_type')
        file = request.FILES.get('file')
        if not doc_type or not file:
            return Response({'error': 'doc_type and file are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if doc_type not in {k for k, _ in DOC_STAGE1_ATTACHMENTS}:
            return Response({'error': 'Unknown document type.'}, status=status.HTTP_400_BAD_REQUEST)
        # Shared customer documents (Aadhaar/PAN/…) live in the lead-level pool so
        # they're inherited across stages — route them there even if posted here.
        kind = kind_for(doc_type)
        if kind:
            doc = LeadDocument.objects.create(
                lead=lead, kind=kind, file=file,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )
            return Response(_shared_doc_dict(doc), status=status.HTTP_201_CREATED)
        doc = DocumentationStage1Document.objects.create(
            stage1=stage1, doc_type=doc_type, file=file,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )
        return Response(DocumentationStage1DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='documentation-stage1/documents/(?P<doc_id>[0-9]+)')
    def documentation_stage1_delete_document(self, request, pk=None, doc_id=None):
        """Delete a single Documentation Stage 1 file (mistaken upload)."""
        from .access import can_edit_documentation_stage1
        lead = self.get_object()
        if not can_edit_documentation_stage1(request.user, lead):
            return Response({'error': 'You do not have permission to edit this documentation.'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            doc = DocumentationStage1Document.objects.get(pk=doc_id, stage1__lead=lead)
        except DocumentationStage1Document.DoesNotExist:
            return Response({'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        if doc.stage1.is_complete:
            return Response({'error': 'Documentation Stage 1 is completed and locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='shared-documents')
    def shared_add_document(self, request, pk=None):
        """Upload a shared customer document (Aadhaar/PAN/…) onto the lead.

        Stored once and inherited by every same-kind slot across the BDE site
        visit and Documentation Stage 1. Editable by anyone who can edit either
        of those stages — so a wrong upload can be corrected downstream.
        """
        from .access import can_edit_site_visit, can_edit_documentation_stage1
        lead = self.get_object()
        if not (can_edit_site_visit(request.user, lead)
                or can_edit_documentation_stage1(request.user, lead)):
            return Response({'error': "You do not have permission to edit this customer's documents."},
                            status=status.HTTP_403_FORBIDDEN)
        kind = request.data.get('kind')
        file = request.FILES.get('file')
        if not kind or not file:
            return Response({'error': 'kind and file are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if kind not in SHARED_KIND_LABELS:
            return Response({'error': 'Unknown document kind.'}, status=status.HTTP_400_BAD_REQUEST)
        doc = LeadDocument.objects.create(
            lead=lead, kind=kind, file=file,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )
        return Response(_shared_doc_dict(doc), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='shared-documents/(?P<doc_id>[0-9]+)')
    def shared_delete_document(self, request, pk=None, doc_id=None):
        """Delete a shared customer document (removes it from every stage slot)."""
        from .access import can_edit_site_visit, can_edit_documentation_stage1
        lead = self.get_object()
        if not (can_edit_site_visit(request.user, lead)
                or can_edit_documentation_stage1(request.user, lead)):
            return Response({'error': "You do not have permission to edit this customer's documents."},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            doc = LeadDocument.objects.get(pk=doc_id, lead=lead)
        except LeadDocument.DoesNotExist:
            return Response({'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Accounts / payment verification ──
    def _accounts_payload(self, lead, request):
        from .access import can_assign_accounts, can_edit_payment_verification
        pv = getattr(lead, 'payment_verification', None)
        s1 = getattr(lead, 'documentation_stage1', None)

        def name(u):
            return (f"{u.first_name} {u.last_name}".strip() or u.username) if u else None

        return {
            'id': lead.id,
            'first_name': lead.first_name,
            'last_name': lead.last_name,
            'phone': lead.phone,
            'email': lead.email,
            'location': lead.company,
            'installation_location': lead.installation_location,
            'product_name': lead.product.name if lead.product else None,
            'value': lead.value,
            'status': lead.status,
            'bde_name': name(lead.bde),
            'documentation_staff_name': name(lead.documentation_staff),
            'accounts_staff': lead.accounts_staff_id,
            'accounts_staff_name': name(lead.accounts_staff),
            'pushed_at': lead.pushed_to_accounts_at,
            'stage1_complete': bool(s1 and s1.is_complete),
            'payment_verification': PaymentVerificationSerializer(pv, context={'request': request}).data if pv else None,
            'payment_complete': bool(pv and pv.is_complete),
            'can_edit_payment': can_edit_payment_verification(request.user, lead),
            'can_assign': can_assign_accounts(request.user),
            'can_reopen_payment': can_assign_accounts(request.user),
        }

    @action(detail=False, methods=['get'], url_path='accounts')
    def accounts(self, request):
        """Accounts team's queue: leads moved to accounts for payment verification."""
        from .access import can_access_accounts
        user = request.user
        if not can_access_accounts(user):
            return Response({'error': 'You do not have access to accounts.'},
                            status=status.HTTP_403_FORBIDDEN)
        qs = (Lead.objects.filter(pushed_to_accounts=True)
              .select_related('product', 'bde', 'documentation_staff', 'accounts_staff',
                              'payment_verification', 'documentation_stage1')
              .order_by('-pushed_to_accounts_at'))
        # Plain accounts staff see only the leads assigned to them.
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'accounts_staff'):
            qs = qs.filter(accounts_staff=user)
        return Response([self._accounts_payload(lead, request) for lead in qs])

    @action(detail=True, methods=['get'], url_path='accounts-detail')
    def accounts_detail(self, request, pk=None):
        """Full accounts view for one lead (customer info + payment verification)."""
        from .access import can_access_accounts
        user = request.user
        if not can_access_accounts(user):
            return Response({'error': 'You do not have access to accounts.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_accounts:
            return Response({'error': 'This lead has not been moved to accounts.'},
                            status=status.HTTP_404_NOT_FOUND)
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'accounts_staff'
                and lead.accounts_staff_id != user.id):
            return Response({'error': 'This lead is not assigned to you.'},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(self._accounts_payload(lead, request))

    @action(detail=True, methods=['get', 'patch'], url_path='payment-verification')
    def payment_verification(self, request, pk=None):
        """Get or update a lead's payment verification."""
        from .access import can_access_accounts, can_edit_payment_verification
        lead = self.get_object()
        if not can_access_accounts(request.user):
            return Response({'error': 'You do not have access to accounts.'},
                            status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_accounts:
            return Response({'error': 'This lead has not been moved to accounts.'},
                            status=status.HTTP_404_NOT_FOUND)
        pv, _ = PaymentVerification.objects.get_or_create(lead=lead)
        if request.method == 'GET':
            return Response(PaymentVerificationSerializer(pv, context={'request': request}).data)
        if not can_edit_payment_verification(request.user, lead):
            return Response({'error': 'You do not have permission to edit this payment verification.'},
                            status=status.HTTP_403_FORBIDDEN)
        if pv.is_complete:
            return Response({'error': 'Payment verification is already completed and locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = PaymentVerificationSerializer(pv, data=request.data, partial=True,
                                                   context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='complete-payment-verification')
    def complete_payment_verification(self, request, pk=None):
        """Mark a lead's payment verification complete (locks it)."""
        from .access import can_edit_payment_verification
        lead = self.get_object()
        if not can_edit_payment_verification(request.user, lead):
            return Response({'error': 'You do not have permission to complete this payment verification.'},
                            status=status.HTTP_403_FORBIDDEN)
        pv, _ = PaymentVerification.objects.get_or_create(lead=lead)
        if pv.is_complete:
            return Response({'error': 'Payment verification is already completed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        missing = pv.missing_required_fields()
        if missing:
            return Response({'error': 'Select a payment mode (and UTR details for non-cash payments) first.',
                             'missing': missing}, status=status.HTTP_400_BAD_REQUEST)
        pv.is_complete = True
        pv.completed_at = timezone.now()
        pv.completed_by = request.user if request.user.is_authenticated else None
        pv.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        actor = (f"{request.user.first_name} {request.user.last_name}".strip()
                 or request.user.username) if request.user.is_authenticated else 'accounts'
        ActivityLog.objects.create(
            activity_type='note_added',
            description=f"Payment verification completed by {actor}.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead,
            extra={'auto_generated': True},
        )
        return Response(self._accounts_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='reopen-payment-verification')
    def reopen_payment_verification(self, request, pk=None):
        """Accounts admin re-opens a completed payment verification for editing."""
        from .access import can_assign_accounts
        lead = self.get_object()
        if not can_assign_accounts(request.user):
            return Response({'error': 'Only accounts admins can reopen a completed payment verification.'},
                            status=status.HTTP_403_FORBIDDEN)
        pv = getattr(lead, 'payment_verification', None)
        if not pv or not pv.is_complete:
            return Response({'error': 'Payment verification is not completed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        pv.is_complete = False
        pv.completed_at = None
        pv.completed_by = None
        pv.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        return Response(self._accounts_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='assign-accounts')
    def assign_accounts(self, request, pk=None):
        """Admin/GM assigns (or clears) the accounts staff handling this lead."""
        from users.models import User
        from .access import can_assign_accounts
        lead = self.get_object()
        if not can_assign_accounts(request.user):
            return Response({'error': 'You do not have permission to assign accounts staff.'},
                            status=status.HTTP_403_FORBIDDEN)
        staff_id = request.data.get('staff')
        if not staff_id:
            lead.accounts_staff = None
        else:
            try:
                lead.accounts_staff = User.objects.get(pk=staff_id)
            except User.DoesNotExist:
                return Response({'error': 'Accounts staff not found.'}, status=status.HTTP_404_NOT_FOUND)
        lead.save(update_fields=['accounts_staff'])
        return Response(self._accounts_payload(lead, request))

    def get_queryset(self):
        user = self.request.user
        base = Lead.objects.select_related('assigned_to')
        if user.sees_all_leads:
            # superadmin / admin / coo / sales & documentation managers / documentation staff
            queryset = base.all().order_by('-created_at')
        elif user.branch_scoped:
            # Branch manager: leads of users in their branch (+ their own + unassigned)
            from django.db.models import Q
            queryset = base.filter(
                Q(assigned_to=user) |
                Q(assigned_to__isnull=True) |
                Q(assigned_to__branch=user.branch)
            ).distinct().order_by('-created_at')
        else:
            # Tele caller: leads assigned to them. BDE: leads handed off to them as BDE.
            from django.db.models import Q
            queryset = base.filter(Q(assigned_to=user) | Q(bde=user)).distinct().order_by('-created_at')
        
        # Filter by "Assigned to Me"
        assigned_to_me = self.request.query_params.get('assigned_to_me')
        if assigned_to_me == 'true' or assigned_to_me == '1':
            queryset = queryset.filter(assigned_to=self.request.user)

        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            statuses = status_param.split(',')
            queryset = queryset.filter(status__in=statuses)
        
        # Filter by source
        source = self.request.query_params.get('source')
        if source:
            queryset = queryset.filter(source=source)

        # Filter by product
        product_id = self.request.query_params.get('product')
        if product_id:
            if product_id == 'none':
                queryset = queryset.filter(product__isnull=True)
            else:
                queryset = queryset.filter(product_id=product_id)

        # Filter by campaign
        campaign_id = self.request.query_params.get('campaign')
        if campaign_id:
            if campaign_id == 'none':
                queryset = queryset.filter(campaigns_set__isnull=True)
            else:
                queryset = queryset.filter(campaigns_set__id=campaign_id)
                
        # Filter by meta_campaign_name
        meta_campaign_name = self.request.query_params.get('meta_campaign_name')
        if meta_campaign_name:
            queryset = queryset.filter(meta_campaign_name__icontains=meta_campaign_name)

        # Filter by assignee
        assigned_to = self.request.query_params.get('assigned_to')
        if assigned_to:
            if assigned_to == 'unassigned':
                queryset = queryset.filter(assigned_to__isnull=True)
            else:
                queryset = queryset.filter(assigned_to_id=assigned_to)
        
        # Filter by date range
        created_after = self.request.query_params.get('created_after')
        if created_after:
            queryset = queryset.filter(created_at__gte=f"{created_after} 00:00:00")
            
        created_before = self.request.query_params.get('created_before')
        if created_before:
            queryset = queryset.filter(created_at__lte=f"{created_before} 23:59:59")
            
        modified_after = self.request.query_params.get('modified_after')
        if modified_after:
            queryset = queryset.filter(status_changed_at__gte=f"{modified_after} 00:00:00")
            
        modified_before = self.request.query_params.get('modified_before')
        if modified_before:
            queryset = queryset.filter(status_changed_at__lte=f"{modified_before} 23:59:59")
            
        modified_empty = self.request.query_params.get('modified_empty')
        if modified_empty == 'true':
            queryset = queryset.filter(status_changed_at__isnull=True)
        elif modified_empty == 'false':
            queryset = queryset.filter(status_changed_at__isnull=False)

        # Advanced Filters
        value_min = self.request.query_params.get('value_min')
        if value_min is not None and value_min != "":
            try:
                queryset = queryset.filter(value__gte=float(value_min))
            except ValueError:
                pass

        value_max = self.request.query_params.get('value_max')
        if value_max is not None and value_max != "":
            try:
                queryset = queryset.filter(value__lte=float(value_max))
            except ValueError:
                pass

        company = self.request.query_params.get('company')
        if company:
            queryset = queryset.filter(company__icontains=company)
            
        # Status Change History Filter
        status_change_from = self.request.query_params.get('status_change_from')
        status_change_to = self.request.query_params.get('status_change_to')
        status_change_after = self.request.query_params.get('status_change_after')
        status_change_before = self.request.query_params.get('status_change_before')

        if status_change_from or status_change_to or status_change_after or status_change_before:
            logs = ActivityLog.objects.filter(activity_type='lead_status_change')
            
            if status_change_from and status_change_from != 'all':
                logs = logs.filter(extra__old_status=status_change_from)
            if status_change_to and status_change_to != 'all':
                logs = logs.filter(extra__new_status=status_change_to)
                
            if status_change_after:
                logs = logs.filter(created_at__gte=f"{status_change_after} 00:00:00")
            if status_change_before:
                logs = logs.filter(created_at__lte=f"{status_change_before} 23:59:59")
                
            # Filter the main queryset to leads that have at least one matching log
            lead_ids = logs.values_list('lead_id', flat=True)
            queryset = queryset.filter(id__in=lead_ids)

        # Activity Filters
        activity_type = self.request.query_params.get('activity_type')
        has_activity_days = self.request.query_params.get('has_activity_days')
        no_activity_days = self.request.query_params.get('no_activity_days')

        if has_activity_days or no_activity_days:
            from datetime import timedelta
            now = timezone.now()
            
            activity_qs = ActivityLog.objects.all()
            if activity_type and activity_type != 'all':
                activity_qs = activity_qs.filter(activity_type=activity_type)
            
            if has_activity_days:
                try:
                    days = int(has_activity_days)
                    threshold = now - timedelta(days=days)
                    active_lead_ids = activity_qs.filter(created_at__gte=threshold).values_list('lead_id', flat=True)
                    queryset = queryset.filter(id__in=active_lead_ids)
                except ValueError:
                    pass
                    
            if no_activity_days:
                try:
                    days = int(no_activity_days)
                    threshold = now - timedelta(days=days)
                    active_lead_ids = activity_qs.filter(created_at__gte=threshold).values_list('lead_id', flat=True)
                    queryset = queryset.exclude(id__in=active_lead_ids)
                except ValueError:
                    pass
        
        # Search global
        search = self.request.query_params.get('search')
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )

        # Prefetch activity_logs and annotate latest_activity_date
        from django.db.models import Max, F
        queryset = queryset.prefetch_related('activity_logs', 'tasks')
        queryset = queryset.annotate(latest_activity_date=Max('activity_logs__created_at'))

        # Ordering
        ordering = self.request.query_params.get('ordering')
        if ordering:
            if ordering == 'activity':
                queryset = queryset.order_by(F('latest_activity_date').asc(nulls_last=True))
            elif ordering == '-activity':
                queryset = queryset.order_by(F('latest_activity_date').desc(nulls_last=True))
            elif ordering == 'first_name':
                queryset = queryset.order_by('first_name', 'last_name')
            elif ordering == '-first_name':
                queryset = queryset.order_by('-first_name', '-last_name')
            elif ordering in ['value', '-value']:
                queryset = queryset.order_by(ordering)
            else:
                queryset = queryset.order_by('-created_at')
        else:
            queryset = queryset.order_by('-created_at')
        
        return queryset

    def perform_create(self, serializer):
        instance = serializer.save()
        
        ActivityLog.objects.create(
            activity_type='lead_created',
            description=f"New lead added: {instance.first_name} {instance.last_name}",
            actor=self.request.user,
            lead=instance,
        )
        if instance.notes and instance.notes.strip():
            ActivityLog.objects.create(
                activity_type='note_added',
                description=f"Note added to {instance.first_name} {instance.last_name}",
                actor=self.request.user,
                lead=instance,
                extra={'note': instance.notes},
            )
        
        # Fire automation triggers — assignment handled via ai_auto_assign automation action
        try:
            from automations.engine import fire_trigger
            fire_trigger('lead_created', instance)
        except Exception as e:
            logger.exception(f"Automation fire_trigger failed on lead #{instance.pk}: {e}")


    def perform_update(self, serializer):
        old_status = serializer.instance.status
        old_notes  = serializer.instance.notes or ""
        
        if 'status' in serializer.validated_data and old_status != serializer.validated_data['status']:
            instance = serializer.save(status_changed_at=timezone.now())
        else:
            instance = serializer.save()
            
        # Log status change
        status_changed = False
        if 'status' in serializer.validated_data and old_status != instance.status:
            status_changed = True
            from organization.utils import get_org_settings
            org = get_org_settings()
            custom_labels = {}
            if org.custom_lead_statuses:
                for item in org.custom_lead_statuses:
                    if isinstance(item, dict) and 'value' in item and 'label' in item:
                        custom_labels[item['value']] = item['label']
            
            old_label = custom_labels.get(old_status) or STATUS_LABELS.get(old_status, old_status)
            new_label = custom_labels.get(instance.status) or STATUS_LABELS.get(instance.status, instance.status)
            ActivityLog.objects.create(
                activity_type='lead_status_change',
                description=f"{instance.first_name} {instance.last_name}: {old_label} → {new_label}",
                actor=self.request.user,
                lead=instance,
                extra={'old_status': old_status, 'new_status': instance.status},
            )
        # Log note change
        new_notes = instance.notes or ""
        if old_notes != new_notes and new_notes.strip():
            added_note = new_notes
            if old_notes and new_notes.startswith(old_notes):
                added_note = new_notes[len(old_notes):].strip()
            ActivityLog.objects.create(
                activity_type='note_added',
                description=f"Note updated on {instance.first_name} {instance.last_name}",
                actor=self.request.user,
                lead=instance,
                extra={'note': added_note},
            )
        
        # Fire automation triggers
        try:
            from automations.engine import fire_trigger
            if status_changed:
                fire_trigger('lead_status_changed', instance, {
                    'old_status': old_status,
                    'new_status': instance.status,
                })
            fire_trigger('lead_updated', instance)
        except Exception as e:
            logger.exception(f"Automation fire_trigger failed on lead #{instance.pk}: {e}")

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Returns all ActivityLog entries for a specific lead."""
        lead = self.get_object()
        logs = ActivityLog.objects.filter(lead=lead).order_by('-created_at')
        data = []
        for log in logs:
            actor_name = None
            if log.actor:
                actor_name = f"{log.actor.first_name} {log.actor.last_name}".strip() or log.actor.username
            data.append({
                "id": log.id,
                "type": log.activity_type,
                "description": log.description,
                "actor": actor_name,
                "timestamp": timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                "extra": log.extra,
            })
        return Response(data)

    @action(detail=False, methods=['get'])
    def csv_template(self, request):
        """Returns a blank CSV template for lead import."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="leads_template.csv"'
        writer = csv.writer(response)
        writer.writerow(['first_name', 'last_name', 'email', 'phone', 'source', 'status'])
        writer.writerow(['John', 'Doe', 'john@example.com', '1234567890', 'manual', 'new'])
        return response

    @action(detail=False, methods=['post'])
    def bulk_upload(self, request):
        """Handles bulk uploads from a CSV file."""
        if 'file' not in request.FILES:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['file']
        campaign_id = request.data.get('campaign_id')
        
        if not file.name.endswith('.csv'):
            return Response({'error': 'Please upload a CSV file.'}, status=status.HTTP_400_BAD_REQUEST)

        # Support multiple encodings (UTF-8, Latin-1, etc.)
        file_bytes = file.read()
        try:
            decoded_file = file_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                decoded_file = file_bytes.decode('latin-1')
            except UnicodeDecodeError:
                return Response({'error': 'Could not decode the CSV file. Please ensure it is saved in UTF-8 or Latin-1 format.'}, status=status.HTTP_400_BAD_REQUEST)

        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)

        fieldnames = reader.fieldnames or []
        
        # Build a mapping of normalized field names to original CSV headers
        def normalize_header(h):
            return h.lower().replace('_', '').replace(' ', '').replace('-', '').replace('*', '').strip()

        header_map = {}
        for h in fieldnames:
            norm = normalize_header(h)
            header_map[norm] = h

        # Helper to get value from row using normalized variants
        def get_row_value(row, keys_to_try):
            for k in keys_to_try:
                norm_k = normalize_header(k)
                if norm_k in header_map:
                    val = row.get(header_map[norm_k])
                    if val is not None:
                        return val.strip()
            return ''

        first_name_keys = ['first_name', 'first name', 'firstname', 'first', 'name']
        last_name_keys = ['last_name', 'last name', 'lastname', 'last']
        email_keys = ['email', 'email id', 'email_id', 'email address', 'emailaddress']
        phone_keys = ['phone', 'phone number', 'phonenumber', 'phone_number', 'mobile', 'mobile number', 'mobilenumber', 'contact', 'contact number']
        source_keys = ['source', 'lead source', 'lead_source']
        status_keys = ['status', 'lead status', 'lead_status']

        leads_to_create = []
        for row in reader:
            first_name = get_row_value(row, first_name_keys)
            if not first_name:
                continue # Skip rows without a first name

            last_name = get_row_value(row, last_name_keys)
            email = get_row_value(row, email_keys)
            phone = get_row_value(row, phone_keys)
            source = get_row_value(row, source_keys) or 'manual'
            status_val = get_row_value(row, status_keys) or 'new'

            leads_to_create.append(Lead(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                source=source,
                status=status_val
            ))
            if len(leads_to_create) > 5000:
                return Response({'error': 'Maximum 5000 leads can be imported at a time.'}, status=status.HTTP_400_BAD_REQUEST)

        if leads_to_create:
            created_leads = Lead.objects.bulk_create(leads_to_create)
            
            if campaign_id:
                try:
                    from campaigns.models import Campaign
                    campaign = Campaign.objects.get(id=campaign_id)
                    campaign.leads.add(*created_leads)
                except Exception as e:
                    logger.error(f"Failed to link bulk imported leads to campaign {campaign_id}: {e}")
                    
            return Response({'message': f'Successfully created {len(leads_to_create)} leads.'})
        
        return Response({'error': 'No valid leads found in the CSV file. Please make sure the CSV has a column for First Name.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """Exports currently filtered leads to CSV."""
        queryset = self.get_queryset()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="leads_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['First Name', 'Last Name', 'Email', 'Phone', 'Company', 'Source', 'Status', 'Value', 'Assigned To', 'Created At'])
        
        for lead in queryset:
            writer.writerow([
                lead.first_name,
                lead.last_name,
                lead.email,
                lead.phone,
                lead.company,
                lead.source,
                lead.status,
                lead.value,
                lead.assigned_to.username if lead.assigned_to else 'Unassigned',
                timezone.localtime(lead.created_at).strftime('%Y-%m-%d %H:%M:%S')
            ])
            
        return response

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """Deletes multiple leads at once."""
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'No lead IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Only allow deleting from the user's accessible set
        queryset = self.get_queryset().filter(id__in=ids)
        count = queryset.count()
        queryset.delete()
        
        return Response({'message': f'Successfully deleted {count} leads.'})

    @action(detail=False, methods=['post'])
    def bulk_assign(self, request):
        """Assigns multiple leads to a user at once."""
        ids = request.data.get('ids', [])
        user_id = request.data.get('user_id')
        
        if not ids or user_id is None:
            return Response({'error': 'IDs and user_id are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from users.models import User
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Target user not found'}, status=status.HTTP_404_NOT_FOUND)

        queryset = self.get_queryset().filter(id__in=ids)
        count = queryset.update(assigned_to=target_user)
        
        return Response({'message': f'Successfully assigned {count} leads to {target_user.username}.'})

    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        """Updates multiple leads with provided fields at once."""
        ids = request.data.get('ids', [])
        update_data = request.data.get('data', {})
        
        if not ids or not update_data:
            return Response({'error': 'IDs and update data are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        allowed_fields = ['status', 'source']
        
        valid_data = {}
        for k, v in update_data.items():
            if k in allowed_fields:
                valid_data[k] = v
            elif k == 'product_id':
                valid_data['product_id'] = v if v else None
            elif k == 'assigned_to_id':
                valid_data['assigned_to_id'] = v if v else None
                
        # Apply status_changed_at if status is changing
        if 'status' in valid_data:
            valid_data['status_changed_at'] = timezone.now()

        queryset = self.get_queryset().filter(id__in=ids)
        count = 0
        if valid_data:
            count = queryset.update(**valid_data)
        
        # Handle Campaign ManyToMany linkage
        if 'campaign_id' in update_data and update_data['campaign_id']:
            try:
                from campaigns.models import Campaign
                campaign = Campaign.objects.get(id=update_data['campaign_id'])
                campaign.leads.add(*list(queryset))
                if count == 0:
                    count = queryset.count()
            except Exception:
                pass

        if not valid_data and 'campaign_id' not in update_data:
            return Response({'error': 'No valid fields to update'}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({'message': f'Successfully updated {count} leads.'})

    @action(detail=True, methods=['post', 'get'])
    def attachments(self, request, pk=None):
        lead = self.get_object()
        
        if request.method == 'GET':
            attachments = lead.attachments.all().order_by('-uploaded_at')
            return Response(LeadAttachmentSerializer(attachments, many=True, context={'request': request}).data)
            
        elif request.method == 'POST':
            file = request.FILES.get('file')
            if not file:
                return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
                
            MAX_SIZE = 50 * 1024 * 1024 # 50MB
            if file.size > MAX_SIZE:
                return Response({'error': 'File size exceeds 50MB limit'}, status=status.HTTP_400_BAD_REQUEST)
                
            attachment = LeadAttachment.objects.create(
                lead=lead,
                file=file,
                file_name=file.name,
                uploaded_by=request.user
            )
            
            # Log activity
            ActivityLog.objects.create(
                activity_type='note_added',
                description=f'Uploaded attachment: {file.name}',
                actor=request.user,
                lead=lead
            )
            
            return Response(LeadAttachmentSerializer(attachment, context={'request': request}).data)

    @action(detail=True, methods=['delete'], url_path='attachments/(?P<attachment_id>[0-9]+)')
    def delete_attachment(self, request, pk=None, attachment_id=None):
        lead = self.get_object()
        try:
            attachment = lead.attachments.get(id=attachment_id)
        except LeadAttachment.DoesNotExist:
            return Response({'error': 'Attachment not found'}, status=status.HTTP_404_NOT_FOUND)

        # Delete file from disk too
        try:
            attachment.file.delete(save=False)
        except Exception:
            pass

        file_name = attachment.file_name
        attachment.delete()

        ActivityLog.objects.create(
            activity_type='note_added',
            description=f'Deleted attachment: {file_name}',
            actor=request.user,
            lead=lead
        )

        return Response({'message': 'Attachment deleted'}, status=status.HTTP_204_NO_CONTENT)

from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework.views import APIView

class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        user = request.user
        
        if user.is_staff or user.is_general_manager:
            base_qs = Lead.objects.all()
        elif user.is_manager:
            from users.models import WorkspaceTeam
            managed_teams = WorkspaceTeam.objects.filter(manager=user)
            team_members_ids = []
            for team in managed_teams:
                team_members_ids.extend(team.members.values_list('id', flat=True))
            
            base_qs = Lead.objects.filter(
                Q(assigned_to=user) | 
                Q(assigned_to__isnull=True) | 
                Q(assigned_to__id__in=team_members_ids)
            ).distinct()
        else:
            base_qs = Lead.objects.filter(assigned_to=user)
        
        total_leads = base_qs.count()
        new_today = base_qs.filter(created_at__date=today).count()
        
        # Pipeline breakdown
        pipeline_data = base_qs.values('status').annotate(count=Count('id'))
        pipeline = {item['status']: item['count'] for item in pipeline_data}
        
        # Total Pipeline Value (Rupees)
        total_value = base_qs.aggregate(total=Sum('value'))['total'] or 0
        
        # Revenue Generated (Enrolled & Partially Paid Leads)
        won_qs = base_qs.filter(status__in=['enrolled', 'partially_paid'])
        total_revenue = won_qs.aggregate(total=Sum('value'))['total'] or 0
        
        # Team/Member Performance (Only for Admin/Manager)
        performance_stats = []
        team_stats = []
        if user.is_staff or user.is_general_manager or user.is_manager:
            from users.models import User as WorkspaceUser, WorkspaceTeam
            
            # Member Stats
            if user.is_staff or user.is_general_manager:
                users_to_check = WorkspaceUser.objects.filter(is_active=True)
                teams_to_check = WorkspaceTeam.objects.all()
            else:
                managed_teams = WorkspaceTeam.objects.filter(manager=user)
                team_members_ids = []
                for team in managed_teams:
                    team_members_ids.extend(team.members.values_list('id', flat=True))
                users_to_check = WorkspaceUser.objects.filter(Q(id=user.id) | Q(id__in=team_members_ids)).distinct()
                # Managers can see all teams for comparison as requested
                teams_to_check = WorkspaceTeam.objects.all()
            
            # Member Stats using ORM Annotation
            users_with_stats = users_to_check.annotate(
                calc_leads_count=Count('assigned_leads'),
                calc_pipeline_value=Sum('assigned_leads__value'),
                calc_won_count=Count('assigned_leads', filter=Q(assigned_leads__status__in=['enrolled', 'partially_paid'])),
                calc_won_value=Sum('assigned_leads__value', filter=Q(assigned_leads__status__in=['enrolled', 'partially_paid']))
            )
            for u in users_with_stats:
                performance_stats.append({
                    "id": u.id,
                    "name": f"{u.first_name} {u.last_name}".strip() or u.username,
                    "role": "Admin" if u.is_staff else ("General Manager" if u.is_general_manager else ("Manager" if u.is_manager else "Agent")),
                    "leads_count": u.calc_leads_count or 0,
                    "pipeline_value": float(u.calc_pipeline_value or 0),
                    "won_count": u.calc_won_count or 0,
                    "won_value": float(u.calc_won_value or 0)
                })
            
            # Team Stats using ORM Annotation
            teams_with_stats = teams_to_check.annotate(
                calc_leads_count=Count('members__assigned_leads'),
                calc_pipeline_value=Sum('members__assigned_leads__value'),
                calc_won_count=Count('members__assigned_leads', filter=Q(members__assigned_leads__status__in=['enrolled', 'partially_paid'])),
                calc_won_value=Sum('members__assigned_leads__value', filter=Q(members__assigned_leads__status__in=['enrolled', 'partially_paid']))
            )
            for t in teams_with_stats:
                team_stats.append({
                    "id": t.id,
                    "name": t.name,
                    "leads_count": t.calc_leads_count or 0,
                    "pipeline_value": float(t.calc_pipeline_value or 0),
                    "won_count": t.calc_won_count or 0,
                    "won_value": float(t.calc_won_value or 0)
                })

        # Recent Activities from ActivityLog (last 25)
        recent_logs = ActivityLog.objects.select_related('actor').order_by('-created_at')[:25]
        recent_activities = []
        for log in recent_logs:
            recent_activities.append({
                "id": log.id,
                "type": log.activity_type,
                "description": log.description,
                "user": (f"{log.actor.first_name} {log.actor.last_name}".strip() or log.actor.username) if log.actor else "System",
                "timestamp": timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                "extra": log.extra,
            })

        # Generate last 6 months data for charts
        six_months_revenue = []
        six_months_leads = []
        now = timezone.now()
        for i in range(5, -1, -1):
            target_month = now.month - i
            target_year = now.year
            if target_month <= 0:
                target_month += 12
                target_year -= 1
            
            # Start of this target month
            start_dt = timezone.datetime(target_year, target_month, 1, tzinfo=now.tzinfo)
            # Start of next month
            if target_month == 12:
                next_month = 1
                next_year = target_year + 1
            else:
                next_month = target_month + 1
                next_year = target_year
            end_dt = timezone.datetime(next_year, next_month, 1, tzinfo=now.tzinfo)
            
            month_label = start_dt.strftime("%b %y")
            
            # Lead volume
            l_count = base_qs.filter(created_at__gte=start_dt, created_at__lt=end_dt).count()
            six_months_leads.append({"name": month_label, "Leads": l_count})
            
            # Revenue (Enrolled within this month)
            m_rev = won_qs.filter(
                Q(status_changed_at__gte=start_dt, status_changed_at__lt=end_dt) |
                (Q(status_changed_at__isnull=True) & Q(created_at__gte=start_dt, created_at__lt=end_dt))
            ).aggregate(total=Sum('value'))['total'] or 0
            
            six_months_revenue.append({"name": month_label, "Revenue": float(m_rev)})

        return Response({
            "total_leads": total_leads,
            "new_today": new_today,
            "pipeline_value": float(total_value),
            "total_revenue": float(total_revenue),
            "pipeline": pipeline,
            "recent_activities": recent_activities,
            "performance_stats": performance_stats,
            "team_stats": team_stats,
            "revenue_over_time": six_months_revenue,
            "leads_over_time": six_months_leads
        })

class LeaderboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        period = request.query_params.get('period', 'all_time') # daily, monthly, all_time
        today = timezone.localdate()
        
        # Build the filter for "won" leads
        won_filter = Q(assigned_leads__status__in=['enrolled', 'partially_paid'])
        
        if period == 'daily':
            won_filter &= (
                Q(assigned_leads__status_changed_at__date=today) | 
                (Q(assigned_leads__status_changed_at__isnull=True) & Q(assigned_leads__created_at__date=today))
            )
        elif period == 'monthly':
            current_month = today.month
            current_year = today.year
            won_filter &= (
                Q(assigned_leads__status_changed_at__month=current_month, assigned_leads__status_changed_at__year=current_year) |
                (Q(assigned_leads__status_changed_at__isnull=True) & Q(assigned_leads__created_at__month=current_month, assigned_leads__created_at__year=current_year))
            )

        # Single annotated query instead of N+1 loop
        from users.models import User as WorkspaceUser
        from django.db.models.functions import Coalesce
        from decimal import Decimal
        # Coalesce revenue to 0 so users with no won leads don't get a NULL,
        # which PostgreSQL sorts FIRST on a descending order (pushing zero-sales
        # agents to the top of the leaderboard).
        users = WorkspaceUser.objects.filter(is_active=True).annotate(
            closed_sales=Count('assigned_leads', filter=won_filter),
            revenue=Coalesce(Sum('assigned_leads__value', filter=won_filter), Decimal('0'))
        ).order_by('-revenue', '-closed_sales', 'first_name', 'last_name')
        
        leaderboard = []
        for u in users:
            leaderboard.append({
                "id": u.id,
                "name": f"{u.first_name} {u.last_name}".strip() or u.username,
                "role": "Admin" if u.is_staff else ("General Manager" if u.is_general_manager else ("Manager" if u.is_manager else "Agent")),
                "closed_sales": u.closed_sales or 0,
                "revenue": float(u.revenue or 0)
            })
        
        return Response({
            "period": period,
            "leaderboard": leaderboard
        })

class ConvertedAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import F, Avg, ExpressionWrapper, DurationField
        user = request.user
        
        # Consistent permission scoping
        if user.is_staff or user.is_general_manager:
            base_qs = Lead.objects.all()
        elif user.is_manager:
            from django.db.models import Q
            from users.models import WorkspaceTeam
            managed_teams = WorkspaceTeam.objects.filter(manager=user)
            team_members_ids = []
            for team in managed_teams:
                team_members_ids.extend(team.members.values_list('id', flat=True))
            
            base_qs = Lead.objects.filter(
                Q(assigned_to=user) | 
                Q(assigned_to__isnull=True) | 
                Q(assigned_to__id__in=team_members_ids)
            ).distinct()
        else:
            base_qs = Lead.objects.filter(assigned_to=user)

        # Base QS for converted leads
        won_qs = base_qs.filter(status__in=['enrolled', 'partially_paid'])

        # Aggregate everything in a single DB query
        agg = won_qs.aggregate(
            total_conversions=Count('id'),
            total_revenue=Sum('value'),
        )

        # Average time to convert — use DB-level aggregation instead of Python loop
        time_to_convert_days = 0
        avg_result = won_qs.filter(
            status_changed_at__isnull=False,
            created_at__isnull=False
        ).annotate(
            conversion_duration=ExpressionWrapper(
                F('status_changed_at') - F('created_at'),
                output_field=DurationField()
            )
        ).aggregate(avg_duration=Avg('conversion_duration'))
        
        if avg_result['avg_duration']:
            time_to_convert_days = round(avg_result['avg_duration'].total_seconds() / 86400, 1)

        # Top Sources
        sources_data = won_qs.values('source').annotate(count=Count('id')).order_by('-count')
        sources = [{"source": item['source'] or 'manual', "count": item['count']} for item in sources_data]

        return Response({
            "total_conversions": agg['total_conversions'] or 0,
            "total_revenue": float(agg['total_revenue'] or 0),
            "avg_conversion_days": time_to_convert_days,
            "top_sources": sources
        })

class IntegrationSettingsViewSet(viewsets.ModelViewSet):
    """
    Manage multiple named Meta integrations (one per branch).
    Full CRUD: list/create/update/delete integrations, plus a per-integration sync.
    """
    serializer_class = IntegrationSettingsSerializer
    permission_classes = [IsAdminOnly]
    queryset = IntegrationSettings.objects.all()

    @action(detail=False, methods=['get'])
    def meta_summary(self, request):
        from .meta_integration import meta_summary

        return Response(meta_summary())

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        from .meta_integration import import_meta_leads

        integration = self.get_object()
        result = import_meta_leads(
            integration,
            actor=request.user,
            page_id=request.data.get('page_id', ''),
            form_id=request.data.get('form_id', ''),
            limit=request.data.get('limit', 100),
        )
        response_status = status.HTTP_200_OK if result.imported or result.skipped or not result.errors else status.HTTP_400_BAD_REQUEST
        return Response(result.as_dict(), status=response_status)

class ProductViewSet(viewsets.ModelViewSet):
    """
    Manage products that can be associated with leads.
    """
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]
