"""
Automation Engine — Core execution logic.

This module evaluates triggers, checks conditions, and dispatches actions.
It is designed for safety (anti-loop, rate limiting, cooldowns) and
observability (every execution is logged).
"""
import time
import logging
import requests
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from django.db.models import Q

from .models import AutomationRule, AutomationLog

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

def fire_trigger(trigger_event: str, obj, context: dict | None = None):
    """
    Called by view hooks whenever a CRM event occurs.
    
    Args:
        trigger_event: One of the TRIGGER_CHOICES keys
        obj: The Django model instance that triggered the event (Lead, Task, etc.)
        context: Optional extra context (e.g. {"old_status": "new", "new_status": "follow_up"})
    """
    context = context or {}
    
    rules = AutomationRule.objects.filter(
        is_active=True,
        trigger_event=trigger_event,
    ).order_by('priority')

    for rule in rules:
        try:
            _execute_rule(rule, obj, context)
        except Exception as e:
            logger.exception(f"Automation rule '{rule.name}' (id={rule.id}) crashed: {e}")
            AutomationLog.objects.create(
                rule=rule,
                trigger_event=trigger_event,
                trigger_object_type=obj.__class__.__name__.lower(),
                trigger_object_id=obj.pk,
                trigger_data=_snapshot(obj),
                conditions_matched=False,
                status='failed',
                error_message=str(e),
            )


# ── Rule Execution ────────────────────────────────────────────────────────────

def _execute_rule(rule: AutomationRule, obj, context: dict, bypass_limits: bool = False):
    start = time.monotonic()
    trigger_data = _snapshot(obj)

    # ── Rate-limit check ──
    if not bypass_limits and rule.max_executions_per_hour > 0:
        one_hour_ago = timezone.now() - timedelta(hours=1)
        recent = AutomationLog.objects.filter(
            rule=rule, created_at__gte=one_hour_ago
        ).count()
        if recent >= rule.max_executions_per_hour:
            AutomationLog.objects.create(
                rule=rule, trigger_event=rule.trigger_event,
                trigger_object_type=obj.__class__.__name__.lower(),
                trigger_object_id=obj.pk, trigger_data=trigger_data,
                conditions_matched=False, status='skipped',
                error_message=f'Rate limit exceeded ({rule.max_executions_per_hour}/hr)',
            )
            return

    # ── Cooldown check ──
    if not bypass_limits and rule.cooldown_seconds > 0:
        cooldown_cutoff = timezone.now() - timedelta(seconds=rule.cooldown_seconds)
        last = AutomationLog.objects.filter(
            rule=rule,
            trigger_object_id=obj.pk,
            trigger_object_type=obj.__class__.__name__.lower(),
            created_at__gte=cooldown_cutoff,
        ).exists()
        if last:
            AutomationLog.objects.create(
                rule=rule, trigger_event=rule.trigger_event,
                trigger_object_type=obj.__class__.__name__.lower(),
                trigger_object_id=obj.pk, trigger_data=trigger_data,
                conditions_matched=False, status='skipped',
                error_message=f'Cooldown active ({rule.cooldown_seconds}s)',
            )
            return

    # ── Trigger-config filter (e.g. from_status / to_status) ──
    if rule.trigger_config:
        tc = rule.trigger_config
        if 'from_status' in tc and tc['from_status']:
            if context.get('old_status') != tc['from_status']:
                return  # silently skip — wrong status transition
        if 'to_status' in tc and tc['to_status']:
            if context.get('new_status') != tc['to_status']:
                return

    # ── Evaluate conditions ──
    matched = _evaluate_conditions(rule, obj)

    if not matched:
        AutomationLog.objects.create(
            rule=rule, trigger_event=rule.trigger_event,
            trigger_object_type=obj.__class__.__name__.lower(),
            trigger_object_id=obj.pk, trigger_data=trigger_data,
            conditions_matched=False, status='skipped',
            error_message='Conditions not met',
            execution_time_ms=int((time.monotonic() - start) * 1000),
        )
        return

    # ── Execute actions (a `wait` step defers the remainder, see _run_action_list) ──
    action_results, overall_status = _run_action_list(rule, obj, context, rule.actions or [])

    elapsed = int((time.monotonic() - start) * 1000)

    AutomationLog.objects.create(
        rule=rule, trigger_event=rule.trigger_event,
        trigger_object_type=obj.__class__.__name__.lower(),
        trigger_object_id=obj.pk, trigger_data=trigger_data,
        conditions_matched=True, actions_executed=action_results,
        status=overall_status, execution_time_ms=elapsed,
    )
    _bump_stats(rule, overall_status)


