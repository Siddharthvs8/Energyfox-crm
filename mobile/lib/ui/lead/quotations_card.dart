import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../widgets/common.dart';

const _statusColors = {
  'draft': Brand.muted,
  'sent': Brand.info,
  'accepted': Brand.success,
  'declined': Brand.danger,
  'converted': Color(0xFF6366F1),
};

/// Quotations raised for this customer.
///
/// Listed natively because a BDE needs to know what was offered and for how
/// much while standing in front of the customer. Building one is a different
/// job — spec lines, cost heads, price variants — and it stays in the browser,
/// on the same form the Inventory module uses, rather than becoming a second,
/// thinner version of it that quietly leaves fields out.
class QuotationsCard extends StatefulWidget {
  const QuotationsCard({
    super.key,
    required this.leadId,
    required this.readOnly,
    required this.customerEmail,
  });

  final int leadId;
  final bool readOnly;
  final String customerEmail;

  @override
  State<QuotationsCard> createState() => _QuotationsCardState();
}

class _QuotationsCardState extends State<QuotationsCard> {
  List<Map<String, dynamic>> _rows = const [];
  bool _loading = true;

  ApiClient get _api => context.read<ApiClient>();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      // scope=all: an offer that became an order is still this customer's
      // paperwork, and a BDE cannot open Inventory to find it.
      final body = await _api.get('/api/quotations/', {
        'lead': widget.leadId,
        'scope': 'all',
      });
      if (!mounted) return;
      setState(() {
        _rows = (body is List ? body : (body?['results'] as List? ?? []))
            .whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList();
        _loading = false;
      });
    } on ApiException {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openInBrowser(String path) async {
    final ok = await launchUrl(
      Uri.parse('${_api.baseUrl}$path'),
      mode: LaunchMode.externalApplication,
    );
    if (!ok && mounted) {
      showToast(context, 'Could not open a browser.', error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(
          title: 'Quotations',
          icon: Icons.request_quote_outlined,
          action: widget.readOnly
              ? null
              : TextButton(
                  onPressed: () => _openInBrowser('/quotations'),
                  child: const Text('New'),
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
              else if (_rows.isEmpty)
                Text(
                  'No quotations for this customer yet.',
                  style: TextStyle(
                    fontSize: 13.5,
                    color: scheme.onSurfaceVariant,
                  ),
                )
              else
                for (var i = 0; i < _rows.length; i++) ...[
                  if (i > 0) Divider(color: scheme.outlineVariant, height: 20),
                  _QuotationRow(
                    row: _rows[i],
                    onOpen: () => _openInBrowser('/quotations'),
                  ),
                ],
            ],
          ),
        ),
      ],
    );
  }
}

class _QuotationRow extends StatelessWidget {
  const _QuotationRow({required this.row, required this.onOpen});

  final Map<String, dynamic> row;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isOrder = row['is_order'] == true;
    final status = '${row['status'] ?? ''}';
    // An offer that has been invoiced still reads "converted" in `status`;
    // once it is an order that is the fact worth showing instead.
    final label = isOrder
        ? 'Converted'
        : (status == 'converted' ? 'Invoiced' : titleize(status));
    final color = isOrder
        ? const Color(0xFF6366F1)
        : (_statusColors[status] ?? Brand.muted);
    final total = double.tryParse('${row['grand_total'] ?? 0}') ?? 0;

    return InkWell(
      onTap: onOpen,
      borderRadius: BorderRadius.circular(10),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${row['number'] ?? 'Quotation'}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '${row['project_name'] ?? 'No project'}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 6),
                  StatusPill(label: label, color: color, dense: true),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  money(total),
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 4),
                Icon(
                  Icons.open_in_new_rounded,
                  size: 15,
                  color: scheme.onSurfaceVariant,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
