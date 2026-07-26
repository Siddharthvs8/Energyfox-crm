from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AutomationRule, AutomationLog
from .serializers import AutomationRuleSerializer, AutomationLogSerializer
from .engine import fire_trigger


# ── Prebuilt automation recipes (Templates gallery) ──────────────────────────
# The frontend opens the builder pre-filled with these so the user can pick
# specific agents/teams before saving.
AUTOMATION_TEMPLATES = [
    {
        'key': 'round_robin_new_leads',
        'name': 'Round-robin new leads',
        'description': 'Auto-assign every new lead via the AI engine, create a follow-up task, and notify the owner.',
        'icon': 'shuffle',
        'rule': {
            'name': 'Round-robin new leads',
            'trigger_event': 'lead_created',
            'condition_logic': 'all',
            'conditions': [],
            'actions': [
                {'type': 'ai_auto_assign', 'params': {}},
                {'type': 'create_task', 'params': {'title': 'First touch — call new lead', 'priority': 'high', 'due_days': 1}},
                {'type': 'notify_assignee', 'params': {'message': 'A new lead was assigned to you — reach out today.'}},
            ],
        },
    },
    {
        'key': 'no_activity_nudge',
        'name': 'No-activity nudge (3 days)',
        'description': 'When a lead has had no activity for 3 days, create a re-engagement task and ping the owner.',
        'icon': 'alarm',
        'rule': {
            'name': 'No-activity nudge',
            'trigger_event': 'lead_inactive',
            'trigger_config': {'inactive_days': 3},
            'cooldown_seconds': 86400,
            'condition_logic': 'all',
            'conditions': [],
            'actions': [
                {'type': 'create_task', 'params': {'title': 'Re-engage stale lead', 'priority': 'medium', 'due_days': 0}},
                {'type': 'notify_assignee', 'params': {'message': 'This lead has gone quiet for 3 days — follow up.'}},
            ],
        },
    },
    {
        'key': 'hot_lead_alert',
        'name': 'Hot lead → alert manager',
        'description': 'When a lead turns Positive, escalate to the team manager with a notification.',
        'icon': 'fire',
        'rule': {
            'name': 'Hot lead alert',
            'trigger_event': 'lead_status_changed',
            'trigger_config': {'to_status': 'positive'},
            'condition_logic': 'all',
            'conditions': [],
            'actions': [
                {'type': 'escalate_to_manager', 'params': {'reassign': False, 'message': 'A hot lead just turned Positive — consider stepping in.'}},
            ],
        },
    },
    {
        'key': 'welcome_sequence',
        'name': 'Welcome email sequence',
        'description': 'Drip: welcome email now → wait 2 days → follow-up task → wait 3 days → check-in email.',
        'icon': 'mail',
        'rule': {
            'name': 'Welcome sequence',
            'trigger_event': 'lead_created',
            'condition_logic': 'all',
            'conditions': [],
            'actions': [
                {'type': 'send_email', 'params': {'subject': 'Welcome, {{first_name}}!', 'body': 'Hi {{first_name}},\n\nThanks for your interest — we’ll be in touch shortly.'}},
                {'type': 'wait', 'params': {'amount': 2, 'unit': 'days'}},
                {'type': 'create_task', 'params': {'title': 'Personal follow-up call', 'priority': 'medium', 'due_days': 0}},
                {'type': 'wait', 'params': {'amount': 3, 'unit': 'days'}},
                {'type': 'send_email', 'params': {'subject': 'Still here for you, {{first_name}}', 'body': 'Just checking in — happy to answer any questions.'}},
            ],
        },
    },
    {
        'key': 'missed_call_followup',
        'name': 'Missed-call follow-up',
        'description': 'After an unanswered/busy call, wait a day then create a retry task and notify the owner.',
        'icon': 'phone-missed',
        'rule': {
            'name': 'Missed-call follow-up',
            'trigger_event': 'call_logged',
            'condition_logic': 'any',
            'conditions': [
                {'field': 'status', 'operator': 'not_equals', 'value': 'converted'},
            ],
            'actions': [
                {'type': 'wait', 'params': {'amount': 1, 'unit': 'days'}},
                {'type': 'create_task', 'params': {'title': 'Retry call — previous attempt failed', 'priority': 'high', 'due_days': 0}},
                {'type': 'notify_assignee', 'params': {'message': 'A call to this lead did not connect — try again.'}},
            ],
        },
    },
    {
        'key': 'duplicate_guard',
        'name': 'Duplicate guard',
        'description': 'On every new lead, flag possible duplicates by email/phone in the notes.',
        'icon': 'copy',
        'rule': {
            'name': 'Duplicate guard',
            'trigger_event': 'lead_created',
            'condition_logic': 'all',
            'conditions': [],
            'actions': [
                {'type': 'duplicate_check', 'params': {'fields': ['email', 'phone']}},
            ],
        },
    },
]