def _bump_stats(rule: AutomationRule, overall_status: str):
    rule.execution_count += 1
    if overall_status == 'success':
        rule.success_count += 1
    else:
        rule.failure_count += 1
    rule.last_executed_at = timezone.now()
    rule.save(update_fields=['execution_count', 'success_count', 'failure_count', 'last_executed_at'])


# ── Action list runner (supports timed `wait` steps) ───────────────────────────

def _run_action_list(rule: AutomationRule, obj, context: dict, actions: list):
    """Run actions in order. On a `wait`/`delay` step, persist the remaining
    actions to the ScheduledAction queue and stop — they resume later via the
    `process_automation_queue` management command."""
    action_results = []
    overall_status = 'success'

    for i, action_def in enumerate(actions or []):
        action_type = action_def.get('type', '')
        params = action_def.get('params', {}) or {}

        if action_type in ('wait', 'delay'):
            remaining = list(actions[i + 1:])
            run_at = _wait_until(params)
            if remaining:
                from .models import ScheduledAction
                ScheduledAction.objects.create(
                    rule=rule,
                    trigger_event=rule.trigger_event,
                    object_type=obj.__class__.__name__.lower(),
                    object_id=obj.pk,
                    remaining_actions=remaining,
                    context=context or {},
                    run_at=run_at,
                )
                action_results.append({
                    'type': 'wait', 'status': 'success',
                    'detail': f"Paused — {len(remaining)} step(s) scheduled for {run_at:%Y-%m-%d %H:%M}",
                })
            else:
                action_results.append({
                    'type': 'wait', 'status': 'success', 'detail': 'Wait step had no following actions',
                })
            break  # everything after the wait runs later

        try:
            result = _dispatch_action(action_type, params, obj, context)
            action_results.append({'type': action_type, 'status': 'success', 'detail': result or 'OK'})
        except Exception as e:
            overall_status = 'partial'
            action_results.append({'type': action_type, 'status': 'failed', 'detail': str(e)})

    if action_results and all(a['status'] == 'failed' for a in action_results):
        overall_status = 'failed'
    return action_results, overall_status


def _wait_until(params: dict):
    amount = float(params.get('amount', params.get('days', 0)) or 0)
    unit = (params.get('unit') or 'days').lower()
    if unit.startswith('min'):
        delta = timedelta(minutes=amount)
    elif unit.startswith('hour'):
        delta = timedelta(hours=amount)
    else:
        delta = timedelta(days=amount)
    return timezone.now() + delta


def _load_object(object_type: str, object_id: int):
    if object_type == 'lead':
        from leads.models import Lead
        return Lead.objects.filter(pk=object_id).first()
    if object_type == 'task':
        from tasks.models import Task
        return Task.objects.filter(pk=object_id).first()
    if object_type == 'calllog':
        from calls.models import CallLog
        return CallLog.objects.filter(pk=object_id).first()
    return None


def resume_scheduled_action(sa) -> str:
    """Resume a queued (post-wait) chunk of a rule. Used by the queue command."""
    obj = _load_object(sa.object_type, sa.object_id)
    if obj is None:
        return 'object_gone'
    rule = sa.rule
    if not rule.is_active:
        return 'rule_inactive'
    action_results, overall_status = _run_action_list(rule, obj, sa.context or {}, sa.remaining_actions or [])
    AutomationLog.objects.create(
        rule=rule, trigger_event=sa.trigger_event or rule.trigger_event,
        trigger_object_type=sa.object_type, trigger_object_id=sa.object_id,
        trigger_data=_snapshot(obj), conditions_matched=True,
        actions_executed=action_results, status=overall_status,
    )
    _bump_stats(rule, overall_status)
    return overall_status


