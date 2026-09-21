import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../widgets/common.dart';

/// Every outcome the CRM records, plus the raw telephony words Exotel and
/// Voxbay send back — the web page maps both, so the app has to as well or the
/// same call reads differently in the two places.
const _outcomeLabels = {
  'connected': 'Connected',
  'completed': 'Connected',
  'rnr': 'RNR',
  'no-answer': 'RNR',
  'busy': 'Busy',
  'failed': 'Busy',
  'rejected': 'Busy',
  'cancelled': 'Cancelled',
  'canceled': 'Cancelled',
  'initiated': 'Initiated',
};

Color _outcomeColor(String outcome) => switch (outcome.toLowerCase()) {
  'connected' || 'completed' => Brand.success,
  'rnr' || 'no-answer' => Brand.amber,
  'busy' || 'failed' || 'rejected' => Brand.info,
  'cancelled' || 'canceled' => Brand.danger,
  'initiated' => const Color(0xFF8B5CF6),
  _ => Brand.muted,
};

String _outcomeLabel(String outcome) =>
    _outcomeLabels[outcome.toLowerCase()] ?? titleize(outcome);

String _duration(int seconds) {
  final m = seconds ~/ 60;
  final s = seconds % 60;
  return '$m:${s.toString().padLeft(2, '0')}';
}

/// Call history and recordings for this lead, with the manual log the web page
/// offers when the dialler is not wired up.
class CallHistoryCard extends StatefulWidget {
  const CallHistoryCard({
    super.key,
    required this.leadId,
    required this.readOnly,
  });

  final int leadId;
  final bool readOnly;

  @override
  State<CallHistoryCard> createState() => CallHistoryCardState();
}

class CallHistoryCardState extends State<CallHistoryCard> {
  List<Map<String, dynamic>> _calls = const [];
  bool _loading = true;

  ApiClient get _api => context.read<ApiClient>();

  @override
  void initState() {
    super.initState();
    reload();
  }

  Future<void> reload() async {
    if (mounted) setState(() => _loading = true);
    try {
      final body = await _api.get('/api/calls/', {'lead': widget.leadId});
      if (!mounted) return;
      setState(() {
        _calls = (body is List ? body : (body?['results'] as List? ?? []))
            .whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList();
        _loading = false;
      });
    } on ApiException {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Recordings on Exotel are behind their credentials, so they come through
  /// the CRM's proxy rather than straight off their CDN.
  String _recordingUrl(Map<String, dynamic> call) {
    final url = '${call['recording_url'] ?? ''}';
    if (url.isEmpty) return '';
    if (url.contains('exotel')) {
      final token = _api.accessToken;
      return '${_api.baseUrl}/api/calls/${call['id']}/recording_proxy/'
          '${token == null ? '' : '?token=$token'}';
    }
    return url;
  }

  Future<void> _logCall({Map<String, dynamic>? existing}) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _CallLogSheet(leadId: widget.leadId, existing: existing),
    );
    if (saved == true) reload();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(
          title: 'Call history',
          icon: Icons.phone_callback_rounded,
          action: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                onPressed: _loading ? null : reload,
                visualDensity: VisualDensity.compact,
                tooltip: 'Refresh',
                icon: const Icon(Icons.refresh_rounded, size: 19),
              ),
              if (!widget.readOnly)
                TextButton(
                  onPressed: () => _logCall(),
                  child: const Text('Log call'),
                ),
            ],
          ),
        ),
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Logs and recordings of all calls with this client',
                style: TextStyle(
                  fontSize: 11.5,
                  color: scheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 12),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 14),
                  child: Center(
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.2),
                    ),
                  ),
                )
              else if (_calls.isEmpty)
                Text(
                  'No calls tracked for this lead yet.',
                  style: TextStyle(
                    fontSize: 13.5,
                    color: scheme.onSurfaceVariant,
                  ),
                )
              else
                for (final call in _calls)
                  _CallTile(
                    call: call,
                    recordingUrl: _recordingUrl(call),
                    onEdit: widget.readOnly
                        ? null
                        : () => _logCall(existing: call),
                  ),
            ],
          ),
        ),
      ],
    );
  }
}

class _CallTile extends StatelessWidget {
  const _CallTile({
    required this.call,
    required this.recordingUrl,
    required this.onEdit,
  });

