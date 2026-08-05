from rest_framework import viewsets, status, permissions, parsers
from core.permissions import IsAdminOnly
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import HttpResponse
import csv
import io
import logging
from .models import Lead, IntegrationSettings, ActivityLog, LeadAttachment, Product, SiteVisit, DocumentationStage1, SiteVisitDocument, DocumentationStage1Document, LeadDocument, PaymentVerification, PurchaseLogistics, Project, ProjectDocument, ServiceEntry, TeamStatsConfig, BalancePayment, DocumentationStage2, DocumentationStage2Document, LiasoningService, LiasoningDocument, Warranty, WarrantyDocument, EmergencyService, EmergencyServiceDocument, PeriodicMaintenance, MaintenanceVisit, MaintenanceVisitDocument, ModuleSeen, ReceiptVoucher
from .serializers import LeadSerializer, IntegrationSettingsSerializer, LeadAttachmentSerializer, ProductSerializer, SiteVisitSerializer, DocumentationStage1Serializer, SiteVisitDocumentSerializer, DocumentationStage1DocumentSerializer, PaymentVerificationSerializer, PurchaseLogisticsSerializer, ProjectSerializer, ProjectDocumentSerializer, ServiceEntrySerializer, BalancePaymentSerializer, DocumentationStage2Serializer, DocumentationStage2DocumentSerializer, LiasoningServiceSerializer, LiasoningDocumentSerializer, WarrantySerializer, WarrantyDocumentSerializer, EmergencyServiceSerializer, EmergencyServiceDocumentSerializer, PeriodicMaintenanceSerializer, MaintenanceVisitSerializer, MaintenanceVisitDocumentSerializer, ReceiptVoucherSerializer
from .document_kinds import SHARED_KIND_LABELS, kind_for
# Module-level: the nine module payloads all report this one rule, and
# access.py imports nothing, so there is no cycle to dodge.
from .access import can_cleanup_deleted_lead
from django.utils import timezone

logger = logging.getLogger(__name__)


def fire_automation(event, obj, context=None):
    """Fire an automation trigger without ever breaking the calling view."""
    try:
        from automations.engine import fire_trigger
        fire_trigger(event, obj, context or {})
    except Exception as e:
        logger.exception(f"Automation fire_trigger({event}) failed on {obj.__class__.__name__} #{obj.pk}: {e}")


