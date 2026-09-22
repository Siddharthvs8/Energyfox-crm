import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/models.dart';
import '../state/auth.dart';
import '../state/stores.dart';
import '../theme.dart';
import 'lead/site_visit_screen.dart';
import 'lead_detail_screen.dart';
import 'widgets/common.dart';

class LeadsScreen extends StatefulWidget {
  const LeadsScreen({super.key});

  @override
  State<LeadsScreen> createState() => _LeadsScreenState();
}

class _LeadsScreenState extends State<LeadsScreen> {
  final _scroll = ScrollController();
  final _search = TextEditingController();

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scroll.dispose();
    _search.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scroll.position.pixels >=
        _scroll.position.maxScrollExtent - 320) {
      context.read<LeadStore>().loadMore();
    }
  }

  @override
  Widget build(BuildContext context) {
    final store = context.watch<LeadStore>();
    final auth = context.watch<AuthController>();
    final leads = store.visible;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _Header(
              controller: _search,
              store: store,
              auth: auth,
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: () => store.load(force: true),
                child: _body(store, auth, leads),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _body(LeadStore store, AuthController auth, List<Lead> leads) {
    if (store.state == LoadState.loading && store.leads.isEmpty) {
      return const ListSkeleton();
    }
    if (store.state == LoadState.failed) {
      return ListView(children: [
        SizedBox(
          height: 380,
          child: ErrorView(
            message: store.error ?? 'Could not load the lead book.',
            onRetry: () => store.load(force: true),
          ),
        ),
      ]);
    }
    if (leads.isEmpty) {
      return ListView(children: [
        SizedBox(
          height: 380,
          child: EmptyState(
            icon: store.query.isNotEmpty
                ? Icons.search_off_rounded
                : Icons.groups_2_outlined,
            title: store.query.isNotEmpty
                ? 'No match for "${store.query}"'
                : 'No leads here',
            message: store.query.isNotEmpty
                ? 'Search looks through the leads already loaded. Scroll down to pull in more, or clear the filters.'
                : store.statusFilter != null || store.mineOnly
                    ? 'Nothing matches these filters yet.'
                    : 'New leads will show up here as they arrive.',
          ),
        ),
      ]);
    }

    return ListView.separated(
      controller: _scroll,
      physics: const AlwaysScrollableScrollPhysics(
          parent: BouncingScrollPhysics()),
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 120),
      itemCount: leads.length + 1,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, i) {
        if (i == leads.length) return _footer(store, leads.length);
        return _LeadCard(
          lead: leads[i],
          status: auth.statusFor(leads[i].status),
          onTap: () => _open(leads[i]),
          onSiteVisit: () => _openSiteVisit(leads[i]),
          onDial: () => _dial(leads[i]),
        );
      },
    );
  }

  /// Straight into the survey, the way the web list's "Site visit" button
  /// goes — a BDE working a day of visits should not have to open the lead and
  /// scroll down to find it.
  Future<void> _openSiteVisit(Lead lead) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => SiteVisitScreen(lead: lead)),
    );
    if (changed == true && mounted) {
      context.read<LeadStore>().load(force: true);
    }
  }

  Future<void> _dial(Lead lead) async {
    if (lead.phone.isEmpty) return;
    final ok = await launchUrl(Uri.parse('tel:${lead.phone}'),
        mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      showToast(context, 'Nothing on this device can place a call.',
          error: true);
    }
  }

  Widget _footer(LeadStore store, int shown) {
    final scheme = Theme.of(context).colorScheme;
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
          child: const Text('Load more leads'),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 20),
      child: Center(
        child: Text(
          '$shown of ${store.total} lead${store.total == 1 ? '' : 's'}',
          style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant),
        ),
      ),
    );
  }

  Future<void> _open(Lead lead) async {
    HapticFeedback.selectionClick();
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => LeadDetailScreen(leadId: lead.id, seed: lead)),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.controller,
    required this.store,
    required this.auth,
  });

  final TextEditingController controller;
  final LeadStore store;
  final AuthController auth;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final statuses = auth.statuses.isEmpty
        ? LeadStatus.fallback
            .map((e) => LeadStatus.fromJson(Map<String, dynamic>.from(e)))
            .toList()
        : auth.statuses;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
          child: Row(
            children: [
              const Text(
                'Leads',
                style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.5),
              ),
              const SizedBox(width: 9),
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '${store.total}',
                  style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: scheme.onSurfaceVariant),
                ),
              ),
              const Spacer(),
              _MineToggle(store: store),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
          child: TextField(
            controller: controller,
            onChanged: store.search,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              hintText: 'Search name, phone, place…',
              prefixIcon: const Icon(Icons.search_rounded, size: 21),
              isDense: true,
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
              suffixIcon: store.query.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.close_rounded, size: 19),
                      onPressed: () {
                        controller.clear();
                        store.search('');
                      },
                    ),
            ),
          ),
        ),
        SizedBox(
          height: 38,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            children: [
              _FilterChip(
                label: 'All',
                selected: store.statusFilter == null,
                color: scheme.primary,
                onTap: () => store.setStatus(null),
              ),
              for (final s in statuses)
                _FilterChip(
                  label: s.label,
                  selected: store.statusFilter == s.value,
                  color: s.color,
                  onTap: () => store
                      .setStatus(store.statusFilter == s.value ? null : s.value),
                ),
            ],
          ),
        ),
        const SizedBox(height: 10),
      ],
    );
  }
}

