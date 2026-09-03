"""
AI Manager Intelligence Engine
- Lead auto-assignment (round robin / workload balanced)
- Monthly-to-daily target splitting (excluding holidays)
- Progress checking
- Reminder/notification generation
"""

import calendar
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone


def get_or_create_config():
    """Get the singleton ManagerConfig for the current tenant."""
    from .models import ManagerConfig
    config, _ = ManagerConfig.objects.get_or_create(pk=1)
    return config


# ─── Lead Auto-Assignment ─────────────────────────────────────────────────────

def assign_lead(lead):
    """
    Assign a lead to the best available agent based on the configured strategy.
    Returns the assigned user or None if manual mode / no agents available.
    """
    config = get_or_create_config()

    if not config.auto_assign_enabled or config.assignment_strategy == 'manual':
        return None

    from users.models import User
    # Only assign to active, non-staff, non-manager agents
    agents = User.objects.filter(
        is_active=True, is_staff=False, is_manager=False
    ).order_by('id')

    if not agents.exists():
        # Fallback 1: assign to managers if no agents
        agents = User.objects.filter(
            is_active=True, is_manager=True
        ).order_by('id')

    if not agents.exists():
        # Fallback 2: assign to any active user (staff / superadmin)
        agents = User.objects.filter(is_active=True).order_by('id')

    if not agents.exists():
        return None

    if config.assignment_strategy == 'round_robin':
        assigned_user = _round_robin_assign(agents)
    else:  # workload_balanced
        assigned_user = _workload_balanced_assign(agents)

    if assigned_user:
        lead.assigned_to = assigned_user
        lead.save(update_fields=['assigned_to'])

    return assigned_user


def _round_robin_assign(agents):
    """Assign to the agent who received a lead least recently."""
    from leads.models import Lead
    from leads.scopes import closed_deals, received_value

    agent_list = list(agents)
    # Find the agent who was last assigned a lead the longest time ago
    last_assigned = []
    for agent in agent_list:
        last_lead = Lead.objects.filter(assigned_to=agent).order_by('-created_at').first()
        last_time = last_lead.created_at if last_lead else datetime.min.replace(tzinfo=dt_timezone.utc)
        last_assigned.append((agent, last_time))

    # Sort by last assignment time (ascending) — agent who hasn't received one recently goes first
    last_assigned.sort(key=lambda x: x[1])
    return last_assigned[0][0] if last_assigned else None


def _workload_balanced_assign(agents):
    """Assign to the agent with the fewest active (non-terminal) leads."""
    from leads.models import Lead
    from leads.scopes import closed_deals, received_value
    from django.db.models import Count, Q

    terminal_statuses = ['converted', 'not_interested']

    agent_workloads = []
    for agent in agents:
        active_count = Lead.objects.filter(
            assigned_to=agent
        ).exclude(
            status__in=terminal_statuses
        ).count()
        agent_workloads.append((agent, active_count))

    agent_workloads.sort(key=lambda x: x[1])
    return agent_workloads[0][0] if agent_workloads else None


# ─── Daily Target Generation ──────────────────────────────────────────────────

