import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/api_client.dart';
import '../../api/models.dart';
import '../../theme.dart';
import '../widgets/common.dart';
import 'pickers.dart';

/// The site-visit survey — the BDE's own screen, and the one the phone app
/// most needed: it is filled in on somebody's roof, not at a desk.
///
/// A port of `frontend/src/app/(crm)/leads/[id]/SiteVisitSection.tsx`, field
/// for field. The scalars save together behind Save Site Visit; documents
/// upload the moment they are picked, because losing a photo to a failed form
/// save on a 3G connection is worse than an extra round trip.

/// Everything saved as a scalar, in the order `scalarPayload` sends them.
const _textKeys = [
  'roof_type',
  'connection_type',
  'connected_load',
  'consumer_number',
  'phase',
  'building_height',
  'panel_to_inverter_distance',
  'kseb_section',
  'feasible_capacity',
  'plant_capacity',
  'transformer_feasibility',
  'neutral_link',
  'roof_access',
  'parapet_height',
  'structure_type',
  'custom_structure_height',
  'cable_panel_to_dc_db',
  'cable_inverter_to_ac_db',
  'earthing_cable_length',
  'lightning_conductor_length',
  'earthing_surface',
  'anchoring_allowed',
  'name_change',
  'loan',
  'loan_amount',
  'load_enhancement',
  'email_linked_to_itr',
  'po_signed_date',
];

/// A customer document is entered once and inherited by every slot of the same
/// kind, across the site visit and Documentation Stage 1 — so these upload to
/// the lead's shared pool rather than to this stage. Mirrors
/// `leads/document_kinds.py`; slots absent from it are stage-local.
const _slotToKind = {
  'aadhaar_card': 'aadhaar',
  'pan_card': 'pan',
  'passbook': 'passbook',
  'kseb_bill_file': 'kseb_bill',
  'land_tax': 'land_tax',
  'ownership_certificate': 'ownership_certificate',
  'building_certificate': 'building_certificate',
  'customer_passport_photo': 'customer_photo',
  'itr_report': 'itr',
  'loan_document': 'loan_document',
  'purchase_order': 'purchase_order',
};

const _rccSubtypes = [
  ('flat', 'Flat'),
  ('slope', 'Slope'),
  ('tiled', 'Tiled'),
  ('non_linear', 'Non linear'),
];

const _photoSlots = [
  ('photo_site', 'Site photos'),
  ('photo_meterbox', 'Meter box'),
  ('photo_earthing', 'Earthing'),
  ('photo_directional', 'Directional'),
  ('photo_hand_sketch', 'Hand sketch'),
  ('photo_feasibility_report', 'Site feasibility report'),
];

/// An ITR report is only asked for on loans above this.
const _itrRequiredAbove = 200000;

class SiteVisitScreen extends StatefulWidget {
  const SiteVisitScreen({super.key, required this.lead});

  final Lead lead;

  @override
  State<SiteVisitScreen> createState() => _SiteVisitScreenState();
}

class _SiteVisitScreenState extends State<SiteVisitScreen> {
  final _values = <String, String>{for (final k in _textKeys) k: ''};
  final _controllers = <String, TextEditingController>{};
  final _priceCtl = TextEditingController();
  final _discountCtl = TextEditingController();

  List<String> _rccTypes = [];
  List<Map<String, dynamic>> _documents = const [];
  String _productPrice = '';
  String _discount = '';
  String _productName = '';
  bool _complete = false;

  bool _loading = true;
  bool _saving = false;
  bool _dirty = false;
  String? _uploading;
  String? _error;

  /// Did anything actually change on the server? The page behind reloads only
  /// when it did.
  bool _changedAnything = false;

  ApiClient get _api => context.read<ApiClient>();
  String get _url => '/api/leads/${widget.lead.id}/site-visit/';
  bool get _canEdit => widget.lead.canEditSiteVisit;

