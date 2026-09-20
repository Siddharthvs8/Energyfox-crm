import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/auth.dart';
import '../state/stores.dart';
import '../theme.dart';
import 'task_editor.dart';
import 'widgets/common.dart';

class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key});

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs =
      TabController(length: TaskItem.statuses.length, vsync: this);
  final _search = TextEditingController();

  @override
  void dispose() {
    _tabs.dispose();
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final store = context.watch<TaskStore>();
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
              child: Row(
                children: [
                  const Text(
                    'Tasks',
                    style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5),
                  ),
                  const SizedBox(width: 10),
                  if (store.overdueCount > 0)
                    StatusPill(
                      label: '${store.overdueCount} overdue',
                      color: Brand.danger,
                      dense: true,
                    ),
                  const Spacer(),
                  _MineToggle(store: store),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 6),
              child: TextField(
                controller: _search,
                onChanged: store.search,
                decoration: InputDecoration(
                  hintText: 'Search tasks…',
                  prefixIcon: const Icon(Icons.search_rounded, size: 21),
                  isDense: true,
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
                  suffixIcon: store.query.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.close_rounded, size: 19),
                          onPressed: () {
                            _search.clear();
                            store.search('');
                          },
                        ),
                ),
              ),
            ),
            TabBar(
              controller: _tabs,
              isScrollable: true,
              tabAlignment: TabAlignment.start,
              dividerColor: Colors.transparent,
              indicatorSize: TabBarIndicatorSize.label,
              indicatorColor: scheme.primary,
              labelColor: scheme.onSurface,
              unselectedLabelColor: scheme.onSurfaceVariant,
              labelStyle:
                  const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
              unselectedLabelStyle:
                  const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
              onTap: (_) => HapticFeedback.selectionClick(),
              tabs: [
                for (final s in TaskItem.statuses)
                  Tab(
                    child: Row(
                      children: [
                        Text(s.$2),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 7, vertical: 2),
                          decoration: BoxDecoration(
                            color: kTaskStatusColors[s.$1]!
                                .withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            '${store.byStatus(s.$1).length}',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w800,
                              color: kTaskStatusColors[s.$1],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
            Expanded(
              child: TabBarView(
                controller: _tabs,
                children: [
                  for (final s in TaskItem.statuses)
                    _TaskList(status: s.$1, store: store),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MineToggle extends StatelessWidget {
  const _MineToggle({required this.store});

  final TaskStore store;

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
              color: store.mineOnly ? scheme.primary : scheme.outline),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              store.mineOnly ? Icons.person_rounded : Icons.people_alt_outlined,
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

class _TaskList extends StatelessWidget {
  const _TaskList({required this.status, required this.store});

  final String status;
  final TaskStore store;

  @override
  Widget build(BuildContext context) {
    if (store.state == LoadState.loading && store.tasks.isEmpty) {
      return const ListSkeleton(count: 4);
    }
    if (store.state == LoadState.failed) {
      return ListView(children: [
        SizedBox(
          height: 340,
          child: ErrorView(
            message: store.error ?? 'Could not load tasks.',
            onRetry: () => store.load(force: true),
          ),
        ),
      ]);
    }

    final tasks = store.byStatus(status);
    // Overdue first, then by due date, then whatever has no date at all.
    tasks.sort((a, b) {
      final ad = a.dueDate, bd = b.dueDate;
      if (ad == null && bd == null) return 0;
      if (ad == null) return 1;
      if (bd == null) return -1;
      return ad.compareTo(bd);
    });

    return RefreshIndicator(
      onRefresh: () => store.load(force: true),
      child: tasks.isEmpty
          ? ListView(children: [
              SizedBox(
                height: 340,
                child: EmptyState(
                  icon: Icons.task_alt_rounded,
                  title: 'Nothing in ${TaskItem.labelFor(status)}',
                  message: status == 'done'
                      ? 'Finished tasks land here.'
                      : 'Tasks you add will show up here.',
                ),
              ),
            ])
          : ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(
                  parent: BouncingScrollPhysics()),
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 120),
              itemCount: tasks.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (_, i) => _TaskCard(task: tasks[i], store: store),
            ),
    );
  }
}

class _TaskCard extends StatelessWidget {
  const _TaskCard({required this.task, required this.store});

  final TaskItem task;
  final TaskStore store;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final readOnly = context.watch<AuthController>().readOnly;
    final priority = kPriorityColors[task.priority] ?? Brand.muted;

    return AppCard(
      onTap: () => openTaskEditor(context, task: task),
      padding: const EdgeInsets.fromLTRB(10, 12, 14, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Checkbox(
            value: task.isDone,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(7)),
            onChanged: readOnly
                ? null
                : (v) async {
                    HapticFeedback.lightImpact();
                    final error = await store.setStatus(
                        task, (v ?? false) ? 'done' : 'todo');
                    if (error != null && context.mounted) {
                      showToast(context, error, error: true);
                    }
                  },
          ),
          const SizedBox(width: 4),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  task.title,
                  style: TextStyle(
                    fontSize: 14.5,
                    fontWeight: FontWeight.w700,
                    height: 1.35,
                    decoration: task.isDone ? TextDecoration.lineThrough : null,
                    color: task.isDone
                        ? scheme.onSurfaceVariant
                        : scheme.onSurface,
                  ),
                ),
                if (task.description.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    task.description,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 12.5,
                        height: 1.35,
                        color: scheme.onSurfaceVariant),
                  ),
                ],
                const SizedBox(height: 9),
                Wrap(
                  spacing: 7,
                  runSpacing: 7,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    StatusPill(
                        label: titleize(task.priority),
                        color: priority,
                        dense: true),
                    if (task.dueDate != null)
                      StatusPill(
                        label: task.isOverdue
                            ? 'Overdue · ${dateLabel(task.dueDate)}'
                            : task.isDueToday
                                ? 'Due today'
                                : dateLabel(task.dueDate),
                        color: task.isOverdue
                            ? Brand.danger
                            : task.isDueToday
                                ? Brand.warning
                                : Brand.muted,
                        dense: true,
                      ),
                    if (task.leadName.isNotEmpty)
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.link_rounded,
                              size: 13, color: scheme.onSurfaceVariant),
                          const SizedBox(width: 3),
                          Text(
                            task.leadName,
                            style: TextStyle(
                                fontSize: 11.5, color: scheme.onSurfaceVariant),
                          ),
                        ],
                      ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          if (task.assigneeName.isNotEmpty)
            InitialsAvatar(
              text: task.assigneeName
                  .trim()
                  .split(RegExp(r'\s+'))
                  .map((p) => p.characters.first)
                  .take(2)
                  .join()
                  .toUpperCase(),
              size: 30,
            ),
        ],
      ),
    );
  }
}