def _render(text: str, obj) -> str:
    """Replace {{field}} placeholders with the object's attribute values."""
    if not text:
        return text or ''
    import re
    return re.sub(r'\{\{\s*(\w+)\s*\}\}', lambda m: str(getattr(obj, m.group(1), '') or ''), text)


# ── Condition Evaluator ───────────────────────────────────────────────────────

def _evaluate_conditions(rule: AutomationRule, obj) -> bool:
    conditions = rule.conditions or []
    if not conditions:
        return True  # no conditions = always match

    results = []
    for cond in conditions:
        field = cond.get('field', '')
        operator = cond.get('operator', 'equals')
        expected = cond.get('value', '')
        results.append(_check_condition(obj, field, operator, expected))

    if rule.condition_logic == 'any':
        return any(results)
    return all(results)


# Condition fields resolved through a relation rather than a plain attribute, so
# rules can match on a human name instead of a raw id. Keyed by the field name
# offered in the rule builder (see automations.views.metadata_options).
_RELATED_FIELDS = {
    # Which Meta Lead Ads account (branch) the lead arrived from.
    'meta_integration_name': lambda o: getattr(getattr(o, 'meta_integration', None), 'name', '') or '',
    'assigned_to_name': lambda o: (
        f"{o.assigned_to.first_name} {o.assigned_to.last_name}".strip() or o.assigned_to.username
    ) if getattr(o, 'assigned_to', None) else '',
    'product_name': lambda o: getattr(getattr(o, 'product', None), 'name', '') or '',
}


def _check_condition(obj, field: str, operator: str, expected) -> bool:
    """Evaluate a single condition against the object."""
    try:
        if field in _RELATED_FIELDS:
            actual = _RELATED_FIELDS[field](obj)
        else:
            actual = getattr(obj, field, None)
    except Exception:
        return False

    if actual is None:
        actual_str = ''
    elif isinstance(actual, Decimal):
        actual_str = str(float(actual))
    else:
        actual_str = str(actual)

    expected_str = str(expected) if expected is not None else ''

    if operator == 'equals':
        return actual_str.lower() == expected_str.lower()
    elif operator == 'not_equals':
        return actual_str.lower() != expected_str.lower()
    elif operator == 'contains':
        return expected_str.lower() in actual_str.lower()
    elif operator == 'not_contains':
        return expected_str.lower() not in actual_str.lower()
    elif operator == 'starts_with':
        return actual_str.lower().startswith(expected_str.lower())
    elif operator == 'ends_with':
        return actual_str.lower().endswith(expected_str.lower())
    elif operator == 'greater_than':
        try:
            return float(actual_str) > float(expected_str)
        except (ValueError, TypeError):
            return False
    elif operator == 'less_than':
        try:
            return float(actual_str) < float(expected_str)
        except (ValueError, TypeError):
            return False
    elif operator == 'greater_or_equal':
        try:
            return float(actual_str) >= float(expected_str)
        except (ValueError, TypeError):
            return False
    elif operator == 'less_or_equal':
        try:
            return float(actual_str) <= float(expected_str)
        except (ValueError, TypeError):
            return False
    elif operator == 'is_empty':
        return not actual_str.strip()
    elif operator == 'is_not_empty':
        return bool(actual_str.strip())
    elif operator == 'in':
        # expected is comma-separated list
        values = [v.strip().lower() for v in expected_str.split(',')]
        return actual_str.lower() in values
    elif operator == 'not_in':
        values = [v.strip().lower() for v in expected_str.split(',')]
        return actual_str.lower() not in values

    return False


# ── Action Dispatcher ─────────────────────────────────────────────────────────

