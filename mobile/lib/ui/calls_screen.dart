import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../state/stores.dart';
import '../theme.dart';
import 'lead_detail_screen.dart';
import 'widgets/common.dart';

/// The call log — the fourth thing the sales floor lives in, and until now the
/// one tab the web app had on a phone and the app did not.
class CallsScreen extends StatefulWidget {
  const CallsScreen({super.key});

  @override
  State<CallsScreen> createState() => _CallsScreenState();
}

class _CallsScreenState extends State<CallsScreen> {
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    // Opening straight onto this tab — the home-screen shortcut does — must
    // load it, not sit on an empty state nobody asked for.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<CallStore>().load();
    });
    _scroll.addListener(() {
      if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 320) {
        context.read<CallStore>().loadMore();
      }
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final store = context.watch<CallStore>();

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
            child: Row(
              children: [
                const Text('Calls',
                    style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5)),
                const SizedBox(width: 9),
                if (store.state == LoadState.ready)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      '${store.total}',
                      style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: Theme.of(context).colorScheme.onSurfaceVariant),
                    ),
                  ),
                const Spacer(),
                for (final option in const [
                  (null, 'All'),
                  ('outbound', 'Out'),
                  ('inbound', 'In'),
                ])
                  Padding(
                    padding: const EdgeInsets.only(left: 6),
                    child: _Chip(
                      label: option.$2,
                      selected: store.direction == option.$1,
                      onTap: () => store.setDirection(option.$1),
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => store.load(force: true),
              child: _body(store),
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(CallStore store) {
    if (store.state == LoadState.loading && store.calls.isEmpty) {
      return const ListSkeleton();
    }
    if (store.state == LoadState.failed) {
      return ListView(children: [
        SizedBox(
          height: 380,
          child: ErrorView(
            message: store.error ?? 'Could not load the call log.',
            onRetry: () => store.load(force: true),
          ),
        ),
      ]);
    }
    if (store.calls.isEmpty) {
      return ListView(children: const [
        SizedBox(
          height: 380,
          child: EmptyState(
            icon: Icons.phone_disabled_rounded,
            title: 'No calls yet',
            message:
                'Calls placed through the CRM are recorded here, against the '
                'lead they were about.',
          ),
        ),
      ]);
    }
    return ListView.separated(
      controller: _scroll,
      physics:
          const AlwaysScrollableScrollPhysics(parent: BouncingScrollPhysics()),
      padding: const EdgeInsets.fromLTRB(16, 2, 16, 120),
      itemCount: store.calls.length + 1,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, i) {
        if (i == store.calls.length) {
          if (store.loadingMore) {
            return const Padding(
              padding: EdgeInsets.symmetric(vertical: 22),
              child: Center(
                child: SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2.2),
                ),
              ),
            );
          }
          if (store.hasMore) {
            return Padding(
              padding: const EdgeInsets.only(top: 14),
              child: OutlinedButton(
                onPressed: store.loadMore,
                child: const Text('Load more calls'),
              ),
            );
          }
          return const SizedBox(height: 20);
        }
        return _CallCard(call: store.calls[i]);
      },
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: () {
        HapticFeedback.selectionClick();
        onTap();
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 7),
        decoration: BoxDecoration(
          color: selected
              ? scheme.primary.withValues(alpha: 0.12)
              : scheme.surface,
          borderRadius: BorderRadius.circular(999),
          border:
              Border.all(color: selected ? scheme.primary : scheme.outline),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12.5,
            fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
            color: selected ? scheme.primary : scheme.onSurfaceVariant,
          ),
        ),
      ),
    );
  }
}

class _CallCard extends StatelessWidget {
  const _CallCard({required this.call});

  final Map<String, dynamic> call;

  /// How the call ended, in the CRM's own words and colours.
  static const _outcomes = {
    'connected': ('Connected', Brand.success),
    'initiated': ('Initiated', Brand.info),
    'rnr': ('No answer', Brand.amber),
    'busy': ('Busy', Brand.amber),
    'cancelled': ('Cancelled', Brand.danger),
  };

  String get _name {
    final n = (call['lead_name'] ?? '').toString().trim();
    return n.isEmpty ? 'Unknown lead' : n;
  }

  String get _phone => (call['lead_phone'] ?? '').toString();

  static String _duration(int seconds) {
    if (seconds <= 0) return '—';
    final m = seconds ~/ 60;
    final s = seconds % 60;
    return m == 0 ? '${s}s' : '${m}m ${s}s';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final outcome = (call['outcome'] ?? '').toString();
    final label = _outcomes[outcome] ?? (titleize(outcome), Brand.muted);
    final inbound = (call['direction'] ?? '').toString() == 'inbound';
    final seconds = (call['duration_seconds'] as num?)?.toInt() ?? 0;
    final when = DateTime.tryParse((call['created_at'] ?? '').toString());
    final leadId = (call['lead'] as num?)?.toInt();

    return AppCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
      onTap: leadId == null
          ? null
          : () {
              HapticFeedback.selectionClick();
              Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => LeadDetailScreen(leadId: leadId),
              ));
            },
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: label.$2.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(13),
            ),
            child: Icon(
              inbound ? Icons.call_received_rounded : Icons.call_made_rounded,
              size: 19,
              color: label.$2,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        _name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.2),
                      ),
                    ),
                    const SizedBox(width: 8),
                    StatusPill(label: label.$1, color: label.$2, dense: true),
                  ],
                ),
                const SizedBox(height: 5),
                Row(
                  children: [
                    Text(
                      [
                        if (_phone.isNotEmpty) _phone,
                        _duration(seconds),
                        if ((call['user_name'] ?? '').toString().isNotEmpty)
                          call['user_name'].toString(),
                      ].join('  ·  '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontSize: 12,
                          color: scheme.onSurfaceVariant),
                    ),
                    const Spacer(),
                    Text(
                      timeAgo(when?.toLocal()),
                      style: TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w600,
                          color: scheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ],
            ),
          ),
          if (_phone.isNotEmpty)
            IconButton(
              onPressed: () => _dial(context),
              icon: const Icon(Icons.call_rounded, size: 19),
              color: scheme.primary,
              tooltip: 'Call back',
            ),
        ],
      ),
    );
  }

  Future<void> _dial(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    HapticFeedback.lightImpact();
    final ok = await launchUrl(Uri.parse('tel:$_phone'),
        mode: LaunchMode.externalApplication);
    if (!ok) {
      messenger.showSnackBar(
        const SnackBar(content: Text('This device cannot place calls.')),
      );
    }
  }
}
