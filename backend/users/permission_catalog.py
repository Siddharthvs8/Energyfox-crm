"""The permissions a custom user type can be granted.

Keys are deliberately the same slugs the sidebar and the module-count endpoint
already use, so a granted key maps straight onto "this module is visible and
usable" with no extra translation table to keep in sync.

Adding a permission here makes it appear in Settings → Roles & Permissions; it
takes effect wherever `leads.access.custom_grant` (or User.granted) is consulted.
"""

# (key, label, group) — group only drives the checkbox layout in Settings.
MODULE_PERMISSIONS = [
    ('dashboard', 'Dashboard', 'Core'),
    ('leads', 'Leads', 'Core'),
    ('converted', 'Converted Leads', 'Core'),
    ('closed-deals', 'Closed Deals', 'Core'),
    ('campaigns', 'Campaigns', 'Core'),
    ('calls', 'Calls', 'Core'),
    ('tasks', 'Tasks', 'Core'),

    ('documentation', 'Documentation Stage 1', 'Documentation'),
    ('documentation-stage2', 'Documentation Stage 2', 'Documentation'),
    ('documentation-status', 'Documentation Tracker', 'Documentation'),
    ('warranty', 'Warranty', 'Documentation'),
    ('discom-followup', 'Discom Follow-up', 'Documentation'),
    ('feasibility', 'KSEB Feasibility', 'Documentation'),

    ('accounts', 'Accounts', 'Money'),
    ('accounts/partially-paid', 'Partially Paid', 'Money'),
    ('accounts/fully-paid', 'Fully Paid', 'Money'),
    ('accounts/completed', 'Completed Projects', 'Money'),

    ('purchase', 'Purchase & Logistics', 'Operations'),
    ('project', 'Project', 'Operations'),
    ('project-overdue', 'Overdue Projects', 'Operations'),
    ('service', 'Service', 'Operations'),
    ('liasoning', 'Liasoning', 'Operations'),
    ('periodic-maintenance', 'Periodic Maintenance', 'Operations'),
    ('emergency-service', 'Emergency Service', 'Operations'),
    ('inventory', 'Inventory / Stock Register', 'Operations'),

    ('leaderboard', 'Leaderboard', 'People'),
    ('my-performance', 'My Performance', 'People'),
    ('team-performance', 'Team Performance', 'People'),
    ('team', 'Team', 'People'),
    ('branches', 'Branches', 'People'),

    ('automations', 'Automations', 'Admin'),
    ('meta', 'Meta Integration', 'Admin'),
    ('settings', 'Settings', 'Admin'),
]

# Things a user can *do*, beyond which screens they can open.
CAPABILITY_PERMISSIONS = [
    ('leads.view_all', 'See all leads (not only their own)', 'Lead capabilities'),
    ('leads.add', 'Add leads', 'Lead capabilities'),
    ('leads.edit', 'Edit lead details', 'Lead capabilities'),
    ('leads.delete', 'Delete leads (move to Trash)', 'Lead capabilities'),
    ('leads.tools', 'CSV template / export, Archived and Trash views', 'Lead capabilities'),
    ('leads.assign', 'Assign leads to someone', 'Lead capabilities'),
    ('leads.status', 'Change a lead status', 'Lead capabilities'),
    ('leads.mark_lost', 'Mark a converted deal as lost', 'Lead capabilities'),
    ('queue.assign', 'Assign work within their modules', 'Lead capabilities'),
]

ALL_PERMISSIONS = MODULE_PERMISSIONS + CAPABILITY_PERMISSIONS
ALL_PERMISSION_KEYS = {key for key, _label, _group in ALL_PERMISSIONS}


def catalog():
    """Serialisable form for Settings → Roles & Permissions."""
    return {
        'modules': [{'key': k, 'label': l, 'group': g} for k, l, g in MODULE_PERMISSIONS],
        'capabilities': [{'key': k, 'label': l, 'group': g} for k, l, g in CAPABILITY_PERMISSIONS],
    }


def clean_permissions(values):
    """Keep only keys we actually know about, de-duplicated and ordered."""
    if not isinstance(values, (list, tuple, set)):
        return []
    wanted = {str(v).strip() for v in values if str(v or '').strip()}
    return [k for k, _l, _g in ALL_PERMISSIONS if k in wanted]
