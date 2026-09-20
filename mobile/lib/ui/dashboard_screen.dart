import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/auth.dart';
import '../state/nav.dart';
import '../state/stores.dart';
import '../theme.dart';
import 'widgets/common.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key, required this.onOpenTab});

  final void Function(AppTab tab) onOpenTab;

  @override
  Widget build(BuildContext context) {
    final store = context.watch<DashboardStore>();
    final auth = context.watch<AuthController>();
    final stats = store.stats;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: RefreshIndicator(
        onRefresh: () => store.load(force: true),
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(
              parent: BouncingScrollPhysics()),
          slivers: [
            // The app frame carries the bar above this (hamburger, alerts,
            // you), so the greeting is content rather than a second bar
            // stacked on the first.
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 10, 8, 4),
                child: Row(
                  children: [
                    Expanded(child: _Greeting(auth: auth)),
                    IconButton(
                      onPressed: () => store.load(force: true),
                      icon: const Icon(Icons.refresh_rounded),
                      tooltip: 'Refresh',
                    ),
                  ],
                ),
              ),
            ),
            if (store.state == LoadState.failed)
              SliverFillRemaining(
                hasScrollBody: false,
                child: ErrorView(
                  message: store.error ?? 'Could not load your dashboard.',
                  onRetry: () => store.load(force: true),
                ),
              )
            else if (stats == null)
              const SliverToBoxAdapter(child: _DashboardSkeleton())
            else
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 110),
                sliver: SliverList.list(children: [
                  if (store.error != null) ...[
                    _StaleBanner(message: store.error!),
                    const SizedBox(height: 14),
                  ],
                  _KpiGrid(stats: stats),
                  const SizedBox(height: 22),
                  _QuickActions(onOpenTab: onOpenTab),
                  const SizedBox(height: 22),
                  const SectionHeader(
                      title: 'Revenue', icon: Icons.trending_up_rounded),
                  _RevenueCard(stats: stats),
                  const SizedBox(height: 22),
                  const SectionHeader(
                      title: 'Pipeline', icon: Icons.donut_small_rounded),
                  _PipelineCard(stats: stats, auth: auth, onOpenTab: onOpenTab),
                  if (stats.performance.isNotEmpty) ...[
                    const SizedBox(height: 22),
                    const SectionHeader(
                        title: 'Top performers',
                        icon: Icons.emoji_events_outlined),
                    _LeaderboardCard(rows: stats.performance),
                  ],
                  const SizedBox(height: 22),
                  const SectionHeader(
                      title: 'Recent activity', icon: Icons.history_rounded),
                  _ActivityCard(entries: stats.recentActivities),
                ]),
              ),
          ],
        ),
      ),
    );
  }
}

class _Greeting extends StatelessWidget {
  const _Greeting({required this.auth});

  final AuthController auth;

  @override
  Widget build(BuildContext context) {
    final user = auth.user;
    final hour = DateTime.now().hour;
    final part = hour < 12
        ? 'Good morning'
        : hour < 17
            ? 'Good afternoon'
            : 'Good evening';
    final scheme = Theme.of(context).colorScheme;

    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                part,
                style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.3,
                    color: scheme.onSurfaceVariant),
              ),
              const SizedBox(height: 1),
              Text(
                user?.name.split(' ').first ?? auth.orgName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.4),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _StaleBanner extends StatelessWidget {
  const _StaleBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(
        color: Brand.warning.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Brand.warning.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.wifi_off_rounded, size: 17, color: Brand.warning),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Showing the last data we had. $message',
              style: const TextStyle(fontSize: 12.5, height: 1.35),
            ),
          ),
        ],
      ),
    );
  }
}

class _KpiGrid extends StatelessWidget {
  const _KpiGrid({required this.stats});

  final DashboardStats stats;

  @override
  Widget build(BuildContext context) {
    final tiles = [
      _Kpi(
        label: 'Total leads',
        value: '${stats.totalLeads}',
        icon: Icons.groups_2_rounded,
        color: const Color(0xFF6366F1),
      ),
      _Kpi(
        label: 'New today',
        value: '${stats.newToday}',
        icon: Icons.bolt_rounded,
        color: Brand.amber,
      ),
      _Kpi(
        label: 'Pipeline value',
        value: moneyShort(stats.pipelineValue),
        icon: Icons.account_tree_rounded,
        color: const Color(0xFF06B6D4),
      ),
      _Kpi(
        label: 'Revenue',
        value: moneyShort(stats.totalRevenue),
        icon: Icons.payments_rounded,
        color: Brand.success,
      ),
    ];

    return LayoutBuilder(builder: (context, c) {
      final columns = c.maxWidth > 620 ? 4 : 2;
      return GridView.count(
        crossAxisCount: columns,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: columns == 4 ? 1.5 : 1.42,
        children: tiles,
      );
    });
  }
}

