import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api_client.dart';
import '../state/nav.dart';
import '../state/stores.dart';
import '../theme.dart';
import 'widgets/common.dart';

/// A work queue — Documentation, Accounts, Purchase, Project, any of them.
///
/// The fulfilment modules all answer with the same customer core (who they are,
/// where, what they bought, who is on it) plus their own fields, so one screen
/// lists any of them; what differs is described by the module's [QueueSource].
/// Filling the paperwork in is still the desktop app's job, and each record
/// says so — this is the field view: who is waiting, what stands where, and the
/// phone number to ring about it.
class ModuleScreen extends StatelessWidget {
  const ModuleScreen({super.key, required this.module, this.embedded = false});

  final NavModule module;

  /// True when the app frame is already drawing the bar above this — the case
  /// for a role whose only modules are queues, whose home this then is.
  final bool embedded;

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) =>
          QueueStore(context.read<ApiClient>(), module.queue!)..load(),
      child: _ModuleBody(module: module, embedded: embedded),
    );
  }
}

class _ModuleBody extends StatefulWidget {
  const _ModuleBody({required this.module, this.embedded = false});

  final NavModule module;
  final bool embedded;

  @override
  State<_ModuleBody> createState() => _ModuleBodyState();
}

class _ModuleBodyState extends State<_ModuleBody> {
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  QueueSource get _source => widget.module.queue!;

