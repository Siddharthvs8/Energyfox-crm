import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../widgets/common.dart';
import 'pickers.dart';

/// Files hung off the lead itself — the web page's Attachments card. Anything
/// belonging to a *stage* (customer documents, site photos) goes through the
/// site visit instead, which is where the paperwork is inherited from.
class AttachmentsCard extends StatefulWidget {
  const AttachmentsCard({
    super.key,
    required this.leadId,
    required this.readOnly,
    required this.invoiceUrl,
  });

  final int leadId;
  final bool readOnly;
  final String invoiceUrl;

  @override
  State<AttachmentsCard> createState() => _AttachmentsCardState();
}

class _AttachmentsCardState extends State<AttachmentsCard> {
  static const _maxBytes = 50 * 1024 * 1024;

  List<Map<String, dynamic>> _files = const [];
  bool _loading = true;
  bool _uploading = false;

  ApiClient get _api => context.read<ApiClient>();
  String get _url => '/api/leads/${widget.leadId}/attachments/';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final body = await _api.get(_url);
      if (!mounted) return;
      setState(() {
        _files = (body as List? ?? [])
            .whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList();
        _loading = false;
      });
    } on ApiException {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _add() async {
    final picked = await pickUploads(context);
    if (picked.isEmpty || !mounted) return;

    setState(() => _uploading = true);
    try {
      for (final file in picked) {
        if (file.bytes.length > _maxBytes) {
          if (mounted) {
            showToast(
              context,
              '${file.name} is over the 50 MB limit.',
              error: true,
            );
          }
          continue;
        }
        await _api.upload(
          _url,
          field: 'file',
          filename: file.name,
          bytes: file.bytes,
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final hasInvoice = widget.invoiceUrl.isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(
          title: 'Attachments',
          icon: Icons.attach_file_rounded,
          action: widget.readOnly
              ? null
              : TextButton(
                  onPressed: _uploading ? null : _add,
                  child: Text(_uploading ? 'Uploading…' : 'Add'),
                ),
        ),
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Center(
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.2),
                    ),
                  ),
                )
              else if (_files.isEmpty && !hasInvoice)
                Column(
                  children: [
                    Icon(
                      Icons.folder_open_rounded,
                      size: 30,
                      color: scheme.onSurfaceVariant,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'No attachments yet',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      'Upload files up to 50 MB',
                      style: TextStyle(
                        fontSize: 11,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                )
              else ...[
                if (hasInvoice)
                  _FileRow(
                    icon: Icons.receipt_long_rounded,
                    color: const Color(0xFFD946EF),
                    title: 'Official invoice',
                    subtitle: 'Invoice on file',
                    url: _api.absoluteMedia(widget.invoiceUrl) ?? '',
                  ),
                for (final f in _files)
                  _FileRow(
                    icon: Icons.description_outlined,
                    color: Brand.info,
                    title: '${f['file_name'] ?? 'File'}',
                    subtitle: [
                      '${f['file_size_kb'] ?? 0} KB',
                      dateLabel(
                        DateTime.tryParse('${f['uploaded_at']}')?.toLocal(),
                      ),
                      if ('${f['uploaded_by_name'] ?? ''}'.isNotEmpty)
                        '${f['uploaded_by_name']}',
                    ].join(' · '),
                    url: '${f['file_url'] ?? ''}',
                  ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _FileRow extends StatelessWidget {
  const _FileRow({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.url,
  });

  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final String url;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: url.isEmpty
          ? null
          : () =>
                launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication),
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, size: 17, color: color),
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              Icons.open_in_new_rounded,
              size: 15,
              color: scheme.onSurfaceVariant,
            ),
          ],
        ),
      ),
    );
  }
}