STATUS_LABELS = {
    'new': 'New', 'follow_up': 'Follow Up', 'positive': 'Positive',
    'interested': 'Interested', 'not_interested': 'Not Interested',
    'converted': 'Converted',
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
    ('purchase_order', 'Purchase Order'),
    ('kseb_feasibility_receipt', 'KSEB Feasibility Receipt'),
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
    ('le_test_cum_completion_report', 'Test cum Completion Report'), ('le_sketch', 'Sketch'),
    ('mnre_aadhaar', 'Aadhaar'), ('mnre_pan', 'PAN'), ('mnre_passbook', 'Passbook'),
    ('mnre_purchase_order', 'Purchase Order'), ('mnre_kseb_bill', 'KSEB Bill'),
    ('loan_aadhaar', 'Aadhaar'), ('loan_pan', 'PAN'), ('loan_passbook', 'Passbook'),
    ('loan_land_tax', 'Land Tax'), ('loan_itr', 'ITR'),
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


def _least_recently_assigned_purchase(candidates):
    """Round-robin pick among purchase staff (least recently assigned goes next)."""
    best, best_time = None, None
    floor = timezone.datetime.min.replace(tzinfo=timezone.utc)
    for u in candidates:
        last = (Lead.objects.filter(purchase_staff=u)
                .order_by('-pushed_to_purchase_at').first())
        t = last.pushed_to_purchase_at if (last and last.pushed_to_purchase_at) else floor
        if best is None or t < best_time:
            best, best_time = u, t
    return best


def auto_assign_purchase(lead):
    """On handoff to purchase & logistics, round-robin assign a purchase_staff
    member: prefer the BDE's team's purchase staff, else any active purchase staff.
    Respects an existing assignment. Returns the assignee or None."""
    from users.models import User, ROLE_PURCHASE_STAFF
    if lead.purchase_staff_id:
        return None
    team = lead.bde.team if (lead.bde and lead.bde.team_id) else None
    candidates = list(team.members.filter(role=ROLE_PURCHASE_STAFF, is_active=True)) if team else []
    if not candidates:
        candidates = list(User.objects.filter(role=ROLE_PURCHASE_STAFF, is_active=True))
    assignee = _least_recently_assigned_purchase(candidates) if candidates else None
    if assignee:
        lead.purchase_staff = assignee
        lead.save(update_fields=['purchase_staff'])
    return assignee


def _least_recently_assigned_project(candidates):
    """Round-robin pick among project managers (least recently assigned goes next)."""
    best, best_time = None, None
    floor = timezone.datetime.min.replace(tzinfo=timezone.utc)
    for u in candidates:
        last = (Lead.objects.filter(project_manager=u)
                .order_by('-pushed_to_project_at').first())
        t = last.pushed_to_project_at if (last and last.pushed_to_project_at) else floor
        if best is None or t < best_time:
            best, best_time = u, t
    return best


def auto_assign_project(lead):
    """On handoff to the project stage, round-robin assign a project_manager:
    prefer the BDE's team's project managers, else any active project manager.
    Respects an existing assignment. Returns the assignee or None."""
    from users.models import User, ROLE_PROJECT_MANAGER
    if lead.project_manager_id:
        return None
    team = lead.bde.team if (lead.bde and lead.bde.team_id) else None
    candidates = list(team.members.filter(role=ROLE_PROJECT_MANAGER, is_active=True)) if team else []
    if not candidates:
        candidates = list(User.objects.filter(role=ROLE_PROJECT_MANAGER, is_active=True))
    assignee = _least_recently_assigned_project(candidates) if candidates else None
    if assignee:
        lead.project_manager = assignee
        lead.save(update_fields=['project_manager'])
    return assignee


from .scopes import live_leads, own_leads_q  # noqa: E402


def reporting_scope(user):
    """The leads a user's own figures are drawn from.

    Mirrors the Leads list: all-access roles (admins plus the downstream
    documentation / accounts / purchase / project / liasoning modules) see the
    whole book, a manager sees their people's, and everyone else sees the leads
    they work. The dashboard and the converted-leads analytics both read this,
    so a figure can never disagree with the rows behind it.
    """
    live = live_leads()
    if user.sees_all_leads:
        return live
    if user.is_manager:
        # Their people hold leads as BDE / tele caller too, not only as owner.
        managed = user.managed_user_ids()
        return live.filter(
            Q(assigned_to__id__in=managed) | Q(bde__id__in=managed)
            | Q(tele_caller__id__in=managed) | Q(assigned_to__isnull=True)
        ).distinct()
    return live.filter(own_leads_q(user)).distinct()


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
            {"value": "interested", "label": "Interested", "bg": "bg-lime-50", "text": "text-lime-700", "dot": "bg-lime-500", "color": "#84cc16"},
            {"value": "not_interested", "label": "Not Interested", "bg": "bg-rose-50", "text": "text-rose-700", "dot": "bg-rose-500", "color": "#f43f5e"},
            {"value": "converted", "label": "Converted", "bg": "bg-emerald-50", "text": "text-emerald-700", "dot": "bg-emerald-500", "color": "#10b981"},
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
        had_po_date = bool(sv.po_signed_date)
        serializer = SiteVisitSerializer(sv, data=request.data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        sv = serializer.save()

        # Signing the PO is what puts a lead on the KSEB feasibility queue, so the
        # BDE's reminder has to be raised from here too — not only from the
        # feasibility screen itself.
        po_just_signed = bool(sv.po_signed_date) and not had_po_date
        if sv.po_signed_date:
            self._sync_feasibility_reminder(lead, sv)
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
        # Tells the site-visit screen to send the BDE on to KSEB Feasibility.
        data['po_just_signed'] = po_just_signed
        return Response(data)

    @staticmethod
    def _sync_feasibility_reminder(lead, sv):
        """When the PO is signed but KSEB feasibility is not taken, ensure the BDE
        has an open reminder notification (due 2 days after PO signing). Resolve it
        once feasibility is taken."""
        from ai_manager.models import Notification
        bde = lead.bde
        if not bde:
            return
        pending = bool(sv.po_signed_date) and sv.kseb_feasibility_taken == 'no'
        existing = Notification.objects.filter(
            user=bde, is_read=False,
            extra_data__kseb_feasibility_lead=lead.id).first()
        if pending and not existing:
            due = sv.kseb_feasibility_due_date
            name = f"{lead.first_name} {lead.last_name or ''}".strip()
            Notification.objects.create(
                user=bde,
                title="KSEB Feasibility pending",
                message=(f"Upload the KSEB feasibility receipt for {name}. "
                         f"Due by {due.strftime('%d %b %Y') if due else '—'} "
                         f"(2 days from PO signing)."),
                notification_type='general',
                extra_data={'kseb_feasibility_lead': lead.id},
            )
        elif not pending and existing:
            existing.is_read = True
            existing.save(update_fields=['is_read'])

    # ── KSEB feasibility (BDE section for pushed-to-documentation leads) ──
    def _feasibility_payload(self, lead, request, sv=None):
        from .access import can_edit_kseb_feasibility
        # `sv` is passed by writers so the response reflects what was just saved;
        # reading lead.site_visit here can hand back a stale cached instance.
        if sv is None:
            sv = getattr(lead, 'site_visit', None)

        def d(x):
            return x.isoformat() if x else None

        receipts = []
        if sv:
            receipts = SiteVisitDocumentSerializer(
                sv.documents.filter(doc_type='kseb_feasibility_receipt'), many=True).data
        return {
            'id': lead.id,
            # A trashed lead leaves this row behind and its detail page will
            # not open, so the list flags it and offers admins the broom.
            'lead_deleted': lead.is_trashed,
            'can_cleanup': lead.is_trashed and can_cleanup_deleted_lead(getattr(request, 'user', None)),
            'first_name': lead.first_name,
            'last_name': lead.last_name,
            'phone': lead.phone,
            'location': lead.company,
            'product_name': lead.product.name if lead.product else None,
            'pushed_at': lead.pushed_to_documentation_at,
            'po_signed_date': d(sv.po_signed_date) if sv else None,
            'kseb_feasibility_taken': sv.kseb_feasibility_taken if sv else '',
            'kseb_feasibility_date': d(sv.kseb_feasibility_date) if sv else None,
            'kseb_feasibility_complete': bool(sv and sv.kseb_feasibility_complete),
            'feasibility_due_date': d(sv.kseb_feasibility_due_date) if sv else None,
            'receipts': receipts,
            'can_edit': can_edit_kseb_feasibility(request.user, lead),
        }

    @action(detail=False, methods=['get'], url_path='bde-feasibility')
    def bde_feasibility(self, request):
        """BDE's pushed-to-documentation leads, for the KSEB feasibility task."""
        user = request.user
        if not user or not user.is_authenticated:
            return Response({'error': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        # A lead joins the feasibility queue the moment its PO is signed; leads
        # already pushed to documentation stay on it as before.
        qs = (Lead.objects.filter(Q(pushed_to_documentation=True)
                                  | Q(site_visit__po_signed_date__isnull=False))
              .select_related('product', 'bde', 'site_visit')
              .prefetch_related('site_visit__documents')
              .distinct()
              .order_by('-pushed_to_documentation_at'))
        if not (user.is_staff or getattr(user, 'is_general_manager', False)):
            if getattr(user, 'branch_scoped', False) and user.branch_id:
                qs = qs.filter(bde__branch_id=user.branch_id)
            else:
                qs = qs.filter(bde=user)
        return Response([self._feasibility_payload(lead, request) for lead in qs])

    # Each downstream module is a push flag plus the record it created. Clearing
    # both is what takes a lead's leftovers out of that module.
    MODULE_CLEANUP = {
        'documentation':        ('pushed_to_documentation', 'pushed_to_documentation_at',
                                 'documentation_staff', 'documentation_stage1'),
        'documentation-stage2': ('pushed_to_doc_stage2', 'pushed_to_doc_stage2_at',
                                 'doc_stage2_staff', 'documentation_stage2'),
        'accounts':             ('pushed_to_accounts', 'pushed_to_accounts_at',
                                 'accounts_staff', 'payment_verification'),
        'purchase':             ('pushed_to_purchase', 'pushed_to_purchase_at',
                                 'purchase_staff', 'purchase_logistics'),
        'project':              ('pushed_to_project', 'pushed_to_project_at',
                                 'project_manager', 'project'),
        'liasoning':            ('pushed_to_liasoning', 'pushed_to_liasoning_at',
                                 None, 'liasoning_service'),
        'warranty':             ('pushed_to_warranty', 'pushed_to_warranty_at',
                                 None, 'warranty'),
    }
    # KSEB feasibility has no push flag of its own — the queue is every lead with
    # a signed PO plus anything in documentation — so its data lives on the site
    # visit and is cleared field by field.
    FEASIBILITY_FIELDS = ('po_signed_date', 'kseb_feasibility_taken',
                          'kseb_feasibility_date', 'kseb_feasibility_complete')

    @action(detail=True, methods=['delete'], url_path='remove-from-module')
    def remove_from_module(self, request, pk=None):
        """Clear a deleted lead's leftover data out of one module.

        Trashing a lead hides it from the Leads page but leaves its rows in the
        modules it had already reached, where they cannot be opened. This is the
        broom for those: an admin removes the residue module by module.

        Deliberately narrow — it only acts on a lead that is already in the
        Trash. It is a cleanup tool, not a way to pull a live customer out of a
        workflow someone is part-way through.
        """
        user = request.user
        if not can_cleanup_deleted_lead(user):
            return Response({'error': 'Only a super admin can remove a deleted lead from a module.'},
                            status=status.HTTP_403_FORBIDDEN)

        module = (request.data.get('module') or request.query_params.get('module') or '').strip()
        known = sorted(list(self.MODULE_CLEANUP) + ['feasibility'])
        if module not in known:
            return Response({'error': f"Unknown module. Expected one of: {', '.join(known)}."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Trashed leads are outside the normal queryset, so look it up directly.
        lead = Lead.objects.filter(pk=pk).first()
        if lead is None:
            return Response({'error': 'Lead not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not lead.is_trashed:
            return Response(
                {'error': 'This customer is still active. Delete the lead first, '
                          'then its leftover module data can be removed.'},
                status=status.HTTP_400_BAD_REQUEST)

        if module == 'feasibility':
            sv = getattr(lead, 'site_visit', None)
            if sv is None or not sv.po_signed_date:
                return Response({'error': 'This lead has no KSEB feasibility data.'},
                                status=status.HTTP_404_NOT_FOUND)
            sv.po_signed_date = None
            sv.kseb_feasibility_taken = ''
            sv.kseb_feasibility_date = None
            sv.kseb_feasibility_complete = False
            sv.save(update_fields=list(self.FEASIBILITY_FIELDS))
            ActivityLog.objects.create(
                activity_type='note_added', lead=lead, actor=user,
                description=f'Deleted lead removed from feasibility by {user.username}',
                extra={'auto_generated': True, 'module_cleanup': 'feasibility'},
            )
            # The queue is "PO signed OR in documentation", so a lead still in
            # documentation keeps its row until that is cleared too — say so
            # rather than let the button look like it did nothing.
            return Response({
                'removed': 'feasibility', 'lead': lead.id,
                'still_listed': lead.pushed_to_documentation,
                'message': ('Feasibility data cleared. This lead is still in '
                            'documentation, so it stays on the feasibility list '
                            'until it is removed from there too.')
                           if lead.pushed_to_documentation else 'Feasibility data cleared.',
            })

        flag, stamp, staff_field, related = self.MODULE_CLEANUP[module]
        if not getattr(lead, flag, False):
            return Response({'error': f'This lead is not in {module}.'},
                            status=status.HTTP_404_NOT_FOUND)

        record = getattr(lead, related, None)
        if record is not None:
            record.delete()

        fields = [flag, stamp]
        setattr(lead, flag, False)
        setattr(lead, stamp, None)
        if staff_field:
            setattr(lead, f'{staff_field}_id', None)
            fields.append(staff_field)
        lead.save(update_fields=fields)

        ActivityLog.objects.create(
            activity_type='note_added', lead=lead, actor=user,
            description=f'Deleted lead removed from {module} by {user.username}',
            extra={'auto_generated': True, 'module_cleanup': module},
        )
        return Response({'removed': module, 'lead': lead.id})

    @action(detail=True, methods=['get'], url_path='activity-timeline')
    def activity_timeline(self, request, pk=None):
        """Everything that has happened to this lead, newest first.

        The downstream modules — documentation, accounts, purchase, project,
        liasoning — each see one slice of a customer's journey. This is the whole
        of it in one place, so whoever picks the file up can see how it got here.

        Access falls out of `get_object()`: a user who cannot open the lead
        cannot read its history either.
        """
        lead = self.get_object()

        def actor_name(u):
            if not u:
                return None
            return f"{u.first_name} {u.last_name}".strip() or u.username

        # System-composed entries are labelled rather than attributed to a person.
        auto_prefixes = ('Documentation Stage 1 completed by', 'Auto-assigned to documentation:')

        logs = (ActivityLog.objects.filter(lead=lead)
                .select_related('actor').order_by('-created_at'))
        entries = [{
            'id': log.id,
            'type': log.activity_type,
            'description': log.description,
            'actor': actor_name(log.actor),
            'auto_generated': bool((log.extra or {}).get('auto_generated'))
                              or (log.description or '').startswith(auto_prefixes),
            'timestamp': timezone.localtime(log.created_at).isoformat(),
        } for log in logs]

        return Response({
            'lead': {
                'id': lead.id,
                'name': f"{lead.first_name} {lead.last_name or ''}".strip(),
                'phone': lead.phone or '',
                'status': lead.status,
                'created_at': timezone.localtime(lead.created_at).isoformat() if lead.created_at else None,
            },
            'count': len(entries),
            'entries': entries,
        })

    @action(detail=False, methods=['get'], url_path='feasibility-pending')
    def feasibility_pending(self, request):
        """The BDE's outstanding KSEB feasibilities, for the reminder popup.

        A lead is outstanding once it joins the queue (PO signed, or pushed to
        documentation) and its feasibility has not been marked complete. The
        client nags on login and every few hours until this comes back empty.
        """
        user = request.user
        if not user or not user.is_authenticated:
            return Response({'error': 'Authentication required.'},
                            status=status.HTTP_401_UNAUTHORIZED)

        qs = (Lead.objects
              .filter(Q(pushed_to_documentation=True)
                      | Q(site_visit__po_signed_date__isnull=False))
              .filter(is_trashed=False)
              .exclude(site_visit__kseb_feasibility_complete=True)
              .select_related('bde', 'site_visit')
              .distinct())
        # Only a BDE is nagged — this is their task. Everyone else gets an empty
        # list, so the popup never fires at someone who cannot act on it.
        if getattr(user, 'role', '') != 'bde':
            qs = qs.none()
        else:
            qs = qs.filter(bde=user)

        today = timezone.localdate()
        items = []
        for lead in qs.order_by('id'):
            sv = getattr(lead, 'site_visit', None)
            due = sv.kseb_feasibility_due_date if sv else None
            items.append({
                'id': lead.id,
                'name': f"{lead.first_name} {lead.last_name or ''}".strip(),
                'phone': lead.phone or '',
                'po_signed_date': sv.po_signed_date.isoformat() if sv and sv.po_signed_date else None,
                'due_date': due.isoformat() if due else None,
                'overdue': bool(due and due < today),
            })
        return Response({'count': len(items), 'items': items})

    @action(detail=True, methods=['get', 'patch'], url_path='kseb-feasibility')
    def kseb_feasibility(self, request, pk=None):
        """Get or update a lead's KSEB feasibility (PO date, taken, feasibility date)."""
        from .access import can_edit_kseb_feasibility
        lead = self.get_object()
        sv, _ = SiteVisit.objects.get_or_create(lead=lead)
        if request.method == 'GET':
            return Response(self._feasibility_payload(lead, request))
        if not can_edit_kseb_feasibility(request.user, lead):
            return Response({'error': 'You do not have permission to edit this feasibility.'},
                            status=status.HTTP_403_FORBIDDEN)
        if sv.kseb_feasibility_complete:
            return Response({'error': 'KSEB feasibility is already completed and locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        for field in ('po_signed_date', 'kseb_feasibility_date'):
            if field in request.data:
                setattr(sv, field, request.data.get(field) or None)
        if 'kseb_feasibility_taken' in request.data:
            sv.kseb_feasibility_taken = request.data.get('kseb_feasibility_taken') or ''
        sv.save()
        sv.refresh_from_db()  # turn date strings into date objects for the payload/reminder
        self._sync_feasibility_reminder(lead, sv)
        return Response(self._feasibility_payload(lead, request, sv=sv))

    @action(detail=True, methods=['post'], url_path='kseb-feasibility/documents')
    def kseb_feasibility_add_document(self, request, pk=None):
        """Upload the KSEB feasibility receipt photo/PDF."""
        from .access import can_edit_kseb_feasibility
        lead = self.get_object()
        if not can_edit_kseb_feasibility(request.user, lead):
            return Response({'error': 'You do not have permission to edit this feasibility.'},
                            status=status.HTTP_403_FORBIDDEN)
        sv, _ = SiteVisit.objects.get_or_create(lead=lead)
        if sv.kseb_feasibility_complete:
            return Response({'error': 'KSEB feasibility is completed and locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'file is required.'}, status=status.HTTP_400_BAD_REQUEST)
        doc = SiteVisitDocument.objects.create(
            site_visit=sv, doc_type='kseb_feasibility_receipt', file=file,
            uploaded_by=request.user if request.user.is_authenticated else None)
        return Response(SiteVisitDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='kseb-feasibility/documents/(?P<doc_id>[0-9]+)')
    def kseb_feasibility_delete_document(self, request, pk=None, doc_id=None):
        """Delete a KSEB feasibility receipt."""
        from .access import can_edit_kseb_feasibility
        lead = self.get_object()
        if not can_edit_kseb_feasibility(request.user, lead):
            return Response({'error': 'You do not have permission to edit this feasibility.'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            doc = SiteVisitDocument.objects.get(pk=doc_id, site_visit__lead=lead,
                                                doc_type='kseb_feasibility_receipt')
        except SiteVisitDocument.DoesNotExist:
            return Response({'error': 'Receipt not found.'}, status=status.HTTP_404_NOT_FOUND)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='complete-kseb-feasibility')
    def complete_kseb_feasibility(self, request, pk=None):
        """Complete the KSEB feasibility and reflect PO + feasibility dates into the
        lead's accounts payment verification."""
        from .access import can_edit_kseb_feasibility
        lead = self.get_object()
        if not can_edit_kseb_feasibility(request.user, lead):
            return Response({'error': 'You do not have permission to complete this feasibility.'},
                            status=status.HTTP_403_FORBIDDEN)
        sv, _ = SiteVisit.objects.get_or_create(lead=lead)
        if sv.kseb_feasibility_complete:
            return Response({'error': 'KSEB feasibility is already completed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        missing = []
        if not sv.po_signed_date:
            missing.append('po_signed_date')
        if sv.kseb_feasibility_taken != 'yes':
            missing.append('kseb_feasibility_taken')
        elif not sv.kseb_feasibility_date:
            missing.append('kseb_feasibility_date')
        if missing:
            return Response({'error': 'Record the PO date and the KSEB feasibility (taken + date) first.',
                             'missing': missing}, status=status.HTTP_400_BAD_REQUEST)
        sv.kseb_feasibility_complete = True
        sv.save(update_fields=['kseb_feasibility_complete', 'updated_at'])
        self._sync_feasibility_reminder(lead, sv)  # resolves the reminder (taken == yes)
        # Reflect PO + feasibility dates into the lead's accounts payment verification.
        pv, _ = PaymentVerification.objects.get_or_create(lead=lead)
        updates = []
        if pv.po_date != sv.po_signed_date:
            pv.po_date = sv.po_signed_date
            updates.append('po_date')
        if pv.kseb_feasibility_date != sv.kseb_feasibility_date:
            pv.kseb_feasibility_date = sv.kseb_feasibility_date
            updates.append('kseb_feasibility_date')
        if updates:
            updates.append('updated_at')
            pv.save(update_fields=updates)
        ActivityLog.objects.create(
            activity_type='note_added',
            description="KSEB feasibility completed by BDE; PO & feasibility dates sent to accounts.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        return Response(self._feasibility_payload(lead, request, sv=sv))

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
        fire_automation('pushed_to_documentation', lead)
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
            # A trashed lead leaves its module rows behind — the detail
            # page refuses to open them, so the list flags them for cleanup.
            # `can_cleanup` is decided here so the six module screens don't each
            # have to fetch the current user to know whether to offer the button.
            'lead_deleted': lead.is_trashed,
            'can_cleanup': lead.is_trashed and can_cleanup_deleted_lead(getattr(request, 'user', None)),
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
                # A trashed lead leaves this row behind and its detail page will
                # not open, so the tracker flags it and offers admins the broom.
                'lead_deleted': lead.is_trashed,
                'can_cleanup': lead.is_trashed and can_cleanup_deleted_lead(user),
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
        # Accounts price the job off the sanctioned capacity, so the BDE's KSEB
        # feasibility has to be signed off before the customer can be handed over.
        sv = getattr(lead, 'site_visit', None)
        if not (sv and sv.kseb_feasibility_complete):
            return Response(
                {'error': 'KSEB feasibility is still pending. The BDE must complete it '
                          'in the KSEB Feasibility module before this customer can be '
                          'pushed to accounts.',
                 'kseb_feasibility_pending': True},
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
            # Fired after the round-robin, so a rule that reassigns (e.g. the
            # accounts manager's own routing) has the last word.
            fire_automation('pushed_to_accounts', lead)
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
            # A trashed lead leaves its module rows behind — the detail
            # page refuses to open them, so the list flags them for cleanup.
            # `can_cleanup` is decided here so the six module screens don't each
            # have to fetch the current user to know whether to offer the button.
            'lead_deleted': lead.is_trashed,
            'can_cleanup': lead.is_trashed and can_cleanup_deleted_lead(getattr(request, 'user', None)),
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
            # Which payment bucket this row sits in — drives the queue's filter.
            'balance_amount': pv.balance_amount if pv else None,
            'fully_paid': bool(pv and pv.is_complete and pv.balance_amount <= 0),
            'balance_payments': BalancePaymentSerializer(lead.balance_payments.all(), many=True).data,
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
        # Payment mode is mandatory — a saved verification must always say how the
        # money came in (and carry the reference for non-cash modes).
        if 'payment_mode' in request.data and not (request.data.get('payment_mode') or '').strip():
            return Response({'error': 'Select a payment mode — it is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = PaymentVerificationSerializer(pv, data=request.data, partial=True,
                                                   context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @staticmethod
    def _sync_rf_reminder(lead, pv):
        """When the KSEB feasibility date is set but the RF hasn't been pushed to
        service, ensure the accounts staff has an open reminder (RF due 30 days from
        feasibility; reminder intended for day 29). Resolve once the RF is pushed."""
        from ai_manager.models import Notification
        recipient = lead.accounts_staff
        if not recipient:
            return
        pending = bool(pv.kseb_feasibility_date) and not pv.rf_pushed_to_service
        existing = Notification.objects.filter(
            user=recipient, is_read=False,
            extra_data__rf_lead=lead.id).first()
        if pending and not existing:
            due = pv.rf_due_date
            name = f"{lead.first_name} {lead.last_name or ''}".strip()
            Notification.objects.create(
                user=recipient,
                title="Registration Fee (RF) due",
                message=(f"RF for {name} is due by {due.strftime('%d %b %Y') if due else '—'} "
                         f"(30 days from KSEB feasibility; remind on day 29). "
                         f"Push to the service department to remit RF at the KSEB section."),
                notification_type='general',
                extra_data={'rf_lead': lead.id},
            )
        elif not pending and existing:
            existing.is_read = True
            existing.save(update_fields=['is_read'])

    @action(detail=True, methods=['post'], url_path='push-rf-to-service')
    def push_rf_to_service(self, request, pk=None):
        """Push the RF remittance task to the service department (creates a service
        entry to remit the registration fee at the KSEB section)."""
        from .access import can_edit_payment_verification
        lead = self.get_object()
        if not can_edit_payment_verification(request.user, lead):
            return Response({'error': 'You do not have permission to push the RF for this lead.'},
                            status=status.HTTP_403_FORBIDDEN)
        pv, _ = PaymentVerification.objects.get_or_create(lead=lead)
        if not pv.kseb_feasibility_date:
            return Response({'error': 'Set the KSEB feasibility date first.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if pv.rf_pushed_to_service:
            return Response({'error': 'RF has already been pushed to the service department.'},
                            status=status.HTTP_400_BAD_REQUEST)
        name = f"{lead.first_name} {lead.last_name or ''}".strip()
        ServiceEntry.objects.create(
            customer_name=name,
            customer_id=str(lead.id),
            scheduled_date=pv.rf_due_date,
            assigned_to='Remit RF at KSEB section',
            created_by=request.user if request.user.is_authenticated else None,
        )
        pv.rf_pushed_to_service = True
        pv.rf_pushed_at = timezone.now()
        pv.save(update_fields=['rf_pushed_to_service', 'rf_pushed_at', 'updated_at'])
        self._sync_rf_reminder(lead, pv)  # resolves the open RF reminder
        ActivityLog.objects.create(
            activity_type='note_added',
            description="RF (registration fee) pushed to the service department to remit at the KSEB section.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        return Response(self._completed_project_payload(lead, request))

    def _push_to_purchase(self, lead, request):
        """Hand the lead off to purchase & logistics (idempotent). Triggered by
        the first payment, part or full — the queue shows which is which so
        procurement can weigh a part-paid order accordingly."""
        if lead.pushed_to_purchase:
            return
        lead.pushed_to_purchase = True
        lead.pushed_to_purchase_at = timezone.now()
        lead.save(update_fields=['pushed_to_purchase', 'pushed_to_purchase_at'])
        pv = getattr(lead, 'payment_verification', None)
        paid = 'Fully paid' if (pv and (pv.balance_amount or 0) <= 0) else 'Part payment received'
        assignee = auto_assign_purchase(lead)
        if assignee:
            pname = f"{assignee.first_name} {assignee.last_name}".strip() or assignee.username
            pdesc = f"{paid} — moved to purchase & logistics. Auto-assigned to {pname}."
        else:
            pdesc = f"{paid} — moved to purchase & logistics."
        ActivityLog.objects.create(
            activity_type='note_added',
            description=pdesc,
            actor=request.user if request.user.is_authenticated else None,
            lead=lead,
            extra={'auto_generated': True},
        )
        if pv and (pv.balance_amount or 0) <= 0:
            fire_automation('payment_fully_paid', lead)

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
        # Auto-generate the money receipt for the amount collected at verification.
        from .receipts import issue_receipt
        issue_receipt(lead, pv.amount_received, on_account_of=pv.on_account_of,
                      payment_mode=pv.get_payment_mode_display() if pv.payment_mode else '',
                      is_initial=True,
                      created_by=request.user if request.user.is_authenticated else None)
        # Hand off to purchase & logistics as soon as money has come in —
        # procurement starts on a part payment; the balance is chased in parallel
        # rather than holding the order up.
        if (pv.amount_received or 0) > 0:
            self._push_to_purchase(lead, request)
        else:
            fire_automation('payment_partially_paid', lead, {'balance_amount': float(pv.balance_amount)})
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

    @action(detail=True, methods=['post'], url_path='mark-lost')
    def mark_lost(self, request, pk=None):
        """Mark a converted lead as lost (customer skipped / backed out of the deal)."""
        from .access import can_mark_lead_lost
        lead = self.get_object()
        if not can_mark_lead_lost(request.user):
            return Response({'error': 'You do not have permission to mark leads as lost.'},
                            status=status.HTTP_403_FORBIDDEN)
        if lead.status != 'converted':
            return Response({'error': 'Only converted leads can be marked lost.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if lead.is_lost:
            return Response({'error': 'This lead is already marked lost.'},
                            status=status.HTTP_400_BAD_REQUEST)
        lead.is_lost = True
        lead.lost_at = timezone.now()
        lead.lost_reason = (request.data.get('reason') or '')[:255]
        lead.lost_by = request.user if request.user.is_authenticated else None
        lead.save(update_fields=['is_lost', 'lost_at', 'lost_reason', 'lost_by'])
        fire_automation('lead_lost', lead, {'reason': lead.lost_reason})
        actor = (f"{request.user.first_name} {request.user.last_name}".strip()
                 or request.user.username) if request.user.is_authenticated else 'user'
        reason = f" Reason: {lead.lost_reason}" if lead.lost_reason else ''
        ActivityLog.objects.create(
            activity_type='note_added',
            description=f"Lead marked as lost by {actor}.{reason}",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        return Response(self.get_serializer(lead).data)

    @action(detail=True, methods=['post'], url_path='restore-lost')
    def restore_lost(self, request, pk=None):
        """Restore a lead that was previously marked lost."""
        from .access import can_mark_lead_lost
        lead = self.get_object()
        if not can_mark_lead_lost(request.user):
            return Response({'error': 'You do not have permission to restore leads.'},
                            status=status.HTTP_403_FORBIDDEN)
        if not lead.is_lost:
            return Response({'error': 'This lead is not marked lost.'},
                            status=status.HTTP_400_BAD_REQUEST)
        lead.is_lost = False
        lead.lost_at = None
        lead.lost_reason = ''
        lead.lost_by = None
        lead.save(update_fields=['is_lost', 'lost_at', 'lost_reason', 'lost_by'])
        actor = (f"{request.user.first_name} {request.user.last_name}".strip()
                 or request.user.username) if request.user.is_authenticated else 'user'
        ActivityLog.objects.create(
            activity_type='note_added',
            description=f"Lead restored from lost by {actor}.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        return Response(self.get_serializer(lead).data)

    # ── Payment collection buckets (partially / fully paid) ──
    def _payment_bucket_item(self, lead, request):
        pv = getattr(lead, 'payment_verification', None)

        def name(u):
            return (f"{u.first_name} {u.last_name}".strip() or u.username) if u else None

        balance = pv.balance_amount if pv else None
        return {
            'id': lead.id,
            'first_name': lead.first_name,
            'last_name': lead.last_name,
            'phone': lead.phone,
            'location': lead.company,
            'product_name': lead.product.name if lead.product else None,
            'value': lead.value,
            'accounts_staff_name': name(lead.accounts_staff),
            'amount_received': pv.amount_received if pv else None,
            'balance_amount': balance,
            'fully_paid': bool(balance is not None and balance <= 0),
            'verified_at': pv.completed_at if pv else None,
        }

    @action(detail=False, methods=['get'], url_path='module-counts')
    def module_counts(self, request):
        """Per-module count of work still waiting on the current user.

        Drives the sidebar badges (and the "new work" popup, which compares
        successive readings). Every count uses the same visibility rules as the
        module's own queue, so staff only ever count what they can actually see;
        a module the user can't open is simply absent from the response.
        """
        from datetime import timedelta
        from django.db.models import Q
        from .access import (can_access_documentation, can_access_doc_stage2, can_access_warranty,
                             can_access_accounts, can_access_purchase, can_access_project,
                             can_access_liasoning)
        user = request.user
        counts = {}
        # Of those, the ones assigned to this user by name — the client shows a
        # modal for these ("assigned to you") and a quieter toast for the rest.
        assigned = {}
        # Customers this user has already opened, per module — those no longer
        # count towards the badge.
        seen = {}
        for module, lead_id in ModuleSeen.objects.filter(user=user).values_list('module', 'lead_id'):
            seen.setdefault(module, set()).add(lead_id)

        def mine(qs, role, field):
            """Restrict a queue to the user's own assignments, like its view does."""
            if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                    and getattr(user, 'role', '') == role):
                return qs.filter(**{field: user})
            return qs

        def unseen(qs, module):
            """Drop the customers this user has already looked at in this module."""
            ids = seen.get(module)
            return qs.exclude(id__in=ids) if ids else qs

        def record(module, qs, assignee_field=None):
            """Store the unseen count, plus how many are assigned to this user."""
            qs = unseen(qs, module)
            counts[module] = qs.count()
            if assignee_field:
                assigned[module] = qs.filter(**{assignee_field: user}).count()
            return counts[module]

        # Leads personally owned by this user — the tele caller they're assigned
        # to, or the BDE handling the site visit. Everyone gets the key, but it
        # is only non-zero for people who actually own leads.
        record('leads',
               Lead.objects.filter(Q(assigned_to=user) | Q(bde=user))
                   .filter(is_trashed=False, is_archived=False)
                   .exclude(status__in=['not_interested'])
                   .distinct(),
               None)
        # Every lead in that count is by definition assigned to them.
        assigned['leads'] = counts['leads']

        if can_access_documentation(user):
            qs = Lead.objects.filter(pushed_to_documentation=True).exclude(documentation_stage1__is_complete=True)
            record('documentation', mine(qs, 'documentation_staff', 'documentation_staff'), 'documentation_staff')

        if can_access_doc_stage2(user):
            qs = Lead.objects.filter(pushed_to_doc_stage2=True).exclude(documentation_stage2__is_complete=True)
            record('documentation-stage2', mine(qs, 'documentation_staff', 'doc_stage2_staff'), 'doc_stage2_staff')

        if can_access_warranty(user):
            counts['warranty'] = unseen(Lead.objects.filter(pushed_to_warranty=True)
                                        .exclude(warranty__is_complete=True), 'warranty').count()

        if can_access_accounts(user):
            qs = Lead.objects.filter(pushed_to_accounts=True).exclude(payment_verification__is_complete=True)
            record('accounts', mine(qs, 'accounts_staff', 'accounts_staff'), 'accounts_staff')
            bucket = self._payment_bucket_qs(user)
            counts['accounts/partially-paid'] = unseen(bucket.filter(_balance__gt=0), 'accounts/partially-paid').count()
            counts['accounts/fully-paid'] = unseen(bucket.filter(_balance__lte=0), 'accounts/fully-paid').count()
            # Completed projects still waiting for the RF push to service.
            counts['accounts/completed'] = unseen(Lead.objects.filter(project__is_complete=True)
                                                 .exclude(payment_verification__rf_pushed_to_service=True), 'accounts/completed').count()

        if can_access_purchase(user):
            qs = Lead.objects.filter(pushed_to_purchase=True).exclude(purchase_logistics__is_complete=True)
            record('purchase', mine(qs, 'purchase_staff', 'purchase_staff'), 'purchase_staff')

        if can_access_project(user):
            qs = Lead.objects.filter(pushed_to_project=True).exclude(project__is_complete=True)
            record('project', mine(qs, 'project_manager', 'project_manager'), 'project_manager')

        if can_access_liasoning(user):
            counts['liasoning'] = unseen(Lead.objects.filter(pushed_to_liasoning=True)
                                         .exclude(liasoning_service__is_complete=True), 'liasoning').count()
            # Maintenance visits that are due / overdue and not yet filled in.
            counts['periodic-maintenance'] = MaintenanceVisit.objects.filter(
                is_complete=False, due_date__lte=timezone.localdate()).count()
            # Approvals the officer still has to chase at the KSEB section.
            cutoff = timezone.now() - timedelta(days=7)
            counts['discom-followup'] = unseen(
                Lead.objects.filter(pushed_to_doc_stage2=True)
                    .exclude(documentation_stage2__discom_approval='yes')
                    .filter(Q(documentation_stage2__discom_approval='no')
                            | Q(pushed_to_doc_stage2_at__lte=cutoff)
                            | Q(pushed_to_doc_stage2_at__isnull=True)),
                'discom-followup').count()

        return Response({'counts': counts, 'assigned': assigned})

    @action(detail=True, methods=['post'], url_path='seen')
    def mark_module_seen(self, request, pk=None):
        """Record that the user opened this customer in a module, so it stops
        counting towards that module's sidebar badge."""
        modules = request.data.get('modules') or ([request.data.get('module')] if request.data.get('module') else [])
        modules = [str(m).strip() for m in modules if str(m or '').strip()]
        if not modules:
            return Response({'error': 'module is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        for module in modules[:8]:      # a page maps to a couple of modules at most
            ModuleSeen.objects.update_or_create(user=request.user, module=module[:40], lead=lead)
        return Response({'seen': modules})

    def _payment_bucket_qs(self, user):
        """Verified-payment leads, annotated with the outstanding balance
        (deal value − amount received − discount), scoped for plain accounts staff."""
        from django.db.models import F, DecimalField, ExpressionWrapper
        qs = (Lead.objects.filter(pushed_to_accounts=True, payment_verification__is_complete=True)
              .select_related('product', 'accounts_staff', 'payment_verification')
              .annotate(_balance=ExpressionWrapper(
                  F('value') - F('payment_verification__amount_received') - F('payment_verification__discount_value'),
                  output_field=DecimalField(max_digits=14, decimal_places=2)))
              .order_by('-payment_verification__completed_at'))
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'accounts_staff'):
            qs = qs.filter(accounts_staff=user)
        return qs

    @action(detail=False, methods=['get'], url_path='accounts-partially-paid')
    def accounts_partially_paid(self, request):
        """Verified payments that still have a balance due."""
        from .access import can_access_accounts
        if not can_access_accounts(request.user):
            return Response({'error': 'You do not have access to accounts.'}, status=status.HTTP_403_FORBIDDEN)
        qs = self._payment_bucket_qs(request.user).filter(_balance__gt=0)
        return Response([self._payment_bucket_item(lead, request) for lead in qs])

    @action(detail=False, methods=['get'], url_path='accounts-fully-paid')
    def accounts_fully_paid(self, request):
        """Verified payments received in full (no balance due)."""
        from .access import can_access_accounts
        if not can_access_accounts(request.user):
            return Response({'error': 'You do not have access to accounts.'}, status=status.HTTP_403_FORBIDDEN)
        qs = self._payment_bucket_qs(request.user).filter(_balance__lte=0)
        return Response([self._payment_bucket_item(lead, request) for lead in qs])

    @staticmethod
    def _payment_ledger(lead, pv):
        """Every payment against this lead, oldest first.

        The first payment is recorded on the verification form rather than as a
        BalancePayment, so it has to be folded in here — otherwise the history
        adds up to less than the "Received" figure printed above it.
        """
        from decimal import Decimal
        rows = BalancePaymentSerializer(lead.balance_payments.all(), many=True).data
        initial = lead.receipt_vouchers.filter(is_initial=True).order_by('created_at').first()
        # The initial receipt holds the amount as it was at verification; without
        # one (older leads), it's whatever the running total isn't accounted for.
        if initial is not None:
            amount = initial.amount
        else:
            amount = (pv.amount_received or 0) - sum(
                (bp.amount for bp in lead.balance_payments.all()), Decimal('0'))
        if amount <= 0:
            return rows
        who = pv.completed_by
        rows.insert(0, {
            'id': None,
            'is_initial': True,
            'amount': str(amount),
            'payment_mode': pv.payment_mode or (initial.payment_mode if initial else ''),
            'utr_details': pv.utr_details or '',
            'on_account_of': pv.on_account_of or (initial.on_account_of if initial else ''),
            'note': pv.remarks or '',
            'recorded_by_name': ((f'{who.first_name} {who.last_name}'.strip() or who.username)
                                 if who else None),
            'created_at': (initial.date.isoformat() if initial
                           else (pv.completed_at or pv.created_at).isoformat()),
            'receipt_id': initial.id if initial else None,
            'receipt_number': initial.number if initial else None,
        })
        return rows

    @action(detail=True, methods=['get', 'post'], url_path='balance-payments')
    def balance_payments(self, request, pk=None):
        """GET the balance-collection summary + ledger for a verified lead; POST a
        new balance/installment payment (accounts staff), which reduces the balance
        due — once it reaches zero the lead becomes fully paid."""
        from decimal import Decimal, InvalidOperation
        from .access import can_access_accounts, can_edit_payment_verification
        lead = self.get_object()
        if not can_access_accounts(request.user):
            return Response({'error': 'You do not have access to accounts.'}, status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_accounts:
            return Response({'error': 'This lead has not been moved to accounts.'}, status=status.HTTP_404_NOT_FOUND)
        pv = getattr(lead, 'payment_verification', None)
        if not (pv and pv.is_complete):
            return Response({'error': 'Payment must be verified before collecting a balance.'},
                            status=status.HTTP_400_BAD_REQUEST)

        def summary():
            return {
                'deal_value': pv.deal_value,
                'amount_received': pv.amount_received,
                'discount_value': pv.discount_value,
                'balance_amount': pv.balance_amount,
                'fully_paid': pv.balance_amount <= 0,
                'can_collect': can_edit_payment_verification(request.user, lead),
                'payments': self._payment_ledger(lead, pv),
            }

        if request.method == 'GET':
            return Response(summary())

        if not can_edit_payment_verification(request.user, lead):
            return Response({'error': 'You do not have permission to collect balance for this lead.'},
                            status=status.HTTP_403_FORBIDDEN)
        if pv.balance_amount <= 0:
            return Response({'error': 'This lead is already fully paid.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            amount = Decimal(str(request.data.get('amount')))
        except (InvalidOperation, TypeError):
            return Response({'error': 'Enter a valid payment amount.'}, status=status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response({'error': 'Payment amount must be greater than zero.'}, status=status.HTTP_400_BAD_REQUEST)
        # Payment mode is mandatory — every recorded payment says how it came in.
        payment_mode = (request.data.get('payment_mode') or '').strip()
        if not payment_mode:
            return Response({'error': 'Select a payment mode — it is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        # Never collect more than what's still due.
        if amount > pv.balance_amount:
            amount = pv.balance_amount
        bp = BalancePayment.objects.create(
            lead=lead, amount=amount,
            payment_mode=payment_mode,
            utr_details=request.data.get('utr_details', '') or '',
            on_account_of=request.data.get('on_account_of', '') or '',
            note=request.data.get('note', '') or '',
            recorded_by=request.user if request.user.is_authenticated else None,
        )
        # Auto-generate the money receipt for this balance payment.
        from .receipts import issue_receipt
        issue_receipt(lead, amount, on_account_of=bp.on_account_of,
                      payment_mode=dict(PaymentVerification.PAYMENT_MODES).get(payment_mode, payment_mode),
                      balance_payment=bp,
                      created_by=request.user if request.user.is_authenticated else None)
        pv.amount_received = (pv.amount_received or 0) + amount
        pv.save(update_fields=['amount_received', 'updated_at'])
        actor = (f"{request.user.first_name} {request.user.last_name}".strip()
                 or request.user.username) if request.user.is_authenticated else 'accounts'
        ActivityLog.objects.create(
            activity_type='note_added',
            description=f"Balance payment of {amount} recorded by {actor}. Balance due: {pv.balance_amount}.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        # The lead is already in purchase (it moved there on the first payment);
        # clearing the balance is what makes it fully paid.
        if pv.balance_amount <= 0:
            self._push_to_purchase(lead, request)      # no-op if already pushed
            fire_automation('payment_fully_paid', lead)
        return Response(summary())

    @action(detail=True, methods=['get'], url_path='receipts')
    def receipts(self, request, pk=None):
        """Money receipts issued for a lead, plus the fixed company / bank details
        printed on them (so the client can render the voucher PDF)."""
        from .access import can_access_accounts
        lead = self.get_object()
        if not can_access_accounts(request.user):
            return Response({'error': 'You do not have access to accounts.'}, status=status.HTTP_403_FORBIDDEN)
        from organization.utils import get_org_settings
        org = get_org_settings()

        def url(f):
            if not f:
                return None
            return request.build_absolute_uri(f.url) if request else f.url

        return Response({
            'receipts': ReceiptVoucherSerializer(lead.receipt_vouchers.all(), many=True).data,
            'org': {
                'company_name': org.warranty_company_name,
                'cin': org.warranty_cin,
                'gst': org.warranty_gst,
                'signature': url(org.warranty_signature),
                'seal': url(org.warranty_seal),
                'bank_name': org.receipt_bank_name,
                'bank_account': org.receipt_bank_account,
                'bank_ifsc': org.receipt_bank_ifsc,
                'bank_branch': org.receipt_bank_branch,
                'address': org.receipt_address,
                'phone': org.receipt_phone,
                'website': org.receipt_website,
                'email': org.receipt_email,
            },
        })

    @action(detail=True, methods=['post'], url_path='send-receipt',
            parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def send_receipt(self, request, pk=None):
        """Store a rendered receipt against its voucher and send it to the customer.

        The client draws the voucher (it owns that template) and posts the PDF
        back; keeping the file means email can attach it and WhatsApp can link to
        it — the Cloud API fetches documents by URL rather than by upload.
        """
        from .access import can_access_accounts
        lead = self.get_object()
        if not can_access_accounts(request.user):
            return Response({'error': 'You do not have access to accounts.'},
                            status=status.HTTP_403_FORBIDDEN)

        receipt_id = request.data.get('receipt_id')
        voucher = (lead.receipt_vouchers.filter(pk=receipt_id).first() if receipt_id
                   else lead.receipt_vouchers.order_by('-created_at').first())
        if voucher is None:
            return Response({'error': 'No receipt has been generated for this payment yet.'},
                            status=status.HTTP_404_NOT_FOUND)

        pdf = request.FILES.get('pdf')
        if pdf:
            safe = (voucher.number or 'receipt').replace('/', '-')
            voucher.pdf.save(f'{safe}.pdf', pdf, save=True)
        if not voucher.pdf:
            return Response({'error': 'No document to send. Generate the receipt first.'},
                            status=status.HTTP_400_BAD_REQUEST)

        channels = [c.strip() for c in str(request.data.get('channels', 'email')).split(',') if c.strip()]
        results, failures, delivered = {}, [], []
        who = voucher.received_from or f"{lead.first_name} {lead.last_name or ''}".strip()
        filename = f"Receipt_{(voucher.number or 'receipt').replace('/', '_')}.pdf"

        if 'email' in channels:
            raw = request.data.get('email') or lead.email or ''
            recipients = [a.strip() for a in str(raw).split(',') if a.strip()]
            if not recipients:
                failures.append('No email address given for this customer.')
            else:
                from messaging.email import send_and_log
                voucher.pdf.open('rb')
                data = voucher.pdf.read()
                voucher.pdf.close()
                log = send_and_log(
                    to=recipients,
                    subject=f"Receipt {voucher.number}",
                    body=(f"Dear {who or 'Customer'},\n\nPlease find attached receipt "
                          f"{voucher.number} for Rs. {voucher.amount}"
                          f"{' towards ' + voucher.on_account_of if voucher.on_account_of else ''}."
                          f"\n\nRegards,\nEnergyFox"),
                    kind='receipt',
                    attachments=[(filename, data, 'application/pdf')],
                    created_by=request.user if request.user.is_authenticated else None,
                )
                results['email'] = log.status
                if log.status == 'sent':
                    delivered.append(f"email to {', '.join(recipients)}")
                else:
                    failures.append(f'Email failed: {log.error}')

        if 'whatsapp' in channels:
            to = request.data.get('phone') or lead.phone or ''
            if not to:
                failures.append('No WhatsApp number given for this customer.')
            else:
                from messaging import whatsapp
                try:
                    whatsapp.send_document(
                        to=to,
                        link=request.build_absolute_uri(voucher.pdf.url),
                        filename=filename,
                        caption=f"Receipt {voucher.number}",
                    )
                    results['whatsapp'] = 'sent'
                    delivered.append(f'WhatsApp to {to}')
                except Exception as exc:                     # surfaced to the user
                    failures.append(f'WhatsApp failed: {exc}')

        if failures and not results:
            return Response({'error': ' '.join(failures)}, status=status.HTTP_502_BAD_GATEWAY)
        # Sending a receipt is something that happened to this customer, so it
        # belongs on their Activity Timeline beside the payment it acknowledges.
        # Only actual deliveries are recorded — a failed send is not an event.
        if delivered:
            ActivityLog.objects.create(
                activity_type='note_added', lead=lead,
                actor=request.user if request.user.is_authenticated else None,
                description=f"Receipt {voucher.number} sent by {' and '.join(delivered)}.",
                extra={'auto_generated': True, 'receipt': voucher.number,
                       'channels': sorted(results)},
            )
        return Response({'sent': results, 'warnings': failures,
                         'number': voucher.number,
                         'pdf': request.build_absolute_uri(voucher.pdf.url)})

    # ── Completed projects (accounts RF stage) ──
    def _completed_project_payload(self, lead, request):
        """Accounts view of a lead whose installation is complete: customer info
        plus the registration-fee (RF) status, ready to be remitted/pushed to
        the service department."""
        from .access import can_edit_payment_verification
        pv = getattr(lead, 'payment_verification', None)
        pr = getattr(lead, 'project', None)

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
            'accounts_staff': lead.accounts_staff_id,
            'accounts_staff_name': name(lead.accounts_staff),
            'project_manager_name': name(lead.project_manager),
            'project_completed_at': pr.completed_at if pr else None,
            'registration_fee': PaymentVerificationSerializer(pv, context={'request': request}).data if pv else None,
            'rf_pushed': bool(pv and pv.rf_pushed_to_service),
            'can_edit_rf': can_edit_payment_verification(request.user, lead),
        }

    @action(detail=False, methods=['get'], url_path='accounts-completed')
    def accounts_completed(self, request):
        """Completed-projects queue for accounts: leads whose installation is
        complete, awaiting/tracking the registration-fee (RF) remittance."""
        from .access import can_access_accounts
        user = request.user
        if not can_access_accounts(user):
            return Response({'error': 'You do not have access to accounts.'},
                            status=status.HTTP_403_FORBIDDEN)
        qs = (Lead.objects.filter(pushed_to_accounts=True, project__is_complete=True)
              .select_related('product', 'bde', 'accounts_staff', 'project_manager',
                              'payment_verification', 'project')
              .order_by('-project__completed_at'))
        # Plain accounts staff see only the leads assigned to them.
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'accounts_staff'):
            qs = qs.filter(accounts_staff=user)
        return Response([self._completed_project_payload(lead, request) for lead in qs])

    @action(detail=True, methods=['get'], url_path='accounts-completed-detail')
    def accounts_completed_detail(self, request, pk=None):
        """Full completed-project view for one lead (customer info + RF)."""
        from .access import can_access_accounts
        user = request.user
        if not can_access_accounts(user):
            return Response({'error': 'You do not have access to accounts.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        pr = getattr(lead, 'project', None)
        if not (lead.pushed_to_accounts and pr and pr.is_complete):
            return Response({'error': 'This lead is not a completed project.'},
                            status=status.HTTP_404_NOT_FOUND)
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'accounts_staff'
                and lead.accounts_staff_id != user.id):
            return Response({'error': 'This lead is not assigned to you.'},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(self._completed_project_payload(lead, request))

    @action(detail=True, methods=['get', 'patch'], url_path='registration-fee')
    def registration_fee(self, request, pk=None):
        """Get or update a lead's registration-fee (RF) details (PO date & KSEB
        feasibility date). Editable in the completed-project stage until the RF is
        pushed to the service department — independent of the payment-verification
        lock."""
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
            return Response({'error': 'You do not have permission to edit this registration fee.'},
                            status=status.HTTP_403_FORBIDDEN)
        if pv.rf_pushed_to_service:
            return Response({'error': 'RF has already been pushed to the service department and is locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        # Only the RF date fields are editable here (never the payment amounts).
        data = {}
        for f in ('po_date', 'kseb_feasibility_date'):
            if f in request.data:
                data[f] = request.data.get(f) or None
        serializer = PaymentVerificationSerializer(pv, data=data, partial=True,
                                                   context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        self._sync_rf_reminder(lead, pv)
        return Response(serializer.data)

    # ── Purchase & logistics ──
    def _purchase_payload(self, lead, request):
        from .access import can_assign_purchase, can_edit_purchase_logistics
        pl = getattr(lead, 'purchase_logistics', None)
        pv = getattr(lead, 'payment_verification', None)

        def name(u):
            return (f"{u.first_name} {u.last_name}".strip() or u.username) if u else None

        return {
            'id': lead.id,
            # A trashed lead leaves its module rows behind — the detail
            # page refuses to open them, so the list flags them for cleanup.
            # `can_cleanup` is decided here so the six module screens don't each
            # have to fetch the current user to know whether to offer the button.
            'lead_deleted': lead.is_trashed,
            'can_cleanup': lead.is_trashed and can_cleanup_deleted_lead(getattr(request, 'user', None)),
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
            'accounts_staff_name': name(lead.accounts_staff),
            'purchase_staff': lead.purchase_staff_id,
            'purchase_staff_name': name(lead.purchase_staff),
            'pushed_at': lead.pushed_to_purchase_at,
            # Accounts (payment) data is included read-only so purchase staff can
            # see both the accounts and the purchase & logistics data together.
            'payment_verification': PaymentVerificationSerializer(pv, context={'request': request}).data if pv else None,
            'payment_complete': bool(pv and pv.is_complete),
            # Which payment bucket this row sits in — drives the queue's filter.
            'payment_state': ('fully_paid' if pv and (pv.balance_amount or 0) <= 0
                              else 'partially_paid') if pv else None,
            'balance_amount': pv.balance_amount if pv else None,
            'amount_received': pv.amount_received if pv else None,
            'purchase_logistics': PurchaseLogisticsSerializer(pl, context={'request': request}).data if pl else None,
            'purchase_complete': bool(pl and pl.is_complete),
            'can_edit_purchase': can_edit_purchase_logistics(request.user, lead),
            'can_assign': can_assign_purchase(request.user),
            'can_reopen_purchase': can_assign_purchase(request.user),
        }

    @action(detail=False, methods=['get'], url_path='purchase')
    def purchase(self, request):
        """Purchase & logistics queue: leads with a verified payment."""
        from .access import can_access_purchase
        user = request.user
        if not can_access_purchase(user):
            return Response({'error': 'You do not have access to purchase & logistics.'},
                            status=status.HTTP_403_FORBIDDEN)
        qs = (Lead.objects.filter(pushed_to_purchase=True)
              .select_related('product', 'bde', 'accounts_staff', 'purchase_staff',
                              'payment_verification', 'purchase_logistics')
              .order_by('-pushed_to_purchase_at'))
        # Plain purchase staff see only the leads assigned to them.
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'purchase_staff'):
            qs = qs.filter(purchase_staff=user)

        rows = [self._purchase_payload(lead, request) for lead in qs]
        # ?payment=partially_paid|fully_paid — the balance is derived from the
        # lead value, so it is filtered on the built rows rather than in SQL.
        wanted = request.query_params.get('payment')
        if wanted in ('partially_paid', 'fully_paid'):
            rows = [r for r in rows if r['payment_state'] == wanted]
        return Response(rows)

    @action(detail=True, methods=['get'], url_path='purchase-detail')
    def purchase_detail(self, request, pk=None):
        """Full purchase view for one lead (customer + accounts data + purchase form)."""
        from .access import can_access_purchase
        user = request.user
        if not can_access_purchase(user):
            return Response({'error': 'You do not have access to purchase & logistics.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_purchase:
            return Response({'error': 'This lead has not been moved to purchase & logistics.'},
                            status=status.HTTP_404_NOT_FOUND)
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'purchase_staff'
                and lead.purchase_staff_id != user.id):
            return Response({'error': 'This lead is not assigned to you.'},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(self._purchase_payload(lead, request))

    @action(detail=True, methods=['get', 'patch'], url_path='purchase-logistics')
    def purchase_logistics(self, request, pk=None):
        """Get or update a lead's purchase & logistics record."""
        from .access import can_access_purchase, can_edit_purchase_logistics
        lead = self.get_object()
        if not can_access_purchase(request.user):
            return Response({'error': 'You do not have access to purchase & logistics.'},
                            status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_purchase:
            return Response({'error': 'This lead has not been moved to purchase & logistics.'},
                            status=status.HTTP_404_NOT_FOUND)
        pl, _ = PurchaseLogistics.objects.get_or_create(lead=lead)
        if request.method == 'GET':
            return Response(PurchaseLogisticsSerializer(pl, context={'request': request}).data)
        if not can_edit_purchase_logistics(request.user, lead):
            return Response({'error': 'You do not have permission to edit this purchase & logistics.'},
                            status=status.HTTP_403_FORBIDDEN)
        # Completing locks the record for purchase staff. An admin keeps editing —
        # they are the ones who signed it off, sometimes on an override, and have
        # to be able to correct it afterwards.
        if pl.is_complete and not (request.user.is_staff
                                   or getattr(request.user, 'is_general_manager', False)):
            return Response({'error': 'Purchase & logistics is already completed and locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = PurchaseLogisticsSerializer(pl, data=request.data, partial=True,
                                                 context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='complete-purchase-logistics')
    def complete_purchase_logistics(self, request, pk=None):
        """Mark a lead's purchase & logistics complete (locks it)."""
        from .access import can_edit_purchase_logistics
        lead = self.get_object()
        if not can_edit_purchase_logistics(request.user, lead):
            return Response({'error': 'You do not have permission to complete this purchase & logistics.'},
                            status=status.HTTP_403_FORBIDDEN)
        pl, _ = PurchaseLogistics.objects.get_or_create(lead=lead)
        if pl.is_complete:
            return Response({'error': 'Purchase & logistics is already completed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        # Everything has to have arrived and nothing be outstanding. An admin may
        # sign off regardless, but the exception is recorded rather than hidden.
        unmet = pl.unmet_conditions()
        is_admin = bool(request.user.is_staff
                        or getattr(request.user, 'is_general_manager', False))
        override = str(request.data.get('override', '')).lower() in ('1', 'true', 'yes')
        if unmet and not (override and is_admin):
            return Response({
                'error': 'Not ready to complete: ' + ', '.join(label for _f, label in unmet) + '.',
                'unmet': [{'field': f, 'label': label} for f, label in unmet],
                'can_override': is_admin,
            }, status=status.HTTP_400_BAD_REQUEST)

        pl.is_complete = True
        pl.completed_at = timezone.now()
        pl.completed_by = request.user if request.user.is_authenticated else None
        pl.completed_with_override = bool(unmet)
        pl.override_reason = (', '.join(label for _f, label in unmet))[:255] if unmet else ''
        pl.save(update_fields=['is_complete', 'completed_at', 'completed_by',
                               'completed_with_override', 'override_reason', 'updated_at'])
        actor = (f"{request.user.first_name} {request.user.last_name}".strip()
                 or request.user.username) if request.user.is_authenticated else 'purchase'
        note = f"Purchase & logistics completed by {actor}."
        if pl.completed_with_override:
            note += f" Conditions overridden: {pl.override_reason}."
        ActivityLog.objects.create(
            activity_type='note_added',
            description=note,
            actor=request.user if request.user.is_authenticated else None,
            lead=lead,
            extra={'auto_generated': True, 'override': pl.completed_with_override},
        )
        # Hand the lead off to the project (installation) stage.
        if not lead.pushed_to_project:
            lead.pushed_to_project = True
            lead.pushed_to_project_at = timezone.now()
            lead.save(update_fields=['pushed_to_project', 'pushed_to_project_at'])
            assignee = auto_assign_project(lead)
            if assignee:
                prname = f"{assignee.first_name} {assignee.last_name}".strip() or assignee.username
                prdesc = f"Moved to project / installation. Auto-assigned to {prname}."
            else:
                prdesc = "Moved to project / installation."
            ActivityLog.objects.create(
                activity_type='note_added',
                description=prdesc,
                actor=request.user if request.user.is_authenticated else None,
                lead=lead,
                extra={'auto_generated': True},
            )
        return Response(self._purchase_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='reopen-purchase-logistics')
    def reopen_purchase_logistics(self, request, pk=None):
        """Admin re-opens a completed purchase & logistics record for editing."""
        from .access import can_assign_purchase
        lead = self.get_object()
        if not can_assign_purchase(request.user):
            return Response({'error': 'Only purchase admins can reopen a completed record.'},
                            status=status.HTTP_403_FORBIDDEN)
        pl = getattr(lead, 'purchase_logistics', None)
        if not pl or not pl.is_complete:
            return Response({'error': 'Purchase & logistics is not completed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        pl.is_complete = False
        pl.completed_at = None
        pl.completed_by = None
        pl.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        return Response(self._purchase_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='assign-purchase')
    def assign_purchase(self, request, pk=None):
        """Admin/GM assigns (or clears) the purchase staff handling this lead."""
        from users.models import User
        from .access import can_assign_purchase
        lead = self.get_object()
        if not can_assign_purchase(request.user):
            return Response({'error': 'You do not have permission to assign purchase staff.'},
                            status=status.HTTP_403_FORBIDDEN)
        staff_id = request.data.get('staff')
        if not staff_id:
            lead.purchase_staff = None
        else:
            try:
                lead.purchase_staff = User.objects.get(pk=staff_id)
            except User.DoesNotExist:
                return Response({'error': 'Purchase staff not found.'}, status=status.HTTP_404_NOT_FOUND)
        lead.save(update_fields=['purchase_staff'])
        return Response(self._purchase_payload(lead, request))

    # ── Project / installation ──
    def _project_payload(self, lead, request):
        from .access import can_assign_project, can_edit_project
        pr = getattr(lead, 'project', None)

        def name(u):
            return (f"{u.first_name} {u.last_name}".strip() or u.username) if u else None

        return {
            'id': lead.id,
            # A trashed lead leaves its module rows behind — the detail
            # page refuses to open them, so the list flags them for cleanup.
            # `can_cleanup` is decided here so the six module screens don't each
            # have to fetch the current user to know whether to offer the button.
            'lead_deleted': lead.is_trashed,
            'can_cleanup': lead.is_trashed and can_cleanup_deleted_lead(getattr(request, 'user', None)),
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
            'project_manager': lead.project_manager_id,
            'project_manager_name': name(lead.project_manager),
            'pushed_at': lead.pushed_to_project_at,
            'project': ProjectSerializer(pr, context={'request': request}).data if pr else None,
            'project_complete': bool(pr and pr.is_complete),
            'can_edit_project': can_edit_project(request.user, lead),
            'can_assign': can_assign_project(request.user),
            'can_reopen_project': can_assign_project(request.user),
        }

    @action(detail=False, methods=['get'], url_path='project')
    def project(self, request):
        """Project / installation queue: leads with a completed purchase stage."""
        from .access import can_access_project
        user = request.user
        if not can_access_project(user):
            return Response({'error': 'You do not have access to projects.'}, status=status.HTTP_403_FORBIDDEN)
        qs = (Lead.objects.filter(pushed_to_project=True)
              .select_related('product', 'bde', 'project_manager', 'project')
              .order_by('-pushed_to_project_at'))
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'project_manager'):
            qs = qs.filter(project_manager=user)
        return Response([self._project_payload(lead, request) for lead in qs])

    @action(detail=True, methods=['get'], url_path='project-detail')
    def project_detail(self, request, pk=None):
        """Full project view for one lead (customer + installation form)."""
        from .access import can_access_project
        user = request.user
        if not can_access_project(user):
            return Response({'error': 'You do not have access to projects.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_project:
            return Response({'error': 'This lead is not in the project stage.'}, status=status.HTTP_404_NOT_FOUND)
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'project_manager'
                and lead.project_manager_id != user.id):
            return Response({'error': 'This lead is not assigned to you.'}, status=status.HTTP_403_FORBIDDEN)
        return Response(self._project_payload(lead, request))

    @action(detail=True, methods=['get', 'patch'], url_path='project-record')
    def project_record(self, request, pk=None):
        """Get or update a lead's project (installation) record."""
        from .access import can_access_project, can_edit_project
        lead = self.get_object()
        if not can_access_project(request.user):
            return Response({'error': 'You do not have access to projects.'}, status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_project:
            return Response({'error': 'This lead is not in the project stage.'}, status=status.HTTP_404_NOT_FOUND)
        pr, _ = Project.objects.get_or_create(lead=lead)
        if request.method == 'GET':
            return Response(ProjectSerializer(pr, context={'request': request}).data)
        if not can_edit_project(request.user, lead):
            return Response({'error': 'You do not have permission to edit this project.'}, status=status.HTTP_403_FORBIDDEN)
        if pr.is_complete:
            return Response({'error': 'Project is already completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ProjectSerializer(pr, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='project-record/documents')
    def project_add_document(self, request, pk=None):
        """Upload one geotagged installation photo to a project slot."""
        from .access import can_edit_project
        lead = self.get_object()
        if not can_edit_project(request.user, lead):
            return Response({'error': 'You do not have permission to edit this project.'}, status=status.HTTP_403_FORBIDDEN)
        pr, _ = Project.objects.get_or_create(lead=lead)
        if pr.is_complete:
            return Response({'error': 'Project is completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        doc_type = request.data.get('doc_type')
        file = request.FILES.get('file')
        if not doc_type or not file:
            return Response({'error': 'doc_type and file are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if doc_type not in {k for k, _ in Project.PHOTO_SLOTS}:
            return Response({'error': 'Unknown photo type.'}, status=status.HTTP_400_BAD_REQUEST)
        doc = ProjectDocument.objects.create(
            project=pr, doc_type=doc_type, file=file,
            uploaded_by=request.user if request.user.is_authenticated else None)
        return Response(ProjectDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='project-record/documents/(?P<doc_id>[0-9]+)')
    def project_delete_document(self, request, pk=None, doc_id=None):
        """Delete a single project installation photo."""
        from .access import can_edit_project
        lead = self.get_object()
        if not can_edit_project(request.user, lead):
            return Response({'error': 'You do not have permission to edit this project.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            doc = ProjectDocument.objects.get(pk=doc_id, project__lead=lead)
        except ProjectDocument.DoesNotExist:
            return Response({'error': 'Photo not found.'}, status=status.HTTP_404_NOT_FOUND)
        if doc.project.is_complete:
            return Response({'error': 'Project is completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='complete-project')
    def complete_project(self, request, pk=None):
        """Mark a lead's project complete (locks it)."""
        from .access import can_edit_project
        lead = self.get_object()
        if not can_edit_project(request.user, lead):
            return Response({'error': 'You do not have permission to complete this project.'}, status=status.HTTP_403_FORBIDDEN)
        pr, _ = Project.objects.get_or_create(lead=lead)
        if pr.is_complete:
            return Response({'error': 'Project is already completed.'}, status=status.HTTP_400_BAD_REQUEST)
        pr.is_complete = True
        pr.completed_at = timezone.now()
        pr.completed_by = request.user if request.user.is_authenticated else None
        pr.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        actor = (f"{request.user.first_name} {request.user.last_name}".strip()
                 or request.user.username) if request.user.is_authenticated else 'project manager'
        ActivityLog.objects.create(
            activity_type='note_added',
            description=f"Project / installation completed by {actor}.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        # Fan out in parallel: Documentation Stage 2 and Liasoning & Service both
        # receive the lead the moment the installation project is complete.
        fanout = []
        now = timezone.now()
        if not lead.pushed_to_doc_stage2:
            lead.pushed_to_doc_stage2 = True
            lead.pushed_to_doc_stage2_at = now
            fanout += ['pushed_to_doc_stage2', 'pushed_to_doc_stage2_at']
            DocumentationStage2.objects.get_or_create(lead=lead)
        if not lead.pushed_to_liasoning:
            lead.pushed_to_liasoning = True
            lead.pushed_to_liasoning_at = now
            fanout += ['pushed_to_liasoning', 'pushed_to_liasoning_at']
            LiasoningService.objects.get_or_create(lead=lead)
        if not lead.pushed_to_warranty:
            lead.pushed_to_warranty = True
            lead.pushed_to_warranty_at = now
            fanout += ['pushed_to_warranty', 'pushed_to_warranty_at']
            Warranty.objects.get_or_create(lead=lead)
        if fanout:
            lead.save(update_fields=fanout)
            ActivityLog.objects.create(
                activity_type='note_added',
                description="Moved to Documentation Stage 2, Warranty and Liasoning & Service.",
                actor=request.user if request.user.is_authenticated else None,
                lead=lead, extra={'auto_generated': True})
        fire_automation('project_completed', lead)
        return Response(self._project_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='reopen-project')
    def reopen_project(self, request, pk=None):
        """Admin re-opens a completed project for editing."""
        from .access import can_assign_project
        lead = self.get_object()
        if not can_assign_project(request.user):
            return Response({'error': 'Only project admins can reopen a completed project.'}, status=status.HTTP_403_FORBIDDEN)
        pr = getattr(lead, 'project', None)
        if not pr or not pr.is_complete:
            return Response({'error': 'Project is not completed.'}, status=status.HTTP_400_BAD_REQUEST)
        pr.is_complete = False
        pr.completed_at = None
        pr.completed_by = None
        pr.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        return Response(self._project_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='assign-project')
    def assign_project(self, request, pk=None):
        """Admin/GM assigns (or clears) the project manager handling this lead."""
        from users.models import User
        from .access import can_assign_project
        lead = self.get_object()
        if not can_assign_project(request.user):
            return Response({'error': 'You do not have permission to assign a project manager.'}, status=status.HTTP_403_FORBIDDEN)
        pm_id = request.data.get('staff')
        if not pm_id:
            lead.project_manager = None
        else:
            try:
                lead.project_manager = User.objects.get(pk=pm_id)
            except User.DoesNotExist:
                return Response({'error': 'Project manager not found.'}, status=status.HTTP_404_NOT_FOUND)
        lead.save(update_fields=['project_manager'])
        return Response(self._project_payload(lead, request))

    # ── Documentation Stage 2 (post-installation documentation queue) ──
    def _doc_stage2_payload(self, lead, request):
        from .access import can_access_doc_stage2, can_reopen_documentation, can_assign_documentation
        rec = getattr(lead, 'documentation_stage2', None)

        def name(u):
            return (f"{u.first_name} {u.last_name}".strip() or u.username) if u else None

        return {
            'id': lead.id,
            # A trashed lead leaves its module rows behind — the detail
            # page refuses to open them, so the list flags them for cleanup.
            # `can_cleanup` is decided here so the six module screens don't each
            # have to fetch the current user to know whether to offer the button.
            'lead_deleted': lead.is_trashed,
            'can_cleanup': lead.is_trashed and can_cleanup_deleted_lead(getattr(request, 'user', None)),
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
            'pushed_at': lead.pushed_to_doc_stage2_at,
            'record': DocumentationStage2Serializer(rec, context={'request': request}).data if rec else None,
            'is_complete': bool(rec and rec.is_complete),
            'subsidy_requested': bool(rec and rec.subsidy_requested),
            # Signed off and handed on, but nobody has claimed the subsidy yet —
            # the one thing left outstanding after Stage 2 closes. Decided here
            # so the list and any later consumer share one definition.
            'subsidy_pending': bool(rec and rec.is_complete and not rec.subsidy_requested),
            'can_edit': can_access_doc_stage2(request.user),
            'can_reopen': can_reopen_documentation(request.user),
            # Stage 2 has its own assignee, set by the documentation manager.
            'doc_stage2_staff': lead.doc_stage2_staff_id,
            'doc_stage2_staff_name': name(lead.doc_stage2_staff),
            'can_assign': can_assign_documentation(request.user),
        }

    @action(detail=False, methods=['get'], url_path='documentation-stage2')
    def documentation_stage2(self, request):
        """Documentation Stage 2 queue: leads whose installation project is complete."""
        from .access import can_access_doc_stage2
        if not can_access_doc_stage2(request.user):
            return Response({'error': 'You do not have access to documentation.'}, status=status.HTTP_403_FORBIDDEN)
        user = request.user
        qs = (Lead.objects.filter(pushed_to_doc_stage2=True)
              .select_related('product', 'bde', 'doc_stage2_staff', 'documentation_stage2')
              .order_by('-pushed_to_doc_stage2_at'))
        # Documentation staff see only what the manager assigned them; managers
        # and admins see the whole queue.
        if (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'documentation_staff'):
            qs = qs.filter(doc_stage2_staff=user)
        return Response([self._doc_stage2_payload(lead, request) for lead in qs])

    @action(detail=True, methods=['post'], url_path='assign-doc-stage2')
    def assign_doc_stage2(self, request, pk=None):
        """Documentation manager assigns Stage 2 to a documentation staff member."""
        from users.models import User
        from .access import can_assign_documentation
        lead = self.get_object()
        if not can_assign_documentation(request.user):
            return Response({'error': 'Only documentation managers can assign documentation staff.'},
                            status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_doc_stage2:
            return Response({'error': 'This lead is not in Documentation Stage 2.'},
                            status=status.HTTP_404_NOT_FOUND)
        staff_id = request.data.get('staff')
        if not staff_id:
            lead.doc_stage2_staff = None
        else:
            try:
                lead.doc_stage2_staff = User.objects.get(pk=staff_id)
            except User.DoesNotExist:
                return Response({'error': 'Staff not found.'}, status=status.HTTP_404_NOT_FOUND)
        lead.save(update_fields=['doc_stage2_staff'])
        if lead.doc_stage2_staff:
            who = (f"{lead.doc_stage2_staff.first_name} {lead.doc_stage2_staff.last_name}".strip()
                   or lead.doc_stage2_staff.username)
            ActivityLog.objects.create(
                activity_type='note_added',
                description=f"Documentation Stage 2 assigned to: {who}",
                actor=request.user if request.user.is_authenticated else None,
                lead=lead, extra={'auto_generated': True})
        return Response(self._doc_stage2_payload(lead, request))

    @staticmethod
    def _doc_stage2_not_mine(user, lead):
        """Documentation staff may only work the Stage 2 leads assigned to them
        by the manager. Managers / admins are never restricted."""
        return (not user.is_staff and not getattr(user, 'is_general_manager', False)
                and getattr(user, 'role', '') == 'documentation_staff'
                and lead.doc_stage2_staff_id != user.id)

    @action(detail=True, methods=['get'], url_path='documentation-stage2-detail')
    def documentation_stage2_detail(self, request, pk=None):
        """Full Documentation Stage 2 view for one lead."""
        from .access import can_access_doc_stage2
        if not can_access_doc_stage2(request.user):
            return Response({'error': 'You do not have access to documentation.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_doc_stage2:
            return Response({'error': 'This lead is not in Documentation Stage 2.'}, status=status.HTTP_404_NOT_FOUND)
        if self._doc_stage2_not_mine(request.user, lead):
            return Response({'error': 'This lead is not assigned to you.'}, status=status.HTTP_403_FORBIDDEN)
        DocumentationStage2.objects.get_or_create(lead=lead)
        return Response(self._doc_stage2_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='complete-documentation-stage2')
    def complete_documentation_stage2(self, request, pk=None):
        """Mark Documentation Stage 2 complete for a lead."""
        from .access import can_access_doc_stage2
        if not can_access_doc_stage2(request.user):
            return Response({'error': 'You do not have permission to complete Documentation Stage 2.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_doc_stage2:
            return Response({'error': 'This lead is not in Documentation Stage 2.'}, status=status.HTTP_404_NOT_FOUND)
        rec, _ = DocumentationStage2.objects.get_or_create(lead=lead)
        if rec.is_complete:
            return Response({'error': 'Documentation Stage 2 is already completed.'}, status=status.HTTP_400_BAD_REQUEST)
        rec.is_complete = True
        rec.completed_at = timezone.now()
        rec.completed_by = request.user if request.user.is_authenticated else None
        rec.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        ActivityLog.objects.create(
            activity_type='note_added', description="Documentation Stage 2 completed.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        fire_automation('doc_stage2_completed', lead)
        return Response(self._doc_stage2_payload(lead, request))

    @action(detail=True, methods=['post'], url_path='reopen-documentation-stage2')
    def reopen_documentation_stage2(self, request, pk=None):
        """Unlock a completed Documentation Stage 2 so it can be edited again.
        Documentation managers and admins / general managers only."""
        from .access import can_reopen_documentation
        if not can_reopen_documentation(request.user):
            return Response({'error': 'Only documentation managers and admins can reopen a completed stage.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        rec = getattr(lead, 'documentation_stage2', None)
        if not rec or not rec.is_complete:
            return Response({'error': 'Documentation Stage 2 is not completed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        rec.is_complete = False
        rec.completed_at = None
        rec.completed_by = None
        rec.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        actor = (f"{request.user.first_name} {request.user.last_name}".strip()
                 or request.user.username) if request.user.is_authenticated else 'a manager'
        ActivityLog.objects.create(
            activity_type='note_added',
            description=f"Documentation Stage 2 reopened for editing by {actor}.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        return Response(self._doc_stage2_payload(lead, request))

    def _doc_stage2_prefill(self, lead):
        """Pre-fill values for the completion-doc forms, pulled from what the CRM
        already knows about the customer (lead info, site visit, Stage 1, project).
        Saved form values always win over these on the frontend."""
        sv = getattr(lead, 'site_visit', None)
        s1 = getattr(lead, 'documentation_stage1', None)
        pr = getattr(lead, 'project', None)
        name = f"{lead.first_name} {lead.last_name or ''}".strip()
        address = lead.installation_location or lead.company or ''
        # Capacity chain: documentation's own value, else the BDE's site visit.
        capacity = ((s1.mnre_plant_capacity if s1 else '')
                    or (sv.plant_capacity if sv else '')
                    or (sv.feasible_capacity if sv else '') or '')
        completed = pr.completed_at.strftime('%d/%m/%Y') if (pr and pr.completed_at) else ''
        product = (lead.product.name if lead.product else '') or ''
        return {
            'completion_letterhead': {
                'name_of_consumer': name,
                'consumer_number': (sv.consumer_number if sv else '') or '',
                'kseb_section': (sv.kseb_section if sv else '') or '',
                'capacity': capacity,
                'connection_type': (sv.connection_type if sv else '') or '',
                'date_of_completion': completed,
            },
            'customer_details': {
                'electrical_section': (sv.kseb_section if sv else '') or '',
                'consumer_no': (sv.consumer_number if sv else '') or '',
                'tariff': 'LT-1',
                'connected_load': (sv.connected_load if sv else '') or '',
                'solar_plant_owner': name,
                'address': address,
                'email': lead.email or '',
                'contact_phone': lead.phone or '',
                'plant_type': 'Hybrid' if 'hybrid' in product.lower() else 'OnGrid',
                'total_capacity': capacity,
                # Checklist rows 6–14 — the standard answers, editable per customer.
                'hybrid_scheme_confirms': 'NA',
                'completion_certificate_submitted': 'Yes',
                'energization_approval_obtained': 'Not Applicable',
                'energization_approval_details': '',
                'dc_isolator_provided': 'Yes',
                'visual_isolator_provided': 'Yes',
                'wiring_completed': 'Yes',
                'earthing_provided': 'Yes',
                'protection_functions_equipped': 'Yes',
            },
            'inverter_panel_details': {
                'customer_name': name,
                'customer_contact_no': lead.phone or '',
                'customer_address': address,
            },
        }

    @action(detail=True, methods=['get', 'patch'], url_path='documentation-stage2-record')
    def documentation_stage2_record(self, request, pk=None):
        """Get or update a lead's Documentation Stage 2 record (Annexure 3 status,
        MNRE / discom approval, warranty)."""
        from .access import can_access_doc_stage2
        lead = self.get_object()
        if not can_access_doc_stage2(request.user):
            return Response({'error': 'You do not have access to documentation.'}, status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_doc_stage2:
            return Response({'error': 'This lead is not in Documentation Stage 2.'}, status=status.HTTP_404_NOT_FOUND)
        if self._doc_stage2_not_mine(request.user, lead):
            return Response({'error': 'This lead is not assigned to you.'}, status=status.HTTP_403_FORBIDDEN)
        rec, _ = DocumentationStage2.objects.get_or_create(lead=lead)
        if request.method == 'GET':
            from .access import can_reopen_documentation
            data = DocumentationStage2Serializer(rec, context={'request': request}).data
            data['prefill'] = self._doc_stage2_prefill(lead)
            data['can_reopen'] = can_reopen_documentation(request.user)
            return Response(data)
        # The discom approval arrives from KSEB on its own schedule, often after
        # the rest of Stage 2 has been signed off — so it is the one field that
        # survives the lock. Everything else still stops here.
        if rec.is_complete and set(request.data.keys()) - {'discom_approval'}:
            return Response({'error': 'Documentation Stage 2 is already completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        old_discom = rec.discom_approval
        serializer = DocumentationStage2Serializer(rec, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if 'discom_approval' in request.data:
            self._sync_discom_to_liasoning(lead, rec, old_discom, request)
        return Response(serializer.data)

    def _sync_discom_to_liasoning(self, lead, rec, old_discom, request):
        """Documentation Stage 2 owns the discom approval; Liasoning displays it.

        Written straight to the model rather than through the liasoning endpoint
        so a completed (locked) liasoning record still receives it — otherwise a
        late approval would never reach the officer's list.
        """
        lia, _ = LiasoningService.objects.get_or_create(lead=lead)
        if lia.discom_approval != rec.discom_approval:
            lia.discom_approval = rec.discom_approval
            lia.save(update_fields=['discom_approval', 'updated_at'])
        # Approval clears the customer for the warranty hand-over. Checked on the
        # current state (not just the transition) and idempotent, so a customer
        # approved before this rule existed still gets moved on the next save.
        if rec.discom_approval == 'yes':
            self._push_to_warranty(lead, request)
        if rec.discom_approval != old_discom:
            if rec.discom_approval == 'yes':
                fire_automation('discom_approved', lead)
            elif rec.discom_approval == 'no':
                fire_automation('discom_not_approved', lead)

    @action(detail=True, methods=['post'], url_path='documentation-stage2/documents')
    def doc_stage2_add_document(self, request, pk=None):
        """Upload one file to a Documentation Stage 2 slot (e.g. Annexure 3)."""
        from .access import can_access_doc_stage2
        lead = self.get_object()
        if not can_access_doc_stage2(request.user):
            return Response({'error': 'You do not have access to documentation.'}, status=status.HTTP_403_FORBIDDEN)
        rec, _ = DocumentationStage2.objects.get_or_create(lead=lead)
        if rec.is_complete:
            return Response({'error': 'Documentation Stage 2 is completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        doc_type = request.data.get('doc_type')
        file = request.FILES.get('file')
        if not doc_type or not file:
            return Response({'error': 'doc_type and file are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if doc_type not in {k for k, _ in DocumentationStage2.DOC_SLOTS}:
            return Response({'error': 'Unknown document type.'}, status=status.HTTP_400_BAD_REQUEST)
        doc = DocumentationStage2Document.objects.create(
            stage2=rec, doc_type=doc_type, file=file,
            uploaded_by=request.user if request.user.is_authenticated else None)
        return Response(DocumentationStage2DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='documentation-stage2/documents/(?P<doc_id>[0-9]+)')
    def doc_stage2_delete_document(self, request, pk=None, doc_id=None):
        """Delete a single Documentation Stage 2 document."""
        from .access import can_access_doc_stage2
        lead = self.get_object()
        if not can_access_doc_stage2(request.user):
            return Response({'error': 'You do not have access to documentation.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            doc = DocumentationStage2Document.objects.get(pk=doc_id, stage2__lead=lead)
        except DocumentationStage2Document.DoesNotExist:
            return Response({'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        if doc.stage2.is_complete:
            return Response({'error': 'Documentation Stage 2 is completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='discom-followup')
    def discom_followup(self, request):
        """Discom Follow-up queue: Documentation Stage 2 customers whose discom
        approval needs chasing — explicitly not approved, or still pending for
        more than 7 days. Chasing the approval is the liasoning officer's job, so
        the queue lives in Liasoning; a customer leaves it once Documentation
        Stage 2 records the approval."""
        from datetime import timedelta
        from django.db.models import Q
        from .access import can_access_liasoning
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to liasoning & service.'}, status=status.HTTP_403_FORBIDDEN)
        cutoff = timezone.now() - timedelta(days=7)
        qs = (Lead.objects.filter(pushed_to_doc_stage2=True)
              .exclude(documentation_stage2__discom_approval='yes')
              # 'no' enters immediately; 'pending' only after 7 days in Stage 2.
              .filter(Q(documentation_stage2__discom_approval='no')
                      | Q(pushed_to_doc_stage2_at__lte=cutoff)
                      | Q(pushed_to_doc_stage2_at__isnull=True))
              .select_related('documentation_stage2')
              .order_by('-pushed_to_doc_stage2_at'))
        rows = []
        for lead in qs:
            rec = getattr(lead, 'documentation_stage2', None)
            rows.append({
                'id': lead.id,
                'first_name': lead.first_name,
                'last_name': lead.last_name,
                'phone': lead.phone,
                'location': lead.company,
                'installation_location': lead.installation_location,
                'discom_approval': rec.discom_approval if rec else 'pending',
                'sent_to_liasoning': bool(rec and rec.sent_to_liasoning),
                'is_complete': bool(rec and rec.is_complete),
                'pushed_at': lead.pushed_to_doc_stage2_at,
                'days_pending': (timezone.now() - lead.pushed_to_doc_stage2_at).days if lead.pushed_to_doc_stage2_at else None,
            })
        return Response(rows)

    @action(detail=True, methods=['patch'], url_path='discom-followup-sent')
    def discom_followup_sent(self, request, pk=None):
        """Tick 'liasoning officer sent to the concerned section' from the Discom
        Follow-up queue.

        Its own endpoint because the queue belongs to Liasoning while the flag
        itself lives on the Stage 2 record — the officer should not need
        documentation access to mark their own visit.
        """
        from .access import can_access_liasoning
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to liasoning & service.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_doc_stage2:
            return Response({'error': 'This lead is not in Documentation Stage 2.'}, status=status.HTTP_404_NOT_FOUND)
        rec, _ = DocumentationStage2.objects.get_or_create(lead=lead)
        rec.sent_to_liasoning = str(request.data.get('sent_to_liasoning')).lower() in ('true', '1', 'yes', 'on')
        rec.save(update_fields=['sent_to_liasoning', 'updated_at'])
        return Response({'id': lead.id, 'sent_to_liasoning': rec.sent_to_liasoning})

    # ── Warranty (post-installation documentation module) ──
    def _push_to_warranty(self, lead, request=None):
        """Hand the customer over to the Warranty module (idempotent).

        Normally happens in the fan-out when the project completes; also called
        when liasoning records the discom approval, so approved customers reach
        warranty even if they finished installation before that fan-out existed.
        """
        if lead.pushed_to_warranty:
            return False
        lead.pushed_to_warranty = True
        lead.pushed_to_warranty_at = timezone.now()
        lead.save(update_fields=['pushed_to_warranty', 'pushed_to_warranty_at'])
        Warranty.objects.get_or_create(lead=lead)
        ActivityLog.objects.create(
            activity_type='note_added',
            description="Discom approved — moved to warranty.",
            actor=request.user if (request and request.user.is_authenticated) else None,
            lead=lead, extra={'auto_generated': True})
        return True

    def _warranty_payload(self, lead, request):
        from .access import can_access_warranty
        rec = getattr(lead, 'warranty', None)

        def name(u):
            return (f"{u.first_name} {u.last_name}".strip() or u.username) if u else None

        return {
            'id': lead.id,
            # A trashed lead leaves this row behind and its detail page will
            # not open, so the list flags it and offers admins the broom.
            'lead_deleted': lead.is_trashed,
            'can_cleanup': lead.is_trashed and can_cleanup_deleted_lead(getattr(request, 'user', None)),
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
            'pushed_at': lead.pushed_to_warranty_at,
            'record': WarrantySerializer(rec, context={'request': request}).data if rec else None,
            'is_complete': bool(rec and rec.is_complete),
            'can_edit': can_access_warranty(request.user),
        }

    def _warranty_prefill(self, lead):
        """Pre-fill for the warranty certificate form, pulled from the customer's
        history (lead, site visit, Stage 1, project, Doc Stage 2 inverter/panel
        form). Saved form values always win over these on the frontend."""
        sv = getattr(lead, 'site_visit', None)
        s1 = getattr(lead, 'documentation_stage1', None)
        s2 = getattr(lead, 'documentation_stage2', None)
        pr = getattr(lead, 'project', None)
        ip = (s2.inverter_panel_details if s2 else {}) or {}
        product = (lead.product.name if lead.product else '') or ''
        return {
            'customer_name': f"{lead.first_name} {lead.last_name or ''}".strip(),
            'system_type': 'Hybrid' if 'hybrid' in product.lower() else 'OnGrid',
            'capacity_kw': ((s1.mnre_plant_capacity if s1 else '')
                            or (sv.plant_capacity if sv else '')
                            or (sv.feasible_capacity if sv else '') or ''),
            'panel_make': str(ip.get('panel_make') or ''),
            'inverter_make': str(ip.get('inverter_make') or ''),
            'installation_date': pr.completed_at.strftime('%d/%m/%Y') if (pr and pr.completed_at) else '',
            'site_address': lead.installation_location or lead.company or '',
        }

    def _warranty_org(self, request):
        """Fixed details printed on the warranty certificate — company identity,
        director sign-off, default warranty years, signature & seal — maintained
        in the Settings module (organization.OrgSettings), not entered per lead."""
        from organization.utils import get_org_settings
        org = get_org_settings()

        def url(f):
            if not f:
                return None
            return request.build_absolute_uri(f.url) if request else f.url

        return {
            'company_name': org.warranty_company_name,
            'cin': org.warranty_cin,
            'gst': org.warranty_gst,
            'director_name': org.warranty_director_name,
            'director_designation': org.warranty_director_designation,
            'panel_years': org.warranty_panel_years,
            'inverter_years': org.warranty_inverter_years,
            'service_years': org.warranty_service_years,
            'signature': url(org.warranty_signature),
            'seal': url(org.warranty_seal),
        }

    @action(detail=False, methods=['get'], url_path='warranty')
    def warranty(self, request):
        """Warranty queue: leads whose installation project is complete."""
        from .access import can_access_warranty
        if not can_access_warranty(request.user):
            return Response({'error': 'You do not have access to warranty.'}, status=status.HTTP_403_FORBIDDEN)
        qs = (Lead.objects.filter(pushed_to_warranty=True)
              .select_related('product', 'bde', 'documentation_staff', 'warranty')
              .order_by('-pushed_to_warranty_at'))
        return Response([self._warranty_payload(lead, request) for lead in qs])

    @action(detail=True, methods=['get'], url_path='warranty-detail')
    def warranty_detail(self, request, pk=None):
        """Full warranty view for one lead."""
        from .access import can_access_warranty
        if not can_access_warranty(request.user):
            return Response({'error': 'You do not have access to warranty.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_warranty:
            return Response({'error': 'This lead is not in the warranty stage.'}, status=status.HTTP_404_NOT_FOUND)
        Warranty.objects.get_or_create(lead=lead)
        return Response(self._warranty_payload(lead, request))

    @action(detail=True, methods=['get', 'patch'], url_path='warranty-record')
    def warranty_record(self, request, pk=None):
        """Get or update a lead's warranty record (sent flag, remark)."""
        from .access import can_access_warranty
        lead = self.get_object()
        if not can_access_warranty(request.user):
            return Response({'error': 'You do not have access to warranty.'}, status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_warranty:
            return Response({'error': 'This lead is not in the warranty stage.'}, status=status.HTTP_404_NOT_FOUND)
        rec, _ = Warranty.objects.get_or_create(lead=lead)
        if request.method == 'GET':
            data = WarrantySerializer(rec, context={'request': request}).data
            data['prefill'] = self._warranty_prefill(lead)
            data['org'] = self._warranty_org(request)
            return Response(data)
        if rec.is_complete:
            return Response({'error': 'Warranty is already completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = WarrantySerializer(rec, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='warranty/documents')
    def warranty_add_document(self, request, pk=None):
        """Upload one warranty document."""
        from .access import can_access_warranty
        lead = self.get_object()
        if not can_access_warranty(request.user):
            return Response({'error': 'You do not have access to warranty.'}, status=status.HTTP_403_FORBIDDEN)
        rec, _ = Warranty.objects.get_or_create(lead=lead)
        if rec.is_complete:
            return Response({'error': 'Warranty is completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        doc_type = request.data.get('doc_type')
        file = request.FILES.get('file')
        if not doc_type or not file:
            return Response({'error': 'doc_type and file are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if doc_type not in {k for k, _ in Warranty.DOC_SLOTS}:
            return Response({'error': 'Unknown document type.'}, status=status.HTTP_400_BAD_REQUEST)
        doc = WarrantyDocument.objects.create(
            warranty=rec, doc_type=doc_type, file=file,
            uploaded_by=request.user if request.user.is_authenticated else None)
        return Response(WarrantyDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='warranty/documents/(?P<doc_id>[0-9]+)')
    def warranty_delete_document(self, request, pk=None, doc_id=None):
        """Delete a single warranty document."""
        from .access import can_access_warranty
        lead = self.get_object()
        if not can_access_warranty(request.user):
            return Response({'error': 'You do not have access to warranty.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            doc = WarrantyDocument.objects.get(pk=doc_id, warranty__lead=lead)
        except WarrantyDocument.DoesNotExist:
            return Response({'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        if doc.warranty.is_complete:
            return Response({'error': 'Warranty is completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='send-warranty')
    def send_warranty(self, request, pk=None):
        """Send the warranty certificate to the customer over the configured
        WhatsApp / email integrations.

        Goes out from the CRM's own accounts (Settings → Integrations) rather
        than the staff member's device, so every send is logged in the outbox and
        arrives from the company, not from whoever happened to click.
        """
        from .access import can_access_warranty
        lead = self.get_object()
        if not can_access_warranty(request.user):
            return Response({'error': 'You do not have access to warranty.'},
                            status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_warranty:
            return Response({'error': 'This lead is not in the warranty stage.'},
                            status=status.HTTP_404_NOT_FOUND)
        rec, _ = Warranty.objects.get_or_create(lead=lead)

        # The generated certificate is the thing being sent; if staff attached
        # other files to the slot afterwards, prefer the certificate anyway.
        docs = list(rec.documents.filter(doc_type='warranty'))
        doc = next((d for d in reversed(docs)
                    if (d.file.name or '').split('/')[-1].startswith('Warranty_Certificate')),
                   docs[-1] if docs else None)
        if doc is None:
            return Response({'error': 'No warranty document to send. Generate the certificate first.'},
                            status=status.HTTP_400_BAD_REQUEST)

        who = f"{lead.first_name} {lead.last_name or ''}".strip()
        filename = (doc.file.name or 'Warranty.pdf').split('/')[-1]
        channels = [c.strip() for c in str(request.data.get('channels', 'email')).split(',') if c.strip()]
        results, failures, delivered = {}, [], []

        if 'email' in channels:
            raw = request.data.get('email') or lead.email or ''
            recipients = [a.strip() for a in str(raw).split(',') if a.strip()]
            if not recipients:
                failures.append('No email address given for this customer.')
            else:
                from messaging.email import send_and_log
                doc.file.open('rb')
                data = doc.file.read()
                doc.file.close()
                log = send_and_log(
                    to=recipients,
                    subject='Solar System Warranty',
                    body=(f"Dear {who or 'Customer'},\n\nPlease find attached the warranty "
                          f"certificate for your solar system.\n\nRegards,\nEnergyFox"),
                    lead=lead, kind='warranty',
                    attachments=[(filename, data, 'application/pdf')],
                    created_by=request.user if request.user.is_authenticated else None,
                )
                results['email'] = log.status
                if log.status == 'sent':
                    delivered.append(f"email to {', '.join(recipients)}")
                else:
                    failures.append(f'Email failed: {log.error}')

        if 'whatsapp' in channels:
            to = request.data.get('phone') or lead.phone or ''
            if not to:
                failures.append('No WhatsApp number given for this customer.')
            else:
                from messaging import whatsapp
                try:
                    whatsapp.send_document(
                        to=to,
                        link=request.build_absolute_uri(doc.file.url),
                        filename=filename,
                        caption='Solar System Warranty',
                    )
                    results['whatsapp'] = 'sent'
                    delivered.append(f'WhatsApp to {to}')
                except Exception as exc:                     # surfaced to the user
                    failures.append(f'WhatsApp failed: {exc}')

        # A recorded attempt is not a delivery: an SMTP refusal comes back as a
        # log with status 'failed', and neither the error nor the "sent" tick
        # should be softened into a success.
        sent_channels = [c for c, outcome in results.items() if outcome == 'sent']
        if not sent_channels:
            return Response({'error': ' '.join(failures) or 'Nothing was sent.'},
                            status=status.HTTP_502_BAD_GATEWAY)
        if not rec.sent:
            rec.sent = True
            rec.save(update_fields=['sent', 'updated_at'])
        # The hand-over of the warranty belongs on the customer's timeline.
        ActivityLog.objects.create(
            activity_type='note_added', lead=lead,
            actor=request.user if request.user.is_authenticated else None,
            description=f"Warranty certificate sent by {' and '.join(delivered)}.",
            extra={'auto_generated': True, 'channels': sorted(results)},
        )
        return Response({'sent': results, 'warnings': failures,
                         'pdf': request.build_absolute_uri(doc.file.url)})

    @action(detail=True, methods=['post'], url_path='complete-warranty')
    def complete_warranty(self, request, pk=None):
        """Mark warranty complete for a lead."""
        from .access import can_access_warranty
        if not can_access_warranty(request.user):
            return Response({'error': 'You do not have permission to complete warranty.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_warranty:
            return Response({'error': 'This lead is not in the warranty stage.'}, status=status.HTTP_404_NOT_FOUND)
        rec, _ = Warranty.objects.get_or_create(lead=lead)
        if rec.is_complete:
            return Response({'error': 'Warranty is already completed.'}, status=status.HTTP_400_BAD_REQUEST)
        rec.is_complete = True
        rec.completed_at = timezone.now()
        rec.completed_by = request.user if request.user.is_authenticated else None
        rec.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        ActivityLog.objects.create(
            activity_type='note_added', description="Warranty completed.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        fire_automation('warranty_completed', lead)
        return Response(self._warranty_payload(lead, request))

    # ── Liasoning & Service (post-installation; handled by the liasoning officer) ──
    def _liasoning_payload(self, lead, request):
        from .access import can_access_liasoning
        rec = getattr(lead, 'liasoning_service', None)

        def name(u):
            return (f"{u.first_name} {u.last_name}".strip() or u.username) if u else None

        return {
            'id': lead.id,
            # A trashed lead leaves its module rows behind — the detail
            # page refuses to open them, so the list flags them for cleanup.
            # `can_cleanup` is decided here so the six module screens don't each
            # have to fetch the current user to know whether to offer the button.
            'lead_deleted': lead.is_trashed,
            'can_cleanup': lead.is_trashed and can_cleanup_deleted_lead(getattr(request, 'user', None)),
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
            'pushed_at': lead.pushed_to_liasoning_at,
            'record': LiasoningServiceSerializer(rec, context={'request': request}).data if rec else None,
            'is_complete': bool(rec and rec.is_complete),
            'can_edit': can_access_liasoning(request.user),
        }

    @action(detail=False, methods=['get'], url_path='liasoning')
    def liasoning(self, request):
        """Liasoning & Service queue: leads whose installation project is complete."""
        from .access import can_access_liasoning
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to liasoning & service.'}, status=status.HTTP_403_FORBIDDEN)
        qs = (Lead.objects.filter(pushed_to_liasoning=True)
              .select_related('product', 'bde', 'liasoning_service')
              .order_by('-pushed_to_liasoning_at'))
        return Response([self._liasoning_payload(lead, request) for lead in qs])

    @action(detail=True, methods=['get'], url_path='liasoning-detail')
    def liasoning_detail(self, request, pk=None):
        """Full Liasoning & Service view for one lead."""
        from .access import can_access_liasoning
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to liasoning & service.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_liasoning:
            return Response({'error': 'This lead is not in liasoning & service.'}, status=status.HTTP_404_NOT_FOUND)
        LiasoningService.objects.get_or_create(lead=lead)
        return Response(self._liasoning_payload(lead, request))

    @action(detail=True, methods=['get', 'patch'], url_path='liasoning-record')
    def liasoning_record(self, request, pk=None):
        """Get or update a lead's liasoning record (Annexure 3).

        The Annexure 3 status, remark and discom approval write through to the
        lead's Documentation Stage 2 — its Annexure section is 'fetched from
        liasoning' (the liasoning officer is the one at the KSEB section).

        Feasibility lives in the KSEB Feasibility module, not here."""
        from .access import can_access_liasoning
        lead = self.get_object()
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to liasoning & service.'}, status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_liasoning:
            return Response({'error': 'This lead is not in liasoning & service.'}, status=status.HTTP_404_NOT_FOUND)
        rec, _ = LiasoningService.objects.get_or_create(lead=lead)
        if request.method == 'GET':
            return Response(LiasoningServiceSerializer(rec, context={'request': request}).data)
        if rec.is_complete:
            return Response({'error': 'Liasoning & Service is already completed and locked.'}, status=status.HTTP_400_BAD_REQUEST)
        # Discom approval is owned by Documentation Stage 2 (auto-fetched via
        # write-through) — it cannot be edited from here.
        data = {k: v for k, v in request.data.items() if k != 'discom_approval'}
        serializer = LiasoningServiceSerializer(rec, data=data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Annexure 3 belongs to liasoning — Documentation Stage 2 only displays
        # it — so it syncs through even when Stage 2 has been completed and
        # locked. Otherwise a later submission would never reach the record.
        synced = {'annexure3_completed', 'annexure3_remark'} & set(data.keys())
        if synced:
            s2, _ = DocumentationStage2.objects.get_or_create(lead=lead)
            update = []
            if 'annexure3_completed' in synced:
                s2.annexure3_completed = rec.annexure3_completed
                update.append('annexure3_completed')
            if 'annexure3_remark' in synced:
                s2.annexure3_remark = rec.annexure3_remark
                update.append('annexure3_remark')
            s2.save(update_fields=update + ['updated_at'])
        return Response(LiasoningServiceSerializer(rec, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='liasoning/documents',
            parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def liasoning_add_document(self, request, pk=None):
        """Attach a file to a liasoning record — the commissioned plant photo."""
        from .access import can_access_liasoning
        lead = self.get_object()
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to liasoning & service.'},
                            status=status.HTTP_403_FORBIDDEN)
        rec, _ = LiasoningService.objects.get_or_create(lead=lead)
        if rec.is_complete:
            return Response({'error': 'Liasoning & Service is completed and locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'file is required.'}, status=status.HTTP_400_BAD_REQUEST)
        doc_type = (request.data.get('doc_type') or LiasoningService.PLANT_PHOTO).strip()
        if doc_type != LiasoningService.PLANT_PHOTO:
            return Response({'error': 'Unknown document type.'}, status=status.HTTP_400_BAD_REQUEST)
        doc = LiasoningDocument.objects.create(
            liasoning=rec, doc_type=doc_type, file=file,
            uploaded_by=request.user if request.user.is_authenticated else None)
        return Response(LiasoningDocumentSerializer(doc, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='liasoning/documents/(?P<doc_id>[0-9]+)')
    def liasoning_delete_document(self, request, pk=None, doc_id=None):
        """Remove a liasoning file. Refused once the record is signed off — the
        photo is the evidence behind that sign-off."""
        from .access import can_access_liasoning
        lead = self.get_object()
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to liasoning & service.'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            doc = LiasoningDocument.objects.get(pk=doc_id, liasoning__lead=lead)
        except LiasoningDocument.DoesNotExist:
            return Response({'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        if doc.liasoning.is_complete:
            return Response({'error': 'Liasoning & Service is completed and locked.'},
                            status=status.HTTP_400_BAD_REQUEST)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='complete-liasoning')
    def complete_liasoning(self, request, pk=None):
        """Mark Liasoning & Service complete for a lead."""
        from .access import can_access_liasoning
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have permission to complete liasoning & service.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not lead.pushed_to_liasoning:
            return Response({'error': 'This lead is not in liasoning & service.'}, status=status.HTTP_404_NOT_FOUND)
        rec, _ = LiasoningService.objects.get_or_create(lead=lead)
        if rec.is_complete:
            return Response({'error': 'Liasoning & Service is already completed.'}, status=status.HTTP_400_BAD_REQUEST)
        # Signing this off says the plant is live, so it waits on the evidence.
        if not rec.has_plant_photo:
            return Response(
                {'error': 'Upload the commissioned plant photo before completing liasoning.',
                 'needs_plant_photo': True},
                status=status.HTTP_400_BAD_REQUEST)
        rec.is_complete = True
        rec.completed_at = timezone.now()
        rec.completed_by = request.user if request.user.is_authenticated else None
        rec.save(update_fields=['is_complete', 'completed_at', 'completed_by', 'updated_at'])
        ActivityLog.objects.create(
            activity_type='note_added', description="Liasoning & Service completed.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        fire_automation('liasoning_completed', lead)
        return Response(self._liasoning_payload(lead, request))

    # ── Periodic maintenance (5 years, 6-month tenure gap) ──
    @staticmethod
    def _add_months(d, months):
        import calendar
        from datetime import date as _date
        y = d.year + (d.month - 1 + months) // 12
        m = (d.month - 1 + months) % 12 + 1
        return _date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

    def _pm_detail(self, lead, request):
        from .access import can_access_liasoning
        plan = getattr(lead, 'periodic_maintenance', None)

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
            'bde_name': name(lead.bde),
            'plan': PeriodicMaintenanceSerializer(plan, context={'request': request}).data if plan else None,
            'can_edit': can_access_liasoning(request.user),
        }

    @action(detail=False, methods=['get'], url_path='periodic-maintenance')
    def periodic_maintenance(self, request):
        """Scheduled customer list, plus installed customers not yet scheduled."""
        from .access import can_access_liasoning
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to periodic maintenance.'}, status=status.HTTP_403_FORBIDDEN)
        qs = (Lead.objects.filter(pushed_to_liasoning=True)
              .select_related('periodic_maintenance')
              .prefetch_related('periodic_maintenance__visits')
              .order_by('-pushed_to_liasoning_at'))
        scheduled, eligible = [], []
        for lead in qs:
            plan = getattr(lead, 'periodic_maintenance', None)
            base = {'id': lead.id, 'first_name': lead.first_name, 'last_name': lead.last_name,
                    'phone': lead.phone, 'location': lead.company}
            if plan:
                visits = list(plan.visits.all())
                done = sum(1 for v in visits if v.is_complete)
                nxt = next((v for v in visits if not v.is_complete), None)
                scheduled.append({**base,
                                  'start_date': plan.start_date,
                                  'done_count': done,
                                  'total_visits': len(visits),
                                  'next_due': nxt.due_date if nxt else None,
                                  'next_sequence': nxt.sequence if nxt else None})
            else:
                eligible.append(base)
        return Response({'scheduled': scheduled, 'eligible': eligible})

    @action(detail=True, methods=['post'], url_path='schedule-maintenance')
    def schedule_maintenance(self, request, pk=None):
        """Put a customer on the periodic maintenance schedule: 5 years of visits,
        one every 6 months, starting from the given start date."""
        from datetime import date as _date
        from .access import can_access_liasoning
        lead = self.get_object()
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to periodic maintenance.'}, status=status.HTTP_403_FORBIDDEN)
        if not lead.pushed_to_liasoning:
            return Response({'error': 'This customer is not in liasoning & service yet.'}, status=status.HTTP_404_NOT_FOUND)
        if getattr(lead, 'periodic_maintenance', None):
            return Response({'error': 'This customer is already scheduled.'}, status=status.HTTP_400_BAD_REQUEST)
        raw = (request.data.get('start_date') or '').strip()
        try:
            start = _date.fromisoformat(raw) if raw else timezone.localdate()
        except ValueError:
            return Response({'error': 'Enter a valid start date (YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)
        plan = PeriodicMaintenance.objects.create(
            lead=lead, start_date=start,
            created_by=request.user if request.user.is_authenticated else None)
        for i in range(1, PeriodicMaintenance.VISIT_COUNT + 1):
            MaintenanceVisit.objects.create(
                plan=plan, sequence=i,
                due_date=self._add_months(start, PeriodicMaintenance.GAP_MONTHS * i))
        ActivityLog.objects.create(
            activity_type='note_added',
            description=f"Scheduled for periodic maintenance: {PeriodicMaintenance.VISIT_COUNT} visits every "
                        f"{PeriodicMaintenance.GAP_MONTHS} months from {start.strftime('%d/%m/%Y')}.",
            actor=request.user if request.user.is_authenticated else None,
            lead=lead, extra={'auto_generated': True})
        fire_automation('maintenance_scheduled', lead, {'start_date': start.isoformat()})
        return Response(self._pm_detail(lead, request))

    @action(detail=True, methods=['get'], url_path='maintenance-detail')
    def maintenance_detail(self, request, pk=None):
        """Full maintenance view for one customer (plan + all visits)."""
        from .access import can_access_liasoning
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to periodic maintenance.'}, status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if not getattr(lead, 'periodic_maintenance', None):
            return Response({'error': 'This customer is not scheduled for maintenance.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._pm_detail(lead, request))

    @action(detail=True, methods=['patch'], url_path='maintenance-visits/(?P<visit_id>[0-9]+)')
    def maintenance_visit_update(self, request, pk=None, visit_id=None):
        """Update one maintenance visit's readings; toggling ``is_complete`` stamps
        who completed it and when."""
        from .access import can_access_liasoning
        lead = self.get_object()
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to periodic maintenance.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            visit = MaintenanceVisit.objects.get(pk=visit_id, plan__lead=lead)
        except MaintenanceVisit.DoesNotExist:
            return Response({'error': 'Visit not found.'}, status=status.HTTP_404_NOT_FOUND)
        was_complete = visit.is_complete
        serializer = MaintenanceVisitSerializer(visit, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if visit.is_complete and not was_complete:
            visit.completed_at = timezone.now()
            visit.completed_by = request.user if request.user.is_authenticated else None
            visit.save(update_fields=['completed_at', 'completed_by', 'updated_at'])
        elif was_complete and not visit.is_complete:
            visit.completed_at = None
            visit.completed_by = None
            visit.save(update_fields=['completed_at', 'completed_by', 'updated_at'])
        return Response(MaintenanceVisitSerializer(visit, context={'request': request}).data)

    @action(detail=True, methods=['post'],
            url_path='maintenance-visits/(?P<visit_id>[0-9]+)/reschedule')
    def maintenance_visit_reschedule(self, request, pk=None, visit_id=None):
        """Move a visit's due date.

        Its own action rather than a field on the general PATCH, because moving a
        scheduled visit is a decision worth recording: the original date is kept
        and the change is written to the customer's timeline.
        """
        from datetime import date as _date
        from .access import can_access_liasoning
        lead = self.get_object()
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to periodic maintenance.'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            visit = MaintenanceVisit.objects.get(pk=visit_id, plan__lead=lead)
        except MaintenanceVisit.DoesNotExist:
            return Response({'error': 'Visit not found.'}, status=status.HTTP_404_NOT_FOUND)
        if visit.is_complete:
            return Response({'error': 'This visit is already done — there is nothing to reschedule.'},
                            status=status.HTTP_400_BAD_REQUEST)

        raw = (request.data.get('due_date') or '').strip()
        try:
            new_date = _date.fromisoformat(raw)
        except ValueError:
            return Response({'error': 'Give the new date as YYYY-MM-DD.'},
                            status=status.HTTP_400_BAD_REQUEST)

        was = visit.due_date
        if new_date == was:
            return Response({'error': 'That is the date it is already due on.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Remember where it started, so a visit moved twice still shows the date
        # the schedule originally called for.
        if visit.original_due_date is None:
            visit.original_due_date = was
        visit.due_date = new_date
        visit.reschedule_reason = (request.data.get('reason') or '').strip()[:255]
        visit.save(update_fields=['due_date', 'original_due_date', 'reschedule_reason', 'updated_at'])

        ActivityLog.objects.create(
            activity_type='note_added', lead=lead,
            actor=request.user if request.user.is_authenticated else None,
            description=(f'Maintenance visit {visit.sequence} rescheduled from '
                         f'{was.isoformat()} to {new_date.isoformat()}'
                         + (f' — {visit.reschedule_reason}' if visit.reschedule_reason else '.')),
            extra={'auto_generated': True, 'visit': visit.sequence,
                   'from': was.isoformat(), 'to': new_date.isoformat()},
        )
        return Response(MaintenanceVisitSerializer(visit, context={'request': request}).data)

    @action(detail=True, methods=['post'],
            url_path='maintenance-visits/(?P<visit_id>[0-9]+)/documents',
            parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def maintenance_visit_add_document(self, request, pk=None, visit_id=None):
        """Attach one photo to a slot on a visit. Slots hold several files —
        a panel is photographed from more than one angle."""
        from .access import can_access_liasoning
        lead = self.get_object()
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to periodic maintenance.'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            visit = MaintenanceVisit.objects.get(pk=visit_id, plan__lead=lead)
        except MaintenanceVisit.DoesNotExist:
            return Response({'error': 'Visit not found.'}, status=status.HTTP_404_NOT_FOUND)
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'file is required.'}, status=status.HTTP_400_BAD_REQUEST)
        doc_type = (request.data.get('doc_type') or '').strip()
        if doc_type not in {k for k, _ in MaintenanceVisit.PHOTO_SLOTS}:
            return Response({'error': 'Unknown photo slot.'}, status=status.HTTP_400_BAD_REQUEST)
        doc = MaintenanceVisitDocument.objects.create(
            visit=visit, doc_type=doc_type, file=file,
            uploaded_by=request.user if request.user.is_authenticated else None)
        return Response(MaintenanceVisitDocumentSerializer(doc, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'],
            url_path='maintenance-visits/(?P<visit_id>[0-9]+)/documents/(?P<doc_id>[0-9]+)')
    def maintenance_visit_delete_document(self, request, pk=None, visit_id=None, doc_id=None):
        """Remove one photo from a visit."""
        from .access import can_access_liasoning
        lead = self.get_object()
        if not can_access_liasoning(request.user):
            return Response({'error': 'You do not have access to periodic maintenance.'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            doc = MaintenanceVisitDocument.objects.get(
                pk=doc_id, visit_id=visit_id, visit__plan__lead=lead)
        except MaintenanceVisitDocument.DoesNotExist:
            return Response({'error': 'Photo not found.'}, status=status.HTTP_404_NOT_FOUND)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get', 'patch'], url_path='team-stats')
    def team_stats(self, request):
        """Structure/electrical team stats, derived from project work-completion
        dates, plus the manually-set team lead names. PATCH updates the leads."""
        import datetime
        from .access import can_access_project, can_assign_project
        if not can_access_project(request.user):
            return Response({'error': 'You do not have access to team stats.'}, status=status.HTTP_403_FORBIDDEN)
        cfg = TeamStatsConfig.get_solo()
        if request.method == 'PATCH':
            for f in ('structure_team_lead', 'electrical_team_lead'):
                if f in request.data:
                    setattr(cfg, f, request.data.get(f) or '')
            cfg.save()

        today = timezone.localdate()
        seq = []
        for i in range(5, -1, -1):
            mm, yy = today.month - i, today.year
            while mm <= 0:
                mm += 12
                yy -= 1
            seq.append((yy, mm))

        def series_for(field):
            out = []
            for (yy, mm) in seq:
                count = Lead.objects.filter(**{
                    'project__%s__year' % field: yy,
                    'project__%s__month' % field: mm,
                }).count()
                out.append({'label': datetime.date(yy, mm, 1).strftime('%b'), 'count': count})
            return out

        structure_series = series_for('structure_work_completed_date')
        electrical_series = series_for('electrical_work_completed_date')
        return Response({
            'structure': {
                'team_lead': cfg.structure_team_lead,
                'this_month': structure_series[-1]['count'],
                'series': structure_series,
            },
            'electrical': {
                'team_lead': cfg.electrical_team_lead,
                'this_month': electrical_series[-1]['count'],
                'series': electrical_series,
            },
            'can_edit': can_access_project(request.user),
        })

    def get_queryset(self):
        user = self.request.user
        # site_visit is read for every row (the list's Site Visit button/indicator),
        # so pull it in the same query instead of one per lead.
        base = Lead.objects.select_related('assigned_to', 'tele_caller', 'bde', 'site_visit')
        if user.sees_all_leads:
            # superadmin / admin / coo / sales & documentation managers / documentation staff
            queryset = base.all().order_by('-created_at')
        elif user.branch_scoped:
            # Branch manager: everything their branch works on — leads owned by
            # branch staff, handled by a branch BDE, plus their own + unassigned.
            from django.db.models import Q
            scope = own_leads_q(user) | Q(assigned_to__isnull=True)
            if user.branch_id:
                scope |= Q(assigned_to__branch_id=user.branch_id) | Q(bde__branch_id=user.branch_id)
            queryset = base.filter(scope).distinct().order_by('-created_at')
        else:
            # Tele caller: leads they own or once owned (handing a lead to a BDE
            # moves assigned_to, and it must not disappear from their list).
            # BDE: leads handed off to them as BDE.
            from django.db.models import Q
            queryset = base.filter(own_leads_q(user)).distinct().order_by('-created_at')

        # Trashed leads live only in the Trash view (and are purged after 7 days).
        queryset = queryset.filter(is_trashed=False)

        # Archived (old, terminal) leads are out of the hot working set by
        # default — pass ?archived=true to view them, ?archived=all for both.
        archived_param = (self.request.query_params.get('archived') or '').lower()
        if archived_param in ('true', '1', 'yes', 'only'):
            queryset = queryset.filter(is_archived=True)
        elif archived_param != 'all':
            queryset = queryset.filter(is_archived=False)

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

        # Filter by fulfilment pipeline stage (the module a lead is currently in).
        # Mirrors Lead.pipeline_stage: each stage excludes any further-advanced flag.
        stage = self.request.query_params.get('stage')
        if stage:
            stage_filters = {
                'project': {'pushed_to_project': True},
                'purchase': {'pushed_to_purchase': True, 'pushed_to_project': False},
                'accounts': {'pushed_to_accounts': True, 'pushed_to_purchase': False},
                'documentation': {'pushed_to_documentation': True, 'pushed_to_accounts': False},
                'site_visit': {'bde__isnull': False, 'pushed_to_documentation': False},
                'tele_caller': {'bde__isnull': True},
            }.get(stage)
            if stage_filters:
                queryset = queryset.filter(**stage_filters)

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

        # Filter by the Meta integration (one per branch) the lead came from.
        # Accepts an integration id, 'none' for leads with no integration, or a
        # name so saved links/automation rules can use the friendly branch name.
        meta_integration = self.request.query_params.get('meta_integration')
        if meta_integration:
            if meta_integration == 'none':
                queryset = queryset.filter(meta_integration__isnull=True)
            elif str(meta_integration).isdigit():
                queryset = queryset.filter(meta_integration_id=int(meta_integration))
            else:
                queryset = queryset.filter(meta_integration__name__iexact=meta_integration)

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

    @staticmethod
    def _stamp_owner_role(queryset, target_user):
        """Bulk assignment uses queryset.update(), which skips Lead.save() — so
        the ownership stamps have to be applied here too. Mirrors Lead.save():
        an owner who is a tele caller is recorded as the tele caller, one who is
        a BDE is recorded as the BDE (without which the lead can never be
        converted).

        The tele caller stamp is sticky; the BDE stamp is replaced, so moving a
        lead between BDEs takes it out of the previous one's list.
        """
        role = getattr(target_user, 'role', '') if target_user else ''
        if role == 'tele_caller':
            queryset.filter(tele_caller__isnull=True).update(tele_caller=target_user)
        elif role == 'bde':
            queryset.exclude(bde=target_user).update(bde=target_user)

    @staticmethod
    def _assignable_user_ids(user):
        """Ids this user may hand a lead to, or None when unrestricted.
        Mirrors the people the assignee picker offers (see
        ``User.assignable_lead_user_ids`` / ``/api/users/assignable/``)."""
        if not user or not user.is_authenticated:
            return set()
        return user.assignable_lead_user_ids()

    def perform_create(self, serializer):
        from rest_framework.exceptions import PermissionDenied
        from .access import can_add_leads, can_edit_lead_status

        # Leads are sourced by the tele-calling side; a BDE only receives them.
        if not can_add_leads(self.request.user):
            raise PermissionDenied('A BDE cannot add leads.')

        # Belt and braces for any other role that may not own the status.
        new_status = serializer.validated_data.get('status')
        if new_status and new_status != 'new' and not can_edit_lead_status(self.request.user):
            raise PermissionDenied('You cannot set the lead status.')

        instance = serializer.save()

        # An agent who adds a lead without naming an assignee keeps it: their
        # lead list is scoped to leads they own, so an unassigned one would
        # otherwise vanish the moment it was created.
        user = self.request.user
        if (instance.assigned_to_id is None and user.is_authenticated
                and not user.is_staff
                and not getattr(user, 'is_general_manager', False)
                and not getattr(user, 'is_manager', False)):
            instance.assigned_to = user
            instance.save(update_fields=['assigned_to'])

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
        # The lead record belongs to the tele-calling side. A BDE reports through
        # the site visit, so editing the lead itself is closed to them — their
        # own actions (site visit, mark lost) are separate endpoints.
        from .access import can_edit_leads
        if not can_edit_leads(self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('A BDE cannot edit lead details.')

        old_status = serializer.instance.status
        old_notes  = serializer.instance.notes or ""

        # BDEs don't own the lead status — they report through the site visit.
        # Only an actual change is refused, so a PATCH that echoes back the
        # current status (as the edit form does) still saves its other fields.
        new_status = serializer.validated_data.get('status')
        if new_status is not None and new_status != old_status:
            from .access import can_edit_lead_status
            if not can_edit_lead_status(self.request.user):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('A BDE cannot change the lead status.')

        # Re-assignment is scoped the same way as bulk assign: agents may only
        # hand a lead to their own team, and a BDE may not route leads at all.
        # As with the status, an unchanged owner (the edit form posts it back) is
        # not a re-assignment.
        if 'assigned_to' in serializer.validated_data:
            from rest_framework.exceptions import PermissionDenied
            target = serializer.validated_data['assigned_to']
            target_id = target.id if target is not None else None
            if target_id != serializer.instance.assigned_to_id:
                from .access import can_assign_leads
                if not can_assign_leads(self.request.user):
                    raise PermissionDenied('A BDE cannot assign leads.')
                allowed = self._assignable_user_ids(self.request.user)
                if target is not None and allowed is not None and target.id not in allowed:
                    raise PermissionDenied('You can only assign leads to your team or another tele caller / BDE.')


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
                if instance.status == 'converted':
                    fire_trigger('lead_converted', instance, {'old_status': old_status})
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
        from .access import can_use_lead_tools
        if not can_use_lead_tools(request.user):
            return Response({'error': 'Not available to a BDE.'},
                            status=status.HTTP_403_FORBIDDEN)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="leads_template.csv"'
        writer = csv.writer(response)
        writer.writerow(['first_name', 'last_name', 'email', 'phone', 'source', 'status'])
        writer.writerow(['John', 'Doe', 'john@example.com', '1234567890', 'manual', 'new'])
        return response

    @action(detail=False, methods=['post'])
    def bulk_upload(self, request):
        """Handles bulk uploads from a CSV file."""
        from .access import can_add_leads
        if not can_add_leads(request.user):
            return Response({'error': 'A BDE cannot add leads.'}, status=status.HTTP_403_FORBIDDEN)

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
        from .access import can_use_lead_tools
        if not can_use_lead_tools(request.user):
            return Response({'error': 'Not available to a BDE.'},
                            status=status.HTTP_403_FORBIDDEN)
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

    # ── Trash (soft delete; auto-purged after Lead.TRASH_RETENTION_DAYS) ──

    def destroy(self, request, *args, **kwargs):
        """Deleting a lead moves it to Trash instead of removing it. It can be
        restored from the Trash view for 7 days, after which it is purged."""
        from .access import can_delete_leads
        if not can_delete_leads(request.user):
            return Response({'error': 'A BDE cannot delete leads.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        lead.is_trashed = True
        lead.trashed_at = timezone.now()
        lead.trashed_by = request.user if request.user.is_authenticated else None
        lead.save(update_fields=['is_trashed', 'trashed_at', 'trashed_by'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """Moves multiple leads to Trash at once."""
        from .access import can_delete_leads
        if not can_delete_leads(request.user):
            return Response({'error': 'A BDE cannot delete leads.'},
                            status=status.HTTP_403_FORBIDDEN)
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'No lead IDs provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Only allow trashing from the user's accessible set
        queryset = self.get_queryset().filter(id__in=ids)
        count = queryset.update(
            is_trashed=True, trashed_at=timezone.now(),
            trashed_by=request.user if request.user.is_authenticated else None)

        return Response({'message': f'Moved {count} leads to Trash.'})

    @staticmethod
    def _purge_expired_trash():
        """Permanently delete anything trashed more than the retention ago."""
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=Lead.TRASH_RETENTION_DAYS)
        Lead.objects.filter(is_trashed=True, trashed_at__lte=cutoff).delete()

    def _trash_scope(self):
        """Trashed leads the current user may see — mirrors the normal role scope."""
        from django.db.models import Q
        user = self.request.user
        qs = Lead.objects.filter(is_trashed=True).select_related('assigned_to', 'trashed_by')
        if user.sees_all_leads:
            return qs
        if getattr(user, 'branch_scoped', False):
            return qs.filter(Q(assigned_to=user) | Q(assigned_to__isnull=True)
                             | Q(assigned_to__branch=user.branch)).distinct()
        return qs.filter(Q(assigned_to=user) | Q(bde=user)).distinct()

    @action(detail=False, methods=['get'], url_path='trash')
    def trash(self, request):
        """The Trash: soft-deleted leads with their days left before purge."""
        from .access import can_use_lead_tools
        if not can_use_lead_tools(request.user):
            return Response({'error': 'Not available to a BDE.'},
                            status=status.HTTP_403_FORBIDDEN)
        self._purge_expired_trash()
        rows = []
        for lead in self._trash_scope().order_by('-trashed_at'):
            days_gone = (timezone.now() - lead.trashed_at).days if lead.trashed_at else 0
            trasher = lead.trashed_by
            rows.append({
                'id': lead.id,
                'first_name': lead.first_name,
                'last_name': lead.last_name,
                'phone': lead.phone,
                'email': lead.email,
                'status': lead.status,
                'trashed_at': lead.trashed_at,
                'trashed_by_name': (f"{trasher.first_name} {trasher.last_name}".strip() or trasher.username) if trasher else None,
                'days_left': max(0, Lead.TRASH_RETENTION_DAYS - days_gone),
            })
        return Response({'retention_days': Lead.TRASH_RETENTION_DAYS, 'leads': rows})

    @action(detail=True, methods=['post'], url_path='restore-trash')
    def restore_trash(self, request, pk=None):
        """Bring a lead back from the Trash."""
        lead = self._trash_scope().filter(pk=pk).first()
        if lead is None:
            return Response({'error': 'Lead not found in Trash.'}, status=status.HTTP_404_NOT_FOUND)
        lead.is_trashed = False
        lead.trashed_at = None
        lead.trashed_by = None
        lead.save(update_fields=['is_trashed', 'trashed_at', 'trashed_by'])
        return Response({'message': 'Lead restored.'})

    @action(detail=True, methods=['delete'], url_path='purge')
    def purge_trash(self, request, pk=None):
        """Permanently delete one trashed lead right now (skips the 7-day wait)."""
        lead = self._trash_scope().filter(pk=pk).first()
        if lead is None:
            return Response({'error': 'Lead not found in Trash.'}, status=status.HTTP_404_NOT_FOUND)
        lead.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['delete'], url_path='empty-trash')
    def empty_trash(self, request):
        """Permanently delete everything in the Trash, now.

        Irreversible and workspace-wide, so it is a super admin's call alone —
        not an admin's, and not scoped to what the caller happens to see. The
        client asks for confirmation; this is the guard that actually holds.
        """
        user = request.user
        if getattr(user, 'role', '') != 'superadmin':
            return Response(
                {'error': 'Only a super admin can empty the Trash.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = Lead.objects.filter(is_trashed=True)
        count = qs.count()
        if not count:
            return Response({'deleted': 0, 'message': 'The Trash is already empty.'})
        qs.delete()
        return Response({
            'deleted': count,
            'message': f'Permanently deleted {count} lead{"" if count == 1 else "s"}.',
        })

    # ── Archive (old, terminal leads kept out of the hot working set) ──
    @action(detail=True, methods=['post'], url_path='archive')
    def archive_lead(self, request, pk=None):
        """Move a lead to the archive (kept, but out of the active lists)."""
        from .access import can_use_lead_tools
        if not can_use_lead_tools(request.user):
            return Response({'error': 'Not available to a BDE.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead = self.get_object()
        if lead.is_archived:
            return Response({'error': 'This lead is already archived.'}, status=status.HTTP_400_BAD_REQUEST)
        lead.is_archived = True
        lead.archived_at = timezone.now()
        lead.save(update_fields=['is_archived', 'archived_at'])
        return Response({'message': 'Lead archived.'})

    @action(detail=True, methods=['post'], url_path='unarchive')
    def unarchive_lead(self, request, pk=None):
        """Restore a lead from the archive back into the active lists."""
        from .access import can_use_lead_tools
        if not can_use_lead_tools(request.user):
            return Response({'error': 'Not available to a BDE.'},
                            status=status.HTTP_403_FORBIDDEN)
        lead = Lead.objects.filter(pk=pk, is_archived=True).first()
        if lead is None:
            return Response({'error': 'Lead not found in the archive.'}, status=status.HTTP_404_NOT_FOUND)
        lead.is_archived = False
        lead.archived_at = None
        lead.save(update_fields=['is_archived', 'archived_at'])
        return Response({'message': 'Lead restored from archive.'})

    @action(detail=False, methods=['get'], url_path='archive-stats')
    def archive_stats(self, request):
        """How many leads are archived vs active (for the Leads page toggle)."""
        base = Lead.objects.filter(is_trashed=False)
        return Response({
            'archived': base.filter(is_archived=True).count(),
            'active': base.filter(is_archived=False).count(),
            'archive_after_months': Lead.ARCHIVE_AFTER_MONTHS,
        })

    @action(detail=False, methods=['post'])
    def bulk_assign(self, request):
        """Assigns multiple leads to a user at once."""
        ids = request.data.get('ids', [])
        user_id = request.data.get('user_id')
        
        if not ids or user_id is None:
            return Response({'error': 'IDs and user_id are required'}, status=status.HTTP_400_BAD_REQUEST)

        from .access import can_assign_leads
        if not can_assign_leads(request.user):
            return Response({'error': 'A BDE cannot assign leads.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            from users.models import User
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Target user not found'}, status=status.HTTP_404_NOT_FOUND)

        allowed = self._assignable_user_ids(request.user)
        if allowed is not None and target_user.id not in allowed:
            return Response({'error': 'You can only assign leads to your team or another tele caller / BDE.'},
                            status=status.HTTP_403_FORBIDDEN)

        queryset = self.get_queryset().filter(id__in=ids)
        count = queryset.update(assigned_to=target_user)
        self._stamp_owner_role(Lead.objects.filter(id__in=ids), target_user)

        return Response({'message': f'Successfully assigned {count} leads to {target_user.username}.'})

    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        """Updates multiple leads with provided fields at once."""
        ids = request.data.get('ids', [])
        update_data = request.data.get('data', {})
        
        if not ids or not update_data:
            return Response({'error': 'IDs and update data are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        allowed_fields = ['status', 'source']

        if update_data.get('status'):
            from .access import can_edit_lead_status
            if not can_edit_lead_status(request.user):
                return Response({'error': 'A BDE cannot change the lead status.'},
                                status=status.HTTP_403_FORBIDDEN)

        if update_data.get('assigned_to_id'):
            from .access import can_assign_leads
            if not can_assign_leads(request.user):
                return Response({'error': 'A BDE cannot assign leads.'},
                                status=status.HTTP_403_FORBIDDEN)

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
            if valid_data.get('assigned_to_id'):
                from users.models import User as _U
                self._stamp_owner_role(Lead.objects.filter(id__in=ids),
                                       _U.objects.filter(pk=valid_data['assigned_to_id']).first())
        
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
        
        base_qs = reporting_scope(user)
        
        total_leads = base_qs.count()
        new_today = base_qs.filter(created_at__date=today).count()
        
        # Pipeline breakdown
        pipeline_data = base_qs.values('status').annotate(count=Count('id'))
        pipeline = {item['status']: item['count'] for item in pipeline_data}
        
        # Total Pipeline Value (Rupees)
        total_value = base_qs.aggregate(total=Sum('value'))['total'] or 0
        
        # Revenue Generated (Enrolled & Partially Paid Leads)
        won_qs = base_qs.filter(status__in=['converted'])
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
                users_to_check = (WorkspaceUser.objects
                                  .filter(id__in=user.managed_user_ids(), is_active=True)
                                  .distinct())
                # Managers can see all teams for comparison as requested
                teams_to_check = WorkspaceTeam.objects.all()
            
            # Member Stats using ORM Annotation
            users_with_stats = users_to_check.annotate(
                calc_leads_count=Count('assigned_leads'),
                calc_pipeline_value=Sum('assigned_leads__value'),
                calc_won_count=Count('assigned_leads', filter=Q(assigned_leads__status__in=['converted'])),
                calc_won_value=Sum('assigned_leads__value', filter=Q(assigned_leads__status__in=['converted']))
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
                calc_won_count=Count('members__assigned_leads', filter=Q(members__assigned_leads__status__in=['converted'])),
                calc_won_value=Sum('members__assigned_leads__value', filter=Q(members__assigned_leads__status__in=['converted']))
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

        # Credit goes to the lead's BDE, not its owner: the tele caller hands a
        # lead over and the BDE closes it (a lead cannot even reach Converted
        # until a BDE is assigned — see LeadSerializer.validate), so `bde` is the
        # relation that actually carries the sale.
        # A deleted lead is not a closed sale — its value must not sit on
        # anyone's board. Restoring it from the Trash puts it back.
        won_filter = Q(bde_leads__status__in=['converted'],
                       bde_leads__is_trashed=False)

        if period == 'daily':
            won_filter &= (
                Q(bde_leads__status_changed_at__date=today) |
                (Q(bde_leads__status_changed_at__isnull=True) & Q(bde_leads__created_at__date=today))
            )
        elif period == 'monthly':
            current_month = today.month
            current_year = today.year
            won_filter &= (
                Q(bde_leads__status_changed_at__month=current_month, bde_leads__status_changed_at__year=current_year) |
                (Q(bde_leads__status_changed_at__isnull=True) & Q(bde_leads__created_at__month=current_month, bde_leads__created_at__year=current_year))
            )

        # Single annotated query instead of N+1 loop
        from users.models import User as WorkspaceUser
        from django.db.models.functions import Coalesce
        from decimal import Decimal
        # Coalesce revenue to 0 so users with no won leads don't get a NULL,
        # which PostgreSQL sorts FIRST on a descending order (pushing zero-sales
        # agents to the top of the leaderboard).
        # BDEs only — the board ranks the people who close deals, so admins,
        # managers and back-office staff don't pad it out with rows of zeros.
        from users.models import ROLE_BDE
        users = WorkspaceUser.objects.filter(is_active=True, role=ROLE_BDE).annotate(
            closed_sales=Count('bde_leads', filter=won_filter),
            revenue=Coalesce(Sum('bde_leads__value', filter=won_filter), Decimal('0'))
        ).order_by('-revenue', '-closed_sales', 'first_name', 'last_name')

        leaderboard = []
        for u in users:
            leaderboard.append({
                "id": u.id,
                "name": f"{u.first_name} {u.last_name}".strip() or u.username,
                "role": "BDE",
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
        
        base_qs = reporting_scope(user)

        # Base QS for converted leads
        won_qs = base_qs.filter(status__in=['converted'])

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

class ServiceEntryViewSet(viewsets.ModelViewSet):
    """Service module — a standalone list of scheduled service entries, managed by
    the project manager (and admins/general managers)."""
    serializer_class = ServiceEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = ServiceEntry.objects.all()

    def _guard(self):
        from .access import can_access_project
        if not can_access_project(self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to the service module.')

    def get_queryset(self):
        self._guard()
        return ServiceEntry.objects.all()

    def perform_create(self, serializer):
        self._guard()
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    def perform_update(self, serializer):
        self._guard()
        serializer.save()

    def perform_destroy(self, instance):
        self._guard()
        instance.delete()


class EmergencyServiceViewSet(viewsets.ModelViewSet):
    """Emergency Service module — urgent service visits with on-site electrical
    readings, managed by the liasoning officer (and admins/general managers)."""
    serializer_class = EmergencyServiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    # The AC readings arrive as text plus a meter photo each, so the entry is
    # submitted as multipart; JSON still works for an entry with no photos.
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]
    queryset = EmergencyService.objects.all()

    def _guard(self):
        from .access import can_access_liasoning
        if not can_access_liasoning(self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to the emergency service module.')

    def get_queryset(self):
        self._guard()
        return EmergencyService.objects.all()

    def perform_create(self, serializer):
        self._guard()
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    def perform_update(self, serializer):
        self._guard()
        serializer.save()

    @action(detail=True, methods=['post'], url_path='documents',
            parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def add_document(self, request, pk=None):
        """Attach one photo to a reading on this entry."""
        self._guard()
        entry = self.get_object()
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'file is required.'}, status=status.HTTP_400_BAD_REQUEST)
        doc_type = (request.data.get('doc_type') or '').strip()
        if doc_type not in {k for k, _ in EmergencyService.PHOTO_SLOTS}:
            return Response({'error': 'Unknown photo slot.'}, status=status.HTTP_400_BAD_REQUEST)
        doc = EmergencyServiceDocument.objects.create(
            entry=entry, doc_type=doc_type, file=file,
            uploaded_by=request.user if request.user.is_authenticated else None)
        return Response(EmergencyServiceDocumentSerializer(doc, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='documents/(?P<doc_id>[0-9]+)')
    def delete_document(self, request, pk=None, doc_id=None):
        """Remove one photo from this entry."""
        self._guard()
        entry = self.get_object()
        try:
            doc = EmergencyServiceDocument.objects.get(pk=doc_id, entry=entry)
        except EmergencyServiceDocument.DoesNotExist:
            return Response({'error': 'Photo not found.'}, status=status.HTTP_404_NOT_FOUND)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        self._guard()
        instance.delete()


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
