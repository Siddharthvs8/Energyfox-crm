/// Every module in the CRM, and who gets to see it.
///
/// This is a port of the web app's sidebar — `frontend/src/app/(crm)/layout.tsx`
/// — module for module and rule for rule, because a phone showing a different
/// set of modules from the browser on the same account is a bug report every
/// time. Keys are the slugs the web routes, the permission catalogue and
/// `/api/leads/module-counts/` all already use, so a badge, a permission and a
/// drawer row never need translating between each other.
///
/// What the app does with a module depends on what it has:
///   * [tab]   — the four modules the field app carries itself, on the bottom bar
///   * [queue] — a work queue, listed natively from its own endpoint
///   * neither — opens in the browser, where the paperwork it involves belongs
library;

import 'package:flutter/material.dart';

import '../api/models.dart';


enum AppTab { home, leads, calls, tasks, profile }

/// How a work queue is fetched and how its rows read. The queue endpoints all
/// answer with the same customer shape (name, phone, place, value, who is on
/// it) plus the module's own fields, which is what lets one screen list any of
/// them — see `_documentation_payload` and friends in `leads/views.py`.
class QueueSource {
  const QueueSource(
    this.path, {
    this.query,
    this.rootKey,
    this.paged = false,
    this.doneKey,
    this.assigneeKey,
    this.assigneeLabel,
    this.dateKey = 'pushed_at',
    this.dateLabel = 'Arrived',
  });

  final String path;
  final Map<String, dynamic>? query;

  /// The key the rows sit under, when the endpoint answers with an object
  /// rather than a bare list (closed deals return a board plus its summary).
  final String? rootKey;

  /// True for the endpoints that page like the lead list does.
  final bool paged;

  /// The boolean that says this row's work is finished.
  final String? doneKey;
  final String? assigneeKey;
  final String? assigneeLabel;
  final String dateKey;
  final String dateLabel;
}

class NavModule {
  const NavModule({
    required this.key,
    required this.label,
    required this.icon,
    this.tab,
    this.queue,
    this.webPath,
  });

  /// The slug: the web route, the permission key and the badge key, all one
  /// thing.
  final String key;
  final String label;
  final IconData icon;
  final AppTab? tab;
  final QueueSource? queue;

  /// Where it lives in the web app, when that differs from `/key`.
  final String? webPath;

  String get path => webPath ?? '/$key';

  /// Nothing native to show — the drawer hands it to the browser.
  bool get opensInBrowser => tab == null && queue == null;
}

// ── Role sets, mirroring the web sidebar (and the server behind it) ──────────

const _b2bOnlyRoles = {'store_manager', 'store_keeper', 'accounts_b2b'};
const _companyPerformanceRoles = {'superadmin', 'admin', 'coo'};
const _closedDealsRoles = {
  'superadmin', 'admin', 'coo', 'sales_manager', 'leads_manager',
  'branch_manager', 'bde', 'tele_caller',
};
const _docOnlyRoles = {'documentation_staff', 'documentation_manager'};
const _accountsOnlyRoles = {'accounts_staff', 'accounts_manager'};

/// The four modules the bottom bar carries, in the order they sit in. Same list
/// as the web app's `TAB_BAR_HREFS`, and filtered through the same role rules,
/// so a role that cannot open Calls gets three tabs rather than one that
/// answers 403.
const tabBarKeys = ['dashboard', 'leads', 'calls', 'tasks'];

/// One module plus the gate it is shown behind. The flags are the web
/// sidebar's, kept by name so the two lists can be read side by side.
class _Entry {
  const _Entry(
    this.module, {
    this.leadsDesk = false,
    this.closedDeals = false,
    this.managerFeature = false,
    this.managerOnly = false,
    this.hideForManager = false,
    this.adminOnly = false,
    this.strictAdminOnly = false,
    this.adminAndSuperOnly = false,
    this.companyPerformance = false,
    this.docFeature = false,
    this.docTracker = false,
    this.docStage2 = false,
    this.warranty = false,
    this.feasibility = false,
    this.accounts = false,
    this.paymentBucket = false,
    this.completedProjects = false,
    this.purchase = false,
    this.pm = false,
    this.liasoning = false,
    this.inventory = false,
    this.inB2B = false,
  });

  final NavModule module;
  final bool leadsDesk;
  final bool closedDeals;
  final bool managerFeature;
  final bool managerOnly;
  final bool hideForManager;
  final bool adminOnly;
  final bool strictAdminOnly;
  final bool adminAndSuperOnly;
  final bool companyPerformance;
  final bool docFeature;
  final bool docTracker;
  final bool docStage2;
  final bool warranty;
  final bool feasibility;
  final bool accounts;
  final bool paymentBucket;
  final bool completedProjects;
  final bool purchase;
  final bool pm;
  final bool liasoning;
  final bool inventory;
  final bool inB2B;

