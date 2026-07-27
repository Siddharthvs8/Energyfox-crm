"""Custom user types: a role built in Settings grants exactly what it lists."""
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from leads.access import (can_access_accounts, can_access_documentation, can_access_warranty,
                          can_access_purchase, can_access_project, can_access_liasoning,
                          can_add_leads, can_assign_leads, can_edit_lead_status,
                          can_mark_lead_lost, can_assign_documentation)
from .models import User, CustomRole
from .permission_catalog import ALL_PERMISSION_KEYS


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role, custom_role=None):
    u = User.objects.create_user(username=username, password='Pw@123456')
    u.role = role
    u.custom_role = custom_role
    u.save()
    return u


class CustomRoleModelTests(TestCase):
    def test_unknown_permissions_are_dropped_on_save(self):
        """A stale key would look granted in the UI while doing nothing."""
        role = CustomRole.objects.create(name='Odd', permissions=['accounts', 'not-a-thing', 'leads'])
        role.refresh_from_db()
        self.assertEqual(role.permissions, ['leads', 'accounts'])   # catalogue order

    def test_granted_is_none_for_builtin_roles(self):
        """None means 'use the built-in rules'; False would mean 'denied'."""
        self.assertIsNone(mk('m_bde', 'bde').granted)
        self.assertIsNone(mk('m_admin', 'admin').granted)
        self.assertIsNone(mk('m_bde2', 'bde').can('accounts'))

    def test_inactive_role_grants_nothing(self):
        role = CustomRole.objects.create(name='Paused', permissions=['accounts'], is_active=False)
        u = mk('m_paused', 'custom', role)
        self.assertIsNone(u.granted)        # falls back to the (powerless) built-in rules
        self.assertFalse(can_access_accounts(u))

    def test_custom_role_without_a_role_object_is_powerless(self):
        u = mk('m_orphan', 'custom')
        self.assertIsNone(u.granted)
        self.assertFalse(can_access_accounts(u))
        self.assertFalse(can_access_documentation(u))


class CustomRoleAccessTests(TestCase):
    """The gates must both open and close for a custom role."""

    def setUp(self):
        self.role = CustomRole.objects.create(
            name='Site Supervisor',
            permissions=['accounts', 'project', 'leads', 'leads.add', 'leads.status'])
        self.user = mk('c_sup', 'custom', self.role)

    def test_granted_modules_open(self):
        self.assertTrue(can_access_accounts(self.user))
        self.assertTrue(can_access_project(self.user))

    def test_ungranted_modules_stay_shut(self):
        for gate in (can_access_documentation, can_access_warranty,
                     can_access_purchase, can_access_liasoning):
            self.assertFalse(gate(self.user), gate.__name__)

    def test_capabilities_follow_the_list(self):
        self.assertTrue(can_add_leads(self.user))
        self.assertTrue(can_edit_lead_status(self.user))
        # Not listed → denied, even though every built-in non-BDE role may do it.
        self.assertFalse(can_assign_leads(self.user))
        self.assertFalse(can_mark_lead_lost(self.user))
        self.assertFalse(can_assign_documentation(self.user))

    def test_view_all_leads_is_a_permission(self):
        self.assertFalse(self.user.sees_all_leads)
        self.role.permissions = self.role.permissions + ['leads.view_all']
        self.role.save()
        self.user.refresh_from_db()
        self.assertTrue(self.user.sees_all_leads)

    def test_custom_role_carries_no_implicit_flags(self):
        for flag in ('is_staff', 'is_superuser', 'is_general_manager', 'is_manager'):
            self.assertFalse(getattr(self.user, flag), flag)

    def test_editing_the_role_changes_access_for_its_members(self):
        self.assertFalse(can_access_warranty(self.user))
        self.role.permissions = ['warranty']
        self.role.save()
        self.user.refresh_from_db()
        self.assertTrue(can_access_warranty(self.user))
        self.assertFalse(can_access_accounts(self.user))     # revoked

    def test_module_counts_follow_the_grants(self):
        r = self.client.get('/api/leads/module-counts/', HTTP_AUTHORIZATION=token_for(self.user))
        self.assertEqual(r.status_code, 200)
        counts = r.json()['counts']
        self.assertIn('accounts', counts)
        self.assertIn('project', counts)
        self.assertNotIn('documentation', counts)
        self.assertNotIn('purchase', counts)


