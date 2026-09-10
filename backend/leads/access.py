"""Per-lead access rules for the site-visit / BDE-assignment workflow.

Shared by the Lead serializer (to tell the UI what to show) and the viewset
actions (to actually enforce it).

Every `can_*` gate below first asks the user's custom role (if they are on one):
a user type defined in Settings grants exactly the keys it lists, so it must be
able to both open and close a door that a built-in role would decide differently.
`custom_grant` returns None for built-in roles, which means "fall through".

The spectator runs the other way: `is_view_only` opens every `can_access_*` gate
and closes every `can_edit_* / can_add_* / can_assign_* / can_delete_*` one, so
the account reads the whole company and writes none of it. The refusal that
actually protects the data is
`core.middleware.SpectatorReadOnlyMiddleware`; the gates here exist so the client
never draws a button that refusal would have to catch.
"""


def is_view_only(user):
    """True for a spectator: an account that reads the whole company and writes
    nothing.

    Every write gate below starts with this. Middleware already refuses the
    request, so this is not what keeps the data safe — it is what keeps the UI
    honest, because these same gates are what the serializers report to the
    client to decide which buttons to draw.
    """
    return bool(user and getattr(user, 'is_authenticated', False)
                and getattr(user, 'is_spectator', False))


def custom_grant(user, key):
    """True/False when the user is on a custom role, else None.

    Note the difference between None and False matters at every call site: None
    means "this user isn't custom, use the built-in rules", while False means
    "a custom role exists and does not include this permission".
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    can = getattr(user, 'can', None)
    return can(key) if callable(can) else None


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
    if is_view_only(user):
        return False
    if getattr(user, 'sees_all_leads', False):
        return True
    # Once handed off to documentation, the field team (the BDE and their managers)
    # can no longer edit the site visit — it becomes read-only for them.
    #
    # Unless a super admin has reopened it. That is the whole point of the
    # unlock: a correction to a survey is the BDE's job, and an unlock that only
    # let the super admin type would mean ringing the office to have someone
    # else enter what the BDE is standing in front of. Marking the visit
    # complete again clears the flag and closes this door.
    if getattr(lead, 'pushed_to_documentation', False):
        sv = getattr(lead, 'site_visit', None)
        if not (sv and sv.reopened_at):
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

    Active once the lead has reached the feasibility queue — either its PO has
    been signed on the site visit, or it has been pushed to documentation.
    Allowed for the assigned BDE, that BDE's manager, and all-access roles.
    """
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    sv = getattr(lead, 'site_visit', None)
    po_signed = bool(sv and sv.po_signed_date)
    if not po_signed and not getattr(lead, 'pushed_to_documentation', False):
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
    manager/admin tier user. Never the BDE side itself — routing work to a BDE
    is not a BDE's job, even on a lead that happens to be owned by one."""
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    if not can_assign_leads(user):
        return False
    if user.is_staff or user.is_general_manager or user.is_manager:
        return True
    # The current owner, or the tele caller who worked it — ownership is shared
    # once a lead is handed on, so passing it to a BDE must not cost the tele
    # caller the ability to hand it to a different one.
    return bool((lead.assigned_to_id and lead.assigned_to_id == user.id)
                or (lead.tele_caller_id and lead.tele_caller_id == user.id))


def can_push_to_documentation(user, lead):
    """Whoever can edit the site visit (the BDE, their manager, admins) may push
    the lead to documentation."""
    return can_edit_site_visit(user, lead)


def can_assign_documentation(user):
    """Documentation managers (and admins/superadmins) may assign a lead to a
    documentation staff member. Not lead-specific."""
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'queue.assign')
    if granted is not None:
        return granted
    return user.is_staff or getattr(user, 'role', '') == 'documentation_manager'


DOCUMENTATION_ROLES = {'documentation_staff', 'documentation_manager'}


def can_mark_lead_lost(user):
    """Who may mark a converted lead as lost (customer skipped / backed out) or
    restore it: admins, general managers, branch managers, and BDEs."""
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'leads.mark_lost')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'is_manager', False) or getattr(user, 'role', '') == 'bde')