class _Kpi extends StatelessWidget {
  const _Kpi({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AppCard(
      padding: const EdgeInsets.all(15),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.13),
              borderRadius: BorderRadius.circular(11),
            ),
            child: Icon(icon, size: 19, color: color),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(
                  value,
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.8,
                  ),
                ),
              ),
              const SizedBox(height: 2),
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: scheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.onOpenTab});

  final void Function(AppTab) onOpenTab;

  @override
  Widget build(BuildContext context) {
    final tasks = context.watch<TaskStore>();
    final leads = context.watch<LeadStore>();

    return Row(
      children: [
        Expanded(
          child: _Action(
            icon: Icons.person_search_rounded,
            label: 'Leads',
            hint: '${leads.total} in book',
            onTap: () => onOpenTab(AppTab.leads),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _Action(
            icon: Icons.task_alt_rounded,
            label: 'Tasks',
            hint: tasks.overdueCount > 0
                ? '${tasks.overdueCount} overdue'
                : '${tasks.openCount} open',
            tint: tasks.overdueCount > 0 ? Brand.danger : null,
            onTap: () => onOpenTab(AppTab.tasks),
          ),
        ),
      ],
    );
  }
}

class _Action extends StatelessWidget {
  const _Action({
    required this.icon,
    required this.label,
    required this.hint,
    required this.onTap,
    this.tint,
  });

  final IconData icon;
  final String label;
  final String hint;
  final VoidCallback onTap;
  final Color? tint;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = tint ?? scheme.primary;
    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
      child: Row(
        children: [
          Icon(icon, size: 21, color: color),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(label,
                    style: const TextStyle(
                        fontSize: 14.5, fontWeight: FontWeight.w700)),
                Text(
                  hint,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w600,
                      color: tint ?? scheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
          Icon(Icons.chevron_right_rounded,
              size: 20, color: scheme.onSurfaceVariant),
        ],
      ),
    );
  }
}

class _RevenueCard extends StatelessWidget {
  const _RevenueCard({required this.stats});

  final DashboardStats stats;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final series = stats.revenueOverTime;
    if (series.isEmpty) {
      return const AppCard(
        child: SizedBox(
          height: 120,
          child: Center(child: Text('No revenue recorded yet.')),
        ),
      );
    }

    final maxY = series.fold<double>(0, (m, e) => e.value > m ? e.value : m);
    final last = series.last.value;
    final prev = series.length > 1 ? series[series.length - 2].value : 0.0;
    final delta = prev == 0 ? null : ((last - prev) / prev) * 100;

