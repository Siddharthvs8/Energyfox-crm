"""Account-management hierarchy: who may edit, delete and rename whom.

These guard a real privilege-escalation path — before the hierarchy checks, any
is_staff user could PATCH a super admin's password and take the account over.
"""
import tempfile

from django.test import TestCase, override_settings
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


class B2BRoleTests(TestCase):
    """Store manager / store keeper / accounts B2B belong to the wholesale side
    and must not pick up any B2C powers along the way."""

    ROLES = ('store_manager', 'store_keeper', 'accounts_b2b')

    def test_flagged_b2b_only(self):
        for role in self.ROLES:
            self.assertTrue(mk(f't_{role}', role).is_b2b_only, role)
        self.assertFalse(mk('t_bde', 'bde').is_b2b_only)
        self.assertFalse(mk('t_admin', 'admin').is_b2b_only)

    def test_carry_no_b2c_powers(self):
        """is_staff / is_manager would open team, lead and assignment paths."""
        for role in self.ROLES:
            u = mk(f't_{role}', role)
            self.assertFalse(u.is_staff, role)
            self.assertFalse(u.is_superuser, role)
            self.assertFalse(u.is_general_manager, role)
            self.assertFalse(u.is_manager, role)
            self.assertFalse(u.sees_all_leads, role)
            self.assertFalse(u.branch_scoped, role)

    def test_see_no_leads(self):
        from leads.models import Lead
        Lead.objects.create(first_name='Someone', phone='9995550000', value=0)
        for role in self.ROLES:
            u = mk(f't_{role}', role)
            r = self.client.get('/api/leads/', HTTP_AUTHORIZATION=token_for(u))
            rows = r.json() if isinstance(r.json(), list) else r.json()['results']
            self.assertEqual(rows, [], role)

    def test_admin_can_appoint_them(self):
        admin = mk('t_admin', 'admin')
        for role in self.ROLES:
            r = self.client.post('/api/users/', data={
                'username': f'new_{role}', 'password': 'Pw@123456', 'role': role},
                content_type='application/json', HTTP_AUTHORIZATION=token_for(admin))
            self.assertEqual(r.status_code, 201, role)
        offered = [x['value'] for x in self.client.get(
            '/api/users/assignable-roles/?segment=b2b',
            HTTP_AUTHORIZATION=token_for(admin)).json()]
        for role in self.ROLES:
            self.assertIn(role, offered)

    def test_store_manager_outranks_the_other_two(self):
        sm = mk('t_sm', 'store_manager')
        self.assertTrue(sm.can_manage(mk('t_sk', 'store_keeper')))
        self.assertTrue(sm.can_manage(mk('t_ab', 'accounts_b2b')))
        self.assertFalse(mk('t_sk2', 'store_keeper').can_manage(sm))


