"""Automation logic for the accounts desk.

The accounts manager hands leads to their staff by hand; these are the same
handovers expressed as rules, so routing keeps working when nobody is at the
screen.
"""
from decimal import Decimal

from django.test import TestCase

from leads.models import Lead
from users.models import User

from .engine import _dispatch_action
from .models import AutomationRule


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456')
    u.role = role
    u.save()
    return u


class AssignAccountsStaffActionTests(TestCase):
    def setUp(self):
        self.staff_a = mk('au_staff_a', 'accounts_staff')
        self.staff_b = mk('au_staff_b', 'accounts_staff')
        self.lead = Lead.objects.create(first_name='mini', last_name='A', phone='9526396822',
                                        status='converted', value=Decimal('330000'),
                                        pushed_to_accounts=True)

    def run_action(self, params):
        return _dispatch_action('assign_accounts_staff', params, self.lead, {})

    def test_it_assigns_the_named_staff_member(self):
        detail = self.run_action({'user_id': self.staff_b.id})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.accounts_staff_id, self.staff_b.id)
        self.assertIn(str(self.staff_b.id), detail)

    def test_it_round_robins_when_nobody_is_named(self):
        self.run_action({})
        self.lead.refresh_from_db()
        self.assertIn(self.lead.accounts_staff_id, (self.staff_a.id, self.staff_b.id))

    def test_it_refuses_someone_who_cannot_work_the_queue(self):
        """Assigning a non-accounts user would strand the lead in the queue."""
        bde = mk('au_bde', 'bde')
        with self.assertRaises(ValueError):
            self.run_action({'user_id': bde.id})
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.accounts_staff_id)

    def test_it_refuses_a_deactivated_staff_member(self):
        self.staff_b.is_active = False
        self.staff_b.save(update_fields=['is_active'])
        with self.assertRaises(ValueError):
            self.run_action({'user_id': self.staff_b.id})

    def test_a_lead_not_yet_in_accounts_is_left_alone(self):
        other = Lead.objects.create(first_name='early', phone='9000000002', status='new')
        detail = _dispatch_action('assign_accounts_staff', {'user_id': self.staff_a.id}, other, {})
        other.refresh_from_db()
        self.assertIsNone(other.accounts_staff_id)
        self.assertIn('not in accounts', detail)


class NotifyByRoleTests(TestCase):
    """A rule can address a desk rather than a person, so it survives the
    person changing."""

    def setUp(self):
        self.manager = mk('nr_manager', 'accounts_manager')
        self.second = mk('nr_manager2', 'accounts_manager')
        mk('nr_staff', 'accounts_staff')
        self.lead = Lead.objects.create(first_name='mini', phone='9526396824', status='converted')

    def notify(self, params):
        return _dispatch_action('send_notification', params, self.lead, {})

    def test_every_holder_of_the_role_is_notified(self):
        from ai_manager.models import Notification
        detail = self.notify({'role': 'accounts_manager', 'message': 'New work in accounts'})
        recipients = set(Notification.objects.filter(message='New work in accounts')
                         .values_list('user_id', flat=True))
        self.assertEqual(recipients, {self.manager.id, self.second.id})
        self.assertIn('2', detail)

    def test_a_vacant_role_is_reported_not_raised(self):
        detail = self.notify({'role': 'project_manager', 'message': 'x'})
        self.assertIn('No active user', detail)

    def test_naming_neither_a_user_nor_a_role_is_an_error(self):
        with self.assertRaises(ValueError):
            self.notify({'message': 'x'})


class AccountsTriggerTests(TestCase):
    def test_the_accounts_handoff_is_offered_as_a_trigger(self):
        values = dict(AutomationRule.TRIGGER_CHOICES)
        self.assertIn('pushed_to_accounts', values)
