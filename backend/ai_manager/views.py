from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes as perm_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Sum, Count, Q

from .models import ManagerConfig, MonthlyTarget, DailyTarget, Holiday, Meeting, Notification, AIMeetingSession, AIMeetingMessage, DailyTargetProof
from .serializers import (
    ManagerConfigSerializer, MonthlyTargetSerializer, DailyTargetSerializer,
    HolidaySerializer, MeetingSerializer, NotificationSerializer, DailyTargetProofSerializer
)
from . import engine
from . import ai_meeting as ai_meeting_engine


from rest_framework.exceptions import PermissionDenied
from core.permissions import watches_everything
# Won means closed — one definition, shared with every other figure in the CRM.
from leads.scopes import closed_deals, received_value


# ─── Custom Permission ────────────────────────────────────────────────────────

class IsAdminOrGeneralManager(permissions.BasePermission):
    """Only allow admin (is_staff) or general managers — plus the spectator,
    which reads this module like any other and is refused every write by
    core.middleware.SpectatorReadOnlyMiddleware."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.is_staff or request.user.is_general_manager
             or watches_everything(request.user))
        )

class IsAdminOrManager(permissions.BasePermission):
    """Allow admin, general managers, and regular managers (plus the spectator)."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.is_staff or request.user.is_general_manager or request.user.is_manager
             or watches_everything(request.user))
        )



# ─── Config (Singleton) ───────────────────────────────────────────────────────

class ConfigView(APIView):
    permission_classes = [IsAdminOrGeneralManager]

    def get(self, request):
        config = engine.get_or_create_config()
        serializer = ManagerConfigSerializer(config)
        return Response(serializer.data)

    def put(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Only admins can update config'},
                            status=status.HTTP_403_FORBIDDEN)
        config = engine.get_or_create_config()
        serializer = ManagerConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ─── Monthly Targets ──────────────────────────────────────────────────────────

class MonthlyTargetViewSet(viewsets.ModelViewSet):
    serializer_class = MonthlyTargetSerializer
    permission_classes = [IsAdminOrManager]

    def get_queryset(self):
        qs = MonthlyTarget.objects.all()
        month = self.request.query_params.get('month')
        year = self.request.query_params.get('year')
        agent = self.request.query_params.get('agent')
        if month:
            qs = qs.filter(month=month)
        if year:
            qs = qs.filter(year=year)
        if agent:
            qs = qs.filter(agent_id=agent)
        return qs

    def perform_create(self, serializer):
        agent = serializer.validated_data.get('agent')
        if not (self.request.user.is_staff or self.request.user.is_general_manager):
            if not agent.team or agent.team.manager != self.request.user:
                raise PermissionDenied("You can only set targets for your own team members.")
        mt = serializer.save(created_by=self.request.user)
        # Auto-generate daily targets
        engine.generate_daily_targets(mt)

    def perform_update(self, serializer):
        mt = self.get_object()
        agent = mt.agent
        if not (self.request.user.is_staff or self.request.user.is_general_manager):
            if not agent.team or agent.team.manager != self.request.user:
                raise PermissionDenied("You can only update targets for your own team members.")
        mt = serializer.save()
        # Regenerate daily targets on update
        engine.generate_daily_targets(mt)


# ─── Daily Targets ────────────────────────────────────────────────────────────

class DailyTargetViewSet(viewsets.ModelViewSet):
    serializer_class = DailyTargetSerializer
    permission_classes = [IsAdminOrManager]

    def get_queryset(self):
        qs = DailyTarget.objects.all()
        agent = self.request.query_params.get('agent')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if agent:
            qs = qs.filter(agent_id=agent)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return qs

    def perform_update(self, serializer):
        dt = self.get_object()
        agent = dt.monthly_target.agent
        if not (self.request.user.is_staff or self.request.user.is_general_manager):
            if not agent.team or agent.team.manager != self.request.user:
                raise PermissionDenied("You can only update daily targets for your own team members.")
        # When a manager manually updates the daily target, flag it as manual
        serializer.save(is_manual=True)

    @action(detail=False, methods=['post'])
    def regenerate(self, request):
        month = request.data.get('month')
        year = request.data.get('year')
        if not month or not year:
            return Response({'error': 'month and year are required'},
                            status=status.HTTP_400_BAD_REQUEST)
        engine.regenerate_all_daily_targets_for_month(int(month), int(year))
        return Response({'message': f'Daily targets regenerated for {month}/{year}'})


