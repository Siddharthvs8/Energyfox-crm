from rest_framework import viewsets, permissions, parsers, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from core.permissions import IsAdminOnly
from organization.utils import get_org_settings
from .models import User, WorkspaceTeam, Branch, CustomRole
from .serializers import UserSerializer, CustomRoleSerializer, WorkspaceTeamSerializer, BranchSerializer


def _looks_masked(value, current):
    """True when `value` is the masked form of `current` being echoed back by the
    settings form rather than a newly typed secret.

    The API returns secrets as '••••1234'. A browser round-trips those bullets
    intact, but any re-encoding in between can mangle them — and saving a mangled
    mask would silently replace the real credential. So treat a value as a mask
    whenever everything before the last 4 characters is non-alphanumeric and the
    last 4 match what we already have.
    """
    if not value:
        return False
    if value.startswith('•'):
        return True
    if not current or len(value) != len(current) or len(value) <= 4:
        return False
    head, tail = value[:-4], value[-4:]
    return tail == current[-4:] and head != '' and not any(c.isalnum() for c in head)


class BranchViewSet(viewsets.ModelViewSet):
    """Manage branches (the admin Branches module). Admin/superadmin only."""
    serializer_class = BranchSerializer
    queryset = (Branch.objects.all()
                .select_related('manager')
                .prefetch_related('members')
                .order_by('name'))

    def get_permissions(self):
        # Anyone authenticated can list branches (needed by the user form);
        # only admins can create/edit/delete.
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAdminOnly()]

    def destroy(self, request, *args, **kwargs):
        """Refuse to delete a branch that still has staff — their branch would be
        silently cleared. Move them to another branch first (or deactivate this one)."""
        from rest_framework import status as http_status
        branch = self.get_object()
        count = branch.members.count()
        if count:
            return Response(
                {'error': f'{count} team member(s) still belong to this branch. '
                          f'Move them to another branch first, or deactivate this branch instead.'},
                status=http_status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='toggle-active')
    def toggle_active(self, request, pk=None):
        """Activate / deactivate a branch without deleting it."""
        branch = self.get_object()
        branch.is_active = not branch.is_active
        branch.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(branch).data)

    @action(detail=False, methods=['get'], url_path='performance')
    def performance(self, request):
        """Per-branch performance for the Branches module.

        Cohort report: every figure describes the leads a branch *received* in
        the selected period, so the counts and the conversion rate always refer
        to the same set of leads. `period` = this_month | last_30 | this_year | all.
        """
        from datetime import timedelta
        from decimal import Decimal
        from django.db.models import Count, Q, Sum
        from django.utils import timezone
        from leads.models import Lead

        period = request.query_params.get('period', 'this_month')
        now = timezone.now()
        if period == 'last_30':
            start, label = now - timedelta(days=30), 'Last 30 days'
        elif period == 'this_year':
            start, label = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), 'This year'
        elif period == 'all':
            start, label = None, 'All time'
        else:
            period = 'this_month'
            start, label = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), 'This month'

        rows = []
        for branch in self.get_queryset():
            qs = Lead.objects.filter(assigned_to__branch=branch, is_trashed=False)
            if start is not None:
                qs = qs.filter(created_at__gte=start)

            agg = qs.aggregate(
                leads=Count('id'),
                converted=Count('id', filter=Q(status='converted', is_lost=False)),
                lost=Count('id', filter=Q(is_lost=True)),
                # A closed deal is one that has been paid (part or full), the same
                # rule the Converted Leads board uses — not merely handed to
                # documentation, which is work in progress.
                closed_deals=Count('id', filter=Q(pushed_to_accounts=True,
                                                  payment_verification__amount_received__gt=0)),
                completed=Count('id', filter=Q(project__is_complete=True)),
                deal_value=Sum('value', filter=Q(status='converted', is_lost=False)),
                collected=Sum('payment_verification__amount_received'),
                discounts=Sum('payment_verification__discount_value'),
            )
            leads = agg['leads'] or 0
            converted = agg['converted'] or 0
            deal_value = agg['deal_value'] or Decimal('0')
            collected = agg['collected'] or Decimal('0')
            discounts = agg['discounts'] or Decimal('0')
            rows.append({
                'id': branch.id,
                'name': branch.name,
                'code': branch.code,
                'manager_name': (f"{branch.manager.first_name} {branch.manager.last_name}".strip()
                                 or branch.manager.username) if branch.manager else None,
                'is_active': branch.is_active,
                'staff': branch.members.count(),
                'leads': leads,
                'converted': converted,
                'conversion_rate': round(converted * 100.0 / leads, 1) if leads else 0.0,
                'closed_deals': agg['closed_deals'] or 0,
                'completed_projects': agg['completed'] or 0,
                'lost': agg['lost'] or 0,
                'deal_value': float(deal_value),
                'collected': float(collected),
                'balance_due': float(max(deal_value - collected - discounts, Decimal('0'))),
            })

        rows.sort(key=lambda r: (-r['collected'], -r['converted'], r['name']))
        totals = {k: sum(r[k] for r in rows) for k in
                  ['staff', 'leads', 'converted', 'closed_deals', 'completed_projects',
                   'lost', 'deal_value', 'collected', 'balance_due']}
        totals['conversion_rate'] = round(totals['converted'] * 100.0 / totals['leads'], 1) if totals['leads'] else 0.0

        return Response({'period': period, 'period_label': label, 'branches': rows, 'totals': totals})

class WorkspaceTeamViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceTeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from django.db.models import Q
        qs = WorkspaceTeam.objects.all().prefetch_related('members').order_by('name')
        user = self.request.user
        # Admin and GM see all teams; others see only their own team
        if not user.sees_everything:
            if user.branch_scoped and user.branch_id:
                # Branch manager: teams they head, their own, and any team with
                # staff from their branch.
                qs = qs.filter(Q(manager=user) | Q(id=user.team_id)
                               | Q(members__branch_id=user.branch_id)).distinct()
            elif user.team_id:
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
        from django.db.models import Sum, Count, Q
        
        team = self.get_object()
        members = team.members.filter(is_active=True)
        from leads.scopes import closed_deals, own_leads_q, received_value
        # A member's BDE work is theirs too: handing a lead over moves nothing —
        # `assigned_to` stays with the tele caller — so scoping on the owner
        # alone reports a BDE as having closed nothing at all.
        team_leads = Lead.objects.filter(
            Q(assigned_to__in=members) | Q(bde__in=members) | Q(tele_caller__in=members)
        ).distinct()
        # Won means closed: in accounts with money received. See
        # leads.scopes.CLOSED_DEAL_FILTER — one definition for every figure.
        won_leads = closed_deals(team_leads)
        
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
            member_leads = Lead.objects.filter(own_leads_q(member)).distinct()
            m_won = closed_deals(member_leads)
            leaderboard.append({
                "id": member.id,
                "name": f"{member.first_name} {member.last_name}".strip() or member.username,
                "won_value": float(m_won.aggregate(total=Sum(received_value()))['total'] or 0),
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
                "won_value": float(won_leads.aggregate(total=Sum(received_value()))['total'] or 0),
                "won_count": enrolled_count,
                "total_leads": total_count,
                "pipeline_value": float(team_leads.aggregate(total=Sum('value'))['total'] or 0),
                "win_rate": round(win_rate, 1)
            },
            "status_distribution": status_distribution,
            "recent_leads": recent_data,
            "leaderboard": leaderboard
        })

class CustomRoleViewSet(viewsets.ModelViewSet):
    """Custom user types, managed from Settings. Only admins / super admins may
    change them: a role is a grant of access, so editing one is a privilege
    change for everybody on it."""
    serializer_class = CustomRoleSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = CustomRole.objects.all()

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), permissions.IsAdminUser()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.members.exists():
            return Response(
                {'error': f'{role.name} is assigned to {role.members.count()} '
                          f'user(s). Move them to another role first.'},
                status=400,
            )
        return super().destroy(request, *args, **kwargs)


class UserViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing user instances.
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from .models import B2B_ONLY_ROLES
        qs = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
        user = self.request.user

        # The wholesale side keeps its own roster. B2B staff see that roster and
        # nothing else; they have no team or branch scoping to fall through to.
        if user.is_b2b_only:
            return qs.filter(role__in=B2B_ONLY_ROLES)

        # Which roster the *directory* shows: ?segment=b2b is the B2B Team module
        # asking for the wholesale side, otherwise B2B people stay out of the
        # CRM's lists and pickers. Detail routes are deliberately exempt — an
        # admin editing a B2B account posts to /api/users/<id>/ with no segment,
        # and filtering there would 404 them out of their own Team page.
        if self.action == 'list':
            if self.request.query_params.get('segment') == 'b2b':
                qs = qs.filter(role__in=B2B_ONLY_ROLES)
            else:
                qs = qs.exclude(role__in=B2B_ONLY_ROLES)

        # Admin and GM see all users; branch managers see their branch; others see their team/self
        if not user.sees_everything:
            if user.branch_scoped and user.branch_id:
                qs = qs.filter(branch_id=user.branch_id)
            elif user.team_id:
                qs = qs.filter(team_id=user.team_id)
            else:
                qs = qs.filter(id=user.id)  # at least see themselves
        return qs

    @action(detail=False, methods=['get'])
    def assignable(self, request):
        """People the caller may assign a lead to.

        Kept separate from `list` (which is scoped to the caller's own team for
        directory purposes) so the assignee picker always offers exactly the set
        the backend will accept — agents get the front-line agents, managers and
        admins get everyone.
        """
        from .models import B2B_ONLY_ROLES
        allowed = request.user.assignable_lead_user_ids()
        # B2B staff never own leads, so they never belong in an assignee picker.
        qs = User.objects.filter(is_active=True).exclude(role__in=B2B_ONLY_ROLES)
        if allowed is not None:
            qs = qs.filter(id__in=allowed)
        return Response([{
            'id': u.id,
            'name': f"{u.first_name} {u.last_name}".strip() or u.username,
            'role': u.role,
            'role_label': u.get_role_display(),
        } for u in qs.order_by('first_name', 'last_name')])

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
        actor = request.user

        if self.action in ['update', 'partial_update']:
            # Your own profile, or an account below you in the hierarchy. An
            # admin editing a peer or a super admin is refused — otherwise they
            # could reset that account's password and take it over.
            own = obj.id == actor.id
            if not own and not actor.can_manage(obj):
                self.permission_denied(
                    request,
                    message=("You can only edit your own profile and accounts below you. "
                             f"Editing {obj.get_role_display()} accounts is a "
                             "Super Admin's responsibility."))
            # Staff-tier accounts are managed from Team; everyone else may only
            # ever reach their own profile.
            if not own and not (actor.is_staff or actor.is_general_manager):
                self.permission_denied(request, message="You do not have permission to edit this profile.")

        if self.action == 'destroy':
            if not actor.is_staff:
                self.permission_denied(request, message="Only admins can remove team members.")
            if obj.id == actor.id:
                self.permission_denied(request, message="You cannot remove your own account.")
            if not actor.can_manage(obj):
                self.permission_denied(
                    request,
                    message=f"Only a Super Admin can remove {obj.get_role_display()} accounts.")

    def _guard_role(self, serializer):
        """Enforce who may grant which role — you can only appoint roles below
        your own, so making someone an admin is a Super Admin's job."""
        from rest_framework.exceptions import PermissionDenied
        requester = self.request.user
        new_role = serializer.validated_data.get('role')
        if new_role is None:
            return
        # Unchanged role on an edit is not a grant.
        if serializer.instance is not None and serializer.instance.role == new_role:
            return
        if not requester.is_staff:
            serializer.validated_data.pop('role', None)
            return
        if not requester.can_assign_role(new_role):
            from .models import ROLE_CHOICES
            label = dict(ROLE_CHOICES).get(new_role, new_role)
            raise PermissionDenied(f"Only a Super Admin can assign the {label} role.")

    def _guard_username(self, serializer):
        """Only an Admin or Super Admin may change a username — nobody else, not
        even on their own profile. The login name is issued by the company."""
        from rest_framework.exceptions import PermissionDenied
        instance = serializer.instance
        if instance is None:
            return                      # creation is already admin-only
        new_username = serializer.validated_data.get('username')
        if new_username is None or new_username == instance.username:
            return                      # unchanged (the form always posts it)
        if not self.request.user.is_staff:
            raise PermissionDenied("Only an Admin or Super Admin can change a username.")

    def perform_create(self, serializer):
        self._guard_role(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._guard_role(serializer)
        self._guard_username(serializer)
        serializer.save()

    @action(detail=False, methods=['get'], url_path='assignable-roles')
    def assignable_roles(self, request):
        """Roles the caller may grant — drives the Team form's role picker so it
        never offers something the API will reject."""
        from .models import ROLE_CHOICES, B2B_ONLY_ROLES
        allowed = set(request.user.assignable_roles())
        # On the wholesale side only wholesale roles are on offer, and vice versa.
        if request.query_params.get('segment') == 'b2b' or request.user.is_b2b_only:
            allowed &= set(B2B_ONLY_ROLES)
        else:
            allowed -= set(B2B_ONLY_ROLES)
        return Response([{'value': r, 'label': label}
                         for r, label in ROLE_CHOICES if r in allowed])

    @action(detail=True, methods=['post', 'delete'], url_path='avatar',
            parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def avatar(self, request, pk=None):
        """Set (POST) or clear (DELETE) a profile picture.

        Everyone may change their own; touching someone else's follows the same
        hierarchy as editing their profile. Note this action needs its own check —
        check_object_permissions only guards update/destroy, so without it any
        authenticated user could overwrite anyone's picture.
        """
        from rest_framework.exceptions import PermissionDenied
        user = self.get_object()
        actor = request.user
        if user.id != actor.id and not actor.can_manage(user):
            raise PermissionDenied('You can only change your own profile picture.')

        # Keep hold of the current file so the replaced one doesn't linger in
        # media storage forever.
        storage, previous = user.avatar.storage, (user.avatar.name or None)

        if request.method == 'DELETE':
            if previous:
                user.avatar = None
                user.save(update_fields=['avatar'])
                storage.delete(previous)
            return Response(self.get_serializer(user).data)

        upload = request.FILES.get('avatar') or request.FILES.get('file')
        if not upload:
            return Response({'error': 'No image supplied.'}, status=400)

        serializer = self.get_serializer(user, data={'avatar': upload}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user.refresh_from_db()
        if previous and previous != user.avatar.name:
            storage.delete(previous)
        return Response(self.get_serializer(user).data)

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='permission-catalog')
    def permission_catalog(self, request):
        """Every permission a custom user type can be granted — drives the
        checkbox grid in Settings → Roles & Permissions."""
        from .permission_catalog import catalog
        return Response(catalog())

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

    @action(detail=False, methods=['get'], url_path='purchase-staff')
    def purchase_staff(self, request):
        """List active purchase staff (for the purchase-assign picker)."""
        return Response(self._role_picker('purchase_staff'))

    @action(detail=False, methods=['get'], url_path='project-managers')
    def project_managers(self, request):
        """List active project managers (for the project-assign picker)."""
        return Response(self._role_picker('project_manager'))

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
        
        from leads.scopes import own_leads_q
        user = self.get_object()
        # The leads this person works, not only the ones they own. Handing a lead
        # to a BDE moves nothing — `assigned_to` stays with the tele caller — so
        # scoping on the owner alone reports a BDE as having closed nothing at
        # all. Same relation the leaderboard credits the sale to.
        user_leads = Lead.objects.filter(own_leads_q(user)).distinct()
        
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from and date_to:
            user_leads = user_leads.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)

        from leads.scopes import closed_deals, received_value
        won_leads = closed_deals(user_leads)

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
                "won_value": float(won_leads.aggregate(total=Sum(received_value()))['total'] or 0),
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

        masked_email_password = ''
        if org.email_host_password:
            masked_email_password = '•' * max(0, len(org.email_host_password) - 4) + org.email_host_password[-4:]

        # The wholesale side's own credentials, masked the same way.
        masked_b2b_email_password = ''
        if org.b2b_email_host_password:
            masked_b2b_email_password = ('•' * max(0, len(org.b2b_email_host_password) - 4)
                                         + org.b2b_email_host_password[-4:])
        masked_b2b_whatsapp_token = ''
        if org.b2b_whatsapp_access_token:
            masked_b2b_whatsapp_token = ('•' * max(0, len(org.b2b_whatsapp_access_token) - 4)
                                         + org.b2b_whatsapp_access_token[-4:])

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
            "email_host": org.email_host,
            "email_port": org.email_port,
            "email_use_tls": org.email_use_tls,
            "email_use_ssl": org.email_use_ssl,
            "email_host_user": org.email_host_user,
            "email_host_password": masked_email_password,
            "email_from_name": org.email_from_name,
            "email_from_address": org.email_from_address,
            "email_signature": org.email_signature,
            "email_signature_html": org.email_signature_html,
            # B2B (wholesale) email + WhatsApp. Blank means "use the shared one".
            "b2b_email_host": org.b2b_email_host,
            "b2b_email_port": org.b2b_email_port,
            "b2b_email_use_tls": org.b2b_email_use_tls,
            "b2b_email_use_ssl": org.b2b_email_use_ssl,
            "b2b_email_host_user": org.b2b_email_host_user,
            "b2b_email_host_password": masked_b2b_email_password,
            "b2b_email_from_name": org.b2b_email_from_name,
            "b2b_email_from_address": org.b2b_email_from_address,
            "b2b_email_signature": org.b2b_email_signature,
            "b2b_email_signature_html": org.b2b_email_signature_html,
            "b2b_whatsapp_phone_number_id": org.b2b_whatsapp_phone_number_id,
            "b2b_whatsapp_business_account_id": org.b2b_whatsapp_business_account_id,
            "b2b_whatsapp_access_token": masked_b2b_whatsapp_token,
            "custom_lead_statuses": org.custom_lead_statuses or [],
            "theme": org.theme,
            "warranty_company_name": org.warranty_company_name,
            "warranty_cin": org.warranty_cin,
            "warranty_gst": org.warranty_gst,
            "warranty_director_name": org.warranty_director_name,
            "warranty_director_designation": org.warranty_director_designation,
            "warranty_panel_years": org.warranty_panel_years,
            "warranty_inverter_years": org.warranty_inverter_years,
            "warranty_service_years": org.warranty_service_years,
            "warranty_signature": org.warranty_signature.url if org.warranty_signature else None,
            "warranty_seal": org.warranty_seal.url if org.warranty_seal else None,
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

        # Email (SMTP) integration — configured here instead of server env vars.
        for f in ['email_host', 'email_host_user', 'email_from_name', 'email_from_address',
                  'email_signature', 'email_signature_html']:
            v = request.data.get(f)
            if v is not None:
                setattr(tenant, f, v)
        if request.data.get('email_port') not in (None, ''):
            try:
                tenant.email_port = int(request.data.get('email_port'))
            except (TypeError, ValueError):
                pass
        for f in ['email_use_tls', 'email_use_ssl']:
            v = request.data.get(f)
            if v is not None:
                setattr(tenant, f, str(v).lower() in ('true', '1', 'yes', 'on'))
        # Masked value means "unchanged" — same convention as the other secrets,
        # but tolerant of the mask characters being re-encoded in transit: any
        # value whose head is all non-alphanumeric and whose last 4 match the
        # stored secret is a mask being echoed back, not a new password.
        pw = request.data.get('email_host_password')
        if pw is not None and not _looks_masked(str(pw), tenant.email_host_password):
            tenant.email_host_password = pw

        # B2B (wholesale) email + WhatsApp — same shape, same masking rule.
        for f in ['b2b_email_host', 'b2b_email_host_user', 'b2b_email_from_name',
                  'b2b_email_from_address', 'b2b_email_signature', 'b2b_email_signature_html',
                  'b2b_whatsapp_phone_number_id', 'b2b_whatsapp_business_account_id']:
            v = request.data.get(f)
            if v is not None:
                setattr(tenant, f, v)
        if request.data.get('b2b_email_port') not in (None, ''):
            try:
                tenant.b2b_email_port = int(request.data.get('b2b_email_port'))
            except (TypeError, ValueError):
                pass
        for f in ['b2b_email_use_tls', 'b2b_email_use_ssl']:
            v = request.data.get(f)
            if v is not None:
                setattr(tenant, f, str(v).lower() in ('true', '1', 'yes', 'on'))
        for field, current in (('b2b_email_host_password', tenant.b2b_email_host_password),
                               ('b2b_whatsapp_access_token', tenant.b2b_whatsapp_access_token)):
            v = request.data.get(field)
            if v is not None and not _looks_masked(str(v), current):
                setattr(tenant, field, v)

        # Warranty certificate settings (fixed details printed on the generated document).
        for f in ['warranty_company_name', 'warranty_cin', 'warranty_gst',
                  'warranty_director_name', 'warranty_director_designation',
                  'warranty_panel_years', 'warranty_inverter_years', 'warranty_service_years']:
            v = request.data.get(f)
            if v is not None:
                setattr(tenant, f, v)
        if request.FILES.get('warranty_signature'):
            tenant.warranty_signature = request.FILES['warranty_signature']
        if request.FILES.get('warranty_seal'):
            tenant.warranty_seal = request.FILES['warranty_seal']

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

        masked_email_pw_out = ''
        if tenant.email_host_password:
            masked_email_pw_out = '•' * max(0, len(tenant.email_host_password) - 4) + tenant.email_host_password[-4:]

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
            "email_host": tenant.email_host,
            "email_port": tenant.email_port,
            "email_use_tls": tenant.email_use_tls,
            "email_use_ssl": tenant.email_use_ssl,
            "email_host_user": tenant.email_host_user,
            "email_host_password": masked_email_pw_out,
            "email_from_name": tenant.email_from_name,
            "email_from_address": tenant.email_from_address,
            "email_signature": tenant.email_signature,
            "email_signature_html": tenant.email_signature_html,
            "custom_lead_statuses": tenant.custom_lead_statuses or [],
            "warranty_company_name": tenant.warranty_company_name,
            "warranty_cin": tenant.warranty_cin,
            "warranty_gst": tenant.warranty_gst,
            "warranty_director_name": tenant.warranty_director_name,
            "warranty_director_designation": tenant.warranty_director_designation,
            "warranty_panel_years": tenant.warranty_panel_years,
            "warranty_inverter_years": tenant.warranty_inverter_years,
            "warranty_service_years": tenant.warranty_service_years,
            "warranty_signature": tenant.warranty_signature.url if tenant.warranty_signature else None,
            "warranty_seal": tenant.warranty_seal.url if tenant.warranty_seal else None,
        })



