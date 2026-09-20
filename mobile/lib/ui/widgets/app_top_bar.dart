import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../state/auth.dart';
import '../../state/stores.dart';
import '../notifications_sheet.dart';
import 'common.dart';

/// The bar at the top of every tab: the hamburger, where you are, and the two
/// controls that belong at the top of an app — alerts and you.
///
/// The same four things the web app puts there on a phone, so somebody moving
/// between the browser and the app reaches for the same corners.
class AppTopBar extends StatelessWidget implements PreferredSizeWidget {
  const AppTopBar({
    super.key,
    required this.title,
    required this.onProfile,
    this.actions = const [],
  });

  final String title;
  final VoidCallback onProfile;

  /// The screen's own controls, left of the bell.
  final List<Widget> actions;

  @override
  Size get preferredSize => const Size.fromHeight(56);

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final notifications = context.watch<NotificationStore>();
    final counts = context.watch<ModuleCountStore>();
    final api = context.read<ApiClient>();
    final scheme = Theme.of(context).colorScheme;
    final dark = Theme.of(context).brightness == Brightness.dark;

    return AppBar(
      titleSpacing: 0,
      leading: Builder(
        builder: (context) => Stack(
          alignment: Alignment.center,
          children: [
            IconButton(
              onPressed: Scaffold.of(context).openDrawer,
              icon: const Icon(Icons.menu_rounded),
              tooltip: 'All modules',
            ),
            // Work waiting in a module that is not on the bottom bar would
            // otherwise be invisible until somebody happened to open the menu.
            if (counts.total > 0)
              Positioned(
                top: 12,
                right: 10,
                child: Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: scheme.error,
                    shape: BoxShape.circle,
                    border: Border.all(color: scheme.surface, width: 1.5),
                  ),
                ),
              ),
          ],
        ),
      ),
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: -0.3),
          ),
          Text(
            auth.orgName,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
                fontSize: 10.5,
                fontWeight: FontWeight.w600,
                color: scheme.onSurfaceVariant),
          ),
        ],
      ),
      actions: [
        ...actions,
        // Day/night, where the web app's phone header keeps it. The full
        // light / dark / follow-the-system choice is still on Profile; this is
        // the one-tap flip for walking out into the sun.
        IconButton(
          onPressed: () => auth.setThemeMode(
              dark ? ThemeMode.light : ThemeMode.dark),
          tooltip: dark ? 'Switch to day mode' : 'Switch to night mode',
          icon: Icon(dark
              ? Icons.light_mode_rounded
              : Icons.dark_mode_outlined),
        ),
        IconButton(
          onPressed: () => showNotifications(context),
          tooltip: notifications.unread > 0
              ? 'Notifications, ${notifications.unread} unread'
              : 'Notifications',
          icon: notifications.unread > 0
              ? Badge.count(
                  count: notifications.unread,
                  backgroundColor: scheme.error,
                  child: const Icon(Icons.notifications_none_rounded),
                )
              : const Icon(Icons.notifications_none_rounded),
        ),
        Padding(
          padding: const EdgeInsets.only(left: 2, right: 12),
          child: GestureDetector(
            onTap: onProfile,
            child: InitialsAvatar(
              text: auth.user?.initials ?? '?',
              size: 32,
              imageUrl: api.absoluteMedia(auth.user?.avatarUrl),
            ),
          ),
        ),
      ],
    );
  }
}