# ─── Holidays ─────────────────────────────────────────────────────────────────

class HolidayViewSet(viewsets.ModelViewSet):
    serializer_class = HolidaySerializer
    permission_classes = [IsAdminOrManager]

    def get_queryset(self):
        qs = Holiday.objects.all()
        month = self.request.query_params.get('month')
        year = self.request.query_params.get('year')
        if month:
            qs = qs.filter(date__month=month)
        if year:
            qs = qs.filter(date__year=year)
        return qs

    def perform_create(self, serializer):
        holiday = serializer.save(created_by=self.request.user)
        # Regenerate daily targets for the holiday's month
        engine.regenerate_all_daily_targets_for_month(
            holiday.date.month, holiday.date.year
        )

    def perform_destroy(self, instance):
        month, year = instance.date.month, instance.date.year
        instance.delete()
        # Regenerate daily targets after removing a holiday
        engine.regenerate_all_daily_targets_for_month(month, year)


# ─── Meetings ─────────────────────────────────────────────────────────────────

class MeetingViewSet(viewsets.ModelViewSet):
    serializer_class = MeetingSerializer
    permission_classes = [IsAdminOrManager]

    def get_queryset(self):
        qs = Meeting.objects.all()
        upcoming = self.request.query_params.get('upcoming')
        if upcoming == 'true':
            qs = qs.filter(scheduled_at__gte=timezone.now())
        return qs

    def perform_create(self, serializer):
        meeting = serializer.save(created_by=self.request.user)
        # Notify all attendees
        engine.notify_meeting(meeting)

    def perform_update(self, serializer):
        meeting = serializer.save()
        # Re-notify on update
        engine.notify_meeting(meeting)


# ─── Notifications ────────────────────────────────────────────────────────────

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=['post'])
    def mark_read(self, request):
        ids = request.data.get('ids', [])
        if ids:
            Notification.objects.filter(user=request.user, id__in=ids).update(is_read=True)
        else:
            # Mark all as read
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'Notifications marked as read'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'count': count})


# ─── AI Manager Dashboard ────────────────────────────────────────────────────