  /// What a custom user type's permission list is checked against. The module
  /// slugs and the permission keys are deliberately the same strings — see
  /// `users/permission_catalog.py`.
  String get permKey => module.key;
}

const _catalog = <_Entry>[
  _Entry(NavModule(
      key: 'dashboard',
      label: 'Dashboard',
      icon: Icons.space_dashboard_rounded,
      tab: AppTab.home,
      webPath: '/')),
  _Entry(
    NavModule(
        key: 'leads',
        label: 'Leads',
        icon: Icons.groups_2_rounded,
        tab: AppTab.leads),
    leadsDesk: true,
  ),
  _Entry(NavModule(
    key: 'converted',
    label: 'Converted Leads',
    icon: Icons.how_to_reg_rounded,
    queue: QueueSource('/api/leads/',
        query: {'status': 'converted', 'ordering': '-status_changed_at'},
        paged: true,
        dateKey: 'status_changed_at',
        dateLabel: 'Converted'),
  )),
  _Entry(
    NavModule(
      key: 'closed-deals',
      label: 'Closed Deals',
      icon: Icons.emoji_events_rounded,
      queue: QueueSource('/api/leads/closed-deals/',
          rootKey: 'deals',
          doneKey: 'payment_verified',
          assigneeKey: 'tele_caller_name',
          assigneeLabel: 'Owner',
          dateKey: 'closed_on',
          dateLabel: 'Closed'),
    ),
    closedDeals: true,
    leadsDesk: true,
  ),
  _Entry(
    NavModule(
        key: 'campaigns',
        label: 'Campaigns',
        icon: Icons.campaign_rounded),
    managerFeature: true,
    leadsDesk: true,
  ),
  _Entry(NavModule(
      key: 'calls',
      label: 'Calls',
      icon: Icons.call_rounded,
      tab: AppTab.calls)),
  _Entry(NavModule(
      key: 'tasks',
      label: 'Tasks',
      icon: Icons.checklist_rounded,
      tab: AppTab.tasks)),
  _Entry(
    NavModule(
        key: 'inventory',
        label: 'Inventory',
        icon: Icons.inventory_2_rounded),
    inventory: true,
    inB2B: true,
  ),
  _Entry(NavModule(
      key: 'leaderboard',
      label: 'Leaderboard',
      icon: Icons.leaderboard_rounded)),
  _Entry(
    NavModule(
        key: 'my-performance',
        label: 'My Performance',
        icon: Icons.show_chart_rounded),
    hideForManager: true,
  ),
  _Entry(
    NavModule(
        key: 'team-performance',
        label: 'Team Performance',
        icon: Icons.insights_rounded),
    managerOnly: true,
  ),
  _Entry(
    NavModule(
        key: 'company-performance',
        label: 'Company Performance',
        icon: Icons.apartment_rounded),
    companyPerformance: true,
  ),
  _Entry(
    NavModule(
        key: 'manager',
        label: 'Manager',
        icon: Icons.admin_panel_settings_rounded),
    managerFeature: true,
  ),
  _Entry(
    NavModule(
        key: 'automations', label: 'Automations', icon: Icons.bolt_rounded),
    adminOnly: true,
  ),
  _Entry(
    NavModule(key: 'meta', label: 'Meta Integration', icon: Icons.hub_rounded),
    strictAdminOnly: true,
    leadsDesk: true,
  ),
  _Entry(
    NavModule(key: 'team', label: 'Team', icon: Icons.people_alt_rounded),
    inB2B: true,
  ),
  _Entry(
    NavModule(
        key: 'branches',
        label: 'Branches',
        icon: Icons.account_balance_rounded),
    adminOnly: true,
  ),
  _Entry(
    NavModule(
      key: 'documentation',
      label: 'Documentation Stage 1',
      icon: Icons.description_rounded,
      queue: QueueSource('/api/leads/documentation/',
          doneKey: 'stage1_complete',
          assigneeKey: 'documentation_staff_name',
          assigneeLabel: 'Doc staff'),
    ),
    docFeature: true,
  ),
  _Entry(
    NavModule(
      key: 'documentation-status',
      label: 'Documentation',
      icon: Icons.fact_check_rounded,
      queue: QueueSource('/api/leads/documentation-overview/',
          assigneeKey: 'documentation_staff_name', assigneeLabel: 'Doc staff'),
    ),
    docTracker: true,
  ),
  _Entry(
    NavModule(
      key: 'documentation-stage2',
      label: 'Documentation Stage 2',
      icon: Icons.description_outlined,
      queue: QueueSource('/api/leads/documentation-stage2/',
          doneKey: 'is_complete',
          assigneeKey: 'doc_stage2_staff_name',
          assigneeLabel: 'Doc staff'),
    ),
    docStage2: true,
  ),
  _Entry(
    NavModule(
      key: 'warranty',
      label: 'Warranty',
      icon: Icons.verified_user_rounded,
      queue: QueueSource('/api/leads/warranty/', doneKey: 'is_complete'),
    ),
    warranty: true,
  ),
  _Entry(
    NavModule(
      key: 'feasibility',
      label: 'KSEB Feasibility',
      icon: Icons.solar_power_rounded,
      queue: QueueSource('/api/leads/bde-feasibility/',
          doneKey: 'kseb_feasibility_complete',
          assigneeKey: 'bde_name',
          assigneeLabel: 'BDE'),
    ),
    feasibility: true,
  ),
  _Entry(
    NavModule(
      key: 'accounts',
      label: 'Accounts',
      icon: Icons.account_balance_wallet_rounded,
      queue: QueueSource('/api/leads/accounts/',
          doneKey: 'payment_complete',
          assigneeKey: 'accounts_staff_name',
          assigneeLabel: 'Accounts'),
    ),
    accounts: true,
  ),
  _Entry(
    NavModule(
      key: 'accounts/partially-paid',
      label: 'Partially Paid',
      icon: Icons.pie_chart_rounded,
      queue: QueueSource('/api/leads/accounts-partially-paid/',
          doneKey: 'payment_complete'),
    ),
    paymentBucket: true,
  ),
  _Entry(
    NavModule(
      key: 'accounts/fully-paid',
      label: 'Fully Paid',
      icon: Icons.paid_rounded,
      queue: QueueSource('/api/leads/accounts-fully-paid/',
          doneKey: 'payment_complete'),
    ),
    paymentBucket: true,
  ),
  _Entry(
    NavModule(
      key: 'accounts/completed',
      label: 'Completed Projects',
      icon: Icons.task_alt_rounded,
      queue: QueueSource('/api/leads/accounts-completed/',
          doneKey: 'rf_pushed',
          dateKey: 'project_completed_at',
          dateLabel: 'Completed'),
    ),
    completedProjects: true,
  ),
  _Entry(
    NavModule(
      key: 'purchase',
      label: 'Purchase & Logistics',
      icon: Icons.local_shipping_rounded,
      queue: QueueSource('/api/leads/purchase/',
          doneKey: 'purchase_complete',
          assigneeKey: 'purchase_staff_name',
          assigneeLabel: 'Purchase'),
    ),
    purchase: true,
  ),
  _Entry(
    NavModule(
      key: 'project',
      label: 'Project',
      icon: Icons.engineering_rounded,
      queue: QueueSource('/api/leads/project/',
          doneKey: 'project_complete',
          assigneeKey: 'project_manager_name',
          assigneeLabel: 'Project manager'),
    ),
    pm: true,
  ),
  _Entry(
    NavModule(
      key: 'project-overdue',
      label: 'Overdue Projects',
      icon: Icons.warning_amber_rounded,
      queue: QueueSource('/api/leads/project-overdue/',
          doneKey: 'project_complete',
          assigneeKey: 'project_manager_name',
          assigneeLabel: 'Project manager'),
    ),
    pm: true,
  ),
  _Entry(
    NavModule(
      key: 'service',
      label: 'Service',
      icon: Icons.build_rounded,
      queue: QueueSource('/api/service-entries/',
          dateKey: 'scheduled_date', dateLabel: 'Scheduled'),
    ),
    pm: true,
  ),
  _Entry(
    NavModule(
        key: 'team-stats',
        label: 'Team Stats',
        icon: Icons.query_stats_rounded),
    pm: true,
  ),
  _Entry(
    NavModule(
      key: 'liasoning',
      label: 'Liasoning',
      icon: Icons.assignment_turned_in_rounded,
      queue: QueueSource('/api/leads/liasoning/',
          doneKey: 'is_complete'),
    ),
    liasoning: true,
  ),
  _Entry(
    NavModule(
      key: 'discom-followup',
      label: 'Discom Follow-up',
      icon: Icons.electrical_services_rounded,
      queue: QueueSource('/api/leads/discom-followup/'),
    ),
    liasoning: true,
  ),
  _Entry(
    NavModule(
      key: 'periodic-maintenance',
      label: 'Periodic Maintenance',
      icon: Icons.event_repeat_rounded,
      queue: QueueSource('/api/leads/periodic-maintenance/',
          rootKey: 'scheduled',
          dateKey: 'next_due',
          dateLabel: 'Next visit'),
    ),
    liasoning: true,
  ),
  _Entry(
    NavModule(
      key: 'emergency-service',
      label: 'Emergency Service',
      icon: Icons.emergency_rounded,
      queue: QueueSource('/api/emergency-services/',
          dateKey: 'created_at', dateLabel: 'Logged'),
    ),
    liasoning: true,
  ),
  _Entry(
    NavModule(
        key: 'activity-log',
        label: 'Activity Log',
        icon: Icons.history_rounded),
    adminAndSuperOnly: true,
  ),
  _Entry(
    NavModule(
        key: 'settings', label: 'Settings', icon: Icons.settings_rounded),
    adminOnly: true,
  ),
];

