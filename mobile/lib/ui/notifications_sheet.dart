import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/stores.dart';
import '../theme.dart';
import 'widgets/common.dart';

/// What the AI manager and the pipeline have to tell this user, in the sheet
/// the bell opens. Read on the same endpoints as the web app's dropdown, so the
/// unread count means the same thing in both places.
Future<void> showNotifications(BuildContext context) {
  final store = context.read<NotificationStore>();
  store.load();
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => ChangeNotifierProvider.value(
      value: store,
      child: const _NotificationsSheet(),
    ),
  );
}

class _NotificationsSheet extends StatelessWidget {
  const _NotificationsSheet();

  @override
  Widget build(BuildContext context) {
    final store = context.watch<NotificationStore>();
    final scheme = Theme.of(context).colorScheme;

    return SafeArea(
      top: false,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.78,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 12, 8),
              child: Row(
                children: [
                  const Text('Notifications',
                      style: TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.3)),
                  if (store.unread > 0) ...[
                    const SizedBox(width: 9),
                    StatusPill(
                        label: '${store.unread} new',
                        color: scheme.error,
                        dense: true),
                  ],
                  const Spacer(),
                  if (store.unread > 0)
                    TextButton(
                      onPressed: store.markAllRead,
                      child: const Text('Mark all read'),
                    ),
                ],
              ),
            ),
            Flexible(child: _body(context, store)),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  Widget _body(BuildContext context, NotificationStore store) {
    if (store.state == LoadState.loading && store.items.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 40),
        child: Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
      );
    }
    if (store.state == LoadState.failed) {
      return SizedBox(
        height: 240,
        child: ErrorView(
          message: store.error ?? 'Could not load your notifications.',
          onRetry: store.load,
        ),
      );
    }
    if (store.items.isEmpty) {
      return const SizedBox(
        height: 240,
        child: EmptyState(
          icon: Icons.notifications_none_rounded,
          title: 'Nothing new',
          message: 'Reminders and updates from the CRM land here.',
        ),
      );
    }
    return ListView.separated(
      shrinkWrap: true,
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
      itemCount: store.items.length,
      separatorBuilder: (_, _) => const SizedBox(height: 8),
      itemBuilder: (context, i) => _NotificationCard(item: store.items[i]),
    );
  }
}

class _NotificationCard extends StatelessWidget {
  const _NotificationCard({required this.item});

  final Map<String, dynamic> item;

  static const _icons = {
    'daily_target': Icons.flag_rounded,
    'monthly_target': Icons.calendar_month_rounded,
    'meeting': Icons.groups_rounded,
    'achievement': Icons.emoji_events_rounded,
    'general': Icons.notifications_rounded,
  };

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final read = item['is_read'] == true;
    final type = (item['notification_type'] ?? 'general').toString();
    final when = DateTime.tryParse((item['created_at'] ?? '').toString())?.toLocal();

    return AppCard(
      color: read ? null : scheme.primary.withValues(alpha: 0.06),
      padding: const EdgeInsets.fromLTRB(13, 12, 13, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: (read ? Brand.muted : scheme.primary).withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(_icons[type] ?? Icons.notifications_rounded,
                size: 17, color: read ? Brand.muted : scheme.primary),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  (item['title'] ?? '').toString(),
                  style: TextStyle(
                      fontSize: 13.5,
                      fontWeight: read ? FontWeight.w600 : FontWeight.w800),
                ),
                if ((item['message'] ?? '').toString().isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    item['message'].toString(),
                    style: TextStyle(
                        fontSize: 12.5,
                        height: 1.45,
                        color: scheme.onSurfaceVariant),
                  ),
                ],
                const SizedBox(height: 6),
                Text(
                  timeAgo(when),
                  style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: scheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