def _dispatch_action(action_type: str, params: dict, obj, context: dict) -> str:
    """Route to the appropriate action handler."""
    handlers = {
        'assign_lead': _action_assign_lead,
        'ai_auto_assign': _action_ai_auto_assign,
        'change_status': _action_change_status,
        'create_task': _action_create_task,
        'add_to_campaign': _action_add_to_campaign,
        'send_webhook': _action_send_webhook,
        'send_notification': _action_send_notification,
        'update_field': _action_update_field,
        'add_note': _action_add_note,
        'duplicate_check': _action_duplicate_check,
        'reassign_employee_leads': _action_reassign_employee_leads,
        'send_email': _action_send_email,
        'escalate_to_manager': _action_escalate_to_manager,
        'notify_assignee': _action_notify_assignee,
        'send_whatsapp': _action_send_whatsapp,
    }
    handler = handlers.get(action_type)
    if not handler:
        raise ValueError(f"Unknown action type: {action_type}")
    return handler(params, obj, context)


# ── Individual Action Implementations ─────────────────────────────────────────

def _action_assign_lead(params, obj, context) -> str:
    from leads.models import Lead
    if not isinstance(obj, Lead):
        raise ValueError("assign_lead only works on Lead objects")

    user_id = params.get('user_id')
    round_robin = params.get('round_robin', False)
    team_id = params.get('team_id')

    if round_robin and team_id:
        # Round-robin among team members
        from users.models import WorkspaceTeam, User
        try:
            team = WorkspaceTeam.objects.get(id=team_id)
            members = list(team.members.filter(is_active=True).order_by('id'))
            if not members:
                return "No active team members for round-robin"
            
            # Find who got the last assignment
            last_log = AutomationLog.objects.filter(
                actions_executed__contains=[{'type': 'assign_lead'}],
                status='success',
            ).order_by('-created_at').first()
            
            last_assigned_id = None
            if last_log:
                for ax in (last_log.actions_executed or []):
                    if ax.get('type') == 'assign_lead' and '(id=' in ax.get('detail', ''):
                        try:
                            last_assigned_id = int(ax['detail'].split('(id=')[1].split(')')[0])
                        except (IndexError, ValueError):
                            pass

            # Pick next in rotation
            member_ids = [m.id for m in members]
            if last_assigned_id and last_assigned_id in member_ids:
                idx = (member_ids.index(last_assigned_id) + 1) % len(member_ids)
            else:
                idx = 0

            target = members[idx]
            obj.assigned_to = target
            obj.save(update_fields=['assigned_to'])
            return f"Round-robin assigned to {target.first_name} {target.last_name} (id={target.id})"
        except WorkspaceTeam.DoesNotExist:
            raise ValueError(f"Team id={team_id} not found")
    elif user_id:
        from users.models import User
        try:
            user = User.objects.get(id=user_id)
            obj.assigned_to = user
            obj.save(update_fields=['assigned_to'])
            return f"Assigned to {user.first_name} {user.last_name} (id={user.id})"
        except User.DoesNotExist:
            raise ValueError(f"User id={user_id} not found")
    else:
        raise ValueError("assign_lead requires user_id or round_robin+team_id")


def _action_ai_auto_assign(params, obj, context) -> str:
    """
    Assigns the lead using the AI Manager's intelligent assignment engine.
    Respects the ManagerConfig assignment_strategy (workload_balanced / round_robin)
    and skips assignment if the lead is already assigned (unless force=True is passed).
    """
    from leads.models import Lead
    if not isinstance(obj, Lead):
        raise ValueError("ai_auto_assign only works on Lead objects")

    force = params.get('force', False)

    # Don't re-assign if already assigned unless forced
    if obj.assigned_to and not force:
        return f"Skipped — lead already assigned to {obj.assigned_to.first_name} {obj.assigned_to.last_name} (use force=true to override)"

    try:
        from ai_manager.engine import assign_lead
        assigned_user = assign_lead(obj)
        if assigned_user:
            return f"AI-assigned to {assigned_user.first_name} {assigned_user.last_name} (id={assigned_user.id})"
        else:
            return "AI auto-assign skipped — manual mode or no eligible agents"
    except Exception as e:
        raise ValueError(f"AI auto-assign failed: {e}")


def _action_change_status(params, obj, context) -> str:
    from leads.models import Lead
    if not isinstance(obj, Lead):
        raise ValueError("change_status only works on Lead objects")

    new_status = params.get('status')
    if not new_status:
        raise ValueError("change_status requires 'status' param")

    old_status = obj.status
    obj.status = new_status
    obj.status_changed_at = timezone.now()
    obj.save(update_fields=['status', 'status_changed_at'])
    return f"Status changed: {old_status} → {new_status}"