  final Map<String, dynamic> call;
  final String recordingUrl;
  final VoidCallback? onEdit;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final outcome = '${call['outcome'] ?? ''}';
    final notes = '${call['notes'] ?? ''}';
    final at = DateTime.tryParse('${call['created_at']}')?.toLocal();
    final seconds = int.tryParse('${call['duration_seconds'] ?? 0}') ?? 0;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.fromLTRB(13, 11, 13, 11),
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              StatusPill(
                label: _outcomeLabel(outcome),
                color: _outcomeColor(outcome),
                dense: true,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'by ${call['user_name'] ?? 'Unknown'}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 11.5,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ),
              if (onEdit != null)
                InkWell(
                  onTap: onEdit,
                  borderRadius: BorderRadius.circular(8),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 3,
                    ),
                    child: Text(
                      'Edit',
                      style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w700,
                        color: scheme.primary,
                      ),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Icon(
                Icons.schedule_rounded,
                size: 14,
                color: scheme.onSurfaceVariant,
              ),
              const SizedBox(width: 5),
              Text(
                _duration(seconds),
                style: TextStyle(
                  fontSize: 12,
                  fontFeatures: const [],
                  color: scheme.onSurfaceVariant,
                ),
              ),
              const Spacer(),
              Text(
                dateTimeLabel(at),
                style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
              ),
            ],
          ),
          if (notes.isNotEmpty) ...[
            const SizedBox(height: 7),
            Text(
              notes,
              style: TextStyle(
                fontSize: 12.5,
                height: 1.4,
                fontStyle: FontStyle.italic,
                color: scheme.onSurfaceVariant,
              ),
            ),
          ],
          const SizedBox(height: 8),
          if (recordingUrl.isEmpty)
            Text(
              'No recording available',
              style: TextStyle(
                fontSize: 11,
                fontStyle: FontStyle.italic,
                color: scheme.onSurfaceVariant,
              ),
            )
          else
            // Handed to the system player rather than played in-app: there is
            // no audio package here, and a recording is something you listen
            // to once, not something the screen needs to own.
            OutlinedButton.icon(
              onPressed: () => launchUrl(
                Uri.parse(recordingUrl),
                mode: LaunchMode.externalApplication,
              ),
              icon: const Icon(Icons.play_circle_outline_rounded, size: 18),
              label: const Text('Play recording'),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(40),
              ),
            ),
        ],
      ),
    );
  }
}

/// Log a call by hand, or correct one already logged — the same two forms the
/// web page shows, which differ only in where they POST.
class _CallLogSheet extends StatefulWidget {
  const _CallLogSheet({required this.leadId, this.existing});

  final int leadId;
  final Map<String, dynamic>? existing;

  @override
  State<_CallLogSheet> createState() => _CallLogSheetState();
}

class _CallLogSheetState extends State<_CallLogSheet> {
  static const _outcomes = [
    ('connected', 'Connected'),
    ('rnr', 'Ring no reply'),
    ('busy', 'Busy'),
    ('cancelled', 'Cancelled'),
  ];

  late String _outcome = '${widget.existing?['outcome'] ?? 'connected'}'
      .toLowerCase();
  late final _minutes = TextEditingController(
    text:
        (((int.tryParse('${widget.existing?['duration_seconds'] ?? 0}') ??
                    0)) ~/
                60)
            .toString(),
  );
  late final _seconds = TextEditingController(
    text:
        (((int.tryParse('${widget.existing?['duration_seconds'] ?? 0}') ?? 0)) %
                60)
            .toString(),
  );
  late final _notes = TextEditingController(
    text: '${widget.existing?['notes'] ?? ''}',
  );

  bool _saving = false;

  @override
  void dispose() {
    _minutes.dispose();
    _seconds.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final api = context.read<ApiClient>();
    final connected = _outcome == 'connected';
    final total = connected
        ? (int.tryParse(_minutes.text) ?? 0) * 60 +
              (int.tryParse(_seconds.text) ?? 0)
        : 0;
    final payload = {
      'outcome': _outcome,
      'notes': _notes.text.trim(),
      'duration_seconds': total,
    };
    try {
      if (widget.existing == null) {
        await api.post('/api/calls/', {'lead': widget.leadId, ...payload});
      } else {
        await api.patch('/api/calls/${widget.existing!['id']}/', payload);
      }
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final insets = MediaQuery.of(context).viewInsets.bottom;

    return Padding(
      padding: EdgeInsets.fromLTRB(20, 18, 20, 20 + insets),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.existing == null ? 'Log a call' : 'Edit call log',
              style: const TextStyle(
                fontSize: 17.5,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 16),
            const FieldLabel('Outcome'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final o in _outcomes)
                  ChoiceChip(
                    label: Text(o.$2),
                    selected: _outcome == o.$1,
                    onSelected: (_) => setState(() => _outcome = o.$1),
                  ),
              ],
            ),
            if (_outcome == 'connected') ...[
              const SizedBox(height: 16),
              const FieldLabel('Duration'),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _minutes,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(suffixText: 'min'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextField(
                      controller: _seconds,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(suffixText: 'sec'),
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 16),
            const FieldLabel('Notes'),
            TextField(
              controller: _notes,
              minLines: 2,
              maxLines: 5,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                hintText: 'What was said, in short',
              ),
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _saving ? null : _save,
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(50),
              ),
              child: _saving
                  ? const SizedBox(
                      width: 19,
                      height: 19,
                      child: CircularProgressIndicator(strokeWidth: 2.2),
                    )
                  : const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }
}
