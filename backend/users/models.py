from django.contrib.auth.models import AbstractUser
from django.db import models


class Branch(models.Model):
    """A physical/operational branch, managed from the Branches module.
    Branch managers see only their own branch's data."""
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True, default='')

    # Office details
    manager = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_branches')
    location = models.CharField(max_length=200, blank=True, default='')
    address = models.TextField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    email = models.EmailField(blank=True, default='')

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Branches'

    def __str__(self):
        return self.name


class WorkspaceTeam(models.Model):
    name = models.CharField(max_length=150)
    manager = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_teams')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# ─── Roles ──────────────────────────────────────────────────────────────────────
# `role` is the single source of truth. The legacy booleans (is_staff,
# is_superuser, is_general_manager, is_manager) are kept as a denormalized cache,
# auto-maintained in User.save(), so all existing attribute checks AND ORM filters
# keep working unchanged.
ROLE_SUPERADMIN = 'superadmin'
ROLE_ADMIN = 'admin'
ROLE_COO = 'coo'
ROLE_SALES_MANAGER = 'sales_manager'
ROLE_DOC_MANAGER = 'documentation_manager'
ROLE_DOC_STAFF = 'documentation_staff'
ROLE_ACCOUNTS_STAFF = 'accounts_staff'
ROLE_PURCHASE_STAFF = 'purchase_staff'
ROLE_PROJECT_MANAGER = 'project_manager'
ROLE_LIASONING_OFFICER = 'liasoning_officer'
ROLE_BRANCH_MANAGER = 'branch_manager'
ROLE_BDE = 'bde'
ROLE_TELE_CALLER = 'tele_caller'

ROLE_CHOICES = [
    (ROLE_SUPERADMIN, 'Super Admin'),
    (ROLE_ADMIN, 'Admin'),
    (ROLE_COO, 'COO'),
    (ROLE_SALES_MANAGER, 'Sales Manager'),
    (ROLE_DOC_MANAGER, 'Documentation Manager'),
    (ROLE_DOC_STAFF, 'Documentation Staff'),
    (ROLE_ACCOUNTS_STAFF, 'Accounts Staff'),
    (ROLE_PURCHASE_STAFF, 'Purchase Staff'),
    (ROLE_PROJECT_MANAGER, 'Project Manager'),
    (ROLE_LIASONING_OFFICER, 'Liasoning Officer'),
    (ROLE_BRANCH_MANAGER, 'Branch Manager'),
    (ROLE_BDE, 'BDE'),
    (ROLE_TELE_CALLER, 'Tele Caller'),
]

# role -> (is_staff, is_superuser, is_general_manager, is_manager)
ROLE_BOOL_MAP = {
    ROLE_SUPERADMIN:     (True,  True,  False, False),
    ROLE_ADMIN:          (True,  False, False, False),
    ROLE_COO:            (False, False, True,  False),
    ROLE_SALES_MANAGER:  (False, False, True,  False),
    ROLE_DOC_MANAGER:    (False, False, True,  False),
    ROLE_DOC_STAFF:      (False, False, False, False),
    ROLE_ACCOUNTS_STAFF: (False, False, False, False),
    ROLE_PURCHASE_STAFF: (False, False, False, False),
    ROLE_PROJECT_MANAGER: (False, False, False, False),
    ROLE_LIASONING_OFFICER: (False, False, False, False),
    ROLE_BRANCH_MANAGER: (False, False, False, True),
    ROLE_BDE:            (False, False, False, False),
    ROLE_TELE_CALLER:    (False, False, False, False),
}


def _infer_role_from_flags(*, is_superuser, is_staff, is_general_manager, is_manager):
    """Bootstrap a role for legacy rows / createsuperuser (role left blank)."""
    if is_superuser:
        return ROLE_SUPERADMIN
    if is_staff:
        return ROLE_ADMIN
    if is_general_manager:
        return ROLE_COO
    if is_manager:
        return ROLE_BRANCH_MANAGER
    return ROLE_BDE


class User(AbstractUser):
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, blank=True, default='')
    is_manager = models.BooleanField(default=False)
    is_general_manager = models.BooleanField(default=False, help_text="General Manager: admin-like access except user creation")
    team = models.ForeignKey(WorkspaceTeam, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')

    phone = models.CharField(max_length=20, blank=True, null=True)
    voxbay_extension = models.CharField(max_length=20, blank=True, null=True)

    def save(self, *args, **kwargs):
        # `role` is the source of truth. Derive the cached booleans from it; if role
        # is blank (legacy / createsuperuser), infer one from the booleans first.
        if not self.role:
            self.role = _infer_role_from_flags(
                is_superuser=self.is_superuser, is_staff=self.is_staff,
                is_general_manager=self.is_general_manager, is_manager=self.is_manager,
            )
        is_staff, is_superuser, is_gm, is_mgr = ROLE_BOOL_MAP.get(self.role, (False, False, False, False))
        self.is_staff = is_staff
        self.is_superuser = is_superuser
        self.is_general_manager = is_gm
        self.is_manager = is_mgr
        super().save(*args, **kwargs)

    # ── Capability helpers (read-only; used by data-visibility + serializer output) ──
    @property
    def sees_all_leads(self):
        return self.is_staff or self.is_general_manager or self.role in (ROLE_DOC_STAFF, ROLE_ACCOUNTS_STAFF, ROLE_PURCHASE_STAFF, ROLE_PROJECT_MANAGER, ROLE_LIASONING_OFFICER)

    @property
    def branch_scoped(self):
        return self.role == ROLE_BRANCH_MANAGER

    def managed_user_ids(self):
        """Ids of the people this manager oversees — members of the teams they
        head, everyone in their branch (branch managers), and themselves.

        Returns ``None`` for admins / general managers, who oversee everyone.
        Use it wherever a view scopes data to "this manager's people" so branch
        managers get their whole branch, not only formal WorkspaceTeams.
        """
        if self.is_staff or self.is_general_manager:
            return None
        ids = {self.id}
        for team in self.managed_teams.all():
            ids.update(team.members.values_list('id', flat=True))
        if self.branch_scoped and self.branch_id:
            ids.update(
                User.objects.filter(branch_id=self.branch_id).values_list('id', flat=True))
        return ids
