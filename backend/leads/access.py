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


def can_access_accounts(user):
    """Who can open the Accounts view (the payment-verification queue):
    accounts staff, plus admins / general managers who oversee them."""
    if not user or not user.is_authenticated:
        return False
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') == 'accounts_staff')


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
