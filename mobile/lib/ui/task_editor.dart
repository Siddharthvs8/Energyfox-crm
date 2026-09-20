import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../state/auth.dart';
import '../state/stores.dart';
import '../theme.dart';
import 'widgets/common.dart';

/// Create or edit a task in a sheet — a task is four fields, and a full screen
/// for four fields is a screen too many on a phone.
Future<TaskItem?> openTaskEditor(
  BuildContext context, {
  TaskItem? task,
  Lead? lead,
}) {
  return showModalBottomSheet<TaskItem>(
    context: context,
    isScrollControlled: true,
    builder: (_) => _TaskEditor(task: task, lead: lead),
  );
}

class _TaskEditor extends StatefulWidget {
  const _TaskEditor({this.task, this.lead});

  final TaskItem? task;
  final Lead? lead;

  @override
  State<_TaskEditor> createState() => _TaskEditorState();
}

class _TaskEditorState extends State<_TaskEditor> {
  final _form = GlobalKey<FormState>();
  late final _title = TextEditingController(text: widget.task?.title);
  late final _description =
      TextEditingController(text: widget.task?.description);

  late String _status = widget.task?.status ?? 'todo';
  late String _priority = widget.task?.priority ?? 'medium';
  late DateTime? _due = widget.task?.dueDate;
  late int? _assigneeId = widget.task?.assigneeId;
  bool _saving = false;

  bool get _isEdit => widget.task != null;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<LookupStore>().ensure();
      if (!_isEdit) {
        final me = context.read<AuthController>().user;
        if (me != null && _assigneeId == null) {
          setState(() => _assigneeId = me.id);
        }
      }
    });
  }

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _due ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 3),
    );
    if (picked != null) setState(() => _due = picked);
  }

  Future<void> _save() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    final payload = <String, dynamic>{
      'title': _title.text.trim(),
      'description': _description.text.trim(),
      'status': _status,
      'priority': _priority,
      'due_date': _due == null ? null : DateFormat('yyyy-MM-dd').format(_due!),
      'assignee': _assigneeId,
      if (widget.lead != null) 'lead': widget.lead!.id,
    };

    final api = context.read<ApiClient>();
    try {
      final body = _isEdit
          ? await api.patch('/api/tasks/${widget.task!.id}/', payload)
          : await api.post('/api/tasks/', payload);
      if (!mounted) return;
      final saved = TaskItem((body as Map).cast<String, dynamic>());
      context.read<TaskStore>().upsert(saved);
      HapticFeedback.mediumImpact();
      showToast(context, _isEdit ? 'Task updated.' : 'Task created.');
      Navigator.of(context).pop(saved);
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this task?'),
        content: const Text('It will be gone for everyone on the team.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Keep it')),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            style: FilledButton.styleFrom(
                backgroundColor: Brand.danger, minimumSize: const Size(90, 44)),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await context.read<ApiClient>().delete('/api/tasks/${widget.task!.id}/');
      if (!mounted) return;
      context.read<TaskStore>().remove(widget.task!.id);
      showToast(context, 'Task deleted.');
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final lookups = context.watch<LookupStore>();
    final scheme = Theme.of(context).colorScheme;
    final linkedLead = widget.lead ?? widget.task;

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SingleChildScrollView(
        child: Form(
          key: _form,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    Text(
                      _isEdit ? 'Edit task' : 'New task',
                      style: const TextStyle(
                          fontSize: 18, fontWeight: FontWeight.w800),
                    ),
                    const Spacer(),
                    if (_isEdit)
                      IconButton(
                        onPressed: _delete,
                        icon: const Icon(Icons.delete_outline_rounded),
                        color: Brand.danger,
                        tooltip: 'Delete',
                      ),
                  ],
                ),
                if (linkedLead != null) ...[
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(Icons.link_rounded,
                          size: 15, color: scheme.onSurfaceVariant),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          widget.lead?.name ?? widget.task?.leadName ?? '',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: scheme.onSurfaceVariant),
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 18),
                TextFormField(
                  controller: _title,
                  autofocus: !_isEdit,
                  textCapitalization: TextCapitalization.sentences,
                  decoration: const InputDecoration(
                      labelText: 'What needs doing? *'),
                  validator: (v) => (v == null || v.trim().isEmpty)
                      ? 'Give the task a title'
                      : null,
                ),
                const SizedBox(height: 14),
                TextFormField(
                  controller: _description,
                  maxLines: 3,
                  textCapitalization: TextCapitalization.sentences,
                  decoration: const InputDecoration(labelText: 'Details'),
                ),
                const SizedBox(height: 18),
                Text('Priority',
                    style: TextStyle(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                        color: scheme.onSurfaceVariant)),
                const SizedBox(height: 8),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'low', label: Text('Low')),
                    ButtonSegment(value: 'medium', label: Text('Medium')),
                    ButtonSegment(value: 'high', label: Text('High')),
                  ],
                  selected: {_priority},
                  showSelectedIcon: false,
                  onSelectionChanged: (s) =>
                      setState(() => _priority = s.first),
                ),
                const SizedBox(height: 18),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _pickDate,
                        icon: const Icon(Icons.event_rounded, size: 18),
                        label: Text(
                          _due == null ? 'Due date' : dateLabel(_due),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                    if (_due != null) ...[
                      const SizedBox(width: 8),
                      IconButton(
                        onPressed: () => setState(() => _due = null),
                        icon: const Icon(Icons.close_rounded),
                        tooltip: 'Clear date',
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  initialValue: _status,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Status'),
                  items: [
                    for (final s in TaskItem.statuses)
                      DropdownMenuItem(value: s.$1, child: Text(s.$2)),
                  ],
                  onChanged: (v) => setState(() => _status = v ?? 'todo'),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<int?>(
                  initialValue:
                      lookups.users.any((u) => u.id == _assigneeId)
                          ? _assigneeId
                          : null,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Assign to'),
                  items: [
                    const DropdownMenuItem<int?>(
                        value: null, child: Text('Unassigned')),
                    for (final u in lookups.users)
                      DropdownMenuItem<int?>(
                          value: u.id,
                          child:
                              Text(u.name, overflow: TextOverflow.ellipsis)),
                  ],
                  onChanged: (v) => setState(() => _assigneeId = v),
                ),
                const SizedBox(height: 22),
                FilledButton(
                  onPressed: _saving ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2.2))
                      : Text(_isEdit ? 'Save task' : 'Create task'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