class B2BRosterTests(TestCase):
    """The wholesale roster lives in the B2B Team module and nowhere else."""

    def setUp(self):
        self.admin = mk('t_admin', 'admin')
        self.caller = mk('t_caller', 'tele_caller')
        self.bde = mk('t_bde', 'bde')
        self.store_mgr = mk('t_store_mgr', 'store_manager')
        self.keeper = mk('t_keeper', 'store_keeper')
        self.acct = mk('t_acct_b2b', 'accounts_b2b')

    def usernames(self, actor, query=''):
        r = self.client.get(f'/api/users/{query}', HTTP_AUTHORIZATION=token_for(actor))
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        rows = rows if isinstance(rows, list) else rows['results']
        return sorted(x['username'] for x in rows)

    def test_crm_team_module_hides_b2b_staff(self):
        listed = self.usernames(self.admin)
        self.assertIn('t_bde', listed)
        for name in ('t_store_mgr', 't_keeper', 't_acct_b2b'):
            self.assertNotIn(name, listed)

    def test_b2b_team_module_shows_only_b2b_staff(self):
        self.assertEqual(self.usernames(self.admin, '?segment=b2b'),
                         ['t_acct_b2b', 't_keeper', 't_store_mgr'])

    def test_b2b_staff_always_get_their_own_roster(self):
        """Pinned server-side — asking for the B2C segment changes nothing."""
        for actor in (self.store_mgr, self.keeper, self.acct):
            for query in ('', '?segment=b2c', '?segment=b2b'):
                self.assertEqual(self.usernames(actor, query),
                                 ['t_acct_b2b', 't_keeper', 't_store_mgr'],
                                 f'{actor.role} {query!r}')

    def test_role_picker_is_segmented(self):
        def roles(query=''):
            r = self.client.get(f'/api/users/assignable-roles/{query}',
                                HTTP_AUTHORIZATION=token_for(self.admin))
            return [x['value'] for x in r.json()]

        b2b = roles('?segment=b2b')
        self.assertEqual(sorted(b2b), ['accounts_b2b', 'store_keeper', 'store_manager'])
        b2c = roles()
        self.assertIn('bde', b2c)
        for role in ('store_manager', 'store_keeper', 'accounts_b2b'):
            self.assertNotIn(role, b2c)

    def test_b2b_staff_are_never_offered_as_lead_assignees(self):
        r = self.client.get('/api/users/assignable/', HTTP_AUTHORIZATION=token_for(self.admin))
        names = [x['name'] for x in r.json()]
        for name in ('t_store_mgr', 't_keeper', 't_acct_b2b'):
            self.assertNotIn(name, names)

    def test_admins_can_still_manage_b2b_accounts(self):
        """The edit/delete calls carry no ?segment, so the roster filter must not
        reach detail routes — it would 404 the B2B Team page's own buttons."""
        superadmin = mk('t_super', 'superadmin')
        for actor in (superadmin, self.admin):
            r = self.client.patch(f'/api/users/{self.keeper.id}/', data={'first_name': actor.role},
                                  content_type='application/json',
                                  HTTP_AUTHORIZATION=token_for(actor))
            self.assertEqual(r.status_code, 200, actor.role)
        r = self.client.delete(f'/api/users/{self.acct.id}/',
                               HTTP_AUTHORIZATION=token_for(superadmin))
        self.assertEqual(r.status_code, 204)

    def test_b2b_staff_cannot_reach_a_b2c_account(self):
        """Their roster pins every action, not just the list."""
        r = self.client.patch(f'/api/users/{self.bde.id}/', data={'first_name': 'Nope'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.store_mgr))
        self.assertEqual(r.status_code, 404)


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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='avatar-tests-'))
class AvatarTests(TestCase):
    """Everyone may set their own picture; nobody may set someone else's unless
    the hierarchy already lets them edit that account."""

    def setUp(self):
        self.superadmin = mk('t_super', 'superadmin')
        self.admin = mk('t_admin', 'admin')
        self.bde = mk('t_bde', 'bde')
        self.caller = mk('t_caller', 'tele_caller')

    @staticmethod
    def image(name='pic.png', size=(8, 8), fmt='PNG'):
        """A real image — Django's ImageField runs it through Pillow, so a
        hand-rolled byte string won't do."""
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = BytesIO()
        Image.new('RGB', size, (200, 120, 40)).save(buf, format=fmt)
        return SimpleUploadedFile(name, buf.getvalue(), content_type=f'image/{fmt.lower()}')

    def post_avatar(self, actor, target, upload=None):
        return self.client.post(f'/api/users/{target.id}/avatar/',
                                {'avatar': upload if upload is not None else self.image()},
                                HTTP_AUTHORIZATION=token_for(actor))

    def test_anyone_can_set_their_own(self):
        for user in (self.bde, self.caller, self.admin, self.superadmin):
            r = self.post_avatar(user, user)
            self.assertEqual(r.status_code, 200, f"{user.role}: {r.content[:200]}")
            self.assertTrue(r.json()['avatar_url'], user.role)
            user.refresh_from_db()
            self.assertTrue(user.avatar.name.startswith('avatars/'), user.avatar.name)

    def test_cannot_set_a_visible_peers_picture(self):
        """Same team, so the account IS fetchable — this exercises the action's own
        guard, since check_object_permissions only covers update/destroy."""
        from .models import WorkspaceTeam
        team = WorkspaceTeam.objects.create(name='Squad')
        for u in (self.bde, self.caller):
            u.team = team
            u.save()
        r = self.post_avatar(self.bde, self.caller)
        self.assertEqual(r.status_code, 403)
        self.caller.refresh_from_db()
        self.assertFalse(self.caller.avatar)

    def test_cannot_set_an_out_of_scope_picture(self):
        r = self.post_avatar(self.bde, self.admin)
        self.assertIn(r.status_code, (403, 404))
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.avatar)

    def test_hierarchy_still_applies(self):
        self.assertEqual(self.post_avatar(self.admin, self.bde).status_code, 200)
        self.assertEqual(self.post_avatar(self.admin, self.superadmin).status_code, 403)

    def test_replacing_removes_the_old_file(self):
        self.post_avatar(self.bde, self.bde)
        self.bde.refresh_from_db()
        first, storage = self.bde.avatar.name, self.bde.avatar.storage
        self.assertTrue(storage.exists(first))
        self.post_avatar(self.bde, self.bde, self.image('second.png'))
        self.bde.refresh_from_db()
        self.assertNotEqual(self.bde.avatar.name, first)
        self.assertFalse(storage.exists(first))

    def test_delete_clears_it(self):
        self.post_avatar(self.bde, self.bde)
        self.bde.refresh_from_db()
        name, storage = self.bde.avatar.name, self.bde.avatar.storage
        r = self.client.delete(f'/api/users/{self.bde.id}/avatar/',
                               HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['avatar_url'])
        self.bde.refresh_from_db()
        self.assertFalse(self.bde.avatar)
        self.assertFalse(storage.exists(name))

    def test_rejects_a_non_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = SimpleUploadedFile('run.sh', b'#!/bin/sh\necho hi\n', content_type='text/x-sh')
        r = self.post_avatar(self.bde, self.bde, bad)
        self.assertEqual(r.status_code, 400)
        self.bde.refresh_from_db()
        self.assertFalse(self.bde.avatar)

    def test_rejects_an_oversized_image(self):
        """A valid image, just too big — the size check sits behind Pillow's."""
        import os
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = BytesIO()
        # Noise doesn't compress, so this clears 5 MB as a PNG.
        Image.frombytes('RGB', (1500, 1500), os.urandom(1500 * 1500 * 3)).save(buf, format='PNG')
        self.assertGreater(buf.tell(), 5 * 1024 * 1024)
        big = SimpleUploadedFile('big.png', buf.getvalue(), content_type='image/png')
        r = self.post_avatar(self.bde, self.bde, big)
        self.assertEqual(r.status_code, 400)
        self.assertIn('5 MB', str(r.json()))
        self.bde.refresh_from_db()
        self.assertFalse(self.bde.avatar)

    def test_missing_file_is_a_400(self):
        r = self.client.post(f'/api/users/{self.bde.id}/avatar/', {},
                             HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertEqual(r.status_code, 400)

    def test_avatar_url_is_absolute(self):
        r = self.post_avatar(self.bde, self.bde)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertTrue(r.json()['avatar_url'].startswith('http'))

    def test_me_carries_the_picture(self):
        self.post_avatar(self.bde, self.bde)
        r = self.client.get('/api/users/me/', HTTP_AUTHORIZATION=token_for(self.bde))
        self.assertTrue(r.json()['avatar_url'])


class LeadsManagerRoleTests(TestCase):
    """The leads manager runs the lead book: Leads, Campaigns, Meta Integration.

    Three doors and no more — the point of the role is that it is *not* an admin,
    so most of these tests are about what it cannot reach.
    """

    def setUp(self):
        from campaigns.models import Campaign
        self.lm = mk('lm_user', 'leads_manager')
        self.admin = mk('lm_admin', 'superadmin')
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save()
        self.campaign = Campaign.objects.create(name='TVM ad', campaign_type='advertisement',
                                                status='active')

    def get(self, path, user=None):
        return self.client.get(path, HTTP_AUTHORIZATION=token_for(user or self.lm))

    # ── The role itself ──
    def test_it_is_not_an_admin_or_a_general_manager(self):
        """Either flag would open every module in the company."""
        self.lm.refresh_from_db()
        self.assertFalse(self.lm.is_staff)
        self.assertFalse(self.lm.is_superuser)
        self.assertFalse(self.lm.is_general_manager)
        self.assertFalse(self.lm.is_manager)

    def test_it_is_offered_when_an_admin_creates_an_account(self):
        r = self.get('/api/users/assignable-roles/', user=self.admin)
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertIn('leads_manager', [row['value'] for row in r.json()])

    # ── Leads ──
    def test_it_sees_the_whole_lead_book(self):
        from leads.models import Lead
        Lead.objects.create(first_name='Someone', last_name='Else', phone='9895271487')
        self.lm.refresh_from_db()
        self.assertTrue(self.lm.sees_all_leads)
        r = self.get('/api/leads/')
        self.assertEqual(r.status_code, 200, r.content[:200])
        body = r.json()
        rows = body if isinstance(body, list) else body.get('results', [])
        self.assertTrue(any(x['first_name'] == 'Someone' for x in rows))

    def test_it_can_add_edit_assign_and_use_the_lead_tools(self):
        from leads.access import (can_add_leads, can_edit_leads, can_assign_leads,
                                  can_use_lead_tools, can_edit_lead_status)
        for fn in (can_add_leads, can_edit_leads, can_assign_leads,
                   can_use_lead_tools, can_edit_lead_status):
            self.assertTrue(fn(self.lm), fn.__name__)

    # ── Campaigns ──
    def test_it_can_list_and_open_campaigns(self):
        self.assertEqual(self.get('/api/campaigns/').status_code, 200)
        self.assertEqual(self.get(f'/api/campaigns/{self.campaign.id}/').status_code, 200)

    def test_it_can_create_a_campaign(self):
        r = self.client.post('/api/campaigns/',
                             data={'name': 'Onam push', 'campaign_type': 'advertisement',
                                   'status': 'active'},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.lm))
        self.assertEqual(r.status_code, 201, r.content[:300])

    # ── Meta integration ──
    def test_it_can_reach_the_meta_integration(self):
        self.assertEqual(self.get('/api/integration-settings/').status_code, 200)

    # ── Everything else is shut ──
    def test_it_cannot_reach_the_other_modules(self):
        from leads.access import (can_access_accounts, can_access_purchase,
                                  can_access_project, can_access_liasoning,
                                  can_access_documentation, can_access_doc_stage2,
                                  can_access_warranty, can_cleanup_deleted_lead)
        for fn in (can_access_accounts, can_access_purchase, can_access_project,
                   can_access_liasoning, can_access_documentation,
                   can_access_doc_stage2, can_access_warranty,
                   can_cleanup_deleted_lead):
            self.assertFalse(fn(self.lm), fn.__name__)

    def test_it_cannot_administer_users(self):
        r = self.client.post('/api/users/',
                             data={'username': 'sneaky', 'password': 'Pw@123456',
                                   'role': 'admin'},
                             content_type='application/json',
                             HTTP_AUTHORIZATION=token_for(self.lm))
        self.assertIn(r.status_code, (400, 403))
        self.assertFalse(User.objects.filter(username='sneaky').exists())

    def test_it_cannot_reach_the_ai_manager(self):
        """IsAdminOrManager guards it, and the leads desk was added elsewhere."""
        r = self.get('/api/ai-manager/config/')
        self.assertIn(r.status_code, (403, 404))

    def test_it_cannot_change_organization_settings(self):
        r = self.client.patch('/api/org-settings/', data={'email_signature': 'nope'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=token_for(self.lm))
        self.assertEqual(r.status_code, 403)

    def test_it_cannot_reach_the_stock_register(self):
        r = self.get('/api/stock-items/')
        self.assertEqual(r.status_code, 403)

    # ── Rank ──
    def test_an_admin_can_manage_it_but_it_cannot_manage_anyone(self):
        from users.models import role_rank
        self.assertGreater(role_rank('admin'), role_rank('leads_manager'))
        self.assertGreater(role_rank('leads_manager'), role_rank('tele_caller'))


class TeamRolePickerCoverageTests(TestCase):
    """The Team form's role list is hardcoded in the frontend.

    `assignable-roles` only *filters* that list, so a role missing from it can
    never be picked however correct the backend is — which is exactly how the
    leads manager shipped invisible. This keeps the two in step.
    """

    PICKER = '../frontend/src/app/(crm)/team/page.tsx'

    def picker_values(self):
        import io
        import os
        import re
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.normpath(os.path.join(here, self.PICKER))
        if not os.path.exists(path):
            self.skipTest('frontend not present next to the backend')
        source = io.open(path, encoding='utf-8').read()
        block = re.search(r'const ROLES = \[(.*?)\];', source, re.S)
        self.assertIsNotNone(block, 'could not find the ROLES list in the Team page')
        return set(re.findall(r'value:\s*"([a-z0-9_]+)"', block.group(1)))

    def test_every_role_can_be_picked_in_the_team_form(self):
        from .models import ROLE_CHOICES
        missing = {r for r, _label in ROLE_CHOICES} - self.picker_values()
        self.assertEqual(missing, set(),
                         f'roles the Team form cannot offer: {sorted(missing)}')

    def test_the_picker_offers_nothing_the_backend_would_reject(self):
        from .models import ROLE_CHOICES
        unknown = self.picker_values() - {r for r, _label in ROLE_CHOICES}
        self.assertEqual(unknown, set(),
                         f'roles the Team form offers that do not exist: {sorted(unknown)}')