/// The modules this account may open, in sidebar order.
///
/// Read this beside the web app's `navItems` filter: the order of the tests is
/// the order of that one, because the tests are not independent — the focused
/// roles return early and must be asked about before the general rules.
List<NavModule> visibleModules(AppUser? user) {
  final role = user?.role ?? '';
  final spectator = user?.readOnly ?? false;
  final isStaff = user?.isStaff ?? false;
  final isGm = user?.isGeneralManager ?? false;
  final isManager = user?.isManager ?? false;
  // A spectator watches the whole company and changes none of it: every module
  // an admin can open, and no working button inside them. They hold neither
  // flag on purpose — those are what the write gates read — so module
  // visibility is asked through this instead.
  final seesAllModules = isStaff || isGm || spectator;
  final onCustomRole = user?.onCustomRole ?? false;
  final perms = user?.permissions ?? const <String>[];

  final b2bOnly = _b2bOnlyRoles.contains(role);
  final docOnly = _docOnlyRoles.contains(role);
  final accountsOnly = _accountsOnlyRoles.contains(role);
  final purchaseOnly = role == 'purchase_staff';
  final pmOnly = role == 'project_manager';
  final liasoningOnly = role == 'liasoning_officer';
  final leadsDeskOnly = role == 'leads_manager';

  bool show(_Entry e) {
    if (e.inventory) {
      // The wholesale side's staff always have the stock register; on the
      // retail side it is the admin/GM module it always was.
      if (b2bOnly) return true;
      return onCustomRole ? perms.contains('inventory') : seesAllModules;
    }
    // A custom user type is decided purely by its permission list — none of the
    // role rules below apply to it.
    if (onCustomRole) return perms.contains(e.permKey);
    if (b2bOnly) return e.inB2B;
    if (docOnly) return e.docFeature || e.docStage2 || e.warranty;
    if (liasoningOnly) return e.liasoning;
    if (leadsDeskOnly) return e.leadsDesk;
    if (accountsOnly) return e.accounts || e.completedProjects || e.paymentBucket;
    if (purchaseOnly) return e.purchase;
    if (pmOnly) return e.pm;
    // The work queues below belong to their own team (handled above) plus the
    // admins and general managers who oversee them.
    if (e.docFeature) return false;
    if (e.docStage2 ||
        e.warranty ||
        e.liasoning ||
        e.accounts ||
        e.completedProjects ||
        e.paymentBucket ||
        e.purchase ||
        e.pm) {
      return seesAllModules;
    }
    if (e.companyPerformance) {
      return _companyPerformanceRoles.contains(role) || spectator;
    }
    if (e.closedDeals) return _closedDealsRoles.contains(role) || spectator;
    // The read-only documentation tracker — everyone except the doc team, who
    // have their own work queue.
    if (e.docTracker) return true;
    if (e.feasibility) return role == 'bde' || seesAllModules || isManager;
    if (e.strictAdminOnly) return isStaff || spectator;
    // Narrower than strictAdminOnly on purpose: a record of who changed what —
    // roles and money included — is not a watching brief.
    if (e.adminAndSuperOnly) return role == 'admin' || role == 'superadmin';
    if (e.adminOnly) return seesAllModules;
    if (e.managerFeature) return seesAllModules || isManager;
    if (e.managerOnly) return isManager && !isStaff && !isGm;
    if (e.hideForManager) {
      // Hidden for branch managers and admins (they have the team views), and
      // for anyone who has Company Performance: the top of the house answers
      // for the company's numbers, not a personal target.
      if (_companyPerformanceRoles.contains(role)) return false;
      return !((isManager && !isGm) || isStaff);
    }
    return true;
  }

  return [for (final e in _catalog) if (show(e)) e.module];
}

/// The bottom bar: the tab modules this account can open, in tab-bar order,
/// with Profile always last — it is the account itself, not a module.
List<NavModule> tabModules(AppUser? user) {
  final visible = visibleModules(user);
  return [
    for (final key in tabBarKeys)
      ...visible.where((m) => m.key == key && m.tab != null),
  ];
}