class AIDashboardView(APIView):
    permission_classes = [IsAdminOrGeneralManager]

    def get(self, request):
        from users.models import User
        from leads.models import Lead

        now = timezone.now()
        today = timezone.localdate(now)
        month = int(request.query_params.get('month', today.month))
        year = int(request.query_params.get('year', today.year))

        config = engine.get_or_create_config()

        # Auto-generate daily targets if missing for any monthly target, and adjust future ones
        engine.sync_daily_targets(month, year)

        # Get all active agents
        agents = User.objects.filter(is_active=True).exclude(is_staff=True).order_by('first_name')

        agent_data = []
        for agent in agents:
            daily_progress = engine.check_daily_progress(agent, today)
            monthly_progress = engine.check_monthly_progress(agent, month, year)

            # Active leads count
            active_leads = Lead.objects.filter(
                assigned_to=agent
            ).exclude(
                status__in=['converted', 'not_interested']
            ).count()

            total_leads = Lead.objects.filter(assigned_to=agent).count()

            name = f"{agent.first_name} {agent.last_name}".strip() or agent.username
            role = "General Manager" if agent.is_general_manager else ("Manager" if agent.is_manager else "Agent")

            agent_data.append({
                'id': agent.id,
                'name': name,
                'role': role,
                'active_leads': active_leads,
                'total_leads': total_leads,
                'daily_progress': daily_progress,
                'monthly_progress': monthly_progress,
            })

        # Upcoming meetings
        upcoming_meetings = Meeting.objects.filter(
            scheduled_at__gte=now
        ).order_by('scheduled_at')[:10]
        meeting_data = MeetingSerializer(upcoming_meetings, many=True).data

        # Holidays this month
        holidays = Holiday.objects.filter(date__month=month, date__year=year)
        holiday_data = HolidaySerializer(holidays, many=True).data

        # Monthly targets summary
        monthly_targets = MonthlyTarget.objects.filter(month=month, year=year)
        total_target_leads = monthly_targets.aggregate(t=Sum('target_leads'))['t'] or 0
        total_target_amount = monthly_targets.aggregate(t=Sum('target_amount'))['t'] or 0

        # Actual wins this month. Won means closed — in accounts with money
        # received (leads.scopes.CLOSED_DEAL_FILTER) — so achievement against a
        # target is measured in business landed, not leads marked converted.
        enrolled_this_month = closed_deals(Lead.objects.filter(
            status_changed_at__year=year,
            status_changed_at__month=month,
        ))
        actual_enrolled = enrolled_this_month.count()
        actual_revenue = enrolled_this_month.aggregate(t=Sum(received_value()))['t'] or 0

        return Response({
            'config': ManagerConfigSerializer(config).data,
            'agents': agent_data,
            'meetings': meeting_data,
            'holidays': holiday_data,
            'summary': {
                'total_agents': len(agent_data),
                'total_target_leads': total_target_leads,
                'total_target_amount': float(total_target_amount),
                'actual_enrolled': actual_enrolled,
                'actual_revenue': float(actual_revenue),
                'month': month,
                'year': year,
            }
        })

class TeamPerformanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.user.is_manager:
            return Response({'error': 'Only managers can view team performance.'}, status=status.HTTP_403_FORBIDDEN)
        
        from users.models import User
        from leads.models import Lead

        now = timezone.now()
        today = timezone.localdate(now)
        month = int(request.query_params.get('month', today.month))
        year = int(request.query_params.get('year', today.year))

        # Get agents ONLY in the manager's team
        agents = User.objects.filter(is_active=True, team__manager=request.user).order_by('first_name')

        # Auto-generate daily targets if missing, and adjust future ones
        engine.sync_daily_targets(month, year)

        agent_data = []
        for agent in agents:
            daily_progress = engine.check_daily_progress(agent, today)
            monthly_progress = engine.check_monthly_progress(agent, month, year)

            # Active leads count
            active_leads = Lead.objects.filter(
                assigned_to=agent
            ).exclude(
                status__in=['converted', 'not_interested']
            ).count()

            total_leads = Lead.objects.filter(assigned_to=agent).count()

            name = f"{agent.first_name} {agent.last_name}".strip() or agent.username
            role = "Agent"

            agent_data.append({
                'id': agent.id,
                'name': name,
                'role': role,
                'active_leads': active_leads,
                'total_leads': total_leads,
                'daily_progress': daily_progress,
                'monthly_progress': monthly_progress,
            })

        # Upcoming meetings
        upcoming_meetings = Meeting.objects.filter(
            scheduled_at__gte=now
        ).order_by('scheduled_at')[:10]
        meeting_data = MeetingSerializer(upcoming_meetings, many=True).data

        # Holidays this month
        holidays = Holiday.objects.filter(date__month=month, date__year=year)
        holiday_data = HolidaySerializer(holidays, many=True).data

        # Monthly targets summary for the team
        monthly_targets = MonthlyTarget.objects.filter(month=month, year=year, agent__in=agents)
        total_target_leads = monthly_targets.aggregate(t=Sum('target_leads'))['t'] or 0
        total_target_amount = monthly_targets.aggregate(t=Sum('target_amount'))['t'] or 0

        # Actual wins this month for the team — closed, not merely converted.
        enrolled_this_month = closed_deals(Lead.objects.filter(
            status_changed_at__year=year,
            status_changed_at__month=month,
            assigned_to__in=agents,
        ))
        actual_enrolled = enrolled_this_month.count()
        actual_revenue = enrolled_this_month.aggregate(t=Sum(received_value()))['t'] or 0

        return Response({
            'agents': agent_data,
            'meetings': meeting_data,
            'holidays': holiday_data,
            'summary': {
                'total_agents': len(agent_data),
                'total_target_leads': total_target_leads,
                'total_target_amount': float(total_target_amount),
                'actual_enrolled': actual_enrolled,
                'actual_revenue': float(actual_revenue),
                'month': month,
                'year': year,
            }
        })


