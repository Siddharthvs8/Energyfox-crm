"""Per-lead access rules for the site-visit / BDE-assignment workflow.

Shared by the Lead serializer (to tell the UI what to show) and the viewset
actions (to actually enforce it).
"""


def can_edit_site_visit(user, lead):
    """Who may fill/update a lead's site visit:

    - the assigned BDE
    - that BDE's manager (branch manager of the BDE's branch, or the manager of
      the BDE's team)
    - all-access roles (admin/superadmin/COO/sales & documentation managers, and
      documentation staff who handle the uploaded documents)
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'sees_all_leads', False):
        return True
    # Once handed off to documentation, the field team (the BDE and their managers)
    # can no longer edit the site visit — it becomes read-only for them.
    if getattr(lead, 'pushed_to_documentation', False):
        return False
    bde = lead.bde
    if bde is None:
        return False
    if bde.id == user.id:
        return True
    # BDE's manager
    if getattr(user, 'branch_scoped', False) and user.branch_id and bde.branch_id == user.branch_id:
        return True
    if bde.team_id and bde.team and bde.team.manager_id == user.id:
        return True
    return False


def can_edit_kseb_feasibility(user, lead):
    """Who may handle a lead's KSEB feasibility task (PO + feasibility receipt).

    Active only AFTER the lead is pushed to documentation (the BDE handles it from
    the dedicated feasibility section, not the now-locked site visit). Allowed for
    the assigned BDE, that BDE's manager, and all-access roles.
    """
    if not user or not user.is_authenticated:
        return False
    if not getattr(lead, 'pushed_to_documentation', False):
        return False
    if user.is_staff or getattr(user, 'is_general_manager', False):
        return True
    bde = lead.bde
    if bde is None:
        return False
    if bde.id == user.id:
        return True
    if getattr(user, 'branch_scoped', False) and user.branch_id and bde.branch_id == user.branch_id:
        return True
    if bde.team_id and bde.team and bde.team.manager_id == user.id:
        return True
    return False


def can_assign_bde(user, lead):
    """Who may hand a lead off to a BDE: the lead's tele caller (owner) or any
    manager/admin tier user."""
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_general_manager or user.is_manager:
        return True
    return bool(lead.assigned_to_id and lead.assigned_to_id == user.id)


def can_push_to_documentation(user, lead):
    """Whoever can edit the site visit (the BDE, their manager, admins) may push
    the lead to documentation."""
    return can_edit_site_visit(user, lead)


def can_assign_documentation(user):
    """Documentation managers (and admins/superadmins) may assign a lead to a
    documentation staff member. Not lead-specific."""
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or getattr(user, 'role', '') == 'documentation_manager'


DOCUMENTATION_ROLES = {'documentation_staff', 'documentation_manager'}


def can_mark_lead_lost(user):
    """Who may mark a converted lead as lost (customer skipped / backed out) or
    restore it: admins, general managers, branch managers, and BDEs."""
    if not user or not user.is_authenticated:
        return False
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'is_manager', False) or getattr(user, 'role', '') == 'bde')


def can_access_accounts(user):
    """Who can open the Accounts view (the payment-verification queue): accounts
    staff and admins / general managers (who can edit), plus purchase staff who
    get a read-only view of the accounts data alongside their own module."""
    if not user or not user.is_authenticated:
        return False
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') in ('accounts_staff', 'purchase_staff'))


def can_assign_accounts(user):
    """Admins / general managers may assign a lead to an accounts staff member
    and reopen a completed payment verification. Not lead-specific."""
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or getattr(user, 'is_general_manager', False)


def can_edit_payment_verification(user, lead):
    """Who may fill/complete a lead's payment verification:

    - admins / general managers with accounts access (any lead)
    - an accounts_staff member ONLY for leads assigned to them

    The lead must already have been moved to accounts.
    """
    if not can_access_accounts(user):
        return False
    if not getattr(lead, 'pushed_to_accounts', False):
        return False
    is_plain_accounts_staff = (
        getattr(user, 'role', '') == 'accounts_staff'
        and not user.is_staff
        and not getattr(user, 'is_general_manager', False)
    )
    if is_plain_accounts_staff:
        return bool(lead.accounts_staff_id and lead.accounts_staff_id == user.id)
    # Admins / general managers may edit; other roles with access (purchase staff)
    # only view.
    return bool(user.is_staff or getattr(user, 'is_general_manager', False))


def can_access_purchase(user):
    """Who can open the Purchase & Logistics view: purchase staff, plus admins /
    general managers who oversee them."""
    if not user or not user.is_authenticated:
        return False
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') == 'purchase_staff')


def can_assign_purchase(user):
    """Admins / general managers may assign a lead to a purchase staff member
    and reopen a completed purchase & logistics record. Not lead-specific."""
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or getattr(user, 'is_general_manager', False)


def can_edit_purchase_logistics(user, lead):
    """Who may fill/complete a lead's purchase & logistics:

    - admins / general managers with purchase access (any lead)
    - a purchase_staff member ONLY for leads assigned to them

    The lead must already have been moved to purchase & logistics.
    """
    if not can_access_purchase(user):
        return False
    if not getattr(lead, 'pushed_to_purchase', False):
        return False
    is_plain_purchase_staff = (
        getattr(user, 'role', '') == 'purchase_staff'
        and not user.is_staff
        and not getattr(user, 'is_general_manager', False)
    )
    if is_plain_purchase_staff:
        return bool(lead.purchase_staff_id and lead.purchase_staff_id == user.id)
    return True


def can_access_project(user):
    """Who can open the Project / Service / Team-Stats views: the project manager,
    plus admins / general managers."""
    if not user or not user.is_authenticated:
        return False
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') == 'project_manager')


def can_assign_project(user):
    """Admins / general managers may assign a lead to a project manager and reopen
    a completed project. Not lead-specific."""
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or getattr(user, 'is_general_manager', False)


def can_edit_project(user, lead):
    """Who may fill/complete a lead's project:

    - admins / general managers with project access (any lead)
    - a project_manager ONLY for leads assigned to them

    The lead must already have been moved to the project stage.
    """
    if not can_access_project(user):
        return False
    if not getattr(lead, 'pushed_to_project', False):
        return False
    is_plain_pm = (
        getattr(user, 'role', '') == 'project_manager'
        and not user.is_staff
        and not getattr(user, 'is_general_manager', False)
    )
    if is_plain_pm:
        return bool(lead.project_manager_id and lead.project_manager_id == user.id)
    return True


def can_access_documentation(user):
    """Who can open the Documentation view (the pushed-customer queue)."""
    if not user or not user.is_authenticated:
        return False
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') in DOCUMENTATION_ROLES)


def can_edit_documentation_stage1(user, lead):
    """Who may fill/complete a lead's Documentation Stage 1:

    - admins / general & documentation managers with documentation access (any lead)
    - a documentation_staff member ONLY for leads assigned to them

    The lead must already have been pushed to documentation.

    NB: ``User.sees_all_leads`` is True for every documentation_staff (a *view*
    permission), so it must NOT be used here — this mirrors the assigned-only
    rule already enforced in the ``documentation_detail`` action.
    """
    if not can_access_documentation(user):
        return False
    if not getattr(lead, 'pushed_to_documentation', False):
        return False
    is_plain_doc_staff = (
        getattr(user, 'role', '') == 'documentation_staff'
        and not user.is_staff
        and not getattr(user, 'is_general_manager', False)
    )
    if is_plain_doc_staff:
        return bool(lead.documentation_staff_id and lead.documentation_staff_id == user.id)
    return True