def _action_create_task(params, obj, context) -> str:
    from tasks.models import Task
    from leads.models import Lead

    title = params.get('title', 'Follow-up Task')
    priority = params.get('priority', 'medium')
    due_days = int(params.get('due_days', 1))
    assignee_id = params.get('assignee_id')

    task_data = {
        'title': title,
        'priority': priority,
        'status': 'todo',
        'due_date': (timezone.now() + timedelta(days=due_days)).date(),
    }

    if isinstance(obj, Lead):
        task_data['lead'] = obj

    if assignee_id:
        from users.models import User
        try:
            task_data['assignee'] = User.objects.get(id=assignee_id)
        except User.DoesNotExist:
            pass
    elif isinstance(obj, Lead) and obj.assigned_to:
        task_data['assignee'] = obj.assigned_to

    task = Task.objects.create(**task_data)
    return f"Task created: '{title}' (id={task.id}), due in {due_days} day(s)"


def _action_add_to_campaign(params, obj, context) -> str:
    from leads.models import Lead
    from campaigns.models import Campaign

    if not isinstance(obj, Lead):
        raise ValueError("add_to_campaign only works on Lead objects")

    campaign_id = params.get('campaign_id')
    if not campaign_id:
        raise ValueError("add_to_campaign requires 'campaign_id'")

    try:
        campaign = Campaign.objects.get(id=campaign_id)
        campaign.leads.add(obj)
        return f"Added to campaign '{campaign.name}' (id={campaign.id})"
    except Campaign.DoesNotExist:
        raise ValueError(f"Campaign id={campaign_id} not found")


def _action_send_webhook(params, obj, context) -> str:
    url = params.get('url')
    method = params.get('method', 'POST').upper()
    if not url:
        raise ValueError("send_webhook requires 'url'")

    payload = _snapshot(obj)
    payload['_trigger'] = context

    headers = params.get('headers', {})
    headers.setdefault('Content-Type', 'application/json')

    try:
        if method == 'POST':
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
        elif method == 'GET':
            resp = requests.get(url, params=payload, headers=headers, timeout=10)
        else:
            resp = requests.request(method, url, json=payload, headers=headers, timeout=10)

        return f"Webhook {method} {url} → {resp.status_code}"
    except requests.RequestException as e:
        raise ValueError(f"Webhook failed: {e}")


def _action_send_notification(params, obj, context) -> str:
    """Create an in-app notification (uses ai_manager notification if available)."""
    user_id = params.get('user_id')
    message = params.get('message', 'Automation notification')

    if not user_id:
        raise ValueError("send_notification requires 'user_id'")

    try:
        from ai_manager.models import Notification
        from users.models import User
        user = User.objects.get(id=user_id)
        Notification.objects.create(
            user=user,
            title='🤖 Automation Alert',
            message=message,
        )
        return f"Notification sent to user id={user_id}"
    except ImportError:
        # Fallback: just log it
        return f"Notification logged for user id={user_id} (notification module not available)"
    except Exception as e:
        raise ValueError(f"Notification failed: {e}")


def _action_update_field(params, obj, context) -> str:
    field = params.get('field')
    value = params.get('value')

    if not field:
        raise ValueError("update_field requires 'field'")

    if not hasattr(obj, field):
        raise ValueError(f"Object has no field '{field}'")

    old_value = getattr(obj, field)
    setattr(obj, field, value)
    obj.save(update_fields=[field])
    return f"Field '{field}' updated: '{old_value}' → '{value}'"


def _action_add_note(params, obj, context) -> str:
    from leads.models import Lead
    if not isinstance(obj, Lead):
        raise ValueError("add_note only works on Lead objects")

    note = params.get('note', '')
    if not note:
        raise ValueError("add_note requires 'note'")

    existing = obj.notes or ''
    timestamp = timezone.now().strftime('%Y-%m-%d %H:%M')
    obj.notes = f"{existing}\n\n[AUTO {timestamp}] {note}".strip()
    obj.save(update_fields=['notes'])
    return f"Note appended to lead"


