import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../widgets/common.dart';

/// One note, as `/api/leads/<id>/notes/` returns it.
///
/// Notes are records of their own rather than a field on the lead, because
/// writing one is not editing the lead: the BDE who is refused on the lead
/// record can still say what they saw. `can_edit` is the server's answer about
/// *this* note — your own words, or an admin's override — so the pencil is
/// never drawn on a note the server would refuse to change.
class LeadNote {
  LeadNote(this.raw);

  final Map<String, dynamic> raw;

  int get id => int.tryParse('${raw['id']}') ?? 0;
  String get body => '${raw['body'] ?? ''}';
  String get authorName => '${raw['author_name'] ?? 'Unknown'}';
  DateTime? get createdAt =>
      DateTime.tryParse('${raw['created_at']}')?.toLocal();
  bool get edited => raw['edited_at'] != null;
  bool get canEdit => raw['can_edit'] == true;
}

class NotesCard extends StatefulWidget {
  const NotesCard({
    super.key,
    required this.leadId,
    required this.readOnly,
    this.onChanged,
  });

  final int leadId;
  final bool readOnly;

  /// A note lands on the lead's timeline too, so the page above reloads it.
  final VoidCallback? onChanged;

  @override
  State<NotesCard> createState() => _NotesCardState();
}

class _NotesCardState extends State<NotesCard> {
  final _draft = TextEditingController();

  List<LeadNote> _notes = const [];
  bool _loading = true;
  bool _adding = false;
  int? _editing;

  ApiClient get _api => context.read<ApiClient>();
  String get _url => '/api/leads/${widget.leadId}/notes/';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _draft.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final body = await _api.get(_url);
      if (!mounted) return;
      setState(() {
        _notes = (body as List? ?? [])
            .whereType<Map>()
            .map((e) => LeadNote(e.cast<String, dynamic>()))
            .toList();
        _loading = false;
      });
    } on ApiException {
      // The panel keeps whatever it had; the page's own error banner covers a
      // server that is properly down.
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _add() async {
    final text = _draft.text.trim();
    if (text.isEmpty || _adding) return;
    setState(() => _adding = true);
    try {
      await _api.post(_url, {'body': text});
      _draft.clear();
      await _load();
      widget.onChanged?.call();
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _adding = false);
    }
  }

  Future<void> _saveEdit(LeadNote note, String text) async {
    if (text.trim().isEmpty) return;
    try {
      await _api.patch('$_url${note.id}/', {'body': text.trim()});
      if (mounted) setState(() => _editing = null);
      await _load();
      widget.onChanged?.call();
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    }
  }

  Future<void> _delete(LeadNote note) async {
    final ok = await confirm(
      context,
      title: 'Delete this note?',
      message: 'It disappears from the lead and from the timeline.',
      danger: true,
      confirmLabel: 'Delete',
    );
    if (!ok) return;
    try {
      await _api.delete('$_url${note.id}/');
      await _load();
      widget.onChanged?.call();
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(
          title: 'Notes',
          icon: Icons.sticky_note_2_outlined,
          action: _notes.isEmpty
              ? null
              : Text(
                  '${_notes.length}',
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
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
              else if (_notes.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Text(
                    'No notes added yet.',
                    style: TextStyle(
                      fontSize: 13.5,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                )
              else
                for (final note in _notes)
                  _NoteTile(
                    // Keyed by the note, so deleting one does not leave the
                    // next note's text in a tile that was mid-edit.
                    key: ValueKey(note.id),
                    note: note,
                    editing: _editing == note.id,
                    onEdit: () => setState(() => _editing = note.id),
                    onCancel: () => setState(() => _editing = null),
                    onSave: (text) => _saveEdit(note, text),
                    onDelete: () => _delete(note),
                  ),
              if (!widget.readOnly) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: _draft,
                  minLines: 2,
                  maxLines: 5,
                  textCapitalization: TextCapitalization.sentences,
                  decoration: const InputDecoration(hintText: 'Add a note…'),
                ),
                const SizedBox(height: 10),
                Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton.icon(
                    onPressed: _adding ? null : _add,
                    icon: _adding
                        ? const SizedBox(
                            width: 15,
                            height: 15,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.add_rounded, size: 18),
                    label: const Text('Add note'),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _NoteTile extends StatefulWidget {
  const _NoteTile({
    super.key,
    required this.note,
    required this.editing,
    required this.onEdit,
    required this.onCancel,
    required this.onSave,
    required this.onDelete,
  });

  final LeadNote note;
  final bool editing;
  final VoidCallback onEdit;
  final VoidCallback onCancel;
  final ValueChanged<String> onSave;
  final VoidCallback onDelete;

  @override
  State<_NoteTile> createState() => _NoteTileState();
}

class _NoteTileState extends State<_NoteTile> {
  late final TextEditingController _c = TextEditingController(
    text: widget.note.body,
  );

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(_NoteTile old) {
    super.didUpdateWidget(old);
    // Reopening the editor starts from what is on the server, not from a draft
    // that was abandoned last time.
    if (widget.editing && !old.editing) _c.text = widget.note.body;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final note = widget.note;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.fromLTRB(13, 11, 13, 11),
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: widget.editing
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _c,
                  minLines: 2,
                  maxLines: 6,
                  autofocus: true,
                ),
                const SizedBox(height: 9),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: widget.onCancel,
                      child: const Text('Cancel'),
                    ),
                    const SizedBox(width: 6),
                    FilledButton(
                      onPressed: () => widget.onSave(_c.text),
                      child: const Text('Save'),
                    ),
                  ],
                ),
              ],
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  note.body,
                  style: const TextStyle(fontSize: 13.5, height: 1.45),
                ),
                const SizedBox(height: 7),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        [
                          note.authorName,
                          dateTimeLabel(note.createdAt),
                          if (note.edited) 'edited',
                        ].join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 11,
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                    if (note.canEdit) ...[
                      _MiniButton(label: 'Edit', onTap: widget.onEdit),
                      const SizedBox(width: 4),
                      _MiniButton(
                        label: 'Delete',
                        danger: true,
                        onTap: widget.onDelete,
                      ),
                    ],
                  ],
                ),
              ],
            ),
    );
  }
}

class _MiniButton extends StatelessWidget {
  const _MiniButton({
    required this.label,
    required this.onTap,
    this.danger = false,
  });

  final String label;
  final VoidCallback onTap;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11.5,
            fontWeight: FontWeight.w700,
            color: danger ? scheme.error : scheme.primary,
          ),
        ),
      ),
    );
  }
}