# ─── Auto-Assign Unassigned Leads ─────────────────────────────────────────────

class AutoAssignView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Only admins can trigger auto-assign'},
                            status=status.HTTP_403_FORBIDDEN)

        from leads.models import Lead
        unassigned = Lead.objects.filter(assigned_to__isnull=True)
        count = 0
        for lead in unassigned:
            result = engine.assign_lead(lead)
            if result:
                count += 1

        return Response({'message': f'Successfully assigned {count} leads.'})


# ─── Generate Reminders ──────────────────────────────────────────────────────

class GenerateRemindersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Only admins can generate reminders'},
                            status=status.HTTP_403_FORBIDDEN)

        reminder_type = request.data.get('type', 'daily')  # daily or monthly

        if reminder_type == 'daily':
            created = engine.generate_daily_reminders()
        else:
            month = request.data.get('month')
            year = request.data.get('year')
            created = engine.generate_monthly_summary_notifications(
                month=int(month) if month else None,
                year=int(year) if year else None
            )

        return Response({'message': f'Created {len(created)} reminder notifications.'})


# ─── Employee Submit Performance ──────────────────────────────────────────────

class SubmitDailyPerformanceView(APIView):
    """Allow employees to submit their daily performance metrics and screenshots."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        date_str = request.data.get('date')
        if not date_str:
            return Response({'error': 'Date is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            daily_target = DailyTarget.objects.get(agent=request.user, date=date_str)
        except DailyTarget.DoesNotExist:
            return Response({'error': 'Daily target not found for this date'}, status=status.HTTP_404_NOT_FOUND)

        if 'achieved_dialed_calls' in request.data:
            daily_target.achieved_dialed_calls = int(request.data['achieved_dialed_calls'])
        if 'achieved_call_time' in request.data:
            daily_target.achieved_call_time = int(request.data['achieved_call_time'])
            
        daily_target.save()

        # Handle file uploads
        files = request.FILES.getlist('proofs')
        for f in files:
            DailyTargetProof.objects.create(daily_target=daily_target, file=f)

        return Response(DailyTargetSerializer(daily_target).data)


class DeleteDailyProofView(APIView):
    """Delete one of the logged-in user's own performance-proof files."""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, proof_id):
        try:
            proof = DailyTargetProof.objects.get(pk=proof_id, daily_target__agent=request.user)
        except DailyTargetProof.DoesNotExist:
            return Response({'error': 'Proof not found.'}, status=status.HTTP_404_NOT_FOUND)
        proof.file.delete(save=False)
        proof.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── My Performance (Agent/Manager facing) ───────────────────────────────────

