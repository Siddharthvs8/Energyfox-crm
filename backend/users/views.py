from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from core.permissions import IsAdminOnly
from organization.utils import get_org_settings
from .models import User, WorkspaceTeam, Branch
from .serializers import UserSerializer, WorkspaceTeamSerializer, BranchSerializer


class BranchViewSet(viewsets.ModelViewSet):
    """Manage branches. Admin/superadmin only."""
    serializer_class = BranchSerializer
    queryset = Branch.objects.all().order_by('name')

    def get_permissions(self):
        # Anyone authenticated can list branches (needed by the user form);
        # only admins can create/edit/delete.
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminOnly()]

class WorkspaceTeamViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceTeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = WorkspaceTeam.objects.all().prefetch_related('members').order_by('name')
        user = self.request.user
        # Admin and GM see all teams; others see only their own team
        if not (user.is_staff or user.is_general_manager):
            if user.team_id:
                qs = qs.filter(id=user.team_id)
            else:
                qs = qs.none()
        return qs

    def get_permissions(self):
        # Admins and General Managers can manage teams
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    def check_permissions(self, request):
        super().check_permissions(request)
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            if not (request.user.is_staff or request.user.is_general_manager):
                self.permission_denied(request, message='Only admins and general managers can manage teams.')

    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Returns detailed performance metrics for a specific team."""
        from leads.models import Lead
        from django.db.models import Sum, Count
        
        team = self.get_object()
        members = team.members.filter(is_active=True)
        team_leads = Lead.objects.filter(assigned_to__in=members)
        won_leads = team_leads.filter(status='enrolled')
        
        total_count = team_leads.count()
        enrolled_count = won_leads.count()
        win_rate = (enrolled_count / total_count * 100) if total_count > 0 else 0
        
        # Status Distribution
        status_data = team_leads.values('status').annotate(count=Count('id'))
        status_distribution = {item['status']: item['count'] for item in status_data}
        
        # Recent Leads
        recent_leads = team_leads.order_by('-created_at')[:5]
        recent_data = []
        for l in recent_leads:
            recent_data.append({
                "id": l.id,
                "name": f"{l.first_name} {l.last_name}",
                "status": l.status,
                "value": float(l.value),
                "date": l.created_at.strftime("%Y-%m-%d"),
                "agent": f"{l.assigned_to.first_name} {l.assigned_to.last_name}".strip() if l.assigned_to else "Unassigned"
            })

        # Leaderboard
        leaderboard = []
        for member in members:
            member_leads = Lead.objects.filter(assigned_to=member)
            m_won = member_leads.filter(status='enrolled')
            leaderboard.append({
                "id": member.id,
                "name": f"{member.first_name} {member.last_name}".strip() or member.username,
                "won_value": float(m_won.aggregate(total=Sum('value'))['total'] or 0),
                "won_count": m_won.count(),
                "total_leads": member_leads.count(),
                "pipeline_value": float(member_leads.aggregate(total=Sum('value'))['total'] or 0)
            })
        leaderboard.sort(key=lambda x: x['won_value'], reverse=True)

        return Response({
            "team_info": {
                "id": team.id,
                "name": team.name,
            },
            "summary": {
                "won_value": float(won_leads.aggregate(total=Sum('value'))['total'] or 0),
                "won_count": enrolled_count,
                "total_leads": total_count,
                "pipeline_value": float(team_leads.aggregate(total=Sum('value'))['total'] or 0),
                "win_rate": round(win_rate, 1)
            },
            "status_distribution": status_distribution,
            "recent_leads": recent_data,
            "leaderboard": leaderboard
        })

class UserViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing user instances.
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
        user = self.request.user
        # Admin and GM see all users; branch managers see their branch; others see their team/self
        if not (user.is_staff or user.is_general_manager):
            if user.branch_scoped and user.branch_id:
                qs = qs.filter(branch_id=user.branch_id)
            elif user.team_id:
                qs = qs.filter(team_id=user.team_id)
            else:
                qs = qs.filter(id=user.id)  # at least see themselves
        return qs

    def get_permissions(self):
        """
        Custom permissions:
        - create, destroy: Only Admins (is_staff) — NOT General Managers
        - list, retrieve, me: All Authenticated
        - update, partial_update: Admins, General Managers, OR the user themselves
        """
        if self.action in ['create', 'destroy']:
            return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if self.action in ['update', 'partial_update']:
            # Allow if it's the user's own profile OR they are an admin/general_manager
            if not (request.user.is_staff or request.user.is_general_manager or obj.id == request.user.id):
                self.permission_denied(request, message="You do not have permission to edit this profile.")
        
        if self.action == 'destroy':
             if not request.user.is_staff:
                self.permission_denied(request, message="Only admins can remove team members.")

    ADMIN_ROLES = {'admin', 'superadmin'}

    def _guard_role(self, serializer):
        """Enforce who may assign which role (no self-escalation / privilege grant)."""
        requester = self.request.user
        new_role = serializer.validated_data.get('role')
        if new_role is None:
            return
        # Only admin-tier may set roles at all; only a superadmin may grant admin/superadmin.
        if not requester.is_staff or (new_role in self.ADMIN_ROLES and requester.role != 'superadmin'):
            serializer.validated_data.pop('role', None)

    def perform_create(self, serializer):
        self._guard_role(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._guard_role(serializer)
        serializer.save()

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def bdes(self, request):
        """List active BDEs (for the 'Assign to BDE' picker). Any authenticated user."""
        return Response(self._role_picker('bde'))

    @action(detail=False, methods=['get'], url_path='documentation-staff')
    def documentation_staff(self, request):
        """List active documentation staff (for the documentation-assign picker)."""
        return Response(self._role_picker('documentation_staff'))

    @action(detail=False, methods=['get'], url_path='accounts-staff')
    def accounts_staff(self, request):
        """List active accounts staff (for the accounts-assign picker)."""
        return Response(self._role_picker('accounts_staff'))

    def _role_picker(self, role):
        qs = User.objects.filter(is_active=True, role=role).order_by('first_name', 'last_name')
        return [
            {'id': u.id,
             'name': f"{u.first_name} {u.last_name}".strip() or u.username,
             'branch_name': u.branch.name if u.branch else None}
            for u in qs
        ]

    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Returns detailed performance metrics for a specific user."""
        from leads.models import Lead
        from django.db.models import Sum, Count
        
        user = self.get_object()
        user_leads = Lead.objects.filter(assigned_to=user)
        
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from and date_to:
            user_leads = user_leads.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)

        won_leads = user_leads.filter(status='enrolled')
        
        total_count = user_leads.count()
        enrolled_count = won_leads.count()
        win_rate = (enrolled_count / total_count * 100) if total_count > 0 else 0
        
        # Status Distribution
        status_data = user_leads.values('status').annotate(count=Count('id'))
        status_distribution = {item['status']: item['count'] for item in status_data}
        
        # Recent Leads
        recent_leads = user_leads.order_by('-created_at')[:5]
        recent_data = []
        for l in recent_leads:
            recent_data.append({
                "id": l.id,
                "name": f"{l.first_name} {l.last_name}",
                "status": l.status,
                "value": float(l.value),
                "date": l.created_at.strftime("%Y-%m-%d")
            })

        return Response({
            "user_info": {
                "id": user.id,
                "name": f"{user.first_name} {user.last_name}".strip() or user.username,
                "role": "Admin" if user.is_staff else ("General Manager" if user.is_general_manager else ("Manager" if user.is_manager else "Agent"))
            },
            "summary": {
                "won_value": float(won_leads.aggregate(total=Sum('value'))['total'] or 0),
                "won_count": enrolled_count,
                "total_leads": total_count,
                "pipeline_value": float(user_leads.aggregate(total=Sum('value'))['total'] or 0),
                "win_rate": round(win_rate, 1)
            },
            "status_distribution": status_distribution,
            "recent_leads": recent_data
        })