def _action_duplicate_check(params, obj, context) -> str:
    """Check for duplicate leads based on specified fields."""
    from leads.models import Lead
    if not isinstance(obj, Lead):
        raise ValueError("duplicate_check only works on Lead objects")

    fields = params.get('fields', ['email', 'phone'])
    q = Q()
    for field in fields:
        val = getattr(obj, field, None)
        if val and str(val).strip():
            q |= Q(**{field: val})

    if not q:
        return "No fields to check for duplicates"

    dupes = Lead.objects.filter(q).exclude(id=obj.id)
    count = dupes.count()

    if count > 0:
        dupe_ids = list(dupes.values_list('id', flat=True)[:5])
        note = f"[DUPLICATE ALERT] {count} possible duplicate(s) found: IDs {dupe_ids}"
        existing = obj.notes or ''
        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M')
        obj.notes = f"{existing}\n\n[AUTO {timestamp}] {note}".strip()
        obj.save(update_fields=['notes'])
        return f"Found {count} duplicate(s): {dupe_ids}"

    return "No duplicates found"


def _action_reassign_employee_leads(params, obj, context) -> str:
    """Reassign all leads from one employee to another (or team), optionally filtering by status."""
    from leads.models import Lead
    from users.models import User, WorkspaceTeam

    from_user_id = params.get('from_user_id')
    if not from_user_id:
        raise ValueError("reassign_employee_leads requires 'from_user_id'")

    to_user_id = params.get('to_user_id')
    round_robin = params.get('round_robin', False)
    team_id = params.get('team_id')

    lead_status = params.get('lead_status')
    new_status = params.get('new_status')

    qs = Lead.objects.filter(assigned_to_id=from_user_id)
    if lead_status:
        qs = qs.filter(status=lead_status)

    leads = list(qs)
    if not leads:
        return f"No leads found for user_id={from_user_id} with status={lead_status or 'any'}."

    if round_robin and team_id:
        try:
            team = WorkspaceTeam.objects.get(id=team_id)
            members = list(team.members.filter(is_active=True).order_by('id'))
            if not members:
                return "No active team members for round-robin"

            member_count = len(members)
            for i, lead in enumerate(leads):
                target = members[i % member_count]
                lead.assigned_to = target
                if new_status:
                    lead.status = new_status
                    lead.status_changed_at = timezone.now()
                lead.save(update_fields=['assigned_to', 'status', 'status_changed_at'] if new_status else ['assigned_to'])
            return f"Reassigned {len(leads)} leads via round-robin to team id={team_id}"
        except WorkspaceTeam.DoesNotExist:
            raise ValueError(f"Team id={team_id} not found")
    elif to_user_id:
        try:
            target_user = User.objects.get(id=to_user_id)
            for lead in leads:
                lead.assigned_to = target_user
                if new_status:
                    lead.status = new_status
                    lead.status_changed_at = timezone.now()
                lead.save(update_fields=['assigned_to', 'status', 'status_changed_at'] if new_status else ['assigned_to'])
            return f"Reassigned {len(leads)} leads to user id={to_user_id}"
        except User.DoesNotExist:
            raise ValueError(f"User id={to_user_id} not found")
    else:
        raise ValueError("reassign_employee_leads requires 'to_user_id' or 'round_robin'+'team_id'")


def _action_send_email(params, obj, context) -> str:
    """Send an email to the lead (or an explicit address). Supports {{field}}
    placeholders in subject/body."""
    from leads.models import Lead
    to = params.get('to')
    if not to and isinstance(obj, Lead):
        to = obj.email
    if not to:
        raise ValueError("send_email requires a 'to' address or a lead with an email")

    subject = _render(params.get('subject', 'An update for you'), obj)
    body = _render(params.get('body', ''), obj)

    # Goes through the CRM's configured email account (Settings → Email
    # Integration) and is recorded in the email outbox.
    from messaging.email import send_and_log
    log = send_and_log(
        to=to, subject=subject, body=body,
        lead=obj if isinstance(obj, Lead) else None,
        cc=params.get('cc'), kind='automation',
    )
    if log.status != 'sent':
        raise ValueError(log.error or 'Email send failed')
    return f"Email sent to {to}"