def can_add_leads(user):
    """Who may create a lead.

    Everyone in the pipeline except BDEs: leads are sourced and owned by the
    tele-calling side, and reach a BDE only as a hand-off for the site visit.
    """
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'leads.add')
    if granted is not None:
        return granted
    return getattr(user, 'role', '') != 'bde'


def can_assign_leads(user):
    """Who may route a lead — set its owner, or hand it to a BDE.

    Same audience as can_add_leads: a BDE receives work, they don't distribute it.
    """
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'leads.assign')
    if granted is not None:
        return granted
    return getattr(user, 'role', '') != 'bde'


def can_edit_leads(user):
    """Who may edit a lead's details.

    Same audience as can_add_leads: the lead record belongs to the tele-calling
    side. A BDE reports through the site visit and can still mark a converted
    deal lost — they just don't edit the lead itself.
    """
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'leads.edit')
    if granted is not None:
        return granted
    return getattr(user, 'role', '') != 'bde'


def can_delete_leads(user):
    """Who may send a lead to Trash. A BDE receives work, they don't discard it."""
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'leads.delete')
    if granted is not None:
        return granted
    return getattr(user, 'role', '') != 'bde'


def can_use_lead_tools(user):
    """Who gets the list-management tools: CSV template, export, and the
    Archived / Trash views.

    These manage the lead book rather than work a lead, so they belong to the
    tele-calling side. A BDE gets the leads handed to them and the site visit.

    No `is_view_only` check here, unlike every other gate: all four are reads.
    The write controls that sit among them in the UI — Import, and the per-row
    Archive button — are gated by can_add_leads / can_edit_leads instead.
    """
    if not user or not user.is_authenticated:
        return False
    granted = custom_grant(user, 'leads.tools')
    if granted is not None:
        return granted
    return getattr(user, 'role', '') != 'bde'


def can_edit_lead_status(user):
    """Who may change a lead's status.

    Everyone in the pipeline except BDEs: a BDE works the site visit and reports
    through it, so the status is owned by the tele caller / managers. Automations
    run without a request user and are not affected.
    """
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'leads.status')
    if granted is not None:
        return granted
    return getattr(user, 'role', '') != 'bde'


# Who may open the Closed Deals board. The sales side of the house — the people
# who win the business and the people who manage them — plus the read-only
# spectator. Deliberately not the fulfilment desks (documentation, accounts,
# purchase, project, liasoning): they work a customer through their own stage
# and have their own queues for it.
CLOSED_DEALS_ROLES = {
    'superadmin', 'admin', 'coo', 'sales_manager', 'leads_manager',
    'branch_manager', 'bde', 'tele_caller',
}


def can_access_closed_deals(user):
    """Who can open the Closed Deals module.

    Access is the door; *which* deals are behind it is a separate question,
    answered by the same scoping the Leads list uses — so a BDE opens the module
    and finds their own closed deals in it, not the company's.
    """
    if not user or not user.is_authenticated:
        return False
    granted = custom_grant(user, 'closed-deals')
    if granted is not None:
        return granted
    return (getattr(user, 'role', '') in CLOSED_DEALS_ROLES
            or is_view_only(user))


# Who may open Company Performance. It reports the whole company — every
# branch's revenue, every team's, every person's — so it is the top of the house
# only: the super admin, the admin and the COO, plus the read-only spectator.
# Deliberately not the general-manager tier at large: a sales or documentation
# manager runs a function, and the Manager module already reports their people
# to them. Narrower than User.sees_everything for that reason.
COMPANY_PERFORMANCE_ROLES = {'superadmin', 'admin', 'coo', 'spectator'}


def can_access_company_performance(user):
    """Company-wide performance reporting. Read-only by nature, so the spectator
    belongs here on the same footing as the others."""
    if not user or not user.is_authenticated:
        return False
    granted = custom_grant(user, 'company-performance')
    if granted is not None:
        return granted
    return getattr(user, 'role', '') in COMPANY_PERFORMANCE_ROLES