  @override
  Widget build(BuildContext context) {
    final store = context.watch<QueueStore>();
    final rows = store.visible;
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: widget.embedded ? null : AppBar(
        titleSpacing: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(widget.module.label,
                style: const TextStyle(
                    fontSize: 16.5,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.3)),
            if (store.state == LoadState.ready)
              Text(
                '${store.rows.length} ${store.rows.length == 1 ? 'record' : 'records'}',
                style: TextStyle(
                    fontSize: 10.5,
                    fontWeight: FontWeight.w600,
                    color: scheme.onSurfaceVariant),
              ),
          ],
        ),
        actions: [
          IconButton(
            onPressed: () => store.load(force: true),
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh',
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: Column(
        children: [
          if (widget.embedded)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 8, 0),
              child: Row(
                children: [
                  Text(
                    '${store.rows.length} '
                    '${store.rows.length == 1 ? 'record' : 'records'}',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: scheme.onSurfaceVariant),
                  ),
                  const Spacer(),
                  IconButton(
                    onPressed: () => store.load(force: true),
                    icon: const Icon(Icons.refresh_rounded),
                    tooltip: 'Refresh',
                  ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
            child: TextField(
              controller: _search,
              onChanged: store.search,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: 'Search this queue…',
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
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => store.load(force: true),
              child: _body(store, rows),
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(QueueStore store, List<Map<String, dynamic>> rows) {
    if (store.state == LoadState.loading && store.rows.isEmpty) {
      return const ListSkeleton();
    }
    if (store.state == LoadState.failed) {
      return ListView(children: [
        SizedBox(
          height: 380,
          child: ErrorView(
            message: store.error ?? 'Could not load ${widget.module.label}.',
            onRetry: () => store.load(force: true),
          ),
        ),
      ]);
    }
    if (rows.isEmpty) {
      return ListView(children: [
        SizedBox(
          height: 380,
          child: EmptyState(
            icon: store.query.isNotEmpty
                ? Icons.search_off_rounded
                : widget.module.icon,
            title: store.query.isNotEmpty
                ? 'No match for "${store.query}"'
                : 'Nothing in ${widget.module.label}',
            message: store.query.isNotEmpty
                ? 'Try a name, a phone number or a place.'
                : 'Customers show up here as they reach this stage.',
          ),
        ),
      ]);
    }
    return ListView.separated(
      physics:
          const AlwaysScrollableScrollPhysics(parent: BouncingScrollPhysics()),
      padding: const EdgeInsets.fromLTRB(16, 2, 16, 28),
      itemCount: rows.length + (store.hasMore ? 1 : 0),
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, i) {
        if (i == rows.length) {
          return Padding(
            padding: const EdgeInsets.only(top: 14),
            child: store.loadingMore
                ? const Center(
                    child: SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(strokeWidth: 2.2),
                    ),
                  )
                : OutlinedButton(
                    onPressed: store.loadMore,
                    child: Text('Load more (${rows.length} of ${store.total})'),
                  ),
          );
        }
        return _QueueCard(
          row: QueueRow(rows[i], _source),
          onTap: () {
            HapticFeedback.selectionClick();
            Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => ModuleRecordScreen(
                module: widget.module,
                row: QueueRow(rows[i], _source),
              ),
            ));
          },
        );
      },
    );
  }
}

/// One row of a queue, read through the module's [QueueSource].
///
/// The endpoints differ in the details — a name arrives split in two here and
/// joined there, the date is "pushed" in one module and "scheduled" in the next
/// — so every reading falls back through the shapes they actually use rather
/// than assuming one.
class QueueRow {
  QueueRow(this.raw, this.source);

  final Map<String, dynamic> raw;
  final QueueSource source;

  String _str(String key) {
    final v = raw[key];
    return v == null ? '' : v.toString();
  }

  int? get leadId {
    final v = raw['id'];
    return v is int ? v : int.tryParse(v?.toString() ?? '');
  }

  String get name {
    final joined = '${_str('first_name')} ${_str('last_name')}'.trim();
    for (final candidate in [
      joined,
      _str('name'),
      _str('customer_name'),
      _str('lead_name'),
    ]) {
      if (candidate.isNotEmpty && candidate != 'null') return candidate;
    }
    return 'Unnamed';
  }

  String get phone =>
      [_str('phone'), _str('lead_phone')].firstWhere((s) => s.isNotEmpty,
          orElse: () => '');

  String get email => _str('email');

  String get place => [_str('location'), _str('place'), _str('district')]
      .where((s) => s.isNotEmpty)
      .take(2)
      .join(' · ');

  String get product =>
      [_str('product_name'), _str('product')].firstWhere((s) => s.isNotEmpty,
          orElse: () => '');

  double get value {
    final v = raw['value'];
    if (v is num) return v.toDouble();
    return double.tryParse(v?.toString() ?? '') ?? 0;
  }

  String get assignee => source.assigneeKey == null
      ? _str('bde_name')
      : _str(source.assigneeKey!);

  String get assigneeLabel => source.assigneeLabel ?? 'BDE';

  DateTime? get date =>
      DateTime.tryParse(_str(source.dateKey))?.toLocal();

  bool get done => source.doneKey != null && raw[source.doneKey!] == true;

  /// A lead that was trashed leaves its module row behind, and its page will
  /// not open — the web queues flag those rather than letting someone tap into
  /// a dead end, and so does this.
  bool get leadDeleted => raw['lead_deleted'] == true;

  String get initials {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.length == 1) {
      return parts.first.characters.take(2).toString().toUpperCase();
    }
    return (parts.first.characters.first + parts.last.characters.first)
        .toUpperCase();
  }
}

class _QueueCard extends StatelessWidget {
  const _QueueCard({required this.row, required this.onTap});