class MyPerformanceView(APIView):
    """
    Personal performance dashboard for the logged-in user.
    Accessible to all authenticated users — returns only THEIR data.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from users.models import User
        from leads.models import Lead

        user = request.user
        now = timezone.now()
        today = timezone.localdate(now)
        month = int(request.query_params.get('month', today.month))
        year = int(request.query_params.get('year', today.year))

        # ── Daily progress ──
        # Auto-generate daily targets if missing for this user's monthly target, and adjust future ones
        engine.sync_daily_targets(month, year)
        daily_progress = engine.check_daily_progress(user, today)

        # ── Monthly progress ──
        monthly_progress = engine.check_monthly_progress(user, month, year)

        # ── Daily targets for the month (calendar view data) ──
        daily_targets = DailyTarget.objects.filter(
            agent=user, date__month=month, date__year=year
        ).order_by('date')
        daily_targets_data = DailyTargetSerializer(daily_targets, many=True).data

        # ── My meetings (upcoming) ──
        my_meetings = Meeting.objects.filter(
            attendees=user, scheduled_at__gte=now
        ).order_by('scheduled_at')[:15]
        meetings_data = MeetingSerializer(my_meetings, many=True).data

        # ── All meetings I'm part of this month ──
        month_meetings = Meeting.objects.filter(
            attendees=user,
            scheduled_at__year=year,
            scheduled_at__month=month
        ).order_by('scheduled_at')
        month_meetings_data = MeetingSerializer(month_meetings, many=True).data

        # ── Lead stats ──
        # The shared scope, so this page agrees with the Leads list and the
        # dashboard: a BDE's handed-over leads count (they stay owned by the tele
        # caller), and deleted leads do not.
        from leads.scopes import my_leads as leads_for
        my_leads = leads_for(user)
        total_leads = my_leads.count()
        active_leads = my_leads.exclude(
            status__in=['converted', 'not_interested']
        ).count()

        # Status breakdown
        status_data = my_leads.values('status').annotate(count=Count('id'))
        status_breakdown = {item['status']: item['count'] for item in status_data}

        # Won this month — closed, not merely converted.
        enrolled_this_month = closed_deals(my_leads.filter(
            status_changed_at__year=year,
            status_changed_at__month=month,
        ))
        enrolled_count = enrolled_this_month.count()
        enrolled_revenue = enrolled_this_month.aggregate(t=Sum(received_value()))['t'] or 0

        # Win rate
        total_decided = my_leads.filter(
            status__in=['converted', 'not_interested']
        ).count()
        win_rate = (enrolled_count / total_decided * 100) if total_decided > 0 else 0

        # ── Purchase orders signed ──
        # The BDE's own milestone: the customer has signed, which is the point a
        # lead stops being a maybe. Counted off `po_signed_date` rather than the
        # lead's own dates, so it lands in the month the order was actually
        # signed however long the lead had been open before that.
        #
        # Scoped through `my_leads` like everything else on this page, so it
        # agrees with the lead counts above rather than quietly counting orders
        # on somebody else's leads.
        po_signed_this_month = my_leads.filter(
            site_visit__po_signed_date__year=year,
            site_visit__po_signed_date__month=month,
        ).count()
        po_signed_total = my_leads.filter(site_visit__po_signed_date__isnull=False).count()

        # ── Recent activity ──
        recent_leads = my_leads.order_by('-created_at')[:5]
        recent_data = [{
            'id': l.id,
            'name': f"{l.first_name} {l.last_name}",
            'status': l.status,
            'value': float(l.value),
            'created_at': l.created_at.strftime('%Y-%m-%d'),
        } for l in recent_leads]

        # ── Holidays this month ──
        holidays = Holiday.objects.filter(date__month=month, date__year=year)
        holiday_data = HolidaySerializer(holidays, many=True).data

        # ── User info ──
        name = f"{user.first_name} {user.last_name}".strip() or user.username
        role = "Admin" if user.is_staff else (
            "General Manager" if user.is_general_manager else (
                "Manager" if user.is_manager else "Agent"
            )
        )

        return Response({
            'user': {
                'id': user.id,
                'name': name,
                'role': role,
                'username': user.username,
                'email': user.email,
            },
            'daily_progress': daily_progress,
            'monthly_progress': monthly_progress,
            'daily_targets': daily_targets_data,
            'meetings': meetings_data,
            'month_meetings': month_meetings_data,
            'holidays': holiday_data,
            'lead_stats': {
                'total_leads': total_leads,
                'active_leads': active_leads,
                'enrolled_this_month': enrolled_count,
                'revenue_this_month': float(enrolled_revenue),
                'po_signed_this_month': po_signed_this_month,
                'po_signed_total': po_signed_total,
                'win_rate': round(win_rate, 1),
                'status_breakdown': status_breakdown,
            },
            'recent_leads': recent_data,
            'month': month,
            'year': year,
        })


# ─── Popup Reminders & Custom Generation ──────────────────────────────────────

from datetime import timedelta

class PopupRemindersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        local_date = timezone.localdate(now)

        # Only process for agents
        if not user.is_staff and not user.is_general_manager and not user.is_manager:
            config = engine.get_or_create_config()
            mp = engine.check_monthly_progress(user, local_date.month, local_date.year)
            dp = engine.check_daily_progress(user, local_date)

            # 1. Check Monthly Popup (every N hours as configured)
            if mp['has_target'] and mp['leads_pct'] < 100:
                monthly_interval_hours = config.monthly_popup_interval_hours or 24
                monthly_cutoff = now - timedelta(hours=monthly_interval_hours)
                has_monthly_recent = Notification.objects.filter(
                    user=user,
                    is_popup=True,
                    notification_type='monthly_target',
                    created_at__gte=monthly_cutoff
                ).exists()

                if not has_monthly_recent:
                    Notification.objects.create(
                        user=user,
                        title=f"Monthly Target Progress — {local_date.strftime('%B')}",
                        message=f"You're at {mp['leads_pct']}% of your monthly target! Keep pushing!",
                        notification_type='monthly_target',
                        is_popup=True,
                        extra_data=mp
                    )

            # 2. Check Daily Popup (every N hours as configured)
            if dp['has_target'] and dp['leads_pct'] < 100:
                daily_interval_hours = config.daily_popup_interval_hours or 3
                daily_cutoff = now - timedelta(hours=daily_interval_hours)
                has_daily_recent = Notification.objects.filter(
                    user=user,
                    is_popup=True,
                    notification_type='daily_target',
                    created_at__gte=daily_cutoff
                ).exists()

                if not has_daily_recent:
                    Notification.objects.create(
                        user=user,
                        title="Quick Daily Check-in",
                        message=f"You've secured {dp['actual_leads']} out of {dp['target_leads']} leads so far today. Let's hit that daily goal!",
                        notification_type='daily_target',
                        is_popup=True,
                        extra_data=dp
                    )

        # Fetch, Serialize, and Mark as shown
        popups = Notification.objects.filter(user=user, is_popup=True, popup_shown=False).order_by('created_at')
        if not popups.exists():
            return Response([])

        data = NotificationSerializer(popups, many=True).data
        popups.update(popup_shown=True)
        return Response(data)



class SendCustomReminderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not (user.is_staff or user.is_general_manager or user.is_manager):
            raise PermissionDenied("Only managers can send custom reminders.")
            
        agent_id = request.data.get('agent_id')
        title = request.data.get('title', 'Important Notice')
        message = request.data.get('message', '')
        
        if not message:
            return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        from users.models import User
        if agent_id and agent_id != "all":
            # Target specific agent
            try:
                target = User.objects.get(id=agent_id)
                targets = [target]
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        else:
            # Target everyone under manager
            if user.is_staff or user.is_general_manager:
                targets = list(User.objects.exclude(id=user.id))
            else:
                team = getattr(user, 'managed_team', None)
                if not team:
                    return Response({"error": "You don't manage any team"}, status=status.HTTP_400_BAD_REQUEST)
                targets = list(User.objects.filter(team=team).exclude(id=user.id))
            
            # Also append the manager themselves so they can preview the broadcast
            if user not in targets:
                targets.append(user)
        
        created = 0
        for t in targets:
            Notification.objects.create(
                user=t,
                title=title,
                message=message,
                notification_type='general',
                is_popup=True,
            )
            created += 1
            
        return Response({"success": True, "created": created})


# --- AI Meeting Room Views -----------------------------------------------------

class AIMeetingCheckView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        today = timezone.localdate()

        # For regular agents: auto-start if it's meeting time
        if not user.is_staff and not user.is_general_manager and not user.is_manager:
            session, is_new = ai_meeting_engine.check_and_auto_start_meeting(user)
            if session:
                data = self._serialize_session(session)
                data['active_session']['is_new'] = is_new
                return Response(data)

        # For everyone: return any active session they have today
        active = AIMeetingSession.objects.filter(
            agent=user, status='active', started_at__date=today
        ).first()
        if active:
            return Response(self._serialize_session(active))
        return Response({'active_session': None})

    def _serialize_session(self, session):
        messages = [
            {
                'id': m.id,
                'sender_type': m.sender_type,
                'content': m.content,
                'timestamp': m.timestamp.isoformat(),
            }
            for m in session.messages.all()
        ]
        return {
            'active_session': {
                'id': session.id,
                'session_type': session.session_type,
                'session_type_display': session.get_session_type_display(),
                'status': session.status,
                'started_at': session.started_at.isoformat(),
                'messages': messages,
            }
        }


class AIMeetingStartView(APIView):
    """Allow any authenticated user to manually start an AI meeting session."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        today = timezone.localdate()

        # Close any lingering active sessions first
        AIMeetingSession.objects.filter(
            agent=user, status='active', started_at__date=today
        ).update(status='completed', ended_at=timezone.now())

        # Determine session type by time of day
        hour = timezone.now().hour
        session_type = 'morning' if hour < 13 else 'evening'
        session_type_param = request.data.get('session_type', session_type)

        session = ai_meeting_engine.start_meeting(user, session_type_param)

        messages = [
            {
                'id': m.id,
                'sender_type': m.sender_type,
                'content': m.content,
                'timestamp': m.timestamp.isoformat(),
            }
            for m in session.messages.all()
        ]
        return Response({
            'active_session': {
                'id': session.id,
                'session_type': session.session_type,
                'session_type_display': session.get_session_type_display(),
                'status': session.status,
                'started_at': session.started_at.isoformat(),
                'messages': messages,
                'is_new': True,
            }
        }, status=201)

class AIMeetingChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, session_id):
        user = request.user
        try:
            session = AIMeetingSession.objects.get(id=session_id, agent=user, status='active')
        except AIMeetingSession.DoesNotExist:
            return Response({'error': 'Active session not found.'}, status=404)
        message = request.data.get('message', '').strip()
        if not message:
            return Response({'error': 'Message is required.'}, status=400)
        ai_reply = ai_meeting_engine.ai_respond(session, message, user)
        return Response({'user_message': message, 'ai_reply': ai_reply})

class AIMeetingEndView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, session_id):
        user = request.user
        try:
            session = AIMeetingSession.objects.get(id=session_id)
        except AIMeetingSession.DoesNotExist:
            return Response({'error': 'Session not found.'}, status=404)
        if session.agent != user and not user.is_staff and not user.is_general_manager and not user.is_manager:
            return Response({'error': 'Permission denied.'}, status=403)
        if session.status == 'completed':
            return Response({'mom': session.mom, 'already_completed': True})
        mom = ai_meeting_engine.close_meeting_and_generate_mom(session)
        return Response({'mom': mom, 'success': True})

class AIMeetingSessionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        user = request.user
        today = timezone.localdate()
        if user.is_staff or user.is_general_manager or user.is_manager:
            sessions = AIMeetingSession.objects.filter(started_at__date=today).select_related('agent')
        else:
            sessions = AIMeetingSession.objects.filter(agent=user, started_at__date=today)
        data = []
        for s in sessions:
            agent_name = s.agent.first_name or s.agent.username
            data.append({'id': s.id,'agent_name': agent_name,'session_type': s.session_type,'session_type_display': s.get_session_type_display(),'status': s.status,'started_at': s.started_at.isoformat(),'ended_at': s.ended_at.isoformat() if s.ended_at else None,'has_mom': bool(s.mom),'mom': s.mom,'message_count': s.messages.count()})
        return Response(data)