  double get _priceNum => double.tryParse(_productPrice) ?? 0;
  double get _discountNum => double.tryParse(_discount) ?? 0;
  bool get _overDiscounted => _discountNum > _priceNum;
  double get _computedDeal =>
      (_priceNum - _discountNum) < 0 ? 0 : _priceNum - _discountNum;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    _priceCtl.dispose();
    _discountCtl.dispose();
    super.dispose();
  }

  TextEditingController _controllerFor(String key) => _controllers.putIfAbsent(
    key,
    () => TextEditingController(text: _values[key] ?? ''),
  );

  Future<void> _load() async {
    try {
      final body = await _api.get(_url);
      if (!mounted) return;
      final data = (body as Map?)?.cast<String, dynamic>() ?? {};
      setState(() {
        for (final k in _textKeys) {
          final v = data[k];
          _values[k] = v == null ? '' : '$v';
          // A controller that already exists must follow the server, or a
          // reload after a save would leave the old text on screen.
          if (_controllers.containsKey(k)) _controllers[k]!.text = _values[k]!;
        }
        _rccTypes = (data['rcc_roof_types'] as List? ?? [])
            .map((e) => '$e')
            .toList();
        _complete = data['site_visit_complete'] == true;
        _productPrice = _money(data['product_price']);
        _discount = _money(data['discount']);
        _priceCtl.text = _productPrice;
        _discountCtl.text = _discount;
        _productName = '${data['product_name'] ?? ''}';
        _documents = (data['documents'] as List? ?? [])
            .whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList();
        _loading = false;
        _dirty = false;
        _error = null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  /// "150000.00" in a number box is noise, and it makes the field look edited
  /// the moment it loads.
  static String _money(dynamic v) {
    if (v == null || '$v'.isEmpty) return '';
    final n = double.tryParse('$v');
    if (n == null) return '$v';
    return n == n.roundToDouble() ? n.toInt().toString() : n.toString();
  }

  void _set(String key, String value) {
    _values[key] = value;
    if (!_dirty) setState(() => _dirty = true);
  }

  Map<String, dynamic> get _payload => {
    for (final k in _textKeys) k: _values[k] ?? '',
    // Every other key is a CharField, where '' is valid. This one is a
    // date: an empty string is not, so a cleared date goes as null.
    'po_signed_date': (_values['po_signed_date'] ?? '').isEmpty
        ? null
        : _values['po_signed_date'],
    'rcc_roof_types': _rccTypes,
    'site_visit_complete': _complete,
    // The deal value is not sent: the server derives it from these two,
    // and posting a third figure would only give it something to disagree
    // with.
    'product_price': _productPrice.isEmpty ? '0' : _productPrice,
    'discount': _discount.isEmpty ? '0' : _discount,
  };

  Future<void> _save({bool silent = false}) async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      final body = await _api.patch(_url, _payload);
      _changedAnything = true;
      if (!mounted) return;
      final data = (body as Map?)?.cast<String, dynamic>() ?? {};
      await _load();
      if (!mounted) return;
      if (!silent) showToast(context, 'Site visit saved.');
      if (data['po_just_signed'] == true) _showPoPrompt();
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _showPoPrompt() {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Purchase order signed'),
        content: const Text(
          'Site visit saved. The KSEB feasibility is now due within 2 days of '
          'the PO date — take it from the Feasibility module.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  Future<void> _pickPoDate() async {
    final current = DateTime.tryParse(_values['po_signed_date'] ?? '');
    final picked = await showDatePicker(
      context: context,
      initialDate: current ?? DateTime.now(),
      firstDate: DateTime(2015),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked == null) return;
    final text =
        '${picked.year.toString().padLeft(4, '0')}-'
        '${picked.month.toString().padLeft(2, '0')}-'
        '${picked.day.toString().padLeft(2, '0')}';
    setState(() => _values['po_signed_date'] = text);
    // Signing the PO starts the KSEB feasibility clock, so it does not wait
    // behind Save Site Visit.
    await _save(silent: true);
    if (mounted) showToast(context, 'PO signed date saved.');
  }

  // ── Documents ─────────────────────────────────────────────────────────────

  Future<void> _addDocs(String docType) async {
    final files = await pickUploads(context);
    if (files.isEmpty || !mounted) return;

    final kind = _slotToKind[docType];
    final path = kind == null
        ? '/api/leads/${widget.lead.id}/site-visit/documents/'
        : '/api/leads/${widget.lead.id}/shared-documents/';

    setState(() => _uploading = docType);
    var any = false;
    try {
      for (final f in files) {
        try {
          await _api.upload(
            path,
            field: 'file',
            filename: f.name,
            bytes: f.bytes,
            fields: kind == null ? {'doc_type': docType} : {'kind': kind},
          );
          any = true;
        } on ApiException catch (e) {
          if (mounted) {
            showToast(context, '${f.name}: ${e.message}', error: true);
          }
        }
      }
    } finally {
      if (mounted) setState(() => _uploading = null);
    }
    if (any) {
      _changedAnything = true;
      await _refreshDocuments();
    }
  }

  /// Re-pull only the document list, so a shared document re-merges across
  /// every slot of its kind without clobbering unsaved text in the form.
  Future<void> _refreshDocuments() async {
    try {
      final body = await _api.get(_url);
      if (!mounted) return;
      setState(() {
        _documents = ((body as Map?)?['documents'] as List? ?? [])
            .whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList();
      });
    } on ApiException {
      // Keep what is on screen.
    }
  }

  Future<void> _deleteDoc(Map<String, dynamic> doc) async {
    final ok = await confirm(
      context,
      title: 'Delete this file?',
      message: doc['shared'] == true
          ? 'It is the customer\'s only copy — every stage that shows it '
                'loses it too.'
          : "This can't be undone.",
      danger: true,
      confirmLabel: 'Delete',
    );
    if (!ok) return;
    final path = doc['shared'] == true
        ? '/api/leads/${widget.lead.id}/shared-documents/${doc['id']}/'
        : '/api/leads/${widget.lead.id}/site-visit/documents/${doc['id']}/';
    try {
      await _api.delete(path);
      _changedAnything = true;
      await _refreshDocuments();
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    }
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final roofType = _values['roof_type'] ?? '';
    final loanAmount =
        double.tryParse(
          (_values['loan_amount'] ?? '').replaceAll(RegExp(r'[^0-9.]'), ''),
        ) ??
        0;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        final navigator = Navigator.of(context);
        if (_dirty) {
          final leave = await confirm(
            context,
            title: 'Leave without saving?',
            message: 'The details you typed are not on the server yet.',
            confirmLabel: 'Discard',
            danger: true,
          );
          if (!leave) return;
        }
        navigator.pop(_changedAnything);
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Site visit'),
          bottom: PreferredSize(
            preferredSize: const Size.fromHeight(20),
            child: Padding(
              padding: const EdgeInsets.only(left: 16, bottom: 10),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  widget.lead.name.isEmpty ? 'Lead' : widget.lead.name,
                  style: TextStyle(
                    fontSize: 12.5,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ),
            ),
          ),
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
            ? ErrorView(message: _error!, onRetry: _load)
            : ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 40),
                children: [
                  if (!_canEdit) _viewOnlyBanner(scheme),
                  if (widget.lead.siteVisitReopened) _reopenedBanner(),

                  _group('Deal', [
                    _moneyField(
                      label: 'Product price (₹)',
                      controller: _priceCtl,
                      helper: _productName.isEmpty ? null : _productName,
                      onChanged: (v) => setState(() {
                        _productPrice = v;
                        _dirty = true;
                      }),
                    ),
                    _moneyField(
                      label: 'Discount (₹)',
                      controller: _discountCtl,
                      error: _overDiscounted
                          ? 'More than the product price — the deal cannot '
                                'be worth less than nothing.'
                          : null,
                      onChanged: (v) => setState(() {
                        _discount = v;
                        _dirty = true;
                      }),
                    ),
                    _readOnlyField(
                      label: 'Deal value',
                      value: money(_computedDeal),
                      helper: 'Price − discount. The server works it out.',
                    ),
                  ]),

                  _group('Roof', [
                    _select('roof_type', 'Roof type', const [
                      ('rcc', 'RCC'),
                      ('sheet', 'Sheet'),
                      ('mixed', 'Mixed'),
                    ]),
                    if (roofType == 'rcc') _rccPicker(),
                  ]),

                  _group('Electrical & supply', [
                    _select('connection_type', 'Connection type', const [
                      ('commercial', 'Commercial'),
                      ('residential', 'Residential'),
                    ]),
                    _text('connected_load', 'Connected load'),
                    _text(
                      'consumer_number',
                      'Consumer number',
                      digitsOnly: true,
                      maxLength: 15,
                    ),
                    _select('phase', 'Phase', const [
                      ('1ph', '1 Phase'),
                      ('3ph', '3 Phase'),
                    ]),
                    _text('building_height', 'Building height'),
                    _text(
                      'panel_to_inverter_distance',
                      'Solar panel to inverter distance',
                    ),
                    _text('kseb_section', 'KSEB section'),
                    _text('feasible_capacity', 'Feasible capacity'),
                    _text(
                      'plant_capacity',
                      'Plant capacity',
                      hint: 'e.g. 5 kW',
                    ),
                    _yesNo(
                      'transformer_feasibility',
                      'Transformer feasibility',
                    ),
                    _yesNo('neutral_link', 'Neutral link'),
                  ]),

                  // A sheet roof has no parapet and takes a custom
                  // structure regardless, so only its height is asked for.
                  _group('Roof access & structure', [
                    if (roofType == 'sheet')
                      _text(
                        'custom_structure_height',
                        'Custom structure height',
                      )
                    else ...[
                      _text('roof_access', 'Access to the roof'),
                      _text('parapet_height', 'Parapet height'),
                      _select('structure_type', 'Structure type', const [
                        ('table_top', 'Table top'),
                        ('custom', 'Custom'),
                      ]),
                      if (_values['structure_type'] == 'custom')
                        _text(
                          'custom_structure_height',
                          'Custom structure height',
                        ),
                      _yesNo('anchoring_allowed', 'Anchoring in roof allowed?'),
                    ],
                  ]),

                  _group('Cabling requirements (meters)', [
                    _text('cable_panel_to_dc_db', 'Panel to DC DB'),
                    _text('cable_inverter_to_ac_db', 'Inverter to AC DB'),
                    _text('earthing_cable_length', 'Earthing cable length'),
                    _text(
                      'lightning_conductor_length',
                      'Lightning conductor length',
                    ),
                  ]),

                  _group('Earthing', [
                    _select('earthing_surface', 'Earthing surface', const [
                      ('soil', 'Soil'),
                      ('concrete', 'Concrete'),
                      ('tile', 'Tile'),
                      ('interlock', 'Interlock'),
                    ]),
                  ]),

                  _group('Customer details', [
                    _yesNo('name_change', 'Name change'),
                    _yesNo('loan', 'Loan'),
                    _yesNo('load_enhancement', 'Load enhancement'),
                  ]),

                  _group('Customer documents', [
                    _docSlot('kseb_bill_file', 'KSEB bill'),
                    _docSlot('aadhaar_card', 'Aadhaar card'),
                    _docSlot('pan_card', 'PAN card'),
                    _docSlot('passbook', 'Passbook'),
                    // Land tax sits here rather than under Name Change
                    // because Documentation Stage 1 needs it for the loan
                    // paperwork too, and a loan customer may have no name
                    // change at all.
                    _docSlot('land_tax', 'Land tax details'),
                  ]),

                  if (_values['name_change'] == 'yes')
                    _group('Name change documents', [
                      _docSlot(
                        'ownership_certificate',
                        'Ownership certificate',
                      ),
                      _docSlot(
                        'customer_passport_photo',
                        'Customer passport photo',
                      ),
                      _docSlot('building_certificate', 'Building certificate'),
                    ]),

                  if (_values['loan'] == 'yes')
                    _group('Loan documents', [
                      _text(
                        'loan_amount',
                        'Required loan amount (₹)',
                        hint: 'e.g. 250000',
                        digitsOnly: true,
                      ),
                      _text(
                        'email_linked_to_itr',
                        'Email linked to passbook',
                        hint: 'email@example.com',
                      ),
                      _docSlot('kseb_bill_file', 'KSEB bill'),
                      _text('kseb_section', 'KSEB section'),
                      if (loanAmount > _itrRequiredAbove)
                        _docSlot('itr_report', 'ITR report')
                      else
                        Padding(
                          padding: const EdgeInsets.only(bottom: 14),
                          child: Text(
                            'An ITR report is required only for loans above '
                            '${money(_itrRequiredAbove)}.',
                            style: TextStyle(
                              fontSize: 11.5,
                              height: 1.4,
                              color: scheme.onSurfaceVariant,
                            ),
                          ),
                        ),
                    ]),

                  _group('Site visit photos', [
                    for (final slot in _photoSlots) _docSlot(slot.$1, slot.$2),
                  ]),

                  _group('Purchase order', [
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        'Uploaded once here — it appears automatically under '
                        "Documentation Stage 1's For MNRE and For Loan "
                        'sections.',
                        style: TextStyle(
                          fontSize: 11.5,
                          height: 1.4,
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                    _docSlot('purchase_order', 'Purchase order'),
                    _poDateField(scheme),
                  ]),

                  const SizedBox(height: 8),
                  _completeToggle(scheme),
                  const SizedBox(height: 14),
                  if (_canEdit)
                    FilledButton.icon(
                      onPressed: (_saving || _overDiscounted) ? null : _save,
                      icon: _saving
                          ? const SizedBox(
                              width: 17,
                              height: 17,
                              child: CircularProgressIndicator(
                                strokeWidth: 2.2,
                              ),
                            )
                          : const Icon(Icons.save_rounded, size: 19),
                      label: Text(_saving ? 'Saving…' : 'Save site visit'),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size.fromHeight(52),
                      ),
                    ),
                ],
              ),
      ),
    );
  }

  // ── Pieces ────────────────────────────────────────────────────────────────

  Widget _viewOnlyBanner(ColorScheme scheme) => Container(
    margin: const EdgeInsets.only(bottom: 16),
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
    decoration: BoxDecoration(
      color: scheme.surfaceContainerHigh,
      borderRadius: BorderRadius.circular(14),
    ),
    child: Row(
      children: [
        Icon(
          Icons.lock_outline_rounded,
          size: 18,
          color: scheme.onSurfaceVariant,
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            'View only — this site visit is signed off, or it belongs to '
            'another BDE.',
            style: TextStyle(
              fontSize: 12.5,
              height: 1.4,
              color: scheme.onSurfaceVariant,
            ),
          ),
        ),
      ],
    ),
  );

  Widget _reopenedBanner() => Container(
    margin: const EdgeInsets.only(bottom: 16),
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
    decoration: BoxDecoration(
      color: Brand.amber.withValues(alpha: 0.14),
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: Brand.amber.withValues(alpha: 0.4)),
    ),
    child: const Row(
      children: [
        Icon(Icons.lock_open_rounded, size: 18, color: Brand.amber),
        SizedBox(width: 10),
        Expanded(
          child: Text(
            'Reopened — sign off again to lock it.',
            style: TextStyle(fontSize: 12.5, height: 1.4),
          ),
        ),
      ],
    ),
  );

  Widget _group(String title, List<Widget> children) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(4, 4, 4, 10),
            child: Text(
              title.toUpperCase(),
              style: const TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.1,
                color: Brand.amber,
              ),
            ),
          ),
          AppCard(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 2),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: children,
            ),
          ),
        ],
      ),
    );
  }

  Widget _text(
    String key,
    String label, {
    String? hint,
    bool digitsOnly = false,
    int? maxLength,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextField(
        controller: _controllerFor(key),
        enabled: _canEdit,
        keyboardType: digitsOnly ? TextInputType.number : null,
        // A digits-only field drops anything else as it is typed, so a pasted
        // value with spaces or dashes lands clean rather than failing on save.
        inputFormatters: [
          if (digitsOnly) FilteringTextInputFormatter.digitsOnly,
          if (maxLength != null) LengthLimitingTextInputFormatter(maxLength),
        ],
        onChanged: (v) => _set(key, v),
        decoration: InputDecoration(labelText: label, hintText: hint),
      ),
    );
  }

  Widget _select(String key, String label, List<(String, String)> options) {
    final value = _values[key] ?? '';
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: DropdownButtonFormField<String>(
        // '' rather than null for "not answered": there is an item with that
        // value, so the field shows the em dash instead of going blank.
        initialValue: value,
        isExpanded: true,
        decoration: InputDecoration(labelText: label),
        items: [
          const DropdownMenuItem(value: '', child: Text('—')),
          for (final o in options)
            DropdownMenuItem(value: o.$1, child: Text(o.$2)),
        ],
        onChanged: _canEdit
            ? (v) => setState(() {
                _values[key] = v ?? '';
                _dirty = true;
              })
            : null,
      ),
    );
  }

  Widget _yesNo(String key, String label) =>
      _select(key, label, const [('yes', 'Yes'), ('no', 'No')]);

  Widget _moneyField({
    required String label,
    required TextEditingController controller,
    required ValueChanged<String> onChanged,
    String? helper,
    String? error,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextField(
        controller: controller,
        enabled: _canEdit,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        onChanged: onChanged,
        decoration: InputDecoration(
          labelText: label,
          helperText: helper,
          errorText: error,
          errorMaxLines: 3,
        ),
      ),
    );
  }

  Widget _readOnlyField({
    required String label,
    required String value,
    String? helper,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          helperText: helper,
          filled: true,
        ),
        child: Text(
          value,
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
        ),
      ),
    );
  }

  Widget _rccPicker() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const FieldLabel('RCC roof type (choose any)'),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final o in _rccSubtypes)
                FilterChip(
                  label: Text(o.$2),
                  selected: _rccTypes.contains(o.$1),
                  onSelected: _canEdit
                      ? (on) => setState(() {
                          on ? _rccTypes.add(o.$1) : _rccTypes.remove(o.$1);
                          _dirty = true;
                        })
                      : null,
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _poDateField(ColorScheme scheme) {
    final value = _values['po_signed_date'] ?? '';
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const FieldLabel('PO signed date'),
          OutlinedButton.icon(
            onPressed: _canEdit ? _pickPoDate : null,
            icon: const Icon(Icons.event_outlined, size: 18),
            label: Text(
              value.isEmpty
                  ? 'Pick a date'
                  : dateLabel(DateTime.tryParse(value)),
            ),
            style: OutlinedButton.styleFrom(
              minimumSize: const Size.fromHeight(48),
              alignment: Alignment.centerLeft,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Saves immediately and adds this lead to KSEB Feasibility.',
            style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  Widget _completeToggle(ColorScheme scheme) {
    return AppCard(
      child: Row(
        children: [
          Checkbox(
            value: _complete,
            onChanged: _canEdit
                ? (v) => setState(() {
                    _complete = v ?? false;
                    _dirty = true;
                  })
                : null,
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Site visit complete',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: _complete ? Brand.success : scheme.onSurface,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  'Tick this, save, then push the lead to documentation.',
                  style: TextStyle(
                    fontSize: 11.5,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// One document slot: every file already uploaded against this doc_type,
  /// plus a way to add more. Uploads and deletes take effect immediately.
  Widget _docSlot(String docType, String label) {
    final scheme = Theme.of(context).colorScheme;
    final mine = _documents.where((d) => d['doc_type'] == docType).toList();
    final busy = _uploading == docType;

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          FieldLabel(label),
          for (final doc in mine)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                children: [
                  Icon(
                    Icons.insert_drive_file_outlined,
                    size: 15,
                    color: Brand.success,
                  ),
                  const SizedBox(width: 7),
                  Expanded(
                    child: InkWell(
                      onTap: () => _openDoc(doc),
                      child: Text(
                        _fileName(doc),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: Brand.success,
                          decoration: TextDecoration.underline,
                        ),
                      ),
                    ),
                  ),
                  if (_canEdit)
                    IconButton(
                      onPressed: () => _deleteDoc(doc),
                      visualDensity: VisualDensity.compact,
                      constraints: const BoxConstraints(),
                      padding: const EdgeInsets.all(6),
                      icon: Icon(
                        Icons.close_rounded,
                        size: 16,
                        color: scheme.error,
                      ),
                    ),
                ],
              ),
            ),
          const SizedBox(height: 4),
          OutlinedButton.icon(
            onPressed: (!_canEdit || busy) ? null : () => _addDocs(docType),
            icon: busy
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.add_rounded, size: 17),
            label: Text(busy ? 'Uploading…' : 'Add file(s)'),
            style: OutlinedButton.styleFrom(
              minimumSize: const Size(140, 40),
              visualDensity: VisualDensity.compact,
            ),
          ),
        ],
      ),
    );
  }

  String _fileName(Map<String, dynamic> doc) {
    final raw = '${doc['file'] ?? ''}';
    final name = Uri.decodeComponent(raw.split('/').last);
    return name.isEmpty ? 'file' : name;
  }

  Future<void> _openDoc(Map<String, dynamic> doc) async {
    final url = _api.absoluteMedia('${doc['file'] ?? ''}');
    if (url == null) return;
    final ok = await launchUrl(
      Uri.parse(url),
      mode: LaunchMode.externalApplication,
    );
    if (!ok && mounted) {
      showToast(context, 'Nothing on this device can open that.', error: true);
    }
  }
}