def _action_escalate_to_manager(params, obj, context) -> str:
    """Reassign the lead to its team manager (or any manager) and notify them."""
    from leads.models import Lead
    if not isinstance(obj, Lead):
        raise ValueError("escalate_to_manager only works on Lead objects")

    manager = None
    agent = obj.assigned_to
    if agent is not None and agent.team_id and agent.team and agent.team.manager:
        manager = agent.team.manager
    if manager is None:
        from users.models import WorkspaceTeam
        team = WorkspaceTeam.objects.exclude(manager__isnull=True).first()
        if team:
            manager = team.manager
    if manager is None:
        raise ValueError("No manager available to escalate to")

    reassign = params.get('reassign', True)
    if reassign:
        obj.assigned_to = manager
        obj.save(update_fields=['assigned_to'])

    try:
        from ai_manager.models import Notification
        Notification.objects.create(
            user=manager,
            title='🚨 Lead escalated',
            message=_render(params.get('message') or f"Lead {obj.first_name} {obj.last_name} needs attention.", obj),
        )
    except Exception:
        pass

    return f"Escalated to {manager.first_name} {manager.last_name}" + (" (reassigned)" if reassign else "")


def _action_send_whatsapp(params, obj, context) -> str:
    """Send a WhatsApp message (text or approved template) to the lead via the
    Cloud API. Text and template variables support {{field}} placeholders."""
    from leads.models import Lead
    if not isinstance(obj, Lead):
        raise ValueError("send_whatsapp only works on Lead objects")
    to = params.get('to') or obj.phone
    if not to:
        raise ValueError("Lead has no phone number")

    from messaging.whatsapp import send_and_log
    kind = params.get('mode') or params.get('kind') or 'text'

    if kind == 'template':
        template_name = params.get('template_name')
        if not template_name:
            raise ValueError("send_whatsapp template requires 'template_name'")
        variables = [_render(str(v), obj) for v in (params.get('variables') or [])]
        msg = send_and_log(
            to=to, lead=obj, kind='template', template_name=template_name,
            language=params.get('language', 'en_US'), variables=variables,
        )
    else:
        msg = send_and_log(to=to, lead=obj, kind='text', text=_render(params.get('text', ''), obj))

    if msg.status == 'failed':
        raise ValueError(msg.error or 'WhatsApp send failed')
    return f"WhatsApp {kind} sent to {to}"


def _action_notify_assignee(params, obj, context) -> str:
    """Send an in-app notification to the lead's current owner."""
    from leads.models import Lead
    if not isinstance(obj, Lead):
        raise ValueError("notify_assignee only works on Lead objects")
    if not obj.assigned_to:
        return "Lead has no assignee to notify"
    try:
        from ai_manager.models import Notification
        Notification.objects.create(
            user=obj.assigned_to,
            title='🔔 Lead update',
            message=_render(params.get('message', 'One of your leads needs a look.'), obj),
        )
        return f"Notified {obj.assigned_to.first_name}"
    except Exception as e:
        raise ValueError(f"Notification failed: {e}")


# ── Utilities ─────────────────────────────────────────────────────────────────

def _snapshot(obj) -> dict:
    """Create a JSON-safe snapshot of a model instance.

    Handles Decimals, dates, and FileFields (and any other non-primitive),
    so logging never crashes on un-serializable field values.
    """
    data = {}
    for field in obj._meta.get_fields():
        if not hasattr(field, 'attname'):
            continue
        try:
            val = getattr(obj, field.attname)
            if isinstance(val, Decimal):
                val = float(val)
            elif hasattr(val, 'isoformat'):  # date / datetime
                val = val.isoformat()
            elif val is not None and not isinstance(val, (str, int, float, bool, list, dict)):
                # FieldFile, UUID, model instances, etc. -> fall back to a name/string.
                val = getattr(val, 'name', None)
                if val is None:
                    val = str(getattr(obj, field.attname))
            data[field.attname] = val
        except Exception:
            pass
    return data