class _MineToggle extends StatelessWidget {
  const _MineToggle({required this.store});

  final LeadStore store;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: () {
        HapticFeedback.selectionClick();
        store.setMineOnly(!store.mineOnly);
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 8),
        decoration: BoxDecoration(
          color: store.mineOnly
              ? scheme.primary.withValues(alpha: 0.12)
              : scheme.surface,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(
            color: store.mineOnly ? scheme.primary : scheme.outline,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              store.mineOnly
                  ? Icons.person_rounded
                  : Icons.people_alt_outlined,
              size: 16,
              color: store.mineOnly ? scheme.primary : scheme.onSurfaceVariant,
            ),
            const SizedBox(width: 6),
            Text(
              store.mineOnly ? 'Mine' : 'Everyone',
              style: TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
                color: store.mineOnly ? scheme.primary : scheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.color,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: GestureDetector(
        onTap: () {
          HapticFeedback.selectionClick();
          onTap();
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(horizontal: 15),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: selected ? color.withValues(alpha: 0.14) : scheme.surface,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: selected ? color : scheme.outline),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
              color: selected ? color : scheme.onSurfaceVariant,
            ),
          ),
        ),
      ),
    );
  }
}

class _LeadCard extends StatelessWidget {
  const _LeadCard({
    required this.lead,
    required this.status,
    required this.onTap,
    required this.onSiteVisit,
    required this.onDial,
  });

  final Lead lead;
  final LeadStatus status;
  final VoidCallback onTap;
  final VoidCallback onSiteVisit;
  final VoidCallback onDial;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final place = [lead.company, lead.district]
        .where((s) => s.isNotEmpty)
        .join(' · ');
    // A finished survey stays on the card even once the lead has been pushed to
    // documentation and editing is locked, the way the web list shows it — the
    // tick is the status, not an invitation to edit.
    final showSiteVisit = lead.canEditSiteVisit || lead.siteVisitComplete;

    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.fromLTRB(14, 13, 14, 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
  Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            InitialsAvatar(text: lead.initials, size: 44),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          lead.name.isEmpty ? 'Unnamed lead' : lead.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 15.5,
                              fontWeight: FontWeight.w700,
                              letterSpacing: -0.2),
                        ),
                      ),
                      const SizedBox(width: 8),
                      StatusPill(
                          label: status.label, color: status.color, dense: true),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      if (lead.phone.isNotEmpty) ...[
                        Icon(Icons.call_rounded,
                            size: 13, color: scheme.onSurfaceVariant),
                        const SizedBox(width: 4),
                        Text(
                          lead.phone,
                          style: TextStyle(
                              fontSize: 12.5,
                              fontWeight: FontWeight.w600,
                              color: scheme.onSurfaceVariant),
                        ),
                      ],
                      if (place.isNotEmpty) ...[
                        if (lead.phone.isNotEmpty)
                          Text('  ·  ',
                              style: TextStyle(color: scheme.onSurfaceVariant)),
                        Flexible(
                          child: Text(
                            place,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                fontSize: 12.5, color: scheme.onSurfaceVariant),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 9),
                  Row(
                    children: [
                      if (lead.value > 0) ...[
                        Text(
                          moneyShort(lead.value),
                          style: const TextStyle(
                              fontSize: 13, fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(width: 10),
                      ],
                      if (lead.assignedToName.isNotEmpty)
                        Flexible(
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.person_outline_rounded,
                                  size: 13, color: scheme.onSurfaceVariant),
                              const SizedBox(width: 3),
                              Flexible(
                                child: Text(
                                  lead.assignedToName,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                      fontSize: 12,
                                      color: scheme.onSurfaceVariant),
                                ),
                              ),
                            ],
                          ),
                        ),
                      const Spacer(),
                      Text(
                        timeAgo(lead.createdAt),
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
          ],
        ),
          // The two things done from the list rather than from the record:
          // ring the customer, and open the survey. Both are on the web
          // list too, and both are why a BDE has the phone out at all.
          if (lead.phone.isNotEmpty || showSiteVisit) ...[
            const SizedBox(height: 11),
            Row(
              children: [
                if (showSiteVisit)
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: onSiteVisit,
                      // A tick once the survey is signed off, a map pin while it
                      // is still to be done — same two marks as the web list, and
                      // a real icon rather than a character the label can clip.
                      icon: Icon(
                        lead.siteVisitComplete
                            ? Icons.check_rounded
                            : Icons.place_outlined,
                        size: 16,
                      ),
                      label: const Text(
                        'Site visit',
                        style: TextStyle(fontSize: 12.5),
                      ),
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size.fromHeight(38),
                        visualDensity: VisualDensity.compact,
                        foregroundColor:
                            lead.siteVisitComplete ? Brand.success : null,
                        backgroundColor: lead.siteVisitComplete
                            ? Brand.success.withValues(alpha: 0.10)
                            : null,
                        side: lead.siteVisitComplete
                            ? BorderSide(
                                color: Brand.success.withValues(alpha: 0.55))
                            : null,
                      ),
                    ),
                  ),
                if (showSiteVisit && lead.phone.isNotEmpty)
                  const SizedBox(width: 9),
                if (lead.phone.isNotEmpty)
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: onDial,
                      icon: const Icon(Icons.call_rounded, size: 16),
                      label: const Text('Call',
                          style: TextStyle(fontSize: 12.5)),
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size.fromHeight(38),
                        visualDensity: VisualDensity.compact,
                        foregroundColor: Brand.success,
                      ),
                    ),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
