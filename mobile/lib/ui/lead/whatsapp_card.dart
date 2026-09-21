import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../widgets/common.dart';

/// The WhatsApp thread with this customer, sent through the CRM rather than
/// off somebody's own handset — so the conversation stays on the lead when the
/// person handling it changes.
class WhatsAppCard extends StatefulWidget {
  const WhatsAppCard({super.key, required this.leadId, required this.readOnly});

  final int leadId;
  final bool readOnly;

  @override
  State<WhatsAppCard> createState() => _WhatsAppCardState();
}

class _WhatsAppCardState extends State<WhatsAppCard> {
  final _draft = TextEditingController();

  List<Map<String, dynamic>> _messages = const [];
  bool _loading = true;
  bool _sending = false;

  ApiClient get _api => context.read<ApiClient>();

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
      final body = await _api.get('/api/whatsapp/messages/', {
        'lead': widget.leadId,
      });
      if (!mounted) return;
      setState(() {
        _messages = (body is List ? body : (body?['results'] as List? ?? []))
            .whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList();
        _loading = false;
      });
    } on ApiException {
      // A workspace with WhatsApp switched off answers 403 here. That is not
      // an error worth shouting about — the panel just stays empty.
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _send() async {
    final text = _draft.text.trim();
    if (text.isEmpty || _sending) return;
    setState(() => _sending = true);
    try {
      await _api.post('/api/whatsapp/send/', {
        'lead_id': widget.leadId,
        'kind': 'text',
        'text': text,
      });
      _draft.clear();
      await _load();
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(
          title: 'WhatsApp',
          icon: Icons.chat_bubble_outline_rounded,
          action: _messages.isEmpty
              ? null
              : Text(
                  '${_messages.length}',
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
              else if (_messages.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Center(
                    child: Text(
                      'No WhatsApp messages yet.',
                      style: TextStyle(
                        fontSize: 13.5,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                )
              else
                ConstrainedBox(
                  // The newest message is at the bottom, as in every other
                  // chat: the list arrives newest-first and is reversed.
                  constraints: const BoxConstraints(maxHeight: 320),
                  child: SingleChildScrollView(
                    reverse: true,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        for (final m in _messages.reversed) _Bubble(message: m),
                      ],
                    ),
                  ),
                ),
              if (!widget.readOnly) ...[
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _draft,
                        textCapitalization: TextCapitalization.sentences,
                        onSubmitted: (_) => _send(),
                        decoration: const InputDecoration(
                          hintText: 'Type a WhatsApp message…',
                        ),
                      ),
                    ),
                    const SizedBox(width: 9),
                    FilledButton(
                      onPressed: _sending ? null : _send,
                      style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF25D366),
                        foregroundColor: Colors.white,
                        minimumSize: const Size(64, 50),
                      ),
                      child: _sending
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Icon(Icons.send_rounded, size: 19),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  'Free text reaches contacts who messaged in the last 24h. '
                  'For first contact, use a template (Automations / Bulk).',
                  style: TextStyle(
                    fontSize: 11,
                    height: 1.4,
                    color: scheme.onSurfaceVariant,
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

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});

  final Map<String, dynamic> message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final outgoing = '${message['direction']}' == 'out';
    final kind = '${message['kind']}';
    final text = '${message['text'] ?? ''}';
    final body = kind == 'template'
        ? '[template: ${message['template_name']}]${text.isEmpty ? '' : ' $text'}'
        : text;
    final at = DateTime.tryParse('${message['created_at']}')?.toLocal();

    return Align(
      alignment: outgoing ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.62,
        ),
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.fromLTRB(12, 9, 12, 8),
        decoration: BoxDecoration(
          color: outgoing
              ? const Color(0xFF25D366).withValues(alpha: 0.18)
              : scheme.surfaceContainerHigh,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(14),
            topRight: const Radius.circular(14),
            bottomLeft: Radius.circular(outgoing ? 14 : 4),
            bottomRight: Radius.circular(outgoing ? 4 : 14),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(body, style: const TextStyle(fontSize: 13.5, height: 1.4)),
            const SizedBox(height: 3),
            Text(
              [
                dateTimeLabel(at),
                if (outgoing) '${message['status'] ?? ''}',
              ].where((s) => s.isNotEmpty).join(' · '),
              style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}