    return AppCard(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('This month',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: scheme.onSurfaceVariant)),
                  const SizedBox(height: 3),
                  Text(
                    money(last),
                    style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.6),
                  ),
                ],
              ),
              const Spacer(),
              if (delta != null)
                StatusPill(
                  label:
                      '${delta >= 0 ? '▲' : '▼'} ${delta.abs().toStringAsFixed(0)}%',
                  color: delta >= 0 ? Brand.success : Brand.danger,
                  dense: true,
                ),
            ],
          ),
          const SizedBox(height: 18),
          SizedBox(
            height: 150,
            child: LineChart(
              LineChartData(
                minY: 0,
                maxY: maxY <= 0 ? 1 : maxY * 1.25,
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: maxY <= 0 ? 1 : maxY / 2,
                  getDrawingHorizontalLine: (_) => FlLine(
                      color: scheme.outlineVariant, strokeWidth: 1),
                ),
                borderData: FlBorderData(show: false),
                titlesData: FlTitlesData(
                  leftTitles:
                      const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles:
                      const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  topTitles:
                      const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 26,
                      interval: 1,
                      getTitlesWidget: (value, meta) {
                        final i = value.round();
                        if (i < 0 || i >= series.length) {
                          return const SizedBox.shrink();
                        }
                        return Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Text(
                            series[i].label.split(' ').first,
                            style: TextStyle(
                                fontSize: 10.5,
                                fontWeight: FontWeight.w600,
                                color: scheme.onSurfaceVariant),
                          ),
                        );
                      },
                    ),
                  ),
                ),
                lineTouchData: LineTouchData(
                  touchTooltipData: LineTouchTooltipData(
                    getTooltipItems: (spots) => spots
                        .map((s) => LineTooltipItem(
                              moneyShort(s.y),
                              const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 12),
                            ))
                        .toList(),
                  ),
                ),
                lineBarsData: [
                  LineChartBarData(
                    spots: [
                      for (var i = 0; i < series.length; i++)
                        FlSpot(i.toDouble(), series[i].value),
                    ],
                    isCurved: true,
                    curveSmoothness: 0.28,
                    barWidth: 3,
                    color: Brand.amber,
                    dotData: FlDotData(
                      show: true,
                      getDotPainter: (spot, _, _, _) => FlDotCirclePainter(
                        radius: 3.4,
                        color: Brand.amber,
                        strokeWidth: 2,
                        strokeColor: scheme.surface,
                      ),
                    ),
                    belowBarData: BarAreaData(
                      show: true,
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Brand.amber.withValues(alpha: 0.28),
                          Brand.amber.withValues(alpha: 0.0),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PipelineCard extends StatelessWidget {
  const _PipelineCard({
    required this.stats,
    required this.auth,
    required this.onOpenTab,
  });

  final DashboardStats stats;
  final AuthController auth;
  final void Function(AppTab) onOpenTab;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entries = stats.pipeline.entries.where((e) => e.value > 0).toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    if (entries.isEmpty) {
      return const AppCard(
        child: SizedBox(
          height: 90,
          child: Center(child: Text('No leads in the pipeline yet.')),
        ),
      );
    }

    final total = entries.fold<int>(0, (s, e) => s + e.value);

    return AppCard(
      child: Column(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: SizedBox(
              height: 9,
              child: Row(
                children: [
                  for (final e in entries)
                    Expanded(
                      flex: e.value,
                      child: Container(
                          color: auth.statusFor(e.key).color,
                          margin: const EdgeInsets.only(right: 1.5)),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          for (final e in entries) ...[
            InkWell(
              onTap: () {
                context.read<LeadStore>().setStatus(e.key);
                onOpenTab(AppTab.leads);
              },
              borderRadius: BorderRadius.circular(10),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 7),
                child: Row(
                  children: [
                    Container(
                      width: 9,
                      height: 9,
                      decoration: BoxDecoration(
                        color: auth.statusFor(e.key).color,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        auth.statusFor(e.key).label,
                        style: const TextStyle(
                            fontSize: 13.5, fontWeight: FontWeight.w600),
                      ),
                    ),
                    Text(
                      '${((e.value / total) * 100).round()}%',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: scheme.onSurfaceVariant),
                    ),
                    const SizedBox(width: 12),
                    SizedBox(
                      width: 42,
                      child: Text(
                        '${e.value}',
                        textAlign: TextAlign.right,
                        style: const TextStyle(
                            fontSize: 13.5, fontWeight: FontWeight.w800),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _LeaderboardCard extends StatelessWidget {
  const _LeaderboardCard({required this.rows});

  final List<Map<String, dynamic>> rows;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ranked = [...rows]..sort((a, b) =>
        ((b['won_value'] ?? 0) as num).compareTo((a['won_value'] ?? 0) as num));
    final top = ranked.take(5).toList();

    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      child: Column(
        children: [
          for (var i = 0; i < top.length; i++)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Row(
                children: [
                  SizedBox(
                    width: 22,
                    child: Text(
                      '${i + 1}',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w800,
                        color: i == 0 ? Brand.amber : scheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          (top[i]['name'] ?? '—').toString(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 14, fontWeight: FontWeight.w700),
                        ),
                        Text(
                          '${top[i]['won_count'] ?? 0} closed · ${top[i]['leads_count'] ?? 0} leads',
                          style: TextStyle(
                              fontSize: 11.5, color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    moneyShort(((top[i]['won_value'] ?? 0) as num)),
                    style: const TextStyle(
                        fontSize: 13.5, fontWeight: FontWeight.w800),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _ActivityCard extends StatelessWidget {
  const _ActivityCard({required this.entries});

  final List<ActivityEntry> entries;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (entries.isEmpty) {
      return const AppCard(
        child: SizedBox(
          height: 80,
          child: Center(child: Text('Nothing has happened yet today.')),
        ),
      );
    }

    final shown = entries.take(8).toList();
    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      child: Column(
        children: [
          for (final e in shown)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 9),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 30,
                    height: 30,
                    decoration: BoxDecoration(
                      color: _tint(e.type).withValues(alpha: 0.13),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(_icon(e.type), size: 15, color: _tint(e.type)),
                  ),
                  const SizedBox(width: 11),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          e.description,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 13, height: 1.35),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          [
                            if (e.actor.isNotEmpty) e.actor,
                            timeAgo(e.timestamp),
                          ].where((s) => s.isNotEmpty).join(' · '),
                          style: TextStyle(
                              fontSize: 11.5, color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  static IconData _icon(String type) => switch (type) {
        'lead_created' => Icons.person_add_alt_1_rounded,
        'status_changed' => Icons.swap_horiz_rounded,
        'call_made' || 'call_logged' => Icons.call_rounded,
        'note_added' => Icons.sticky_note_2_outlined,
        'task_created' || 'task_completed' => Icons.task_alt_rounded,
        'lead_assigned' => Icons.assignment_ind_outlined,
        _ => Icons.circle_notifications_outlined,
      };

  static Color _tint(String type) => switch (type) {
        'lead_created' => const Color(0xFF6366F1),
        'status_changed' => Brand.amber,
        'call_made' || 'call_logged' => Brand.info,
        'task_created' || 'task_completed' => Brand.success,
        _ => const Color(0xFF8B5CF6),
      };
}

class _DashboardSkeleton extends StatelessWidget {
  const _DashboardSkeleton();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: const [
            Expanded(child: Skeleton(height: 104, radius: 18)),
            SizedBox(width: 12),
            Expanded(child: Skeleton(height: 104, radius: 18)),
          ]),
          const SizedBox(height: 12),
          Row(children: const [
            Expanded(child: Skeleton(height: 104, radius: 18)),
            SizedBox(width: 12),
            Expanded(child: Skeleton(height: 104, radius: 18)),
          ]),
          const SizedBox(height: 22),
          const Skeleton(height: 230, radius: 18),
          const SizedBox(height: 22),
          const Skeleton(height: 180, radius: 18),
        ],
      ),
    );
  }
}