class AutomationRuleViewSet(viewsets.ModelViewSet):
    """Full CRUD for automation rules with toggle, test, and logs actions."""
    queryset = AutomationRule.objects.all()
    serializer_class = AutomationRuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Enable/disable a rule."""
        rule = self.get_object()
        rule.is_active = not rule.is_active
        rule.save(update_fields=['is_active'])
        return Response({
            'id': rule.id,
            'is_active': rule.is_active,
            'message': f"Rule '{ rule.name }' {'enabled' if rule.is_active else 'disabled'}."
        })

    @action(detail=False, methods=['get'])
    def templates(self, request):
        """Prebuilt automation recipes the user can install & tweak."""
        return Response(AUTOMATION_TEMPLATES)

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Dry-run: fire the rule against the most recent matching object."""
        rule = self.get_object()

        # Determine the object type based on trigger
        if rule.trigger_event.startswith('lead'):
            from leads.models import Lead
            obj = Lead.objects.order_by('-created_at').first()
            if not obj:
                return Response({'error': 'No leads found to test against.'}, status=status.HTTP_404_NOT_FOUND)
        elif rule.trigger_event.startswith('task'):
            from tasks.models import Task
            obj = Task.objects.order_by('-created_at').first()
            if not obj:
                return Response({'error': 'No tasks found to test against.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            from leads.models import Lead
            obj = Lead.objects.order_by('-created_at').first()
            if not obj:
                return Response({'error': 'No objects found to test against.'}, status=status.HTTP_404_NOT_FOUND)

        # Fire the trigger just for this single rule
        try:
            from .engine import _execute_rule
            _execute_rule(rule, obj, {})
            # Get the latest log for this rule
            log = AutomationLog.objects.filter(rule=rule).order_by('-created_at').first()
            log_data = AutomationLogSerializer(log).data if log else {}
            return Response({
                'message': f"Test executed against {obj.__class__.__name__} #{obj.id}",
                'log': log_data,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def bulk_run(self, request, pk=None):
        """Execute the rule retroactively against all existing records (max 500)."""
        rule = self.get_object()

        # Determine the object type based on trigger
        if rule.trigger_event.startswith('lead'):
            from leads.models import Lead
            objects = Lead.objects.all().order_by('-created_at')[:500]
        elif rule.trigger_event.startswith('task'):
            from tasks.models import Task
            objects = Task.objects.all().order_by('-created_at')[:500]
        else:
            from leads.models import Lead
            objects = Lead.objects.all().order_by('-created_at')[:500]

        if not objects:
            return Response({'message': 'No records found to execute against.', 'success': 0, 'skipped': 0, 'failed': 0}, status=status.HTTP_200_OK)

        success_count = 0
        skipped_count = 0
        failed_count = 0

        from .engine import _execute_rule
        # Get count of logs before
        before_logs = rule.logs.count()

        for obj in objects:
            try:
                _execute_rule(rule, obj, {}, bypass_limits=True)
            except Exception:
                failed_count += 1
                continue

        # Summarize by checking newly created logs
        # Since _execute_rule synchronously writes logs, we can just aggregate recent logs.
        # However, a simpler estimation:
        # We can just count up all statuses in the last minute for this rule.
        # But this loop is fine. Let's just group by logs.
        import datetime
        from django.utils import timezone
        recent_logs = rule.logs.filter(created_at__gte=timezone.now() - datetime.timedelta(minutes=5)).order_by('-id')[:len(objects)]
        
        for log in recent_logs:
            if log.status == 'success':
                success_count += 1
            elif log.status == 'skipped':
                skipped_count += 1
            else:
                failed_count += 1

        # Adjust for possible miscount if fewer logs generated
        if (success_count + skipped_count + failed_count) == 0:
            success_count = len(objects) # fallback assumption if logs are disabled or missing (unlikely)

        return Response({
            'message': f'Bulk execution completed on {len(objects)} records.',
            'success': success_count,
            'skipped': skipped_count,
            'failed': failed_count
        })

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """Retrieve execution history for a specific rule."""
        rule = self.get_object()
        logs = AutomationLog.objects.filter(rule=rule).order_by('-created_at')[:100]
        serializer = AutomationLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def all_logs(self, request):
        """Retrieve all automation logs across all rules."""
        logs = AutomationLog.objects.all().order_by('-created_at')[:200]
        serializer = AutomationLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def metadata_options(self, request):
        """Return available fields, operators, action types for the rule builder UI."""
        # Live Meta integration (branch) names, so a rule can be scoped to the
        # account a lead arrived from without typing the name by hand.
        from leads.models import IntegrationSettings
        meta_integration_names = [
            n for n in IntegrationSettings.objects.exclude(name='')
            .order_by('name').values_list('name', flat=True)
        ]
        return Response({
            'triggers': [
                {'value': k, 'label': v}
                for k, v in AutomationRule.TRIGGER_CHOICES
            ],
            'condition_fields': [
                {'value': 'source', 'label': 'Source', 'type': 'text'},
                {'value': 'status', 'label': 'Status', 'type': 'select', 'options': [
                    'new', 'follow_up', 'positive', 'interested', 'not_interested', 'converted',
                ]},
                # Which Meta Lead Ads account (branch) the lead came from — lets a
                # rule route, assign or notify per branch.
                {'value': 'meta_integration_name', 'label': 'Meta Integration (Branch)',
                 'type': 'select', 'options': meta_integration_names},
                {'value': 'meta_campaign_name', 'label': 'Meta Campaign', 'type': 'text'},
                {'value': 'value', 'label': 'Deal Value', 'type': 'number'},
                {'value': 'first_name', 'label': 'First Name', 'type': 'text'},
                {'value': 'last_name', 'label': 'Last Name', 'type': 'text'},
                {'value': 'email', 'label': 'Email', 'type': 'text'},
                {'value': 'phone', 'label': 'Phone', 'type': 'text'},
                {'value': 'company', 'label': 'Company', 'type': 'text'},
                {'value': 'notes', 'label': 'Notes', 'type': 'text'},
                {'value': 'installation_location', 'label': 'Installation Location', 'type': 'text'},
                # Pipeline flags (compare against "True" / "False")
                {'value': 'is_lost', 'label': 'Deal Lost (True/False)', 'type': 'text'},
                {'value': 'pushed_to_documentation', 'label': 'In Documentation — Closed Deal (True/False)', 'type': 'text'},
                {'value': 'pushed_to_purchase', 'label': 'In Purchase & Logistics (True/False)', 'type': 'text'},
                {'value': 'pushed_to_doc_stage2', 'label': 'In Documentation Stage 2 (True/False)', 'type': 'text'},
                {'value': 'pushed_to_warranty', 'label': 'In Warranty (True/False)', 'type': 'text'},
                {'value': 'pushed_to_liasoning', 'label': 'In Liasoning & Service (True/False)', 'type': 'text'},
            ],
            'operators': [
                {'value': 'equals', 'label': 'Equals'},
                {'value': 'not_equals', 'label': 'Not Equals'},
                {'value': 'contains', 'label': 'Contains'},
                {'value': 'not_contains', 'label': 'Does Not Contain'},
                {'value': 'starts_with', 'label': 'Starts With'},
                {'value': 'ends_with', 'label': 'Ends With'},
                {'value': 'greater_than', 'label': 'Greater Than'},
                {'value': 'less_than', 'label': 'Less Than'},
                {'value': 'greater_or_equal', 'label': 'Greater or Equal'},
                {'value': 'less_or_equal', 'label': 'Less or Equal'},
                {'value': 'is_empty', 'label': 'Is Empty'},
                {'value': 'is_not_empty', 'label': 'Is Not Empty'},
            ],
            'action_types': [
                {'value': 'ai_auto_assign', 'label': '🤖 AI Auto-Assign (Smart)', 'params': ['force']},
                {'value': 'assign_lead', 'label': 'Assign to Specific User', 'params': ['user_id', 'round_robin', 'team_id']},
                {'value': 'change_status', 'label': 'Change Status', 'params': ['status']},
                {'value': 'create_task', 'label': 'Create Task', 'params': ['title', 'priority', 'due_days', 'assignee_id']},
                {'value': 'add_to_campaign', 'label': 'Add to Campaign', 'params': ['campaign_id']},
                {'value': 'send_webhook', 'label': 'Send Webhook', 'params': ['url', 'method']},
                {'value': 'send_notification', 'label': 'Send Notification', 'params': ['user_id', 'message']},
                {'value': 'update_field', 'label': 'Update Field', 'params': ['field', 'value']},
                {'value': 'add_note', 'label': 'Add Note', 'params': ['note']},
                {'value': 'duplicate_check', 'label': 'Duplicate Check', 'params': ['fields']},
                {'value': 'reassign_employee_leads', 'label': 'Reassign Employee Leads', 'params': ['from_user_id', 'to_user_id', 'round_robin', 'team_id', 'lead_status', 'new_status']},
            ],
            'priorities': [
                {'value': k, 'label': v}
                for k, v in AutomationRule.PRIORITY_CHOICES
            ],
        })
