"""What is worth recording, and which module it belongs to.

An allow-list rather than "everything". Auditing every model in the project
would fill the log with session rows, token refreshes and the audit entries
themselves — noise that buries the one line somebody is looking for, and in the
last case a loop.

A model not listed here is simply not recorded, which is the safe default: the
log stays readable, and adding a module is one line.
"""

# app_label -> the module name a person would look for it under.
CATEGORY_BY_APP = {
    'leads': 'Leads',
    'users': 'Users',
    'tasks': 'Tasks',
    'calls': 'Calls',
    'campaigns': 'Campaigns',
    'automations': 'Automations',
    'inventory': 'Inventory',
    'organization': 'Settings',
    'messaging': 'Messaging',
    'ai_manager': 'Targets',
}

# Where the app is too coarse. The leads app holds the whole pipeline, so a
# change to a payment and a change to a site visit would otherwise both read as
# "Leads" — and the person looking for one does not want the other.
CATEGORY_BY_MODEL = {
    'leads.PaymentVerification': 'Accounts',
    'leads.BalancePayment': 'Accounts',
    'leads.SiteVisit': 'Site Visits',
    'leads.DocumentationStage1': 'Documentation',
    'leads.DocumentationStage2': 'Documentation',
    'leads.TrackingLink': 'Documentation',
    'leads.PurchaseLogistics': 'Purchase & Logistics',
    'leads.Project': 'Projects',
    'leads.LiasoningService': 'Liasoning',
    'leads.Warranty': 'Warranty',
    'leads.ServiceEntry': 'Service',
    'leads.EmergencyService': 'Service',
    'leads.PeriodicMaintenance': 'Maintenance',
    'leads.MaintenanceVisit': 'Maintenance',
    'leads.Product': 'Inventory',
    'leads.District': 'Settings',
    'leads.IntegrationSettings': 'Settings',
    'leads.TeamStatsConfig': 'Settings',
}

# Recorded. Anything outside this list is ignored.
AUDITED = {
    # ── The pipeline ──
    'leads.Lead', 'leads.SiteVisit', 'leads.DocumentationStage1',
    'leads.DocumentationStage2', 'leads.PaymentVerification', 'leads.BalancePayment',
    'leads.PurchaseLogistics', 'leads.Project', 'leads.LiasoningService',
    'leads.Warranty', 'leads.ServiceEntry', 'leads.EmergencyService',
    'leads.PeriodicMaintenance', 'leads.MaintenanceVisit', 'leads.TrackingLink',
    'leads.Product', 'leads.District', 'leads.IntegrationSettings',
    'leads.TeamStatsConfig',
    # ── People and their powers ──
    'users.User', 'users.CustomRole',
    # ── Work ──
    'tasks.Task', 'calls.Call', 'campaigns.Campaign',
    'automations.Automation',
    # ── Money and stock ──
    'inventory.ProjectSpec', 'inventory.Quotation', 'inventory.QuotationCost',
    'inventory.Quote', 'inventory.SalesOrder', 'inventory.PurchaseOrder',
    'inventory.Vendor', 'inventory.StockItem',
    # ── Company settings ──
    'organization.OrgSettings',
}

# Never recorded, whatever else says. Passwords and tokens must not reach a log
# that admins read, and `last_login` would write a row every time anyone signs
# in — a change nobody made.
REDACTED_FIELDS = {
    'password', 'token', 'access_token', 'refresh_token', 'api_key',
    'secret', 'client_secret', 'page_access_token', 'signature',
}
IGNORED_FIELDS = {
    'updated_at', 'created_at', 'last_login', 'modified_at',
    # Counters that move on their own, not edits anybody made.
    'view_count', 'last_viewed_at',
}


def is_audited(model):
    return label_for(model) in AUDITED


def label_for(model):
    return f'{model._meta.app_label}.{model.__name__}'


def category_for(model):
    label = label_for(model)
    if label in CATEGORY_BY_MODEL:
        return CATEGORY_BY_MODEL[label]
    return CATEGORY_BY_APP.get(model._meta.app_label, 'Other')


def categories():
    """Every category the filter can offer, in a settled order."""
    return sorted({*CATEGORY_BY_APP.values(), *CATEGORY_BY_MODEL.values()})
