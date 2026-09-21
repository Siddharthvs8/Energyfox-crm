import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../state/auth.dart';
import '../state/stores.dart';
import '../theme.dart';
import 'widgets/common.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final api = context.read<ApiClient>();
    final user = auth.user;
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: RefreshIndicator(
        onRefresh: auth.refreshIdentity,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(
              parent: BouncingScrollPhysics()),
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 110),
          children: [
            const SizedBox(height: 8),
            Center(
              child: Column(
                children: [
                  InitialsAvatar(
                    text: user?.initials ?? '?',
                    size: 84,
                    imageUrl: api.absoluteMedia(user?.avatarUrl),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    user?.name ?? 'Signed in',
                    style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.4),
                  ),
                  const SizedBox(height: 5),
                  Wrap(
                    spacing: 8,
                    children: [
                      if ((user?.roleLabel ?? '').isNotEmpty)
                        StatusPill(
                            label: user!.roleLabel,
                            color: Brand.amber,
                            dense: true),
                      if ((user?.branchName ?? '').isNotEmpty)
                        StatusPill(
                            label: user!.branchName!,
                            color: Brand.info,
                            dense: true),
                      if (auth.readOnly)
                        const StatusPill(
                            label: 'View only',
                            color: Brand.muted,
                            dense: true),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 28),
            const SectionHeader(
                title: 'Account', icon: Icons.badge_outlined),
            AppCard(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Column(
                children: [
                  _Row(
                      icon: Icons.alternate_email_rounded,
                      label: 'Username',
                      value: user?.username ?? '—'),
                  _Divider(color: scheme.outlineVariant),
                  _Row(
                      icon: Icons.mail_outline_rounded,
                      label: 'Email',
                      value: (user?.email.isNotEmpty ?? false)
                          ? user!.email
                          : '—'),
                  _Divider(color: scheme.outlineVariant),
                  _Row(
                      icon: Icons.call_rounded,
                      label: 'Phone',
                      value: (user?.phone.isNotEmpty ?? false)
                          ? user!.phone
                          : 'Not set'),
                ],
              ),
            ),
            const SizedBox(height: 22),
            const SectionHeader(
                title: 'App', icon: Icons.tune_rounded),
            AppCard(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 13),
                    child: Row(
                      children: [
                        Icon(Icons.dark_mode_outlined,
                            size: 18, color: scheme.onSurfaceVariant),
                        const SizedBox(width: 12),
                        const Text('Appearance',
                            style: TextStyle(
                                fontSize: 13.5, fontWeight: FontWeight.w600)),
                        const Spacer(),
                        SegmentedButton<ThemeMode>(
                          style: SegmentedButton.styleFrom(
                            visualDensity: VisualDensity.compact,
                            textStyle: const TextStyle(fontSize: 12),
                          ),
                          segments: const [
                            ButtonSegment(
                                value: ThemeMode.light,
                                icon: Icon(Icons.light_mode_rounded, size: 16)),
                            ButtonSegment(
                                value: ThemeMode.system,
                                icon: Icon(Icons.brightness_auto_rounded,
                                    size: 16)),
                            ButtonSegment(
                                value: ThemeMode.dark,
                                icon: Icon(Icons.dark_mode_rounded, size: 16)),
                          ],
                          selected: {auth.themeMode},
                          showSelectedIcon: false,
                          onSelectionChanged: (s) =>
                              auth.setThemeMode(s.first),
                        ),
                      ],
                    ),
                  ),
                  _Divider(color: scheme.outlineVariant),
                  // Shown, not offered: the server is fixed in the build, so
                  // this is here to answer "which CRM am I on?" and nothing
                  // more.
                  _Row(
                    icon: Icons.dns_outlined,
                    label: 'Server',
                    value: auth.baseUrl.replaceFirst(RegExp(r'^https?://'), ''),
                  ),
                  _Divider(color: scheme.outlineVariant),
                  InkWell(
                    onTap: () => _refreshAll(context),
                    child: const _Row(
                      icon: Icons.sync_rounded,
                      label: 'Refresh everything',
                      value: '',
                      trailing: Icons.chevron_right_rounded,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 22),
            AppCard(
              color: scheme.surfaceContainer,
              child: Row(
                children: [
                  const BrandMark(size: 40, radius: 12),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${auth.orgName} CRM',
                            style: const TextStyle(
                                fontSize: 14.5, fontWeight: FontWeight.w800)),
                        const SizedBox(height: 2),
                        Text(
                          'Installable app · add it to your home screen from your browser menu.',
                          style: TextStyle(
                              fontSize: 11.5,
                              height: 1.4,
                              color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 22),
            OutlinedButton.icon(
              onPressed: () => _confirmSignOut(context, auth),
              icon: const Icon(Icons.logout_rounded, size: 18),
              label: const Text('Sign out'),
              style: OutlinedButton.styleFrom(
                foregroundColor: Brand.danger,
                side: BorderSide(color: Brand.danger.withValues(alpha: 0.4)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _refreshAll(BuildContext context) {
    context.read<DashboardStore>().load(force: true);
    context.read<LeadStore>().load(force: true);
    context.read<TaskStore>().load(force: true);
    context.read<CallStore>().load(force: true);
    context.read<ModuleCountStore>().load();
    context.read<NotificationStore>().load();
    // Identity last: a role change is what would redraw the drawer and the
    // tabs around everything above.
    context.read<AuthController>().refreshIdentity();
    showToast(context, 'Refreshing…');
  }

  Future<void> _confirmSignOut(
      BuildContext context, AuthController auth) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text('You will need your password to get back in.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Stay')),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            style: FilledButton.styleFrom(
                backgroundColor: Brand.danger,
                minimumSize: const Size(100, 44)),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (ok == true) await auth.signOut();
  }
}

class _Row extends StatelessWidget {
  const _Row({
    required this.icon,
    required this.label,
    required this.value,
    this.trailing,
  });

  final IconData icon;
  final String label;
  final String value;
  final IconData? trailing;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 14),
      child: Row(
        children: [
          Icon(icon, size: 18, color: scheme.onSurfaceVariant),
          const SizedBox(width: 12),
          Text(label,
              style: const TextStyle(
                  fontSize: 13.5, fontWeight: FontWeight.w600)),
          const Spacer(),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
            ),
          ),
          if (trailing != null) ...[
            const SizedBox(width: 4),
            Icon(trailing, size: 19, color: scheme.onSurfaceVariant),
          ],
        ],
      ),
    );
  }
}

class _Divider extends StatelessWidget {
  const _Divider({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) => Divider(height: 1, color: color);
}
