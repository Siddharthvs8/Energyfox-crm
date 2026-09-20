import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../state/auth.dart';
import '../state/nav.dart';
import '../state/stores.dart';
import 'app_drawer.dart';
import 'calls_screen.dart';
import 'dashboard_screen.dart';
import 'lead_form_screen.dart';
import 'leads_screen.dart';
import 'module_screen.dart';
import 'profile_screen.dart';
import 'task_editor.dart';
import 'tasks_screen.dart';
import 'widgets/app_top_bar.dart';

/// The app frame: the modules this account works every day along the bottom,
/// everything else behind the hamburger, and one create button that appears
/// only when there is something this account may actually create.
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  late AppTab _tab = _initialTab();
  late final ModuleCountStore _counts = context.read<ModuleCountStore>();
  late final NotificationStore _notifications =
      context.read<NotificationStore>();

  /// The manifest's home-screen shortcuts land on `?tab=leads` / `?tab=tasks`,
  /// so a long-press on the app icon opens where it says it will.
  static AppTab _initialTab() => switch (Uri.base.queryParameters['tab']) {
        'leads' => AppTab.leads,
        'calls' => AppTab.calls,
        'tasks' => AppTab.tasks,
        'profile' => AppTab.profile,
        _ => AppTab.home,
      };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<DashboardStore>().load();
      context.read<LeadStore>().load();
      context.read<TaskStore>().load();
      // The badges and the bell keep themselves up to date for as long as
      // somebody is signed in.
      _counts.start();
      _notifications.start();
    });
  }

  @override
  void dispose() {
    // Signing out takes this frame down: the pollers stop with it rather than
    // going on knocking with a dead token.
    _counts.stop();
    _notifications.stop();
    super.dispose();
  }

  void _go(AppTab tab) {
    if (tab == _tab) return;
    HapticFeedback.selectionClick();
    setState(() => _tab = tab);
    if (tab == AppTab.calls) context.read<CallStore>().load();
  }

  Future<void> _create(AppTab tab) async {
    HapticFeedback.lightImpact();
    if (tab == AppTab.tasks) {
      await openTaskEditor(context);
      return;
    }
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const LeadFormScreen()),
    );
  }

  Widget _screenFor(AppTab tab) => switch (tab) {
        AppTab.home => DashboardScreen(onOpenTab: _go),
        AppTab.leads => const LeadsScreen(),
        AppTab.calls => const CallsScreen(),
        AppTab.tasks => const TasksScreen(),
        AppTab.profile => const ProfileScreen(),
      };

  static const _labels = {
    AppTab.home: 'Dashboard',
    AppTab.leads: 'Leads',
    AppTab.calls: 'Calls',
    AppTab.tasks: 'Tasks',
    AppTab.profile: 'Profile',
  };

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    // The bottom bar is the tab modules this account can open — a role without
    // Calls gets three tabs rather than one that answers 403 — with Profile
    // always last, because that is the account itself and not a module.
    final field = tabModules(auth.user);
    // The fulfilment roles (documentation, accounts, purchase, the project
    // manager, liasoning) have no field tabs at all: their work is a queue, so
    // that queue is their home, the way the web app drops them straight into it
    // instead of a dashboard they have no use for.
    final home = field.isEmpty
        ? visibleModules(auth.user).where((m) => m.queue != null).firstOrNull
        : null;
    final tabs = [
      ...field.map((m) => m.tab!),
      if (home != null) AppTab.home,
      AppTab.profile,
    ];
    // A role change (or a first identity load) can take the tab we are on off
    // the bar; fall back to the first one it does carry.
    final tab = tabs.contains(_tab) ? _tab : tabs.first;

    return Scaffold(
      appBar: AppTopBar(
        title: tab == AppTab.home && home != null ? home.label : _labels[tab]!,
        onProfile: () => _go(AppTab.profile),
      ),
      drawer: AppDrawer(current: tab, onOpenTab: _go),
      body: IndexedStack(
        index: tabs.indexOf(tab),
        children: [
          for (final t in tabs)
            if (t == AppTab.home && home != null)
              ModuleScreen(module: home, embedded: true)
            else
              _screenFor(t),
        ],
      ),
      floatingActionButton: _fab(auth, tab, queueHome: home != null),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tabs.indexOf(tab),
        onDestinationSelected: (i) => _go(tabs[i]),
        destinations: [
          for (final t in tabs)
            if (t == AppTab.home && home != null)
              NavigationDestination(icon: Icon(home.icon), label: 'Queue')
            else
              _destination(context, t),
        ],
      ),
    );
  }

  /// The create button, and what it would create.
  ///
  /// Shown only where this account has something to create *and* may create it:
  /// a BDE receives leads rather than sourcing them, a spectator writes nothing
  /// at all, and a custom user type is decided by the keys its role was granted
  /// — all three the same rules `leads/access.py` enforces. The button used to
  /// appear for everyone, which meant offering a form the server would refuse.
  Widget? _fab(AuthController auth, AppTab tab, {required bool queueHome}) {
    final leadTab = !queueHome && (tab == AppTab.home || tab == AppTab.leads);
    if (tab == AppTab.tasks && auth.canAddTasks) {
      return FloatingActionButton(
        onPressed: () => _create(tab),
        elevation: 2,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        tooltip: 'New task',
        child: const Icon(Icons.add_task_rounded),
      );
    }
    if (leadTab && auth.canAddLeads) {
      return FloatingActionButton(
        onPressed: () => _create(tab),
        elevation: 2,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        tooltip: 'New lead',
        child: const Icon(Icons.person_add_alt_1),
      );
    }
    return null;
  }

  NavigationDestination _destination(BuildContext context, AppTab tab) {
    switch (tab) {
      case AppTab.home:
        return const NavigationDestination(
          icon: Icon(Icons.space_dashboard_outlined),
          selectedIcon: Icon(Icons.space_dashboard_rounded),
          label: 'Home',
        );
      case AppTab.leads:
        return const NavigationDestination(
          icon: Icon(Icons.groups_2_outlined),
          selectedIcon: Icon(Icons.groups_2_rounded),
          label: 'Leads',
        );
      case AppTab.calls:
        return const NavigationDestination(
          icon: Icon(Icons.call_outlined),
          selectedIcon: Icon(Icons.call_rounded),
          label: 'Calls',
        );
      case AppTab.tasks:
        final overdue = context.watch<TaskStore>().overdueCount;
        return NavigationDestination(
          icon: _TaskIcon(icon: Icons.checklist_rounded, badge: overdue),
          selectedIcon: _TaskIcon(icon: Icons.checklist_rtl_rounded, badge: overdue),
          label: 'Tasks',
        );
      case AppTab.profile:
        return const NavigationDestination(
          icon: Icon(Icons.person_outline_rounded),
          selectedIcon: Icon(Icons.person_rounded),
          label: 'Profile',
        );
    }
  }
}

class _TaskIcon extends StatelessWidget {
  const _TaskIcon({required this.icon, required this.badge});

  final IconData icon;
  final int badge;

  @override
  Widget build(BuildContext context) {
    if (badge <= 0) return Icon(icon);
    return Badge.count(
      count: badge,
      backgroundColor: Theme.of(context).colorScheme.error,
      child: Icon(icon),
    );
  }
}