  final QueueRow row;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.fromLTRB(14, 13, 14, 13),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InitialsAvatar(text: row.initials, size: 44),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        row.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 15.5,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.2),
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (row.leadDeleted)
                      const StatusPill(
                          label: 'Deleted', color: Brand.danger, dense: true)
                    else if (row.source.doneKey != null)
                      StatusPill(
                        label: row.done ? 'Done' : 'Pending',
                        color: row.done ? Brand.success : Brand.amber,
                        dense: true,
                      ),
                  ],
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    if (row.phone.isNotEmpty) ...[
                      Icon(Icons.call_rounded,
                          size: 13, color: scheme.onSurfaceVariant),
                      const SizedBox(width: 4),
                      Text(row.phone,
                          style: TextStyle(
                              fontSize: 12.5,
                              fontWeight: FontWeight.w600,
                              color: scheme.onSurfaceVariant)),
                    ],
                    if (row.place.isNotEmpty) ...[
                      if (row.phone.isNotEmpty)
                        Text('  ·  ',
                            style: TextStyle(color: scheme.onSurfaceVariant)),
                      Flexible(
                        child: Text(
                          row.place,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              fontSize: 12.5, color: scheme.onSurfaceVariant),
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 9),
                Row(
                  children: [
                    if (row.value > 0) ...[
                      Text(moneyShort(row.value),
                          style: const TextStyle(
                              fontSize: 13, fontWeight: FontWeight.w800)),
                      const SizedBox(width: 10),
                    ],
                    if (row.assignee.isNotEmpty)
                      Flexible(
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.person_outline_rounded,
                                size: 13, color: scheme.onSurfaceVariant),
                            const SizedBox(width: 3),
                            Flexible(
                              child: Text(
                                row.assignee,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                    fontSize: 12,
                                    color: scheme.onSurfaceVariant),
                              ),
                            ),
                          ],
                        ),
                      ),
                    const Spacer(),
                    Text(
                      timeAgo(row.date),
                      style: TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w600,
                          color: scheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// One customer as a module sees them: the contact, the module's own fields,
/// and the way to reach them.
class ModuleRecordScreen extends StatelessWidget {
  const ModuleRecordScreen({
    super.key,
    required this.module,
    required this.row,
  });

  final NavModule module;
  final QueueRow row;

  /// Fields every queue carries and the header already shows, or that mean
  /// nothing to a reader (ids, permission flags the client used to decide what
  /// to draw). Everything else is the module's own and is worth showing.
  static const _covered = {
    'id', 'first_name', 'last_name', 'name', 'customer_name', 'lead_name',
    'phone', 'lead_phone', 'email', 'location', 'place', 'district', 'value',
    'product_name', 'product', 'lead_deleted', 'can_cleanup',
  };

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fields = <MapEntry<String, String>>[
      for (final e in row.raw.entries)
        if (!_covered.contains(e.key) &&
            !e.key.startsWith('can_') &&
            e.value != null &&
            e.value is! Map &&
            e.value is! List &&
            e.value.toString().isNotEmpty)
          MapEntry(titleize(e.key), _readable(e.value)),
    ];

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(title: Text(module.label)),
      body: ListView(
        physics:
            const AlwaysScrollableScrollPhysics(parent: BouncingScrollPhysics()),
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 40),
        children: [
          AppCard(
            child: Column(
              children: [
                Row(
                  children: [
                    InitialsAvatar(text: row.initials, size: 52),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(row.name,
                              style: const TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: -0.4)),
                          if (row.place.isNotEmpty) ...[
                            const SizedBox(height: 3),
                            Text(row.place,
                                style: TextStyle(
                                    fontSize: 12.5,
                                    color: scheme.onSurfaceVariant)),
                          ],
                        ],
                      ),
                    ),
                    if (row.source.doneKey != null)
                      StatusPill(
                        label: row.done ? 'Done' : 'Pending',
                        color: row.done ? Brand.success : Brand.amber,
                        dense: true,
                      ),
                  ],
                ),
                if (row.value > 0 || row.product.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      if (row.value > 0)
                        Expanded(
                          child: _Stat(
                              label: 'Deal value', value: money(row.value)),
                        ),
                      if (row.product.isNotEmpty)
                        Expanded(
                          child: _Stat(label: 'Product', value: row.product),
                        ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 14),
          _Contact(row: row),
          if (fields.isNotEmpty) ...[
            const SizedBox(height: 22),
            SectionHeader(title: module.label, icon: module.icon),
            AppCard(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Column(
                children: [
                  for (var i = 0; i < fields.length; i++) ...[
                    if (i > 0) Divider(height: 1, color: scheme.outlineVariant),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 13),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            flex: 4,
                            child: Text(fields[i].key,
                                style: const TextStyle(
                                    fontSize: 13, fontWeight: FontWeight.w600)),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            flex: 5,
                            child: Text(
                              fields[i].value,
                              textAlign: TextAlign.right,
                              style: TextStyle(
                                  fontSize: 13,
                                  color: scheme.onSurfaceVariant),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
          const SizedBox(height: 20),
          OutlinedButton.icon(
            onPressed: () => _openInBrowser(context),
            icon: const Icon(Icons.open_in_new_rounded, size: 18),
            label: const Text('Open in the web app'),
            style: OutlinedButton.styleFrom(minimumSize: const Size(0, 48)),
          ),
          const SizedBox(height: 8),
          Text(
            'Uploads and sign-offs for this stage are filled in on the web app, '
            'where the paperwork they involve belongs.',
            textAlign: TextAlign.center,
            style: TextStyle(
                fontSize: 11.5, height: 1.5, color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  /// A date reads as a date, a yes/no as a yes/no — the rest as it came.
  static String _readable(Object value) {
    if (value is bool) return value ? 'Yes' : 'No';
    final text = value.toString();
    final date = DateTime.tryParse(text);
    if (date != null && text.length >= 10) {
      return text.length <= 10 ? dateLabel(date) : dateTimeLabel(date.toLocal());
    }
    if (value is num && value % 1 == 0 && value.abs() >= 1000) {
      return money(value);
    }
    return text;
  }

  Future<void> _openInBrowser(BuildContext context) async {
    final base = context.read<ApiClient>().baseUrl;
    final messenger = ScaffoldMessenger.of(context);
    final id = row.leadId;
    final path = id == null ? module.path : '${module.path}/$id';
    final ok = base.isNotEmpty &&
        await launchUrl(Uri.parse('$base$path'),
            mode: LaunchMode.externalApplication);
    if (!ok) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Could not open a browser.')),
      );
    }
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label.toUpperCase(),
            style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.6,
                color: scheme.onSurfaceVariant)),
        const SizedBox(height: 3),
        Text(value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w800)),
      ],
    );
  }
}

/// Ring, message or write to the customer, from wherever in the pipeline they
/// have got to.
class _Contact extends StatelessWidget {
  const _Contact({required this.row});

  final QueueRow row;

  @override
  Widget build(BuildContext context) {
    final hasPhone = row.phone.isNotEmpty;
    final hasEmail = row.email.isNotEmpty;
    if (!hasPhone && !hasEmail) return const SizedBox.shrink();

    return Row(
      children: [
        if (hasPhone) ...[
          Expanded(
            child: _ContactButton(
              icon: Icons.call_rounded,
              label: 'Call',
              onTap: () => _open(context, 'tel:${row.phone}'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: _ContactButton(
              icon: Icons.chat_rounded,
              label: 'WhatsApp',
              onTap: () => _open(context, 'https://wa.me/${_wa(row.phone)}'),
            ),
          ),
        ],
        if (hasEmail) ...[
          if (hasPhone) const SizedBox(width: 10),
          Expanded(
            child: _ContactButton(
              icon: Icons.mail_outline_rounded,
              label: 'Email',
              onTap: () => _open(context, 'mailto:${row.email}'),
            ),
          ),
        ],
      ],
    );
  }

  static String _wa(String phone) {
    var digits = phone.replaceAll(RegExp(r'\D'), '');
    if (digits.length == 10) digits = '91$digits';
    return digits;
  }

  Future<void> _open(BuildContext context, String url) async {
    final messenger = ScaffoldMessenger.of(context);
    final ok = await launchUrl(Uri.parse(url),
        mode: LaunchMode.externalApplication);
    if (!ok) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Nothing on this device can open that.')),
      );
    }
  }
}

class _ContactButton extends StatelessWidget {
  const _ContactButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: () {
          HapticFeedback.lightImpact();
          onTap();
        },
        borderRadius: BorderRadius.circular(14),
        child: Ink(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 13),
            child: Column(
              children: [
                Icon(icon, size: 19, color: scheme.primary),
                const SizedBox(height: 5),
                Text(label,
                    style: const TextStyle(
                        fontSize: 11.5, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