class SubscriptionStatusView(APIView):
    """Lightweight org summary used by the app shell (name/logo/telephony)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = get_org_settings()
        return Response({
            "name": org.name,
            "logo": org.logo.url if org.logo else None,
            "user_count": User.objects.count(),
            "custom_lead_statuses": org.custom_lead_statuses or [],
            "telephony_provider": org.telephony_provider,
            "theme": org.theme,
        })

class TenantSettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method in ['PATCH', 'PUT'] and not request.user.is_staff:
            self.permission_denied(request, message='Only admins can update organization settings.')

    def get(self, request):
        org = get_org_settings()

        masked_voxbay_upin = ''
        if org.voxbay_upin:
            masked_voxbay_upin = '•' * max(0, len(org.voxbay_upin) - 4) + org.voxbay_upin[-4:]

        masked_voxbay_access_token = ''
        if org.voxbay_access_token:
            masked_voxbay_access_token = '•' * max(0, len(org.voxbay_access_token) - 4) + org.voxbay_access_token[-4:]

        masked_exotel_api_token = ''
        if org.exotel_api_token:
            masked_exotel_api_token = '•' * max(0, len(org.exotel_api_token) - 4) + org.exotel_api_token[-4:]

        masked_whatsapp_token = ''
        if org.whatsapp_access_token:
            masked_whatsapp_token = '•' * max(0, len(org.whatsapp_access_token) - 4) + org.whatsapp_access_token[-4:]

        return Response({
            "name": org.name,
            "logo": org.logo.url if org.logo else None,
            "voxbay_uid": org.voxbay_uid,
            "voxbay_upin": masked_voxbay_upin,
            "voxbay_callerid": org.voxbay_callerid,
            "voxbay_api_url": org.voxbay_api_url,
            "voxbay_access_token": masked_voxbay_access_token,
            "telephony_provider": org.telephony_provider,
            "exotel_sid": org.exotel_sid,
            "exotel_api_key": org.exotel_api_key,
            "exotel_api_token": masked_exotel_api_token,
            "exotel_callerid": org.exotel_callerid,
            "exotel_subdomain": org.exotel_subdomain,
            "whatsapp_phone_number_id": org.whatsapp_phone_number_id,
            "whatsapp_business_account_id": org.whatsapp_business_account_id,
            "whatsapp_verify_token": org.whatsapp_verify_token,
            "whatsapp_access_token": masked_whatsapp_token,
            "custom_lead_statuses": org.custom_lead_statuses or [],
            "theme": org.theme,
        })

    def patch(self, request):
        tenant = get_org_settings()
        name = request.data.get('name')
        logo = request.FILES.get('logo')

        voxbay_uid = request.data.get('voxbay_uid')
        voxbay_upin = request.data.get('voxbay_upin')
        voxbay_callerid = request.data.get('voxbay_callerid')
        voxbay_api_url = request.data.get('voxbay_api_url')
        voxbay_access_token = request.data.get('voxbay_access_token')

        telephony_provider = request.data.get('telephony_provider')
        exotel_sid = request.data.get('exotel_sid')
        exotel_api_key = request.data.get('exotel_api_key')
        exotel_api_token = request.data.get('exotel_api_token')
        exotel_callerid = request.data.get('exotel_callerid')
        exotel_subdomain = request.data.get('exotel_subdomain')

        whatsapp_phone_number_id = request.data.get('whatsapp_phone_number_id')
        whatsapp_access_token = request.data.get('whatsapp_access_token')
        whatsapp_business_account_id = request.data.get('whatsapp_business_account_id')
        whatsapp_verify_token = request.data.get('whatsapp_verify_token')

        custom_lead_statuses_raw = request.data.get('custom_lead_statuses')

        if name:
            tenant.name = name
        if logo:
            tenant.logo = logo

        # Theme (accent colour) — super admin only.
        theme = request.data.get('theme')
        if theme and theme in dict(tenant.THEME_CHOICES) and request.user.is_superuser:
            tenant.theme = theme

        if voxbay_uid is not None:
            tenant.voxbay_uid = voxbay_uid
        if voxbay_upin is not None:
            if not voxbay_upin.startswith('•'):
                tenant.voxbay_upin = voxbay_upin
        if voxbay_callerid is not None:
            tenant.voxbay_callerid = voxbay_callerid
        if voxbay_api_url is not None:
            tenant.voxbay_api_url = voxbay_api_url
        if voxbay_access_token is not None:
            if not voxbay_access_token.startswith('•'):
                tenant.voxbay_access_token = voxbay_access_token

        if telephony_provider is not None:
            tenant.telephony_provider = telephony_provider
        if exotel_sid is not None:
            tenant.exotel_sid = exotel_sid
        if exotel_api_key is not None:
            tenant.exotel_api_key = exotel_api_key
        if exotel_api_token is not None:
            if not exotel_api_token.startswith('•'):
                tenant.exotel_api_token = exotel_api_token
        if exotel_callerid is not None:
            tenant.exotel_callerid = exotel_callerid
        if exotel_subdomain is not None:
            tenant.exotel_subdomain = exotel_subdomain

        if whatsapp_phone_number_id is not None:
            tenant.whatsapp_phone_number_id = whatsapp_phone_number_id
        if whatsapp_business_account_id is not None:
            tenant.whatsapp_business_account_id = whatsapp_business_account_id
        if whatsapp_verify_token is not None:
            tenant.whatsapp_verify_token = whatsapp_verify_token
        if whatsapp_access_token is not None and not whatsapp_access_token.startswith('•'):
            tenant.whatsapp_access_token = whatsapp_access_token

        if custom_lead_statuses_raw is not None:
            import json
            try:
                if isinstance(custom_lead_statuses_raw, str):
                    custom_lead_statuses = json.loads(custom_lead_statuses_raw)
                else:
                    custom_lead_statuses = custom_lead_statuses_raw
            except Exception:
                custom_lead_statuses = []
            
            cleaned_statuses = []
            if isinstance(custom_lead_statuses, list):
                for cs in custom_lead_statuses:
                    if isinstance(cs, dict) and 'value' in cs and 'label' in cs:
                        val = cs['value'].strip().lower().replace(' ', '_')
                        label = cs['label'].strip()
                        if val and label:
                            cleaned_statuses.append({
                                "value": val,
                                "label": label,
                                "bg": cs.get("bg", "bg-purple-50"),
                                "text": cs.get("text", "text-purple-700"),
                                "dot": cs.get("dot", "bg-purple-500"),
                                "color": cs.get("color", "#a855f7")
                            })
            tenant.custom_lead_statuses = cleaned_statuses

        tenant.save()

        masked_voxbay_upin = ''
        if tenant.voxbay_upin:
            masked_voxbay_upin = '•' * max(0, len(tenant.voxbay_upin) - 4) + tenant.voxbay_upin[-4:]

        masked_voxbay_access_token = ''
        if tenant.voxbay_access_token:
            masked_voxbay_access_token = '•' * max(0, len(tenant.voxbay_access_token) - 4) + tenant.voxbay_access_token[-4:]

        masked_exotel_api_token = ''
        if tenant.exotel_api_token:
            masked_exotel_api_token = '•' * max(0, len(tenant.exotel_api_token) - 4) + tenant.exotel_api_token[-4:]

        masked_whatsapp_token = ''
        if getattr(tenant, 'whatsapp_access_token', ''):
            masked_whatsapp_token = '•' * max(0, len(tenant.whatsapp_access_token) - 4) + tenant.whatsapp_access_token[-4:]

        return Response({
            "name": tenant.name,
            "logo": tenant.logo.url if tenant.logo else None,
            "voxbay_uid": tenant.voxbay_uid,
            "voxbay_upin": masked_voxbay_upin,
            "voxbay_callerid": tenant.voxbay_callerid,
            "voxbay_api_url": tenant.voxbay_api_url,
            "voxbay_access_token": masked_voxbay_access_token,
            "telephony_provider": tenant.telephony_provider,
            "exotel_sid": tenant.exotel_sid,
            "exotel_api_key": tenant.exotel_api_key,
            "exotel_api_token": masked_exotel_api_token,
            "exotel_callerid": tenant.exotel_callerid,
            "exotel_subdomain": tenant.exotel_subdomain,
            "whatsapp_phone_number_id": tenant.whatsapp_phone_number_id,
            "whatsapp_business_account_id": tenant.whatsapp_business_account_id,
            "whatsapp_verify_token": tenant.whatsapp_verify_token,
            "whatsapp_access_token": masked_whatsapp_token,
            "custom_lead_statuses": tenant.custom_lead_statuses or [],
        })

