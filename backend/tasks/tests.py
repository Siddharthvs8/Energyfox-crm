"""Task reminders: a notification and a popup before a task falls due, and while
it is overdue, at intervals the admins set."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from ai_manager.engine import get_or_create_config
from ai_manager.models import Notification
from users.models import User

from .models import Task
from .reminders import send_due_reminders

IST = ZoneInfo('Asia/Kolkata')


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456')
    u.role = role
    u.save()
    return u


def at(day, hour=0, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)


DUE = date(2026, 11, 5)


class TaskReminderTests(TestCase):

    def setUp(self):
        self.user = mk('tr_staff', 'documentation_staff')
        self.config = get_or_create_config()          # 60 minutes before; daily while overdue

    def configure(self, before=None, repeat=None):
        if before is not None:
            self.config.task_reminder_minutes = before
        if repeat is not None:
            self.config.task_overdue_repeat_minutes = repeat
        self.config.save()

    def task(self, **fields):
        fields.setdefault('title', 'Call back')
        fields.setdefault('assignee', self.user)
        fields.setdefault('due_date', DUE)
        return Task.objects.create(**fields)

    def sent(self, when):
        """What a poll at `when` sent: [(type, message)]."""
        before = set(Notification.objects.values_list('id', flat=True))
        send_due_reminders(self.user, when)
        return [(n.notification_type, n.message)
                for n in Notification.objects.exclude(id__in=before).order_by('id')]

    # ── Before it falls due ──
    def test_reminded_once_before_a_timed_task_falls_due(self):
        self.task(due_time=time(15, 0))
        self.assertEqual(self.sent(at(DUE, 13, 59)), [])
        self.assertEqual(self.sent(at(DUE, 14, 0)), [('task_due', '"Call back" is due today at 3:00 PM.')])
        self.assertEqual(self.sent(at(DUE, 14, 30)), [], 'once is enough')
        n = Notification.objects.get()
        self.assertTrue(n.is_popup)
        self.assertEqual(n.title, '⏰ Task due soon')

    def test_it_names_the_customer(self):
        from leads.models import Lead
        lead = Lead.objects.create(first_name='Asha', last_name='Nair')
        self.task(due_time=time(15, 0), lead=lead)
        self.assertEqual(self.sent(at(DUE, 14, 0)),
                         [('task_due', '"Call back" for Asha Nair is due today at 3:00 PM.')])

    def test_the_early_reminder_can_be_turned_off(self):
        self.configure(before=0)
        self.task(due_time=time(15, 0))
        self.assertEqual(self.sent(at(DUE, 14, 59)), [])
        self.assertEqual([k for k, _ in self.sent(at(DUE, 15, 0))], ['task_overdue'])

    # ── Once it is overdue ──
    def test_overdue_when_it_passes_and_again_every_interval(self):
        self.task(due_time=time(15, 0))
        self.sent(at(DUE, 14, 0))
        self.assertEqual(self.sent(at(DUE, 15, 0)),
                         [('task_overdue', '"Call back" was due today at 3:00 PM and is not done yet.')])
        self.assertEqual(self.sent(at(DUE, 23, 0)), [])
        self.assertEqual(self.sent(at(DUE + timedelta(days=1), 15, 0)),
                         [('task_overdue', '"Call back" was due yesterday at 3:00 PM and is not done yet.')])

    def test_overdue_only_once_when_the_interval_is_nothing(self):
        self.configure(repeat=0)
        self.task(due_time=time(15, 0))
        self.assertEqual(len(self.sent(at(DUE, 16, 0))), 1)
        self.assertEqual(self.sent(at(DUE + timedelta(days=3), 16, 0)), [])

    def test_a_late_comer_gets_the_overdue_one_not_a_due_soon(self):
        task = self.task(due_time=time(15, 0))
        self.assertEqual([k for k, _ in self.sent(at(DUE, 18, 0))], ['task_overdue'])
        task.refresh_from_db()
        self.assertIsNone(task.reminded_at)

    # ── A task with only a date ──
    def test_a_dated_task_is_reminded_on_the_morning_it_is_due(self):
        self.task()
        self.assertEqual(self.sent(at(DUE - timedelta(days=1), 23, 30)), [], 'not the night before')
        self.assertEqual(self.sent(at(DUE, 9, 0)), [('task_due', '"Call back" is due today.')])
        self.assertEqual(self.sent(at(DUE, 23, 59)), [])
        self.assertEqual(self.sent(at(DUE + timedelta(days=1), 0, 0)),
                         [('task_overdue', '"Call back" was due yesterday and is not done yet.')])

    def test_a_lead_of_days_counts_whole_days(self):
        self.configure(before=24 * 60)
        self.task()
        self.assertEqual(self.sent(at(DUE - timedelta(days=2), 18, 0)), [])
        self.assertEqual(self.sent(at(DUE - timedelta(days=1), 8, 0)), [('task_due', '"Call back" is due tomorrow.')])

    # ── Who is not reminded ──
    def test_done_undated_and_other_peoples_tasks_are_left_alone(self):
        self.task(due_time=time(15, 0), status='done')
        self.task(due_date=None)
        self.task(due_time=time(15, 0), assignee=mk('tr_other', 'tele_caller'))
        self.task(due_time=time(15, 0), assignee=None)
        self.assertEqual(self.sent(at(DUE, 16, 0)), [])

    # ── Changing the task starts over ──
    def test_rescheduling_reassigning_or_reopening_starts_the_reminders_over(self):
        task = self.task(due_time=time(15, 0))
        self.sent(at(DUE, 16, 0))

        def patch(**data):
            r = self.client.patch(f'/api/tasks/{task.id}/', data=data, content_type='application/json',
                                  HTTP_AUTHORIZATION=token_for(self.user))
            self.assertEqual(r.status_code, 200, r.content[:300])
            task.refresh_from_db()

        patch(title='Call back about the subsidy')
        self.assertIsNotNone(task.overdue_reminded_at, 'an unrelated edit keeps them')
        patch(due_date='2026-11-08')
        self.assertIsNone(task.overdue_reminded_at)
        self.assertEqual(len(self.sent(at(date(2026, 11, 8), 14, 0))), 1)
        patch(status='done')
        patch(status='todo')
        self.assertIsNone(task.reminded_at, 'reopened')

    # ── Delivered with the other popups ──
    def test_the_popup_poll_delivers_them(self):
        soon = timezone.localtime() + timedelta(minutes=30)
        task = self.task(due_date=soon.date(), due_time=soon.time().replace(second=0, microsecond=0))
        r = self.client.get('/api/ai-manager/popups/', HTTP_AUTHORIZATION=token_for(self.user))
        self.assertEqual(r.status_code, 200, r.content[:300])
        popups = [p for p in r.json() if p['notification_type'] == 'task_due']
        self.assertEqual(len(popups), 1)
        self.assertEqual(popups[0]['extra_data']['task_id'], task.id)
        again = self.client.get('/api/ai-manager/popups/', HTTP_AUTHORIZATION=token_for(self.user)).json()
        self.assertEqual([p for p in again if p['notification_type'] == 'task_due'], [])
        # It stays in the notification list after the popup has been shown.
        self.assertTrue(Notification.objects.filter(user=self.user, notification_type='task_due').exists())


class TaskReminderSettingsTests(TestCase):
    URL = '/api/ai-manager/meeting-config/'

    def setUp(self):
        self.admin = mk('trs_admin', 'admin')

    def patch(self, user, **data):
        return self.client.patch(self.URL, data=data, content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(user))

    def test_admins_set_the_intervals(self):
        r = self.patch(self.admin, task_reminder_minutes=120, task_overdue_repeat_minutes=0)
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual((r.json()['task_reminder_minutes'], r.json()['task_overdue_repeat_minutes']), (120, 0))
        got = self.client.get(self.URL, HTTP_AUTHORIZATION=token_for(self.admin)).json()
        self.assertEqual((got['task_reminder_minutes'], got['task_overdue_repeat_minutes']), (120, 0))

    def test_nobody_else_does(self):
        self.assertEqual(self.patch(mk('trs_caller', 'tele_caller'), task_reminder_minutes=5).status_code, 403)
        self.assertEqual(get_or_create_config().task_reminder_minutes, 60)

    def test_an_interval_that_makes_no_sense_changes_nothing(self):
        for bad in (-5, 'soon', 30 * 24 * 60 + 1):
            self.assertEqual(self.patch(self.admin, task_reminder_minutes=bad,
                                        daily_popup_interval_hours=9).status_code, 400, bad)
        config = get_or_create_config()
        self.assertEqual((config.task_reminder_minutes, config.daily_popup_interval_hours), (60, 3))
