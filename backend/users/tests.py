"""Account-management hierarchy: who may edit, delete and rename whom.

These guard a real privilege-escalation path — before the hierarchy checks, any
is_staff user could PATCH a super admin's password and take the account over.
"""
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


def token_for(user):
    return f"Bearer {RefreshToken.for_user(user).access_token}"


def mk(username, role):
    u = User.objects.create_user(username=username, password='Pw@123456', first_name=username)
    u.role = role
    u.save()          # save() derives is_staff/is_superuser/... from the role
    return u


class AccountHierarchyTests(TestCase):
    def setUp(self):
        self.superadmin = mk('t_super', 'superadmin')
        self.admin = mk('t_admin', 'admin')
        self.admin2 = mk('t_admin2', 'admin')
        self.coo = mk('t_coo', 'coo')            # general manager, not is_staff
        self.bde = mk('t_bde', 'bde')

    # ── helpers ──
    def patch_user(self, actor, target, payload):
        return self.client.patch(f'/api/users/{target.id}/', data=payload,
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor))

    def delete_user(self, actor, target):
        return self.client.delete(f'/api/users/{target.id}/',
                                  HTTP_AUTHORIZATION=token_for(actor))

    def create_user(self, actor, payload):
        return self.client.post('/api/users/', data=payload,
                                content_type='application/json',
                                HTTP_AUTHORIZATION=token_for(actor))

    # ── editing ──
    def test_admin_cannot_edit_superadmin(self):
        """The takeover path: resetting a super admin's password must be refused."""
        r = self.patch_user(self.admin, self.superadmin, {'password': 'pwned12345'})
        self.assertEqual(r.status_code, 403)
        self.superadmin.refresh_from_db()
        self.assertTrue(self.superadmin.check_password('Pw@123456'))

    def test_admin_cannot_edit_peer_admin(self):
        r = self.patch_user(self.admin, self.admin2, {'first_name': 'Nope'})
        self.assertEqual(r.status_code, 403)
        self.admin2.refresh_from_db()
        self.assertEqual(self.admin2.first_name, 't_admin2')

    def test_admin_can_edit_self_and_lower(self):
        self.assertEqual(self.patch_user(self.admin, self.admin, {'first_name': 'Me'}).status_code, 200)
        self.assertEqual(self.patch_user(self.admin, self.bde, {'first_name': 'Field'}).status_code, 200)

    def test_superadmin_can_edit_everyone(self):
        self.assertEqual(self.patch_user(self.superadmin, self.admin, {'first_name': 'A'}).status_code, 200)
        self.assertEqual(self.patch_user(self.superadmin, self.superadmin, {'first_name': 'S'}).status_code, 200)

    # ── deleting ──
    def test_admin_cannot_delete_superadmin_or_peer(self):
        self.assertEqual(self.delete_user(self.admin, self.superadmin).status_code, 403)
        self.assertEqual(self.delete_user(self.admin, self.admin2).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.superadmin.pk).exists())

    def test_superadmin_can_delete_admin(self):
        self.assertEqual(self.delete_user(self.superadmin, self.admin2).status_code, 204)

    # ── granting roles ──
    def test_admin_cannot_grant_admin_or_superadmin(self):
        for role in ('admin', 'superadmin'):
            self.assertEqual(self.patch_user(self.admin, self.bde, {'role': role}).status_code, 403, role)
        self.bde.refresh_from_db()
        self.assertEqual(self.bde.role, 'bde')

    def test_appointing_an_admin_is_a_superadmin_job(self):
        payload = {'username': 't_new_admin', 'password': 'Pw@123456', 'role': 'admin'}
        self.assertEqual(self.create_user(self.admin, payload).status_code, 403)
        self.assertFalse(User.objects.filter(username='t_new_admin').exists())
        self.assertEqual(self.create_user(self.superadmin, payload).status_code, 201)

    def test_admin_can_still_staff_the_company(self):
        r = self.create_user(self.admin, {'username': 't_new_bde', 'password': 'Pw@123456', 'role': 'bde'})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.patch_user(self.admin, self.bde, {'role': 'sales_manager'}).status_code, 200)

    def test_assignable_roles_endpoint(self):
        def roles_for(user):
            r = self.client.get('/api/users/assignable-roles/', HTTP_AUTHORIZATION=token_for(user))
            self.assertEqual(r.status_code, 200)
            return [x['value'] for x in r.json()]

        self.assertIn('admin', roles_for(self.superadmin))
        self.assertNotIn('admin', roles_for(self.admin))
        # Nobody can mint another super admin through the API.
        self.assertNotIn('superadmin', roles_for(self.superadmin))

    def test_can_manage_flag_matches_enforcement(self):
        """The Team page hides controls off this flag, so it must not over-promise."""
        r = self.client.get('/api/users/', HTTP_AUTHORIZATION=token_for(self.admin))
        rows = r.json()
        rows = rows if isinstance(rows, list) else rows['results']
        flags = {x['username']: x['can_manage'] for x in rows}
        self.assertFalse(flags['t_super'])
        self.assertFalse(flags['t_admin2'])
        self.assertTrue(flags['t_admin'])      # yourself
        self.assertTrue(flags['t_bde'])


class UsernameChangeTests(TestCase):
    """Only an Admin or Super Admin may change a username — including their own."""

    def setUp(self):
        self.superadmin = mk('t_super', 'superadmin')
        self.admin = mk('t_admin', 'admin')
        self.coo = mk('t_coo', 'coo')
        self.bde = mk('t_bde', 'bde')

    def patch_user(self, actor, target, payload):
        return self.client.patch(f'/api/users/{target.id}/', data=payload,
                                 content_type='application/json',
                                 HTTP_AUTHORIZATION=token_for(actor))

    def test_non_staff_cannot_rename_themselves(self):
        for user in (self.bde, self.coo):
            original = user.username
            r = self.patch_user(user, user, {'username': f'{original}_new'})
            self.assertEqual(r.status_code, 403, user.role)
            user.refresh_from_db()
            self.assertEqual(user.username, original)

    def test_non_staff_can_still_edit_their_other_details(self):
        """The edit form always posts the username; an unchanged one must not 403."""
        r = self.patch_user(self.bde, self.bde, {'username': 't_bde', 'phone': '9000000001'})
        self.assertEqual(r.status_code, 200)
        self.bde.refresh_from_db()
        self.assertEqual(self.bde.phone, '9000000001')

    def test_staff_can_rename(self):
        self.assertEqual(self.patch_user(self.admin, self.bde, {'username': 't_bde2'}).status_code, 200)
        self.assertEqual(self.patch_user(self.admin, self.admin, {'username': 't_admin_x'}).status_code, 200)
        self.assertEqual(self.patch_user(self.superadmin, self.superadmin, {'username': 't_super_x'}).status_code, 200)

    def test_rename_still_obeys_the_hierarchy(self):
        r = self.patch_user(self.admin, self.superadmin, {'username': 't_super_taken'})
        self.assertEqual(r.status_code, 403)
        self.superadmin.refresh_from_db()
        self.assertEqual(self.superadmin.username, 't_super')