def can_access_doc_stage2(user):
    """Who can open Documentation Stage 2: the documentation team plus admins /
    general managers (same audience as Documentation Stage 1)."""
    if not user or not user.is_authenticated:
        return False
    granted = custom_grant(user, 'documentation-stage2')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') in DOCUMENTATION_ROLES
            or is_view_only(user))


def can_reopen_documentation(user):
    """Who may unlock a completed documentation stage so it can be edited again:
    documentation managers and admins / general managers. Ordinary documentation
    staff can complete a stage but not reopen it."""
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'queue.assign')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') == 'documentation_manager')


def can_reopen_site_visit(user):
    """Who may unlock a signed-off site visit so it can be edited again: the
    super admin, and no one else.

    Same reasoning as ``can_reopen_liasoning`` below, and deliberately not routed
    through ``custom_grant``. Completing a site visit is what hands the customer
    to documentation; letting the person who signed it quietly unsign it would
    make the hand-off meaningless. Reopening is an exception someone senior
    grants, and it is logged against the lead.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return bool(getattr(user, 'is_superuser', False))


def can_reopen_liasoning(user):
    """Who may unlock a completed liasoning record so it can be edited again:
    the super admin, and no one else.

    Deliberately not routed through ``custom_grant``. Completing liasoning is a
    statement that the plant is live and the evidence is on file; letting the
    same person who made that statement quietly take it back would leave the
    record saying nothing at all. Reopening is an exception someone senior
    grants, not a permission the role carries.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return bool(getattr(user, 'is_superuser', False))


def can_access_liasoning(user):
    """Who can open the Liasoning & Service module: the liasoning officer plus
    admins / general managers who oversee them."""
    if not user or not user.is_authenticated:
        return False
    granted = custom_grant(user, 'liasoning')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') == 'liasoning_officer'
            or is_view_only(user))


def can_access_warranty(user):
    """Who can open the Warranty module: the documentation team plus admins /
    general managers (it lives under documentation)."""
    if not user or not user.is_authenticated:
        return False
    granted = custom_grant(user, 'warranty')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') in DOCUMENTATION_ROLES
            or is_view_only(user))


# The accounts team. The manager runs the queue and hands leads to their staff;
# unlike the documentation manager it carries no company-wide flag, so every
# power it has is granted here by name.
ACCOUNTS_ROLES = {'accounts_staff', 'accounts_manager'}


def can_access_accounts(user):
    """Who can open the Accounts view (the payment-verification queue): the
    accounts team and admins / general managers (who can edit), plus purchase
    staff who get a read-only view of the accounts data alongside their own
    module."""
    if not user or not user.is_authenticated:
        return False
    granted = custom_grant(user, 'accounts')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') in (ACCOUNTS_ROLES | {'purchase_staff'})
            or is_view_only(user))


def can_assign_accounts(user):
    """The accounts manager (and admins / general managers) may assign a lead to
    an accounts staff member and reopen a completed payment verification. Not
    lead-specific."""
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'queue.assign')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') == 'accounts_manager')


def can_edit_payment_verification(user, lead):
    """Who may fill/complete a lead's payment verification:

    - admins / general managers with accounts access (any lead)
    - the accounts manager, who oversees the whole queue (any lead)
    - an accounts_staff member ONLY for leads assigned to them

    The lead must already have been moved to accounts.
    """
    if not can_access_accounts(user) or is_view_only(user):
        return False
    if not getattr(lead, 'pushed_to_accounts', False):
        return False
    role = getattr(user, 'role', '')
    is_plain_accounts_staff = (
        role == 'accounts_staff'
        and not user.is_staff
        and not getattr(user, 'is_general_manager', False)
    )
    if is_plain_accounts_staff:
        return bool(lead.accounts_staff_id and lead.accounts_staff_id == user.id)
    # Admins / general managers / the accounts manager may edit; other roles with
    # access (purchase staff) only view.
    return bool(user.is_staff or getattr(user, 'is_general_manager', False)
                or role == 'accounts_manager')


