import 'package:flutter/material.dart' hide Page;
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../api/models.dart';
import '../widgets/common.dart';

/// The hand-offs and assignments that live in the web page's header, each one
/// a sheet rather than a modal because a phone has no room for a dialogue with
/// a dropdown in it.
///
/// Every one of these returns the updated [Lead] when the server accepted the
/// change, and null when nothing happened — so a caller can refresh on a
/// change without having to ask what changed.

/// What the customer is buying.
///
/// Written through the *site visit* rather than the lead, because a BDE is
/// refused on the lead record (leads.access.can_edit_leads) and the site visit
/// is the screen they own. Picking one seeds the price from the catalogue; the
/// discount is settled in the Deal section of the site visit.
Future<bool> openProductSheet(BuildContext context, Lead lead) async {
  final api = context.read<ApiClient>();

  List<Map<String, dynamic>> products = const [];
  try {
    final body = await api.get('/api/products/');
    products = Page.from(body).items;
  } on ApiException catch (e) {
    if (!context.mounted) return false;
    showToast(context, e.message, error: true);
    return false;
  }
  if (!context.mounted) return false;

  final saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (_) => _ProductSheet(lead: lead, products: products),
  );
  return saved == true;
}

class _ProductSheet extends StatefulWidget {
  const _ProductSheet({required this.lead, required this.products});

  final Lead lead;
  final List<Map<String, dynamic>> products;

  @override
  State<_ProductSheet> createState() => _ProductSheetState();
}

class _ProductSheetState extends State<_ProductSheet> {
  late int? _choice = widget.lead.productId;
  bool _seedPrice = true;
  bool _saving = false;

  double _priceOf(int? id) {
    final p = widget.products.firstWhere(
      (e) => e['id'] == id,
      orElse: () => const <String, dynamic>{},
    );
    return double.tryParse('${p['default_price'] ?? 0}') ?? 0;
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final api = context.read<ApiClient>();
    final body = <String, dynamic>{'product': _choice};
    if (_choice != null && _seedPrice) {
      body['product_price'] = _priceOf(_choice).toString();
    }
    try {
      await api.patch('/api/leads/${widget.lead.id}/site-visit/', body);
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final chosenPrice = _priceOf(_choice);

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.lead.productId == null ? 'Add product' : 'Edit product',
              style: const TextStyle(
                fontSize: 17.5,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'What this customer is buying. The price and any discount are '
              'set in the Deal section of the site visit.',
              style: TextStyle(
                fontSize: 12,
                height: 1.4,
                color: scheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 18),
            if (widget.products.isEmpty)
              Text(
                'No products yet. Add one under Inventory → Item Master first.',
                style: TextStyle(fontSize: 12.5, color: scheme.error),
              )
            else
              DropdownButtonFormField<int?>(
                initialValue: _choice,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Product'),
                items: [
                  const DropdownMenuItem(value: null, child: Text('— None —')),
                  for (final p in widget.products)
                    DropdownMenuItem(
                      value: p['id'] as int?,
                      child: Text(
                        '${p['name']}'
                        '${(double.tryParse('${p['default_price'] ?? 0}') ?? 0) > 0 ? ' — ${money(double.parse('${p['default_price']}'))}' : ''}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: (v) => setState(() => _choice = v),
              ),
            if (_choice != null && chosenPrice > 0) ...[
              const SizedBox(height: 8),
              CheckboxListTile(
                value: _seedPrice,
                onChanged: (v) => setState(() => _seedPrice = v ?? false),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: Text(
                  'Set the product price to ${money(chosenPrice)}, this '
                  "product's catalogue price.",
                  style: const TextStyle(fontSize: 12.5, height: 1.35),
                ),
              ),
            ],
            const SizedBox(height: 16),
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
                  : const Text('Save product'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Hand this lead to a BDE for the site visit.
Future<Lead?> openAssignSheet(
  BuildContext context, {
  required Lead lead,
  required bool documentation,
}) async {
  final api = context.read<ApiClient>();
  final listPath = documentation
      ? '/api/users/documentation-staff/'
      : '/api/users/bdes/';

  List<Map<String, dynamic>> people = const [];
  try {
    final body = await api.get(listPath);
    people = Page.from(body).items;
  } on ApiException catch (e) {
    if (!context.mounted) return null;
    showToast(context, e.message, error: true);
    return null;
  }
  if (!context.mounted) return null;

  final current = documentation ? lead.documentationStaffId : lead.bdeId;
  final picked = await showModalBottomSheet<Object?>(
    context: context,
    builder: (context) => SafeArea(
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.only(bottom: 10),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
            child: Text(
              documentation ? 'Assign documentation' : 'Assign to BDE',
              style: const TextStyle(
                fontSize: 17.5,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          if (people.isEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 16),
              child: Text(
                documentation
                    ? 'Nobody has the documentation role yet. Set one under Team first.'
                    : 'No BDEs found. Set a user\'s role to "BDE" under Team first.',
                style: TextStyle(
                  fontSize: 12.5,
                  color: Theme.of(context).colorScheme.error,
                ),
              ),
            ),
          ListTile(
            leading: const Icon(Icons.person_off_outlined),
            title: const Text('Unassigned'),
            trailing: current == null ? const Icon(Icons.check_rounded) : null,
            // A sentinel, because popping null is how the sheet says "backed
            // out" — and clearing the assignment is a real answer.
            onTap: () => Navigator.pop(context, 'clear'),
          ),
          for (final p in people)
            ListTile(
              leading: InitialsAvatar(
                text: _initials('${p['name'] ?? ''}'),
                size: 36,
              ),
              title: Text('${p['name'] ?? ''}'),
              subtitle: '${p['branch_name'] ?? ''}'.isEmpty
                  ? null
                  : Text('${p['branch_name']}'),
              trailing: current == p['id']
                  ? const Icon(Icons.check_rounded)
                  : null,
              onTap: () => Navigator.pop(context, p['id']),
            ),
        ],
      ),
    ),
  );

  if (picked == null || !context.mounted) return null;
  final value = picked == 'clear' ? null : picked;

  try {
    final body = await api.post(
      documentation
          ? '/api/leads/${lead.id}/assign-documentation/'
          : '/api/leads/${lead.id}/assign-bde/',
      documentation ? {'staff': value} : {'bde': value},
    );
    return Lead((body as Map).cast<String, dynamic>());
  } on ApiException catch (e) {
    if (context.mounted) showToast(context, e.message, error: true);
    return null;
  }
}

/// The hand-off that follows a completed site visit.
Future<Lead?> pushToDocumentation(BuildContext context, Lead lead) async {
  final ok = await confirm(
    context,
    title: 'Push to documentation?',
    message:
        'The documentation team picks this lead up and the site visit locks.',
    confirmLabel: 'Push',
  );
  if (!ok || !context.mounted) return null;

  try {
    final body = await context.read<ApiClient>().post(
      '/api/leads/${lead.id}/push-to-documentation/',
    );
    if (context.mounted) showToast(context, 'Sent to documentation.');
    return Lead((body as Map).cast<String, dynamic>());
  } on ApiException catch (e) {
    if (context.mounted) showToast(context, e.message, error: true);
    return null;
  }
}

String _initials(String name) {
  final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty);
  if (parts.isEmpty) return '?';
  if (parts.length == 1) {
    return parts.first.substring(0, 1).toUpperCase();
  }
  return (parts.first[0] + parts.last[0]).toUpperCase();
}