def _fmt_time(value):
    """Safely format a TimeField value (whether string or datetime.time) to HH:MM."""
    if value is None:
        return '00:00'
    if hasattr(value, 'strftime'):
        return value.strftime('%H:%M')
    # It's already a string — normalize to HH:MM
    return str(value)[:5]


class AIMeetingConfigView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .engine import get_or_create_config
        config = get_or_create_config()
        return Response({
            'morning_meeting_time': _fmt_time(config.morning_meeting_time),
            'evening_meeting_time': _fmt_time(config.evening_meeting_time),
            'meeting_enabled': config.meeting_enabled,
            'meeting_language': config.meeting_language,
            'monthly_popup_interval_hours': config.monthly_popup_interval_hours,
            'daily_popup_interval_hours': config.daily_popup_interval_hours,
        })

    def patch(self, request):
        user = request.user
        if not (user.is_staff or user.is_general_manager):
            return Response({'error': 'Permission denied.'}, status=403)
        from .engine import get_or_create_config
        config = get_or_create_config()
        if 'morning_meeting_time' in request.data:
            config.morning_meeting_time = request.data['morning_meeting_time']
        if 'evening_meeting_time' in request.data:
            config.evening_meeting_time = request.data['evening_meeting_time']
        if 'meeting_enabled' in request.data:
            config.meeting_enabled = request.data['meeting_enabled']
        if 'meeting_language' in request.data:
            config.meeting_language = request.data['meeting_language']
        if 'monthly_popup_interval_hours' in request.data:
            config.monthly_popup_interval_hours = int(request.data['monthly_popup_interval_hours'])
        if 'daily_popup_interval_hours' in request.data:
            config.daily_popup_interval_hours = int(request.data['daily_popup_interval_hours'])
        config.save()
        # Re-fetch from DB to ensure we have proper Python objects (not raw strings)
        config.refresh_from_db()
        return Response({
            'morning_meeting_time': _fmt_time(config.morning_meeting_time),
            'evening_meeting_time': _fmt_time(config.evening_meeting_time),
            'meeting_enabled': config.meeting_enabled,
            'meeting_language': config.meeting_language,
            'monthly_popup_interval_hours': config.monthly_popup_interval_hours,
            'daily_popup_interval_hours': config.daily_popup_interval_hours,
        })


class ForceAIMeetingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not (user.is_staff or user.is_general_manager or user.is_manager):
            return Response({'error': 'Permission denied.'}, status=403)

        agent_id = request.data.get('agent_id')
        if not agent_id:
            return Response({'error': 'Agent ID required'}, status=400)

        from users.models import User
        agent = User.objects.filter(id=agent_id).first()
        if not agent:
            return Response({'error': 'Agent not found'}, status=404)

        from .models import AIMeetingSession, Notification
        # Close any open sessions first
        AIMeetingSession.objects.filter(agent=agent, status='active').update(
            status='completed', ended_at=timezone.now()
        )

        session = ai_meeting_engine.start_meeting(agent, 'ad_hoc')

        Notification.objects.create(
            user=agent,
            title="📞 Ad-hoc AI Meeting Requested",
            message=(
                f"Your manager {user.first_name or user.username} has requested "
                f"an immediate AI check-in. Tap to join."
            ),
            notification_type='meeting',
            is_popup=True,
            extra_data={'session_id': session.id, 'join_meeting': True},
        )

        return Response({'message': 'AI Meeting started successfully!', 'session_id': session.id})
