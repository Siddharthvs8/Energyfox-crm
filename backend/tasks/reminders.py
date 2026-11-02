"""Task reminders: a notification and a popup for the person a task is assigned
to, before it falls due and once it is overdue.

    * due      — once, `task_reminder_minutes` before the task falls due.
    * overdue  — when it is past due and still not done, and again every
                 `task_overdue_repeat_minutes` until it is (once, if that is 0).

Both intervals are the admins' to set, in Settings → Automation
(ai_manager.ManagerConfig).

They are worked out for a person when their screen asks for its popups
(ai_manager.views.PopupRemindersView, polled every minute while they are signed
in), the same way the target popups are: there is no scheduler to keep running,
and someone who was away finds theirs when they come back. Each reminder is
claimed with a conditional update before it is sent, so two tabs polling at the
same moment send it once.
"""
from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import Task

DAY = 24 * 60


def due_moment(task):
    """When a task falls due: its due time on its due day; for a task with only
    a date, the end of that day, which is when the task list starts calling it
    overdue."""
    if task.due_date is None:
        return None
    zone = timezone.get_current_timezone()
    if task.due_time:
        return timezone.make_aware(datetime.combine(task.due_date, task.due_time), zone)
    return timezone.make_aware(datetime.combine(task.due_date + timedelta(days=1), time.min), zone)


def remind_from(task, lead_minutes):
    """When the before-it-is-due reminder may go out.

    A task with a time is reminded `lead_minutes` before it. One with only a
    date has no moment to count back from, so whole days are counted instead:
    on the morning it is due when the lead is under a day, a day early for a
    day or more, and so on — never at eleven at night because the end of the
    day happens to be an hour away.
    """
    if task.due_time:
        return due_moment(task) - timedelta(minutes=lead_minutes)
    zone = timezone.get_current_timezone()
    first_day = task.due_date - timedelta(days=lead_minutes // DAY)
    return timezone.make_aware(datetime.combine(first_day, time.min), zone)


def _when(task, today):
    if task.due_date == today:
        day = 'today'
    elif task.due_date == today + timedelta(days=1):
        day = 'tomorrow'
    elif task.due_date == today - timedelta(days=1):
        day = 'yesterday'
    else:
        day = f'on {task.due_date.day} {task.due_date.strftime("%b")}'
    if task.due_time:
        return f'{day} at {task.due_time.strftime("%I:%M %p").lstrip("0")}'
    return day


def _about(task):
    """The task as a reminder names it: its title, and the customer it is for."""
    who = ' '.join(p for p in (task.lead.first_name, task.lead.last_name) if p) if task.lead else ''
    return f'"{task.title}" for {who}' if who else f'"{task.title}"'


def _claim(task, field, expected, now):
    """Mark a reminder sent unless someone else just did; True if this call did."""
    match = {f'{field}__isnull': True} if expected is None else {field: expected}
    return Task.objects.filter(pk=task.pk, **match).update(**{field: now}) == 1


def send_due_reminders(user, now=None):
    """Send the due and overdue reminders this person has coming. Returns how
    many were sent."""
    from ai_manager.engine import get_or_create_config
    from ai_manager.models import Notification

    config = get_or_create_config()
    lead_minutes = config.task_reminder_minutes or 0
    repeat_minutes = config.task_overdue_repeat_minutes or 0
    now = now or timezone.now()
    today = timezone.localtime(now).date()

    sent = 0
    # Nothing due later than this can need a reminder yet.
    horizon = today + timedelta(days=lead_minutes // DAY + 1)
    tasks = (Task.objects.filter(assignee=user, due_date__isnull=False, due_date__lte=horizon)
             .exclude(status='done').select_related('lead'))
    for task in tasks:
        due = due_moment(task)
        if now >= due:
            last = task.overdue_reminded_at
            if last is not None and not (repeat_minutes and now - last >= timedelta(minutes=repeat_minutes)):
                continue
            if not _claim(task, 'overdue_reminded_at', last, now):
                continue
            Notification.objects.create(
                user=user, notification_type='task_overdue', is_popup=True,
                title='⚠️ Task overdue',
                message=f'{_about(task)} was due {_when(task, today)} and is not done yet.',
                extra_data={'task_id': task.id, 'kind': 'overdue', 'due': due.isoformat()})
            sent += 1
        elif lead_minutes and task.reminded_at is None and now >= remind_from(task, lead_minutes):
            # A task already overdue skips this one: it gets the overdue
            # reminder instead, rather than a "due soon" that is too late.
            if not _claim(task, 'reminded_at', None, now):
                continue
            Notification.objects.create(
                user=user, notification_type='task_due', is_popup=True,
                title='⏰ Task due soon',
                message=f'{_about(task)} is due {_when(task, today)}.',
                extra_data={'task_id': task.id, 'kind': 'due', 'due': due.isoformat()})
            sent += 1
    return sent
