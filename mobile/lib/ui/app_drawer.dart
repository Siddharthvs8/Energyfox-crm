import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api_client.dart';
import '../state/auth.dart';
import '../state/nav.dart';
import '../state/stores.dart';
import '../theme.dart';
import 'module_screen.dart';
import 'widgets/common.dart';

/// The hamburger drawer: every module this account can open.
///
/// The web app puts four modules on the bottom bar and everything else behind
/// the hamburger; this is that everything else, built from the same list and
/// the same role rules (see `lib/state/nav.dart`), with the same work-waiting
/// badges. A module the app carries itself opens here; one whose paperwork
/// belongs on a big screen opens in the browser and says so.
class AppDrawer extends StatelessWidget {
  const AppDrawer({
    super.key,
    required this.current,
    required this.onOpenTab,
  });

  /// The tab showing behind the drawer, so its row reads as the current one.
  final AppTab current;
  final void Function(AppTab tab) onOpenTab;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final counts = context.watch<ModuleCountStore>();
    final modules = visibleModules(auth.user);

    return Drawer(
      width: 296,
      backgroundColor: Brand.navy,
      child: SafeArea(
        child: Column(
          children: [
            _Header(orgName: auth.orgName),
            Divider(height: 1, color: Colors.white.withValues(alpha: 0.06)),
            Expanded(
              child: modules.isEmpty
                  ? const _NoModules()
                  : ListView(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 10),
                      children: [
                        for (final m in modules)
                          _ModuleRow(
                            module: m,
                            badge: counts[m.key],
                            selected: m.tab != null && m.tab == current,
                            onTap: () => _open(context, m),
                          ),
                      ],
                    ),
            ),
            Divider(height: 1, color: Colors.white.withValues(alpha: 0.06)),
            _Footer(onProfile: () {
              Navigator.of(context).pop();
              onOpenTab(AppTab.profile);
            }),
          ],
        ),
      ),
    );
  }

  Future<void> _open(BuildContext context, NavModule module) async {
    HapticFeedback.selectionClick();
    final navigator = Navigator.of(context);
    if (module.tab != null) {
      navigator.pop();
      onOpenTab(module.tab!);
      return;
    }
    if (module.queue != null) {
      navigator.pop();
      navigator.push(MaterialPageRoute(
        builder: (_) => ModuleScreen(module: module),
      ));
      return;
    }
    // No screen of its own: hand it to the browser, where the desktop CRM is.
    final base = context.read<ApiClient>().baseUrl;
    final messenger = ScaffoldMessenger.of(context);
    navigator.pop();
    final opened = base.isNotEmpty &&
        await launchUrl(Uri.parse('$base${module.path}'),
            mode: LaunchMode.externalApplication);
    if (!opened) {
      messenger.showSnackBar(SnackBar(
        content: Text('Could not open ${module.label} in a browser.'),
      ));
    }
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.orgName});

  final String orgName;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(18, 16, 12, 16),
      child: Row(
        children: [
          const BrandMark(size: 38, radius: 12),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  orgName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14.5,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.2),
                ),
                const SizedBox(height: 1),
                Text('Workspace',
                    style: TextStyle(
                        fontSize: 10.5,
                        color: Colors.white.withValues(alpha: 0.45))),
              ],
            ),
          ),
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.close_rounded, size: 20),
            color: Colors.white.withValues(alpha: 0.5),
            tooltip: 'Close menu',
          ),
        ],
      ),
    );
  }
}

class _ModuleRow extends StatelessWidget {
  const _ModuleRow({
    required this.module,
    required this.badge,
    required this.selected,
    required this.onTap,
  });

  final NavModule module;
  final int badge;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final tint = selected ? Brand.amber : Colors.white.withValues(alpha: 0.62);
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Material(
        color: selected ? Colors.white.withValues(alpha: 0.08) : Colors.transparent,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
            child: Row(
              children: [
                Icon(module.icon, size: 19, color: tint),
                const SizedBox(width: 13),
                Expanded(
                  child: Text(
                    module.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13.5,
                      fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
                      color: selected
                          ? Colors.white
                          : Colors.white.withValues(alpha: 0.82),
                    ),
                  ),
                ),
                if (module.opensInBrowser)
                  Icon(Icons.open_in_new_rounded,
                      size: 14, color: Colors.white.withValues(alpha: 0.3)),
                if (badge > 0) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(
                      color: Brand.danger,
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(
                      badge > 99 ? '99+' : '$badge',
                      style: const TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w800,
                          color: Colors.white),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Footer extends StatelessWidget {
  const _Footer({required this.onProfile});

  final VoidCallback onProfile;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final api = context.read<ApiClient>();
    final user = auth.user;

    return InkWell(
      onTap: onProfile,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 13, 14, 15),
        child: Row(
          children: [
            InitialsAvatar(
              text: user?.initials ?? '?',
              size: 36,
              imageUrl: api.absoluteMedia(user?.avatarUrl),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    user?.name ?? 'Signed in',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 13.5,
                        fontWeight: FontWeight.w700),
                  ),
                  Text(
                    auth.readOnly
                        ? 'View only'
                        : (user?.roleLabel.isNotEmpty ?? false)
                            ? user!.roleLabel
                            : 'Profile & settings',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 11,
                        color: Colors.white.withValues(alpha: 0.5)),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded,
                size: 20, color: Colors.white.withValues(alpha: 0.4)),
          ],
        ),
      ),
    );
  }
}

class _NoModules extends StatelessWidget {
  const _NoModules();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Text(
          'Your account has no other modules yet.',
          textAlign: TextAlign.center,
          style: TextStyle(
              fontSize: 13,
              height: 1.5,
              color: Colors.white.withValues(alpha: 0.55)),
        ),
      ),
    );
  }
}