class CustomRoleApiTests(TestCase):
    def setUp(self):
        self.admin = mk('a_admin', 'admin')
        self.bde = mk('a_bde', 'bde')

    def test_catalog_is_served(self):
        r = self.client.get('/api/users/permission-catalog/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 200)
        keys = {p['key'] for p in r.json()['modules']} | {p['key'] for p in r.json()['capabilities']}
        self.assertEqual(keys, ALL_PERMISSION_KEYS)

    def test_admin_can_build_a_role(self):
        r = self.client.post('/api/custom-roles/', data={
            'name': 'Auditor', 'description': 'Read the money screens',
            'permissions': ['accounts', 'accounts/fully-paid'],
        }, content_type='application/json', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 201, r.content[:200])
        self.assertEqual(r.json()['permissions'], ['accounts', 'accounts/fully-paid'])

    def test_unknown_permission_is_rejected_with_a_message(self):
        r = self.client.post('/api/custom-roles/', data={'name': 'Bad', 'permissions': ['sudo']},
                             content_type='application/json', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 400)
        self.assertIn('sudo', str(r.json()))

    def test_non_admin_cannot_create_or_edit(self):
        r = self.client.post('/api/custom-roles/', data={'name': 'Sneaky', 'permissions': ['settings']},
                             content_type='application/json', HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403)
        role = CustomRole.objects.create(name='Real', permissions=['leads'])
        r = self.client.patch(f'/api/custom-roles/{role.id}/', data={'permissions': ['settings']},
                              content_type='application/json', HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 403)
        role.refresh_from_db()
        self.assertEqual(role.permissions, ['leads'])

    def test_role_in_use_cannot_be_deleted(self):
        role = CustomRole.objects.create(name='Busy', permissions=['leads'])
        mk('a_member', 'custom', role)
        r = self.client.delete(f'/api/custom-roles/{role.id}/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 400)
        self.assertIn('assigned to', str(r.json()))
        self.assertTrue(CustomRole.objects.filter(pk=role.pk).exists())

    def test_unused_role_can_be_deleted(self):
        role = CustomRole.objects.create(name='Spare', permissions=[])
        r = self.client.delete(f'/api/custom-roles/{role.id}/', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 204)

    def test_user_payload_exposes_the_resolved_permissions(self):
        """The sidebar filters off this list, so it must match the role."""
        role = CustomRole.objects.create(name='Desk', permissions=['leads', 'accounts'])
        user = mk('a_desk', 'custom', role)
        r = self.client.get('/api/users/me/', HTTP_AUTHORIZATION=token_for(user))
        # Catalogue order, matching what /api/custom-roles/ reports for the role.
        self.assertEqual(r.json()['permissions'], role.permissions)
        self.assertEqual(sorted(r.json()['permissions']), ['accounts', 'leads'])
        self.assertEqual(r.json()['custom_role_name'], 'Desk')
        # A built-in role reports an empty list, never a misleading partial one.
        r = self.client.get('/api/users/me/', HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.json()['permissions'], [])

    def test_admin_can_assign_the_custom_user_type(self):
        role = CustomRole.objects.create(name='Supervisor', permissions=['project'])
        r = self.client.post('/api/users/', data={
            'username': 'a_new_custom', 'password': 'Pw@123456',
            'role': 'custom', 'custom_role': role.id,
        }, content_type='application/json', HTTP_AUTHORIZATION=token_for(self.admin))
        self.assertEqual(r.status_code, 201, r.content[:200])
        created = User.objects.get(username='a_new_custom')
        self.assertEqual(created.custom_role_id, role.id)
        self.assertTrue(can_access_project(created))