class InventoryDocumentProfileView(APIView):
    """Settings → Inventory Documents.

    The letterhead, artwork and bank block printed on the inventory documents,
    kept separately for retail and wholesale so the two sides can trade under
    their own identity. GET returns both; PATCH updates one, named by `side`.

    Every field is optional — what is left blank falls back to the
    organisation's own settings, which is what these documents printed before
    this screen existed.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    TEXT_FIELDS = [
        'company_name', 'address', 'phone', 'email', 'gst', 'cin', 'pan',
        'bank_name', 'bank_account_name', 'bank_account_number', 'bank_ifsc', 'bank_branch',
    ]
    IMAGE_FIELDS = ['logo', 'signature', 'seal']

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method in ('PATCH', 'PUT') and not request.user.is_staff:
            self.permission_denied(request, message='Only admins can update document settings.')

    def _payload(self, request, profile):
        from organization.utils import get_org_settings

        def url(f):
            return request.build_absolute_uri(f.url) if f else None

        data = {'side': profile.side}
        for f in self.TEXT_FIELDS:
            data[f] = getattr(profile, f)
        for f in self.IMAGE_FIELDS:
            data[f] = url(getattr(profile, f))
        # What the document prints today, so the screen can show the fallback in
        # place rather than an empty box that looks like nothing is configured.
        printed = profile.resolved(get_org_settings())
        data['effective'] = {
            'name': printed['name'], 'address': printed['address'], 'phone': printed['phone'],
            'email': printed['email'], 'gst': printed['gst'], 'cin': printed['cin'],
            'pan': printed['pan'],
            'logo': url(printed['logo']), 'signature': url(printed['signature']),
            'seal': url(printed['seal']),
            **{f'bank_{k}': v for k, v in printed['bank'].items()},
        }
        return data

    def get(self, request):
        from organization.models import InventoryDocumentProfile
        return Response({
            side: self._payload(request, InventoryDocumentProfile.load(side))
            for side, _ in InventoryDocumentProfile.SIDE_CHOICES
        })

    def patch(self, request):
        from organization.models import InventoryDocumentProfile
        sides = {s for s, _ in InventoryDocumentProfile.SIDE_CHOICES}
        side = (request.data.get('side') or request.query_params.get('side') or '').strip()
        if side not in sides:
            return Response({'error': f"Pass side as one of {', '.join(sorted(sides))}."},
                            status=status.HTTP_400_BAD_REQUEST)

        profile = InventoryDocumentProfile.load(side)
        for f in self.TEXT_FIELDS:
            v = request.data.get(f)
            if v is not None:
                setattr(profile, f, v)
        for f in self.IMAGE_FIELDS:
            if request.FILES.get(f):
                setattr(profile, f, request.FILES[f])
            # An explicit empty string clears the artwork back to the fallback.
            elif request.data.get(f) == '':
                setattr(profile, f, None)
        profile.save()
        return Response(self._payload(request, profile))