def can_access_purchase(user):
    """Who can open the Purchase & Logistics view: purchase staff, plus admins /
    general managers who oversee them."""
    if not user or not user.is_authenticated:
        return False
    granted = custom_grant(user, 'purchase')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') == 'purchase_staff'
            or is_view_only(user))


def can_assign_purchase(user):
    """Admins / general managers may assign a lead to a purchase staff member
    and reopen a completed purchase & logistics record. Not lead-specific."""
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'queue.assign')
    if granted is not None:
        return granted
    return user.is_staff or getattr(user, 'is_general_manager', False)


def can_edit_purchase_logistics(user, lead):
    """Who may fill/complete a lead's purchase & logistics:

    - admins / general managers with purchase access (any lead)
    - a purchase_staff member ONLY for leads assigned to them

    The lead must already have been moved to purchase & logistics.
    """
    if not can_access_purchase(user) or is_view_only(user):
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
    granted = custom_grant(user, 'project')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') == 'project_manager'
            or is_view_only(user))


def can_assign_project(user):
    """Admins / general managers may assign a lead to a project manager and reopen
    a completed project. Not lead-specific."""
    if not user or not user.is_authenticated:
        return False
    if is_view_only(user):
        return False
    granted = custom_grant(user, 'queue.assign')
    if granted is not None:
        return granted
    return user.is_staff or getattr(user, 'is_general_manager', False)


def can_access_overdue_projects(user):
    """Who can open the Overdue Projects module.

    Its own permission key so a custom role can be given the escalation view
    without the working queue, or the other way round; otherwise it follows
    project access, since it is the same records past their deadline.
    """
    if not user or not user.is_authenticated:
        return False
    granted = custom_grant(user, 'project-overdue')
    if granted is not None:
        return granted
    return can_access_project(user)


def can_release_overdue_project(user):
    """Who may release an overdue project back to the project team: the super
    admin, and no one else.

    Deliberately not routed through ``custom_grant`` — the whole point of the
    Overdue queue is that a missed deadline stops being the project team's to
    edit, so the release cannot be handed out as a role permission.
    """
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser)


def can_edit_project(user, lead):
    """Who may fill/complete a lead's project:

    - admins / general managers with project access (any lead)
    - a project_manager ONLY for leads assigned to them

    The lead must already have been moved to the project stage.

    Once the 20-day deadline has passed the project is in the Overdue queue and
    nobody but a super admin may touch it, whatever their role — that lock is
    what the queue is for. Editing resumes when a super admin releases it with a
    fresh deadline.
    """
    if not can_access_project(user) or is_view_only(user):
        return False
    if not getattr(lead, 'pushed_to_project', False):
        return False
    project = getattr(lead, 'project', None)
    if project is not None and project.is_overdue and not can_release_overdue_project(user):
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
    granted = custom_grant(user, 'documentation')
    if granted is not None:
        return granted
    return (user.is_staff or getattr(user, 'is_general_manager', False)
            or getattr(user, 'role', '') in DOCUMENTATION_ROLES
            or is_view_only(user))


def can_edit_documentation_stage1(user, lead):
    """Who may fill/complete a lead's Documentation Stage 1:

    - admins / general & documentation managers with documentation access (any lead)
    - a documentation_staff member ONLY for leads assigned to them

    The lead must already have been pushed to documentation.

    NB: ``User.sees_all_leads`` is True for every documentation_staff (a *view*
    permission), so it must NOT be used here — this mirrors the assigned-only
    rule already enforced in the ``documentation_detail`` action.
    """
    if not can_access_documentation(user) or is_view_only(user):
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


def can_cleanup_deleted_lead(user):
    """Who may clear a deleted lead's leftovers out of a module.

    Super admin only, and deliberately not grantable through a custom role. The
    button destroys a module's record of a customer outright — the paperwork
    another department filed — so it sits above the admin tier rather than
    beside it.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return bool(getattr(user, 'is_superuser', False))
