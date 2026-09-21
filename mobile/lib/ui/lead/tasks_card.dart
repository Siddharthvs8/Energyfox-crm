import 'package:flutter/material.dart' hide Page;
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../api/models.dart';
import '../../theme.dart';
import '../task_editor.dart';
import '../widgets/common.dart';

/// The tasks raised against this lead — the "Related Tasks" panel on the web
/// page. Tapping one opens the same editor the Tasks tab uses.
class RelatedTasksCard extends StatefulWidget {
  const RelatedTasksCard({
    super.key,
    required this.lead,
    required this.canAddTasks,
  });

  final Lead lead;
  final bool canAddTasks;

  @override
  State<RelatedTasksCard> createState() => RelatedTasksCardState();
}

class RelatedTasksCardState extends State<RelatedTasksCard> {
  List<TaskItem> _tasks = const [];
  bool _loading = true;

  ApiClient get _api => context.read<ApiClient>();

  @override
  void initState() {
    super.initState();
    reload();
  }

  Future<void> reload() async {
    try {
      final body = await _api.get('/api/tasks/', {'lead': widget.lead.id});
      if (!mounted) return;
      setState(() {
        _tasks = Page.from(body).items.map(TaskItem.new).toList();
        _loading = false;
      });
    } on ApiException {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(
          title: 'Related tasks',
          icon: Icons.checklist_rounded,
          action: widget.canAddTasks
              ? TextButton(
                  onPressed: () async {
                    final created = await openTaskEditor(
                      context,
                      lead: widget.lead,
                    );
                    if (created != null) reload();
                  },
                  child: const Text('Add'),
                )
              : null,
        ),
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 18),
                  child: Center(
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.2),
                    ),
                  ),
                )
              else if (_tasks.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Text(
                    'No tasks linked to this lead yet.',
                    style: TextStyle(
                      fontSize: 13.5,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                )
              else
                for (var i = 0; i < _tasks.length; i++) ...[
                  if (i > 0) Divider(color: scheme.outlineVariant, height: 18),
                  _TaskRow(
                    task: _tasks[i],
                    onTap: () async {
                      final changed = await openTaskEditor(
                        context,
                        task: _tasks[i],
                        lead: widget.lead,
                      );
                      if (changed != null) reload();
                    },
                  ),
                ],
            ],
          ),
        ),
      ],
    );
  }
}

class _TaskRow extends StatelessWidget {
  const _TaskRow({required this.task, required this.onTap});

  final TaskItem task;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final priority = switch (task.priority) {
      'high' => Brand.danger,
      'medium' => Brand.amber,
      _ => Brand.success,
    };

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: priority,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    task.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w600,
                      decoration: task.isDone
                          ? TextDecoration.lineThrough
                          : null,
                      color: task.isDone
                          ? scheme.onSurfaceVariant
                          : scheme.onSurface,
                    ),
                  ),
                  if (task.dueDate != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      task.isOverdue
                          ? 'Overdue — ${dateLabel(task.dueDate)}'
                          : 'Due ${dateLabel(task.dueDate)}',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: task.isOverdue ? FontWeight.w700 : null,
                        color: task.isOverdue
                            ? Brand.danger
                            : scheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 10),
            StatusPill(
              label: TaskItem.labelFor(task.status),
              color: kTaskStatusColors[task.status] ?? Brand.muted,
              dense: true,
            ),
          ],
        ),
      ),
    );
  }
}