def generate_daily_targets(monthly_target):
    """
    Generate daily targets from a monthly target, excluding explicit holidays.
    Distributes the remaining monthly target based on intelligent historical models
    or an industry fallback curve.
    Dynamically adjusts future targets based on past performance for the current month.
    """
    from .models import DailyTarget, Holiday
    from leads.models import Lead
    from leads.scopes import closed_deals, received_value
    from django.db.models import Sum, Count
    from django.db.models.functions import ExtractWeekDay
    from django.utils import timezone
    from decimal import Decimal, ROUND_HALF_UP
    import calendar
    from datetime import date, timedelta

    today = timezone.localdate()
    year = monthly_target.year
    month = monthly_target.month

    # Get all days in the month
    num_days = calendar.monthrange(year, month)[1]
    all_days = [date(year, month, d) for d in range(1, num_days + 1)]

    # Get holiday dates for this month
    holiday_dates = set(
        Holiday.objects.filter(date__year=year, date__month=month).values_list('date', flat=True)
    )

    if today.month == month and today.year == year:
        # Dynamic Adjustment Mode for the current month
        # 1. Delete future auto-generated targets (from today onwards)
        DailyTarget.objects.filter(monthly_target=monthly_target, is_manual=False, date__gte=today).delete()

        # 2. Get past actuals (up to yesterday)
        yesterday = today - timedelta(days=1)
        # Won means closed — in accounts with money received. A target is met
        # by business landed, not by leads marked converted. One definition,
        # shared: leads.scopes.CLOSED_DEAL_FILTER.
        actual_past_qs = closed_deals(Lead.objects.filter(
            assigned_to=monthly_target.agent,
            status_changed_at__year=year,
            status_changed_at__month=month,
            status_changed_at__date__lte=yesterday,
        ))
        actual_leads_past = actual_past_qs.count()
        actual_amount_past = actual_past_qs.aggregate(t=Sum(received_value()))['t'] or Decimal('0.00')

        # 3. Get manual targets from today onwards
        manual_targets = list(DailyTarget.objects.filter(monthly_target=monthly_target, is_manual=True, date__gte=today))
        manual_dates = {t.date for t in manual_targets}
        manual_leads = sum(t.target_leads for t in manual_targets)
        manual_amount = sum(t.target_amount for t in manual_targets)
        manual_dialed_calls = sum(t.target_dialed_calls for t in manual_targets)
        manual_call_time = sum(t.target_call_time for t in manual_targets)

        # 4. Calculate Remaining to Distribute
        remaining_leads = max(0, monthly_target.target_leads - actual_leads_past - manual_leads)
        remaining_amount = max(Decimal('0.00'), Decimal(str(monthly_target.target_amount)) - Decimal(str(actual_amount_past)) - Decimal(str(manual_amount)))
        
        actual_dialed_calls_past = sum(t.achieved_dialed_calls for t in DailyTarget.objects.filter(monthly_target=monthly_target, date__lte=yesterday))
        actual_call_time_past = sum(t.achieved_call_time for t in DailyTarget.objects.filter(monthly_target=monthly_target, date__lte=yesterday))
        remaining_dialed_calls = max(0, monthly_target.target_dialed_calls - actual_dialed_calls_past - manual_dialed_calls)
        remaining_call_time = max(0, monthly_target.target_call_time - actual_call_time_past - manual_call_time)

        # 5. Determine auto working days (from today onwards)
        auto_working_days = [d for d in all_days if d >= today and d not in holiday_dates and d not in manual_dates]

    elif today < date(year, month, 1):
        # Future month mode: generate the whole month normally
        DailyTarget.objects.filter(monthly_target=monthly_target, is_manual=False).delete()
        
        manual_targets = list(DailyTarget.objects.filter(monthly_target=monthly_target, is_manual=True))
        manual_dates = {t.date for t in manual_targets}
        manual_leads = sum(t.target_leads for t in manual_targets)
        manual_amount = sum(t.target_amount for t in manual_targets)
        manual_dialed_calls = sum(t.target_dialed_calls for t in manual_targets)
        manual_call_time = sum(t.target_call_time for t in manual_targets)

        remaining_leads = max(0, monthly_target.target_leads - manual_leads)
        remaining_amount = max(Decimal('0.00'), Decimal(str(monthly_target.target_amount)) - Decimal(str(manual_amount)))
        remaining_dialed_calls = max(0, monthly_target.target_dialed_calls - manual_dialed_calls)
        remaining_call_time = max(0, monthly_target.target_call_time - manual_call_time)
        
        auto_working_days = [d for d in all_days if d not in holiday_dates and d not in manual_dates]
    else:
        # Past month mode: do not adjust historical targets
        return []

    if not auto_working_days:
        return []

    # 6. Extract historical performance to weight weekdays
    # Look back 6 months for historical conversions
    six_months_ago = timezone.now() - timedelta(days=180)
    agent = monthly_target.agent
    
    historical_qs = closed_deals(Lead.objects.filter(
        assigned_to=agent,
        status_changed_at__gte=six_months_ago,
    )).annotate(
        weekday=ExtractWeekDay('status_changed_at')
    ).values('weekday').annotate(
        conversions=Count('id')
    )

    total_history = sum(w['conversions'] for w in historical_qs)
    has_enough_history = (total_history >= 10)
    
    # Weights for each weekday: 0=Monday, 6=Sunday
    default_curve = {
        0: 0.18, # Mon
        1: 0.18, # Tue
        2: 0.18, # Wed
        3: 0.16, # Thu
        4: 0.15, # Fri
        5: 0.10, # Sat
        6: 0.05  # Sun
    }
    
    weights = {}
    if has_enough_history:
        # Django ExtractWeekDay: 1=Sunday, 2=Monday, ..., 7=Saturday
        # We'll map them to datetime weekday (0=Monday, 6=Sunday)
        for item in historical_qs:
            dj_weekday = item['weekday'] # 1=Sun, 2=Mon
            py_weekday = (dj_weekday + 5) % 7
            weights[py_weekday] = item['conversions'] / total_history
            
        # Fill missing days with small baseline
        for d in range(7):
            if d not in weights:
                weights[d] = 0.01
        
        # Normalize
        total_w = sum(weights.values())
        weights = {k: v/total_w for k, v in weights.items()}
    else:
        weights = default_curve

    # Get sum of weights for the available working days in the month
    sum_available_weights = sum(weights[d.weekday()] for d in auto_working_days)

    if sum_available_weights == 0:
        sum_available_weights = 1 # Avoid division by zero
        
    normalized_day_weights = [ (weights[d.weekday()] / sum_available_weights) for d in auto_working_days ]

    # Fetch all connected call logs for this agent in this month
    from calls.models import CallLog
    connected_calls = CallLog.objects.filter(
        user=agent,
        created_at__year=year,
        created_at__month=month,
        outcome='connected'
    )
    
    # Group by date using local time
    call_metrics_by_date = {}
    for call in connected_calls:
        call_date = timezone.localtime(call.created_at).date()
        if call_date not in call_metrics_by_date:
            call_metrics_by_date[call_date] = {'count': 0, 'seconds': 0}
        call_metrics_by_date[call_date]['count'] += 1
        call_metrics_by_date[call_date]['seconds'] += (call.duration_seconds or 0)

    daily_targets = []
    allocated_leads = 0
    allocated_amount = Decimal('0.00')
    allocated_dialed_calls = 0
    allocated_call_time = 0

    # Distribute the base allocations
    for i, day in enumerate(auto_working_days):
        day_weight = normalized_day_weights[i]
        
        day_leads = int(round(remaining_leads * day_weight))
        day_amount = (remaining_amount * Decimal(str(day_weight))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        day_dialed_calls = int(round(remaining_dialed_calls * day_weight))
        day_call_time = int(round(remaining_call_time * day_weight))
        
        allocated_leads += day_leads
        allocated_amount += day_amount
        allocated_dialed_calls += day_dialed_calls
        allocated_call_time += day_call_time
        
        # Look up achievements from grouped dict
        metrics = call_metrics_by_date.get(day, {'count': 0, 'seconds': 0})
        day_achieved_calls = metrics['count']
        day_achieved_minutes = int(round(metrics['seconds'] / 60.0))

        dt = DailyTarget(
            monthly_target=monthly_target,
            agent=agent,
            date=day,
            target_leads=day_leads,
            target_amount=day_amount,
            target_dialed_calls=day_dialed_calls,
            target_call_time=day_call_time,
            achieved_dialed_calls=day_achieved_calls,
            achieved_call_time=day_achieved_minutes,
            is_manual=False
        )
        daily_targets.append(dt)

    # 7. Adjust rounding residuals on the highest weighted days
    if daily_targets:
        diff_leads = remaining_leads - allocated_leads
        diff_amount = remaining_amount - allocated_amount
        diff_dialed_calls = remaining_dialed_calls - allocated_dialed_calls
        diff_call_time = remaining_call_time - allocated_call_time
        
        # Sort targets by their assigned amount to give leftovers to the "best" days
        targets_sorted = sorted(daily_targets, key=lambda t: t.target_amount, reverse=True)
        
        if diff_leads != 0 and targets_sorted:
            direction = 1 if diff_leads > 0 else -1
            idx = 0
            while diff_leads != 0:
                targets_sorted[idx % len(targets_sorted)].target_leads += direction
                diff_leads -= direction
                idx += 1
                
        if diff_amount != 0 and targets_sorted:
            targets_sorted[0].target_amount += diff_amount
            
        if diff_dialed_calls != 0 and targets_sorted:
            direction = 1 if diff_dialed_calls > 0 else -1
            idx = 0
            while diff_dialed_calls != 0:
                targets_sorted[idx % len(targets_sorted)].target_dialed_calls += direction
                diff_dialed_calls -= direction
                idx += 1
                
        if diff_call_time != 0 and targets_sorted:
            direction = 1 if diff_call_time > 0 else -1
            idx = 0
            while diff_call_time != 0:
                targets_sorted[idx % len(targets_sorted)].target_call_time += direction
                diff_call_time -= direction
                idx += 1

    DailyTarget.objects.bulk_create(daily_targets)
    return daily_targets


def regenerate_all_daily_targets_for_month(month, year):
    """Regenerate daily targets for ALL monthly targets in a given month/year."""
    from .models import MonthlyTarget
    targets = MonthlyTarget.objects.filter(month=month, year=year)
    for mt in targets:
        generate_daily_targets(mt)


def sync_daily_targets(month, year):
    """Auto-generate daily targets if missing, and adjust future targets for current month."""
    from .models import MonthlyTarget, DailyTarget
    from django.utils import timezone
    targets = MonthlyTarget.objects.filter(month=month, year=year)
    today = timezone.localdate()
    for mt in targets:
        if today.month == month and today.year == year:
            generate_daily_targets(mt)
        elif not DailyTarget.objects.filter(monthly_target=mt).exists():
            generate_daily_targets(mt)


# ─── Progress Checking ─────────────────────────────────────────────────────────

def check_daily_progress(agent, check_date=None):
    """
    Returns the agent's progress towards today's daily target.
    Returns dict with target info and actual counts.
    """
    from .models import DailyTarget
    from leads.models import Lead
    from leads.scopes import closed_deals, received_value

    if check_date is None:
        check_date = timezone.localdate()

    try:
        daily_target = DailyTarget.objects.get(agent=agent, date=check_date)
    except DailyTarget.DoesNotExist:
        return {
            'has_target': False,
            'date': str(check_date),
        }

    # Count leads enrolled today for this agent
    enrolled_today = closed_deals(Lead.objects.filter(
        assigned_to=agent,
        status_changed_at__date=check_date,
    )).count()

    # Revenue from enrolled leads today
    from django.db.models import Sum
    revenue_today = closed_deals(Lead.objects.filter(
        assigned_to=agent,
        status_changed_at__date=check_date,
    )).aggregate(total=Sum(received_value()))['total'] or 0

    leads_pct = (enrolled_today / daily_target.target_leads * 100) if daily_target.target_leads > 0 else 0
    amount_pct = (float(revenue_today) / float(daily_target.target_amount) * 100) if daily_target.target_amount > 0 else 0
    dialed_calls_pct = (daily_target.achieved_dialed_calls / daily_target.target_dialed_calls * 100) if daily_target.target_dialed_calls > 0 else 0
    call_time_pct = (daily_target.achieved_call_time / daily_target.target_call_time * 100) if daily_target.target_call_time > 0 else 0

    return {
        'has_target': True,
        'id': daily_target.id,
        'date': str(check_date),
        'target_leads': daily_target.target_leads,
        'target_amount': float(daily_target.target_amount),
        'target_dialed_calls': daily_target.target_dialed_calls,
        'target_call_time': daily_target.target_call_time,
        'actual_leads': enrolled_today,
        'actual_amount': float(revenue_today),
        'achieved_dialed_calls': daily_target.achieved_dialed_calls,
        'achieved_call_time': daily_target.achieved_call_time,
        'leads_pct': round(leads_pct, 1),
        'amount_pct': round(amount_pct, 1),
        'dialed_calls_pct': round(dialed_calls_pct, 1),
        'call_time_pct': round(call_time_pct, 1),
        'status': daily_target.status,
        'is_manual': daily_target.is_manual,
    }


def check_monthly_progress(agent, month=None, year=None):
    """Returns agent's progress towards their monthly target."""
    from .models import MonthlyTarget
    from leads.models import Lead
    from leads.scopes import closed_deals, received_value
    from django.db.models import Sum

    now = timezone.now()
    if month is None:
        month = now.month
    if year is None:
        year = now.year

    try:
        mt = MonthlyTarget.objects.get(agent=agent, month=month, year=year)
    except MonthlyTarget.DoesNotExist:
        return {'has_target': False, 'month': month, 'year': year}

    # Enrolled this month
    enrolled = closed_deals(Lead.objects.filter(
        assigned_to=agent,
        status_changed_at__year=year,
        status_changed_at__month=month,
    ))
    enrolled_count = enrolled.count()
    enrolled_revenue = enrolled.aggregate(total=Sum(received_value()))['total'] or 0

    leads_pct = (enrolled_count / mt.target_leads * 100) if mt.target_leads > 0 else 0
    amount_pct = (float(enrolled_revenue) / float(mt.target_amount) * 100) if mt.target_amount > 0 else 0

    # Also calculate achieved dialed calls and call time for the month
    from .models import DailyTarget
    dt_qs = DailyTarget.objects.filter(monthly_target=mt)
    achieved_dialed_calls = sum(dt.achieved_dialed_calls for dt in dt_qs)
    achieved_call_time = sum(dt.achieved_call_time for dt in dt_qs)

    dialed_calls_pct = (achieved_dialed_calls / mt.target_dialed_calls * 100) if mt.target_dialed_calls > 0 else 0
    call_time_pct = (achieved_call_time / mt.target_call_time * 100) if mt.target_call_time > 0 else 0

    return {
        'has_target': True,
        'month': month,
        'year': year,
        'target_leads': mt.target_leads,
        'target_amount': float(mt.target_amount),
        'target_dialed_calls': mt.target_dialed_calls,
        'target_call_time': mt.target_call_time,
        'actual_leads': enrolled_count,
        'actual_amount': float(enrolled_revenue),
        'achieved_dialed_calls': achieved_dialed_calls,
        'achieved_call_time': achieved_call_time,
        'leads_pct': round(leads_pct, 1),
        'amount_pct': round(amount_pct, 1),
        'dialed_calls_pct': round(dialed_calls_pct, 1),
        'call_time_pct': round(call_time_pct, 1),
    }


# ─── Reminder / Notification Generation ───────────────────────────────────────

def generate_daily_reminders():
    """
    Generate daily target reminder notifications for all agents
    who have a target for today.
    """
    from .models import DailyTarget, Notification
    from users.models import User

    today = timezone.localdate()
    daily_targets = DailyTarget.objects.filter(date=today)

    created = []
    for dt in daily_targets:
        # Don't create duplicate reminders
        already_exists = Notification.objects.filter(
            user=dt.agent,
            notification_type='daily_target',
            created_at__date=today
        ).exists()

        if not already_exists:
            progress = check_daily_progress(dt.agent, today)
            notif = Notification.objects.create(
                user=dt.agent,
                title="📋 Daily Target Reminder",
                message=(
                    f"Today's target: {dt.target_leads} leads, "
                    f"₹{dt.target_amount:,.0f} revenue. "
                    f"Progress: {progress.get('actual_leads', 0)} leads, "
                    f"₹{progress.get('actual_amount', 0):,.0f} revenue."
                ),
                notification_type='daily_target',
            )
            created.append(notif)

    return created


def generate_monthly_summary_notifications(month=None, year=None):
    """Generate monthly progress notifications for all agents with targets."""
    from .models import MonthlyTarget, Notification

    now = timezone.now()
    if month is None:
        month = now.month
    if year is None:
        year = now.year

    targets = MonthlyTarget.objects.filter(month=month, year=year)
    created = []

    for mt in targets:
        progress = check_monthly_progress(mt.agent, month, year)
        notif = Notification.objects.create(
            user=mt.agent,
            title="📊 Monthly Target Update",
            message=(
                f"Month {month}/{year} progress: "
                f"{progress.get('actual_leads', 0)}/{mt.target_leads} leads "
                f"({progress.get('leads_pct', 0)}%), "
                f"₹{progress.get('actual_amount', 0):,.0f}/₹{float(mt.target_amount):,.0f} revenue "
                f"({progress.get('amount_pct', 0)}%)."
            ),
            notification_type='monthly_target',
        )
        created.append(notif)

    return created


def notify_meeting(meeting):
    """Create meeting notifications for all attendees."""
    from .models import Notification

    created = []
    for attendee in meeting.attendees.all():
        notif = Notification.objects.create(
            user=attendee,
            title="📅 Meeting Scheduled",
            message=(
                f"\"{meeting.title}\" scheduled for "
                f"{timezone.localtime(meeting.scheduled_at).strftime('%b %d, %Y %I:%M %p')} "
                f"({meeting.duration_minutes} min)."
            ),
            notification_type='meeting',
        )
        created.append(notif)

    return created
